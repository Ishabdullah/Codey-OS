#!/usr/bin/env python3
"""
Model loader for Codey-OS - Termux/Android compatible.

Uses llama-server binary via subprocess instead of llama-cpp-python bindings
(since llama-cpp-python doesn't support Android platform).

Single-model architecture: always loads the primary 7B model.
"""

import http.client
import json
import os
import signal
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

import core.resource_gate as rg
import utils.config as cfg
from utils.config import (
    CODEY_STATE_DIR,
    LLAMA_SERVER_BIN,
    MODEL_CONFIG,
    PRIMARY_SERVER_PORT,
)
from utils.logger import error, info, success, warning

# NOTE: MODEL_PATH is intentionally NOT imported as a bound name above (no
# `from utils.config import MODEL_PATH`). core/lora_import.py's
# swap_to_finetuned_model()/rollback_to_backup() mutate `cfg.MODEL_PATH` on
# the live `utils.config` module object at runtime; a name bound once here
# at import time would never see that mutation, so a hot-swap would report
# success while this loader kept spawning the original weights
# (NEW_ISSUES.md NEW-84). load_primary() below reads `cfg.MODEL_PATH` fresh,
# once per call, into a local — see that method for why "once per call" and
# not "read cfg.MODEL_PATH at each of several use sites in the method".

# llama-server configuration
SERVER_HOST = "127.0.0.1"
SERVER_PORT = PRIMARY_SERVER_PORT

# ── Sequential-swap guard (primary 7B vs. planner 1.5B) ─────────────────────
# Ish's decision: the primary and planner models must never be resident at
# the same time on this device. This lock is in-process mutual exclusion
# ONLY — it stops core/daemon.py's watchdog (which calls
# ModelLoader.ensure_model() every 30s, on the event loop) from evicting the
# planner while core/planner_loader.py's ensure_planner() is mid-swap in a
# run_in_executor thread of the *same* daemon process. It is deliberately
# non-blocking everywhere it's used (see ensure_model()/ensure_planner()) —
# daemon.py:562 calls ensure_model() directly on the event loop, so blocking
# here would stall the whole daemon. This is plain mutual exclusion, not a
# resource-gate/headroom check (that's future Track 3 Phase 5a) — it doesn't
# measure capacity, it just prevents two in-process swaps from racing.
SWAP_GUARD = threading.Lock()


def probe_port_health(port: int) -> bool:
    """
    Cross-process-safe check: is anything answering GET /health on *port*?

    Used by the primary/planner sequential-swap arbiter to detect a model
    server that some OTHER process spawned (this loader's own _loaded flag
    only reflects in-process state) — CLAUDE.md rule 3 forbids killing a
    process we didn't spawn, so this is a read-only probe, never a kill.
    """
    try:
        with urllib.request.urlopen(
            f"http://{SERVER_HOST}:{port}/health", timeout=2
        ) as response:
            return response.status == 200
    except (urllib.error.URLError, OSError, ValueError, http.client.HTTPException):
        # http.client.HTTPException (e.g. BadStatusLine from a half-dead
        # server mid-teardown) does NOT inherit from URLError/OSError/
        # ValueError, so it must be listed explicitly — this is a read-only
        # health probe, "can't tell if it's healthy" must mean "not healthy",
        # never an uncaught exception (see NEW-12 fix-up round 2, Bug 2).
        return False


# ── Resource-gate residency confirmation (Track 3 Phase 5a / 7.4 sub-task 2) ─
# core/resource_gate.py's mark_resident() docstring is explicit: it must not
# be called merely because a health endpoint answered — llama.cpp/mmap pages
# a model's weights in over time (see resource_gate.ModelSpec.
# mmap_resident_fraction's own docstring), so "server answers /health" and
# "this model's real memory footprint is reflected in a fresh /proc/meminfo
# read" are two different moments. This polls MemAvailable for a bounded
# window after a health-confirmed spawn, looking for a drop consistent with
# (a fraction of) the reserved cost estimate, before actually calling
# mark_resident() — a best-effort confirmation, not a guarantee: other
# concurrent processes on the device can also move MemAvailable during the
# same window, so a false positive/negative here is possible and accepted
# (see docstring below for the timeout tradeoff).
#
# Like resource_gate.py's REQUIRED_HEADROOM_FACTOR / DEVICE_CEILING_USABLE_
# FRACTION, these are uncalibrated first defaults reasoned from NEW-21's
# swap-growth observation, not derived from controlled on-device
# measurements — retune against real observed load behavior once this is
# live-verified, not treated as settled here.
CONFIRM_RESIDENT_FRACTION = 0.5
CONFIRM_RESIDENT_TIMEOUT_S = 10.0
CONFIRM_RESIDENT_POLL_INTERVAL_S = 0.5


