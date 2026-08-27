---
name: project-new224-subcontractor-task-preempted-by-concurrent-session
description: NEW-224 subcontractor-recruiter.js unblocking task was assigned to this session but a concurrent session completed, reviewed, and committed the identical (and further) work mid-turn — check git log before declaring findings/starting duplicate design work
metadata:
  type: project
---

On 2026-08-27, this session was assigned to scope (not implement)
`CRMService.update_subcontractor()` — a general partial-update method to
unblock `subcontractor-recruiter.js`'s write-through, per `NEW-224`. Independently
derived the full spec (22-field allow-list, unknown/None-key rejection,
qualification_data shallow-merge vs. secondary_trades replace,
transaction-scoped SELECT+UPDATE, unconditional audit log, `NEW-234`
through `NEW-237` findings) and began writing it into
`CODEY_MASTER_PLAN.md` §6.4 and `NEW_ISSUES.md`.

Partway through, a **second, concurrent session** (same repo, same
working tree) had already carried the task all the way through
implementation, code-reviewer approval, a further follow-on round
(`find_subcontractor()`, `NEW-241`–`NEW-246`), and a cleanup round —
and committed all of it to `main` (commits `c29e037`..`20af231`),
overwriting this session's in-progress `CODEY_MASTER_PLAN.md`/
`NEW_ISSUES.md` edits. The committed implementation matched this
session's independently-derived spec almost verbatim (same allow-list
fields, same rejection rules, same merge/replace split) — strong
evidence the design reasoning was sound, but the parallel dispatch
wasted a full session's work.

**Why:** this project's orchestration occasionally dispatches the same
task to more than one agent session concurrently (or a very fast
worker session runs far ahead while a slower one is still scoping).
`git status`/`git diff HEAD` mid-task can go from showing local edits
to showing "nothing to commit, working tree clean" if a concurrent
commit lands and the working tree gets fast-forwarded/reset under you.

**How to apply:** before starting substantive design/scoping work on a
task that sounds like it might already be "in flight" (references an
existing open finding like `NEW-224`, `NEW-nnn`), run `git log --oneline
-15` and grep the target finding ID in recent commit messages first. If
mid-task an `Edit` unexpectedly fails to match text you just wrote (old
content not found), don't assume a stale read — check `git log`/`git
status` immediately; it may mean a concurrent session already committed
over the state you were editing. In that case, verify the committed
work actually satisfies the task (re-derive independently and diff
against what landed, as done here) rather than re-applying your own
now-redundant edit, and report the collision to the user rather than
silently discarding your analysis.

See also [[project_new224_subcontractor_scoping]] if a scoping-detail
memory is ever added for the design itself — not created here since the
work was already fully captured in `CODEY_MASTER_PLAN.md` §6.4 and
`NEW_ISSUES.md` by the winning session.
