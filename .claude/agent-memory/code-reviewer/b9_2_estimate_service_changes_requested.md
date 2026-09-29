---
name: b9_2_estimate_service_changes_requested
description: Phase B9.2 EstimateService (restoricon_core) review — CHANGES REQUESTED, found unlogged Critical bug via advisor-directed empirical repro
metadata:
  type: project
---

Phase B9.2 (Codey-Estimator Integration, branch `feat/estimator-phase3-schema`,
2026-09-29): `restoricon_core/services/estimate_service.py` + vendored
`codey_estimator/` calc library. Round1 verdict: **CHANGES REQUESTED**.

**What my own read-and-test pass missed, that advisor caught before I signed off:**
the task brief's own checklist item 7 ("assess whether record_decision's
missing-Contract gap is safe to defer") led me to just re-quote the
implementer's disclosed `NEW-705` (no Contract created on accept) instead of
independently checking whether `record_decision('accepted')` also fails to
lock the version. It doesn't. I wrote a live repro script (real
`DatabaseManager(":memory:")` + real service classes, not mocks) and
confirmed: `create()` → `add_line()` → `record_decision(accepted)` → a SECOND
`add_line()` on the SAME estimate succeeds and silently changes the totals of
an estimate the customer already legally signed. This is a bigger, *unlogged*
gap than the disclosed `NEW-705` — it breaks the codebase's own stated
"§1.6: prices don't silently refresh" invariant. The existing test
(`test_record_decision_requires_signer_name_on_accept`) didn't catch it
because it calls `_lock_version()` manually before `record_decision()`,
so the happy path via `record_decision()` alone was never exercised.

**Pattern for future reviews**: when a task's own checklist directs you to
verify a *disclosed* deferral/gap, don't stop at confirming the disclosed
claim is accurate — check whether the SAME code path has an adjacent,
UNDISCLOSED gap the implementer didn't think to log. "Is X properly deferred
and documented" and "is there an X-shaped bug nobody wrote down" are
different questions; a clean answer to the first doesn't cover the second.
Empirically probe the actual state transition (lock/permission/workflow
guard), don't just check that the documented gap matches the doc.

**Also found**: line-level cost fields (`unit_cost_cents`, `cost_total_cents`,
`material_markup_bp`, `override_reason`, `internal_note`) in
`_row_to_line()` have NO permission gate, unlike the header-level cost fields
(`_attach_cost_fields()` correctly gates those on `PERM_READ_ESTIMATE_COSTS`).
Reproduced live: a `ROLE_CUSTOMER` actor calling
`get(..., include_lines=True)` sees full cost breakdown on their own line
items. Not live-exploitable yet (no route calls `include_lines=True` for a
customer this round — B9.3 routes deferred), but will become one the moment
a future round wires that route. Docstring claims "D9 cost gating" is done;
that's only true at the header level — a doc-claim/actual-behavior gap
worth watching for on every future `get()`/`list()` cost-gating claim in
this project (see also [new533_sales_manager_permission_approved] for the
general "audit after-image re-gate" pattern of narrow permission claims
that don't cover every field/level).

**NEW-707 test-count claim did not reproduce**: implementer claimed
"59 failed, 703 passed" for `pytest tests/test_restoricon_core/`
(HTTP_PROXY unset). I ran the identical command twice: 762 passed, 0 failed,
both times. Root cause found: `test_api_health_and_unauthenticated_access`
is fixture-order-dependent — fails 405-vs-200 when run in isolation
(`pytest ...::test_name`), passes when the whole file or whole directory
runs (52/52, 762/762). 703+59=762 exactly matches my total, so the
implementer's claimed test SET was real, just the observed pass/fail split
depended on invocation scope/order, not a flat, reproducible 59-failure
state. This is a NEW case distinct from [[sandbox_proxy_test_artifact]]
(that one was proxy-env-var-caused false failures) — this one is
fixture-order/isolation-caused false failures, opposite direction (fails
alone, passes in the full run). Lesson: when a "pre-existing failures"
claim doesn't reproduce, don't assume the implementer fabricated it —
try running the SAME named test in isolation vs. in its full file/dir
before concluding anything; order-dependent fixtures are a real, recurring
failure mode in this test suite, not just proxy env vars.

**What verified clean and matched claims exactly**: vendored library
byte-identity (`diff -r` against `~/Codey-Estimator-reference/src/codey_estimator`
— only new `__init__.py` docstring differs, `__pycache__` excluded), AST-based
stdlib-only import sweep (confirmed `install.sh` genuinely needs no change),
markup-default gating (non-vacuous, confirmed via truthy-or negative
control), `revise()` clone-verbatim (no `_recalculate_version()` call,
`_LINE_ITEM_CLONE_COLUMNS` includes `material_markup_bp`), RBAC role-grant
sets checked programmatically against real `ROLE_PERMISSIONS`, atomic
`estimate_number_sequences` bump inside the same `BEGIN IMMEDIATE` as the
estimate insert (NEW-534 precedent, already-approved pattern on this branch).