def confirm_resident_and_mark_slot(
    slot_id: str,
    baseline_meminfo: dict,
    estimated_cost_bytes: int,
    timeout_s: float = CONFIRM_RESIDENT_TIMEOUT_S,
    poll_interval_s: float = CONFIRM_RESIDENT_POLL_INTERVAL_S,
    pid: Optional[int] = None,
) -> None:
    """
    Poll /proc/meminfo (bounded by `timeout_s`) for a MemAvailable drop
    consistent with `estimated_cost_bytes` actually having landed, then call
    resource_gate.mark_resident(slot_id) — see this section's header comment
    for why "health endpoint answered" alone isn't sufficient per
    mark_resident()'s documented precondition. Shared by
    core/loader_v2.py:ModelLoader.load_primary() and
    core/planner_loader.py:PlannerLoader.load() so both loaders apply the
    same confirmation policy rather than each reimplementing it.

    `pid` (optional): the real spawned `llama-server` subprocess PID —
    forwarded straight to `resource_gate.mark_resident()`'s own `pid`
    argument so the slot is rebound from the caller's own PID (what
    `reserve_slot()` registered it under, before the subprocess existed) to
    the process whose death should actually free it. See
    `resource_gate.mark_resident()`'s docstring (NEW-81) for the full
    reasoning. Both `load_primary()` and `PlannerLoader.load()` pass
    `self._server.process.pid` here in the only branch where they know it
    (the branch where they genuinely spawned the process, not reused one).

    On timeout (no confirming drop observed within `timeout_s`): marks the
    slot resident anyway, with a logged warning, rather than leaving it
    PENDING forever. A permanently-PENDING slot for a model that is actually
    loaded would keep counting against total_reserved_bytes() (see its
    docstring) on top of that SAME memory already being reflected in every
    subsequent live meminfo read — double-counting a live, correctly-loaded
    model's cost, which would incorrectly refuse most/all later admissions
    on this device. A late/never-detected drop (which can happen even for a
    genuinely successful load, e.g. if unrelated memory pressure/reclaim
    from other processes confounds the delta during the poll window) is the
    worse-in-the-common-case failure to guard against here, not the rarer
    case this leaves imperfectly guarded (marking resident slightly before
    the OS fully reflects the new load).

    **TODO.md 7.4a sub-task D3 note, no code change**: per `NEW-105`, this
    `MemAvailable`-delta poll has never once actually confirmed a load in
    this project's live-test history — it has fallen through to the
    "mark resident anyway" fallback above on every observed run so far,
    including genuinely successful loads (RSS matched the cost estimate
    almost exactly). Under `resource_gate.py`'s swap-assisted admission
    (TODO.md 7.4a sub-task C2), this is expected to get structurally
    worse, not just stay flaky: a swap-assisted load is, by design, one
    the device's live `MemAvailable` alone was NOT enough to satisfy, so a
    larger share of the model's pages landing in swap (rather than fresh
    anonymous RAM) makes a `MemAvailable` drop of the expected magnitude
    even less likely to be observed within `timeout_s` than it already is
    on the plain-RAM path today. This is a prediction from the mechanism's
    own shape (swap-assisted pages don't reduce `MemAvailable` the way a
    fresh RAM allocation does), not a live measurement — sub-task E's live
    pass is what would actually confirm whether this path ever fires under
    swap-assisted admission at all. Not a blocking bug here: the "mark
    resident anyway" fallback already exists and is already the observed
    behavior on every path, swapped or not — this note exists so a future
    reader doesn't mistake the fallback firing under swap-assist for a new
    regression this sub-task introduced.
    """
    threshold = int(estimated_cost_bytes * CONFIRM_RESIDENT_FRACTION)
    baseline_available = baseline_meminfo.get("MemAvailable", 0)
    deadline = time.time() + timeout_s
    confirmed = False
    while time.time() < deadline:
        current = rg.read_meminfo()
        drop = baseline_available - current.get("MemAvailable", 0)
        if drop >= threshold:
            confirmed = True
            break
        time.sleep(poll_interval_s)

    if not confirmed:
        warning(
            f"resource_gate: could not confirm a MemAvailable drop for slot "
            f"{slot_id} within {timeout_s}s (threshold "
            f"{threshold / 1024 / 1024:.0f}MiB) — marking resident anyway "
            "rather than leaving it permanently PENDING (see "
            "confirm_resident_and_mark_slot()'s docstring)"
        )

    rg.mark_resident(slot_id, pid=pid)


