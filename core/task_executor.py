#!/usr/bin/env python3
"""
Task executor for Codey-OS daemon.

Executes queued tasks using the full run_agent() pipeline — the same code
path used by the interactive CLI.  Both modes are now identical in capability:
layered prompts, RAG, recursive self-critique, linting, hallucination detection.

Daemon-specific behaviour is injected via AGENT_CONFIG overrides:
- confirm_write / confirm_shell set to False  (no interactive prompts)
- _shell_fn replaced with _daemon_shell       (allowlist-only execution)
These are restored after each task so they never bleed into interactive sessions.
"""

import asyncio
import os
import threading
import time
from typing import Any, Dict, Optional

from core.daemon_config import DaemonConfig
from core.state import StateStore
from core.thermal import end_inference, start_inference
from utils.logger import error, warning

# ---------------------------------------------------------------------------
# Daemon shell allowlist
# Commands the daemon may run without user confirmation.
# Extend this list when new safe operations are needed.
#
# Rationale for each prefix:
#   python / python3  — run scripts / test files the agent just wrote
#   pip / pip3        — install packages the agent determines are missing
#   pytest            — run the test suite as part of TDD/fix loops
#   ls / cat / echo   — read-only inspection of files and directories
#   grep              — search file contents; read-only
#   find              — locate files; read-only (daemon never passes -delete)
#   git status/log/diff/show — read-only git introspection; no write ops
#                      (git commit/push/reset are intentionally excluded)
#   cd                — change working directory for subsequent commands
#   pwd / which / env / printenv — environment introspection; read-only
#
# Security note: Python/pip commands are validated to prevent arbitrary code
# execution. Only specific patterns are allowed (e.g., "python script.py",
# "pip install package"). Commands like "python -c 'import os; os.system(...)'"
# are blocked.
# ---------------------------------------------------------------------------
_DAEMON_ALLOWED_PREFIXES = (
    "pytest",
    "ls",
    "cat",
    "echo",
    "grep",
    "find",
    "git status",
    "git log",
    "git diff",
    "git show",
    "cd ",
    "pwd",
    "which",
    "env",
    "printenv",
)

# Dangerous patterns that should be blocked even if prefix is allowed
_DANGEROUS_FLAGS = ["-c", "-e", "-exec", "--eval", "-r", "-m"]

# Allowed Python/pip patterns (more restrictive)
_PYTHON_ALLOWED_PATTERNS = [
    "python ",
    "python3 ",  # Must have space after (not "python -c")
    "pip install ",
    "pip3 install ",  # Only install allowed
    "pytest ",  # Test runner
]


# ---------------------------------------------------------------------------
# T7 telemetry (docs/telemetry_layer_design.md §2.E category "task").
#
# Scope note (2026-09-04): the design's own §2.E table sources `task_id`,
# `task_type`, and `needs_planning` from `core/daemon.py`'s `task_queue`
# row / `_process_planner_tasks()` branch — data that never reaches
# `_execute_task()` today (both call sites, core/daemon.py:1273 and :1361,
# pass only a bare prompt string). This sub-task's file scope explicitly
# excludes core/daemon.py (rule 4 — daemon.py is T8's file), so
# `_execute_task()` below accepts this metadata as optional keyword-only
# parameters and emits nothing at all unless a caller supplies task_id and
# task_type. Until a future daemon.py change (T8) passes real values in,
# this wiring is present but inert in production — the same shape of gap
# as NEW-341, called out explicitly in the T7 handoff rather than forced.
#
# `superseded_by_plan` (design §2.E) is NOT emitted anywhere in this file:
# it covers core/daemon.py:1349-1351, where the raw task_queue row is
# marked done because it expanded into an N-step plan — `_execute_task()`
# is never even called on that path. Emitting it would require
# instrumenting core/daemon.py directly, out of this sub-task's scope.
# ---------------------------------------------------------------------------


