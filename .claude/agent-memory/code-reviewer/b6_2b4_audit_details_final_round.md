---
name: b6-2b4-audit-details-final-round
description: B6.2b-4 (FINAL round) — last 11 service-layer audit.log sites onto build_audit_details. APPROVED (380 green). Closes the B6.2b sub-series.
metadata:
  type: project
---

B6.2b-4 (2026-09-03): last 11 `audit.log` sites (scheduling 3 / automation 2 /
business_ops 2 / crm 4) → `build_audit_details`. +4 NEW-314 frozensets
(CONTACT excludes `license_number`+`references`; APPOINTMENT / REVIEW_REQUEST /
PURCHASE_ORDER exclude nothing — drift guards).

**APPROVED.** `tests/test_restoricon_core/` 380 passed (+22 new), `test_business_ops.py`
9 passed. Zero regressions. No other test asserted the old details shapes
(grepped old_rating/lead_id/android/appointment_id — only b6_2a hits, untouched).

Verified sound:
- Frozensets checked live vs `<Model>().to_dict()` keys: contact diff is
  EXACTLY `to_dict - {license_number, references}`; appt/review/po are exact
  equality. ScheduleConfig/BusinessProfile carry no credentials/PII (verified
  key dump) → `snapshot=` verbatim pass-through is safe for 3.3/3.4.
- NEW-312 remedy correct at 3.2 (update_appointment) and 3.8 (update_contact):
  `_before` strictly above first mutation (right after `if not row`); `_after`
  from a post-commit RAW re-read through the SAME `_row_to_*` staticmethod as
  `_before` (both actor-less → no redaction → symmetric); `_after` Optional-
  guarded (`... if _after_row else None`); `audit.log` fires BEFORE the
  return-path `get_*()` getter. `_ConnProxy` tests force the 2nd SELECT empty
  (drop_on_hit=2 lands on the after re-read; UPDATE has no "FROM" so isn't
  counted) and assert `{"old": <v>, "new": None}`.
- NEW-311 compliance: 3.1 adds no read (snapshot from input param only, does
  NOT widen its history_json-only pre-read); 3.3/3.4/3.11 add no reads; 3.7
  `_after` is a `{**dict(row), ...}` mirror of the SET clause, no new SELECT;
  3.2/3.8 re-read the row THIS method just wrote (spec-allowed).
- `action=`/`change_summary=` byte-identical at all 11 (dedicated persisted-value
  test). submit_review's pair only moves position (hoist), unchanged.
- side_effects rule-4: 3.9/3.11 ids+counts only; 3.10 ids + `score` result.
- Negative control reproduced: dropping `fields=_AUDITABLE_CONTACT_FIELDS` leaks
  license_number + references into changed_fields.

**Non-blocking — need NEW_ISSUES lines (rule 8), all implementer-flagged:**
1. `add_to_do_not_contact` None-path payload drop: `after=entry.to_dict() if
   entry else None` → on the (unreachable-after-committed-upsert) `entry is
   None` path, `build_audit_details(after=None)` returns `{}`, dropping the
   old `{reason, source}`. Normal path now captures MORE (reason/source are
   dnc columns in `entry.to_dict()`). Latent only.
2. No `_row_to_review_request` builder — `submit_review` (now ×2: `_before` +
   `result`), `list_reviews`, `create_review_request` hand-construct
   `ReviewRequest(...)` from a row. Refactor candidate, not a defect.
3. 3.10 `submit_public_lead` side_effects carries `score` (a nested dict, not
   an id/flag) — pre-existing (old code had it), it's the lead's own scoring
   metadata not a child-entity dict, JSON-serializable. Minor spec deviation.

This closes the B6.2b service-layer audit-canonicalization sub-series
(b1: 25 mechanical, b2: 11 crm updates, b3: 8 operations updates, b4: final 11).
See [[b6-2b3-audit-details-operations-update-sites]], [[b6-2b2-audit-details-crm-update-sites]], [[b6-2b1-audit-details-canonicalization]].
