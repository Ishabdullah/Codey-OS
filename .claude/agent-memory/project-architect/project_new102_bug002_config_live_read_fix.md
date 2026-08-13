---
name: project_new102_bug002_config_live_read_fix
description: 2026-08-13, NEW-102/bug_002 (config n_ctx constants frozen at import, --ctx never reaches them) fixed for real; also corrected ultrareview's bug_001 (file existed, just untracked); spun off NEW-150
metadata:
  type: project
---

Cloud ultrareview on 7.4a/7.4b's branch returned two nits: bug_001 (a
`.claude/agent-memory/project-architect/MEMORY.md` index entry pointing
to a memory file it claimed didn't exist) and bug_002 (7.4b sub-task C's
own first pass had reintroduced the exact NEW-102 import-order trap for
two new values, `PLANNER_N_CTX`/`CODER_BACKGROUND_N_CTX`).

**bug_001 correction:** the file existed on disk with correct content —
it was untracked (`??` in git status), not absent. Ultrareview reviewed
the diff, which never shows untracked files. Lesson: when a
diff-based review claims a referenced file "doesn't exist," check the
actual working tree (`ls`, `git ls-files`) before either creating a
duplicate or rewording the reference — the real bug may just be a
missing `git add`.

**bug_002/NEW-102 real fix:** converted `utils/config.py`'s
`PLANNER_N_CTX`/`CODER_BACKGROUND_N_CTX` and `core/memory_v2.py`'s
`CTX_TOTAL` from import-time-frozen constants to functions
(`get_planner_n_ctx()`/`get_coder_background_n_ctx()`/`get_ctx_total()`)
that re-read `MODEL_CONFIG["n_ctx"]` live, so a runtime `--ctx` override
(`main.py`'s `apply_overrides()`) actually reaches them — confirmed via
`git show 163b5e5:core/planner_loader.py` that this was a genuine
regression (baseline read `MODEL_CONFIG.get(...)` live), not just a gap.
Also added the missing positive-value guard to `--ctx` itself
(`if args.ctx is not None: ... if args.ctx <= 0: raise ValueError`).

**Spun off [[project_new145_lazy_coder_load_scoping]]-adjacent finding
NEW-150:** `tests/test_new19_patch_failed_repeat_escalation.py`'s
`_in_subtask=False` tests run real, unmocked git operations against the
actual working tree and fail with an `OSError` reading stdin whenever
the file they touch (`main.py`) has ANY real pre-existing uncommitted
diff at test-run time — not caused by this round's change, but exposed
by it (this round legitimately left `main.py` dirty before commit).
Confirmed by reproducing with `main.py` clean (passes) vs. dirty (fails,
deterministically, not flaky). Worth remembering: a full-suite test run
mid-session (before committing) can produce failures that look like
regressions but are really "this test isn't hermetic against a dirty
working tree" — check whether the failure survives a `git stash` of just
the file in question before assuming your own change broke it.

Verification tier: code complete, unit-verified only (default-path
numbers unchanged, so no live model load needed or done).
