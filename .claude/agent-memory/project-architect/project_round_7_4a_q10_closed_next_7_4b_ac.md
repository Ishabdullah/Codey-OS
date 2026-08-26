---
name: round-7-4a-q10-closed-next-7-4b-ac
description: Ish's 2026-08-26 §8 Q10 decision closes 7.4a as risk-acceptance (not a fix); next queue item is 7.4b sub-tasks A/C live-verify under codey-start, bundled with NEW-180
metadata:
  type: project
---

Ish answered `CODEY_MASTER_PLAN.md` §8 Q10 on 2026-08-26, exact words:
"accept the residual as a standing documented risk for now." This closes
**7.4a** — but as a risk-acceptance decision, not a fix or a successful
live reproduction. Two axes, kept distinct per rules 5/6: (a) general
swap-assist activation on the real device — CONFIRMED live the round
before this one; (b) the compound low-RAM-AND-low-swap `NEW-21`-shaped
distress state — never observed live across 3 consecutive sessions, now
accepted as a standing risk rather than chased further.

`NEW-140`/`NEW-188` were left **OPEN, not Resolved** — the underlying
arithmetic risk is real and undisputed; what changed is a decision to
stop pursuing live reproduction, not a correction to the finding. This
is a real, deliberate distinction worth preserving in future closures of
this shape: risk-acceptance closes the *tracking item* (7.4a) without
closing the *finding* (NEW-140/NEW-188), because the finding's content
didn't change, only the appetite to keep testing it did.

**Advisor caught two things worth remembering for future §8-question
closures:** (1) always check whether the question's own numbered entry
in §8 follows this project's own struck-through "ANSWERED by Ish, DATE:
..." convention (see Q1/Q3/Q8) — I initially only appended a resolution
paragraph below Q10 without striking the title, which still read as
open in a section literally headed "Open decisions awaiting Ish." (2)
Before inheriting a "covered by M1-E" style claim onto an adjacent item
(here, 7.4's own remaining live-pass note), re-verify it independently
rather than assuming a prior item's rule-6 correction (7.4b-A/C: M1-E
used `main.py --no-resume`, not `codey-start`) automatically applies —
in 7.4's case it does NOT apply, because M1-E's own text states it used
`_spawn_locked()`, "the same code path as `codey-start`," and 7.4's ask
is specifically about that shared admission path, unlike 7.4b-A/C which
need the daemon/GUI session wrapper `--no-resume` skips.

**Next queue item per §6.2's stated Phase A1 ordering** (7.4 → 7.4a →
7.4b → lease/registry → concurrency test): **7.4b sub-tasks A and C's
live-verification under the real `codey-start` entry point** — both
code-complete and code-reviewer-approved already, just never actually
run under `codey-start` (M1-E deliberately used `--no-resume` to avoid
the daemon+GUI's extra headroom draw). Recommended to bundle with
`NEW-180` (embed model RSS, still unmeasured) in one live-verifier
session — see the 2026-08-26 `PROJECT_LOG.md` entry for the full
live-verifier brief (incremental evidence capture to survive a crash,
per [[project_round13_new11_closed]]'s 2-crash history; sample NEW-180's
RSS before the primary model loads, not at peak, or swap eviction will
understate it). Lease/registry and the concurrency test ("the central
question of this phase," per §6.2 Appendix A) are correctly ordered
behind this — both unstarted design work, not live-verify-ready.
