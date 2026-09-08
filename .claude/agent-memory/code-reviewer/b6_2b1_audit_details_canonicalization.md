---
name: b6-2b1-audit-details-canonicalization
description: B6.2b-1 — 25 mechanical create/delete service-layer audit sites onto build_audit_details envelope + 4 NEW-314 frozenset allow-lists. APPROVED (full suite 288 green).
metadata:
  type: project
---

B6.2b-1 (2026-09-02): 4 `_AUDITABLE_<ENTITY>_FIELDS` frozensets in audit_service.py
(contract/invoice/subcontractor/employee, NEW-314); 21 creates `details=X.to_dict()`
→ `build_audit_details(after=X.to_dict())`; 4 sensitive creates also `fields=`;
delete_contact/delete_rule → `snapshot=`; remove_from_do_not_contact → snapshot;
record_transaction → `side_effects` when project actual_cost UPDATE ran.

**APPROVED.** Code is safe and correct. New file 28 pass; full
`tests/test_restoricon_core/` 288 passed (B6.2a baseline 259 + 28 new + prior
intervening; zero regressions — no pre-existing test asserted `details == X.to_dict()`).
Negative control reproduced — breaking subcontractor `fields=` leaks
"gl-secret"/"wc-secret" and fails the leak sweep.

Non-blocking items for the coordinator (ledger = pipeline step 5):

1. **Cross-round `create` shape (NOT blocking — pre-flagged by coordinator item 7).** B6.2a (committed, routes.py:275)
   emits `user_created` as `build_audit_details(snapshot=user.to_dict())`. B6.2b emits
   entity creates as `after=`-only → `changed_fields` full of `{old:None,new:v}`.
   Same semantic op (create), two shapes, permanent in the append-only audit_log,
   and B6.2c's diff reader must handle both. Worth an architect note for B6.2c, but
   the helper supports `after`-only by construction (`before: Optional=None`, guard
   `if before is not None or after is not None`) — not a misuse. The wrinkle that
   forced it: `snapshot=` is UNFILTERED, so routing the 4 sensitive creates through
   snapshot would reintroduce customer_signature_data/payments/license_number/
   hourly_rate leaks — `after`+`fields=` is the only current filtered-create path.
   The implementer's choice was motivated and safe.

2. **`add_to_do_not_contact` (automation_service.py:384, `action="create"`, the 23rd
   create site) left uncanonicalized** while its sibling `remove_from_do_not_contact`
   was done (item 6). Defensible — it's an `ON CONFLICT DO UPDATE` upsert like the two singletons
   (business_profile:313, schedule_config:425) deferred to B6.2b-4 — but must be
   explicitly noted / NEW_ISSUES'd, not silently skipped (rule 8). Explains the spec's
   "26 headline vs 25 body" gap.

**Warnings / Suggestions (not blocking) — "what's sensitive" inconsistency:**
- `delete_contact` passes full unfiltered `Contact.to_dict()` snapshot incl.
  `license_number`, which `create_subcontractor` allow-list-excludes. Contact has no
  true credential (gl/wc_insurance are 0/1 flags) so not a leak.
- `create_compliance_item` passes `ComplianceItem.license_number` + `issuer` freely
  (test docstring calls this deliberate).
- `record_transaction` passes `FinancialTransaction.reference_number` +
  `payment_method` unfiltered — `reference_number` is the most plausible NEW-314
  omission. NEW-314 only scoped 4 entities; none of these three were in it.

**Verified sound:** all 4 allow-lists checked field-by-field against models.py —
names all real, sensitive fields (signature/content/payments/license_number/
general_liability/workers_comp/references/qualification_data/hourly_rate/
emergency_contact) all excluded; subcontractor list is exactly 48 model fields − 5.
`fields=` semantics: domain = the frozenset, `if not in_b and not in_a: continue`
skips allow-listed keys absent from the dict, never emits a non-allow-list key.
delete_rule: SELECT added inside `with conn:` before DELETE is a harmless read;
`if row else None` dead-safe (deleted True ⇒ row found); not-found path unchanged.
record_transaction: `cost_applied` set exactly where the conditional UPDATE runs;
`txn.amount` in side_effects is the literal value passed to the UPDATE. All 7 other
remaining raw `details=X.to_dict()` sites in services/ are `action="update"` /
`work_order_dispatch` — correctly out of scope.
