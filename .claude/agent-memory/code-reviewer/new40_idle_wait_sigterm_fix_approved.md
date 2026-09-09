---
name: new40-idle-wait-sigterm-fix-approved
description: NEW-40 idle input() wait SystemExit fix (main.py + tests/test_new40_repl_idle_wait_sigterm.py) — approved, negative-control verified
metadata:
  type: project
---

Follow-up to [[new10_sigterm_handler_new40_mischaracterization]] — that
earlier review flagged that NEW-40's write-up wrongly claimed SIGINT and
SIGTERM behaved the same at the REPL's idle `input()` wait, and specified
the exact trivial fix needed (add `SystemExit` to that one `except` tuple).
This round is exactly that fix, done as its own scoped, code-reviewer-gated
task per CLAUDE.md rule 4.

**Diff (main.py only, ~40 lines, all additive/comment):**
- `except (KeyboardInterrupt, EOFError):` → `except (KeyboardInterrupt,
  EOFError, SystemExit):` at the idle-wait site (~line 1711), with a comment
  explaining the mechanism and the exit-code tradeoff.
- `_sigterm_handler`'s docstring rewritten to mark this half fixed and the
  adjacent initial-prompt branch (~line 1684, `except KeyboardInterrupt:`,
  no `shutdown()` for SIGINT either) as deliberately still uncovered — full
  reasoning restated accurately (adding SystemExit there would absorb a
  termination signal into a continued session, worse than today's clean
  uncaught-propagation-with-signal-exit-code).

**Verified independently, not just read:**
1. Traced `break` → falls off end of `repl()` (function literally ends
   right after the `while True:` block, confirmed via `wc -l` + reading
   the tail) → implicit `None` return → `main()`'s
   `try: repl(...) finally: _remove_tui_pid_file()` (no `shutdown()`
   there) → `main()` returns → `if __name__ == "__main__": main()` →
   normal Python exit code 0. No hang, no second pass through anything.
2. Negative control: reverted just the one-line `except` tuple change
   (scripted sed-equivalent, not trusting the diff), reran the new test
   file — `test_sigterm_at_idle_input_wait_runs_shutdown` genuinely FAILS
   pre-fix (`SystemExit: 143` propagates out of `repl()` uncaught), the
   KeyboardInterrupt guard-test still passes. Restored the file and
   reconfirmed both pass post-fix. This is real coverage, not tautological
   — `mock_monitor.stop.assert_called_once()` / `mock_loader.unload
   .assert_called_once()` are genuine `shutdown()`-reached assertions, and
   `get_monitor`/`core.loader_v2.get_loader` are patched at exactly the
   names `shutdown()` actually resolves them through (module-level import
   into `main`'s namespace, confirmed via grep).
3. Cross-checked the "4 guards already exit 0 via return, same tradeoff"
   claim against all 4 site bodies (lines 1614, 1944, 1963, 1995) — every
   one does `shutdown(); return` with no re-raise, confirmed exit-0
   behavior is real, not just asserted in a comment.
4. Full test suite: `1545 passed, 1 skipped` in 218s — exact match to the
   expected count, no discrepancy despite other agents' parallel
   uncommitted work in the tree elsewhere.

**Verdict: APPROVED** for main.py + tests/test_new40_repl_idle_wait_sigterm.py.
No blocking issues. The "deliberately not touched" second site's reasoning
holds up under adversarial trace of the actual call stack, not just the
stated argument — worth re-verifying the same way (trace, don't trust) if a
future round decides to close that second half.

Lesson: when a diff cites a docstring/ledger's own prior claims (like
"exits 0, same tradeoff as the 4 guards"), those claims are cheap to
independently re-verify by reading the actual site bodies — do it rather
than accepting a comment's self-description of sibling code.
