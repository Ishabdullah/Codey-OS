---
name: new17-git-commit-scoped-staging-approved
description: NEW-17 fix (core/githelper.py git_status_paths/git_commit_paths + core/agent.py files_touched threading) reviewed and APPROVED
metadata:
  type: project
---

Reviewed and approved: `core/githelper.py` gained `git_status_paths()`/`git_commit_paths()`
(scoped `git add -- <paths>` / `git commit -m ... -- <paths>`), and
`check_git_and_offer_commit()` in `core/agent.py` now takes `files_touched`
and uses these instead of the unscoped `git_status()`/`git_commit(add_all=True)`.
Fixes NEW-17 (post-edit commit offer scope-bleeding into unrelated dirty files).

**Why this needed care:** any change to what `git commit`/`git add` actually
stage is in the "accidental commit of unintended files" risk category this
project treats seriously (CLAUDE.md rule 3 spirit, even though this isn't
process-lifecycle code so rule 4 doesn't strictly apply).

**Key verified fact worth remembering:** the trailing `-- <paths>` on the
`git commit` call is NOT redundant with the preceding `git add -- <paths>`.
Empirically confirmed in a scratch repo: if some other file was already
staged (`git add`ed) by unrelated code *before* this function runs, a bare
`git commit -m msg` would sweep it into the commit too — the pathspec on
`git commit` itself is what excludes it. Without that trailing pathspec,
scoped `git add` alone does not guarantee a scoped commit.

**Also verified:** `files_touched` is a local list initialized fresh inside
`run_agent()` (`core/agent.py` ~line 1452, alongside `tools_used`/`error_log`)
— not module-level/session-persistent state, so no cross-turn scope-bleed
reintroduced. It's populated from `args.get("path", "")` for *every* tool
call with a path arg (not just write_file/patch_file), so it can include
paths that were only read, not written — harmless in practice since
`git add`/`git status` are no-ops on unmodified tracked files, but noted as
a minor imprecision (Suggestion, not blocking).

Guard order in `check_git_and_offer_commit()`: `is_git_repo()` check, then
`if not files_touched: return` — correct placement, no crash, fails closed
(under-commits rather than falls back to broad commit) if files_touched is
empty despite write_file/patch_file having been used.

`git_commit()`/`git_status()` bodies themselves are byte-for-byte untouched
in this diff — confirmed via diff inspection, and their other callers
(main.py ~586/603/629, ccos/plugins/coding/git_integration/test.py) still
pass that test suite's self-test verbatim (`All git_integration tests
passed!`).

See also [[gui_c2_remediation_sequence]] and [[daemon_self_pid_check_verified]]
for the general pattern of re-verifying process/state-scoping claims by
direct scratch-repo reproduction rather than trusting a reported test result.