class LlamaServer:
    """
    Manages llama-server subprocess and HTTP API communication.

    Starts llama-server as a background process and communicates
    via HTTP API for inference.
    """

    def __init__(self, model_path: Path, port: int = SERVER_PORT, n_ctx: Optional[int] = None):
        self.model_path = model_path
        self.process: Optional[subprocess.Popen] = None
        self.port = port
        self._started = False
        # n_ctx=None (the default) preserves this class's original
        # behavior — every server it spawns uses the shared global
        # MODEL_CONFIG["n_ctx"]. TODO.md 7.4b sub-tasks B/C give the
        # planner and the background-dispatched coder their own smaller
        # ceilings (utils.config.get_planner_n_ctx() / get_coder_background_n_ctx())
        # — callers that need a role-specific value pass it explicitly
        # here so the actual spawned `-c` flag (see _spawn_locked()
        # below) matches whatever n_ctx the caller's resource_gate.ModelSpec
        # was built with, rather than the two silently diverging (the
        # NEW-84 class of gate/spawn desync bug).
        self.n_ctx = n_ctx if n_ctx is not None else MODEL_CONFIG["n_ctx"]

    def start(self) -> bool:
        """Start llama-server subprocess."""
        try:
            if self.process and self.process.poll() is None:
                # Already running
                return True

            # Check if llama-server is already running on this port (e.g., from daemon)
            if self._is_port_in_use():
                info(f"llama-server already running on port {self.port}, using existing server")
                self._started = True
                return True

            # ── Cross-process lock (NEW-12 item 4) ──────────────────────────
            # The _is_port_in_use() check above is only a TOCTOU-racy HTTP
            # probe: a daemon process and a separately-invoked CLI process can
            # both see the port free and both attempt to spawn, and the
            # up-to-60s health-check wait below widens that window further.
            # Close it with an flock'd lock file, one per port so the primary
            # and planner locks never collide, mirroring the exact pattern
            # core/daemon.py:48-93 (check_pid_file/write_pid_file) already
            # uses for daemon-vs-daemon locking — LOCK_EX | LOCK_NB
            # (non-blocking), imported locally like that file does (keeps
            # this class import-safe on platforms without fcntl).
            import fcntl

            lock_path = CODEY_STATE_DIR / f"llama-server-{self.port}.lock"
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            lock_fd = open(lock_path, "w")
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except (IOError, OSError):
                # Another process's start() is in flight for this port. Don't
                # spawn a second server — poll for its server to come up and
                # reuse it, exactly like the _is_port_in_use() reuse branch
                # above. Keep retrying the (non-blocking) lock too: if the
                # other process dies mid-start without ever binding the port,
                # health-polling alone would time out here and report failure
                # even though the port is actually free again — retrying the
                # lock lets us fall through and spawn ourselves in that case.
                lock_fd.close()
                info(
                    f"Another process is starting llama-server on port {self.port}; "
                    "waiting for it instead of double-spawning..."
                )
                for _ in range(120):  # 120 * 0.5s = 60s, matches the spawn health-wait below
                    time.sleep(0.5)
                    if self._check_health():
                        self._started = True
                        success(
                            f"Reusing llama-server started by another process on port {self.port}"
                        )
                        return True
                    lock_fd = open(lock_path, "w")
                    try:
                        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break  # acquired — the other process is gone, fall through and spawn
                    except (IOError, OSError):
                        lock_fd.close()
                        continue
                else:
                    error(
                        f"Timeout waiting for another process's llama-server on port {self.port}"
                    )
                    return False

            try:
                # Re-check now that we hold the lock — closes the remaining
                # window between the unlocked check above and lock acquisition.
                if self._is_port_in_use():
                    info(
                        f"llama-server already running on port {self.port}, using existing server"
                    )
                    self._started = True
                    return True
                return self._spawn_locked()
            finally:
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
                except (IOError, OSError):
                    # Best-effort only — closing the fd (immediately below) or
                    # process exit releases the flock regardless, so a failure
                    # here can never leave the lock stuck for other processes.
                    pass
                lock_fd.close()

        except Exception as e:
            error(f"Failed to start llama-server: {e}")
            import traceback

            error(traceback.format_exc())
            return False

    def _spawn_locked(self) -> bool:
        """
        Actual spawn + health-wait, called while the per-port start lock
        (see start()) is held. Split out only so start()'s lock-acquire /
        reuse-poll logic stays readable — not a public entry point.
        """
        try:
            # NOTE: this mask MUST start here (before any Popen-related setup, not just
            # around Popen() itself) — a narrower placement here previously failed to
            # close a live-reproduced orphan-process bug (see NEW-9 in NEW_ISSUES.md).
            # Do not narrow this window without re-reading that history.
            signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT})
            try:
                info(f"Starting llama-server...")

                # Build command
                cmd = [
                    str(LLAMA_SERVER_BIN),
                    "-m",
                    str(self.model_path),
                    "--host",
                    SERVER_HOST,
                    "--port",
                    str(self.port),
                    "-c",
                    str(self.n_ctx),
                    "-t",
                    str(MODEL_CONFIG["n_threads"]),
                    "--temp",
                    str(MODEL_CONFIG["temperature"]),
                    "--top-p",
                    str(MODEL_CONFIG["top_p"]),
                    "--top-k",
                    str(MODEL_CONFIG["top_k"]),
                    "--repeat-penalty",
                    str(MODEL_CONFIG["repeat_penalty"]),
                    "--n-predict",
                    str(MODEL_CONFIG["max_tokens"]),
                    "--flash-attn",
                    "on",  # fused attention kernel, faster prefill
                    "--embedding",  # enable /v1/embeddings endpoint for hybrid KB search
                    "--pooling",
                    "mean",  # mean pooling → single vector per input (OAI-compatible)
                ]

                # Add stop tokens (using --reverse-prompt)
                for stop in MODEL_CONFIG.get("stop", []):
                    cmd.extend(["--reverse-prompt", stop])

                # ── mmap / mlock settings for the 7B model (Change 2) ──────────
                # Pass --mmap / --no-mmap explicitly in both directions so the flag
                # is visible in ps output and not left to llama.cpp's default.
                # --no-mlock does NOT exist in this llama.cpp build; omitting --mlock
                # is sufficient to keep mlock disabled (the llama.cpp default).
                try:
                    from utils.config import QWEN_7B_MLOCK, QWEN_7B_MMAP

                    if QWEN_7B_MMAP:
                        cmd.append("--mmap")
                    else:
                        cmd.append("--no-mmap")
                    if QWEN_7B_MLOCK:
                        cmd.append("--mlock")
                    info(
                        f"7B model: mmap={'enabled' if QWEN_7B_MMAP else 'disabled'}, "
                        f"mlock={'enabled' if QWEN_7B_MLOCK else 'disabled'}"
                    )
                except ImportError:
                    pass  # Config not available — use llama.cpp defaults (mmap on, mlock off)

                # Start process - redirect output to log file to avoid pipe buffer issues
                log_file = CODEY_STATE_DIR / "llama-server.log"
                log_file.parent.mkdir(parents=True, exist_ok=True)

                with open(log_file, "w") as f:
                    f.write(f"Starting llama-server: {' '.join(cmd)}\n")
                    f.flush()

                # Open log file for appending stdout/stderr
                log_fd = open(log_file, "a")

                self.process = subprocess.Popen(
                    cmd,
                    stdout=log_fd,
                    stderr=subprocess.STDOUT,
                    preexec_fn=os.setsid if os.name != "nt" else None,
                )
            finally:
                signal.pthread_sigmask(signal.SIG_UNBLOCK, {signal.SIGINT})

            info(f"llama-server PID: {self.process.pid}, logging to {log_file}")

            # Wait for server to be ready (up to 60 seconds for large models)
            for i in range(120):  # 120 * 0.5s = 60s timeout
                time.sleep(0.5)

                # Check if process died
                if self.process.poll() is not None:
                    error(f"llama-server process died (exit code {self.process.poll()})")
                    # Read log for error
                    try:
                        with open(log_file, "r") as f:
                            logs = f.read()
                        error(f"Server log: {logs[-1000:]}")
                    except (IOError, OSError):
                        pass
                    return False

                if self._check_health():
                    # Give server a moment to fully initialize all endpoints
                    time.sleep(0.5)
                    self._started = True
                    success(f"llama-server started on port {self.port}")
                    return True

            error(f"Timeout waiting for llama-server to start")
            self.stop()
            return False

        except Exception as e:
            error(f"Failed to start llama-server: {e}")
            import traceback

            error(traceback.format_exc())
            return False

    def stop(self):
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
                    self.process.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    if os.name != "nt":
                        try:
                            os.killpg(os.getpgid(self.process.pid), _signal.SIGKILL)
                        except Exception:
                            self.process.kill()
                    else:
                        self.process.kill()
            except Exception as e:
                try:
                    self.process.kill()
                except Exception:
                    pass
            finally:
                self.process = None
                self._started = False

    def _check_health(self) -> bool:
        """Check if server is responding."""
        try:
            url = f"http://{SERVER_HOST}:{self.port}/health"
            with urllib.request.urlopen(url, timeout=2) as response:
                return response.status == 200
        except (urllib.error.URLError, OSError, ValueError, http.client.HTTPException):
            # See probe_port_health()'s matching comment: http.client.HTTPException
            # (e.g. BadStatusLine) doesn't inherit from the other three, and this
            # method backs is_running()/is_loaded(), which callers (e.g.
            # PlannerLoader.ensure_planner()) document as never raising.
            return False

    def _is_port_in_use(self) -> bool:
        """Check if port 8080 is already in use by another llama-server instance."""
        import socket

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1.0)
            result = sock.connect_ex((SERVER_HOST, self.port))
            sock.close()
            # If port is open, check if it's actually llama-server responding
            if result == 0:
                try:
                    url = f"http://{SERVER_HOST}:{self.port}/health"
                    with urllib.request.urlopen(url, timeout=2) as response:
                        return response.status == 200
                except (urllib.error.URLError, OSError, ValueError):
                    pass
            return result == 0
        except Exception:
            return False

    def infer(self, prompt: str, max_tokens: int = None, stop: list = None) -> Optional[str]:
        """
        Run inference via HTTP API.

        Args:
            prompt:     Formatted prompt string.
            max_tokens: Override max output tokens.
            stop:       Extra stop sequences to merge with MODEL_CONFIG["stop"].
                        Callers should pass the combined list so extra_stop tokens
                        (e.g. "</tool>") are honoured by the server.
        """
        if not self._started:
            error("llama-server not running")
            return None

        # Merge caller-supplied stop list with configured defaults
        base_stop = list(MODEL_CONFIG.get("stop", []))
        if stop:
            for s in stop:
                if s not in base_stop:
                    base_stop.append(s)

        # Retry logic for transient errors
        max_retries = 3
        last_error = None

        for attempt in range(max_retries):
            try:
                url = f"http://{SERVER_HOST}:{self.port}/completion"
                data = {
                    "prompt": prompt,
                    "n_predict": max_tokens or MODEL_CONFIG["max_tokens"],
                    "temperature": MODEL_CONFIG["temperature"],
                    "top_p": MODEL_CONFIG["top_p"],
                    "top_k": MODEL_CONFIG["top_k"],
                    "repeat_penalty": MODEL_CONFIG["repeat_penalty"],
                    "stop": base_stop,
                    "stream": False,
                }

                req = urllib.request.Request(
                    url,
                    data=json.dumps(data).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )

                with urllib.request.urlopen(req, timeout=300) as response:
                    result = json.loads(response.read().decode("utf-8"))
                    return result.get("content", "").strip()

            except urllib.error.HTTPError as e:
                if e.code == 503 and attempt < max_retries - 1:
                    warning(f"Server busy (503), retrying ({attempt + 1}/{max_retries})...")
                    time.sleep(1.0)
                    last_error = e
                    continue
                error(f"HTTP error during inference: {e}")
                return None
            except urllib.error.URLError as e:
                error(f"HTTP error during inference: {e}")
                return None
            except json.JSONDecodeError as e:
                error(f"JSON decode error: {e}")
                return None
            except Exception as e:
                error(f"Inference error: {e}")
                return None

        error(f"All retries failed: {last_error}")
        return None

    def is_running(self) -> bool:
        """Check if server process is running."""
        if self.process is not None:
            return self.process.poll() is None
        # If no process but _started is True, check if port is responding
        if self._started:
            return self._check_health()
        return False


