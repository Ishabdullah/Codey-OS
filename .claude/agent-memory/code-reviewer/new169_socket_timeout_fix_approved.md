---
name: new169_socket_timeout_fix_approved
description: NEW-164/165/167/169 chain final pass — core/planner_service.py client-side socket timeout fix — APPROVED w/ 2 non-blocking findings logged
metadata:
  type: project
---

Closes the NEW-164/165/167/169 timeout-chain saga (see
[[new167_recalibration_client_timeout_gap]] for the round that found the
gap this fixes). `core/planner_service.py:_request_daemon_plan()`'s flat
`timeout=185` replaced with `compute_planner_timeout(...) + 30.0 + 10.0`,
mirroring `core/daemon.py`'s own `+30.0` outer buffer exactly, then adding
a fresh `+10.0` for the socket hop. Verified:

- Formula inputs (`estimate_tokens(PLANNER_PROMPT) + estimate_tokens(prompt)`)
  hand-matched line-for-line against `core/daemon.py`'s equivalent — not
  just structurally similar.
- **Traced the FULL chain this time, including a file the prior two
  review rounds never opened: `core/planner_client.py`.**
  `send_plan_request_async()` just delegates via `run_in_executor` to
  `core/plannd.py:get_plan()` — no independent timeout of its own. Also
  verified `get_plan()`'s local `max_tokens` var resolves to
  `PLANNER_MAX_TOKENS` on the normal path (matches what daemon.py/
  planner_service.py use), so the "inner fires first" ordering invariant
  the whole formula design depends on actually holds. **Lesson: when a
  chain has been reviewed 2+ times already and a new gap keeps surfacing
  one layer further out each time, explicitly open every module named in
  an `import` statement inside the diff, not just the files the diff
  edits** — `core/daemon.py`'s new code imports `send_plan_request_async`
  from `core/planner_client.py`, a file untouched by the diff and easy to
  skip.
- `core/daemon.py`'s server-side accept loop (`_handle_client`) has no
  additional wrapping timeout beyond the ones already fixed — confirmed
  by reading the full function.
- 658 passed/1 skipped (`tests/`) and 68 passed (`ccos/tests/`) — literal,
  matches predicted +3 over prior baseline (655+68).
- New test file's `send_command`/`is_daemon_running` mocks patch
  `core.daemon.<name>`, and `_request_daemon_plan()` does
  `from core.daemon import is_daemon_running, send_command` **inside the
  function body** (not module-level) — confirmed this makes the mock
  land on the real call, not a copy bound at import time.
- Both `utils/config.py` comment corrections (this round's actual ask)
  verified by hand: 1296.5s recompute exact, 94%/93% margin hand-check
  exact — no shared-budget or "halved" language reintroduced.

**Two non-blocking findings, not logged in this diff — should be logged
to NEW_ISSUES.md next round (rule 8):**
1. The `except Exception: socket_timeout = 1400.0` fallback is itself a
   flat constant in a chain whose whole thesis is "no flat constants."
   It's provably safe only up to ~3060 estimated prompt tokens (beyond
   that, `daemon`'s computed outer timeout exceeds 1400 and the client
   becomes the shortest link again — NEW-169's exact bug shape,
   reintroduced at the tail). Narrow trigger (import failing in the CLI
   process only, not the daemon process) but worth a line rather than
   silently trusting "comfortably above the worst case."
2. `tests/test_planner_service_daemon_socket_timeout.py`'s test 2 (the
   one that actually asserts the cross-layer "client always outlives
   daemon's outer timeout" invariant) recomputes
   `compute_planner_timeout(...) + 30.0` **inside the test** rather than
   importing/calling anything from `core/daemon.py`. If daemon.py's own
   `+30.0` buffer is ever changed, this test can't see it and stays
   green while the real invariant silently breaks. Test 1 doesn't have
   this problem (its assertion is against the real formula end-to-end).
   Suggestion: a shared `compute_daemon_outer_timeout()` helper both
   files call, rather than three independent `+ 30.0` literals plus a
   fourth in the test.

Verdict: **approved, chain now genuinely complete** (checked all the way
out through `core/planner_client.py` and `main.py`, no fourth
independent timeout found) — the two findings above are follow-up
housekeeping, not blockers.
