---
name: new643-646-technician-operations-write-narrowing-approved
description: NEW-643/644/645/646 write-path counterpart to NEW-628 (6 operations_service.py write methods narrowed for ROLE_TECHNICIAN) — APPROVED round1
metadata:
  type: project
---

2026-09-25, `restoricon_core/services/operations_service.py` +
new `tests/test_restoricon_core/test_new643_646_technician_operations_write_narrowing.py`
(18 tests) + `NEW_ISSUES.md` (NEW-647). APPROVED round1, zero findings — every
specific claim in the task brief independently verified true, none deflated.

**All six specific verification asks came back confirmed, not just plausible:**
- `update_work_order`'s UPDATE SET clause genuinely never writes `project_id`
  (read the full SQL directly) — the DB-fresh-read-not-model-field design is
  correct, not defense-in-depth theater. Test proves it with a hand-spoofed
  `wo.project_id` that doesn't match the real DB row.
- `deploy_equipment`'s check sits after the `AVAILABLE`-status guard but
  before the `with conn:` INSERT/UPDATE block — genuinely before all side
  effects, confirmed by reading the full method body top to bottom, not just
  the diff hunk. Test proves it with a post-denial re-read showing equipment
  still `AVAILABLE`/`current_project_id is None`.
- `crm_service.py`'s subcontractor-delete precheck (`~L6742`, inside
  `delete_subcontractor`) really does call
  `self.operations._query_active_work_orders_for_subcontractor(subcontractor_id)`
  directly — the shared *unfiltered* helper, no `actor` param at all — not
  the narrowed public method. So NOT filtering the shared helper is correct;
  filtering it would have silently let technicians delete subcontractors
  with real active work orders. Confirmed by reading the call site itself.
- The additive `project_id` field on `get_active_work_orders_for_subcontractor`'s
  return rows, and the `/api/v1/subcontractors/{id}/active-references` route
  exposing it, are both real (routes.py ~L2134). **Correction to my own first
  pass:** an initial `.js`/`.html`-only repo scan found zero consumers and I
  nearly wrote "no consumer exists" into this file — wrong methodology. This
  project renders dashboard JS from Python f-strings (`web_surfaces.py`,
  ~5700 lines), not standalone `.js` files (see [[new470_staff_portal_fstring_escape_approved]],
  [[b8_13b_sales_portal_table_scroll_wrapper_approved]] for the same pattern).
  A `.py`-inclusive scan found the real consumer: `web_surfaces.py`'s
  `deleteSubcontractor()` (~L3130), which reads `refData.active_references.work_orders`
  and accesses only `w.id`/`w.work_order_number`/`w.status` by name — no
  `Object.keys`/`for...in`/strict-key iteration. Also confirmed
  `_query_active_work_orders_for_subcontractor` returns `[dict(row) for row in rows]`
  (plain dicts, so `project_id` really is in the JSON body) before concluding
  the additive field is safe. Conclusion (additive field is harmless) held,
  but reached by verifying the actual consumer, not by absence of one.
  **Lesson: file-extension-scoped searches in this repo must include `.py` —
  a large fraction of this project's UI lives inside Python route/surface files.**
- `_actor_assigned_to_project`/`_technician_assigned_project_ids` are reused
  verbatim from NEW-628, not reinvented — confirmed by diffing their bodies
  against the pre-existing code (no diff hunk touches them).
- `ROLE_TECHNICIAN` genuinely holds `PERM_WRITE_OPERATIONS` in
  `auth.py`'s `ROLE_PERMISSIONS` map — this is a live-reachable fix for a
  real pre-existing hole, not narrowing an already-unreachable permission
  combination.

