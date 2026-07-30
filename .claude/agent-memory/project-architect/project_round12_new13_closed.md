---
name: round12-new13-closed
description: Round 12 (NEW-13, thermal-restart regression) closed code complete + reviewer-approved + fully live-verified, commit 811209c
metadata:
  type: project
---

Round 12 (NEW-13) — `core/loader_v2.py`'s `ensure_model()` now consumes
`ThermalManager.restart_recommended` (restarts primary llama-server with
updated thread count, clears flag) — is closed as of 2026-07-30.

**Fix:** commit `0935cbd`. **code-reviewer:** approved, two non-blocking
Warnings (no lock around check-then-act — not exploitable with only one
call site today; no unit test on the new branch). **live-verifier:**
fully live-verified — real PID change (14619 → 14800, confirmed via
exact-PID `ps -p <pid>`, not name-substring grep since Termux truncates
`llama-server` to `llama-serv` in `ps` COMMAND column), flag correctly
cleared, working inference call post-restart, clean teardown, `free -h`
before/after showed full recovery. Docs closeout commit `811209c`
(NEW_ISSUES.md, PROJECT_LOG.md, PROJECT_PLAN.md).

**Why:** completes the punch-list chain from Round 11 (NEW-12), which had
orphaned this thermal mitigation as a documented side effect.

**How to apply:** [[project_round11_new12_closed]] for the prior round's
context. Remaining open items after this round: NEW-7 (recursive
planner, hardest, deferred), NEW-9 (deprioritized per user decision),
NEW-11 (daemon watchdog stale-flag gap, logged only), plus NEW-12's own
two deferred items (cross-process port lock, planner auto-launcher).
Next round to be decided with the user — do not assume which one is next
without asking.
