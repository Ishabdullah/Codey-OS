---
name: new501_506_510_511_513_batch_approved
description: Five-item round (NEW-501/506/510/511/513) closing subcontractor-delete guard relocation, POST allow-list, audit-log XSS, mixed-timestamp mutation test, and Aigentik calendar-invite arg-transposition fix — approved
metadata:
  type: project
---

Round reviewed 2026-09-15, all five items APPROVED (665 tests pass; verified live, not paraphrased).

- **NEW-510** (rule-4 destructive-delete/RBAC-ordering item): active-reference
  guard for subcontractor delete moved from `routes.py`'s `/delete` handler
  into `CRMService.delete_subcontractor()` itself. Permission check is
  genuinely first line inside the method (verified by reading, not by
  trusting the comment). `CRMService.__init__` gained lazy-default
  `scheduling_service`/`operations_service` params
  (`self.scheduling = scheduling_service or SchedulingService(self.db, audit_service)`).
  Verified: (a) no call site anywhere in the repo passes >3 positional args
  to `CRMService(...)`, so the new params are safe; (b) the lazy fallback
  shares `self.db` — same `DatabaseManager`, not a second in-memory DB — a
  new test asserts `crm.scheduling.db is db`; (c) `SchedulingService.__init__`
  and `OperationsService.__init__` are inert (attribute assignment only, no
  side effects), so building extra instances per `CRMService(...)` call
  (30+ fixtures, `server.py`, `migrate_aigentik.py`) is harmless; (d) all 16
  pre-existing tests in `test_new507_subcontractor_delete.py` are byte-for-byte
  unmodified (grep-diffed), only new tests appended.

- **NEW-513** (XSS-class): `loadAuditLogs()` was reading a nonexistent
  `data.entries` key (permanently-false guard, dead code) with unescaped
  interpolation. Fixed to read the real `data.audit_logs` / `timestamp` /
  `change_summary` / `actor_id` fields (confirmed against `AuditRecord`
  dataclass and the route's actual response shape), every field wrapped in
  `escapeHtml()`. `web_surfaces.py` has 3 separate `escapeHtml` function
  declarations across different `<script>` blocks in the same returned HTML
  string — in a browser, function declarations in different `<script>` tags
  on one page share the same global scope, so whichever runs last in
  document order wins at call time (not necessarily a bug, but don't assume
  the nearest-above one is "the" definition in scope — check what code
  actually executes at click-time). All 3 variants in this file are
  null-safe (`(unsafe || '').toString()` or `if (!unsafe) return ''`), so it
  didn't matter here, but this is a wrinkle worth checking again if a future
  `escapeHtml` gets added without matching that null-safety.

- **NEW-501** (test-only, mutation test for `_assert_within_concurrency_cap`
  mixed-timestamp handling): verified non-vacuous via negative control —
  don't just confirm `_parse_iso` is called, prove the specific edge-case
  row actually changes the outcome. Method used: copy the test, drop one
  row (the `-05:00` non-UTC-offset row), assert the create now succeeds
  instead of raising. It did — confirms the loop counts all rows before the
  `count >= max_concurrent` check fires (checked after the full loop, not
  inside it, so no early-exit vacuity risk either). This is the same
  negative-control technique as `new481_textnode_escaping_second_half_approved.md`
  — reusable pattern: "read that the assertion would fail without this
  exact row/format/field" beats "confirm the code path exists."

- **NEW-506/514**: Aigentik `http-server.js`'s `/send-invite` had
  `sendCalendarInvite(data.to, data.appointment, data.text)` transposed
  against the real signature in `email-provider.js`
  (`sendCalendarInvite(appointment, toEmail, bodyText)`) — fixed, and the
  new `/send-cancellation` route was written with correct argument order
  from the start (verified directly against `email-provider.js`, not
  copied from the pre-fix pattern). `delete_staff_schedule()`'s new
  pre-DELETE `SELECT` correctly preserves the NEW-491 no-op contract
  (`False`/no audit row) via both the pre-SELECT `if not row: return False`
  and the existing `rowcount == 0` fallback for the TOCTOU window.

**Process note, not a code bug:** NEW_ISSUES.md entries in this round say
"see PROJECT_LOG" for a round PROJECT_LOG.md doesn't mention yet (only
NEW_ISSUES.md was in the diff, not PROJECT_LOG.md/CODEY_MASTER_PLAN.md).
Expected at review time per the hub-and-spoke workflow (ledger updates are
coordinator step 5, after code-reviewer approval) — flagged as a
non-blocking Warning so the coordinator doesn't forget to close the loop
in the same commit, not as a defect in this round's diff.