def _emit_task_started_telemetry(
    *, task_id: int, task_type: str, needs_planning: bool
) -> None:
    """
    Passive category-E `task_started` observation. Emitted after
    `start_inference()` and before the agent pipeline begins — never a
    gate, never able to block or alter dispatch. Wrapped in a broad
    `except Exception` (mirrors T5/T6's identical helpers) so a telemetry
    failure can never surface as, or block, task execution — this is the
    main daemon task loop.
    """
    try:
        from telemetry import store

        if not store.TELEMETRY_ENABLED:
            return

        from telemetry import recorders

        recorders.record_task_started(
            emitter="codey-os.daemon",
            pid=os.getpid(),
            task_id=task_id,
            task_type=task_type,
            needs_planning=bool(needs_planning),
            started_ts_wall=time.time(),
        )
    except Exception:
        import logging

        logging.getLogger(__name__).warning(
            "telemetry: failed to record task_started for task_executor._execute_task",
            exc_info=True,
        )


def _emit_task_finished_telemetry(
    *,
    task_id: int,
    task_type: str,
    needs_planning: bool,
    start_mono: float,
    terminal_status: str,
    error_class: Optional[str],
    timeout_sec: Optional[int],
    run_stats: Dict[str, Any],
) -> None:
    """
    Passive category-E `task_finished` observation. Same never-crash-the-
    host contract as `_emit_task_started_telemetry` above.

    `run_stats` is whatever `core.agent.get_last_run_stats(thread_id=...)`
    returned for this call's specific worker thread [NEW-345]. Keyed by
    OS-thread identity rather than a single shared "last call" slot: a
    per-thread bucket lookup either finds exactly this call's own stats
    (no other call can share this thread's id while this call is still
    in flight) or finds nothing at all (the callable never started
    executing, e.g. cancelled before the executor picked it up) — an
    honest empty dict, never another task's counters. See the caller
    for how it captures the worker thread's id.

    `retries` is populated from `run_stats["auto_retries"]` — the agent
    loop's own in-loop auto-retry counter (core/agent.py's `auto_retries`),
    per this sub-task's brief ("retry ... counters surfaced from
    core/agent.py's loop"). This is NOT the same quantity as the design
    §2.E table's stated source `task_queue.retry_count` (a daemon-level
    retry-dispatch count this sub-task's scope cannot reach without
    touching core/daemon.py) — flagged explicitly here and in the T7
    handoff rather than silently conflating the two.
    """
    try:
        from telemetry import store

        if not store.TELEMETRY_ENABLED:
            return

        from telemetry import recorders

        duration_ms = (time.monotonic() - start_mono) * 1000.0
        tools_called = run_stats.get("tools_called") or None

        recorders.record_task_finished(
            emitter="codey-os.daemon",
            pid=os.getpid(),
            task_id=task_id,
            task_type=task_type,
            needs_planning=bool(needs_planning),
            finished_ts_wall=time.time(),
            duration_ms=duration_ms,
            terminal_status=terminal_status,
            step_count=run_stats.get("step_count"),
            max_steps=run_stats.get("max_steps"),
            hit_max_steps=run_stats.get("hit_max_steps"),
            tools_called=tools_called,
            retries=run_stats.get("auto_retries"),
            escalated=run_stats.get("escalated"),
            escalation_reason=run_stats.get("escalation_reason"),
            escalation_outcome=run_stats.get("escalation_outcome"),
            error_class=error_class,
            timeout_sec=timeout_sec,
        )
    except Exception:
        import logging

        logging.getLogger(__name__).warning(
            "telemetry: failed to record task_finished for task_executor._execute_task",
            exc_info=True,
        )


