---
name: phase-b2-task2-migration-scoping
description: Phase B2 data-migration script scoped 2026-08-27 — real JSON shapes diverge sharply from the task's initial assumption; spec handed to implementer, no code written
metadata:
  type: project
---

Scoped the Aigentik-CLI → restoricon_core one-off migration script
(Phase B2 task 2, CODEY_MASTER_PLAN.md §6.4) by reading the real, live
`~/Aigentik-CLI/data/*.json` files directly rather than trusting the
task's kickoff framing. `node index.js` (PID 31733) was live and
actively writing during the read; `llama-server` (PID 31746, port 8080)
was also live and untouched — both confirmed via `ps`.

**Why this matters:** the task handoff assumed `contacts.json` maps to
`crm_service`/Customer. It doesn't — it's an Android-contacts phonebook
sync (`source: "android_contacts"`, `type` in
person/subcontractor/unknown), 201 records, with no destination table.
Only `customers.json` (3 records) is real CRM data, and even that
overflows the Customer/Lead schema by ~40 fields with no dedup key
(NEW-212). `schedule-config.json` also has no destination table
(NEW-216, new). Result: first migration pass is scoped to the 4 files
that map cleanly (subcontractors, calendar, email/sms-rules, profile —
combined ~5 real records today), explicitly deferring
contacts/customers/schedule-config pending Ish's scope decisions.

Also found: `subcontractors`/`appointments`/`automation_rules` services
are INSERT-only with `UNIQUE(external_id)` — no lookup method exists, so
a second migration run would throw `IntegrityError` rather than upsert
or skip (NEW-217). Fixing this (3 new service methods) is folded into
the migration task itself, not deferred.

**How to apply:** don't trust a task description's assumed file→table
mapping for this project's data-migration work, even when the mapping
looks obvious from filenames — always read the actual JSON shape and the
JS writer module first (rule 12). When scoping future Aigentik-CLI
migration rounds, check NEW-212/215/216/217 status before assuming the
schema is ready to receive contacts.json or customers.json.

See also [[project_round_phase_b2_schema_expansion]].
