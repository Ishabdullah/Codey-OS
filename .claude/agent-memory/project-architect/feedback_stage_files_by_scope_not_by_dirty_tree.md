---
name: feedback_stage_files_by_scope_not_by_dirty_tree
description: when committing a scoped round on a branch that already has other in-progress uncommitted work, git add only the files that round actually read/touched — never everything modified
metadata:
  type: feedback
---

Self-corrected finding (NEW-151, 2026-08-13), not a direct user
correction, but a strong-enough lesson to keep: when staging a commit
for a scoped task, `git add` the exact files that task's own scoping
read and edited — never every file `git status` shows as modified,
even when the rest of the working tree is legitimate, already-in-flight
work from the same overall effort (e.g. "7.4a/7.4b work in progress").

**Why:** [[project_new102_bug002_config_live_read_fix]]'s commit
(`5687dcf`) was supposed to be a config-only fix (three functions in
`utils/config.py`/`core/memory_v2.py`, three call sites, one `main.py`
guard). It was staged with every modified file in the tree instead,
which silently carried two already-implemented process-lifecycle
changes (`core/daemon.py`, `core/embed_server.py`/`core/inference.py`)
into the commit — both explicitly marked "Mandatory `code-reviewer`
pass" in `TODO.md`'s own text for those sub-tasks, neither of which had
happened. CLAUDE.md rule 4 applies per-file/per-change, not per-round —
"this round's intent was config-only" does not exempt files that
happened to ride along in the same `git add`. The commit message and the
PROJECT_LOG.md entry both then (falsely) asserted "this round does not
touch process-lifecycle," compounding the problem — a claim that was
true of the round's own work but false of the commit as actually made.

**How to apply:** before every `git add`/`git commit` in this repo,
explicitly list the files by name (never `git add -A`, already a
standing rule per [[project_rename_grep_pattern_gaps]]) AND cross-check
that list against the files this round's own scoping actually read or
edited — not against `git status`'s full modified list. If other
in-progress work is sitting uncommitted in the same tree (common here,
per this project's habit of leaving multi-sub-task rounds uncommitted
mid-work), either commit that other work separately with its own
message reflecting what it actually contains and its own review status,
or explicitly flag to the user that a combined commit is intended and
why, before doing it. When in doubt, `git status --porcelain` right
before staging and read every line against this round's task
description, not just the files you personally opened.
