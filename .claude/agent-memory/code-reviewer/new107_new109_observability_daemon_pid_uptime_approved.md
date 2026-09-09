---
name: new107_new109_observability_daemon_pid_uptime_approved
description: NEW-107/NEW-109 core/observability.py daemon_pid/uptime PID-file fix + cpu/memory scope-label reversal — APPROVED
metadata:
  type: project
---

Reviewed core/observability.py + tests/test_new107_new109_observability_daemon_pid_uptime.py
diff (2026-09-09 round). **APPROVED.**

## What was verified, not just trusted

- The implementer's claimed reversal (don't re-point cpu_usage/memory_usage
  at system-wide reads; instead label scope) rests on two citations —
  `ccos/plugins/system/observability/observability.py`'s module docstring
  and `core/resource_gate.py`'s "Signal source 1" comment. Both read
  verbatim and genuinely assert the process-vs-system split is deliberate,
  not the implementer's own interpretation dressed up as a citation.
- `ccos/plugins/system/observability/test.py::test_memory_usage_has_real_data`
  really does pin `{rss_mb, vms_mb}` with `rss_mb > 0` — a re-point to
  system-wide figures would break it. Genuine constraint, not an excuse.
- Confirmed the `"scope": "process"` label actually reaches the user:
  `main.py --status` does `json.dumps(payload, ...)` raw — no template
  stripping keys — so the label is visible in the real CLI output, not
  just internal metadata. The original NEW-109 user-facing confusion is
  reasonably addressed (label + pre-existing separate `"resources"` key
  with true system-wide figures), not just half-fixed.
- `daemon_pid`'s `os.kill(pid, 0)` → `PermissionError` → treat as "alive"
  genuinely mirrors `core.daemon.check_pid_file()`: that function doesn't
  explicitly catch PermissionError in its inner except — it propagates to
  the OUTER `except (IOError, OSError): return True` (PermissionError is
  an OSError subclass), so check_pid_file() also treats it as "running".
  Accurate mirroring, confirmed by reading both code paths, not asserted.
- Verified `core/daemon.py`'s actual ordering: `Daemon.run()` calls
  `write_pid_file()` at line 2155 BEFORE `asyncio.run(self._main_loop())`,
  and `_main_loop()` sets `daemon_started_at` at line 1091 — so the
  "PID file written first, daemon_started_at recorded later" claim
  backing the narrower startup-window gate is real, not assumed.
- The flagged residual (get_full_status() calls `daemon_pid` 3x with no
  snapshotting: direct "pid" key + inside `uptime` + inside
  `health`→`uptime`) is accurately described — confirmed by reading all
  three call sites — and reasonably left out of scope.
- Test-file isolation fixture (`_isolated_daemon_started_at`, save/yield/
  finally-restore around the REAL `~/.codeyOS/state.db`'s
  `daemon_started_at`) was NOT just read — actively negative-controlled:
  patched a test to mutate the real value then raise mid-test, confirmed
  the finally-block still restored the original value even on failure
  (this is the specific pattern class this project has been burned by
  before — a fixture that only restores on the happy path).
- Ran the new test file directly (8/8 pass) and the full suite:
  `1545 passed, 1 skipped in 233.62s` — no regression.
- NEW-428 (ccos wrapper's now-stale `daemon_pid()` docstring) is correctly
  logged as a separate out-of-scope finding, not silently fixed or dropped
  — matches CLAUDE.md rule 8.

## Bug-pattern note for future reviews

This is a good example of a "reversal" claim that survived independent
verification — worth remembering the verification recipe used here for
similar future claims: (1) read the cited source verbatim, don't trust a
paraphrase in the ledger; (2) find the pinned test and confirm it would
actually break under the naive fix, not just plausibly might; (3) trace
whether the "fix" (a label/docstring) actually reaches the user-facing
surface the original bug was about, not just internal metadata; (4)
negative-control any "restores on failure" fixture claim by forcing a
mid-test exception, not just reading the `finally` block and assuming it
works.
