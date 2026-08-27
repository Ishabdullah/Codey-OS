---
name: round-phase-b2-scoping
description: Phase B2 (Codey-Aigentik fork/data-migration) scoped 2026-08-27, not implemented; exit-criterion decision escalated to Ish
metadata:
  type: project
---

Phase B2 (§6.4, the voice/inbox limb writes through to Restoricon Core)
was scoped, not implemented, on 2026-08-27. Desk-only: read
`~/Aigentik-CLI`'s real code/data and `restoricon_core/`'s real schema,
did not touch `~/Aigentik-CLI` (project rule: never modified).

**Key finding (`NEW-209`):** the plan's own brief description of B2's
migration step ("contacts, calendar, rules, profile") undersold the
real scope by roughly half. Grepping every read/write-file call site
(not just current `data/` contents) found ten write-site modules across
five data shapes. The Core's 12-table schema (`restoricon_core/
database.py`) has a destination for only two of those five (contacts,
customers — both partial fits). Subcontractors, calendar/appointments,
automation rules, business profile, and Do-Not-Contact have zero Core
tables. This means B2's own stated exit criterion ("fork runs with no
local data store") is not achievable without a scope decision — either
absorb B3/B5a's schema work into B2, or narrow B2's own exit criterion.
Escalated to Ish, not resolved by this scoping round. See
`CODEY_MASTER_PLAN.md` §6.4 and §4.5 for the full writeup, `NEW_ISSUES.md`
`NEW-209`/`NEW-210`/`NEW-211`.

**Second finding worth remembering (`NEW-211`):** Aigentik-CLI's local
model call (`llama.js::chatLocal()`) already hits `127.0.0.1:8080` —
the exact same default port as Codey-OS's own `PRIMARY_SERVER_PORT`
(`utils/config.py:15`). This means step 4 ("point model calls at the
shared model layer") is NOT a simple hostname/config edit — it's a real
admission-control design item, because a same-port collision would
silently bypass `core/resource_gate.py`'s lease/slot mechanism and the
just-built §8 Q11 concurrency-oversubscription fix (`NEW-206`/`NEW-208`)
entirely. Any future Aigentik/Core model-layer integration work must
route through an actual lease-acquisition surface, not just repoint a
URL.

**Process note — advisor caught two things I'd undercounted/underscoped
before I wrote docs:** (1) I'd counted "five JSON files" instead of the
real ten write-site call-site modules (two of which write files that
don't exist on disk yet — `do-not-contact.js`, `queue.js` — a pure
grep-for-active-files approach misses code paths never yet triggered).
(2) I was about to write B2's exit criterion as achievable/scoped
cleanly without flagging that narrowing it is itself a plan-editing
decision requiring Ish, not an implementer's call. Both corrections
came from calling advisor() before finalizing docs — worth continuing
that habit on any scoping round that touches an authoritative-plan
exit criterion.

**Fork-creation commands determined but NOT executed** (destination
repo `https://github.com/Ishabdullah/Codey-Aigentik` created by Ish
mid-round): clone from Aigentik-CLI's real GitHub remote (not the local
directory) → `git remote rename origin upstream` → add the new repo as
`origin` → `git push -u origin main`. Awaiting go-ahead to run.
