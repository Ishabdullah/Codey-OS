---
name: test_resource_bus_aging_flaky_under_load
description: tests/test_resource_bus.py::test_poll_queue_ordering_and_aging is flaky under full-suite load, unrelated to CRM/B8.3 diffs — don't panic-reject on it alone
metadata:
  type: project
---

During B8.3 round-2 review (2026-09-17), ran the full suite twice back to
back (two background jobs both launched from the same session, unintentional
duplicate). First run: `2122 passed, 1 skipped, 374.98s`. Second run,
~1 minute later, same tree, no code changes between runs: `1 failed, 2121
passed, 1 skipped, 327.31s` — the failure was
`tests/test_resource_bus.py::test_poll_queue_ordering_and_aging`:
```
assert queue[0].requester_id == "req1"
AssertionError: assert 'req2' == 'req1'
```

Confirmed this is **pre-existing test flakiness, not a regression**:
- `git diff --stat -- tests/test_resource_bus.py core/resource_bus.py`
  is empty — neither file is touched by the B8.3 diff (CRM/leads/
  opportunities only).
- Re-ran the single test in isolation 3x back to back: passed every time
  (`0.33s`, `1.23s`, `1.11s`).

Root cause (not fully investigated, but consistent with the symptom): the
test backdates one request's `created_at` via a direct SQL UPDATE to
simulate a 30s-old request for an "aging bonus" priority calculation
(`base 50 + 30 = 80` vs `base 75 + 0 = 75`), and compares two
narrowly-separated priority scores. Under full-suite load (5-6 min run,
CPU contention from ~2100 other tests), the actual elapsed wall-clock time
between the two `request_resource()` calls can be enough to shift the
computed aging bonus and flip the comparison — a classic wall-clock-based
test made flaky by system load, not a logic bug in the aging algorithm
itself.

**Pattern for future reviews:** if a full-suite run shows a failure in a
file completely untouched by the diff under review, don't treat it as
disqualifying without first (1) confirming via `git diff --stat` that the
failing file/module is genuinely untouched, and (2) re-running just that
test in isolation a few times. A single anomalous full-suite failure in
an unrelated wall-clock-sensitive test is not grounds to walk back an
otherwise-verified APPROVED — but it is grounds to say so explicitly
rather than silently re-running until you get the "clean" number (that
would be cherry-picking evidence, the opposite of what verification is
for). Worth flagging to the coordinator as a separate, out-of-scope
finding (`NEW-###`, rule 8) if it recurs.

See also [Sandbox proxy test artifact](../../../.claude/agent-memory/code-reviewer/sandbox_http_proxy_urllib_405_env_artifact.md) —
a second, different class of "full suite doesn't reproduce" environment
gotcha in this sandbox.
