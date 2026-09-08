---
name: new_issues_cleanup_batch2_round2_approved
description: NEW_ISSUES.md cleanup batch 2 re-review after fixes — APPROVED with 2 non-blocking warnings
metadata:
  type: project
---

Round 2 of [[new_issues_cleanup_batch2_changes_requested]]. All 3 flagged
items fixed correctly, verified independently (not just re-reading the
implementer's claim):

- **auth.py tuple-return crash**: grepped all 3 `update_user` return
  sites, confirmed all tuple-shaped now. Only one production caller
  (routes.py:588). New regression test goes through the real
  `router.handle_request` dispatch (not mocked) and asserts 404 on both
  PUT/POST to a nonexistent user id.
- **sandbox.py cwd mis-resolution**: confirmed `exec_cwd` computed
  before the call (ordering matters — an ordering bug would silently
  pass a wrong/uninitialized cwd). Live-reproduced the exact round-1
  token (`"../../home/Codey-OS/ccos/target"`) flipping from
  "validates as allowed" (old, process-cwd-based) to "correctly flagged"
  (new, exec_cwd-based) — proves genuine behavioral fix, not cosmetic.
  Only one call site of the now-3-arg function.
- **shutil import / cleanup no-op**: added correctly; live-verified
  `cleanup()` now actually removes the tmp dir. Checked all other
  `Sandbox().cleanup()` callers in the test suite — none read `_tmp_dir`
  post-cleanup, so no knock-on breakage from making it functional.

**Advisor-prompted scope check that mattered**: my first pass scoped
`git diff` to only the 3 named files and missed that `git diff --stat`
(unscoped) showed 5 more modified files riding along with no commit
boundary since round 1 (same [[working_tree_cross_round_bleed]] /
[[plannd_iter4_report_gen_deletion_scope_warning]] pattern). Read all 5
— matched content already cleared in round 1 (NEW-307/240/248/281/300),
nothing new or weakened. **Lesson: after a round-1 CHANGES REQUESTED on
a pathspec-scoped diff, round 2's re-review must re-run `git diff --stat`
unscoped, not just re-check the named files** — a round-2 fix commit can
carry unrelated drive-by changes that never got reviewed.

**2 non-blocking warnings surfaced this round**:
1. No test pins the `cwd` param of `_find_disallowed_path_token` — a
   mutation-test check (revert `Path(cwd)/token` to bare `Path(token)`)
   still passes all 4 new sandbox tests, since none use a relative
   `../` token. My manual repro proved the fix works but the shipped
   suite doesn't guard it from regressing.
2. Ledger docs (NEW_ISSUES.md/PROJECT_LOG.md/CODEY_MASTER_PLAN.md) still
   untouched by this diff — the round-1 process-gap flag is still open.

**Verification-claim discrepancy**: task description claimed "1486
passed, 1 skipped"; actual unscoped full-suite run (`python3 -m pytest
-q`, live, 328.91s) was **1597 passed, 1 skipped, 68 warnings** — no
failures either way, so not blocking, but the literal claimed count was
stale/wrong. Per rule 5, always re-run the full suite yourself rather
than trusting a pasted count, even when the count "looks fine."
