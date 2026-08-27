---
name: restoricon_core_phase_b2_schema_expansion_new212_inaccuracy
description: Phase B2 Restoricon Core schema expansion (subcontractors/appointments/automation_rules/business_profile/do_not_contact) round 1 review — CHANGES REQUESTED on a ledger factual-accuracy defect, not a code bug
metadata:
  type: project
---

Round 1 review of Track B / Phase B2 (`restoricon_core/database.py`,
`models.py`, `auth.py`, `crm_service.py` extension, new
`scheduling_service.py`/`automation_service.py`), CODEY_MASTER_PLAN.md
§6.4. Verdict: **CHANGES REQUESTED**, blocking on one ledger defect.

**What was clean (all independently verified, not just claimed):**
- All 14 new/extended service methods gate on `has_permission()` with
  the correct read/write constant, before any DB touch — checked every
  one by hand, not just the passing `ZeroPermissionActor` tests.
- `business_profile` singleton: `id INTEGER PRIMARY KEY CHECK(id = 1)` +
  `INSERT ... ON CONFLICT(id) DO UPDATE` genuinely prevents a second row
  (proved via the test's own `COUNT(*)` assertion, re-read by hand).
- `do_not_contact` UNIQUE(type,value) + normalize-before-insert +
  `ON CONFLICT DO UPDATE` is genuinely idempotent.
- **Read the actual `~/Aigentik-CLI/do-not-contact.js` source (not just
  trusted the docstrings) to check the "byte-for-byte equivalent"
  normalization claim** — it holds. `normalizePhone`/`normalizeEmail`/
  `classifyIdentifier` are identical logic (including the zero-validation
  "any string with '@' is an email" behavior — a pre-existing JS
  characteristic, not a Python-invented gap). Even the asymmetric upsert
  (name preserved via COALESCE-if-omitted, reason/source/added_at always
  overwritten-with-default) exactly mirrors the JS's
  `name || existing.name || null` vs `reason || 'requested removal'`
  (always applied) semantics. This was the check most likely to surface
  a real Critical and it came back clean — but it required reading the
  external artifact directly, not just the imitating code's own comments.
- SQL injection: all three service files use `?` placeholders throughout,
  including the `WHERE 1=1` dynamic-filter builders (params appended
  alongside, never interpolated).
- Audit logging on every mutation except `record_rule_match` (deliberate,
  documented, and tested with its own negative-control test).
- stdlib-only, no install.sh update needed (correctly not touched).
- 37/37 and 753 passed/1 skipped reproduced literally, matching claims.

**The blocking defect:** `NEW_ISSUES.md`'s new `NEW-212` entry states as
fact that "the five NEW-209 tables built this round... each got an
`external_id TEXT UNIQUE` column." False — `business_profile` (a
singleton, doesn't need one) and `do_not_contact` (whose natural
idempotency key is `UNIQUE(type, value)`) have **no `external_id`
column** in the actual DDL. Only `subcontractors`, `appointments`, and
`automation_rules` have it. The absence is defensible design, but the
ledger's factual claim about the diff's own schema is wrong, in the same
diff as the schema — same doc-accuracy class as u31/Phase 4.1 C&D/7.4a F.
Fix: correct NEW-212 to name the three tables that actually have the
column.

**Also required (rule 8, not yet logged):** `is_blocked()` gates on
`PERM_READ_DNC`, but `ROLE_SALES` and `ROLE_PROJECT_MANAGER` — the two
roles holding the pre-existing `PERM_LOG_COMMUNICATION` (i.e. the roles
most plausibly about to contact someone) — were granted no DNC
permissions in this round's matrix additions. Not live-exploitable today
(`is_blocked()` has no caller yet; `restoricon_core/api/` untouched, so
none of these services are HTTP-reachable), same "one caller away" shape
as `NEW-189`/`NEW-194`. Needs its own `NEW-21x` ledger entry before this
round can be considered fully logged per rule 8.

**Non-blocking, flagged not fixed:**
- `update_subcontractor_qualification()`/`update_appointment_status()`
  both re-fetch via `get_*()` at the end, which re-checks the READ
  permission — a role with WRITE but not READ would have its write
  silently "succeed" then throw PermissionError on the return value. No
  role in the current matrix has this shape (WRITE always co-occurs with
  READ for these five constants), so latent only, same shape as prior
  "one matrix edit away" findings this project has repeatedly logged as
  non-blocking.
- `add_to_do_not_contact()` returns `None` silently when
  `classify_identifier()` fails to parse, unlike `create_appointment`/
  `create_rule` which raise `ValueError` on bad input — inconsistent on
  a safety-relevant (DAY-ONE-OR-NEVER) path.
- `subcontractors.qualification_status` has no CHECK constraint (unlike
  `appointments.status`/`automation_rules.channel`), so arbitrary strings
  can land in the pipeline field via `update_subcontractor_qualification`.

**Technique reinforced:** when a docstring/DDL comment claims
byte-for-byte equivalence to an external artifact (a sibling JS file in
this case), locate and read that file directly before accepting the
claim — grep-checking only the Python side (as I did on the first pass)
is not sufficient; the advisor call is what caught this gap. This is
rule 12's "read the artifact itself" applied to a cross-language
port, not just a model/API spec.
