---
name: phase-b2-task4-email-sms-rules-scoped
description: Phase B2 task 4's second write-through module (email-rules.js/sms-rules.js) scoped 2026-08-27, spec-only, not implemented
metadata:
  type: project
---

Scoped (not implemented) the second Phase B2 task 4 write-through module: `email-rules.js`/`sms-rules.js` → `restoricon_core`'s automation-rules endpoints. Commit `e93a359` (docs only, pushed).

**Why:** continuing task 4's per-module rollout after the do-not-contact.js pilot (`1a5ccd6`/`4dd1232`). Ish asleep, worked autonomously per standing instruction, made no product-scope decisions (only implementation-readiness/rollout-safety calls).

**Key findings:**
- `calendar.js` evaluated as fallback and rejected without needing it — its real appointment record (`offered_slots`/`rsvp_status`/`form_sent`/`history`) hits a `NEW-224`-class general-update gap, larger than subcontractors'.
- Real production data re-verified directly (not from memory): 2 email rules, 0 SMS rules, 1 appointment (correcting an earlier "calendar.json is empty" claim in the master plan).
- `NEW-230` (new): no delete method/route exists for `automation_rules` — resolved *in-scope* this round (unlike `NEW-224`'s subcontractor deferral) because it's a single-purpose delete-by-id method, same size class as `NEW-217`'s in-scope lookup methods, not an open-ended field-merge design problem.
- `NEW-228` (new): production `email-rules.json` already has a dead rule (`condition_type: "message_contains"` has no matching case in the JS switch) — spec explicitly forbids "fixing" this during the migration, must survive unchanged.
- `NEW-229` (new): `create_rule` validates `channel` but not `condition_type`/`action` domain values — pre-existing, not fixed.
- Core-only vs dual-write decided as Core-only again, but the advisor caught that the *reasoning* differs from the DNC pilot (rules are config, not per-message safety state) — don't reuse "DNC said so" as justification without restating why it still applies.
- Auth/config plumbing (from the DNC pilot's provisioning) reusable as-is, no new config needed.

**How to apply:** next round is handing this spec to implementer, then mandatory code-reviewer (new `.../delete` route is auth-gated/security-relevant regardless of rule 4's narrower scope). Full 7-step spec lives in `CODEY_MASTER_PLAN.md` §6.4, right before §6.5. Remaining task-4 modules after this: comms paths (email-provider.js/gmail.js/index.js Google Voice), contacts.js/customer-module.js (blocked, `NEW-212`/`NEW-215`), subcontractor-recruiter.js (blocked, `NEW-224`), calendar.js (blocked, same class as `NEW-224`, confirmed again this round).

See also [[project_phase_b2_task4_dnc_pilot_closed]] for the pilot precedent this round built on.
