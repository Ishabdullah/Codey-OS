---
name: cleanup-round-new227-new222-new237-closed
description: 2026-08-27 quick-wins round closed three findings (NEW-227 token accumulation, NEW-222/NEW-237 routing quirk); reviewer's stderr-warning follow-up applied same-round
metadata:
  type: project
---

Cleanup round 2026-08-27 (separate from Phase B2, done as a "quick wins"
pass while Phase B2's next step waits on Ish) closed three findings:

- **NEW-227** — `tools/provision_ai_agent_auth.py`'s `provision()` now
  revokes every prior unrevoked token for the `ai_agent` user before
  issuing a new one, closing an unbounded-token-accumulation gap. The
  code-reviewer's one non-blocking recommendation (add a runtime stderr
  warning, since the docstring-only warning wasn't loud enough on the
  actual footgun path — a rerun silently kills whatever token is
  currently deployed in `config.json`) was applied in the same round by
  the requester directly, not deferred to a follow-up round.
- **NEW-222 / NEW-237** — fixed for the 4 by-id `GET` branches that
  exist in `restoricon_core/api/routes.py` today (`customers`,
  `projects`, `subcontractors`, `appointments`); each branch's match
  condition now rejects a trailing `/`-segment after the id so an
  unmatched action suffix 404s instead of raising `ValueError` (400).
  Not audited for reintroduction elsewhere in the Core or in future
  routes — flagged explicitly as a possible future finding, not this
  one reopened.
- **NEW-226** confirmed already closed separately in `Codey-Aigentik`
  (commit `0398396`, docs-only) — verified untouched this round via
  `git status`/`git diff --stat` (nothing in `~/Codey-Aigentik` in the
  changed file set).

**Residual, logged not fixed:** `GET /api/v1/customers/` (empty
trailing id segment) still 400s via `int("")` — same family, different
shape (empty segment vs. extra segment), not covered by this round's
guard. Open in `NEW_ISSUES.md` for a future round.

**Why noted:** demonstrates the project's convention in practice — a
reviewer's non-blocking recommendation, when cheap and purely additive
(a print statement, no logic change), gets applied same-round rather
than spawning a new NEW-## entry for something this small. Contrast
with larger findings (routing-shape gaps, design questions) which do
get their own NEW-## entries even when found in the same round.

**How to apply:** when closing out a reviewer's non-blocking follow-up,
check whether it's small/additive enough to just do immediately (as
here) vs. scope-worthy of its own finding — don't reflexively spin up a
new NEW-## for every non-blocking comment.

Full verification: `python -m pytest tests/ -q` → 814 passed, 1 skipped,
re-run fresh at commit time, matching the implementer's and reviewer's
earlier runs (stderr addition is output-only, no logic change).
