---
name: new10-sigterm-handler-new40-mischaracterization
description: NEW-10 SIGTERM handler review — code/tests approved, but NEW-40's write-up falsely claims SIGINT has the same uncovered gap at the REPL input() wait when it doesn't
metadata:
  type: project
---

Reviewed NEW-10 (main.py, uncommitted at review time): added `import signal`,
a module-level `_sigterm_handler(signum, frame): raise SystemExit(128+signum)`,
and `signal.signal(signal.SIGTERM, _sigterm_handler)` as the literal first
statement in `main()`. Diff is purely additive (`+` lines only) — independently
confirmed `shutdown()` and SIGINT handling genuinely untouched via `git diff --stat`
showing only insertions. All 4 cited `except (KeyboardInterrupt, SystemExit):`
guards around `loader.load_primary()` verified present and unmodified via
`grep -n "except (KeyboardInterrupt, SystemExit)" main.py` (lines 1272, 1540,
1552, 1577). `core/daemon.py`'s `Daemon.__init__` override claim checked
directly: `get_planner()` (line 431) runs before `signal.signal(SIGTERM, ...)`
(line 443), and `get_planner()` → `Planner.__init__` → `get_state_store()` only,
no subprocess/model-load side effect — claim holds. 3 new tests are real
(not tautological): one exercises `main()` itself via `--version`'s early
`sys.exit(0)` to prove handler installation *placement* (before any branch),
not just presence. Independently re-verified the raise-on-SIGTERM mechanism
with a live `kill -TERM` against a standalone tracked-PID script — got
`CAUGHT SystemExit 143` as claimed.

**The one real bug found:** NEW-40 (and the `_sigterm_handler` docstring)
claims the REPL's steady-state `input()` wait (~main.py:1361,
`except (KeyboardInterrupt, EOFError):`) is uncovered "same as SIGINT already
does today." This is **factually wrong** — read main.py:1362-1366 directly:
that except clause DOES catch `KeyboardInterrupt` and DOES call `shutdown()`
(session save + llama-server PID cleanup) before `break`. SIGINT is fully
handled at that site today; SIGTERM (raised as `SystemExit`, not in the
caught tuple) is NOT, and propagates uncaught all the way to interpreter
exit (confirmed no try/except wraps the `repl()` call in `main()`, and no
`if __name__` guard either). So the real-world common case — `kill -TERM`
sent to an idle interactive session with the model already loaded — leaves
the llama-server child unreaped by this fix, while Ctrl-C at the exact same
moment cleans it up. That's an asymmetry NEW-10/NEW-40 doesn't accurately
describe, and it directly touches CLAUDE.md rule 2/3 territory (RAM
discipline / no bare-pkill orphans) even though it doesn't violate either
rule directly (no bare pkill was added; it's an omission, not a new bad
pattern). The gap itself was legitimately out of scope (task said don't
touch existing try/except structure) and is honestly logged as a gap — but
the *characterization* of its severity in NEW-40's "Impact if confirmed"
section needs correcting per CLAUDE.md rule 6, since "same net effect as
SIGINT" is not true at this specific site and probably understates urgency
for a likely-fast follow-up (trivial fix: add `SystemExit` to the tuple at
line 1362, mirroring 4 other sites — no restructuring needed).

**Verdict:** Approved for the NEW-10 diff itself (main.py + test file) — no
blocking bug in the shipped code. Required before commit: correct NEW_ISSUES.md's
NEW-40 entry to state accurately that SIGINT already gets `shutdown()` at the
`input()` wait (main.py:1362-1366) while SIGTERM does not — this is a real
asymmetry, not equivalent uncovered behavior, and per CLAUDE.md rule 6 the
record needs to reflect that rather than the current "same as SIGINT" framing.

Lesson for future reviews: when an implementer's gap-analysis doc claims two
signal paths "behave the same," independently read the actual except clause
at the cited line — don't trust the docstring's characterization of
existing code, even when the line number and general shape check out.
