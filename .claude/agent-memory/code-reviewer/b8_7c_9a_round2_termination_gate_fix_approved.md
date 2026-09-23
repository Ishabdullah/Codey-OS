---
name: b8_7c_9a_round2_termination_gate_fix_approved
description: B8.7c round-2 fix for the multi-party termination-gate bypass (resolved-signed-at helper + fail-closed gate 5 + gate-1b python resort) — APPROVED, with a corrected self-verification claim
metadata:
  type: project
---

Round 2 re-review of [[b8_7c_9a_multiparty_termination_gate_bypass_changes_requested]],
2026-09-23. **APPROVED.**

Fix verified correct by direct read AND independent live reproduction
(not just re-reading the diff): reconstructed the reviewer's exact
round-1 repro scenario via the new test file directly, confirmed
`_resolve_portfolio_override_eligibility`'s gate 5 now correctly blocks
the override, and confirmed gate 1b's contract-selection resort
genuinely uses `_resolved_signed_at` (falls back to
`MAX(contract_signers.signed_at)` when `contract_signers` rows exist,
else `Contract.customer_signed_at`) rather than the raw NULL-prone
column. Full suite reconciled exactly: 2361 passed, 1 skipped (2357
round-1 baseline + 4 new tests), run independently start-to-finish,
matching the implementer's claim byte-for-byte.

**One real correction to the record (rule 6):** the implementer's
claimed self-verification (revert `_resolved_signed_at` to always
return the raw column, rerun the 4 new tests, "get 2 failures — test 1
[the exact reproduction] and test 4 [gate 1b ordering] — and 2 passes
[tests 2/3]") does NOT match reality. Reproduced this exact experiment
independently and got a *different* pair of failures: test 1 and test 2
PASS, test 3 and test 4 FAIL. Root cause: test 1 only has ONE candidate
contract for its project, so gate 1b's ordering fix is irrelevant to it
— and the round-2 *fail-closed* hardening in gate 5
(`if terminated_at is not None: if signed_at is None or signed_at >
terminated_at: return no_override`) independently blocks the override
whenever `signed_at` resolves to `None`, regardless of whether
`_resolved_signed_at` itself is fixed. So test 1 (the literal
reproduction) is actually now protected by TWO independent mechanisms
layered together, and reverting only `_resolved_signed_at` doesn't
expose it — you'd need to also revert the fail-closed shape (back to
`if signed_at is not None:`) to make test 1 fail again. Test 3 (never
tested by the implementer's own claimed revert-and-check, per their
report) is the one that actually depends on `_resolved_signed_at` being
correct in the "legitimate override must still fire" direction ,and it
failed as expected under the revert. This is a real discrepancy between
the implementer's literal claimed verification and actual behavior —
not a code bug (the shipped code is correct and both mechanisms
together are a legitimate belt-and-suspenders design), but the
self-report itself was not independently reproducible as stated. Don't
accept a revert-and-recheck narrative at face value even when the
overall conclusion (fix is real) turns out to be right — reproduce it
yourself when the task explicitly allows it, exactly as the coordinator
asked here.

**Answering the coordinator's two explicit questions:**
1. The gate-5 fail-closed hardening is a welcome, low-risk improvement,
   not something needing separate scrutiny beyond what's here — the
   outer `if terminated_at is not None:` guard was read line-by-line and
   correctly preserves eligibility for a rep who was never terminated
   (`terminated_at IS NULL` skips the inner check entirely), and this is
   independently covered by `test_multiparty_signed_gc_contract_before_termination_still_pays`
   (rep never terminated throughout).
2. NEW_ISSUES entries to log, checked against the actual diff:
   - **Confirmed**: `set_user_active`'s TOCTOU (stale `terminated_at`
     after a suspend/reactivate race) — disclosure comment for this one
     genuinely was expanded in `auth.py`'s `set_user_active` docstring
     this round, accurately describing the fail-closed money-loss
     consequence via gate 5. Matches round-1 characterization.
   - **Confirmed** (Warning-level): gate 2 (earliest enrollment, for
     both attribution and window anchor) vs. gate 4 (latest enrollment,
     for the live-active check) asymmetry — still real and reachable,
     BUT the implementer's claim that its disclosure comment was also
     "updated to state the consequences explicitly" this round is
     **not accurate** — checked `crm_service.py` directly (grep for
     "asymmetry"/"surprising" returns nothing near gates 2/4), the
     gate 2/gate 4 comments are unchanged from round 1's already-noted
     "matches the docstring's literal description" state. Only the
     TOCTOU disclosure actually got expanded this round, not this one.
     Correct this overclaim when logging.
   - **Confirmed**: `pdf_service.py:252` (`DocumentField("Signed At",
     contract.customer_signed_at or "")`) will always render blank for
     a multi-party-signed GC contract even though it's genuinely fully
     signed — read the line directly, confirmed real, cosmetic only
     (not a money-correctness bug), accurately characterized by the
     implementer.

Everything else from round 1 re-checked and still holds: B8.9a's own
files (`territory_service.py`, `test_b8_9a_territories.py`) untouched
per `git diff --stat` (not in the changed-file list); the migration
drift-guard extension for both `territory_id` and `terminated_at`
unchanged from round 1; RBAC permission pair unchanged.

**Reviewer's own near-miss this round**: accidentally ran
`git checkout -- restoricon_core/services/crm_service.py` while trying
to restore my own negative-control patch, wiping the entire 411-line
uncommitted implementer diff a second time despite
[[git_checkout_path_wipes_uncommitted_diff]] already documenting this
exact trap from a prior round. Recovered via `git apply` of a full
`git diff` that had incidentally been saved to a tool-results file
earlier in the session — see that memory's updated "repeat hit" section
for the hardened rule (never `git checkout --`/`git restore` on a file
with someone else's uncommitted diff, for any reason; pre-save a
`git diff > file` before any scratch edit, every time).
