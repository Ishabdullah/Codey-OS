---
name: round14-new7-results
description: Round 14 NEW-7 live-reproduction findings (2026-07-30) — settled recursion-specificity, spawned NEW-15 through NEW-18
metadata:
  type: project
---

Round 14 (commit `f1a9896`) ran 6 of 8 planned live-reproduction draws for
[[project_round14_new7_scoping]]'s plan before stopping at genuine
swap-thrashing (swap 8.9Gi, `llama-server` RSS ~2MB) — a correct,
CLAUDE.md-rule-2-mandated stop, not a failure.

**NEW-7 settled:** the `old_str: ""` bug is NOT recursion-specific —
reproduced once on the recursive path (a2) and once on the plain path
(b1). A related hallucinated-`old_str` variant (assumes `shutdown()` is a
1-line stub, not its real ~15-line body) added 2 more failures (a1, b2).
Combined: 4/6 completed draws (67%) failed the docstring-insertion
prompt. Two other prompt styles (loader_v2 error-handling, patch_tools
rename) did NOT reproduce in the draws that ran, but their plain-path
counterparts (b3, b4) were never run — still an open gap.

**Four new structural findings spawned, all Confirmed, none fixed:**
- **NEW-15** (likely the most severe finding of this investigation): when
  `patch_file` fails, the model can autonomously escalate to a
  `write_file` call attempting to reconstruct an ENTIRE file from memory
  — observed placing the reconstructed function in the WRONG location.
  Only `AGENT_CONFIG["confirm_write"] = True` prevented real data loss.
  Exact trigger logic in `core/agent.py` not yet pinned down to line
  numbers — needs its own dedicated investigation, flagged as possibly
  higher priority than continuing NEW-7's remaining 2 draws.
- **NEW-16**: `core/agent.py`'s `show_patch()` (~line 410-413, needs
  re-verify) renders the "Patching" UI panel unconditionally, even when
  the underlying patch call failed — a UI-honesty gap.
- **NEW-17**: `core/agent.py`'s `check_git_and_offer_commit()` (~line
  659-680, needs re-verify) offers to commit ALL working-tree changes,
  not just the current turn's edit — scope-bleed risk.
- **NEW-18**: severe swap-thrashing reproduced in a single lightweight
  daemon-free REPL session after only 2 model calls with retries — not
  limited to the full 3-model `codeydOS start` stack ([[project_new14_swap_pressure_finding]]). May mean CLAUDE.md rule 2's RAM guidance needs
  updating to cover sustained retry-heavy single sessions, not just
  concurrent multi-model loads.

**Why this matters for future rounds:** next decision point is whether to
prioritize NEW-15 (severity: potential silent full-file data loss) over
finishing NEW-7's last 2 draws (b3/b4) — not yet decided with the user as
of 2026-07-30.
