---
name: b8_16_phase5_backfill_script_approved
description: B8.16 Phase 5 one-off historical backfill script (Joy Clark WO#351695937, $790) — script logic APPROVED, but blocked from live-verifier by a real live-DB schema gap only found by actually executing against a safe copy
metadata:
  type: project
---

**UPDATE (same session, post-advisor):** the advisor flagged that `main()`
itself was never exercised by the 6 tests (they all call `run_backfill`
directly). Copied the real live DB to scratchpad and ran
`python -m restoricon_core.backfill_wo_351695937 --db-path <copy> --apply`
against the copy. It crashed: `sqlite3.OperationalError: table
work_orders has no column named parent_work_order_id`. Confirmed by
reading `work_orders`' actual `CREATE TABLE` SQL on the real live file
directly — the real live DB predates B8.16 Phase 3's additive migration
entirely (missing column AND the `status` CHECK still lacks `'split'`).
This means the live DB has not had `DatabaseManager(init_schema=True)`
(the normal migration path, confirmed purely additive/guarded by
reading `database.py`'s migration list + `_migrate_work_orders_status_constraint`)
run against it since Phase 3 shipped — an environment/deployment gap,
not a defect in the Phase 5 script's own logic, but a hard blocker for
handing this to live-verifier as-is: `--apply` against the real file
would crash identically. Verdict changed from a same-session draft
APPROVED to CHANGES REQUESTED / BLOCKED pending an explicit schema-sync
step before live-verifier runs `--apply`. This is the second time this
project's "code-complete/approved but only actual execution reveals the
real gap" pattern (NEW-259) has recurred here — always try to actually
run the script against a throwaway copy of the real target file when one
is reachable, not just the isolated in-memory test DB.

2026-09-29. `restoricon_core/backfill_wo_351695937.py` +
`tests/test_restoricon_core/test_b8_16_phase5_wo_351695937_backfill.py`
(both new/untracked files, not yet committed). This closes out B8.16 (see
[[b8_16_phase4_intake_form_round2_approved]] for the prior phase in this
chain) — a one-off script bypassing `submit_work_order_intake` to write a
real historical completed/paid job directly via
`CRMService.create_customer/create_project/create_invoice/record_payment`
+ `OperationsService.create_work_order`.

**Verdict: APPROVED.** This is the rare review where I could independently
re-run the implementer's own claimed read-only live-DB queries myself
(direct sqlite3 access to `~/.codeyOS/restoricon.db` was available from
this context) rather than only assessing the reasoning — did so, all
matched: `users.id==1` real row (role='ai_agent', not 'admin' — didn't
matter, see below), `mike.regina` id=3/role=admin/active=1, `work_orders`
count=0, target customer email had zero existing matches (relevant since
`get_customer_by_email` collapses 2+ matches to None, same as zero — a
pre-existing ambiguity-as-unknown contract, not new here), no prior
idempotency-marker row existed yet.

Money-path claims verified by reading the actual code, not the docstring:
- `generate_work_order_number()` really does regex-parse the newest row's
  trailing digits (`\d+$`) — hardcoding `WO-351695937` would genuinely
  poison all future numbering; the chosen alternative (server-assigns,
  historical number folds into `notes`) is sound.
- `_resolve_portfolio_override_eligibility` gate 1b really does require a
  `contracts` row with `status='signed'` linked by `project_id` — a
  brand-new `Project` with zero `Contract` rows unconditionally resolves
  `eligible=False, skip_reason='contract_link_missing'`, so the flat
  commission fires and the override block logs-only, no second row.
  Confirmed via direct read of the actual gate query, not the comment
  above it.
- `commission_service.py` has zero `ROLE_SALES`/role-keyed special case
  anywhere (grepped) — Mike Regina holding `ROLE_ADMIN` doesn't change or
  block commission attribution.
- `AuthContext.has_permission` is pure in-object (role field on the
  constructed object), never re-queries `users.role` from DB — so a
  hand-built actor with `user_id=1, role=ROLE_ADMIN` works regardless of
  what `users.id=1`'s real DB row's role column says. This is the
  established "system actor" convention already used elsewhere
  (`intake_system_actor`, `commission_system_actor`, `pdf_system_actor`),
  not new here.
- `create_project` does not validate `stage` against the normal
  transition state machine at all (no call to `transition_project_stage`
  from `create_customer`/`create_project`), and does NOT auto-generate
  default milestones (`_ensure_default_milestones` is only called
  elsewhere, never from `create_project`) — so creating directly at
  `ProjectStage.BILLED` leaves zero milestone rows, no dangling invariant.
- Line-item math hand-verified: 220+530+70+25+10+2+8-75+0 = 790.00,
  confirmed server-computed (`create_invoice`'s
  `item_total = round(qty*unit_cost, 2)` then summed, never client
  `amount` trusted when `line_items` present).
- `record_payment` writes `recorded_by_user_id: actor.user_id` into
  `payments_json` — this is the actual reason the script's docstring
  gives for using `user_id=1` instead of `migrate_aigentik.py`'s
  `user_id=None` pattern; confirmed by reading the line directly.

Ran the 6 new tests (6 passed) and the full
`tests/test_restoricon_core/` suite myself with `HTTP_PROXY`/
`HTTPS_PROXY` unset ([[sandbox_proxy_test_artifact]] trap) — got
`1359 passed in 250.93s`, matching the implementer's claim verbatim.

One non-blocking Suggestion raised: the idempotency gate is a single
`work_orders.notes LIKE '%Original work order number: 351695937%'`
substring check — fragile if an admin later edits/truncates that notes
field (a third `--apply` run would then silently re-create everything).
Not fixed, flagged only, per the review task's own framing as
not-necessarily-blocking.

Recipe for next time a script writes directly to the real device DB:
if you have direct filesystem/sqlite3 access to the target DB from your
own context, actually run the implementer's claimed read-only
verification queries yourself before trusting a pasted claim — this
round it was possible and caught nothing wrong, but it is the only way
to actually confirm live-DB facts rather than assess reasoning about
them.
