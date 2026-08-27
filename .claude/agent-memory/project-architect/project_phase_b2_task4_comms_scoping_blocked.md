---
name: phase-b2-task4-comms-scoping-blocked
description: 2026-08-27 comms/email/SMS-provider write-through scoping found blocked on missing customers/leads external_id and no communication_history idempotency key; not handed off, pending Ish decision logged
metadata:
  type: project
---

Scoped (not implemented) the comms/email/SMS-provider write-through
(`email-provider.js`/`gmail.js`/`index.js`'s Google Voice handling),
Phase B2 task 4's 3rd module. Concluded it is genuinely blocked, not
just riskier — did not hand it off for implementation.

Key findings:
- No existing local comms log in `~/Codey-Aigentik/data/` (only
  customers.json 1.5KB, subcontractors.json 2 bytes) — unlike DNC/rules,
  this is not a migration of an existing write, it's adding brand-new
  Core calls into a live send/receive path.
- **Blocker:** `customers`/`leads` tables have no `external_id` column
  (NEW-212/NEW-232), so JS-side contact/customer IDs can't resolve to
  Core's integer `customer_id` FK that `record_communication()` needs —
  every write would land `customer_id=NULL`.
- **Confirmed separately (NEW-233):** `communication_history` has no
  idempotency key; combined with email-provider.js's documented IMAP
  `\Seen`-flag reprocessing hazard, inbound write-through would
  duplicate rows in an append-only/immutable table.
- Settled myself (not deferred to Ish): outbound comms logging must be
  best-effort/non-blocking, opposite of DNC's Core-only pattern — because
  `sendEmail`/`sendReply` throw and callers act on the throw, so a Core
  failure in that path risks a suppressed or duplicated real customer
  message. Mechanism-based reasoning, not a "different risk profile"
  hand-wave.
- Two narrow questions ARE Ish's, logged as pending decision in
  `CODEY_MASTER_PLAN.md` §4: (1) prioritize NEW-212/232's schema fix now?
  (2) is a knowingly-lossy best-effort comms log acceptable as interim
  state for the eventual single-backend system?

**Why:** the advisor call before scoping caught that "escalate on
risk-feel" wasn't good enough — needed to name the actual blocking
dependency (external_id) via direct checks (grep database.py, auth.py,
routes.py) rather than general caution. That converted a vague
escalation into a concrete blocked-on-X finding plus two narrow
Ish-only questions.

**How to apply:** before scoping any future write-through module,
check (1) can the JS-side identifier actually resolve to the Core FK
the target service method needs, (2) does the destination table have
an idempotency/dedup mechanism if the source path has any known
retry/reprocessing hazard, (3) whether Core-only vs best-effort should
follow DNC's precedent or invert it — decide via the specific
throw/duplicate-effect mechanism of the module being converted, not by
matching the prior pilot's pattern mechanically. See
[[project_phase_b2_task4_dnc_pilot_closed]] and
[[project_phase_b2_task4_email_sms_rules_closed]] for the two prior
(unblocked) pilots this one deviated from.
