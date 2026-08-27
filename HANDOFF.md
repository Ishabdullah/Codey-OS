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

The `NEW-259` bug fixes above are code-reviewer-approved and committed
(`375dafd`, plus a follow-up `67b61aa` correcting that commit's own
wrong title — a leftover copy-paste, noted honestly in `PROJECT_LOG.md`
rather than force-pushed over, since you might be working concurrently
against this branch and a history rewrite risks your in-flight work more
than a wrong title line is worth). Also landed: the `AGENTS.md`/
`CODEY_MASTER_PLAN.md` doc-consistency fix described above, `NEW-260`
logged, and this file. Nothing from this round should still be
uncommitted — if `git status --short` shows otherwise when you read
this, something changed after this file was written; trust `git log`
over this file's own "what just landed" framing.

## What's next in the queue, in rough priority order

Check `PROJECT_LOG.md`'s top entry and `CODEY_MASTER_PLAN.md` §4/Appendix
A for the authoritative, current version of this list — it will have
moved by the time you read this file. As of when this was written:

1. **Live-verification of the `NEW-145`/`149`/`155` fix itself**, now
   that both real bugs are fixed — this still hasn't actually been
   exercised against a live daemon/real `llama-server` process. The
   exact sequence is written out in `CODEY_MASTER_PLAN.md` Appendix A's
   7.4b-C entry. Rule 2's RAM discipline applies in full: `free -h`
   before/after, one model-load cycle at a time, confirmed unload at the
   end.
2. **`subcontractor-recruiter.js`'s full write-through cutover — DONE.**
   Two Core-side Claude rounds (`update_subcontractor`,
   `find_subcontractor`) each found a new prerequisite before this
   session's rate limit hit; Antigravity picked it up from there and
   actually finished it (`abbc733`: `upsert_subcontractor()`,
   `format_subcontractor_for_js()`, the `POST /api/v1/subcontractors/
   upsert` route, code-reviewer-approved; `53a08bb` in the
   `Codey-Aigentik` repo: the actual JS cutover — `subcontractor-
   recruiter.js` now calls the upsert/update/find routes directly, async
   call sites updated in `index.js`/`owner-command.js`/`role-router.js`,
   150/150 JS tests + 133/133 restoricon-core tests passing). Not
   live-verified against real production traffic (no process-lifecycle
   changes, so live-verify wasn't required per the rules — but "code
   complete + tested" is still not "confirmed working against
   `~/Aigentik-CLI`'s real, restarted, live process," per rule 7).
3. **NEW-260** (newly found, unrelated, low priority): 6 tests in
   `tests/test_plannd_timeout.py`/`tests/test_plannd_tier_split.py` fail
   on a clean checkout — a stale expected-value formula from an older
   round (`dfb655c`) that never got updated when the real timeout formula
   grew a queue-wait term. Confirmed pre-existing and unrelated to
   anything from tonight. Real fix: update both files' hardcoded
   `expected_outer` formulas (or better, have them call
   `compute_outer_plan_timeout()` directly instead of re-deriving it by
   hand, so this can't silently recur).
4. Several items are genuinely blocked pending Ish's decisions, NOT
   implementation tasks to pick up on your own initiative: `NEW-215`
   (contacts.json scope), the lossy-vs-reliable comms log question
   (**already answered by Ish tonight** — reliable, not best-effort;
   `NEW-233`/`257` closed on that basis, see `PROJECT_LOG.md`), and
   whatever's currently listed in `CODEY_MASTER_PLAN.md` §8's "Open
   decisions awaiting Ish."

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
