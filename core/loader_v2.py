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

from utils.config import (
    CODEY_STATE_DIR,
    LLAMA_SERVER_BIN,
    MODEL_CONFIG,
    MODEL_PATH,
    PRIMARY_SERVER_PORT,
)
from utils.logger import error, info, success, warning

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


class LlamaServer:
    """
    Manages llama-server subprocess and HTTP API communication.

    Starts llama-server as a background process and communicates
    via HTTP API for inference.
    """

    def __init__(self, model_path: Path, port: int = SERVER_PORT):
        self.model_path = model_path
        self.process: Optional[subprocess.Popen] = None
        self.port = port
        self._started = False

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
                    str(MODEL_CONFIG["n_ctx"]),
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


class ModelLoader:
    """
    Manages model loading via llama-server.

    Single-model: always loads the primary 7B Qwen2.5-Coder model.
    """

    def __init__(self):
        self._loaded: bool = False
        self._server: Optional[LlamaServer] = None
        self._loaded_at: float = 0
        self._load_failures: int = 0

    def load_primary(self) -> bool:
        """Load the primary (7B) model."""
        try:
            info(f"Loading model: {MODEL_PATH.name}")

            # Check if model file exists
            if not MODEL_PATH.exists():
                error(f"Model file not found: {MODEL_PATH}")
                self._load_failures += 1
                return False

            # Check if llama-server binary exists
            llama_bin = Path(LLAMA_SERVER_BIN)
            if not llama_bin.exists():
                error(f"llama-server not found: {LLAMA_SERVER_BIN}")
                self._load_failures += 1
                return False

            # Start server
            self._server = LlamaServer(MODEL_PATH)
            if not self._server.start():
                self._load_failures += 1
                return False

            self._loaded = True
            self._loaded_at = time.time()
            success(f"Loaded model ({MODEL_PATH.name})")
            return True

        except Exception as e:
            error(f"Failed to load model: {e}")
            self._load_failures += 1
            return False

    def unload(self):
        """Unload (stop) the current model server."""
        if self._server:
            info("Stopping model server...")
            self._server.stop()
            self._server = None
            self._loaded = False

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
                return True

            # ── Sequential swap (cold load) ────────────────────────────
            if not self._evict_planner_and_confirm_free():
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

    def get_model_instance(self) -> Optional[LlamaServer]:
        """Get the llama-server instance."""
        return self._server

    def get_load_failures(self) -> int:
        """Get count of consecutive load failures."""
        return self._load_failures

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
