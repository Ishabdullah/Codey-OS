---
name: feedback-verification-wording-precision
description: When documenting verification in PROJECT_PLAN.md/PROJECT_LOG.md, use the exact tier the user specifies (e.g. "code-reviewer-verified against a live scratch instance") rather than collapsing to "code complete" or "fully live-verified".
metadata:
  type: feedback
---

There are more than two verification tiers in this project, and the
wording used to describe them in the docs must match reality precisely.
Beyond plain "code complete" (static/mock only) and "fully live-verified"
(live-verifier agent confirmed via the real, daemon-driven path), there's
a middle tier: code-reviewer independently running the real code on a
scratch instance/port and confirming real behavior directly (e.g. actual
curl/websocket calls, real PID-tracked teardown) without going through
the production daemon-managed startup path.

**Why:** Ish explicitly asked (Round 2, C-2 GUI security task, 2026-07-29)
for this to be characterized as "code-reviewer-verified against a live
scratch instance" — neither "code complete only" (understates real
evidence gathered) nor "fully live-verified" (overstates it, since the
actual daemon-managed startup path with real env-var propagation was
never exercised).

**How to apply:** when writing PROJECT_PLAN.md/PROJECT_LOG.md entries,
ask what kind of verification actually happened before defaulting to a
binary code-complete/live-verified label. If code-reviewer ran real code
against a scratch instance/port (not mocks, not through the real
production launch path), name that tier explicitly rather than rounding
up or down. See [[project-c2-gui-security-status]] for the case this came
from.
