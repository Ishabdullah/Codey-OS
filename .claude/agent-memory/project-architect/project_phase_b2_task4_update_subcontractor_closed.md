---
name: project_phase_b2_task4_update_subcontractor_closed
description: Phase B2 task 4 third-module (CRMService.update_subcontractor + route) finalized and committed 2026-08-27
metadata:
  type: project
---

Finalized and committed the Core-side groundwork for the
`subcontractor-recruiter.js` write-through conversion (`NEW-224`'s
blocker): `CRMService.update_subcontractor()` + `POST
/api/v1/subcontractors/{id}/update`. Code-complete + code-reviewer-
approved, re-ran `python -m pytest tests/ -q` myself (789 passed, 1
skipped, 64.82s) rather than reusing the cited number, per the
`NEW-223` lesson.

**Why:** This round ships NO JS changes — `~/Codey-Aigentik/
subcontractor-recruiter.js`/`owner-command.js` remain untouched. The
actual write-through conversion is still a separate, not-started
future round. Docs (§4, §6.4 of `CODEY_MASTER_PLAN.md`) were written to
say this explicitly, since a casual reader could otherwise assume "task
4 module 3 done" meant the JS cutover happened, the way modules 1
(DNC) and 2 (email/sms-rules) did include real JS conversion.

**How to apply:** Filed 3 new findings from the reviewer's pass —
`NEW-238` (create/update falsy-email normalization mismatch, real but
non-trivial fix), `NEW-239` (unvalidated JSON-column values -> leaky
500, same class as `NEW-221`, not new), `NEW-240` (WRITE-without-READ
RBAC latent gap recurring identically across 3 methods —
`update_subcontractor_qualification`, `update_appointment_status`,
`update_subcontractor` — across 2 review rounds without ever being
ledgered before; found by grepping code-reviewer's own memory files
for the pattern rather than re-deriving it). Commit `39c0f98`, pushed
to `origin main`. Exactly the expected file set was staged (verified
via `git diff --stat` before `git add`, per
[[feedback_stage_files_by_scope_not_by_dirty_tree]]) — no unrelated
dirty-tree files existed this round.

Next Phase B2 unblocked work: the actual `subcontractor-recruiter.js`/
`owner-command.js` JS conversion (two-Core-call sequencing already
specified in §6.4), or `contacts.js`/`customer-module.js`/
`calendar.js`/comms modules once their respective blockers
(`NEW-212`/`NEW-215`, general-update gap, `NEW-232`/`NEW-233`) are
resolved. See [[project_phase_b2_task4_email_sms_rules_closed]] and
[[project_phase_b2_task4_comms_scoping_blocked]] for the sibling
module states.
