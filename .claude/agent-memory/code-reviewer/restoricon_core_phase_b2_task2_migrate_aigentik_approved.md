---
name: restoricon-core-phase-b2-task2-migrate-aigentik-approved
description: Phase B2 task 2 (migrate_aigentik.py + 3 RBAC lookup methods) code review — approved, one doc-accuracy Warning on NEW-218
metadata:
  type: project
---

Reviewed 2026-08-27: `restoricon_core/migrate_aigentik.py` (new),
`tests/test_restoricon_core/test_migrate_aigentik.py` (new, 10 tests),
+3 new `get_*_by_external_id` RBAC lookup methods (crm_service.py,
scheduling_service.py, automation_service.py). **Approved.**

Verified directly (not from implementer's summary):
- All 3 new lookup methods gate on `has_permission()` before the query,
  same pattern as sibling methods in the same files — no NEW-189-style
  unguarded lookup.
- Hand-constructed `AuthContext(role="ai_agent", user_id=None, ...)` is
  not reachable from any API/CLI route or import-time side effect —
  grepped the whole repo, only referenced from the script itself, its
  own test, and comments in the 3 service files.
- Dry-run boundary: every write call (`create_subcontractor`,
  `create_appointment`, `create_rule`, `upsert_business_profile`) sits
  behind `if apply:` in `_migrate_list_file`/`_migrate_profile_file` —
  traced all 4, no flag-threading gap.
- Idempotency: lookup-by-external_id happens *before* create in the
  driver loop, correct table/column in each new lookup method. Ran a
  **negative control** — patched `existing = lookup_fn(...)` down to
  `existing = None` to fake a broken lookup — and
  `test_idempotent_rerun_no_duplicates` failed with
  `sqlite3.IntegrityError` as expected, confirming the test actually
  exercises the invariant it claims to (this project's recurring
  "test passes but doesn't test the thing" trap). Restored the file by
  hand afterward since it's untracked (`git checkout` no-ops on new
  files — must restore from the Read tool's captured content or a
  literal copy).
- Torn-read guard (`_read_json_stable`) genuinely re-reads and compares
  two parses for equality (not just re-reading and assuming stability),
  has a bounded `max_retries` (default 3) with backoff, and raises with
  a clear message on exhaustion rather than silently returning "absent"
  or "0 records."
- CHECK-constraint domain lists in the script (`VALID_APPT_STATUSES`,
  `VALID_APPT_TYPES`, `VALID_CHANNELS`) matched byte-for-byte against
  the live `CHECK(...)` constraints in `database.py` — not just
  plausible-looking, actually identical sets.
- 10/10 new tests + 48/48 full `tests/test_restoricon_core/` suite
  passed, pasted verbatim output.

**Warning found (not blocking): NEW-218 mischaracterizes its own
mechanism.** NEW-218 says `create_subcontractor`/`create_appointment`/
`create_rule` "discard any caller-supplied value" for created_at, and
cites `email-rules.json`'s real `2026-02-22...` timestamp as an example
of a value that gets clobbered. But `map_subcontractor`/
`map_appointment`/`map_rule` in `migrate_aigentik.py` **never read
`rec.get("created_at")` at all** — grepped the whole file, zero
occurrences outside the docstring/comments. The dataclass passed to
`create_*` never has a caller-supplied created_at in the first place
(it gets `Subcontractor.__init__`'s own `default_factory=utc_now_iso()`
at mapping time, then a *second*, later `utc_now_iso()` at insert time
from the service layer). The final effect NEW-218 describes (historical
timestamps lost) is correct, but the mechanism is incomplete: it blames
the service layer alone and implies the migration script already tried
to carry the source timestamp through and got overridden. In reality
the migration script's own mappers never attempt this, so NEW-218's
"Suggested direction" (add an optional created_at override to the
`create_*` methods) would be necessary but not sufficient — the mapper
functions would also need updating to actually read the source field.
Flagged back to implementer as a doc-accuracy correction (rule 6), not
a functional bug — no behavior needs to change, the write-up does.

Reusable technique: when a "known limitation" doc cites a *specific
example value* from source data, grep the mapper/adapter code for that
exact field name before accepting the citation — a plausible-sounding
example is not evidence the code path it's illustrating actually
exists.
