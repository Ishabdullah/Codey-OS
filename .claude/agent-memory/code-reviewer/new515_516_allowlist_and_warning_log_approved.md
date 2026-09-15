---
name: new515-516-allowlist-and-warning-log-approved
description: NEW-515 (subcontractors/upsert + schedule-config allow-list) and NEW-516 (concurrency-cap skip warning log) — both approved
metadata:
  type: project
---

2026-09-15: Two small independent fixes closing NEW-515 and NEW-516, reviewed
and approved. Full suite 670 passed, 0 failed (`python -m pytest
tests/test_restoricon_core/ -q`); the 5 touched test files alone: 48 passed.

- NEW-515 (`restoricon_core/api/routes.py`): copied [[new501_506_510_511_513_batch_approved]]'s
  NEW-511 allow-list pattern (`{f.name for f in dataclasses.fields(X)}`,
  400 on unknown keys) to `POST /api/v1/subcontractors/upsert` and
  `POST /api/v1/schedule-config`. Verified both `Subcontractor` and
  `ScheduleConfig` are genuine `@dataclass`es (models.py lines 623, 768),
  `dataclasses` import is top-level in routes.py (line 6, pre-existing from
  the NEW-511 round), and the allow-list check is placed before the
  constructor call on both routes (confirmed via diff hunk order, not just
  claimed). New tests use `router.handle_request(...)` — the real route
  path, not mocked.

- NEW-516 (`restoricon_core/services/scheduling_service.py`): added a
  `logging.getLogger(__name__).warning(...)` call inside the existing
  `except ValueError: continue` in `_assert_within_concurrency_cap`, purely
  instrumentation — `continue` still fires last, no control-flow change.
  Confirmed the file's own convention really is inline `import logging`
  inside function bodies (4 pre-existing sites at lines 986/1167/1194/1252,
  not just this new one) — so this isn't an invented pattern.

- Verified a genuinely serious out-of-scope claim the implementer flagged
  but did NOT fix (different repo, correctly deferred): read
  `Codey-Aigentik/subcontractor-recruiter.js`'s `mapJSToCore()` /
  `createOrUpdateSubcontractorLead()` directly. `mapJSToCore` does
  `{...jsObj}` then *adds* `external_id`/`last_contact_at` without deleting
  the original `subcontractor_id`/`last_contact` keys — so the upsert
  caller really does send both old and new key names on every real call,
  meaning `POST /api/v1/subcontractors/upsert` was 500ing in production
  before this fix, and now cleanly 400s. This confirms NEW-515's original
  ledger "Impact: low today" line needs a rule-6 correction for the
  `/subcontractors/upsert` half specifically (not the `/schedule-config`
  half — traced `web_surfaces.py`'s `saveScheduleConfig()` JS and confirmed
  every key it POSTs is a real `ScheduleConfig` field, so that half's
  "no known caller sends unexpected keys" claim still holds).

Lesson: when an implementer flags an out-of-scope caller-side bug found
while verifying safety of an allow-list/validation change, it's cheap and
worthwhile to actually read the caller (even in a sibling repo) rather than
taking the claim on faith — in this case reading ~15 lines of JS was enough
to confirm a real production-impacting claim before it goes into the ledger
as fact.
