"""
Daemon Control Plugin — thin CCOS adapter over core/daemon.py.

Exposes only the daemon's read-only status queries (ping/status/health/
task lookup) and single-task cancellation. core/daemon.py's socket
protocol registers 7 handlers total; two are deliberately left unwrapped
here:

- `shutdown` (core/daemon.py's daemon_shutdown()) stops the entire daemon
  process Codey-OS depends on being up. An agent triggering this as a
  side effect of its own planning would kill the daemon mid-session.
- `command` (no plugin function here — would need to wrap send_command
  directly) is the real "submit a new prompt for the daemon to execute"
  entry point. It's genuinely useful but triggers real 7B model
  inference and real tool execution as a side effect of an agent
  calling a capability, which is a different risk class than a status
  query.

Both are the same risk class as core/lora_import.py's
swap_to_finetuned_model, left unwrapped in the coding.finetune plugin
pending Ish's explicit decision. Same judgement applied here rather than
wrapping mechanically.

`cancel` is exposed: it only affects one pending task by ID (scoped,
reversible in that no data or process state beyond that task is
touched), the same "moderate" tier as finetune's backup/rollback
functions.
"""

from ccos.plugins._pathutil import ensure_repo_root_on_path

ensure_repo_root_on_path()

from core.daemon import check_pid_file as _check_pid_file
from core.daemon import daemon_health, daemon_ping, daemon_status
from core.daemon import is_daemon_running as _is_daemon_running
from core.daemon import send_command


def daemon_check_pid_file() -> dict:
    """Read-only: whether a daemon PID file indicates another instance is running."""
    return {"running": _check_pid_file()}


def daemon_is_running() -> dict:
    """Read-only: whether the daemon is running, probed via its Unix socket."""
    return {"running": _is_daemon_running()}


def daemon_get_task(task_id: int = None, limit: int = 20) -> dict:
    """Look up one task by ID, or list recent tasks (newest first) if task_id is None."""
    data = {"limit": limit}
    if task_id is not None:
        data["id"] = task_id
    return send_command("task", data)


def daemon_cancel_task(task_id: int) -> dict:
    """Cancel one pending task by ID. Does not affect the daemon or other tasks."""
    return send_command("cancel", {"id": task_id})


def test() -> bool:
    """Plugin self-test — verify a read-only, no-daemon-required capability runs."""
    result = daemon_check_pid_file()
    assert isinstance(result, dict) and "running" in result, "Expected dict with 'running'"
    return True