**Test-count discrepancy fully reconciled, not just flagged:** implementer
claimed "2514 passed, 1 skipped" full suite. My own `tests/` run: 1 failed
(`test_resource_bus.py::test_multiprocess_concurrency`, `assert 7 == 5`,
unrelated to this diff) + 2399 passed + 1 skipped = 2401. Reran that one test
in isolation and it passed (`1 passed in 2.62s`) — confirmed load-dependent
flake by direct isolation-reproduction, not by family-resemblance to the
similarly-named [[test_resource_bus_aging_flaky_under_load]] entry (that one
covers a *different* test in the same file; don't let file-level pattern
matching stand in for actually rerunning the specific test). `ccos/tests/`
run separately (not just collected): 114 passed, 69 warnings, 0 failures.
2399 + 114 = 2513, +1 when the flaky test lands passing on a given run = 2514
— arithmetically and empirically explains the implementer's number exactly.
The task brief's own flagged "~2496 baseline vs 2458 cited" drift was NOT
independently re-derived this round (out of scope to bisect further) —
punting that specific number to the coordinator's ledger write, but the
*current* 2514 figure is now solid on both counts and reproduction, not
arithmetic alone.

Full scoped rerun (`test_new643_646...` + `test_new628...` +
`test_new507_subcontractor_delete.py` + `test_operations_domain_engine.py`):
86/86 passed, matches claim exactly. Full `tests/test_restoricon_core/`:
1201 passed, no regressions.

**Internal-caller sweep (the check that actually could have flipped the
verdict) found one real non-test, non-route caller:**
`_ensure_default_milestones()` (~L508) calls `self.create_milestone(m, actor)`
internally during `transition_project_stage()`'s `INTAKE -> ASSESSMENT_SCOPING`
gate, passing the *same* `actor` through unchanged. `transition_project_stage`
itself gates on `PERM_MANAGE_PROJECTS`, which `ROLE_TECHNICIAN` does NOT hold
by default (confirmed via `auth.py`'s `ROLE_PERMISSIONS` map) — so a default
technician can never reach this path at all, no regression there. The one way
in: `AuthContext.custom_permissions` can override role grants per-actor
(`has_permission` checks `custom_permissions` first) — a `ROLE_TECHNICIAN`
actor custom-granted `PERM_MANAGE_PROJECTS` (role stays `ROLE_TECHNICIAN`)
would pass the outer gate, then hit the *new* role-keyed check inside
`create_milestone` and get denied if not assigned to the project, aborting
the whole stage transition. Traced this is NOT a data-corruption risk: the
`_ensure_default_milestones` call sits before the `UPDATE projects SET
stage = ...` write in `transition_project_stage`, so a raised PermissionError
here aborts cleanly with zero partial writes. And the underlying tradeoff
(role-keyed, not permission-keyed, because assigned-employees ownership has
no permission of its own to key on) is NOT new to this round — it's the same
accepted design NEW-628 already reviewed and approved for the read-side
methods. This round's write-side methods just inherit that same precedent
consistently. Narrow, precedent-consistent, no live test exercises the
custom-permission combo today — logged here as a Suggestion-tier awareness
note, not a blocker.

**TOCTOU on `update_work_order`'s ownership check (brief item 1), answered
directly:** `DatabaseManager.get_connection()` returns a cached thread-local
`sqlite3.Connection` (same connection reused across both calls in this
method), but the ownership SELECT runs outside any `with conn:` block while
the subsequent UPDATE runs inside its own separate `with conn:` transaction
— a real gap where a concurrent write could reassign the technician between
the check and the write. Confirmed this is **no worse than the existing
codebase convention**: `deploy_equipment` has the identical shape (read via
`get_equipment` outside a transaction, then a separate `with conn:` block for
the write) and was already approved under NEW-628. Not a new risk introduced
by this round.

Reusable technique: when a task brief cites a specific line number for an
external caller (`crm_service.py:6742`), read that exact call site directly
rather than trusting the docstring's paraphrase of it — the docstring here
was accurate, but that's the kind of claim this project's history (NEW-259)
says needs primary-source confirmation, not docstring-trusting.
