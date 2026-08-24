---
name: new167_recalibration_client_timeout_gap
description: NEW-167 constant recalibration (PLANNER_MIN_PREFILL_TPS/GEN_TPS 20/4->10/2) — CHANGES REQUESTED, uncovers unaddressed client-side timeout that defeats NEW-165's whole purpose
metadata:
  type: project
---

Reviewed the post-live-verification recalibration of `PLANNER_MIN_PREFILL_TPS`
(20->10) / `PLANNER_MIN_GEN_TPS` (4->2) in `utils/config.py`, plus the two
updated hardcoded test expectations in `tests/test_plannd_timeout.py`
(784.5 / 1296.5). This built on the already-approved NEW-164/165 fix
(see [[new164_165_planner_timeout_fix_approved]]).

**The recalibration's own arithmetic and tests are correct** (hand-verified,
655 passed/1 skipped + 68 passed live-run matches prior counts). But tracing
the actual live call chain for point-5's sanity check surfaced a real,
unaddressed bug that neither the original NEW-164/165 review nor this
recalibration caught:

`core/planner_service.py:_request_daemon_plan()` calls
`send_command("command", {...}, timeout=185)` — a **client-side Unix-socket
timeout**, hardcoded, never touched by NEW-164/165/167. This wraps the
entire RPC round-trip for the ONE confirmed live caller of the daemon's
planning RPC (`main.py` -> `core.planner_service.request_plan` ->
`_request_daemon_plan`; `core/daemon.py`'s own docstring calls this "the
interactive CLI's... synchronous planning-oracle RPC" — see also NEW-112,
which documented this as the only live caller but never flagged the
timeout mismatch). The *server-side* formula timeout this whole NEW-164/
165/167 chain has been carefully calibrating (~1296.5s inner, ~1326.5s
outer with the new constants; was already ~663s/~693s even with the
FIRST, since-corrected 20/4 constants) is moot for this caller — the
client already raises `ConnectionError("Connection timed out")` at 185s
and falls through to attempt 2, before the server-side timeout could ever
fire on a real slow/thinking-mode call. This is the exact failure mode
NEW-165 exists to fix, just relocated one more layer up (repeating the
"relocates the bug one layer up" pattern NEW-165 fix 3 was itself
written to avoid for the daemon.py <-> plannd.py boundary).

**Lesson: when reviewing a formula-derived server-side timeout fix, always
trace one more hop outward — to whatever client/RPC layer is calling the
server, not just the layers already touched by the diff.** The prior
NEW-164/165 review's "grep every caller of `send_plan_request_async`"
check (documented in [[new164_165_planner_timeout_fix_approved]]) was
scoped to the async function's callers within the daemon process; it did
not extend to the separate client-side socket helper (`send_command()`)
that wraps the whole RPC from outside the daemon. A formula-timeout fix
inside a server is worthless if a shorter, untouched timeout sits between
the real caller and that server.

**Secondary findings, same review:**
- `utils/config.py`'s NEW-164 comment block (untouched by this delta,
  but shipping in the same uncommitted diff) still cites pre-recalibration
  arithmetic (~667s/~1100s-of-1800s) that's now wrong under the new
  constants (real number ~1296.5s/~500s) — another occurrence of the
  repeated "stale text alongside its own fix, same diff" pattern.
- The new NEW-167 comment claims the constants were "halved again for
  real margin" — arithmetically false: 10 vs measured 10.63 is ~94% of
  it, 2 vs measured 2.15 is ~93% — a ~6-7% cushion, not a halving. Given
  the first calibration attempt was already found ~2x optimistic via live
  measurement, a ~6% margin off one measurement session, described as
  much larger than it is, is worth a second look (policy call for Ish,
  not a silent fix).

Verdict given: recalibration's own diff is correct but do not consider
this round closed — log the client-timeout gap as its own NEW-### entry
before commit (rule 8), it directly undermines whether NEW-165 is
actually resolved in the one place that matters (the live caller).
