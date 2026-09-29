---
name: new625-admin-shell-role-redirect-changes-requested
description: NEW-625 client-side role-redirect gate in render_admin_surface() — CHANGES REQUESTED round1 for a false comment + vacuous-pass test, not for the mechanism itself
metadata:
  type: project
---

Round: added a second `/api/v1/auth/me` fetch inside `render_admin_surface()`'s
existing `validateSession()` block to redirect `project_manager`/`sales`/
`technician`/`customer` away from the full admin ERP shell to their dedicated
portals. Relocation claim (fix belongs in `render_admin_surface()`, not
`_render_staff_portal_base()`/`loadDashboard()` as the original brief said)
verified true by direct read.

**What was independently verified clean:**
- `/api/v1/auth/me` response shape (`{"user": user.to_dict()}`) traced end-to-end:
  server handler in `restoricon_core/api/routes.py` → `User.to_dict()` is
  `asdict(self)` in `restoricon_core/models.py` → `role` is a real field. Matches
  an existing live consumer (`_render_sales_portal()`'s own `loadDashboard()`
  already does the identical fetch→`meData.user`→role-read pattern). This
  mattered because a wrong shape would have made the whole redirect a silent
  permanent no-op passing its own string-presence tests (same failure class as
  NEW-259's missing `port=` kwarg) — always trace the actual server response
  shape for a *new* fetch call, don't assume from a sibling endpoint's shape.
- `validateSession()`'s fail-open catch (`catch(e){return true}`) — comment's
  characterization accurate.
- Redirect-loop safety for all 4 targets (not just the one the implementer
  grepped): region-grepped `_render_staff_portal_base()`, `_render_sales_portal()`,
  AND `render_portal_surface()` (customer) each for any `/admin` in any quote
  style — zero hits, all 401 paths go to `/admin/login` only.
- `subcontractor` truly unissuable — checked BOTH `create_user()` and
  `update_user()` role-write paths against `ALL_ROLES`, not just the one the
  implementer cited.

**Real Critical finding:** the new code's comment asserts
"ROLE_MANAGER, ROLE_SALES_MANAGER, and ROLE_AI_AGENT have no dedicated portal"
— false for `sales_manager`, contradicted in the *same file* two ways: (1)
`_render_sales_portal()`'s own docstring says `sales_manager` is a first-class
intended consumer of `/sales`; (2) the pre-existing login-page redirect
(`handleLoginSubmit`, ~line 714) already does `sales_manager → /sales` when
landing at `/admin`. `manager`/`ai_agent` really do have no portal (grepped,
zero hits) — the false claim is specific to `sales_manager`. Worse: the new
negative test hard-asserts `sales_manager` stays OUT of the map, so a correct
future fix has to delete a test, not just add a line.

**Pattern:** when a new redirect/gating map excludes some roles "because they
have no dedicated portal," grep the entire file for that role string before
trusting the claim — a portal can exist under a docstring/precedent the new
code's author didn't check. Also: a `str.find()`-based test that slices
`html[i:j]` without asserting `i != -1 and j != -1` passes vacuously if the
target construct is ever renamed/removed — always guard slice-based
negative-presence tests.

See also [[b8_14a_new550_executive_dashboard_and_gate_approved]] for the
matching precedent on how to handle "should this role also be gated" as a
separate NEW-### rather than silently absorbing or silently dropping it.
