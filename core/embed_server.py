#!/usr/bin/env python3
"""
Dedicated embedding server for Codey-OS knowledge base indexing.

Runs nomic-embed-text-v1.5 (80 MB Q4, 2048 ctx, 768-dim) as a separate
llama-server on port 8082 — distinct from the generation server on 8080/8081.

Benefits:
- 768-dim vectors — high quality cosine similarity
- 92.6% of chunks get hybrid BM25+vector; 7.4% (>2048 tok) use BM25 fallback
- Full 3777-chunk index builds in ~1 hour on S24 Ultra (~1s/chunk)
- Never evicted by model hot-swapping in loader_v2.py

Lifecycle:
- Auto-started by daemon (_main_loop) and inference.py (_start_server)
- Auto-restarted by daemon watchdog every 30s if dead
- Stopped on daemon shutdown or codeydOS stop (pkill llama-server)

Usage:
    from core.embed_server import get_embed_server, start_embed_server
    ok = start_embed_server()   # idempotent — safe to call multiple times
"""

import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

import core.resource_gate as rg
from utils.config import CODEY_STATE_DIR, EMBED_MODEL_PATH, EMBED_SERVER_PORT, LLAMA_SERVER_BIN
from utils.logger import error, info, success, warning

# Host is always localhost
_HOST = "127.0.0.1"


