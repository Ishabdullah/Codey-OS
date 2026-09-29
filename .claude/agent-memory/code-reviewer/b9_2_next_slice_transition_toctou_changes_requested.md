---
name: b9_2_next_slice_transition_toctou_changes_requested
description: B9.2 next slice (claim/unclaim/reassign/transition()/accept-Contract invariant, 2026-09-29) — CHANGES REQUESTED, found a live-reproduced TOCTOU/no-CAS race in transition()
metadata:
  type: project
---

Round: B9.2's "next slice" on `restoricon_core/services/estimate_service.py`
(claim()/unclaim()/reassign(), the transition() state machine, the accept ->
Contract invariant in record_decision()). Verdict: **CHANGES REQUESTED**.

**Critical, live-reproduced**: `transition()` reads `row`/`old_status`
(and, for `send`, `version_id`) via an unguarded pre-read *before*
`BEGIN IMMEDIATE`, then — unlike `claim()`/`unclaim()`/`reassign()` in the
exact same diff, which correctly use `UPDATE ... WHERE <old-value>` +
rowcount-based conflict detection — its own final state-changing statement
is a **blind, unconditional** `UPDATE estimates SET workflow_status = ? ...
WHERE id = ?` with no `AND workflow_status = ?` guard. Reproduced live
(scratchpad `repro_transition_race.py`): a real `SENT` transition (creates
a live share link on a locked version) followed by a stale writer's exact
`UPDATE` SQL silently produces `CANCELLED` while the `SENT` transition's
share-link row is still live — no conflict raised, no rowcount check
possible since rowcount is always 1 against `WHERE id = ?`. `record_decision()`
in the *same file* gets this right (reads `version_row`/`estimate_row`
*inside* the `BEGIN IMMEDIATE` block). The fix: either re-read state inside
the transaction (matching `record_decision()`'s own convention) or add
`AND workflow_status = ?` to the final UPDATE and raise a conflict error on
rowcount==0, matching this round's own `claim()`/`unclaim()` pattern.

**Other findings, all real, none individually blocking but bundled into
CHANGES REQUESTED alongside the Critical above**:
- `create()`'s `internal_review_required` is pinned from the **creator's**
  `requires_estimate_approval` flag. `codey_estimator_service.md` §1.5's
  transitions table (older text) says the **assignee's** flag gates
  `DRAFT -> SENT`; §9 item 5 (newer, dated 2026-09-27, explicitly "binding")
  names the creator's flag. This is a genuine spec-internal contradiction,
  not obviously the implementer's error — advisor's read (favor recency/
  authority of §9) is reasonable, but it needs to be logged to
  `NEW_ISSUES.md` for Ish to resolve explicitly, not left implicit.
- Zero test coverage for the actual human-facing hard rule (a human user
  with `requires_estimate_approval=1`) — every gate test only exercises the
  `actor.actor_type == "agent"` OR-branch. The more central §9-item-2 "HARD
  RULE, no override" policy is untested.
- `NEW-711`'s disclosure ("stops being fine the moment any other code path
  needs an independent contract_number") is inaccurate — grep confirmed
  `routes.py:1397` (`Contract(**json_body)`) already lets any
  `PERM_WRITE_CONTRACTS` holder set an arbitrary client-supplied
  `contract_number` *today*, predating this round. The round's own
  regression test (`test_accepted_decision_contract_creation_failure_rolls_back...`)
  literally simulates this exact collision. Severity is latent only because
  `record_decision()` isn't reachable from any route yet (B9.3 deferred,
  confirmed via grep) — becomes live the moment B9.3 ships. Rule 6: correct
  the record now.
- The disclosed "double-accept" limitation in `NEW-705`/the docstring
  describes the trigger path narrower than reality: it says "after
  `changes_requested` -> `revise()` -> re-send -> re-accept", but `revise()`
  (pre-existing, unchanged this round) has no gate on `workflow_status` at
  all — only `is_locked=1`, which an `ACCEPTED` estimate's current version
  also satisfies. So `revise()` is reachable directly from `ACCEPTED`
  (no `changes_requested` required), reopening a contract-linked estimate
  for full re-pricing while `contract_id`/`accepted_at` stay stale. The
  round's own new regression test for this
  (`test_accepted_decision_reaccept_after_revise_relinks_existing_contract`)
  actually exercises exactly this narrower ACCEPTED->revise()->re-accept
  path (no `changes_requested` step), i.e. the test's own path already
  proves the broader claim — but the prose describing it undersells how
  easily reachable it is.
- "1398 passed, 1 pre-existing deselected" (a claimed socket-bind
  PermissionError env failure, named test
  `test_api_new528_valid_integer_body_fields_still_work`) did not
  reproduce: full suite ran clean, 1399 passed / 0 failed / 0 deselected,
  and the named test alone also passes standalone. Not a functional issue
  (my run is strictly greener) but a rule-5/6 doc-accuracy correction.

Techniques that worked: comparing the round's own two patterns
(`claim()`'s CAS-guarded UPDATE vs `transition()`'s blind UPDATE) side by
side inside the *same diff* is a fast way to catch a self-inconsistency;
grepping the file for `BEGIN IMMEDIATE` line numbers first to confirm
`with conn: BEGIN IMMEDIATE` is this file's established convention (so
that pattern itself isn't the issue) narrowed the actual bug to "read
happens outside the txn, write has no CAS guard" specifically. A live
repro didn't need real threads — replicating the exact UPDATE SQL text
out-of-band after a legitimate prior transition is enough to prove no
guard exists, since SQL text doesn't lie.
