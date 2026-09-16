---
name: new534-atomic-claim-workflow-approved
description: NEW-534 atomic self-claim (claim_lead/claim_opportunity/claim_task) round — APPROVED, full independent verification of atomicity/disambiguation/route guards/audit-after-image
metadata:
  type: project
---

2026-09-16. `NEW-534` (closes the `NEW-533` "unclaimed pool" race gap) —
`restoricon_core/services/crm_service.py` (`ClaimConflictError` +
`claim_lead`/`claim_opportunity`/`claim_task`), `restoricon_core/api/routes.py`
(3 new `POST .../claim` routes), `restoricon_core/api/web_surfaces.py`
(`_render_sales_portal()` Claim buttons + `claimLead`/`claimOpportunity` JS),
plus `NEW-542` logged (not fixed, correctly out of scope). APPROVED after
full independent verification, not just reading the diff.

**What was verified directly, not taken on trust:**
- Atomicity: single conditional `UPDATE ... WHERE id = ? AND
  assigned_user_id IS NULL`, `cursor.rowcount` checked, all inside `with
  conn:` — confirmed no read-check-then-write gap.
- Disambiguation: on `rowcount == 0`, a **raw** `SELECT id, assigned_user_id`
  (not `get_lead`) distinguishes "row absent" (404) from "row present but
  claimed" (409). Traced `get_lead`'s `PERM_READ_TEAM_SALES_DATA` narrowing
  myself (lines 607-624) and confirmed it really does collapse both cases to
  `None` — the implementer's stated reason for avoiding it here is correct.
- Audit after-image built from the in-memory object mutated with the exact
  just-written values, not a re-read through the permission-gated getter —
  same pattern as the `NEW-533` fix ([[new533_sales_manager_permission_approved]]).
- `ClaimConflictError(Exception)` is NOT a `ValueError` subclass. Read
  `handle_request`'s actual except-chain (routes.py:2739-2744) and confirmed
  there is genuinely no 409 anywhere in it (`PermissionError`->403,
  `ValueError`->400, `Exception`->500) — an uncaught `ClaimConflictError`
  would fall through to 500, not a misleading 400. All 3 new routes catch it
  locally before the global chain.
- Route path-slicing guard (`"/" not in path[prefix:-suffix]`) actually
  rejects a multi-segment attack path — verified by direct simulation:
  `/api/v1/leads/1/2/claim` sliced to `'1/2'`, contains `/`, guard correctly
  fails to match (falls through to 404), following the `NEW-520`-era
  established guard shape ([[new520_522_523_batch1_path_segment_sweep_approved]]).
- Permission gates read side-by-side against `update_lead`/`update_opportunity`/
  `update_task` — exact match on all three (including the 3-way OR for tasks).
- Rendered JS syntax validated directly: extracted the actual `<script>`
  block from `_render_sales_portal()`'s output and ran `node --check` on it
  — passed. This f-string's `{{`/`}}` doubling convention is easy to get
  wrong (see `NEW-538`/`web_surfaces_join_backslash_n_regression` history) so
  don't trust "the tests pass" as proof of JS validity; extract and check the
  actual rendered string yourself.
- `test_sales_portal_has_claim_buttons_and_fetch_calls` genuinely asserts on
  the rendered button markup string, not just function-name presence, and
  also asserts `"Unclaimed"` still renders alongside the button (catches the
  implementer's own earlier draft bug of replacing the label instead of
  adding a button).
- `test_claim_opportunity_api_route_200_409_404` /
  `test_claim_task_api_route_200_409_404` genuinely go through
  `router.handle_request`, not direct service calls — confirmed present and
  correctly scoped (opportunity/task route path-slicing differs from the
  lead route, e.g. task's real prefix is `/api/v1/crm/tasks/`).
- `git diff --stat -- '*resource_bus*'` returned empty — the implementer's
  "pre-existing unrelated flake" attribution for `test_multiprocess_concurrency`
  is correctly scoped to files this diff doesn't touch.
- Full suite reproduced verbatim: `1944 passed, 1 skipped in 306.21s` (proxy
  vars unset per [[sandbox_http_proxy_urllib_405_env_artifact]]), exact match
  to implementer's claim, no flake observed on this run.

**New technique worth reusing:** when a diff touches an f-string-rendered
`<script>` block, don't just eyeball the brace-doubling — programmatically
call the render function, regex out the `<script>...</script>` body, and run
it through `node --check`. Cheap, and this project has hit real
brace/escaping regressions in rendered JS multiple times (`NEW-538`,
`web_surfaces_join_backslash_n_regression`).

See also [[new533_sales_manager_permission_approved]] for the prior round
this one directly builds on (same audit after-image pattern, same
`_scoped_assignee_filter`/narrowing mechanics referenced by `claim_lead`'s
own docstring).
