---
name: round-7-4a-new135-136-scoping
description: NEW-135/NEW-136 fixed in core/resource_gate.py (2026-08-25), code-complete + self-tested, code-reviewer pass still pending; NEW-140 scenario 3/NEW-141 closed
metadata:
  type: project
---

After M1-G closed (2026-08-25), the master plan's §6.2 "Then:" ordering
(7.4, 7.4a, 7.4b, Lease/registry, Concurrency test) was re-read fresh to
pick the next item. 7.4's and 7.4b A/C's remnants are all live-verify-only
(deferred to a real `codey-start` entry point session), and this session
was directed not to run live model-load tests itself — so 7.4a's two open
code-level findings, `NEW-135`/`NEW-136`, were the correct next
dispatchable item (confirmed via advisor before implementing).

**What shipped:** `core/resource_gate.py` — `reserved_swap_bytes` param on
`compute_swap_assisted_headroom_bytes()`/`can_admit()` (subtracted from the
policy cap `max_swap_usage_bytes`, not live `SwapFree` — a PENDING
admission's swap claim hasn't actually reduced `SwapFree` yet);
`GateDecision.swap_bytes_claimed` (a magnitude, not just the existing
`admitted_via_swap` bool — NEW-135's fix needs something summable, and this
single field satisfies NEW-136's fix-direction note in the same change
rather than as a second pass); `reserve_slot()` computes the real
PENDING-only sum of other slots' `swap_bytes_claimed` inside its own
existing lock, mirroring the RAM-side `reserved`/`committed` sums it
already computes there (same TOCTOU reasoning); `register_slot()` gained
the matching param; new `total_reserved_swap_bytes()` mirrors
`total_reserved_bytes()` for any direct `can_admit()` caller outside
`reserve_slot()` (none exist today). 7 new regression tests
(`tests/test_resource_gate.py`, `test_new135_*` prefix). Full suite 668
passed/1 skipped (was 661/1).

**Scope boundary, explicit in the code and docs:** fixes the
`reserve_slot()`/`can_admit()` path only. `can_dispatch_task()`'s separate
swap-assist consumer (7.4a sub-task D2) registers no slot, so this
accounting mechanism has nothing to sum against there — still an open,
documented gap.

**Bundled desk confirmation:** `NEW-140` scenario 3 and `NEW-141` closed —
confirmed `core/planner_loader.py` and `_evict_planner_and_confirm_free()`
are genuinely absent from HEAD (not reused from the earlier M1-D code-read
alone), satisfying `NEW-159`'s stated closure bar. `NEW-140`'s OTHER,
model-independent content (general swap-assist-re-admits-distress
mechanism) stays open.

**Rule-6 correction made same round:** §6.2's table and Appendix A both
previously implied M1-E already covered 7.4b sub-task A/C's live-verify —
wrong; M1-E ran `main.py --no-resume`, not the real `codey-start` entry
point those sub-tasks specifically call for. Corrected in both places.

**Status: code-complete, self-tested, NOT mandatory-code-reviewer-approved**
(rule 4 — resource-gate admission accounting; no code-reviewer subagent
available this session, same gap M1-F hit). Next step for whoever picks
this up: run the code-reviewer pass before this can be marked done. See
[[project-c2-gui-security-status]]-style precedent — M1-F's own entry is
the template for how this gets closed out once a reviewer is available.

Also note: M1-G's own docs closure (CODEY_MASTER_PLAN.md/NEW_ISSUES.md/
PROJECT_LOG.md edits) was found already complete but uncommitted at the
start of this session — committed separately (`cbc87f3`) before this
round's own work, per "stage by scope" discipline.
