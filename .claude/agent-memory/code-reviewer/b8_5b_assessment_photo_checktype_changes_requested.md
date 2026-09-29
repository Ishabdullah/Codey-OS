---
name: b8_5b_assessment_photo_checktype_changes_requested
description: B8.5b assessment-records UI sends document_type='assessment_photo', which is not in documents' CHECK constraint allow-list -- every photo upload 500s. CHANGES REQUESTED.
metadata:
  type: project
---

2026-09-17, B8.5b round (appointment scheduling UI + assessment_records
table/workflow, uncommitted at review time). New table, service, routes,
and sales-portal UI all reviewed clean on their own: parameterized SQL,
consistent `escapeHtml`, permission gate matches Property-CRUD precedent,
`AssessmentRecord(**json_body)`/`Appointment(**json_body)` field names
verified against real dataclasses, `node --check` passed on the real
rendered `<script>` block, full suite `2153 passed, 1 skipped` reproduced
verbatim.

**Real bug found by live-reproducing the multipart claim, not by reading
the diff harder.** The implementer's own NEW-571 claim (multipart `file`
field must be appended last in `FormData` or the server falls back to
`uploads/general/`) was independently live-verified TRUE by directly
driving `router.handle_request` with a `MockRFile` in both field orders
— confirmed via storage path (`.../photos/general/...` vs
`.../uploads/general/...`).

But building that same live harness surfaced an *undisclosed* second bug
in the same code path: `handleAssessmentPhotoUpload` in
`web_surfaces.py`'s `_render_sales_portal()` sends
`formData.append('document_type', 'assessment_photo')`. `documents`'
DDL (`database.py`) has
`CHECK(document_type IN ('contract', 'estimate', 'proposal', 'invoice',
'receipt', 'insurance', 'permit', 'photo', 'pdf', 'upload',
'warranty'))` — `'assessment_photo'` isn't in that list. Every real photo
upload from the new assessment form throws `CHECK constraint failed` as
a 500. Reproduced live with the same `MockRFile` harness
(`tests/test_restoricon_core/test_b6_5_document_upload.py`'s pattern).
`tests/test_restoricon_core/test_b8_5b_assessment_records.py` has zero
references to `multipart`/`document_type`/`assessment_photo` — the photo
upload path was never exercised by any test in this round, string-only
or live.

**Lesson: when asked to live-verify one specific multipart/DB-shape
claim, build the harness broad enough to actually hit the DB write path
end-to-end (not just assert on parser internals) — the CHECK constraint
violation was a free byproduct of doing the field-order repro properly,
and would have been invisible to a narrower "does on_headers_finished
see populated metadata" unit check.** With `customer_id` included (the
real UI always sends it), the fixed order lands at
`photos/customers/<id>/...` and the broken order falls all the way back
to `uploads/general/...` -- losing both the type directory AND the
customer scoping, not just the type directory as a bare repro without
customer_id would suggest.

**Fix recommendation, not "either/or":** do NOT widen the CHECK
constraint -- SQLite CHECK constraints require a full table rebuild
(create-new/copy-rows/drop/rename) on a table that may already hold
production `documents` rows, expensive and out of scope for what should
be a one-line JS fix. Reuse `document_type='photo'` and add an
`assessment` tag instead -- the exact same route already does
`tags.append(f"subcontractor_id:{{subcontractor_id}}")` for the
identical purpose (distinguishing sub-scoped uploads without a new enum
value), so this is in-pattern, zero-migration, and mirrors existing
code the implementer already read.

**New-table migration path verified separately, not a blocker:**
`DatabaseManager.__init__` runs `conn.executescript(_SCHEMA_SQL)`
unconditionally on every open (no versioned migration gate for base
DDL), and `CREATE TABLE IF NOT EXISTS`/`CREATE INDEX IF NOT EXISTS` make
that idempotent. Live-confirmed by pointing `DatabaseManager` at a copy
of the real on-disk `~/.codeyOS/restoricon.db` (never the original) --
`assessment_records` and both new indexes appeared in `sqlite_master`
with no migration step needed. Don't skip this check on future
new-table rounds just because `:memory:`-backed tests pass; `:memory:`
always gets a fresh full schema and proves nothing about an existing
on-disk DB.

See also [[b8_4b_project_property_id_approved]] (same B8.x round family)
and [[sandbox_proxy_test_artifact]] (unrelated env gotcha, unset proxy
vars before trusting pytest counts here too).
