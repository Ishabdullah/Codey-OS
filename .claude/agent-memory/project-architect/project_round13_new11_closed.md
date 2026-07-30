---
name: round13-new11-closed
description: Round 13 (NEW-11, daemon watchdog stale-liveness flag) closed code complete + reviewer-approved + fully live-verified, commit 0c2635b; NEW-14 (device swap-pressure finding) logged
metadata:
  type: project
---

Round 13 (NEW-11) — `core/daemon.py`'s 30s watchdog now checks real
process liveness instead of a stale in-memory `get_loaded_model()` flag
— is closed as of 2026-07-30. This was the last item from the
second-wave punch list (NEW-4/NEW-12/NEW-13 already done).

**Fix:** commit `ab13a8d`. **code-reviewer:** approved (static/unit-test
evidence at review time). **live-verifier:** took four attempts to get a
clean result:
1. Full `codeydOS start` (daemon + 7B + 1.5B plannd + embed, all
   concurrent) — crashed Termux entirely at 7B model-load time.
2. Same full stack — crashed again, possibly compounded by the app being
   backgrounded (unconfirmed).
3. Same full stack, Termux kept foregrounded — did NOT crash but
   self-aborted proactively (per its own safety instructions) after
   swap climbed from ~1Gi baseline to 7.5-8.5Gi within ~40s of steady-
   state startup, before reaching the actual kill/restart test.
4. A lighter, isolated harness — `python3 main.py --daemon` directly,
   bypassing the `codeydOS` wrapper (which is what spawns the separate
   1.5B plannd process) — succeeded cleanly. Peak swap this run: ~1.9Gi,
   vs. 7.5-8.5Gi for the full stack.

Docs closeout commit `0c2635b` (NEW_ISSUES.md, PROJECT_LOG.md,
PROJECT_PLAN.md) — contains the full verbatim evidence for both the
crash history and the successful run.

**Why:** completes the punch-list chain; also surfaced a real,
previously-undocumented device-capacity finding along the way.

**How to apply:** see [[project_new14_swap_pressure_finding]] for the
device-capacity finding this round surfaced — relevant to CLAUDE.md rule
2 (RAM discipline) for any future live-verification work involving the
full `codeydOS start` stack. Remaining open after this round: NEW-7
(recursive planner, hardest, deferred), NEW-9 (fork-window race,
deprioritized), NEW-14 (device swap-pressure, observational, not a code
fix), plus NEW-12's own two deferred items (cross-process port lock,
planner auto-launcher). Next round to be decided with the user — do not
assume which one is next without asking.
