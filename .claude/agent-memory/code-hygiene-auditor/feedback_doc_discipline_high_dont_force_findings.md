---
name: feedback-doc-discipline-high-dont-force-findings
description: This project's tracking docs (master plan, PROJECT_LOG, NEW_ISSUES) self-correct constantly and are usually accurate — a hygiene pass here should expect mostly-clean results, not manufacture findings
metadata:
  type: feedback
---

Rule 6 (correct the record) and rule 12 (never assume, read the artifact)
are actually followed in this project's own history — the master plan is
full of explicit self-corrections ("this document previously said X, Ish
caught it, here is the real number"), and constants/claims checked against
the live code during a 2026-08-25 audit matched almost everywhere.

**Why this matters:** it's tempting, when asked to do a broad sanity pass,
to pad the output with marginal or cosmetic findings to look thorough. In
this project that's actively counterproductive — the signal-to-noise the
maintainers already have is high, and a padded report makes it harder to
see the one real thing (see [[project_master_plan_sanity_audit_2026-08-25]]
for the one real finding that pass turned up: a commit message overclaiming
review approval that the tracked docs correctly did NOT claim).

**How to apply:** when a broad audit comes back mostly clean, say so
plainly and report the small number of real findings with full confidence
ratings, rather than inflating minor stylistic notes into "issues." Do
still report genuine cosmetic slop when it's real (stale `__pycache__` for
a deleted module, a leftover comment) — just don't manufacture severity.
