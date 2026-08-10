---
name: round-daemon-control-4-1-scoping
description: 4.1/daemon-control-redesign scoping pass (2026-08-09) — 5-sub-task order (A-E) handed off, sub-task A ready, GUI mutual-exclusion signal open question to Ish
metadata:
  type: project
---

TODO.md 4.1 / WORK_QUEUE.md Track 3 item 2 (daemon control redesign,
`PENDING_ISH_DECISIONS.md` item 2) was scoped desk-only on 2026-08-09,
no code changed. Full breakdown written into WORK_QUEUE.md item 2 and
TODO.md's 4.1 line.

**Why:** the decision was 100% paper/zero implementation; before handing
implementer anything, needed to verify the decision text's premises
against live code, since two didn't hold up (`daemon_shutdown` is in
`core/daemon.py`, not the plugin; no shipped script actually calls the
socket `shutdown` handler — `codeydOS stop` uses `kill -TERM` against
SIGTERM instead, so retiring the socket path is safe).

**How to apply:** sub-task A (rolling resource snapshot in
`core/resource_gate.py` reusing `core/sysmon.py`'s CPU sampler +
`/status` CLI wiring) is the one ready to hand to implementer now — no
process-lifecycle risk. Sub-tasks B (interactive-lock, PID-bearing like
`check_pid_file()`), C (gate dispatch + move planning off the socket
handler onto the pull side), D (autonomous shutdown tripwire via
`_trigger_shutdown()` only, retire external shutdown trigger), E
(plugin/manifest doc update) all require mandatory code-reviewer per
rule 4. **One open question blocks B's GUI half**: `gui/server.py`
already tracks real connected websocket clients (`clients` set,
`gui/server.py:122`) — that's the correct mutual-exclusion signal, NOT
GUI-process-liveness (`gui-server.pid`), which would make the daemon do
zero background work for an entire `codey-start` session regardless of
whether anyone's looking at the page. Whether the GUI half of the lock
ships in sub-task B or is deferred/decided separately needs Ish's call
before B starts on the GUI side — TUI half is unambiguous and can
proceed.

Also logged `NEW-106`/`NEW-107`: `core/observability.py`'s
`temperature`/`cpu_usage`/`memory_usage` properties are wrong-signal
(sampling temp, not device heat; per-process, not system-wide) — real
signals for 4.1 must come from `core/thermal.py`/`core/resource_gate.py`/
`core/sysmon.py` instead. See [[project_work_queue_pointer]].
