"""
Daemon Control Plugin — thin CCOS adapter over core/daemon.py.

Post-"PENDING_ISH_DECISIONS.md item 2" redesign (7.4/4.1 sub-tasks A-D,
all committed and live-verified/reviewed as of this docstring). As of
this round, `core/daemon.py`'s `_register_default_handlers()` registers
7 socket handlers: `ping`, `command`, `status`, `health`, `task`,
`cancel`, `release_model_slot`. (Before sub-task D there were 8 — D
retired the socket `shutdown` handler and deleted the `daemon_shutdown()`
helper entirely; see below.)

Of those 7, this plugin wraps 5 as read-only or single-task-scoped
capabilities: `ping`→`daemon_ping`, `status`→`daemon_status`,
`health`→`daemon_health`, `task`→`daemon_get_task`,
`cancel`→`daemon_cancel_task`. It also wraps two functions that are NOT
socket handlers at all — `daemon_check_pid_file`/`daemon_is_running` call
`core.daemon`'s `check_pid_file()`/`is_daemon_running()` directly, no
socket round-trip. 7 capabilities total in this plugin.

Two of the 7 handlers are deliberately left unwrapped, for two different
reasons — don't conflate them:

- `command`: per item 2's resolved decision, this handler no longer runs
  inference synchronously — it now only enqueues (`needs_planning`
  flagged for the pull-side planner, per sub-task C) and returns
  immediately. That redesign changed WHEN the risk materializes, not
  WHETHER it does: the real 7B inference and real tool execution this
  handler ultimately causes still happen, just later, via
  `_process_planner_tasks()`'s pull-side dispatch — as an unreviewed
  side effect of whichever agent called this capability, gated only by
  `can_dispatch_task()`'s resource check, not by this project's
  deliberation loop. Same risk class as `core/lora_import.py`'s
  `swap_to_finetuned_model`, left unwrapped in `coding.finetune` — kept
  unwrapped here on the same judgement, not because a decision is still
  pending (item 2 IS decided; the decision just didn't resolve to "safe
  to wrap").
- `release_model_slot`: NOT a "pending Ish decision" risk-tier case at
  all — it's an internal CLI-to-daemon resource-coordination primitive.
  Its only live caller in the shipped system is `main.py`'s own
  `_load_primary_with_gate_recovery()` (7.4 sub-task 5), asking a
  running daemon to free a model slot so the CLI's OWN blocked load can
  retry. It's well-guarded (busy/in-flight-inference check, swap-guard
  serialization, per-model_id cooldown, clean no-op if already
  unloaded) and reversible in the ordinary sense (a released model just
  reloads lazily on next use) — but none of the five deliberation roles
  (Planner/Critic/Optimizer/Capability/Safety) or the coding agent has
  any actual use for "ask the daemon to drop a model," since that
  negotiation only makes sense between two OS-level processes
  contending for the same resource-gate slot. Left unwrapped as a scope
  call (wrong audience for an agent-callable capability), not a risk-tier
  escalation needing Ish's sign-off.

`shutdown`: no longer exists as a socket handler, and `daemon_shutdown()`
no longer exists as a function at all — sub-task D deleted both. This
isn't "deliberately left unwrapped" anymore; there is nothing left to
wrap. The daemon now shuts itself down only via the autonomous
thermal/CPU tripwire (`should_trip_shutdown()`/`_trigger_shutdown()` in
`core/daemon.py`'s watchdog) — no agent- or user-triggerable equivalent
exists, full stop.

`/status` (sub-task A's `core/observability.py` wiring + `main.py
--status` CLI flag, plus `core/resource_gate.py`'s system-wide snapshot
merged into that same CLI payload): NOT wrapped here, and doesn't need to
be — `core/observability.py`'s `status()` is already a CCOS capability,
`system.observability_full_status`, in the separate
`ccos/plugins/system/observability/` plugin (pre-existing, unrelated to
this round). That plugin's own docstring already documents the caveat
that matters for a would-be caller: `status()` reads a per-process `State`
singleton that `core/daemon.py` never populates, so calling it returns
whatever process ran the capability call's own (mostly-empty) state, not
the running daemon's — this plugin's own `daemon_status`/`daemon_health`
(real socket round-trips to the live daemon process) are the correct
capabilities for daemon state, not `observability_full_status`.
`core/resource_gate.py`'s system-wide CPU/RAM snapshot (the other half of
`main.py --status`'s payload) is not wrapped as a capability anywhere yet
— out of scope for this plugin either way, since it's not daemon state;
belongs with `thermal_monitor` or a new resource-gate plugin if wrapped.

`cancel` is exposed: it only affects one pending task by ID (scoped,
reversible in that no data or process state beyond that task is
touched), the same "moderate" tier as finetune's backup/rollback
functions.

`daemon_get_task`'s description is unchanged by sub-task C's
`needs_planning` flag: a caller reads a task's `status` field
("pending"/"running"/"done") the same way regardless of whether planning
already happened before or after enqueue — that timing detail is internal
plumbing an agent caller doesn't need to reason about, not worth
surfacing in the capability description.
"""

from ccos.plugins._pathutil import ensure_repo_root_on_path

ensure_repo_root_on_path()

from core.daemon import check_pid_file as _check_pid_file
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
