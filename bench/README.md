# bench/ — frozen capability benchmark (AGI audit Phase 2.1)

Purpose: the missing capability evaluator. Nothing in Codey-OS may be called an
"improvement" unless it beats the champion here with a paired test.

- `tasks/<id>/` — `prompt.txt`, `starter/` (what the agent sees), `hidden/` (grader tests, never shown), `reference/` (oracle solution).
- `verify.py` grades in a fresh temp copy; hidden tests overwrite same-named agent files.
- `lock.py` / `suite.lock` (v2, two lines) — `tasks:<sha256 of bench/tasks>` and `evaluator:<sha256 of every bench/*.py except scorecard.py and power_analysis.py>`. A NEW `bench/*.py` is covered by default. `runner.py` refuses to run if either hash differs, and a legacy one-line lock fails closed. `run_suite` snapshots the tasks once, grades from the snapshot, re-hashes per task and aborts if they change mid-run; every ledger row records the `suite_hash` of the tasks actually graded and the `evaluator_hash`; `compare()` refuses to pair rows with different evaluator versions (so `gate.decide` reports "not comparable").
- **Symlinks are a lock violation:** any symlink (file, directory or dangling) anywhere under `bench/`, including `bench/tasks/**` and `__pycache__`, makes `verify_lock()` False and makes `write_lock()` raise `RuntimeError` (fail closed; `rglob` skips symlinked dirs, so a linked `.py` would otherwise be importable but unhashed). Remove the link, then relock.
- **Honest limit:** the lock detects edits that are not accompanied by a deliberate relock. `write_lock()` is self-attesting: anyone who can edit a covered file and `suite.lock` can re-attest (accepted residual, G15f Q2; no tty gate). It does not defend the verifier itself (a modified `lock.py`/`runner.py` can skip the check); detection comes from the evaluator hash in the ledger rows.
- **Hashing notes:** `evaluator_hash` length-prefixes paths and contents and covers every `*.py` at any depth under `bench/` (except `tasks/**`, `scorecard.py`, `power_analysis.py`). `suite_hash` keeps its original un-length-prefixed framing, which is ambiguous in theory (accepted residual, kept for ledger continuity; a pinned test documents it). An unchecked-hash `.pyc` shadowing a source file is not defended.
- **Relock order:** finish EVERY edit to every covered `bench/*.py` (docstrings and comments included) first, then run `python -c "from bench.lock import write_lock; print(write_lock())"` as the LAST step and commit `suite.lock` with the code. Any later edit to a covered file (including a code-review fix) breaks `run_suite` and the real-tree lock test until relocked. After deliberately editing tasks, relock and log why in AGI_AUDIT_LOG.md (a NEW suite version; old results are not comparable); after editing evaluator code the tasks hash is unchanged but ledgers from before/after are not comparable.
- `agents.py` — `null_agent` (must score 0), `oracle_agent` (must score 100%), `make_codey_cli_agent` (real agent, on-device only, needs llama-server).
- `runner.py` writes an append-only JSONL ledger; `compare.py` does McNemar exact + bootstrap CI.
- A ledger row's `passed` field is `True`/`False`/`None` -- `None` means the grading harness itself
  errored (see that row's `grading_error` field), not that the agent failed; `compare()`/`gate.py`
  exclude such rows from the comparison but report their count via `"errored"`. By default
  `gate.decide()` refuses to promote at all if `errored > 0` (`max_errored=0`), on the view that a
  comparison the evaluator partly failed on isn't a clean win regardless of the other criteria --
  this is a configurable `max_errored` override like every other gate criterion, not a hardcode.

Sandbox-safe self-checks live in `tests/test_bench_harness.py`. Real model runs are on-device (LIVE_TEST_QUEUE.md).
Limits: 8 seed tasks is small; a single-task flip is not significant. Grow the suite before trusting small deltas (A/A test measures the gate's false-accept rate).
