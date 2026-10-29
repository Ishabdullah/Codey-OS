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
- Owned child teardown is confirmed/reaped; adopted servers are not signaled

Usage:
    from core.embed_server import get_embed_server, start_embed_server
    ok = start_embed_server()   # idempotent — safe to call multiple times
"""

import os
import signal
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from threading import RLock
from typing import Optional

import core.resource_gate as rg
from utils.config import CODEY_STATE_DIR, EMBED_MODEL_PATH, EMBED_SERVER_PORT, LLAMA_SERVER_BIN
from utils.logger import error, info, success, warning

# Host is always localhost
_HOST = "127.0.0.1"


def _diagnostic(log, message):
    """Console/file logging cannot decide child ownership or cleanup results."""
    try:
        log(message)
    except Exception:
        # A broken diagnostic sink must not turn confirmed reap into failure,
        # abandon startup cleanup, or mask the operation's original interrupt.
        pass


class EmbedTeardownError(RuntimeError):
    """Owned embedding cleanup is incomplete and must be retried."""


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
        self._lifecycle_lock = RLock()
        self._owned_session_pid = None
        self._cleanup_pending = False

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    @property
    def cleanup_pending(self) -> bool:
        with self._lifecycle_lock:
            return self._cleanup_pending

    def start(self) -> bool:
        """Start/adopt only after any previous owned cleanup is resolved."""
        with self._lifecycle_lock:
            try:
                result = self._start()
            except BaseException as exc:
                try:
                    self._cleanup_after_failed_start()
                except BaseException:
                    if isinstance(exc, Exception):
                        raise
                    # Preserve the original interruption even if cleanup is
                    # interrupted too; the owned handle/pending state remain.
                if not isinstance(exc, Exception):
                    raise
                _diagnostic(warning, "Embedding startup failed; inspect owned cleanup state before retry")
                return False
            if not result:
                self._cleanup_after_failed_start()
            return result

    def _cleanup_after_failed_start(self):
        if self._cleanup_pending:
            return  # An earlier stop in this attempt already retained retry debt.
        if self.process is not None or self._slot_id is not None or self._cleanup_pending:
            try:
                self.stop()
            except EmbedTeardownError:
                _diagnostic(warning, "Embedding startup cleanup pending; replacement blocked")

    def _start(self) -> bool:
        """Lifecycle lock is held across ownership, startup and accounting."""
        if self.process is not None:
            if not self._cleanup_pending and self.process.poll() is None and self._check_health():
                return True
            # A dead handle is reaped before any port/PID lookup. A live but
            # unhealthy owned child follows owned stop, never the foreign killer.
            try:
                self.stop()
            except EmbedTeardownError:
                return False
        elif self._cleanup_pending or (self._slot_id is not None and not self._started):
            try:
                self.stop()
            except EmbedTeardownError:
                return False

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
            _diagnostic(info, f"Adopting already-healthy embed server on port {self.port}, not restarting it")
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
                    _diagnostic(warning, f"resource_gate: failed to register adopted embed server slot: {e}")
            return True

        # Detach an observation we registered for a now-unhealthy adopted
        # occupant before registering a replacement. Borrowed slots were never
        # assigned to _slot_id and therefore remain untouched.
        if self._slot_id is not None:
            try:
                self.stop()
            except EmbedTeardownError:
                return False

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
            _diagnostic(info, f"Stale process on port {self.port} — replacing with fresh embed server...")
            if not self._kill_port_occupant():
                # Occupant PID unknown/unkillable — do not proceed to bind
                # against a port we couldn't safely clear (see
                # _kill_port_occupant()'s docstring: never kill by name).
                _diagnostic(error, f"embed_server: could not clear port {self.port}, aborting start")
                return False

        if not self.model_path.exists():
            _diagnostic(warning, f"Embed model not found: {self.model_path}")
            _diagnostic(warning, "Run: bash tools/setup_skills.sh   to set up the embedding model")
            return False

        llama_bin = Path(LLAMA_SERVER_BIN)
        if not llama_bin.exists():
            _diagnostic(error, f"llama-server binary not found: {LLAMA_SERVER_BIN}")
            return False

        _diagnostic(info, f"Starting embed server (nomic) on port {self.port}...")

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
            "2",  # 2 threads for embedding (keep CPU headroom for the primary model)
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

        # Close the parent's log stream on every path. Once Popen returns,
        # ownership is assigned before logging/health/accounting can fail.
        with open(log_file, "a") as log_fd:
            log_fd.write(f"\n--- embed server start: {' '.join(cmd)}\n")
            log_fd.flush()
            self.process = subprocess.Popen(
                cmd, stdout=log_fd, stderr=subprocess.STDOUT,
                preexec_fn=os.setsid if os.name != "nt" else None,
            )
            self._owned_session_pid = self.process.pid if os.name != "nt" else None

        _diagnostic(info, f"Embed server PID: {self.process.pid}, log: {log_file}")

        # Wait up to 30 s for the server to become healthy
        for _ in range(60):
            time.sleep(0.5)
            if self.process.poll() is not None:
                _diagnostic(error, f"Embed server died (exit {self.process.poll()})")
                try:
                    with open(log_file) as f:
                        tail = f.read()[-800:]
                    _diagnostic(error, f"Embed log tail:\n{tail}")
                except Exception:
                    pass
                return False
            if self._check_health():
                self._started = True
                _diagnostic(success, f"Embed server ready on port {self.port}")
                # ── Resource gate: accounted-but-exempt (TODO.md 7.4 sub-task 2) ──
                # The embed server is a third, always-resident model process
                # (per this module's own docstring: "Never evicted by model
                # hot-swapping"), so it must be visible to the gate's residency
                # store for accounting/observability — but it is deliberately
                # NOT run through reserve_slot()/can_admit(): it never competes
                # for admission and must never be evicted by the gate the way
                # the primary model's slot is. register_slot() (unconditional, no admission
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
                    _diagnostic(warning, f"resource_gate: failed to register embed server slot: {e}")
                return True

        _diagnostic(error, "Timeout waiting for embed server")
        return False

    _STOP_TIMEOUT_S = 5.0

    def _signal_owned(self, proc, requested_signal):
        """Only the retained live child can anchor its original session group."""
        if proc.poll() is not None:
            return
        if os.name != "nt" and self._owned_session_pid == proc.pid:
            try:
                group = os.getpgid(proc.pid)
                if group == self._owned_session_pid and proc.poll() is None:
                    os.killpg(group, requested_signal)
                    return
            except ProcessLookupError:
                return  # wait/poll must still establish the child's exit.
        if requested_signal == signal.SIGKILL:
            proc.kill()
        else:
            proc.terminate()

    def stop(self):
        """Confirm owned child exit/reap, then release only our registration.

        Adopted servers have no owned Popen and are never signaled. A stale
        handle is polled/reaped before PID lookup: the old NEW-203 claim that
        signaling a dead child's integer was harmless did not exclude PID reuse.
        In-memory retention does not survive owner exit or forced termination.
        """
        with self._lifecycle_lock:
            self._cleanup_pending = True
            self._started = False
            proc = self.process
            if proc is not None:
                try:
                    if proc.poll() is None:
                        self._signal_owned(proc, signal.SIGTERM)
                        try:
                            proc.wait(timeout=self._STOP_TIMEOUT_S)
                        except subprocess.TimeoutExpired:
                            self._signal_owned(proc, signal.SIGKILL)
                            proc.wait(timeout=self._STOP_TIMEOUT_S)
                    else:
                        proc.wait(timeout=self._STOP_TIMEOUT_S)
                    if proc.poll() is None:
                        raise EmbedTeardownError("Embedding child exit not confirmed")
                except Exception as exc:
                    # Do not erase the only handle or release its slot when
                    # signal/wait fails. Interrupts also retain pending state.
                    raise EmbedTeardownError("Embedding owned child cleanup pending") from exc
                self.process = None
                self._owned_session_pid = None
            if self._slot_id is not None:
                try:
                    rg.release_slot(self._slot_id)
                except Exception as exc:
                    # Child is reaped, but retain the exact accounting ID for
                    # retry. False means already absent and is safely resolved.
                    raise EmbedTeardownError("Embedding slot release pending") from exc
                self._slot_id = None
            self._cleanup_pending = False
            _diagnostic(info, "Embed server stopped")

    def is_running(self) -> bool:
        with self._lifecycle_lock:
            if self.process is not None and self.process.poll() is None:
                return True
            if self._started:
                return self._check_health()
            return False

    def is_healthy(self) -> bool:
        """Probe actual health without changing ownership or cleanup state.

        A healthy adopted occupant can answer even when this object has no
        Popen. Callers must independently inspect cleanup_pending before treating
        health as permission to skip a required owned-cleanup retry.
        """
        with self._lifecycle_lock:
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

    _PROC_ROOT = Path("/proc")

    def _capture_embed_occupant(self, pid: int) -> Optional[dict]:
        """Bracketed proof that `pid` is this embed server; None = refuse.

        Requires, between two identical boot/start/UID reads: same UID as us,
        live (non-zombie), /proc/<pid>/exe resolving to LLAMA_SERVER_BIN, and
        argv with exactly one model (-m/--model) equal to the embed model and
        exactly one --port equal to self.port. Same identity fields and
        helpers as the NEW-969 primary-upgrade path (core/loader_v2.py).
        """
        from core import process_identity

        root = self._PROC_ROOT
        if not process_identity.valid_pid(pid) or type(self.port) is not int or not 0 < self.port < 65536:
            return None
        try:
            first = process_identity.process_info(pid, root)
            if first is None or first["uid"] != os.getuid() or first["state"] in ("Z", "X", "x"):
                return None
            directory = Path(root) / str(pid)
            if (directory / "exe").resolve(strict=True) != Path(LLAMA_SERVER_BIN).resolve(strict=True):
                return None
            with (directory / "cmdline").open("rb") as stream:
                raw = stream.read(65537)
            if not raw or len(raw) > 65536 or not raw.endswith(b"\0"):
                return None
            argv = [os.fsdecode(value) for value in raw[:-1].split(b"\0")]
            if not argv or not argv[0]:
                return None
            selected = {"model": [], "port": []}
            for index, value in enumerate(argv[1:], 1):
                for flag, kind in (("-m", "model"), ("--model", "model"), ("--port", "port")):
                    if value == flag:
                        if index + 1 >= len(argv):
                            return None
                        selected[kind].append(argv[index + 1])
                    elif value.startswith(flag + "="):
                        selected[kind].append(value[len(flag) + 1:])
            if len(selected["model"]) != 1 or len(selected["port"]) != 1:
                return None
            port_text = selected["port"][0]
            if not port_text.isascii() or not port_text.isdecimal() or int(port_text) != self.port:
                return None
            model = Path(selected["model"][0])
            if not model.is_absolute():
                model = (directory / "cwd").resolve(strict=True) / model
            if model.resolve(strict=True) != Path(self.model_path).resolve(strict=True):
                return None
            second = process_identity.process_info(pid, root)
            if second is None or second["state"] in ("Z", "X", "x"):
                return None
            if any(first.get(key) != second.get(key) for key in ("pid", "boot_id", "start_ticks", "uid")):
                return None
            return first
        except (OSError, ValueError, RuntimeError, process_identity.UnsafeRecord):
            # Any unreadable/unprovable evidence means refuse (no signal).
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

        # NEW-86: re-verify this PID is still the port's occupant, then
        # (14d) prove it is OUR embed server before any signal. The port
        # re-scan is exactly as strong as `_find_port_occupant_pid()` (on the
        # registered-slot fallback it does not re-observe the port), so the
        # decisive check is the exact identity bracket below: boot id /
        # start ticks / UID read before and after exe + argv evidence, and
        # re-read before every signal by the shared loader_v2 helper. Any
        # occupant that cannot be proven to be this embed server (unrelated
        # process, other model/port, other UID, legacy, recycled PID) is
        # refused with zero signals. Never a process-group kill.
        signalled = False
        reverified_pid = self._find_port_occupant_pid()
        expected = self._capture_embed_occupant(pid) if reverified_pid == pid else None
        if expected is None:
            error(
                f"embed_server: occupant of port {self.port} could not be proven "
                f"to be the embed server (identity or port ownership changed or "
                f"unprovable) — refusing to signal anything. Free the port "
                f"manually and retry."
            )
        else:
            from core import loader_v2

            info(f"Stopping stale embed server PID {pid} occupying port {self.port}")
            outcome = loader_v2._kill_single_pid_term_then_kill(
                pid, self._STOP_TIMEOUT_S, expected=expected, proc_root=self._PROC_ROOT
            )
            signalled = outcome.attempted
            if outcome.outcome != "exited":
                error(
                    f"embed_server: stale embed server PID {pid} exit not confirmed "
                    f"({outcome.outcome}{', PID replaced' if outcome.replaced else ''}) "
                    f"— port {self.port} not cleared; no further signals sent."
                )
                return False

        if signalled:
            time.sleep(2)  # give kernel time to release the port

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
_embed_server_lock = RLock()


def get_embed_server() -> EmbedServer:
    global _embed_server
    with _embed_server_lock:
        if _embed_server is None:
            _embed_server = EmbedServer()
        return _embed_server


def start_embed_server() -> bool:
    """Start the global embed server. Idempotent and serialized with stop."""
    with _embed_server_lock:
        return get_embed_server().start()


def stop_embed_server():
    """Clear the singleton only after confirmed child and slot cleanup."""
    global _embed_server
    with _embed_server_lock:
        if _embed_server is not None:
            _embed_server.stop()
            _embed_server = None
