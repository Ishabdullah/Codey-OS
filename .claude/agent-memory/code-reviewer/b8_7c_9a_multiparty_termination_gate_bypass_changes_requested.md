---
name: b8_7c_9a_multiparty_termination_gate_bypass_changes_requested
description: B8.7c portfolio-override termination gate silently bypassed for multi-party-signed GC contracts (customer_signed_at stays NULL); combined B8.9a territory review round
metadata:
  type: project
---

Combined B8.9a (territory management) + B8.7c (Phase 3 portfolio-override
commission) review, 2026-09-23. **CHANGES REQUESTED** — one Critical, real-money
bug, live-reproduced.

**The bug**: `_resolve_portfolio_override_eligibility`'s gate 5 (the
counter-intuitive termination rule — a GC contract signed before the
originating rep's termination still pays after they leave) reads
`gc_contract["customer_signed_at"]` and only runs the termination check
`if signed_at is not None:`. But `sign_contract`'s multi-party completion
path (`restoricon_core/services/crm_service.py`, the `all_signed` branch
added in B8.6d-b) flips `contracts.status` to `'signed'` WITHOUT ever
setting `customer_signed_at` — only the original single-signer path sets
it. Any GC contract opted into multi-party signing (`add_contract_signers`,
a real supported B8.6d-b feature) therefore has `customer_signed_at IS
NULL` forever, so gate 5's `if signed_at is not None:` is always False and
the function falls straight through to `eligible=True` — the termination
gate is completely skipped, always paying the override regardless of when
the GC contract was actually signed relative to the rep's departure.

Live-reproduced: enrolled HomeCare via hc_rep, terminated hc_rep BEFORE
even creating the GC project/contract, signed the GC contract via the
multi-party path (`add_contract_signers` + two `sign_contract` calls),
then `record_payment` — a $2,500 portfolio_override ledger row was written
attributed to the terminated rep, the exact scenario the termination gate
exists to block (worse than the disclosed opposite test case, since here
the contract didn't even exist yet at termination time).

All 15 new B8.7c tests (`test_b8_7c_portfolio_override.py`) use only the
single-signer `sign_contract` path via `_make_gc_project_and_contract` —
the multi-party path is never exercised, so this is completely untested,
not just an edge case the tests happen to miss narrowly.

**Fix needed**: do NOT stamp `contracts.customer_signed_at` on the
multi-party completion branch — that column pairs with
`customer_signature_data` and specifically means "the customer signed";
on a multi-party contract the last signer may be the admin/PM, so writing
that timestamp there would be semantically wrong and an out-of-scope edit
to an already-reviewed B8.6d-b signing path (read elsewhere at
`crm_service.py:3685`/`:4259`). Instead, confine the fix to B8.7c's own
helper: resolve the "signed" timestamp as `MAX(contract_signers.signed_at)`
when signer rows exist for the contract (the contract is complete when the
*last* required signer finishes, the multi-party analogue of the
single-signer case), falling back to `customer_signed_at` when there are
no signer rows. Also fix gate 1b's contract-selection query
(`ORDER BY customer_signed_at DESC, id DESC`) — SQLite sorts NULLs last
under DESC, so if a project has both a single-signer and a multi-party
signed GC contract, the multi-party one is systematically deprioritized
by that ordering; both the ordering and the gate-5 read need the same
signed-timestamp resolution, not just gate 5.

**Everything else in this round checked out**: `_migrate_users_role_constraint()`
drift-guard correctly extended for both `territory_id` (B8.9a) and
`terminated_at` (B8.7c) in both `_USERS_TABLE_WIDENED_ROLE_SQL` and its
`new_cols` set, and ordering confirmed safe (ALTER migrations run before
the role-constraint rebuild within the same `_migrate_schema()` call).
`set_user_active`'s three UPDATE branches are genuinely one atomic
statement each (no partial-write window). Config-read-inside-try placement
verified literally first line for the third time running (B8.7a/b/c all
independently confirmed this exact bug class avoided). RBAC pair
`PERM_READ_TERRITORIES`/`PERM_WRITE_TERRITORIES` verified byte-for-byte
matching `PERM_READ_APPOINTMENT_TYPES`/`PERM_WRITE_APPOINTMENT_TYPES`'s
grant shape per-role programmatically, including the `ROLE_SALES_MANAGER =
ROLE_SALES | {...}` derived-role trap from prior rounds. `update_lead`'s
dual allow-list + literal SQL/params for `territory_id` both correct.
create_customer/create_lead INSERT placeholder counts both verified 20/20
programmatically. `portfolio_override` already valid in both
`_VALID_SOURCE_TYPES` and the DB CHECK constraint before this diff
(confirmed via `git diff`, not present in the diff = pre-existing). No new
non-stdlib dependency (`calendar`/`namedtuple` both stdlib) — install.sh
correctly untouched. Full suite: 2357 passed, 1 skipped, 340.83s. Baseline
arithmetic closes exactly: 2329 (B8.9a's own pre-round baseline) + 13
(B8.9a's new tests) = 2342 + 15 (B8.7c's new tests) = 2357 — both
implementers' claims reconcile precisely, not just "in the right range."

`set_user_active`'s disclosed TOCTOU is NOT cosmetic: a suspend racing a
reactivate can leave `active=1` with a stale `terminated_at` still set.
Gate 5 would then see a real, currently-employed rep as terminated and
reject an override that should legitimately pay — a silent, fail-closed
**money-loss** direction (not the fail-open direction of the multi-party
bug above), with no audit trail since normal-ineligible outcomes aren't
logged. The disclosure text is accurate but understates this; worth a
NEW_ISSUES entry alongside the Critical.

**Warning (in-scope, not a bug but a surprising outcome, worth
NEW_ISSUES)**: gate 2 reads the customer's *earliest* HomeCare
subscription (`ORDER BY enrolled_at ASC LIMIT 1`) for both rep attribution
and the window anchor, while gate 4 reads the *latest*
(`ORDER BY enrolled_at DESC LIMIT 1`) for the live-active check. A
customer with an old cancelled enrollment and a newer active one gets the
override attributed to the *old* rep, anchored to the *old* enrollment
date, while passing the active check against the *new* subscription. This
matches the docstring's literal description (not a doc/code mismatch) but
is a real, reachable, surprising attribution outcome on a money path.

Confirmed explicitly (coordinator's question): B8.9a's own `territory_id`
drift-guard fix was already correct on its own before B8.7c touched
anything — B8.7c's implementer only extended the identical pattern to add
`terminated_at` alongside it, never had to fix B8.9a's work.

See [[b8_6d_b_round2_atomicity_fix_approved]] for the sibling atomicity
discipline this round's `set_user_active` fix correctly followed, and
[[new565_575_rbac_sign_contract_approved]] for the multi-party signing
mechanics this bug's root cause lives in.