def emit_task_timeout_correction(
    *,
    task_id: int,
    task_type: str,
    needs_planning: bool,
    duration_ms: float,
    timeout_sec: Optional[int],
) -> None:
    """
    Corrective category-E `task_finished` observation for `core/daemon.py`'s
    `wait_for(...)`-timeout dispatch sites (NEW-357). Public (no leading
    underscore) because the caller lives in a different module.

    Why this exists: `_execute_task()`'s own `except asyncio.CancelledError`/
    `finally` blocks above contain no `await`, so per CPython's actual
    `asyncio.timeouts.Timeout`/`asyncio.tasks.wait_for` mechanics they run to
    completion -- including emitting a `task_finished` record with
    `terminal_status="cancelled"` -- BEFORE the `CancelledError` can even
    propagate up to `wait_for()`'s own `Timeout.__aexit__`, which is what
    converts it to `TimeoutError` in `core/daemon.py`. There is no way to
    make that first emission correct from inside `_execute_task()` itself;
    a post-hoc corrective second record from the caller, once it actually
    knows the outcome was a timeout, is structurally required.

    This deliberately reuses the existing `task_finished` event_type rather
    than introducing a new one -- `telemetry/schema/v1.json`'s
    `terminal_status` enum already includes both `"cancelled"` and
    `"timeout"`, so no schema change is needed. See
    `telemetry.recorders.record_task_finished()`'s docstring for the
    resulting "two records per task_id, latest wins" consumer obligation
    this establishes.

    Run-stats-derived fields (`step_count`, `tools_called`, `retries`,
    `escalated`, etc.) are deliberately left null/omitted here rather than
    re-queried from `core.agent`'s thread-keyed stats buckets: the
    `loop.run_in_executor()` worker thread that ran the timed-out call is
    NOT killed by the cancellation (it keeps running orphaned in the
    background, per NEW-345), so a second stats read from this caller at an
    indeterminate later time risks reading a DIFFERENT task's now-reused
    thread-id bucket (`get_last_run_stats()` pops on read and a thread id
    can be reused by the pool). An honest null is safer than a wrong value.

    Same never-crash-the-host contract as `_emit_task_finished_telemetry`
    above: broad `except Exception` + warning log, never affects the
    caller's dispatch/`fail_task()` outcome.
    """
    try:
        from telemetry import store

        if not store.TELEMETRY_ENABLED:
            return

        from telemetry import recorders

        recorders.record_task_finished(
            emitter="codey-os.daemon",
            pid=os.getpid(),
            task_id=task_id,
            task_type=task_type,
            needs_planning=bool(needs_planning),
            finished_ts_wall=time.time(),
            duration_ms=duration_ms,
            terminal_status="timeout",
            error_class=None,
            timeout_sec=timeout_sec,
        )
    except Exception:
        import logging

        logging.getLogger(__name__).warning(
            "telemetry: failed to record task_finished timeout correction "
            "for core/daemon.py's wait_for() dispatch",
            exc_info=True,
        )


