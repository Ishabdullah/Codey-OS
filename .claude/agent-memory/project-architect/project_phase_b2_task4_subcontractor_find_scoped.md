---
name: phase-b2-task4-subcontractor-find-scoped
description: 2026-08-27 subcontractor-recruiter.js continuation — find_subcontractor() Core method scoped, not implemented; update_subcontractor() alone was insufficient
metadata:
  type: project
---

Phase B2 task 4's third module (`~/Codey-Aigentik/subcontractor-recruiter.js`)
continuation round scoped `CRMService.find_subcontractor()` + a `q`-param
route branch, but did NOT implement it — no subagent-invocation tool was
available in this session, so the round ends at a written spec in
`CODEY_MASTER_PLAN.md` §6.4 for whoever picks it up next.

**Why:** the prior round's `update_subcontractor()` (commit 39c0f98) was
believed to "unblock the JS conversion," but re-reading the 682-line file
in full (not trusting the prior round's summary) showed it only unblocked
the *write* half. `findSubcontractor()`'s fuzzy phone/email/name lookup —
used on every inbound SMS/email via `role-router.js:119-121` plus six
`owner-command.js` call sites — has no Core equivalent at all (NEW-241).
Advisor review rejected converting just the two write call sites
(`index.js:959,1290`) as an isolated slice: with reads still on local
JSON, it would be an unverifiable shadow-write that lets NEW-234's
null-overwrite bug silently diverge the two copies of a record.

**How to apply:** when a "the last round unblocked X, now do X" task
handoff arrives, re-verify the actual claim by reading the current file in
full, not the prior round's characterization of what it unblocked —
"unblocks the write" and "unblocks the conversion" are not the same
claim, and this project has now hit that gap twice (see also
[[project_phase_b2_task4_comms_scoping_blocked]] for a similar
external_id/idempotency prerequisite gap found only on close reading).
Also: `createOrUpdateSubcontractorLead()`'s upsert/dedup logic (NEW-242)
is a second, separate prerequisite gap — four call sites, no Core
equivalent — deliberately left for a later round rather than folded in,
consistent with [[feedback_stage_files_by_scope_not_by_dirty_tree]]'s
broader "don't widen scope mid-round" pattern.

A second advisor pass on the draft spec (before it was finalized) caught a
real wrong-answer bug — an unguarded empty query would have matched every
non-null `company_name` and returned the table's first row instead of no
match — and an overstated claim: `find_subcontractor()` alone does NOT make
a real JS cutover possible. Every JS consumer of the returned record reads
local-JSON field names/types (`last_contact` vs Core's `last_contact_at`,
`subcontractor_id` vs Core's `external_id`/numeric `id`, JS booleans vs
Core's int 0/1) with no documented reverse mapping — logged as NEW-245,
since NEW-235 only covers the forward (extraction-schema → Core) direction.
Both fixes were applied to the spec before handoff, and the master plan's
wording was corrected per rule 6 rather than left standing.

**How to apply, specifically:** always run a second advisor pass on a spec
BEFORE calling it done, even after the first pass already validated the
overall approach — the first pass catches wrong-approach risk, a second
pass on the actual written spec text catches wrong-answer bugs and
overstated claims in your own summary of what the spec achieves.

NEW-241/242/243/244/245 all logged. `~/Codey-Aigentik` untouched this round.
