---
name: round-daemon-control-4-1-subtask-c-scoping
description: 4.1 sub-task C (gate queue dispatch, move planning to pull side) scoped 2026-08-10, NEW-112 found and resolved the response-contract question
metadata:
  type: project
---

Scoped WORK_QUEUE.md Track 3 item 2 / TODO.md 4.1 sub-task C on
2026-08-10, desk-only, no code changed (see [[project_round_daemon_control_4_1_scoping]]
for sub-tasks A/B context).

**Key finding (NEW-112, Confirmed):** `core/daemon.py`'s `_handle_command`
enqueue branches (`planner.add_tasks`, `state.add_task`) have zero live
callers today. The only live caller of the `command` socket cmd anywhere
in the shipped system is `core/planner_service.py:_request_daemon_plan()`,
which always sends `plan_only: True` and takes an early return before
either enqueue branch runs — it's a synchronous planning-oracle RPC used
by `main.py`'s interactive CLI to get plan text for local step-by-step
execution, never a real "hand this to the daemon queue" path. This
resolved the parent task's flagged response-contract worry as moot (no
live caller reads `message`/`task_ids`/`task_id`) and reshaped the
sub-task's actual scope.

**Why this matters for future rounds:** grep-based "who calls this
handler" checks caught something a docstring/spec-reading pass alone
would have missed — the *intended* design (per `daemon_control.py`'s own
docstring, calling `command` "the real submit-a-prompt entry point") and
the *live* usage had diverged. Before scoping any change to a
socket/API handler's contract, grep for every actual live caller
(`send_command("cmd_name"`, raw `{"cmd": ...}` payloads, any shell-script
callers) before assuming the handler's docstring describes current
reality.

**Design decision made without escalating to Ish:** `cpu_percent is None`
(confirmed always true on this device, NEW-108 — `/proc/stat` permission
denied) is treated as "signal unmeasured, don't refuse solely on it" —
mirrors `can_admit()`'s own existing temperature-None fail-open
precedent (`core/resource_gate.py:877-879`). Fail-closed would
permanently wedge daemon dispatch on this exact hardware, making the
sub-task unlive-verifiable by construction. This was decided by finding
in-module precedent, not asked to Ish, since it followed an existing
established pattern rather than inventing new policy.

**How to apply:** when scoping resource-gate consumers, always check
whether an existing per-signal None/unmeasurable convention already
exists in `can_admit()` before treating a new None-handling question as
needing product-owner input — CLAUDE.md rule 6 territory (correcting the
record) applies here too if a later round finds this precedent doesn't
actually generalize.
