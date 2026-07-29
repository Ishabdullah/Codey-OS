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
from typing import Dict, Optional

from core.daemon_config import DaemonConfig
from core.state import StateStore
from core.thermal import end_inference, start_inference
from utils.config import AGENT_CONFIG
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

    async def _execute_task(self, prompt: str) -> str:
        """
        Execute a single task using the full run_agent() pipeline.

        Installs a daemon shell guard and disables interactive confirmations
        for the duration of the call, then unconditionally restores the
        previous AGENT_CONFIG values so interactive sessions are unaffected.

        The prompt should already be the enriched step string produced by
        daemon._handle_command (includes original task + step number).
        """
        start_inference()
        try:
            from core.agent import run_agent
            from prompts.layered_prompt import invalidate_prompt_cache

            # Fresh file context for every step — previous steps may have
            # written files that must appear in this step's system prompt.
            invalidate_prompt_cache()

            # Clear working memory between daemon steps — previous step's
            # files and turn counter bleed into this step causing stale
            # context and premature LRU eviction of files we haven't seen yet.
            from core.memory_v2 import memory as _mem

            _mem.clear()

            # Save and override AGENT_CONFIG for daemon execution.
            _saved = {
                "_shell_fn": AGENT_CONFIG.get("_shell_fn"),
                "confirm_shell": AGENT_CONFIG.get("confirm_shell"),
                "confirm_write": AGENT_CONFIG.get("confirm_write"),
            }
            AGENT_CONFIG["_shell_fn"] = self._daemon_shell
            AGENT_CONFIG["confirm_shell"] = False  # guard is in _daemon_shell
            AGENT_CONFIG["confirm_write"] = False  # daemon writes without prompting

            try:
                loop = asyncio.get_event_loop()
                response, _ = await loop.run_in_executor(
                    None,
                    lambda: run_agent(
                        prompt,
                        history=[],
                        yolo=True,
                        no_plan=True,  # each daemon step is already planned
                        _in_subtask=True,  # suppress git prompts; scale max_steps
                    ),
                )
                return response
            finally:
                AGENT_CONFIG.update(_saved)

        except Exception as e:
            import traceback

            error(f"Task execution error: {e}\n{traceback.format_exc()}")
            raise  # re-raise original exception; already logged above
        finally:
            end_inference()

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
