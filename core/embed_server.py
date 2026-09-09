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

        # ── Adopt a healthy occupant instead of killing it (NEW-146) ────────
        # NEW-144's original fix only guarded core/inference.py's caller
        # (_start_server(), which never owns start/stop lifecycle). This
        # method itself is the one true owner (the daemon's _main_loop and
        # 30s watchdog both call it directly) — but a daemon RESTART after
        # an ungraceful crash (bypassing the old daemon's finally: shutdown)
        # starts with a fresh EmbedServer() object that has no memory of a
        # still-alive, healthy embed server the PRIOR incarnation spawned.
        # Without this check, that case fell through to the kill-and-replace
        # branch below against a perfectly healthy process — exactly
        # NEW-146's scenario. A real /health response here means "already
        # correct and running," so adopt it (register a lease/registry slot
        # for its real PID, if not already registered) rather than tearing
        # it down and re-paying the ~1-2s spawn cost for no behavioral gain.
        # `_port_is_bound()` gated first (not `_check_health()` alone): this
        # method's own not-yet-spawned Popen has nothing listening yet, so a
        # real deployment's health probe against an empty port always fails
        # here on its own — gating on the raw TCP-bound check first keeps
        # that failure mode explicit rather than relying on `_check_health()`
        # alone to imply it.
        if self._port_is_bound() and self._check_health():
            info(f"Adopting already-healthy embed server on port {self.port}, not restarting it")
            self._started = True
            if self._slot_id is None:
                try:
                    existing = rg.find_resident_slot(model_id="embed", port=self.port)
                    if existing is None:
                        real_pid = self._find_port_occupant_pid()
                        if real_pid is not None:
                            self._slot_id = rg.register_slot(
                                model_id="embed",
                                cost_bytes=self.model_path.stat().st_size,
                                pid=real_pid,
                                port=self.port,
                                status=rg.SLOT_STATUS_RESIDENT,
                            )
                except Exception as e:
                    # Accounting-only, same posture as the genuine-spawn
                    # registration below — must never block adoption itself.
                    warning(f"resource_gate: failed to register adopted embed server slot: {e}")
            return True

        # Kill any stale llama-server occupying the embed port — it may have
        # different settings (wrong ctx, old ubatch) from a previous run, OR
        # (see the health check just above, which already handles the
        # healthy case) it's bound but NOT answering /health — the original
        # NEW-144 threat model this branch exists for. Uses the raw
        # TCP-connect check (_port_is_bound), not _is_port_open() alone:
        # _is_port_open() also requires a successful /health response, so a
        # foreign occupant that accepts the connection but doesn't answer
        # /health would make _is_port_open() report "not open" and skip
        # clearing the port entirely — then Popen below would fail to bind
        # and this method would burn the full 30 s health-check loop before
        # reporting a misleading "Timeout waiting for embed server" instead
        # of the real cause.
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
        """Stop the embed server subprocess.

        Only kills the process this object actually holds a `Popen` handle
        for (`self.process`) — an adopted server (NEW-146's lease/registry
        fix) is never ours to kill, matching this project's existing
        "never own what you didn't spawn" posture elsewhere
        (`core/loader_v2.py`'s reuse branch, CLAUDE.md rule 3). The slot
        release below is deliberately NOT nested inside the `if
        self.process:` block: an adopted server still has a real
        `self._slot_id` (registered for observability), and leaving the
        release nested there would leak that slot forever on an adopted
        server's `stop()` — exactly the accounting-blind gap this same
        round's lease/registry item exists to close, just re-introduced
        through this method if left as it was.

        NEW-203: `start()`'s adoption branch usually — but not always —
        leaves `self.process` as `None`. If THIS object's own earlier
        spawn already died (`self.process` still holds a stale, dead
        `Popen` handle `start()` hasn't cleared yet) and adoption of a
        DIFFERENT, healthy occupant then happens before that stale
        `self.process` is reset, this object ends up with a non-`None`
        `self.process` even though it adopted, not owned, the real
        server. In that case the kill logic below still only targets
        `self.process`'s own PID — its own already-dead prior spawn, not
        the adopted server — so it harmlessly no-ops (or raises the
        already-handled `ProcessLookupError`) rather than ever touching
        the real adopted server it doesn't own.
        """
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

    def is_healthy(self) -> bool:
        """Public health-check-only probe, independent of whether THIS
        Python object spawned the embed server (`self.process`/`self._started`
        are per-process, per-object state — see `is_running()` above and
        `start()`'s docstring). A real `/health` HTTP request against the
        known port, so a caller in a different OS process than whichever
        one actually owns the embed lifecycle (see `NEW-144` in
        `NEW_ISSUES.md`) can positively confirm "a healthy embed server is
        already up" without needing `self.process` to be set.

        Callers that do NOT own the embed lifecycle (today: only
        `core/inference.py:_start_server()` — see that module's own
        comment) MUST call this first and skip `start()` entirely when it
        returns True, rather than calling `start()` unconditionally:
        `start()`'s only "already running" fast path checks `self.process`,
        so a foreign-but-healthy occupant falls through to `start()`'s
        kill-and-replace branch (`NEW-144`'s exact bug) if this guard isn't
        applied first.
        """
        return self._check_health()

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

        # NEW-86: re-verify this PID is still the port's occupant
        # immediately before the kill below, not just at identification
        # time above. This is a narrow PID-recycling TOCTOU: if the real
        # occupant exits naturally in the gap between identification and
        # the os.kill() call, the OS is free to hand this exact PID
        # number to an unrelated new process before that kill executes,
        # and the old `_port_is_bound()` post-kill check alone can't
        # catch it (the port is already free either way, by then, so it
        # reports success without ever noticing the kill hit the wrong
        # process). A stale cmdline snapshot compared only against
        # itself a few microseconds later does NOT catch this: if the
        # recycle already happened before identification even returned
        # (the common case), both reads see the same, already-recycled
        # process's cmdline and "match" — the actual property that
        # matters is "is this PID still the port's occupant," so
        # re-running the same port-ownership lookup and requiring the
        # same PID come back is what actually discriminates. Not a
        # cmdline *identity gate* (e.g. "must be llama-server") either —
        # `_find_port_occupant_pid()`'s own docstring notes the
        # legitimate occupant need not be our own llama-server, so a
        # gate like that would wrongly refuse to clear a real foreign
        # squatter.
        #
        # Coverage caveat, not fully closed by this fix: this re-scan is
        # exactly as strong as `_find_port_occupant_pid()` itself, which
        # has two internal paths of different strength. Its primary
        # `/proc/net/tcp`(+tcp6) socket scan DOES re-observe the port
        # directly (a real recycle-to-anything, including another
        # llama-server on this device — generation runs on 8080/8081 —
        # would be caught). But that primary path is unreadable in this
        # dev sandbox (confirmed: `head -1 /proc/net/tcp` ->
        # "Permission denied"; on-device Termux/Android behavior is
        # unverified here, needs live-verifier confirmation), in which
        # case `_find_port_occupant_pid()` falls back to
        # `_find_pid_via_registered_slot()` — a lookup against this
        # object's own static `resource_gate` registry entry, re-checked
        # for liveness and llama-server cmdline, but NOT re-observing the
        # port at all. On that fallback path, this re-verification still
        # narrows the window (it re-checks liveness+cmdline later in
        # time, so it catches recycle-to-a-non-llama-server-process) but
        # does NOT catch a recycle where the new process happens to also
        # be some other llama-server on this device — NEW-83's original,
        # narrower blast radius, not fully eliminated on that path.
        # Doesn't fully close the window on either path — only OS-level
        # pidfd support could do that, not evaluated this round — but
        # shrinks it from "identification time" to "immediately before
        # the syscall," and this re-scan is only paid on this
        # already-cold, port-occupied-at-start path.
        reverified_pid = self._find_port_occupant_pid()

        if reverified_pid != pid:
            error(
                f"embed_server: PID {pid} no longer identifies as the "
                f"port {self.port} occupant immediately before kill — "
                f"likely exited and the PID number was recycled to a "
                f"different process. Refusing to kill it."
            )
        else:
            info(f"Killing stale embed server PID {pid} occupying port {self.port}")
            try:
                os.kill(pid, 9)
            except ProcessLookupError:
                # Already gone between the re-check and kill — fine, port is free.
                pass
            except Exception as e:
                error(f"embed_server: failed to kill occupant PID {pid}: {e}")
                return False

        import time as _time

        _time.sleep(2)  # give kernel time to release the port

        if self._port_is_bound():
            # Port is still held. If we actually killed PID {pid} above,
            # this is most likely a child of that PID (inherited the
            # listening socket under the killed process's session) still
            # owning it. If the identity check just above aborted the
            # kill instead (NEW-86 recycling guard), this is simply the
            # port never having been cleared at all. Either way: don't
            # loop retrying automatically, report failure loudly so the
            # caller aborts instead of proceeding to bind against a port
            # that's still occupied.
            error(
                f"embed_server: port {self.port} is still occupied after "
                f"attempting to clear PID {pid} — a child process may "
                f"hold the listening socket, or the kill was aborted (see "
                f"above). Not escalating to a broader kill; free the port "
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
