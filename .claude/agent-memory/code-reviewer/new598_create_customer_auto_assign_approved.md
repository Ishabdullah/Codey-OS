---
name: new598_create_customer_auto_assign_approved
description: NEW-598 create_customer auto-assign-to-creator gate (mirrors NEW-568's PERM_READ_TEAM_SALES_DATA) — APPROVED round 1, contingent on two new ledger entries not yet written
metadata:
  type: project
---

Reviewed 2026-09-22. `restoricon_core/services/crm_service.py::create_customer`
gets a 3-line gate: `if not actor.has_permission(PERM_READ_TEAM_SALES_DATA):
customer.assigned_user_id = actor.user_id`, placed right after the
`PERM_WRITE_CUSTOMERS` check. Closes `NEW-598` (guided-flow customer
creation landing unclaimed).

**APPROVED — core logic verified correct by direct read + live traces,
not just diff:**
- Permission choice literally matches `update_customer`'s NEW-568 gate
  (`crm_service.py:439`, same `PERM_READ_TEAM_SALES_DATA` check) — not just
  "similar," confirmed by reading both lines side by side.
- Traced every non-test caller of `create_customer` (4 total, grepped
  fresh, not trusted from implementer's list): `upsert_customer`'s create
  branch (inherits gate correctly); `upsert_customer`'s *update* branch
  (routes through `update_customer`, which has its own NEW-568 gate — no
  bypass, checked this specifically since it's exactly the "write route
  bypasses a read/gate" class this project's NEW-568 round got bitten by);
  `convert_lead_to_opportunity` (rep-actor case now correctly
  auto-assigns, fixing the real commission-attribution motivation);
  `create_lead_from_web_form`/`submit_public_booking` (both build
  `system_actor` with `role=ROLE_ADMIN`, read both constructions directly,
  confirmed identical shape, both unaffected since `ROLE_ADMIN` holds
  `PERM_READ_TEAM_SALES_DATA` by default).
- Route-level trust confirmed: `POST /api/v1/customers` really does
  `Customer(**json_body)` from untrusted input (`routes.py:786`).
- Checked whether `commission_ledger_entries` writes read
  `customer.assigned_user_id` at all — they don't;
  `CommissionService.record_commission` takes an explicit `rep_user_id`
  arg and currently has zero production call sites (B8.7 not yet built,
  only test callers exist today). So the disclosed "admin converting a
  rep's lead still leaves the customer unclaimed" gap has **no live
  bearing on commission correctness today** — worth stating explicitly
  rather than leaving it as an open question for whoever unblocks B8.7.
- That same admin-convert-lead gap is **not a regression**: pre-diff,
  `create_customer` never auto-assigned for any actor tier, so full-tier
  actors are unaffected before and after; only the rep-tier case improved.
  Correct the implementer's framing if it's phrased as "now leaves
  unclaimed" — it always did.
- ROLE_CUSTOMER custom-permissions edge case (a portal actor
  hypothetically granted `PERM_WRITE_CUSTOMERS` without
  `PERM_READ_TEAM_SALES_DATA`) traced and confirmed real but inert today —
  `has_permission` checks `custom_permissions` override before role
  defaults regardless of role, so it's theoretically reachable via admin
  misconfiguration, but no current route/flow grants it. Low severity,
  consistency-only fix (`actor.role != ROLE_CUSTOMER` guard other narrowing
  checks in this file use, missing here).
- Full suite: `2243 passed, 1 skipped`, verified independently (not
  trusted from implementer's unverified-baseline claim) — matches
  2240 (prior verified baseline, [[b8_6d_c_guided_flow_customer_number_approved]])
  + 3 new tests exactly, zero regressions, 335s.
- `install.sh`/`requirements.txt`: zero diff, correct (no new dep).

**Condition, not blocking the code itself**: per this project's own
NEW-568 precedent (round 1 was CHANGES REQUESTED largely for two disclosed
findings never getting real `NEW-###` ledger entries), the two out-of-scope
gaps above (admin-convert-lead-still-unclaimed; ROLE_CUSTOMER
custom-permission edge) were disclosed in the implementer's report but as
of this diff have **no `NEW-###` entry** in `NEW_ISSUES.md` (checked —
highest id in the file is still 599). Coordinator must add these (rule 8)
in the normal step-5 ledger update alongside closing NEW-598 — this is a
process condition on the round, not a code defect, so it doesn't block
approval the way the NEW-568 case did (that implementer's report never
mentioned its findings at all; this one did).

**Design note worth remembering**: `create_customer`'s new gate silently
*overrides* a narrowed actor's supplied `assigned_user_id` (like
`create_contract`); `update_customer`'s NEW-568 gate *raises*
`PermissionError` on the same permission check instead. Deliberate,
disclosed-in-comment asymmetry (create has no prior value to protect,
update does) — correct call, not a bug, but worth knowing this file has
both idioms for the same permission depending on create-vs-update
semantics.

**Reusable technique**: when a fix reuses a permission constant across
`create_*`/`update_*` pairs, always read the actual line where the
"mirrored" check lives (don't trust a description that it "matches") —
here it genuinely did, byte for byte. Also: before treating a disclosed
downstream gap as "matters for feature X," grep whether X's actual write
path (commission ledger here) even reads the field in question — often it
doesn't yet, because the consuming feature isn't built, which meaningfully
changes severity today vs. later.
