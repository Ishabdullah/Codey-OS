---
name: new83-embed-server-kill-by-pid-approved
description: core/embed_server.py NEW-83 fix (bare pkill -> positively-identified PID kill) — APPROVED, with two process lessons about scope claims and TOCTOU write-ups
metadata:
  type: project
---

## What was reviewed and approved

`core/embed_server.py`'s `_kill_port_occupant()` rewrite: replaced the
CLAUDE.md-rule-3-violating `pkill -9 llama-server` fallback with
`_find_port_occupant_pid()` (parses `/proc/net/tcp`+`tcp6`, prefers LISTEN
rows, fd-scans for the owning PID) and a secondary
`_find_pid_via_registered_slot()` fallback (reads `resource_gate`'s
cross-process slot store, verified alive + `/proc/<pid>/cmdline` names
`llama-server` before trust — guards PID recycling). Fails loudly (no
kill, `start()` returns `False`) if neither path identifies a PID. 14
tests pass, 1 self-skips on `PermissionError` reading `/proc/net/tcp` in
this dev sandbox — confirmed real, matches Android/Termux's known
`/proc/net/tcp` restriction, so live-verifier confirmation was
recommended before treating this as more than code-complete.

## Lesson 1: a task's "these files are a separate parallel fix, don't
review them" framing can still miss a bundled hunk **inside** the file
you were told to review

The task correctly excluded `core/loader_v2.py`/`planner_loader.py`/
`lora_import.py` (a genuinely separate, currently-CHANGES-REQUESTED
sub-task — see [[resource_gate_subtask2_confirm_mark_slot_leak]]). But
`core/embed_server.py`'s own diff also contained a second, distinct
change: a `resource_gate.register_slot()`/`release_slot()` accounting
hookup (same TODO.md 7.4 sub-task 2, but a *different* call-site pattern
than the one that got rejected). Always read the full diff for hunks
that don't match the stated single-purpose description, even in a file
explicitly scoped "in". In this case the second hunk turned out to be
structurally safe (register happens post-health-check with no separate
confirm step to leak between, unlike the rejected loader-wiring
pattern) — but that had to be verified independently, not assumed
because "the task didn't mention it."

## Lesson 2: don't let a post-kill verification check get credited with
covering a race it doesn't cover

`_kill_port_occupant()`'s post-kill `_port_is_bound()` re-check looks
like it would catch a PID-recycling wrong-kill, but it only catches the
case where the *real* occupant (or its child) is still listening after
the kill. It does NOT catch: real occupant exits naturally (freeing the
port) -> PID recycles to an unrelated process -> our delayed
`os.kill(pid, 9)` hits the unrelated process -> port is already free ->
check reports success. Caught myself almost writing this up as
"mitigated" before re-tracing the exact ordering. When a downstream
check looks like it closes a TOCTOU window, trace the specific
interleaving where the resource state changes for a reason *unrelated*
to the race, not just the race's most obvious outcome.

## Also verified, not blocking

- `core/resource_gate.py` itself is untouched in this round (not in
  `git status`) — `register_slot`/`release_slot`/`list_slots`/
  `SLOT_STATUS_RESIDENT` all pre-existed from the already-approved
  sub-task 1.
- The `_pid_owning_inode()` fd-scan's coarse per-PID try/except (one
  `readlink` failure skips the rest of that PID's fds) is a pre-existing
  quality issue unchanged by this diff, not a new regression — confirmed
  by diffing the old code's identical try-wraps-whole-inner-loop shape.
- Cross-process kill-a-healthy-sibling-server risk (two processes both
  calling `start_embed_server()`) is pre-existing "kill and replace on
  every start()" design intent, not introduced by this fix — this fix
  actually narrows the blast radius of that existing behavior (specific
  PID instead of blind name match).
