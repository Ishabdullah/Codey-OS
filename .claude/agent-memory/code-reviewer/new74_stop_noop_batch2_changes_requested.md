---
name: new74-stop-noop-batch2-changes-requested
description: NEW-74 LlamaServer.stop() bool-return + adopted-state warning fix, daemon/process-lifecycle ledger closeout sub-batch 2 — code correct, one doc-accuracy gap
metadata:
  type: project
---

Reviewed uncommitted diff: `core/loader_v2.py`, `NEW_ISSUES.md`,
`tests/test_new74_adopted_stop_noop.py` — sub-batch 2 of the
daemon/process-lifecycle ledger closeout (batch 1 was
[[new409_new70_daemon_lifecycle_batch1_approved]]).

**Code correctness — verified real, not just claimed.** Read the full
`LlamaServer.stop()` body line-by-line (`core/loader_v2.py:812-905`):
- `self.process is None` branch splits correctly on `self._started`:
  adopted (`_started=True`) warns + returns `False` and *leaves
  `_started` untouched* (correct — this instance doesn't actually know
  the adopted server's true state, so it must not claim otherwise);
  never-started (`_started=False`) returns `False` silently, no warning
  — matches the ledger's own description of "quiet" vs "signalled" no-op.
- Genuine-spawn path uses `try/except Exception/else/finally`:
  `stopped_cleanly` is only set `True` in the `else` clause, i.e. only
  when the `try` block ran to completion with zero exceptions escaping
  it. Any exception (including one that escapes the *nested*
  `TimeoutExpired`-handler's own inner `try/except Exception:
  self.process.kill()` fallback) lands in the outer `except`, sets
  `stopped_cleanly = False`, logs via `warning()` (this project has a
  track record of `except Exception: pass` around
  safety-relevant code — this is a real, correctly-placed exception log,
  not a swallow). `finally` always resets `self.process`/`self._started`
  bookkeeping and unlinks the PID file regardless of outcome, matching
  pre-fix behavior for that part. This is a real fix of the exact bug
  shape the implementer's ledger note claims to have self-caught (a
  same-round regression of NEW-74's own "dishonest True" pattern) — not
  present in the committed diff.
- Grepped every `.stop()` call site on a `LlamaServer`/`self._server`
  instance across `core/loader_v2.py` (`:803`, `:1558` — the latter
  already gated on `self._server.process is not None` so never even
  reaches the adopted branch —, `:1666` in `ModelLoader.unload()`) and
  `core/daemon.py:1326` (confirmed unrelated — `self.server` there is a
  `DaemonServer`, not `LlamaServer`). None of the four inspect the
  return value; adding a real `bool` where `None` was implicitly
  returned before is additive and cannot change any caller's behavior
  today. `ModelLoader.unload()` still unconditionally sets `self._loaded
  = False` after `stop()` regardless of return value — confirmed this is
  the deliberately-not-fixed half of NEW-74 (the other half,
  `is_loaded()`/`get_status()` lying about adopted state), not a new gap
  introduced by this diff.
- Test file: all 4 tests exercise the real `LlamaServer.stop()` (no
  mocking of `stop()` itself), monkeypatch `lv.warning` (confirmed
  `warning` is a real module-level name via `from utils.logger import
  ... warning` at `loader_v2.py:31`, so the patch actually intercepts).
  Mentally replayed all 4 against the pre-fix method body (which had no
  `return` statement at all, implicitly returning `None`, and silently
  discarded exceptions with `except Exception as e: ... # e never
  logged`): every test's `result is False`/`result is True` assertion
  would fail against `None`, and the exception-path test's
  `len(warnings) == 1` assertion would fail against the pre-fix code's
  total silence on that path — real regression tests, not tautologies.

**Rule-3 judgment call (log-and-warn, don't kill an adopted PID):
agree.** The alternative (granting `stop()` new authority to
`os.kill()`/`os.killpg()` a PID this instance never spawned, based only
on a health-check-confirmed identity) is exactly the shape of decision
CLAUDE.md rule 4 says must not be made unilaterally inside a
same-sized-as-everything-else sub-batch — and the existing
`_kill_single_pid_term_then_kill()` precedent in this same file (Option
C, NEW-145/149/155) shows this project already has a considered,
separately-reviewed pattern for "kill a positively-identified-but-not-
spawned PID safely" when it decides to do that at all. Correctly left
as an open, explicitly-flagged design question rather than folded into
this fix. The orphaned-adopted-process-holds-RAM-forever concern is
real but pre-existing (it existed before this diff too — `stop()` was
*already* incapable of touching an adopted server, just silently
instead of loudly) — this fix does not create it, it makes it visible
via the warning log, which is a strict improvement.

**One doc-accuracy gap found — CHANGES REQUESTED (doc-only).** The
`NEW_ISSUES.md` resolution note says "Full suite: 1505 passed, 1
skipped (pre-fix baseline; re-run after the exception-path correction
below also passed the three targeted loader suites, 60/60)." I
independently ran `python -m pytest tests/ -q` against the actual
current diff and got the literal verbatim: `1506 passed, 1 skipped in
262.49s`. The ledger's own number is off by one and, worse, the note's
own wording concedes the *full* suite was never re-run after the
exception-path fix that the same paragraph says was necessary — only
"three targeted loader suites, 60/60" were. That's a real instance of
this project's own rule 5 ("verification means real, verbatim output —
never a paraphrase") being under-satisfied in the note itself: the
number attached to "Full suite" is a stale pre-fix count, not the
actual current-code result, even though the actual current-code result
(1506 passed, 1 skipped, confirmed by me) is fine. Fix: update the
ledger line to the correct, currently-verified `1506 passed, 1 skipped`
figure and drop or clarify the "(pre-fix baseline...)" qualifier so it
doesn't read as if the full suite was never re-run against the final
diff. This is the same doc-claim-vs-code-state gap pattern as
[[new357_wait_for_timeout_correction_changes_requested]] and
[[t8a_daemon_dedup_docstring_overclaim]] — narrow, single-round, does
not require touching `core/loader_v2.py` or the test file at all.

Verdict: **CHANGES REQUESTED (doc-only)** — `core/loader_v2.py` and
`tests/test_new74_adopted_stop_noop.py` are both correct and approved
as-is; only the `NEW_ISSUES.md` resolution note's test-count claim needs
correcting before commit, per this project's rule-5 standard for
verbatim-verified claims.
