---
name: new55-agent-input-eof-fix-ki-scope-creep
description: NEW-55 core/agent.py EOFError fix bundled an unrequested KeyboardInterrupt clause with inverted semantics vs the file's own precedent — requested changes
metadata:
  type: project
---

Reviewed a fix for NEW-55 (`core/agent.py` ~line 1677: unguarded `input()`
after the low-confidence gate's `ask_confirm()`, crashing headless/no-TTY
tasks with `EOFError`). The `except EOFError: guidance = ""` clause is
correct and well-scoped to NEW-55 as filed (NEW_ISSUES.md's NEW-55 entry
is EOF-only — no mention of Ctrl-C/KeyboardInterrupt at all).

The implementer bundled in a second clause, `except KeyboardInterrupt:
guidance = ""`, justified by citing the file's own existing pattern at
line 1278 (`except (EOFError, KeyboardInterrupt): ans = "n"`) as
precedent. That citation is backwards: line 1278's KeyboardInterrupt
maps to "n" → `return "[Cancelled]", history` (abort the task). The new
clause maps KeyboardInterrupt to `guidance = ""` → `continue` (swallow
the interrupt, keep looping up to `max_steps` times). Same surface
syntax, opposite semantics — a citation that looks like it supports the
change while actually contradicting it.

Concretely verified (don't re-trust a "mirrors line X" claim without
reading line X's control flow): every call site that reaches
`run_agent` in `main.py` (one-shot mode ~1314, initial-prompt path
~1335, `/lint` fix-offer ~949, `/voice listen` ~984) already wraps the
call in `except KeyboardInterrupt` that cleanly aborts (`pass`, prints
"Interrupted.", or calls `shutdown()`). So pre-fix, Ctrl-C at this exact
`input()` propagated up and correctly aborted the task — working,
correct behavior. The added clause intercepts it earlier and downgrades
an abort into a silent "retry with no guidance," making the task harder
to escape for an interactive user, exactly the kind of regression this
project's process-lifecycle-adjacent code review exists to catch (see
[[gui_c2_remediation_sequence]] for the general pattern of "later part
doesn't actually fix earlier gap").

**Right fix:** delete the `except KeyboardInterrupt` clause entirely,
restoring the exact prior behavior (uncaught KeyboardInterrupt
propagates to the existing, already-correct `main.py` handlers). Do not
convert it to `return "[Cancelled]", history` — at that call site
`history` hasn't had `user_message`/response appended yet (compare the
`tools_used` duplicate-exit path at ~1653-1655 and the orchestrator
cancel path at ~1287-1289, both append before returning); a bare
`return "[Cancelled]", history` would silently drop the current message
from history, a new bug.

**Verdict pattern:** if the KI clause is removed, the fix is EOF-only,
statically trivial, and the existing 266/68 test-suite pass is
sufficient — no live-verifier needed. If KI handling is kept for any
reason, it needs a real interactive on-device Ctrl-C repro, since
"does swallowing Ctrl-C here trap the user" is not resolvable by static
reasoning or a batch test suite.

**General lesson:** when an implementer says "mirrors existing pattern
at line N," always read line N's actual downstream effect (what does
the substituted value *do*), not just whether the except-clause tuple
looks similar. Also: rule 8 (log out-of-scope findings, don't silently
fix) applies in reverse here too — an implementer silently *adding*
scope beyond the filed issue is exactly what rule 8 is meant to prevent
on the input side.
