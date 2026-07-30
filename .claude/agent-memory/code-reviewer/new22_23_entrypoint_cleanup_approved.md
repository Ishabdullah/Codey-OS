---
name: new22-23-entrypoint-cleanup-approved
description: Phase 3 deletion of gui/start.sh and ccos_main.py (NEW-22/NEW-23) — approved with a rule-9 docs-closeout gap noted
metadata:
  type: project
---

Reviewed and approved (2026-07-30) the deletion of `gui/start.sh` and
`ccos_main.py` plus 8 doc/script updates (README.md, docs/security.md,
docs/commands.md, codey-start comment, install.sh, QWEN.md,
CODEY_OS_MASTER_VISION.md, NEW_ISSUES.md new entries NEW-24/NEW-25).

**Independent re-verification held up.** Repo-wide grep (using the full
`/data/data/com.termux/files/usr/bin/grep` path — bare `grep` is broken
in this Termux env, see [[project_termux_grep_find_alias_broken]]) for
`start.sh` and `ccos_main` across all `.py`/`.sh`/`.md` files found zero
live exec/source/subprocess references outside historical docs
(PROJECT_PLAN.md, PROJECT_LOG.md, CHANGELOG.md, Codey-OS-audit.md) and
Claude Code's own `.claude/settings.local.json` permission allow-list
(not live code). `codey-start`, `codeyOS`, `codeydOS` never called
either deleted file — each independently reimplements the GUI-launch/
PID/trap pattern gui/start.sh had.

**Gap found, not blocking:** PROJECT_PLAN.md's Phase 3 checklist still
has `[ ]` unchecked items for `gui/start.sh` and `ccos_main.py`
(lines ~438-451) describing them as "genuine product decision for Ish"
— this round resolved that decision (delete) but PROJECT_PLAN.md/
PROJECT_LOG.md weren't updated to close them out. This project has a
recurring pattern of a separate "docs closeout" commit following the
round's code commit (see git log: "Round 12 (NEW-13) docs closeout" as
its own commit after "Round 12 (NEW-13)"), so this is consistent with
established practice, not a fabricated excuse — but flag it explicitly
each time so it doesn't get silently dropped. CLAUDE.md rule 9 requires
PROJECT_PLAN.md/PROJECT_LOG.md updated "after every completed round" —
verify the follow-up closeout commit actually happens.

**Also verified:** `codeyOS`'s pre-existing `--daemon` branch bug
(NEW-25, literal `"\$@"` outside heredoc at line 119) is isolated to
that branch only — the direct/interactive-mode branch (line 428, `"$@"`
no backslash) is correct and is what docs/commands.md's new "passes
prompt args through to main.py unfiltered" claim describes. Confirmed
by reading both branches side by side; the two are not the same code
path, so the docs claim isn't contaminated by the adjacent bug.

`install.sh`'s removed line (`gui/start.sh` chmod) was a standalone
statement, not part of a conditional — removal doesn't change control
flow. `bash -n` clean on all 4 touched shell scripts. Full test suite:
258 passed, 0 failed (`python3 -m pytest tests/ -q`).

**How to apply:** if reviewing a future "docs closeout" commit for this
same round, confirm it actually flips the `gui/start.sh`/`ccos_main.py`
checklist items to `[x]` in PROJECT_PLAN.md and adds a dated entry to
PROJECT_LOG.md — don't assume it happened just because this round's
code commit was approved.
