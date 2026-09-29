---
name: new625-round2-approved
description: NEW-625 admin-shell role-redirect round-2 fix — APPROVED, closes round-1 CHANGES REQUESTED
metadata:
  type: project
---

Round 2 of [[new625_admin_shell_role_redirect_changes_requested]] — APPROVED.
All three round-1 defects independently re-verified fixed, not just reworded:

1. False comment ("sales_manager has no dedicated portal") replaced with an
   accurate one that names the real portal (`/sales`), cites the same two
   pieces of evidence I found in round 1 (`_render_sales_portal()` docstring,
   login-redirect at web_surfaces.py:713-714), and explicitly defers the
   redirect-map inclusion to NEW-642 rather than asserting it doesn't exist.
   Independently re-read web_surfaces.py:710-716 — the login redirect really
   does have `else if (r === 'sales_manager') target = '/sales'` (and, as a
   bonus, also a `subcontractor` → `/subcontractor` branch, which is itself
   dead code since the role can never be assigned — consistent with the new
   NEW-641 entry).
2. `i != -1` / `j != -1` guards added right after both `html.find()` calls,
   before the slice — correctly placed, not decorative.
3. NEW-641 (subcontractor role unissuable but route/render function live)
   and NEW-642 (sales_manager has a portal, deliberately deferred) both
   added, no id collision (repo was at NEW-640 before this round). Content
   independently re-verified against auth.py: `ALL_ROLES` (line 36-45) has
   no `ROLE_SUBCONTRACTOR`; both `create_user()`/`update_user()` gate on
   `ALL_ROLES` per round-1 notes.

The `rolePortals` map (`project_manager`→/pm, `sales`→/sales,
`technician`→/tech, `customer`→/portal) is byte-identical to round 1 — full
diff of `web_surfaces.py` for this round is purely additive (43 lines, 0
removed), all of it new comment text + the try/fetch block above
`loadUsersList()`. `tests/test_restoricon_core/test_web_surfaces_admin_wiring.py`
and `test_web_surfaces_js_syntax.py` both rerun clean: 39/39 passed
(literal output captured), matching implementer's claim.

**Still true after this round:** the actual `window.location.href`
navigation has zero automated (browser) coverage in this repo — only
string-presence-in-rendered-HTML is tested. A live-verifier pass remains
warranted before/after commit for a redirect that gates access to the full
admin ERP shell for 4 roles, even though the commit itself is safe to make
on code-complete + reviewed evidence (consistent with rule 7's
code-complete/approved/live-verified three-tier distinction, and with how
prior admin-dashboard rounds handled this same gap).
