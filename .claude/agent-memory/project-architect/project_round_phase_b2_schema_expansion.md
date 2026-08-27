---
name: round-phase-b2-schema-expansion
description: Phase B2 round 2 (2026-08-27) — fork creation done, NEW-209 resolved by Ish (expand schema), 5 new tables/services/RBAC built
metadata:
  type: project
---

Fork creation for `Codey-Aigentik` is DONE (2026-08-27) —
`~/Codey-Aigentik` exists, pushed, tracking `origin/main`. Ish resolved
`NEW-209`'s schema-gap open decision by choosing option (a): expand
`restoricon_core`'s schema to cover all 5 of Aigentik-CLI's real data
shapes now (contacts/customers already had tables; subcontractors,
appointments/calendar, automation rules, business profile, do-not-contact
were built this round), not narrow B2 to CRM-only as the prior scoping
round's own stated preference was.

Built this round: 5 new SQLite tables (`database.py`), 5 new dataclasses
(`models.py`), `crm_service.py` extended with subcontractor methods, 2
new service files (`scheduling_service.py` for appointments,
`automation_service.py` for rules/profile/DNC), 10 new RBAC permissions
in `auth.py`. All code-complete + self-tested (`tests/
test_restoricon_core/`: 37 passed; full suite 753 passed/1 skipped) but
NOT code-reviewed and NOT committed — rule 4 applies (auth/RBAC touch)
same as B1's `NEW-189`/`NEW-192` precedent.

**Why:** avoided repeating `NEW-194`'s bug shape (permission gate present,
but narrowing logic below it keyed on `actor.role` identity rather than
the permission held) by giving `ROLE_CUSTOMER` zero permissions on all 5
new resources — no customer-scoped read path exists, so there's no
narrowing branch to get wrong. `ai_agent` role got full read/write on all
5 since it's the literal actor B2's write-through replacement will use.

**How to apply:** next B2 round (auth provisioning, migration script,
write-through replacement, model-layer repoint) needs this round's
code-reviewer pass to land first. `NEW-212` (customers/leads lack
external_id, unlike the 5 new tables) will matter when writing the
migration script — the 5 new tables already have this idempotency
mechanism, migration script should establish something equivalent for
customers/leads or accept the dedup risk. `NEW-213` (subcontractors_json/
communication_history overlap) is a design question for whoever wires
write-through, not a bug to silently fix.

See [[project_round_phase_b2_scoping]] for the prior round's scoping
context (NEW-209/210/211) this one builds on.
