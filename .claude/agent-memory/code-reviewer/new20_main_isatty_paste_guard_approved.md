---
name: new20-main-isatty-paste-guard-approved
description: main.py NEW-20 fix wraps paste-detection select() loop in sys.stdin.isatty() guard — approved, live-verified with scratch harnesses + pty
metadata:
  type: project
---

Round NEW-20: `main.py`'s `repl()` paste-glue block (the `select([sys.stdin], [], [], 0.02)`
loop that concatenates fast multi-line pastes into one turn) was hanging/spinning on
non-TTY (piped/redirected) stdin, because `select()` on a non-tty stream reports
"readable" even at EOF, causing either indefinite readline("")-spin or wrong
concatenation. Fix: wrap the entire `import select` block in
`if sys.stdin.isatty():` (not `os.isatty(sys.stdin.fileno())` — the attribute
form is safer against wrapped/mocked streams and was an explicit constraint).

Verified independently (not just trusting implementer's transcript):
- Built standalone harness replicating old vs new code shape exactly (same
  `.rstrip("\n").strip()`, same 0.02 timeout, same bare `except Exception: pass`).
- `printf 'line1\nline2\nline3\n' | timeout 5 python3 harness.py old` → exit 124 (hangs, confirms bug).
- Same input against `new` mode → 3 lines processed cleanly, EOFError exit, ~0.000s.
- Built a `pty.openpty()`-based harness, wrote two lines to master fast, confirmed
  `isatty()` is True over a pty and paste-glue concatenation still fires
  (`"pasted line one pasted line two"` joined into one GOT line) — so the fix does
  not silently disable paste-detection for real TTY sessions.
- Checked `gui/start.sh` line 58 (`python main.py`, not backgrounded, not stdin-redirected)
  and `codeydOS`/`codeyOS` — none of Codey-OS's launcher scripts redirect or wrap
  main.py's stdin in a way that would make `isatty()` misreport False during normal
  interactive use.
- `git diff --stat` confirmed only `main.py`, 10 insertions/9 deletions, exactly the
  described one-line-added guard — no other structural change, no new CLI flag,
  the `except (KeyboardInterrupt, EOFError):` handler untouched.
- Full test suite: `python3 -m pytest tests/ -q` → 258 passed in 0.39s.

Verdict: approved as code-complete + scratch-harness live-verified. This is not the
same as a live-verifier pass with an actual `main.py` invocation loading a real model
in an interactive session — recommend a lightweight live-verifier check (pipe a
2-3 line input into a real `python3 main.py` invocation and confirm no hang) before
fully closing NEW-20, per CLAUDE.md rule 7 (code-complete vs live-verified distinction).
No process-lifecycle/PID/kill logic touched, so CLAUDE.md rule 4 mandatory-review
gate doesn't strictly apply, but this file still got full scrutiny per project norm.

See [[main_py_new5_keyboardinterrupt_fix_approved]] and
[[main_py_new6_keyboardinterrupt_fix_approved]] for related main.py REPL exception-handling
rounds reviewed the same way (static/harness verification, not full live session).
