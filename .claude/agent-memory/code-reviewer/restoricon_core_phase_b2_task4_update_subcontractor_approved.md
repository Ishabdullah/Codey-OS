---
name: restoricon_core_phase_b2_task4_update_subcontractor_approved
description: Phase B2 task 4 third module — CRMService.update_subcontractor() + POST .../update route — approved, 3 non-blocking findings (1 confirmed real bug to log)
metadata:
  type: project
---

Reviewed 2026-08-27: `restoricon_core/services/crm_service.py` (new
`update_subcontractor()` + `ALLOWED_UPDATE_FIELDS`), `restoricon_core/api/routes.py`
(new `POST /api/v1/subcontractors/{id}/update`), new tests in
`test_operations_services.py`/`test_api.py`. CODEY_MASTER_PLAN.md §6.4
"Task 4, third module." **Approved.**

Verified directly, not from implementer's summary (live Python probes run
against a real `:memory:` DB, not just reading the code):
- Allow-list is genuinely hardcoded (`ALLOWED_UPDATE_FIELDS` a class-level
  set) and the `unknown = set(updates) - ALLOWED_UPDATE_FIELDS` rejection
  happens *before* any key is ever used to build SQL — live-probed with a
  malicious key literally shaped like a SQL fragment
  (`"company_name = ?, id"`) and it was rejected as an unknown field,
  never reached the `f"{key} = ?"` string-building line.
- RBAC gate (`PERM_WRITE_SUBCONTRACTORS`) is the first statement in the
  method, before any DB touch. `get_subcontractor()` (used both for the
  empty-updates no-op and the final return) gates on
  `PERM_READ_SUBCONTRACTORS` — confirmed by reading it directly. No role
  in `auth.py`'s current matrix has WRITE-without-READ for subcontractors
  (checked all 6 roles by hand: admin/manager/PM/ai_agent have both,
  sales has read-only, technician has neither) — so the
  write-succeeds-then-throws-on-return shape from
  [[restoricon_core_phase_b2_schema_expansion_new212_inaccuracy]] is
  reproduced in this new method too but still not live-exploitable today.
- Genuine shallow-merge for `qualification_data` and genuine
  replace-not-merge for `secondary_trades` — live-probed both directly
  (merge preserved an untouched key, added a new key, and overwrote a
  shared key in one call; replace produced exactly the new list with the
  old item gone), not just trusted the passing unit test.
- `None`-valued key vs unknown-key tests are genuinely distinct code
  paths (different keys: an allow-listed key with `None` value vs a
  wholly unknown key name) — read both test bodies directly.
- Audit log test actually asserts `change_summary` content
  (`"qualification_data" in logs[0].change_summary`), not just row count.
- Empty-dict no-op returns before ever calling `self.db.get_connection()`
  — zero DB touch, matching spec exactly.
- `updated_at`/`last_contact_at` both set from one shared `now =
  utc_now_iso()` call, not two separate `datetime.now()` calls.
- SELECT (for the merge read) and UPDATE both inside the same `with
  conn:` block — no split-transaction TOCTOU on the merge.
- Route placed exactly where spec said (after `.../qualification` POST,
  before generic by-id GET); `endswith("/qualification")` vs
  `endswith("/update")` are mutually exclusive, no accidental overlap.
- Zero touches to `~/Codey-Aigentik`/`~/Aigentik-CLI` (checked directly).
- `install.sh`: correctly untouched (stdlib only).
- Test suite: `789 passed, 1 skipped` reproduced literally, matches
  implementer's claim exactly.

**Confirmed real, non-blocking bug (worth a NEW_ISSUES.md entry):**
`update_subcontractor({"email": ""})` writes the literal empty string
`""` into the `email` column (live-verified: raw `SELECT email` on the
row after the update returned `''`), whereas `create_subcontractor`
writes `NULL` for a falsy email
(`sub.email.strip().lower() if sub.email else None`) — but only for the
*database row*; the object `create_subcontractor` returns to its caller
is the original in-memory `sub` unmodified (its own pre-existing,
unrelated quirk — `create_subcontractor` never re-fetches after INSERT,
so `sub.email` in the return value still holds whatever the caller
passed, while the DB row itself does get `NULL`). Net effect: two
distinct falsy-email representations end up in the `email` column
depending on which path wrote the row (`NULL` via create, `''` via
update) — genuine, if minor, data-hygiene inconsistency. Small
single-call-site fix available (normalize `updates["email"]` to `None`
if falsy, mirroring create's ternary) but that would then need to skip
the pre-check None-rejection loop (which only fires on caller-supplied
`None`, not internally-derived `None`) — not entirely trivial to wire in
without restructuring the two loops slightly. Recommend logging as a new
`NEW-23x` entry rather than blocking commit on it.

**Non-blocking Suggestions:**
- `qualification_data`/`secondary_trades` values aren't type-checked
  before use — live-probed `{"qualification_data": ["not", "a", "dict"]}`
  and got an unhandled `TypeError: 'list' object is not a mapping`,
  which routes.py's existing generic `except Exception` handler turns
  into a 500 with the raw exception string leaked in the body. Not a new
  pattern — matches the already-accepted `NEW-221`
  (`Model(**json_body)` TypeError->500) and the Phase B1 review's
  already-flagged "generic 500 handler leaks raw exception text"
  precedent — just a new instance of the same pre-existing shape, not a
  fresh defect this diff introduced.
- The WRITE-without-READ latent gap above has now recurred identically
  three times (`update_subcontractor_qualification`,
  `update_appointment_status`, now `update_subcontractor`) across two
  review rounds without ever getting its own `NEW_ISSUES.md` line — the
  schema-expansion round's review flagged it as "needs its own NEW-21x
  entry" but it still isn't in the ledger. Worth actually filing this
  time so the pattern stops recurring un-logged (rule 8).

**Technique reinforced:** don't just read a merge/replace implementation
and trust the passing test — construct a live probe (real `:memory:` DB,
real service call) that sends a genuinely adversarial value (a SQL-shaped
unknown key, a wrong-typed JSON-column value) and watch what actually
happens, the same way [[restoricon_core_phase_b2_task2_migrate_aigentik_approved]]'s
negative-control technique works for idempotency claims.
