---
name: new164_165_planner_timeout_fix_approved
description: NEW-164/NEW-165 plannd.py token-budget + formula-based timeout fix — APPROVED with 2 non-blocking write-up corrections
metadata:
  type: project
---

Reviewed core/plannd.py's compute_planner_timeout() (NEW-165) + PLANNER_MAX_TOKENS
1024->2048 (NEW-164) + daemon.py's two asyncio.wait_for outer-timeout sites
(2026-08-23, M1-E). **Verdict: APPROVED, ready to commit pending the separate
live-verification pass.**

What actually got checked, beyond the diff read:
- Negative control: hand-reverted both daemon.py `timeout=outer_timeout` sites
  back to flat `timeout=180.0`, reran `tests/test_plannd_timeout.py` — got the
  exact `180.0 == 694.45` failure the implementer claimed, on 2 tests. Restored
  the file, confirmed diffstat matched original (37 insertions/10 deletions).
- Repo-wide grep confirmed exactly 2 real callers of `send_plan_request_async`
  (both in the diff) — no third untouched call site relocating the bug further.
- `estimate_tokens(PLANNER_PROMPT)` == 2446 vs NEW-164's real-tokenizer ground
  truth of 2425 — off by <1%, and in the safe (over-, not under-) direction, so
  the formula's only real input is calibrated correctly, not just "reused."
- `send_plan_request_async(task)` -> `core.plannd.get_plan(task)` directly
  (core/planner_client.py), same prompt string daemon.py uses in its own
  `estimate_tokens(PLANNER_PROMPT) + estimate_tokens(prompt)` calc — inputs to
  daemon's outer-timeout formula and plannd's inner-timeout formula are
  identical on the normal path, not just structurally similar.
- Full suites run live: `pytest tests/` -> 655 passed, 1 skipped;
  `pytest ccos/tests/` -> 68 passed. Matches implementer's claimed counts
  verbatim.
- NEW-166 (shared PLANNER_MAX_TOKENS also silently doubling
  `_get_plan_remote()`'s payload while its own `timeout=60` stays untouched)
  independently confirmed via direct read of plannd.py:328/345. Judged
  reasonable to leave Suspected/open — opt-in remote path, mechanism logged
  accurately, real fix is a design decision (split constant vs. measure
  provider rate), not a correctness gap in this diff.

Two things flagged as required write-up corrections, NOT blocking:
1. The new `except ImportError` guard around `from core.tokens import
   estimate_tokens` (plannd.py get_plan()) is justified in-comment as
   protecting against `utils.config` raising on a malformed `CODEY_N_CTX` —
   but `core/tokens.py` hard-imports `utils.config` at module level, and
   `get_plan()` already has an *identical*, older `except ImportError`-only
   gap around `from utils.config import PLANNER_MAX_TOKENS, PLANNER_TEMPERATURE`
   a few lines earlier in the same function. If `utils.config` really raises
   ValueError (not ImportError) at import, `get_plan()` was already going to
   crash before ever reaching the new NEW-165 code — the new comment's
   specific scenario is moot, not a new regression. daemon.py's outer
   `except Exception` catches it either way (safe fallback: "plannd
   unavailable", not a daemon crash), so this is Warning-level: correct the
   comment's stated rationale, don't leave the overclaim standing (rule 6).
2. `CODEY_MASTER_PLAN.md` (untouched in this diff) still describes
   `PLANNER_MAX_TOKENS=1024` / NEW-164+165 as "confirmed too small" / "Not
   started" — stale relative to the new code, but *not* the "diff ships a
   false current-state claim alongside its own fix" pattern that blocked
   5 prior rounds (see m1a_qwen35_hybrid_arch_ssm_underestimate.md etc.) —
   this doc simply wasn't touched yet. Acceptable to leave for the
   round-close doc-update step (rule 9, after live-verification), but must
   not be forgotten — flag explicitly, don't let it slide silently.

Reusable check for next time a formula-derived timeout/budget fix shows up:
grep every caller of the wrapped async/HTTP function repo-wide before trusting
"both call sites" — a stronger reviewer pass caught this gap in my first
draft; the two calls sites happened to be the only ones here, but next time
they may not be.
