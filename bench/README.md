# bench/ — frozen capability benchmark (AGI audit Phase 2.1)

Purpose: the missing capability evaluator. Nothing in Codey-OS may be called an
"improvement" unless it beats the champion here with a paired test.

- `tasks/<id>/` — `prompt.txt`, `starter/` (what the agent sees), `hidden/` (grader tests, never shown), `reference/` (oracle solution).
- `verify.py` grades in a fresh temp copy; hidden tests overwrite same-named agent files.
- `lock.py` / `suite.lock` — sha256 of all task files. `runner.py` refuses to run if the suite changed. After deliberately editing tasks: `python -c "from bench.lock import write_lock; print(write_lock())"` and log why in AGI_AUDIT_LOG.md (this starts a NEW suite version; old results are not comparable).
- `agents.py` — `null_agent` (must score 0), `oracle_agent` (must score 100%), `make_codey_cli_agent` (real agent, on-device only, needs llama-server).
- `runner.py` writes an append-only JSONL ledger; `compare.py` does McNemar exact + bootstrap CI.

Sandbox-safe self-checks live in `tests/test_bench_harness.py`. Real model runs are on-device (LIVE_TEST_QUEUE.md).
Limits: 8 seed tasks is small; a single-task flip is not significant. Grow the suite before trusting small deltas (A/A test measures the gate's false-accept rate).
