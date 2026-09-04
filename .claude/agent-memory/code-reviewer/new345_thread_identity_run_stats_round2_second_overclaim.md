---
name: new345-thread-identity-run-stats-round2-second-overclaim
description: NEW-345 fix round 2 — coordinator fixed the finally-block overclaim comment but missed an identical overclaim earlier in the same method; CHANGES REQUESTED
metadata:
  type: project
---

Round 2 review of the NEW-345 fix in `core/task_executor.py`. The coordinator correctly fixed the required item from round 1 (the `finally` block's empty-`_worker_thread_id` comment, ~line 369-374, now reads "either never dispatched, or dispatched but cancelled before the callable's first line (the append) ran... honest null, not a lookup miss" — accurate, causal overclaim gone).

**But the exact same false causal claim exists a second time in the same method, unfixed**: the comment where `_worker_thread_id: list = []` is *initialized* (line ~271-275, before the `try:` block) still reads: "an empty list there correctly means 'the callable never started executing'". This is word-for-word the same overclaim my round 1 review flagged and required fixed — cancellation can land between the executor picking up the callable and the callable's first line (the `_worker_thread_id.append(...)`) actually running, so "never started executing" is false in that window; the callable *did* start, it just hadn't published its id yet.

**How this was found**: grepped the whole file for the phrase after seeing round 1's fix applied at the `finally` site, rather than trusting that fixing one occurrence meant the overclaim was gone project-wide (`grep -n "correctly means\|never started executing" core/task_executor.py` → 1 hit, at the *other* location). This is the same lesson as [[plannd_new46_47_28_iter3_onestep_delegation_approved]] ("grep whole prompt for failing-case substrings, not just the diff hunk") applied to a comment-only fix instead of a prompt/regex fix — a duplicated claim can survive a targeted single-site fix.

**Required fix**: reword the init-site comment (~line 271-275) to match the corrected finally-site wording, or better, don't restate the semantics at the init site at all — just point to the finally-block comment as the authoritative explanation, so there's only one place this claim can drift out of sync in the future.

**Verified in this round**: `_seq_before` dead variable fully deleted (grep across repo, only remaining reference is memory files). `tests/test_task_executor_telemetry.py`'s new regression test cleanup (`agent_mod._RUN_STATS_BY_THREAD.pop(thread_ids.get("A"), None)`) is genuinely inside a `try/finally` wrapping `asyncio.run(_run())` (lines 435/448) — round 1's finding #4 was based on an earlier state of the file; as currently written it's not a defect. Full suite: `1410 passed, 1 skipped in 180.73s` — matches coordinator's claim exactly. No other part of the diff changed beyond the two requested items (full diff re-read line-by-line, matches round-1-reviewed design).

Verdict: CHANGES REQUESTED, doc-only (comment wording), same class as round 1 — not ready to commit yet.
