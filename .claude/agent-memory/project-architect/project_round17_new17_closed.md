---
name: project-round17-new17-closed
description: Round 17 (NEW-17) git auto-commit scope-bleed fix closed out in docs, commit c23003d
metadata:
  type: project
---

Round 17 (NEW-17) — `core/agent.py`'s `check_git_and_offer_commit()` was
scoping its "offer to commit" prompt to ALL working-tree changes (via
`git_commit()`'s default `git add -A`), not just the current turn's
edit. Fixed in commit `f4f51fa` by adding `git_status_paths()`/
`git_commit_paths()` to `core/githelper.py` (scoped `git add -- <paths>`
/ `git commit -- <paths>`, mirroring `core/checkpoint.py`'s pattern) and
threading the already-existing per-turn `files_touched` list into the
commit-offer flow. `git_commit()`/`git_status()` themselves untouched.

Code-reviewer's verification was notably rigorous for this class of
change: independently traced `files_touched` to confirm it's genuine
per-turn local state, then ran its OWN adversarial scratch-repo test —
pre-staging an unrelated file before calling the new logic — and
confirmed the trailing `--` pathspec on `git commit` itself (not just
`git add`) is load-bearing, since it excluded the pre-staged file from
the resulting commit. Assessed as sufficient without a live model
session, since this test reproduces the exact real-world scope-bleed
scenario NEW-17 described.

Docs closeout commit `c23003d`: PROJECT_LOG.md top entry, PROJECT_PLAN.md
Round 17 section marked code complete/reviewer-approved, NEW-17 marked
Resolved in NEW_ISSUES.md. The reviewer's one Suggestion (`files_touched`
slightly over-includes paths from any tool call with a `path` arg, e.g.
`read_file`, not strictly write/patch tools) was judged too minor for a
new NEW-2x entry and recorded instead as an accepted-risk footnote on
NEW-17's own entry — harmless since the scoped git functions no-op on
unchanged files.

**Why:** documents precedent for judgment calls on Suggestion-severity
findings — footnote-on-existing-issue vs. new tracked issue — and shows
this project's pattern of the code-reviewer running its own independent
adversarial tests rather than just re-checking the implementer's tests.

**How to apply:** remaining open items after this round are NEW-7
(partially characterized), NEW-9 (deprioritized), NEW-18
(swap-thrashing recurrence, unscoped), NEW-19 (PATCH_FAILED design
question, unscoped), and the two earlier-deferred NEW-12 items
(cross-process port lock, planner auto-launcher). See
[[project_round16_new16_closed]] for the prior round's pattern this one
followed.
