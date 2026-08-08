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

## Queue (empty so far — populated as model-load-dependent items are code-completed)

*(No entries yet as of 2026-08-08. This file will fill in as Phase 1/4
items that touch `core/loader_v2.py`/`core/daemon.py`'s model-loading
paths reach code-complete status.)*

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
