---
name: b8_3_lead_convert_stage_analytics_round2_approved
description: B8.3 (Lead & Pipeline UX) round 2 review — APPROVED, clears rule-4's gate after all 4 round-1 items fixed and independently verified
metadata:
  type: project
---

Round 2 of B8.3 (`convert_lead_to_opportunity`, `get_stage_duration_analytics`)
got **APPROVED**, clearing rule-4's gate. All four round-1 items
(`b8_3_lead_convert_stage_analytics_changes_requested`) were genuinely
fixed, not just described as fixed:

- **customer_id writeback**: final `update_lead` call now sends
  `{"status": "converted", "customer_id": customer_id}`; new test
  re-fetches the Lead (not just Opportunity/Customer) to catch it.
- **NEW-311 docstring overreach**: narrowed to distinguish concurrent-race
  coverage (NEW-311's real scope) from sequential partial-failure-then-retry
  (NOT covered); `NEW-561` logged Suspected (correctly calibrated, not
  overclaimed as Confirmed). Write order unchanged, as instructed.
- **Bare `_parse_iso` calls**: both primary-chain sites now wrapped in
  `try/except (TypeError, ValueError)`, correctly landing in
  `chain_broken_count` not `fallback_count` — traced both branches by hand,
  confirmed with tests asserting the specific counter.
- **Partial stage_hours retraction**: rewrote to accumulate into a
  per-opportunity `pending_stage_hours` list, only merged into the shared
  `stage_hours` dict on full-chain-complete. **Live-verified by reverting
  the merge locally** (bypassing `pending_stage_hours`, writing straight to
  `stage_hours`) and confirming the new test
  (`test_stage_analytics_broken_chain_retracts_partial_stage_hours`) fails
  with a real assertion (`'new_lead' not in {'new_lead': 2.0}` → False) —
  then restored from a scratchpad backup and confirmed it passes again.
  This is the same "revert-and-check" technique the implementer described
  doing themselves; doing it myself rather than trusting the description
  is what the task explicitly asked for, and it's cheap (single `Edit` +
  targeted single-test pytest run, not a full-suite loop) — worth doing
  routinely for any test whose sole job is proving a specific fix branch
  fires, not just that the code "works".

**Full suite reproduced verbatim**: `2122 passed, 1 skipped, 69 warnings in
374.98s` — exactly round-1's `2118` + the 4 new tests, arithmetic checked
and named, not just accepted.

**New non-blocking finding surfaced by advisor, ruled out after checking
the schema (don't skip this step):** the new `except (TypeError,
ValueError)` guards don't catch `AttributeError`, which is what
`_parse_iso(None)` would actually raise (`None.replace(...)`). Initially
looked like a live gap in the item-3 fix. Checked
`restoricon_core/database.py`'s `CREATE TABLE audit_log` DDL directly —
`timestamp TEXT NOT NULL` — so `row["timestamp"]` can never be `None` for
a real row; downgraded to a Suggestion. **Pattern: when an advisor flags a
specific exception-type gap in an except clause, check the schema/type
contract of the input before rating it a blocker — a theoretically
possible but schema-excluded failure mode is a Suggestion, not a
Warning.**

Also flagged but correctly left as a pre-existing, non-blocking Suggestion
(not this round's regression): a create row with a present-but-falsy
`changed_fields.pipeline_stage.new` lands in `fallback_count` rather than
`chain_broken_count` — same corrupt-vs-absent conflation item 3 fixed for
timestamps, just via a different field, from round 1's original code.

**Environment note reused successfully:** `grep`/`find` bare binaries are
broken in this sandbox (memory: `project_termux_grep_find_alias_broken`)
— even `/data/data/com.termux/files/usr/bin/grep` invoked directly failed
with "No such file or directory" this round (worse than just a shell
alias issue — the binary itself doesn't load). Used `python3` string/regex
scans as the reliable fallback throughout, including for schema lookups.

**Full-suite background-job hygiene:** two orphaned background pytest
runs accumulated from earlier `time python -m pytest -q ... | tail -20`
attempts that got auto-backgrounded by the 120s tool timeout before I
switched to `run_in_background: true` explicitly. One of them completed
independently mid-review and delivered the exact verbatim number needed
anyway — but running the same expensive command twice unintentionally is
wasteful. **Pattern: when a command is likely to exceed 120s (a full test
suite in this repo takes ~5-6 min), start it with `run_in_background:
true` from the first attempt, not after the sandbox auto-backgrounds a
blocking call.**
