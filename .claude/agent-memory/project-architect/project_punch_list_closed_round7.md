---
name: punch-list-closed-round7
description: Original 4-item punch list (NEW-3/1/5/2) resolved Round 7 (55e408c); NEW-6 also resolved Round 8 (435c120); NEW-7/8/9 remain open, NEW-9 newly discovered
metadata:
  type: project
---

As of 2026-07-30 (Round 7, commit `55e408c`), all four items of Ish's
original punch list are resolved:
- NEW-3 (GUI session-token log leak) — Resolved, commit `efe9f5c`.
- NEW-1 (pytest orphaning a real 7B llama-server) — fully live-verified.
- NEW-5 (KeyboardInterrupt during model load orphaning llama-server in
  `repl()`) — fully live-verified, **but see the Round 8 caveat below**.
- NEW-2 (silent no-op on failed patch_file after retries exhausted) —
  code complete, code-reviewer approved (not live-verified post-fix —
  the live reproduction only covered the pre-fix bug, which is what
  pinned the corrected root cause: a patch-application failure via
  `old_str=""` on a synthesized whole-function replacement, not a
  JSON-parse failure or false success claim as first hypothesized).

**Why:** this closes out the multi-round remediation effort the user
asked for; future sessions should treat these four as done unless told
otherwise, and check `NEW_ISSUES.md` for current status of what's next
rather than assuming this list is still open.

**Round 8 update (2026-07-30, commit `435c120`):** NEW-6 (the sibling
`loader.load_primary()` KeyboardInterrupt gap at `args.init`/`args.tdd`/
`args.fix`) is now also Resolved — same guard pattern as NEW-5's
`repl()` fix. live-verification found 3 of 4 site-tests clean, but 1
`--init` attempt reproduced a genuine orphan, root-caused to a
**pre-existing, shared** atfork/fork-window race in
`core/loader_v2.py`'s `subprocess.Popen()` call (CPython silently
swallows a `KeyboardInterrupt` landing during the internal `os.fork()`,
before it ever reaches any caller-level `try/except` guard) — not a
regression from Round 8's diff, and not specific to the three new
sites; it affects `repl()`'s existing NEW-5 guard too. Per CLAUDE.md
rule 6, NEW-5's record now carries an honest caveat about this residual
gap (Resolved status not downgraded — the guard genuinely works for the
vast majority of the window). Logged as a new Confirmed entry, **NEW-9**,
needing its own dedicated scoping/fix pass — not yet queued for
implementation, queue position relative to NEW-4/NEW-7 flagged as an
open question for Ish.

**How to apply:** items remain open as incidental discoveries, none of
them originally requested — don't conflate them with the closed punch
list when scoping new work:
- NEW-7: the `[Recursive]` planner path tends to synthesize whole
  duplicate functions with `old_str=""` instead of targeted patches —
  the underlying behavior NEW-2's marker fix works around but doesn't
  fix. Suspected, unscoped.
- NEW-8: `ccos/tests/test_ccos.py::test_sandbox` fails on this device,
  reproduced independently twice during Round 7's full-suite runs,
  unrelated to any Round 7 diff. Confirmed, not yet root-caused.
- NEW-9: atfork/fork-window race silently bypassing the
  KeyboardInterrupt guard pattern at all four sites (`repl()`,
  `args.init`, `args.tdd`, `args.fix`). Confirmed, root-caused, not yet
  scoped into a fix task — see `NEW_ISSUES.md` for the fix-direction
  candidates already sketched (none decided).

See `PROJECT_LOG.md`'s 2026-07-30 Round 7 and Round 8 entries and
`NEW_ISSUES.md` for full verbatim evidence.
