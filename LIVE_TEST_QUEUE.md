# Live Test Queue — for Ish to run without Claude active

**Why this file exists:** per CLAUDE.md rule 2, this device has crashed
from concurrent model loads before. Ish has confirmed the actual trigger
is running Claude (this agent) *at the same time* as the 7B/1.5B/embed
models — the three models alone, without Claude also running, are within
the device's real limit. So: while Claude is doing TODO.md work, any item
that would require loading a model live is **not** executed by Claude —
it's code-complete + unit/mock-tested only, and the specific live-test
step needed is recorded here instead, for Ish to run himself later
(without Claude active) once there's something worth testing.

Add an entry here any time a TODO.md item's real verification needs a
live model load. Update `TODO.md`'s own note for that item to point here
plus "code-complete, live test deferred — see LIVE_TEST_QUEUE.md."
Ish logs any issue found running these back into `NEW_ISSUES.md` per the
normal convention (Confirmed/Suspected, next `NEW-##` ID).

---

## Queue

### [NEW-83] `core/embed_server.py`'s port-occupant kill logic — confirm real PID identification works on-device

- **What was built and reviewed:** `_kill_port_occupant()`'s bare `pkill
  -9 llama-server` (a CLAUDE.md rule 3 violation) replaced with
  positively-identified PID killing: `_find_port_occupant_pid()` (parses
  `/proc/net/tcp`+`tcp6`) as primary, `_find_pid_via_registered_slot()`
  (checks `resource_gate`'s residency store) as secondary fallback, fails
  loudly if neither identifies a PID. Code-reviewer-approved (round 6,
  2026-08-09). 14/14 new tests pass, but one self-skips because
  `/proc/net/tcp` returned `PermissionError` in the dev sandbox — this is
  suspected to match a real Android/Termux restriction on that path for
  unprivileged apps.
- **What the live test should do:** on the actual device, deliberately
  occupy the embed server's port (8082) with a foreign process, then start
  `embed_server` and confirm: (1) it correctly identifies and kills the
  right PID (not a bare-name kill of anything else running), (2) it
  actually starts successfully afterward, (3) if `/proc/net/tcp` really is
  unreadable here, confirm the registered-slot fallback path is what's
  actually firing (add temporary logging if needed to see which path
  succeeded) — this determines whether the "secondary fallback" is
  actually the primary real-world mechanism, which matters for how
  seriously to take `NEW-86`'s residual PID-recycling race.
- **RAM discipline reminder:** this test only needs the embed server
  itself running, not the full 7B/1.5B stack — keep it isolated, run
  `free -h` before/after per rule 2 regardless.
- **What to log back and where if it fails:** if `/proc/net/tcp` is
  confirmed unreadable on-device and the registered-slot fallback also
  fails to identify the occupant in some real scenario, log a new
  Confirmed `NEW-##` finding — this would mean the fix's "fail loudly
  instead of killing blind" behavior could produce real, repeating
  startup failures on this device, not just a theoretical edge case.

## Format for future entries

```
### [Item ref, e.g. TODO.md 7.4] Short description of what needs live-testing
- What was built and unit/mock-tested (commit ref).
- Exactly what the live test should do (steps, expected outcome).
- RAM discipline reminder specific to this test if relevant (e.g. "confirm
  both 7B and 1.5B stay resident per the sequential-swap design" or
  "confirm only one model loads at a time").
- What to log back and where if it fails.
```
