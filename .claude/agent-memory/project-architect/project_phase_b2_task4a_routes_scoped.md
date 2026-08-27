---
name: phase-b2-task4a-routes-scoped
description: Phase B2 task 4a (HTTP routes for the 5 new resources) scoped 2026-08-27, not implemented; RBAC needs zero new grants; 3 new findings (NEW-219/220/221)
metadata:
  type: project
---

Task 4a (routes.py wiring for subcontractors/appointments/
automation_rules/business_profile/do_not_contact) scoped 2026-08-27,
commit `3028466`. Full 17-route table with per-route error-handling
(404 vs 400 vs bare-bool response) written into `CODEY_MASTER_PLAN.md`
§6.4. No code written — spec only, next step is implementer then
mandatory code-reviewer (security clause, not rule 4 — routes.py isn't
a process-lifecycle change).

Key facts a future round needs, not re-derivable without reading again:
- RBAC in this codebase is enforced entirely in the *service* layer
  (`actor.has_permission(...)` inside each service method), not at the
  route layer. `routes.py`'s `handle_request` never calls
  `has_permission()` itself — it just resolves the Bearer token to an
  `AuthContext` and lets a global `except PermissionError` catch turn a
  service-layer rejection into 403. Any future route-layer work should
  expect this shape, not add a second permission check at the route.
- `api/server.py` only constructs `CRMService` today — `SchedulingService`/
  `AutomationService` exist but are never wired into the running server
  or into `APIRouter`. `APIRouter(` is constructed in exactly one place
  in the whole repo (`api/server.py:88`), confirmed by a repo-wide grep,
  so widening its constructor signature is safe.
- Zero existing HTTP routes use PUT/DELETE despite the handler
  dispatching both (`do_PUT`/`do_DELETE` are dead dispatch) — the
  established convention for updates is a POST to an action-suffixed
  path (`/{id}/sign`, `/{id}/pay`), matched by the new
  `/qualification`, `/status`, `/match` routes in the spec.
- `migrate_aigentik.py` calls the three new services directly in-process
  (confirmed by its imports), not over HTTP — so the `get_*_by_external_id`
  lookup methods added for migration idempotency (`NEW-217`) don't need
  HTTP routes and deliberately weren't given any in this spec.
- New findings this round, all Confirmed, none fixed: `NEW-219`
  (`automation_service.py` has no get-rule-by-id, so the planned
  `POST /automation-rules/{id}/match` route is write-only for that id —
  same class as `NEW-193`); `NEW-220` (`is_blocked`/
  `remove_from_do_not_contact` return bare `False` for a malformed
  identifier, indistinguishable from "not on the list" — safety-relevant
  on a do-not-contact suppression surface); `NEW-221`
  (`Model(**json_body)` raises uncaught `TypeError` on unrecognized
  keys, falls through to 500 instead of 400 — pre-existing on all 8
  current POST routes, the 5 new ones will inherit it).
- Test baseline before any implementation: `764 passed, 1 skipped`.
