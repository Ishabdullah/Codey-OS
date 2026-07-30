---
name: working-tree-cross-round-bleed
description: Codey-OS working tree can carry unstaged, unreviewed changes from a prior round when a new sub-task's diff is submitted for review
metadata:
  type: project
---

Observed 2026-07-29 (Round 2 / C-2 sub-task 1 GUI-bind review): when asked
to review "just" a one-line gui/server.py default-host change, `git status`
showed six other modified files (NEW_ISSUES.md, PROJECT_LOG.md,
PROJECT_PLAN.md, core/daemon.py, prompts/layered_prompt.py,
prompts/system_prompt.py) still sitting uncommitted from a Round 1
follow-up (H-4 self-race fix, C-1 short-QA-prompt fix) that PROJECT_LOG.md
already describes as done and live-verified, but that was never actually
committed as its own reviewed commit.

**Why this matters:** a reviewer asked to approve "sub-task 1 of 3,
submitted in isolation" must not assume the working tree only contains
that sub-task's diff. If the implementer runs `git add -A` or
`git commit -a`, unrelated (and, in this case, previously-unreviewed as a
standalone commit) changes to a process-lifecycle file (`core/daemon.py`)
would get bundled into a commit that was supposedly scoped to a GUI-bind
fix. `core/daemon.py` changes fall under CLAUDE.md rule 4 (process
lifecycle) and need their own explicit review — silently riding along in
someone else's commit skips that gate.

**How to apply:** Always run `git status` before approving, even when the
task description says the diff is small/isolated. If the working tree has
more modified files than the described change touches, call it out
explicitly and tell the implementer to stage only the files under review
(`git add <specific file>`, not `-A`/`-a`) — do not let scope creep into
the commit even if the other pending changes look individually fine.
