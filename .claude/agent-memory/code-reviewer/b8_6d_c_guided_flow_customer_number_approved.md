---
name: b8_6d_c_guided_flow_customer_number_approved
description: B8.6d-c guided customer->template->sign flow + customer_number + NEW-597/NEW-593 fixes — APPROVED, all atomicity claims live-stress-tested and held
metadata:
  type: project
---

2026-09-22, B8.6d-c (final B8.6 sub-phase). Reviewed uncommitted diff
across `database.py`/`models.py`/`crm_service.py`/`routes.py`/
`web_surfaces.py` + new `test_b8_6d_c_guided_flow.py`. **APPROVED, no
round 2 needed** — first B8.6d sub-round to clear on round 1 (prior two,
[[b8_6d_b_multi_party_signer_party_role_spoof_changes_requested]] and
[[new568_customer_rep_narrowing_changes_requested]], both needed a
round 2).

**Every atomicity/correctness claim was independently live-stress-tested,
not just diff-read — and all held:**
1. `customer_number` via `INSERT INTO customers (...) SELECT
   COALESCE(MAX(customer_number),0)+1, ... FROM customers` (single
   statement, no split SELECT+INSERT, no UNIQUE constraint backstop by
   design — ALTER TABLE ADD COLUMN can't add one). Ran 60 real threads
   against a real file-backed WAL DB (not `:memory:`) calling
   `create_customer` concurrently: 60/60 unique sequential numbers, zero
   errors, zero collisions.
2. NEW-597's `INSERT ... SELECT ... WHERE NOT EXISTS` guard in
   `add_contract_signers` (the exact bug class flagged as a live-verified
   Warning in [[b8_6d_b_round2_atomicity_fix_approved]]) — ran 30
   concurrent threads calling `add_contract_signers` with the same
   `party_role` against one contract: exactly 1 row created, 29 correctly
   skipped via `cursor.rowcount == 0`, zero errors. Also unit-verified
   `cursor.rowcount` semantics directly (`INSERT...SELECT...WHERE NOT
   EXISTS`: 0 when suppressed, 1 when inserted) against the actual
   installed sqlite3 3.53.4 in this environment, not assumed from docs.
3. `_backfill_customer_numbers` confirmed placed inside `_migrate_schema`'s
   existing `with conn:` block, after the ALTER-column loop (column
   guaranteed to exist first) — read directly, not paraphrased.

**NEW-593 (party_role identity check) correctly placed and correctly
scoped.** Check sits immediately before `_resolve_contract_signer_row` is
called, so a mismatched actor never even reaches row resolution.
Confirmed `_ROLE_TO_PARTY_ROLE` maps `ROLE_SALES` and `ROLE_SALES_MANAGER`
both to `"rep"`, and `ROLE_ADMIN`/`ROLE_MANAGER` both to `"admin"` — the
check is a *value* comparison (`actor.role`'s mapped value `!=
party_role`), so two roles legitimately sharing one party_role are NOT
broken by this check (a real risk the task flagged — verified false).

**Route-level trust verified**: new `POST /api/v1/contracts/<id>/signers`
derives `actor` from the same auth-middleware path every other route uses
(`routes.py:512`, `self.auth.authenticate_token(token)`), not from the
request body; RBAC + ownership narrowing is enforced entirely inside
`add_contract_signers` itself (`PERM_WRITE_CONTRACTS` + rep-ownership),
route does no bypass.

**`template_name` validation correctly distinguishes omitted vs
present-invalid** in both `create_contract` (`None` explicitly allowed)
and `update_contract` (`"template_name" in updates and ... not in
CONTRACT_TEMPLATE_NAMES` — omitted key skips the check entirely, matching
this file's existing `ALLOWED_CONTRACT_UPDATE_FIELDS` partial-update
convention).

**`list_customers` NEW-568 narrowing claim verified true by direct
read** — unmodified in this diff, still present at
`crm_service.py:334-336`. No new backend needed for guided-flow search,
claim checks out.

**JS syntax**: extracted the actual rendered `<script>` block from a live
`_render_sales_portal()` call (not the Python source) and ran `node
--check` on it directly — passed. Doubled-brace `${{...}}` escaping
correct throughout the new guided-flow functions (spot-checked against
the NEW-538 regression class).

**Full suite: 2240 passed, 1 skipped**, matches implementer's claim
verbatim (`python -m pytest -q`, proxy vars unset, 491.03s). Arithmetic
check (NEW-512 lesson): prior verified baseline
([[b8_6d_b_round2_atomicity_fix_approved]]) was 2225 passed; new test
file has exactly 15 `test_` functions; 2225+15=2240, no silently
lost/skipped test. Also re-ran the five specifically-named regression
tests (`test_sign_contract_new192_role_matrix`, `..._rejects_non_owning_narrowed_actor`,
`..._pm_ownership_bypass_local_to_signing`, `..._idempotency_guard`, plus
the full B8.6d-a/b/c test files together) in isolation — all pass.
`install.sh`/`requirements.txt`: confirmed zero diff — correct, no new
imports introduced.

**One out-of-scope gap surfaced, logged not fixed (belongs in
NEW_ISSUES, not this round's blocker):** `guidedSubmitNewCustomer()`'s
POST body to `/api/v1/customers` never sets `assigned_user_id`, and
`create_customer` (unchanged by this diff) never auto-assigns it to the
creating actor the way `create_contract` does
(`contract.assigned_user_id = actor.user_id`, unconditional, overriding
any client value — `crm_service.py:3521`). A customer created through the
new guided flow lands unclaimed (`assigned_user_id IS NULL`), visible to
every narrowed rep via NEW-568's `OR assigned_user_id IS NULL` clause,
not exclusively owned by the rep who created them — unlike this same
file's lead/opportunity "Claim" button idiom. Not a regression (
`create_customer`'s behavior itself is untouched), but a real,
undisclosed UX/ownership gap in the new guided-flow surface the round
itself introduces. Worth a NEW-### asking whether guided-flow customer
creation should auto-assign like contracts do, or get its own claim
affordance.

**Advisor caught a real gap in my verification before I finalized:** I had
verified NEW-593's gate logic and placement, but not verified it against
the *legacy zero-signer* path specifically, even though both `/sign`
routes now pass `party_role=json_body.get("party_role")`
**unconditionally**, and the route comment claims this is "ignored... for
the common single-signer contract." That's a behavior claim, not a test
— the new test file's two NEW-593 tests both call `add_contract_signers`
first, so neither one exercises a zero-`contract_signers`-row contract
with `party_role` supplied. Ran it live: `ROLE_SALES` actor (derived
party_role `"rep"`) calling `sign_contract(contract_id, "FORGED_SIG",
sales_actor, party_role="customer")` against a contract with **zero**
`contract_signers` rows (legacy path) succeeds with no exception,
`customer_signature_data` becomes `"FORGED_SIG"`. **The NEW-593 gate does
NOT fire on the legacy path** — confirmed by reading `sign_contract`
directly: the `party_role is not None and ... != party_role` check sits
inside the multi-party branch (after the `if not signer_rows:` early
path), never reached when `signer_rows` is empty.

**Differential against pre-diff behavior (the exact technique
[[b8_6d_b_multi_party_signer_party_role_spoof_changes_requested]]
demanded) confirms this is NOT a new escalation, not blocking**: ran the
identical scenario with the pre-B8.6d-c call shape (`sign_contract(id,
sig, sales_actor)`, no `party_role` kwarg at all) against a fresh legacy
contract — identical result, same forged customer-slot write succeeds.
This is the exact same pre-existing overloaded-authorization gap the
prior round already found, downgraded to Warning (not Critical), and
explicitly deferred as "matters more once B8.6d-c wires a route that
accepts party_role from a request body" — which is now true, but the
underlying exploit path and its severity are unchanged from what was
already disclosed; the route wiring doesn't newly enable it. Route
comment's claim ("signs exactly as before this round") is accurate.
**Still open, still worth its own NEW-### fix** (the legacy single-slot
path has zero identity validation regardless of who's allowed to sign)
but is not this round's blocker — same Warning-tier call as last round,
now re-confirmed with the actual party_role-passthrough route live in
place, not just reasoned about.

**Residual scope note, not run (per advisor, non-blocking):** the NEW-597
`INSERT...SELECT...WHERE NOT EXISTS` 30-thread stress test ran against a
fresh DB (has the new `UNIQUE(contract_id, party_role)` constraint). Per
`database.py`'s own comment, `CREATE TABLE IF NOT EXISTS` won't retrofit
that constraint onto a DB where `contract_signers` was created by the
earlier 718f692 commit without it — the NOT-EXISTS guard is claimed to be
the load-bearing mechanism on such DBs, independent of the constraint.
This is pure SQL and should behave identically with or without the
UNIQUE index present, but that specific DB shape (table pre-existing,
missing the constraint) was not independently stress-tested — only
reasoned about. If a future round touches this code again, stress-test
against a manually-reconstructed pre-UNIQUE schema before trusting the
"NOT EXISTS alone is sufficient" claim on old DBs.

**Technique notes carried forward:**
- The live thread-stress technique (real file-backed WAL DB via
  `tempfile.mktemp`, N threads hammering one service method, checking
  `set(results)` size / `rowcount` sums) is now proven for both the
  "INSERT...SELECT single atomic statement" class (`customer_number`) and
  the "INSERT...SELECT...WHERE NOT EXISTS idempotent-insert" class
  (`add_contract_signers`) — reusable for any future claim in this
  family instead of trusting the SQLite-locking prose reasoning alone.
- When stress-testing with a fabricated `AuthContext(user_id=1, ...)`
  that doesn't correspond to a real row, watch for `FOREIGN KEY
  constraint failed` on the *audit log* write (not the primary table) —
  create a real user via `AuthService.create_user` first, not just a
  fake `user_id` int, or every worker will silently fail for an unrelated
  reason and you'll misread "0 collisions" as a pass when it's actually
  "0 successful inserts."
