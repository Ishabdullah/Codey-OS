---
name: phase-b2-task4-dnc-pilot-closed
description: Phase B2 task 4 do-not-contact.js write-through pilot finalized across two repos (Codey-Aigentik + Codey-OS), code-reviewer-approved, not live-verified
metadata:
  type: project
---

2026-08-27: finalized and committed the do-not-contact.js write-through
pilot (Phase B2 task 4, first slice). Two separate repos, two commits:
`~/Codey-Aigentik` (`4dd1232`, pushed to its own `origin/main`, NOT
upstream `Aigentik-CLI`) and `~/Codey-OS` (this repo). Tests re-run
fresh, not reused: Codey-Aigentik 122/122 (`npm test`), Codey-OS
774 passed/1 skipped (`python -m pytest tests/ -q`).

**Why this matters for future rounds:** `~/Aigentik-CLI` is the live
original and must never be touched — all write-through work lands in
`~/Codey-Aigentik`, the fork. `config.json` in that fork is real (holds
a live bearer token) and gitignored; always `git check-ignore -v
config.json` before staging to confirm it's still excluded, never trust
memory that it is.

**Verification tier, precisely:** code-complete + code-reviewer-approved
for both repos. NOT live-verified — all HTTP testing (both repos, this
round included) went through a scratch/`:memory:` Core server, never the
real DB path being hit by a real server process from an external
caller. `NEW-225` tracks this distinction; it's now partly discharged
(real DB provisioned, one real `ai_agent` user exists) but not closed
(no server has ever actually served a request against that real DB
path). Don't let a future round collapse "the DB now exists" into
"the API is live-verified" — those are different facts.

**Findings from this round:** `NEW-226` (3 stale docs in
`~/Codey-Aigentik` still describing DNC as a local JSON file, doc-only),
`NEW-227` (`tools/provision_ai_agent_auth.py` accumulates tokens on
rerun, no revocation — already self-documented in the script's own
docstring, logged anyway per rule 8).

**Remaining scope, explicitly not touched:** 9 more write-through
modules in `CODEY_MASTER_PLAN.md` §6.4's per-module list, and the real
production cutover decision (Ish's call, not made).

See also [[project_round_phase_b2_task4a_routes_closed]] (the routes
this pilot's HTTP calls hit) and [[project_new206_concurrency_
oversubscription_finding]]-adjacent NEW-225 lineage in NEW_ISSUES.md for
the Core-API-never-run-in-production thread.
