---
name: b8-7a-commission-trigger-plan-outside-try-changes-requested
description: B8.7a record_payment commission trigger — CHANGES REQUESTED round 1, plan-config fetch sat outside its own try block
metadata:
  type: project
---

2026-09-22, B8.7a (automatic Phase-1 flat commission on assessment-invoice
paid-in-full, `restoricon_core/services/crm_service.py`'s `record_payment`).
CHANGES REQUESTED round 1.

**The bug:** `plan = self.commission.get_commission_plan_config(commission_system_actor)`
was written at the same indent as the `try:` immediately below it, i.e.
BEFORE and OUTSIDE the try block that was supposed to make the whole
commission side-effect best-effort. The `except Exception` handler's own
comment claimed coverage of "e.g. get_commission_plan_config somehow
raising" — false, since that line was never inside the block it commented
on. Live-reproduced by monkeypatching `get_commission_plan_config` to
raise: `record_payment` raised straight out, while the invoice row was
independently confirmed already committed to `status='paid'` in the DB —
exactly the false-500-on-a-successful-payment failure this project's
best-effort/no-rollback pattern (`sign_contract`'s PDF side effect) exists
to prevent. Real triggers for that call raising in production:
`PermissionError` if `PERM_READ_TEAM_COMMISSIONS` grants are ever edited
(this project does edit grants — see NEW-565), `sqlite3.OperationalError`
on a locked DB/30s timeout, or a malformed-row `TypeError` from the
`float(...)` casts.

**How it was found:** advisor caught it from the pasted diff hunk alone
(indentation-level read), before any live test. I then independently
verified the indentation against a fresh `Read` of the file and
live-reproduced the exact failure with a monkeypatch + DB-state check.
Fix is a one-line move (`plan = ...` into the try block) plus correcting
the now-provably-false comment.

**Pattern to remember:** best-effort/no-rollback side-effect blocks (the
`try/except Exception` wrapping a business-side-effect after a payment/
signing transaction already committed) are only as good as everything
that can raise actually being INSIDE the try. Check every line between
`try:` and the first statement that can fail, not just the code the
comment claims is covered — a docstring/comment asserting "X is covered"
is a claim to verify, not evidence. Also: a monkeypatch-to-raise +
DB-state-check live repro is a cheap, decisive way to test a best-effort
contract claim (see also [[b8_6d_b_round2_atomicity_fix_approved]] for the
analogous atomicity-claim live-repro technique).

**Separate real findings from the same round, logged to NEW_ISSUES not
blocking:** hardcoded `user_id=1` system actor for
`commission_ledger_entries.created_by` (a REAL FK, unlike the two
pre-existing `user_id=1` uses at `pdf_system_actor`/`system_web_intake`
which target FK-less columns) works today only because production's
id=1 row (`ai_agent_system`) happens to still exist by insertion-order
coincidence, not by any code guarantee — no guard prevents deleting that
account, and every test's own `admin` user happens to land on id=1 too,
so no test can ever catch this class. `create_invoice` accepts an
arbitrary client-supplied `assigned_user_id` with no existence check
(confirmed live via a `999999` FK-violation test). An invoice created
already at `status='paid'` at creation time never crosses the
not-paid→paid edge and so never produces a commission (known gap of the
transition-edge-only design). NEW-600's anticipatory language ("the more
likely attribution source B8.7 will actually read from" pointing at
`Opportunity.assigned_user_id`) is now stale — confirmed B8.7a's real
trigger reads `Customer.assigned_user_id` one hop removed via
`Invoice.assigned_user_id` inheritance at `create_invoice` time, not
Opportunity's.

**Test-count claim discrepancy:** implementer claimed baseline
"2243 → 2251 (+8)"; my own reproduction of `python -m pytest -q tests/`
gave `2137 passed, 1 skipped` and `tests/test_restoricon_core/` alone gave
`939 passed` — neither matches the claimed scope/numbers. No regressions
in anything I ran (all green), so this isn't evidence of a real failure,
but per rule 5 the "2243/2251" figure itself is unverified/unreproduced
as stated — don't repeat it without re-deriving the actual scope it came
from.