# ── ensure_model()/load_primary() outcome tracking (Track 3 Phase 5a / 7.4
# sub-task 3) ─────────────────────────────────────────────────────────────
# Both methods have always returned a plain bool, and every existing caller
# (core/inference.py, core/inference_v2.py, main.py, core/lora_import.py)
# depends on that — this sub-task does not change either return type. What
# was missing is a way for a caller that DOES care (core/daemon.py's
# watchdog) to distinguish *why* a `False`/failed-restart happened, in
# particular "the resource gate denied a reservation" (a real, expected
# outcome under the 7.4 amendment — no fixed ceiling, but headroom/thermal/
# device-ceiling checks still exist and can legitimately refuse admission)
# from "the process crashed" or "spawn timed out" — those need different
# daemon-side handling (see daemon.py's watchdog comment). These constants
# are set at every return point in ensure_model()/load_primary() (not just
# on the gate-denial path) so a stale value from a PRIOR call is never
# misread as this call's outcome — see the deferred/SWAP_GUARD-busy case in
# ensure_model(), which returns False without ever reaching load_primary().
LOAD_OUTCOME_OK = "ok"
LOAD_OUTCOME_ALREADY_LOADED = "already_loaded"
LOAD_OUTCOME_DEFERRED = "deferred"  # SWAP_GUARD busy — retry next tick, not a failure
LOAD_OUTCOME_GATE_DENIED = "gate_denied"  # transient: headroom/thermal — may succeed on retry
LOAD_OUTCOME_GATE_DENIED_HARD = "gate_denied_hard"  # permanent: model alone exceeds device ceiling
LOAD_OUTCOME_EVICTION_FAILED = "eviction_failed"  # couldn't confirm planner freed its port
LOAD_OUTCOME_SPAWN_FAILED = "spawn_failed"  # llama-server process failed to start/health-check
LOAD_OUTCOME_ERROR = "error"  # missing model file/binary, or an unexpected exception