class TaskExecutor:
    """
    Executes tasks from the daemon's task queue using the full agent pipeline.

    Each task is run via run_agent() in a thread executor so the asyncio event
    loop stays responsive during blocking inference calls.  AGENT_CONFIG is
    temporarily patched to suppress interactive prompts and enforce the daemon
    shell allowlist, then restored unconditionally in a finally block.
    """

    def __init__(self, state: StateStore, config: DaemonConfig):
        self.state = state
        self.config = config
        self.current_task: Optional[Dict] = None

    # ------------------------------------------------------------------
    # Core execution — delegates to the full run_agent() pipeline
    # ------------------------------------------------------------------

    async def _execute_task(
        self,
        prompt: str,
        *,
        task_id: Optional[int] = None,
        task_type: Optional[str] = None,
        needs_planning: Optional[bool] = None,
    ) -> str:
        """
        Execute a single task using the coding.run_agent capability.

        Installs a daemon shell guard and disables interactive confirmations
        via capability parameters, leaving global AGENT_CONFIG untouched.

        The prompt should already be the enriched step string produced by
        daemon._handle_command (includes original task + step number).

        `task_id`/`task_type`/`needs_planning` are optional, keyword-only,
        T7-telemetry-only parameters (see the module-level comment above
        this class). Nothing observation-related is emitted unless both
        `task_id` and `task_type` are supplied — no caller in this
        sub-task's scope supplies them yet (that requires a core/daemon.py
        change, out of scope here). Purely additive: existing callers that
        only pass `prompt` are unaffected.
        """
        start_inference()

        # T7 telemetry setup — never affects control flow below. See the
        # module-level comment above this class for the T7 scope note, and
        # [NEW-345] below (near run_in_executor()) for the thread-identity
        # keying that replaced the old "_seq" mismatch check.
        _telemetry_active = task_id is not None and task_type is not None
        _start_mono = time.monotonic()
        if _telemetry_active:
            _emit_task_started_telemetry(
                task_id=task_id, task_type=task_type, needs_planning=bool(needs_planning)
            )

        _terminal_status = "done"
        _error_class: Optional[str] = None
        # [NEW-345] Initialized here (before the try block), not inside it,
        # so the `finally` block below can always safely check it even if
        # an exception fires before the executor dispatch is ever reached
        # (e.g. in the plugin-manager setup). See the `finally` block's own
        # comment for what an empty list there means — not repeated here so
        # the two descriptions can't drift out of sync.
        _worker_thread_id: list = []
        try:
            from ccos.core.plugin_manager import get_plugin_manager
            from prompts.layered_prompt import invalidate_prompt_cache

            # Fresh file context for every step — previous steps may have
            # written files that must appear in this step's system prompt.
            invalidate_prompt_cache()

            # Clear working memory between daemon steps — previous step's
            # files and turn counter bleed into this step causing stale
            # context and premature LRU eviction of files we haven't seen yet.
            from core.memory_v2 import memory as _mem

            _mem.clear()

            pm = get_plugin_manager()
            if "agent" not in pm._modules:
                pm.load("agent")

            # [NEW-345] Capture the actual worker thread's OS-thread id from
            # inside the callable itself (not e.g. via a wrapping
            # ThreadPoolExecutor API) so it is available even if this
            # await is later cancelled/timed out by the caller — the
            # callable keeps running on its orphaned thread regardless,
            # and core.agent's per-thread stats bucket is keyed by exactly
            # this id (see core/agent.py's module comment above
            # _RUN_STATS_BY_THREAD for why thread identity, not task_id).
            # A single-element list, not a plain variable, so the closure
            # can publish the id back to this scope without a `nonlocal`
            # (there's no enclosing function scope for `_run_capability`
            # to close over other than this one, and list-append avoids
            # any assignment-binding ambiguity). Declared above, before
            # the try block — see the comment there.
            def _run_capability():
                _worker_thread_id.append(threading.get_ident())
                return pm.call_capability(
                    "coding.run_agent",
                    prompt=prompt,
                    history=[],
                    yolo=True,
                    no_plan=True,  # each daemon step is already planned
                    in_subtask=True,  # suppress git prompts; scale max_steps
                    confirm_shell=False,
                    confirm_write=False,
                    shell_fn=self._daemon_shell,
                )

            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, _run_capability)
            response, _ = result
            if isinstance(result, dict) and not result.get("success", True):
                raise RuntimeError(result.get("error") or "Agent capability execution failed")
            return response

        except asyncio.CancelledError:
            # This coroutine's own scope contains no asyncio.wait_for (or
            # equivalent) call — any wait_for/timeout enforcement lives in
            # the caller (core/daemon.py, out of this sub-task's scope).
            # A CancelledError reaching here is therefore always a genuine
            # cancellation of this task, not a distinguishable "this
            # specific call timed out" signal — e.g. asyncio.run()'s own
            # shutdown path cancels the still-pending main-loop task on a
            # real SIGINT (see core/daemon.py's `except KeyboardInterrupt`
            # around `asyncio.run(self._main_loop())`), which surfaces
            # here identically to any other cancellation. Map it to the
            # design schema's dedicated `cancelled` terminal_status
            # (docs/telemetry_layer_design.md §2.E), not `timeout`.
            _terminal_status = "cancelled"
            raise
        except Exception as e:
            import traceback

            _terminal_status = "failed"
            _error_class = type(e).__name__
            error(f"Task execution error: {e}\n{traceback.format_exc()}")
            raise  # re-raise original exception; already logged above
        finally:
            end_inference()
            if _telemetry_active:
                # [NEW-345] Thread-identity lookup replaces the old "_seq"
                # mismatch comparison. A per-thread bucket lookup either
                # finds exactly this call's own bucket (no other call can
                # ever share this worker thread's id while this call is in
                # flight — see core/agent.py's module comment above
                # _RUN_STATS_BY_THREAD) or finds nothing, so there is no
                # separate mis-attribution case left to detect here.
                try:
                    import core.agent as _agent_mod

                    if _worker_thread_id:
                        _stats = _agent_mod.get_last_run_stats(thread_id=_worker_thread_id[0])
                    else:
                        # Empty means this call had not yet published its
                        # worker thread id -- either never dispatched, or
                        # dispatched but cancelled before the callable's
                        # first line (the append) ran. Either way there is
                        # nothing to look up yet; honest null, not a lookup
                        # miss.
                        _stats = {}
                except Exception:
                    # Safe to swallow: this telemetry read is passive
                    # observation only (see the module-level T7 comment
                    # above this class) and never gates or alters task
                    # execution -- the task's actual result/exception was
                    # already determined by the try/except blocks above
                    # this finally. Falling back to an empty stats dict
                    # here means the task_finished record is emitted with
                    # honest nulls for the counters instead of crashing
                    # the daemon's main task loop over a telemetry
                    # read failure.
                    _stats = {}
                _emit_task_finished_telemetry(
                    task_id=task_id,
                    task_type=task_type,
                    needs_planning=bool(needs_planning),
                    start_mono=_start_mono,
                    terminal_status=_terminal_status,
                    error_class=_error_class,
                    timeout_sec=self.config.get("tasks", "task_timeout", default=1800),
                    run_stats=_stats,
                )

    # ------------------------------------------------------------------
    # Daemon shell guard
    # ------------------------------------------------------------------

    def _daemon_shell(self, command: str) -> str:
        """
        Execute a shell command in daemon context.

        Only prefixes listed in _DAEMON_ALLOWED_PREFIXES are permitted.
        Python/pip commands are additionally validated against dangerous patterns.
        Anything else is blocked with a clear message so the model knows
        to restructure its approach rather than silently failing.
        """
        from tools.shell_tools import shell

        cmd = command.strip()

        # Check if it's a Python/pip command (needs special validation)
        is_python_cmd = any(cmd.startswith(p) for p in ["python", "python3", "pip", "pip3"])

        if is_python_cmd:
            # Validate Python/pip commands more strictly
            if not any(cmd.startswith(p) for p in _PYTHON_ALLOWED_PATTERNS):
                warning(f"Daemon: blocked Python/pip command: {cmd[:80]}")
                return (
                    f"[BLOCKED] Daemon mode will not run '{cmd[:60]}'. "
                    "Only 'python script.py' and 'pip install package' are allowed."
                )
            # Check for dangerous flags
            for flag in _DANGEROUS_FLAGS:
                if flag in cmd:
                    warning(f"Daemon: blocked dangerous flag '{flag}' in: {cmd[:80]}")
                    return f"[BLOCKED] Flag '{flag}' is not allowed in daemon mode."
        elif not any(cmd.startswith(p) for p in _DAEMON_ALLOWED_PREFIXES):
            warning(f"Daemon: blocked shell command: {cmd[:80]}")
            return (
                f"[BLOCKED] Daemon mode will not run '{cmd[:60]}' without "
                "explicit authorization. Add the command prefix to "
                "_DAEMON_ALLOWED_PREFIXES in core/task_executor.py to enable it."
            )

        return shell(command, yolo=True)

    # ------------------------------------------------------------------
    # Introspection helpers
    # ------------------------------------------------------------------

    def get_current_task(self) -> Optional[Dict]:
        """Return the task currently being executed, or None."""
        return self.current_task


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_executor: Optional[TaskExecutor] = None


def get_executor() -> TaskExecutor:
    """Return the module-level TaskExecutor singleton."""
    global _executor
    if _executor is None:
        from core.daemon_config import get_config
        from core.state import get_state_store

        _executor = TaskExecutor(get_state_store(), get_config())
    return _executor


def reset_executor():
    """Reset the singleton (used in tests)."""
    global _executor
    _executor = None