class EmbedServer:
    """
    Manages a dedicated llama-server subprocess for embeddings only.

    Uses --embedding --pooling mean to expose /v1/embeddings in OAI format.
    nomic-embed-text-v1.5: 2048 ctx, 768-dim, 4 threads.
    """

    def __init__(self):
        self.model_path = EMBED_MODEL_PATH
        self.port = EMBED_SERVER_PORT
        self.process: Optional[subprocess.Popen] = None
        self._started = False
        self._slot_id: Optional[str] = None

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def start(self) -> bool:
        """Start the embed server subprocess. Idempotent."""
        # Already running as our own subprocess?
        if self.process and self.process.poll() is None and self._check_health():
            return True

        # Kill any stale llama-server occupying the embed port — it may have
        # different settings (wrong ctx, old ubatch) from a previous run.
        # Uses the raw TCP-connect check (_port_is_bound), not
        # _is_port_open() alone: _is_port_open() also requires a
        # successful /health response, so a foreign occupant that accepts
        # the connection but doesn't answer /health would make
        # _is_port_open() report "not open" and skip clearing the port
        # entirely — then Popen below would fail to bind and this method
        # would burn the full 30 s health-check loop before reporting a
        # misleading "Timeout waiting for embed server" instead of the
        # real cause.
        if self._port_is_bound():
            info(f"Stale process on port {self.port} — replacing with fresh embed server...")
            if not self._kill_port_occupant():
                # Occupant PID unknown/unkillable — do not proceed to bind
                # against a port we couldn't safely clear (see
                # _kill_port_occupant()'s docstring: never kill by name).
                error(f"embed_server: could not clear port {self.port}, aborting start")
                return False

        if not self.model_path.exists():
            warning(f"Embed model not found: {self.model_path}")
            warning("Run: bash tools/setup_skills.sh   to set up the embedding model")
            return False

        llama_bin = Path(LLAMA_SERVER_BIN)
        if not llama_bin.exists():
            error(f"llama-server binary not found: {LLAMA_SERVER_BIN}")
            return False

        info(f"Starting embed server (nomic) on port {self.port}...")

        cmd = [
            str(llama_bin),
            "-m",
            str(self.model_path),
            "--host",
            _HOST,
            "--port",
            str(self.port),
            "-c",
            "2048",  # 2k ctx — fast for 92% of chunks; rest use BM25 fallback
            "-t",
            "2",  # 2 threads for embedding (keep CPU headroom for 7B)
            "-b",
            "2048",  # logical batch size matches ctx
            "--ubatch-size",
            "2048",  # physical batch matches ctx
            "--embedding",  # enable /v1/embeddings endpoint
            "--pooling",
            "mean",  # OAI-compatible single vector per input
        ]

        log_file = CODEY_STATE_DIR / "embed-server.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)

        log_fd = open(log_file, "a")
        log_fd.write(f"\n--- embed server start: {' '.join(cmd)}\n")
        log_fd.flush()

        self.process = subprocess.Popen(
            cmd,
            stdout=log_fd,
            stderr=subprocess.STDOUT,
            preexec_fn=os.setsid if os.name != "nt" else None,
        )

        info(f"Embed server PID: {self.process.pid}, log: {log_file}")

        # Wait up to 30 s for the server to become healthy
        for _ in range(60):
            time.sleep(0.5)
            if self.process.poll() is not None:
                error(f"Embed server died (exit {self.process.poll()})")
                try:
                    with open(log_file) as f:
                        tail = f.read()[-800:]
                    error(f"Embed log tail:\n{tail}")
                except Exception:
                    pass
                return False
            if self._check_health():
                self._started = True
                success(f"Embed server ready on port {self.port}")
                # ── Resource gate: accounted-but-exempt (TODO.md 7.4 sub-task 2) ──
                # The embed server is a third, always-resident model process
                # (per this module's own docstring: "Never evicted by model
                # hot-swapping"), so it must be visible to the gate's residency
                # store for accounting/observability — but it is deliberately
                # NOT run through reserve_slot()/can_admit(): it never competes
                # for admission and must never be evicted by the gate the way
                # the 7B/1.5B are. register_slot() (unconditional, no admission
                # check) with status=RESIDENT immediately achieves exactly that:
                # visible in list_slots()/total_reserved_bytes() bookkeeping,
                # but never subject to a can_admit()/reserve_slot() denial or
                # to the two gated loaders' eviction logic.
                try:
                    self._slot_id = rg.register_slot(
                        model_id="embed",
                        cost_bytes=self.model_path.stat().st_size,
                        pid=self.process.pid,
                        port=self.port,
                        status=rg.SLOT_STATUS_RESIDENT,
                    )
                except Exception as e:
                    # Accounting-only and exempt from admission by design —
                    # a failure to register must never stop the embed server
                    # itself from starting/serving (it isn't gated on this).
                    warning(f"resource_gate: failed to register embed server slot: {e}")
                return True

        error("Timeout waiting for embed server")
        self.stop()
        return False

    def stop(self):
        """Stop the embed server subprocess."""
        if self.process:
            try:
                import signal as _signal

                if os.name != "nt":
                    try:
                        os.killpg(os.getpgid(self.process.pid), _signal.SIGTERM)
                    except ProcessLookupError:
                        self.process.terminate()
                else:
                    self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(os.getpgid(self.process.pid), _signal.SIGKILL)
                    except Exception:
                        self.process.kill()
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass
            finally:
                self.process = None
                self._started = False
                if self._slot_id:
                    try:
                        rg.release_slot(self._slot_id)
                    except Exception as e:
                        # Same posture as the registration try/except above —
                        # accounting-only, must never block the actual stop.
                        warning(f"resource_gate: failed to release embed server slot: {e}")
                    self._slot_id = None
                info("Embed server stopped")

    def is_running(self) -> bool:
        if self.process is not None and self.process.poll() is None:
            return True
        if self._started:
            return self._check_health()
        return False

    # ── Health helpers ─────────────────────────────────────────────────────────

    # TCP state 0A = LISTEN, per /proc/net/tcp's documented state codes.
    _TCP_STATE_LISTEN = "0A"

    def _find_port_occupant_pid(self) -> Optional[int]:
        """Resolve the exact PID bound to the embed port via /proc scan.

        Parses /proc/net/tcp and /proc/net/tcp6 (the occupant need not be
        our own IPv4-only llama-server) to find the LISTEN-state socket
        inode on our port, then scans /proc/*/fd for the process that owns
        that inode. Returns None if no owning PID could be positively
        identified — callers must never fall back to a name-based kill in
        that case (CLAUDE.md rule 3: never kill by bare name pattern, only
        a specific known PID).

        Prefers LISTEN rows and keeps scanning remaining matching rows if
        an earlier match's inode can't be resolved to a live PID (e.g. an
        already-closed connection sharing the port's hex suffix) — giving
        up after the first row risked spurious "unidentifiable" aborts.
        """
        try:
            port_hex = f"{self.port:04X}"
            candidates: list[tuple[str, str]] = []  # (state, inode), LISTEN first
            for proc_file in ("/proc/net/tcp", "/proc/net/tcp6"):
                try:
                    with open(proc_file) as f:
                        lines = f.readlines()
                except (FileNotFoundError, PermissionError):
                    continue
                for line in lines[1:]:  # skip header
                    parts = line.split()
                    if len(parts) < 10:
                        continue
                    local_addr, state, inode = parts[1], parts[3], parts[9]
                    if local_addr.endswith(f":{port_hex}"):
                        candidates.append((state, inode))
            # LISTEN rows first, then any other matching row as a fallback.
            candidates.sort(key=lambda c: 0 if c[0] == self._TCP_STATE_LISTEN else 1)

            for _state, inode in candidates:
                pid = self._pid_owning_inode(inode)
                if pid is not None:
                    return pid
        except Exception as e:
            warning(f"embed_server: /proc scan for port occupant failed: {e}")

        # Fallback: the /proc/net/tcp(+tcp6) scan above can be unreadable
        # on some Termux/Android configurations (permission-restricted
        # /proc/net access), or its fd-symlink match can miss. If this
        # code itself previously spawned and registered an embed-server
        # slot on this exact port (resource_gate's residency store —
        # already imported as `rg`, populated by this class's own
        # `start()`), that's a second legitimate source of a *specific,
        # known* PID — not a name-pattern guess. Still verified two ways
        # before use: the PID must be alive, AND its /proc/<pid>/cmdline
        # must actually reference the llama-server binary — PIDs recycle,
        # so a registered-but-stale PID could otherwise now belong to a
        # completely unrelated process.
        return self._find_pid_via_registered_slot()

    def _find_pid_via_registered_slot(self) -> Optional[int]:
        try:
            for slot in rg.list_slots():
                if slot.get("model_id") != "embed" or slot.get("port") != self.port:
                    continue
                pid = slot.get("pid")
                if pid is None:
                    continue
                try:
                    os.kill(pid, 0)  # liveness probe only, no signal delivered
                except ProcessLookupError:
                    continue  # PID is dead — nothing to kill, skip it
                except PermissionError:
                    # Process is alive but not ours (different UID) —
                    # deliberately NOT treated as "our embed server" the
                    # way core/resource_gate.py:_pid_alive() treats this
                    # same exception as "still alive" for reaping
                    # purposes. That function's fail-closed choice is
                    # about not wrongly reaping *accounting* state; here
                    # the stakes are a kill target, so PermissionError
                    # must not be read as confirmation this PID is our
                    # spawned llama-server — skip it, don't kill it.
                    continue
                except OSError:
                    # Unexpected OSError from kill(2) (not
                    # ProcessLookupError/PermissionError) — can't
                    # positively confirm this PID is safe to kill. Fail
                    # closed toward *not* killing (the opposite direction
                    # from _pid_alive()'s fail-closed-toward-"still
                    # alive": that function's worst case is a stale
                    # accounting entry lingering, this function's worst
                    # case would be killing the wrong process, so here
                    # "don't kill on doubt" is the safe direction).
                    continue
                if self._cmdline_is_llama_server(pid):
                    return int(pid)
        except Exception as e:
            warning(f"embed_server: registered-slot fallback lookup failed: {e}")
        return None

    @staticmethod
    def _cmdline_is_llama_server(pid: int) -> bool:
        """Guards the registered-slot fallback against a recycled PID:
        confirms /proc/<pid>/cmdline actually names the llama-server
        binary before that PID is treated as a kill target."""
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                cmdline = f.read()
            return b"llama-server" in cmdline
        except Exception:
            return False

    def _pid_owning_inode(self, inode: str) -> Optional[int]:
        """Scan /proc/*/fd for the PID holding a socket inode."""
        for pid_dir in Path("/proc").iterdir():
            if not pid_dir.name.isdigit():
                continue
            try:
                for fd in (pid_dir / "fd").iterdir():
                    link = os.readlink(str(fd))
                    if f"socket:[{inode}]" in link:
                        return int(pid_dir.name)
            except (PermissionError, OSError):
                # Another UID's process (no fd read access), or the fd/proc
                # entry vanished mid-scan (process exited) — not evidence
                # this is our occupant, just keep scanning other PIDs.
                continue
        return None

    def _kill_port_occupant(self) -> bool:
        """Kill the exact process bound to the embed port, if identifiable.

        Only ever kills a specific PID resolved by `_find_port_occupant_pid()`
        — never a bare name-pattern kill (that was NEW-83: a prior
        `pkill -9 llama-server` fallback here could hit unrelated
        llama-server processes this project doesn't own, the exact
        failure mode CLAUDE.md rule 3 exists to prevent). If the occupant
        PID can't be positively identified, this fails loudly (logs an
        error) and does not proceed to kill anything — the caller's
        subsequent bind attempt will fail with a clear error instead of
        silently killing an unrelated process.

        After killing, re-checks that the port actually came free before
        reporting success: the occupant may be a session leader (started
        with `preexec_fn=os.setsid`, same as our own `start()`) whose
        child inherited the listening socket — killing only the leader's
        PID would leave the port held, and blindly reporting success would
        let the caller burn the full bind/health-check timeout instead of
        seeing the real cause. Deliberately does NOT escalate to
        `os.killpg()` here: that would kill an entire foreign process
        group from a single resolved PID, which is broader than the one
        PID this code positively identified — the same over-reach rule 3
        exists to prevent, just at the process-group level instead of by
        name.
        """
        pid = self._find_port_occupant_pid()
        if pid is None:
            error(
                f"embed_server: port {self.port} appears occupied but the "
                f"owning PID could not be identified — refusing to kill "
                f"anything by name. Free the port manually and retry."
            )
            return False

        info(f"Killing stale embed server PID {pid} occupying port {self.port}")
        try:
            os.kill(pid, 9)
        except ProcessLookupError:
            # Already gone between discovery and kill — fine, port is free.
            pass
        except Exception as e:
            error(f"embed_server: failed to kill occupant PID {pid}: {e}")
            return False

        import time as _time

        _time.sleep(2)  # give kernel time to release the port

        if self._port_is_bound():
            # Killed the PID we found, but the port is still held — most
            # likely a child of that PID (inherited the listening socket
            # under the killed process's session) still owns it. Don't
            # loop retrying automatically: report failure loudly so the
            # caller aborts instead of proceeding to bind against a port
            # that's still occupied.
            error(
                f"embed_server: killed PID {pid} but port {self.port} is "
                f"still occupied — a child process may hold the listening "
                f"socket. Not escalating to a broader kill; free the port "
                f"manually and retry."
            )
            return False
        return True

    def _check_health(self) -> bool:
        try:
            url = f"http://{_HOST}:{self.port}/health"
            with urllib.request.urlopen(url, timeout=2) as r:
                return r.status == 200
        except Exception:
            return False

    def _is_port_open(self) -> bool:
        import socket

        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(1.0)
            result = s.connect_ex((_HOST, self.port))
            s.close()
            if result == 0:
                return self._check_health()
            return False
        except Exception:
            return False

    def _port_is_bound(self) -> bool:
        """Raw TCP-connect check, independent of `_check_health()`.

        Used by `_kill_port_occupant()`'s post-kill verification:
        `_is_port_open()` requires a successful /health response, so a
        non-llama-server occupant (or a not-yet-ready one) that accepts
        the TCP connection but doesn't answer /health would make
        `_is_port_open()` falsely report "not open" even though the port
        is still bound — masking exactly the failure this check exists to
        catch.
        """
        import socket

        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(1.0)
            result = s.connect_ex((_HOST, self.port))
            s.close()
            return result == 0
        except Exception:
            return False


# ── Global singleton ───────────────────────────────────────────────────────────

_embed_server: Optional[EmbedServer] = None


def get_embed_server() -> EmbedServer:
    global _embed_server
    if _embed_server is None:
        _embed_server = EmbedServer()
    return _embed_server


def start_embed_server() -> bool:
    """Start the global embed server. Idempotent."""
    return get_embed_server().start()


def stop_embed_server():
    """Stop the global embed server."""
    global _embed_server
    if _embed_server is not None:
        _embed_server.stop()
        _embed_server = None
