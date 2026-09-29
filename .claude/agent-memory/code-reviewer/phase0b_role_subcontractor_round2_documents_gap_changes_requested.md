---
name: phase0b-role-subcontractor-round2-documents-gap-changes-requested
description: Phase 0b/B8.16 ROLE_SUBCONTRACTOR round 2 — C1/C2/false-comment all correctly fixed, but PERM_READ_DOCUMENTS/PERM_WRITE_DOCUMENTS grant has the identical unnarrowed-leak shape as C2 and was missed
metadata:
  type: project
---

Round 2 of [[phase0b_role_subcontractor_changes_requested]]. All three
requested fixes verified genuinely correct: C1 (`update_work_order`'s
`ROLE_SUBCONTRACTOR` branch now rejects `assigned_subcontractor_id`
reassignment before the `UPDATE`, live-reproduced via a real
create-as-A/reassign-to-B/re-read-as-admin test), C2 (`PERM_READ_COMPLIANCE`
removed from the role entirely, not narrowed; `list_compliance_items`
confirmed to still have zero entity narrowing so removal was the only safe
option this round), and the false "logged... see NEW_ISSUES.md" comment
removed and the underlying claim confirmed false by direct inspection of
`get_project`/`list_projects`. `1291 passed` reproduced verbatim (up from
1290). `NEW-668` entry is clean, non-duplicate, and correctly notes the two
non-blocking warnings are left for the coordinator to log separately (not
silently fixed, not silently dropped) — this matches instructions exactly.

Also worth recording as a **discriminator that came back clean**: I first
suspected `accept_work_order`/`complete_work_order`/`verify_work_order`/
`update_work_order_execution_status` might be unguarded write paths that
bypass the new `ROLE_SUBCONTRACTOR` narrowing (none of the four contain
`ROLE_SUBCONTRACTOR` in their own body). They aren't a gap: all four call
`self.get_work_order(work_order_id, actor)` before any write, and
`get_work_order` has the `ROLE_SUBCONTRACTOR` branch that raises
`PermissionError` for a non-owned row. Transitively protected. Don't
re-flag this pattern without re-checking the call graph first — a method's
own body having no role branch doesn't mean it's unguarded if it delegates
its read through an already-narrowed helper.

**But a real, structurally identical gap to C2 was missed**:
`ROLE_SUBCONTRACTOR`'s grant includes `PERM_READ_DOCUMENTS` and
`PERM_WRITE_DOCUMENTS` (justified in the comment as "job photos/paperwork").
`CRMService.get_document`/`list_documents` (`restoricon_core/services/crm_service.py`)
only apply their per-customer narrowing branch `if not
actor.has_permission(PERM_READ_DOCUMENTS)` — since `ROLE_SUBCONTRACTOR` holds
the broad permission (not the narrow `PERM_READ_OWN_DOCUMENTS`), narrowing is
skipped entirely. Confirmed reachable and unmitigated:
- `GET /api/v1/documents` (no filters required) → `list_documents(actor)` →
  every document in the system, any customer_id/project_id.
- `GET /api/v1/documents/{id}` and `GET /api/v1/documents/{id}/download` →
  `get_document(doc_id, actor)` → raw file bytes of any document, no
  ownership check, no admin gate on the route.
- `create_document` has zero role/entity check beyond `PERM_WRITE_DOCUMENTS`
  — a subcontractor can inject a document row under any customer_id/
  project_id, same shape as the already-accepted non-blocking
  `create_work_order` project-membership gap, but here paired with
  unrestricted read.
- Checked whether `doc.permissions`/`permissions_json` acts as a real ACL
  before concluding this was unmitigated — it's written on create and
  round-tripped into the `Document` model on read, but never consulted by
  `get_document`/`list_documents`. Dead metadata, not enforcement.

`ROLE_TECHNICIAN` (an internal employee) also holds these two permissions
unnarrowed at the same call sites — this exact gap pre-dates Phase 0b for
that role. That does NOT rescue `ROLE_SUBCONTRACTOR`: the diff's own new
comment stakes this role's entire design on being an external party with
"a deliberately narrower subset" than `ROLE_TECHNICIAN", and the reviewer
rejected `PERM_READ_COMPLIANCE` on that identical reasoning one round
earlier in this same review. Newly granting an unnarrowed company-wide
document-read/write permission to an external party, in the same diff that
just fixed the identical shape of bug for compliance, is in-scope and
blocking, not a pre-existing-gap log entry.

Recommended framing to the implementer/coordinator: don't prescribe the
fix — it's a product decision (subcontractors plausibly do need to see
their own job's photos/paperwork) whether to (a) build real entity-level
narrowing for `get_document`/`list_documents`/`create_document` keyed off
the subcontractor's own assigned work orders' `project_id` (mirroring
`_actor_owns_work_order_via_subcontractor`'s pattern), or (b) remove
`PERM_READ_DOCUMENTS`/`PERM_WRITE_DOCUMENTS` from the grant this round the
same way `PERM_READ_COMPLIANCE` was removed, deferring the real feature.
Either is acceptable; shipping the current unnarrowed grant is not.

Technique note: when a round's fix pattern is "remove/narrow permission X
because call site Y has no entity narrowing," always re-run the identical
check against every *other* permission the same new role grant just added
— the fix for one instance of the pattern does not imply the round audited
all of them. `advisor()` caught this one after the implementer's own
summary and my first pass both treated C1/C2 as the complete finding set.