class ModelLoader:
    """
    Manages model loading via llama-server.

    Single-model: always loads the primary 7B Qwen2.5-Coder model.
    """

    def __init__(self):
        self._loaded: bool = False
        self._server: Optional[LlamaServer] = None
        self._loaded_at: float = 0
        # NEW-152 (code-reviewer retroactive pass on the NEW-145 fix, found
        # 2026-08-13): this used to be a single `_ever_loaded` flag set True
        # on EITHER a genuine spawn OR `LlamaServer.start()`'s port-in-use
        # adoption branch. That made the watchdog gate below sticky-True
        # after the very first adoption — the normal `codey-start` steady
        # state (TUI spawns the coder, daemon later adopts it via a
        # background dispatch) — so it stopped protecting the daemon after
        # that point: an ordinary TUI-session-end (not a crash) would still
        # look like "was loaded, restart it" and respawn at the smaller
        # background ceiling. Narrowed to genuine-spawn-only so the gate
        # can tell "this daemon's own loader spawned a coder" (should keep
        # restarting it on crash, regardless of TUI state) apart from
        # "this loader has only ever adopted someone else's coder, or
        # never loaded one at all" (should stay quiet unless a real
        # request comes in — adoption doesn't imply this loader owns that
        # process's lifecycle, same argument the reuse branch already
        # makes about residency accounting). Set True alongside `_loaded_at`
        # below on a successful genuine spawn only, and — unlike `_loaded`
        # — deliberately never reset by `unload()` (same as `_loaded_at`
        # already isn't): for a genuine spawn, that stickiness IS the
        # crash-restart mechanism. See `was_ever_spawned()`'s own
        # docstring for the full case-by-case breakdown.
        self._ever_spawned: bool = False
        self._load_failures: int = 0
        self._slot_id: Optional[str] = None
        # See LOAD_OUTCOME_* constants above this class.
        self._last_ensure_outcome: str = LOAD_OUTCOME_OK
        self._last_ensure_reason: str = ""

    def load_primary(self) -> bool:
        """Load the primary (7B) model."""
        try:
            # Snapshot cfg.MODEL_PATH ONCE, into a local, at the top of this
            # call — not re-read at each use site below. cfg.MODEL_PATH can
            # be mutated concurrently by core/lora_import.py's
            # swap_to_finetuned_model()/rollback_to_backup(); reading it
            # fresh at every one of this method's several use sites (the
            # exists() check, the ModelSpec passed to the resource gate, the
            # LlamaServer that actually spawns, and the log lines) would let
            # a swap landing mid-call gate on one file and spawn a different
            # one — the same self-race class CLAUDE.md rule 4 warns about.
            # One snapshot means this call is internally consistent even if
            # cfg.MODEL_PATH changes again before it returns.
            model_path = cfg.MODEL_PATH
            info(f"Loading model: {model_path.name}")

            # ── TODO.md 7.4b sub-task C: interactive-vs-background n_ctx ────
            # Snapshot the interactive-session signal ONCE here too, same
            # reasoning as the cfg.MODEL_PATH snapshot above — this call's
            # ModelSpec (the gate's admission math) and its actual spawned
            # LlamaServer (the real -c flag) must agree on n_ctx, so both
            # must read the SAME evaluation of is_interactive_session_active(),
            # not two separate reads that could disagree if a TUI session
            # starts/ends mid-call. is_interactive_session_active() is the
            # existing TODO.md 7.4 sub-task C signal (utils.config.
            # TUI_SESSIONS_DIR-backed) already wired into daemon dispatch —
            # reused here, not a second detection mechanism. True when a
            # human is actively using the TUI/GUI: full interactive ceiling
            # (MODEL_CONFIG["n_ctx"], the CODEY_N_CTX-overridable default).
            # False (daemon-dispatched background task, no interactive
            # session): the smaller get_coder_background_n_ctx() ceiling —
            # a function, not a constant (NEW-102/bug_002 fix), so it
            # re-reads MODEL_CONFIG["n_ctx"] live and honors a runtime
            # --ctx override; see its definition in utils/config.py.
            interactive = rg.is_interactive_session_active()
            n_ctx = MODEL_CONFIG.get("n_ctx", 4096) if interactive else cfg.get_coder_background_n_ctx()
            info(
                f"Coder n_ctx={n_ctx} "
                f"({'interactive session active' if interactive else 'no interactive session — background ceiling'})"
            )

            # Check if model file exists
            if not model_path.exists():
                error(f"Model file not found: {model_path}")
                self._load_failures += 1
                self._last_ensure_outcome = LOAD_OUTCOME_ERROR
                self._last_ensure_reason = f"model file not found: {model_path}"
                return False

            # Check if llama-server binary exists
            llama_bin = Path(LLAMA_SERVER_BIN)
            if not llama_bin.exists():
                error(f"llama-server not found: {LLAMA_SERVER_BIN}")
                self._load_failures += 1
                self._last_ensure_outcome = LOAD_OUTCOME_ERROR
                self._last_ensure_reason = f"llama-server binary not found: {LLAMA_SERVER_BIN}"
                return False

            # ── Resource gate: reserve a slot before actually spawning ──────
            # Per CODEY_OS_MASTER_VISION.md 7.4 (2026-08-08 amendment) / TODO.md
            # 7.4 sub-task 2: the gate is the sole admission authority. A
            # denied reservation is a real, surfaced failure, not something
            # this method proceeds past.
            spec = rg.ModelSpec(model_id="primary", path=model_path, n_ctx=n_ctx)
            decision, slot_id = rg.reserve_slot(spec)
            if not decision.admitted:
                error(f"Resource gate denied primary model load: {decision.reason}")
                self._load_failures += 1
                # hard_reject means this model alone exceeds the device
                # ceiling — retrying later cannot change that outcome (the
                # 2026-08-08 amendment's one non-negotiable admission check).
                # Any other denial (headroom/thermal) is transient and worth
                # retrying — see daemon.py's watchdog, which treats these two
                # outcomes differently rather than both as "died, restart".
                self._last_ensure_outcome = (
                    LOAD_OUTCOME_GATE_DENIED_HARD if decision.hard_reject else LOAD_OUTCOME_GATE_DENIED
                )
                self._last_ensure_reason = decision.reason
                return False

            # Captured before spawn so confirm_resident_and_mark_slot() has a
            # true "before" baseline to compare a post-spawn read against.
            baseline_meminfo = rg.read_meminfo()

            # ── Structural reserve→spawn→confirm cleanup guarantee ──────────
            # Everything below (spawn through confirm_resident_and_mark_slot())
            # is wrapped in this try/finally, not just the two failure
            # branches this method explicitly checks (start() returning
            # False; the reuse-without-spawn branch). If ANYTHING in this
            # window raises — including confirm_resident_and_mark_slot()
            # itself, whose rg.mark_resident() does a blocking flock() +
            # atomic os.replace() write, both of which can raise under fd
            # exhaustion/disk pressure (realistic on this device) — the
            # spawned process must be stopped and the reservation released,
            # not silently leaked while the outer except below swallows the
            # exception and returns False. `loaded_ok` is only set True on
            # the genuine success return; every other exit from this block
            # (an explicit `return False` OR an exception propagating to the
            # outer handler) is treated identically by the finally clause.
            # See .claude/agent-memory/code-reviewer/
            # resource_gate_subtask2_confirm_mark_slot_leak.md — this
            # replaces exactly the gap documented there.
            self._server = LlamaServer(model_path, n_ctx=n_ctx)
            loaded_ok = False
            try:
                if not self._server.start():
                    self._load_failures += 1
                    self._last_ensure_outcome = LOAD_OUTCOME_SPAWN_FAILED
                    self._last_ensure_reason = (
                        "llama-server process failed to start or answer /health "
                        "in time (see core/state/llama-server.log)"
                    )
                    return False

                if self._server.process is None:
                    # start() reused a server this loader did NOT spawn (its
                    # "already running on this port" / "reuse another process's
                    # in-flight start" branches both return True with
                    # self.process left None — see LlamaServer.start()). We don't
                    # own that process's residency accounting, so release our own
                    # reservation instead of double-registering it: the process
                    # that actually spawned it owns its slot, and our unload()
                    # must not free a slot for a model we didn't load and isn't
                    # ours to declare gone.
                    info(
                        "Reusing an existing llama-server not spawned by this loader — "
                        "releasing this loader's own gate reservation, not double-accounting "
                        "its residency."
                    )
                    rg.release_slot(slot_id)
                    self._slot_id = None
                else:
                    # pid=self._server.process.pid: rebind the slot from
                    # this loader's own PID (what reserve_slot() registered
                    # it under, before this subprocess existed) to the real
                    # spawned llama-server PID — see
                    # confirm_resident_and_mark_slot()'s pid docstring and
                    # resource_gate.mark_resident()'s (NEW-81) for why. Only
                    # reachable here because self._server.process is not
                    # None (we genuinely spawned it, not the reuse branch
                    # above).
                    confirm_resident_and_mark_slot(
                        slot_id,
                        baseline_meminfo,
                        decision.estimated_cost_bytes,
                        pid=self._server.process.pid,
                    )
                    self._slot_id = slot_id

                self._loaded = True
                self._loaded_at = time.time()
                # NEW-152: only the genuine-spawn branch above (`self._server.
                # process is not None`) sets `_ever_spawned` — the adoption
                # branch leaves it False. `self._server.process` hasn't
                # changed since that branch ran (nothing between there and
                # here touches it), so re-checking it here is equivalent to
                # checking it inside the branch, but keeps the "ever" flag
                # assignment at the single convergence point, matching
                # `_loaded`/`_loaded_at` immediately above.
                if self._server is not None and self._server.process is not None:
                    self._ever_spawned = True
                success(f"Loaded model ({model_path.name})")
                loaded_ok = True
                self._last_ensure_outcome = LOAD_OUTCOME_OK
                self._last_ensure_reason = ""
                return True
            finally:
                if not loaded_ok:
                    if self._server is not None and self._server.process is not None:
                        # We actually spawned this process (a reused server
                        # has self.process left None and must never be
                        # stop()'d here — not ours to kill, CLAUDE.md rule 3)
                        # — tear it down so nothing is left orphaned with no
                        # tracking reference to it.
                        self._server.stop()
                    self._server = None
                    self._loaded = False
                    try:
                        rg.release_slot(slot_id)
                    except Exception as e:
                        # release_slot() itself failing here is the same
                        # class of flock()/os.replace() failure this whole
                        # block guards against — must not mask the original
                        # failure that got us into this cleanup path, so log
                        # and continue; the outer except below still returns
                        # False either way. release_slot() is safe to call
                        # even if the slot was already released above (the
                        # reuse branch) — it's a no-op lookup-miss, not an
                        # error, in that case.
                        warning(
                            f"resource_gate: failed to release slot {slot_id} during "
                            f"load_primary() cleanup: {e}"
                        )
                    self._slot_id = None

        except Exception as e:
            error(f"Failed to load model: {e}")
            self._load_failures += 1
            self._last_ensure_outcome = LOAD_OUTCOME_ERROR
            self._last_ensure_reason = str(e)
            return False

    def unload(self):
        """Unload (stop) the current model server."""
        if self._server:
            info("Stopping model server...")
            self._server.stop()
            self._server = None
            self._loaded = False
        if self._slot_id:
            try:
                rg.release_slot(self._slot_id)
            except Exception as e:
                # The underlying process is already stopped above regardless
                # of this outcome — a failure to update gate accounting here
                # is a (logged) accounting bug, not a reason to make the
                # caller think unload() itself failed.
                warning(f"resource_gate: failed to release slot {self._slot_id}: {e}")
            self._slot_id = None

    def get_pid(self) -> Optional[int]:
        """Return the PID of the llama-server process this loader spawned, if any."""
        if self._server and self._server.process:
            return self._server.process.pid
        return None

    def ensure_model(self, model_type: str = "primary") -> bool:
        """
        Ensure the model is loaded and running.

        SWAP_GUARD covers this method's ENTIRE body — both the "already
        loaded, maybe thermal-restart" branch and the "cold load" branch —
        not just the cold-load branch. A thermal-triggered restart does its
        own unload()/load_primary() cycle, during which _loaded is False
        and the port isn't answering; without the guard covering that
        window too, a concurrent ensure_planner() (running in plannd.py's
        run_in_executor thread) could see "primary not loaded" and spawn
        the planner mid-restart, landing both models resident at once —
        exactly what SWAP_GUARD exists to prevent (see its docstring:
        "any time the primary's loaded/not-loaded state is in transition,
        no exceptions"). Non-blocking, as always (see SWAP_GUARD comment
        above): if the planner is mid-swap, defer — including a thermal
        restart. That's acceptable because thermal state is re-evaluated
        every watchdog tick (≤30s), so a deferred restart just runs on the
        next tick instead of this one; nothing is lost.
        """
        if not SWAP_GUARD.acquire(blocking=False):
            info("Primary load/restart deferred — planner swap in flight")
            # Not load_primary()'s job to set this (it never runs on this
            # path) — every return point in THIS method sets the outcome
            # itself precisely so a stale value from a previous call can
            # never be misread as this call's result (see LOAD_OUTCOME_*
            # comment above the ModelLoader class).
            self._last_ensure_outcome = LOAD_OUTCOME_DEFERRED
            self._last_ensure_reason = "planner swap in flight (SWAP_GUARD busy) — retry next tick"
            return False
        try:
            if self._loaded and self._server and self._server.is_running():
                try:
                    from core.thermal import get_thermal_manager

                    tm = get_thermal_manager()
                    if tm.restart_recommended:
                        info(
                            f"Thermal: restarting server with {tm.current_threads} threads..."
                        )
                        self.unload()
                        tm.restart_recommended = False
                        return self.load_primary()
                except Exception:
                    # Thermal check is best-effort only — any failure here (import
                    # error, unexpected attribute, etc.) must never block normal
                    # model loading/inference, so we fail open and keep the
                    # server running on its current thread count.
                    pass
                self._last_ensure_outcome = LOAD_OUTCOME_ALREADY_LOADED
                self._last_ensure_reason = ""
                return True

            # ── Sequential swap (cold load) ────────────────────────────
            if not self._evict_planner_and_confirm_free():
                self._last_ensure_outcome = LOAD_OUTCOME_EVICTION_FAILED
                self._last_ensure_reason = (
                    "could not confirm the planner (1.5B) freed its port before "
                    "loading the primary (7B) — sequential-swap guard"
                )
                return False
            return self.load_primary()
        finally:
            SWAP_GUARD.release()

    def _evict_planner_and_confirm_free(self) -> bool:
        """
        Unload the planner (1.5B) if THIS process's own planner-loader
        singleton spawned it (we can only stop a process we spawned —
        CLAUDE.md rule 3), then confirm its port is actually free before we
        proceed to load the primary. Mirrors
        core/planner_loader.py:PlannerLoader._evict_primary_and_confirm_free()
        exactly, in the opposite direction — deliberately symmetric, not a
        looser "best effort" version of it: Ish's decision 2 (never both
        resident) is the actual requirement here, not a soft preference, so
        a planner we can't confirm gone must block the primary load exactly
        like an unconfirmed primary blocks the planner load.

        Trade-off worth naming for reviewers: a stuck planner now blocks a
        primary (agent) load too, not just the reverse. This is accepted
        because the alternative — loading a 5GB 7B model on top of a zombie
        1.5B — is the actual OOM-crash scenario this device has hit before,
        and the watchdog (core/daemon.py, ~30s tick) retries ensure_model()
        automatically, so this self-heals once the planner's process
        actually exits.
        """
        try:
            from core.planner_loader import get_planner_loader
            from utils.config import PLANND_SERVER_PORT

            planner = get_planner_loader()
            if planner.is_loaded():
                info("Sequential swap: unloading planner (1.5B) before loading primary (7B)")
                planner.unload()

            if probe_port_health(PLANND_SERVER_PORT):
                warning(
                    f"Planner still answering on port {PLANND_SERVER_PORT} after "
                    "eviction attempt — not loading primary (would violate sequential-swap)"
                )
                return False
            return True
        except Exception as e:
            # A failure in this cooperative check (import error, etc.) is
            # treated the same as "couldn't confirm free" — fail closed
            # rather than risk both models resident, consistent with the
            # planner-side mirror of this method.
            warning(f"Planner eviction check failed: {e} — not loading primary")
            return False

    def get_loaded_model(self) -> Optional[str]:
        """Get the currently loaded model type."""
        return "primary" if self._loaded else None

    def is_loaded(self, model_type: str = None) -> bool:
        """Check if the model is loaded."""
        return self._loaded

    def was_ever_spawned(self) -> bool:
        """
        Whether this loader has GENUINELY SPAWNED a coder server (its own
        subprocess, `LlamaServer.start()` NOT hitting the port-in-use
        reuse/adoption branch) at least once in this process's lifetime —
        not "is it loaded right now" (see `is_loaded()` for that), and
        deliberately NOT "adopted one at least once" either (see NEW-152
        below for why that used to be the same flag and stopped working).
        Set once, at `load_primary()`'s success point, only when
        `self._server.process is not None` at that point; never reset by
        `unload()` (same as `_loaded_at` isn't) — for a genuine spawn,
        that stickiness is what makes crash-restart coverage work at all.

        **NEW-152 (2026-08-13, code-reviewer retroactive pass on the
        NEW-145 fix): replaces the original `_ever_loaded`/
        `was_ever_loaded()`, which was set True on EITHER a genuine spawn
        OR the adoption branch.** That made `core/daemon.py`'s
        `_watchdog_check_model()` gate sticky-True after the very FIRST
        adoption — which, under the normal `codey-start` steady state (TUI
        spawns the coder; the daemon's own loader later adopts it via its
        first background dispatch), is the common case, not an edge case.
        Once adopted, the flag stayed True forever, so an ordinary TUI
        session ending (not a crash) looked identical to "was loaded,
        restart it," and the watchdog respawned the coder at the smaller
        background ceiling — reproducing NEW-145's original symptom
        through adoption instead of through the deleted eager preload.

        Narrowing to genuine-spawn-only fixes that: adoption no longer
        contributes to this flag at all, so a TUI-adopted-then-exited
        coder correctly reads as "nothing currently wants this," matching
        Ish's decision 3 ("loads lazily on first real request") instead of
        being treated as a crash to recover from.

        Used by `_watchdog_check_model()` to distinguish "this daemon's
        own loader spawned a coder and it isn't running now — restart it"
        from "this loader has only ever adopted someone else's coder, or
        never loaded one at all — leave it alone until a real request
        comes in." Case-by-case: (a) unchanged for coder loads THIS
        loader's own process genuinely spawned (background-dispatched
        loads through the daemon's own `get_loader()`) — restarts on
        crash exactly as before, unconditionally, regardless of whether a
        TUI is currently attached; (b) **reduced from the previous
        behavior, deliberately**: a TUI-spawned coder that the daemon's
        loader has only ever ADOPTED (never itself spawned) is no longer
        restarted by the watchdog if it crashes — the daemon does not own
        that process's lifecycle (same argument `load_primary()`'s reuse
        branch already makes about residency accounting), and the TUI's
        own next `infer()` call will reload it. This is the fix for the
        false-positive respawn described above, not a separate regression
        — the previous "restart an adopted coder on crash" behavior is
        exactly the mechanism that caused NEW-152; (c) a coder that has
        never been spawned by NOR adopted through this loader's own
        `load_primary()` call is left alone by the watchdog, same as
        before.

        Known residual, NOT fixed by this change (logged separately,
        NEW-149-adjacent): once this loader HAS genuinely spawned a
        background coder at least once, `_ever_spawned` stays sticky-True
        for the rest of the process's lifetime — a later tick can still
        respawn it at the 16384 background ceiling after it stops, and a
        later-attaching interactive TUI would reuse that under-provisioned
        server via `LlamaServer.start()`'s reuse branch. Only case (b)
        (pure adoption, no genuine spawn ever) is fixed here.
        """
        return self._ever_spawned

    def get_model_instance(self) -> Optional[LlamaServer]:
        """Get the llama-server instance."""
        return self._server

    def get_load_failures(self) -> int:
        """Get count of consecutive load failures."""
        return self._load_failures

    def get_last_ensure_outcome(self) -> str:
        """
        One of the `LOAD_OUTCOME_*` constants above this class, describing
        WHY the most recent `ensure_model()`/`load_primary()` call returned
        what it returned — set at every return point in both methods (see
        their docstrings), never stale from an unrelated earlier call.
        `ensure_model()`'s/`load_primary()`'s own return value stays a plain
        bool for existing callers (core/inference.py, core/inference_v2.py,
        main.py, core/lora_import.py); this is an additive getter for a
        caller that needs to distinguish denial reasons, e.g. core/daemon.py's
        watchdog treating a gate denial differently from a process crash.
        """
        return self._last_ensure_outcome

    def get_last_ensure_reason(self) -> str:
        """Human-readable detail for `get_last_ensure_outcome()`'s value."""
        return self._last_ensure_reason

    def reset_failures(self):
        """Reset failure count (call after successful load)."""
        self._load_failures = 0

    def get_status(self) -> dict:
        """Get loader status."""
        return {
            "loaded_model": "primary" if self._loaded else None,
            "loaded_at": self._loaded_at,
            "uptime_seconds": time.time() - self._loaded_at if self._loaded_at else 0,
            "load_failures": self._load_failures,
            "server_running": self._server.is_running() if self._server else False,
        }


# Global loader instance
_loader: Optional[ModelLoader] = None


def get_loader() -> ModelLoader:
    """Get the global loader instance."""
    global _loader
    if _loader is None:
        _loader = ModelLoader()
    return _loader


def reset_loader():
    """Reset the global loader (for testing)."""
    global _loader
    if _loader:
        _loader.unload()
        _loader = None
