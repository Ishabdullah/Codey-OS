---
name: b8_1_properties_commissions_round2_approved
description: B8.1 commission ledger round 2 — all 3 blocking items fixed and independently re-verified (partial unique index TOCTOU fix, status-filter exclusion, write-permission split) — APPROVED, clears rule-4 gate
metadata:
  type: project
---

Round 2 of [[b8_1_properties_commissions_changes_requested]], reviewed
2026-09-17. All three round-1 blocking items were fixed and each was
re-verified independently rather than taken on the implementer's word:

1. Double-reversal pre-check SELECT added inside `reverse_commission`.
2. TOCTOU-safety via `CREATE UNIQUE INDEX ... WHERE reversed_entry_id IS
   NOT NULL` (partial unique index), with `reverse_commission`'s INSERT
   wrapped in `try/except sqlite3.IntegrityError`, narrowed to the exact
   substring `"commission_ledger_entries.reversed_entry_id"`. Verified
   the substring against SQLite's real error text via a live repro
   (`'UNIQUE constraint failed: t.reversed_entry_id'` format), then went
   further and forced the real INSERT/except code path to fire (by
   proxying the connection to make the pre-check SELECT return None,
   simulating the actual race window) rather than trusting that a format
   match implies the except clause works end-to-end — confirmed it
   converts to the domain ValueError correctly. Also checked the live
   production DB directly (`~/.codeyOS/restoricon.db`) for a
   pre-existing `commission_ledger_entries` table before trusting the
   "safe to add this unique index" claim — none exists.
3. `list_commissions(status=..., include_reversed=False)` excludes rows
   that are the *target* of a reversal via a `NOT IN (SELECT
   reversed_entry_id ... WHERE reversed_entry_id IS NOT NULL)` subquery
   — checked the `IS NOT NULL` guard is present (without it, `NOT IN`
   against any NULL makes the whole filtered query silently return zero
   rows for everyone — the classic SQL NULL-in-NOT-IN trap).

New pattern from this round, worth carrying forward: **when a service
adds a new race-safety try/except around a raw driver exception (e.g.
`sqlite3.IntegrityError`) narrowed by a substring/message match, check
whether the project's own test suite actually exercises the except
clause's *positive* path (the exception actually gets raised and
caught) rather than only a pre-check path that never reaches the
except. Here the new tests proved the pre-check path and proved
*unrelated* IntegrityErrors propagate, but never exercised the real
race window itself — I closed that gap myself with a connection-proxy
repro before approving, rather than trusting "17 tests pass" as
sufficient. This is the same failure class as the b8.1-round1 finding:
a green suite doesn't prove the specific invariant under test unless a
test is deliberately shaped to hit it.**

Also worth noting: `CommissionService.list_commissions`'
`_scoped_rep_filter` has the identical `if effective_uid is not None`
fail-open shape as `CRMService._scoped_assignee_filter` — an actor with
`user_id=None` and no team-read permission would see every rep's rows.
Checked this against the precedent (`list_leads` etc. use the exact
same shape) and confirmed the only `AuthContext(user_id=None, ...)`
construction site in the codebase (`migrate_aigentik.py`) uses
`role="ai_agent"`, which already holds full team-read by default — so
unreachable in practice, and not a new divergence introduced by this
diff. Non-blocking, flagged for a `NEW-###` ledger entry given the
money context rather than silently accepted.

Full suite re-run myself (not restated from implementer): `1964 passed,
1 skipped in 243.81s` — matched implementer's claim exactly this time
(contrast with round 1, where a 1-test discrepancy showed up under
identical proxy-unset conditions — always rerun, don't diff the claim
against memory of a prior run).
