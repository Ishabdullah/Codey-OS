---
name: restoricon_core_phase_b2_task4_find_subcontractor_new246_approved
description: find_subcontractor() read-only lookup + route, deliberate JS null-phone bug mirroring pinned as NEW-246 — approved
metadata:
  type: project
---

Phase B2 task 4, third module continuation (`CRMService.find_subcontractor()`
+ `GET /api/v1/subcontractors?q=`, 2026-08-27, `CODEY_MASTER_PLAN.md` §6.4) —
reviewed and approved. Read-only, not yet wired to any JS call site.

**Why this one required extra scrutiny:** implementer deliberately
reproduced a real bug in `~/Codey-Aigentik/subcontractor-recruiter.js:213-216`
rather than fixing it, per the spec's own explicit instruction (§6.4 was
authored with this decision already made, citing `NEW-235` precedent —
this was not the implementer inventing the call mid-task).

**Bug mechanics, verified directly against the JS source (not the
implementer's characterization):** `subcontractor-recruiter.js:215`:
`if (pDigits.includes(cleanDigits) || cleanDigits.includes(pDigits))
return true;`. When a record has no phone, `pDigits === ''`, and
`cleanDigits.includes('')` is always `true` in JS (empty string is a
substring of everything) — so `cleanDigits.includes(pDigits)` is the
always-true branch, not `pDigits.includes(cleanDigits)`. Core's
`crm_service.py`: `if clean_digits in p_digits or p_digits in
clean_digits:` — same OR order, same direction (`p_digits in
clean_digits` is Python's mirror of `cleanDigits.includes(pDigits)`).
Confirmed exact match, not a look-alike bug.

**Verified myself, not taken on the implementer's word:**
- Empty-query guard (`if not query or not query.strip(): return None`)
  is genuinely load-bearing — removed it, 2 tests failed exactly as
  claimed, restored.
- `ORDER BY id ASC` (vs every sibling method's `DESC`) is genuinely
  load-bearing — flipped it, `test_find_subcontractor_returns_lowest_id_when_multiple_rows_match`
  failed exactly as claimed, restored.
- NEW-246's pinning test is genuinely load-bearing — patched in the
  "fix" (`if p_digits and (...)`), the test failed exactly as claimed,
  restored.
- `python -m pytest tests/ -q` → `811 passed, 1 skipped` — matches
  implementer's claim verbatim, ran it myself.
- No new permission constant invented (`PERM_READ_SUBCONTRACTORS`,
  same as `get_subcontractor`/`list_subcontractors`).
- Route's `q`-branch and list-fallback are mutually exclusive, correct
  priority order, blank/whitespace `q` falls through as spec'd.
- Zero touches to `~/Codey-Aigentik` or `~/Aigentik-CLI` (confirmed via
  `git status`/`git diff --stat` in both those repos).
- `install.sh` correctly untouched — stdlib `re` only.

**My own verdict on the mirror-vs-fix judgment call:** approved as a
reasonable engineering decision, not an escalation-worthy one, because
(a) the method is read-only and explicitly not yet wired to any live
JS call site — no production SMS-misdirection risk exists yet from
this round's change alone; (b) the decision was already made at the
scoping/spec-writing layer (`CODEY_MASTER_PLAN.md` §6.4), not
improvised by the implementer mid-task; (c) it's tightly pinned by a
named regression test and a `NEW_ISSUES.md` entry that explicitly
requires a *joint* Core+JS fix before it can be silently "improved".
Flagged as a Suggestion, not a blocker: whoever actually wires this
method to a live JS call site later must treat NEW-246 as a
must-fix-first item given the described consequence (misdirecting
inbound SMS recruiting conversations to the wrong subcontractor's PII).

See also [[git_checkout_path_wipes_uncommitted_diff]] — near-miss during
this review's own negative-control testing, not a finding against the
implementer's diff.
