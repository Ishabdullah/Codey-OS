# Handoff — Claude → Antigravity, 2026-08-27

Written because Claude Code hit a session rate limit mid-round and Ish
brought Antigravity in to continue the same work. This file is the
immediate "what's happening right now" briefing; it does not replace
`CODEY_MASTER_PLAN.md` (still the single authoritative plan) or
`PROJECT_LOG.md`/`NEW_ISSUES.md` (still the permanent records) — read
those for anything beyond "what do I do in the next five minutes."

**Read `ANTIGRAVITY.md` first if you haven't** — it's your copy of this
project's non-negotiable rules (same content as `CLAUDE.md`, which Claude
Code reads). Both files must stay consistent; if you ever find one says
something the other doesn't, that's a bug in the docs, not a real
divergence in the rules — fix the docs, don't pick a favorite.

## How to pick this up

1. Read `CODEY_MASTER_PLAN.md` §4 (current state) and Appendix A (open
   item register) — both are kept current after every round, by
   whichever agent (Claude or Antigravity) does that round's work.
2. Read the top 3-5 entries of `PROJECT_LOG.md` for what just happened.
3. Check `git log --oneline -20` and `git status --short` — if anything
   is uncommitted, figure out whose it is and whether it's mid-review
   before touching it (see "Working alongside another agent" below).
4. Continue exactly through the pipeline `ANTIGRAVITY.md`/`CLAUDE.md`
   both describe: Project Architect scopes → implementer/prompt-engineer
   builds → **code-reviewer approves before every commit, no exceptions
   for small-looking changes** → live-verifier confirms on-device when a
   change needs real (not just mocked) confirmation.

## Working alongside another agent (this is new as of tonight)

Both Claude and Antigravity may be working on this repo in the same
session or close together in time. Two things that actually happened
tonight, worth knowing before it happens to you:

- **Doc-write collisions.** `CODEY_MASTER_PLAN.md`/`NEW_ISSUES.md`/
  `PROJECT_LOG.md` are plain files with no merge mechanism between two
  agents editing them concurrently — whoever saves second silently
  overwrites whoever saved first, and both can allocate the same next
  `NEW-###` id. Before you save any of the three tracking docs, run
  `git status --short` immediately beforehand and confirm nothing
  changed out from under you since you last read them. If you're about
  to do a long research/implementation task and know another agent might
  be touching the tracking docs around the same time, consider writing
  your findings to a scratch file first and folding them into the real
  docs once you're sure you have exclusive access.
- **A fix that passes every test can still be wrong.** Tonight's
  `NEW-145`/`149`/`155` context-ceiling fix (`b0d2d86`) shipped
  code-complete and was approved across TWO separate code-reviewer
  passes — and still had two real bugs that would have made it either
  crash (`AttributeError` on `DaemonServer._config`, which never existed)
  or silently do nothing at all in production (a missing `port=` kwarg
  on the only `reserve_slot()` call site, which would have made the
  whole upgrade mechanism a permanent no-op). Both were caught by
  actually attempting live-verification, not by re-reading the diff
  harder. See `NEW-259` for the full detail. **The lesson: "code-reviewer
  approved" and "live-verified" are genuinely different tiers, and this
  project's own rule 7 exists because the gap between them is real, not
  theoretical — don't let a round get marked done on the strength of
  passing unit tests alone when live-verification is what the plan calls
  for.**

## What just landed (committed, done as of this writing)

1. **`NEW-260` resolved (`6af3ad6`)**: Fixed stale hand-derived outer timeout assertions in `tests/test_plannd_timeout.py` and `tests/test_plannd_tier_split.py` to call `compute_outer_plan_timeout()` dynamically.
2. **7.4b-C / `NEW-145`/`149`/`155` Option C upgrade LIVE-VERIFIED ON-DEVICE**:
   - Initial live run discovered `NEW-261`: `core/resource_gate.py:reserve_slot()` was double-counting same-port resident slots in `_sum_committed_bytes()`, rejecting the candidate before `LlamaServer.start()` could execute the upgrade.
   - Fixed `NEW-261` by excluding same-port slots from the concurrent sum in `reserve_slot()` when `port` is provided; added unit test `test_reserve_slot_same_port_excludes_resident_slot_for_upgrade` (all 883 pytest tests pass).
   - Real on-device live verification executed successfully: background server spawned at `n_ctx=16384` (PID 5943), interactive attach killed PID 5943 (exit code 0) and respawned at `n_ctx=65536` (PID 6300), verified new resident slot, confirmed clean teardown, 0 lingering processes, and RAM recovered to baseline (6.9GiB available).
   - Item 7.4b-C and parent 7.4b are now fully closed across all tiers.

## What's next in the queue, in rough priority order

1. **Phase B2 Write-Through Cutover (Remaining Modules)**:
   - `subcontractor-recruiter.js` cutover is done (`53a08bb` in Codey-Aigentik, `abbc733` in Codey-OS).
   - Reliable comms logging is in place (`NEW-233`/`257`, `9748a49`).
   - Next modules for write-through in `Codey-Aigentik`:
     - `calendar.js` $\rightarrow$ Core Appointments endpoints (`POST /api/v1/appointments`, `POST /api/v1/appointments/:id/status`, `GET /api/v1/appointments`).
     - `email-rules.js` / `sms-rules.js` $\rightarrow$ Core Automation Rules endpoints (`POST /api/v1/automation-rules`, `POST /api/v1/automation-rules/:id/match`, `GET /api/v1/automation-rules`).
     - `do-not-contact.js` $\rightarrow$ Core DNC endpoints (`POST /api/v1/do-not-contact`, `POST /api/v1/do-not-contact/remove`, `GET /api/v1/do-not-contact/check`).
     - `contacts.js` / `customer-module.js` $\rightarrow$ Core Customer/Lead endpoints.
2. **Items pending Ish's decisions**:
   - `NEW-215` (contacts.json scope / schema decisions) and whatever is currently listed in `CODEY_MASTER_PLAN.md` §8.

## Rules that bear repeating (both files already say these, stated once more because tonight involved a lot of concurrent work)

- Never `git add -A`/`git commit -a` when another agent might have
  uncommitted work in the same tree — stage exact file paths.
- Never mark something "done" on code-complete/unit-tested evidence
  alone when the plan calls for live-verification (rule 7).
- Anything found outside a task's scope gets logged to `NEW_ISSUES.md`,
  never silently fixed or dropped (rule 8) — even something as small as
  a stale test formula.
- Never kill a process by bare name pattern; track and kill the specific
  PID your own code spawned (rule 3).
- Correct the record when a claim doesn't hold up (rule 6) — including,
  as tonight showed, a claim your own prior round made.
