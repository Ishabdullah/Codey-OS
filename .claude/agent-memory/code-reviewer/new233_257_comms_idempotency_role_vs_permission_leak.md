---
name: new233-257-comms-idempotency-role-vs-permission-leak
description: NEW-233/257 comms provider_message_id dedup — round1 rejected on role-vs-permission leak, round2 approved with 1 residual doc-accuracy warning
metadata:
  type: project
---

**Round 1 (rejected):** `restoricon_core/services/communication_service.py`
`record_communication()`'s `ON CONFLICT(provider_message_id) ... DO
NOTHING` dedup path returned the existing row verbatim on collision,
leaking content to `ROLE_TECHNICIAN` (holds `PERM_LOG_COMMUNICATION` but
not `PERM_READ_COMMUNICATIONS`) despite the fix only stripping
`provider_message_id` for `ROLE_CUSTOMER`. Full detail in git history of
this file / PROJECT_LOG.md.

**Round 2 (approved):** gate changed to
`not actor.has_permission(PERM_READ_COMMUNICATIONS)`, dropping the
now-dead `or actor.role == ROLE_CUSTOMER` branch entirely. Verified:
- Read `auth.py`'s full `ROLE_PERMISSIONS` dict directly — confirmed
  `ROLE_CUSTOMER` holds only `PERM_READ_OWN_COMMUNICATIONS` (distinct
  permission), and `ROLE_TECHNICIAN`/`ROLE_CUSTOMER` are the *only* two
  roles with `PERM_LOG_COMMUNICATION` but not `PERM_READ_COMMUNICATIONS`
  — the single-permission gate covers both correctly, no third role
  slipped through.
- Negative-control confirmed live: hand-reverted the gate to
  `actor.role == ROLE_CUSTOMER` back to a scratchpad-backed copy, re-ran
  `test_technician_cannot_use_provider_message_id_to_read_another_customers_row`
  — it failed with the exact leak (`result.id == private_row.id`, wrong
  customer/content/subject all returned), confirming the test is
  genuinely load-bearing, not a trivial assertion. Restored file after
  (`cp` from scratchpad backup, not `git checkout`, per
  [[git_checkout_path_wipes_uncommitted_diff]]).
- Warning 2 (routes.py `provider_message_id` type check before
  `.strip()`) verified present in the diff and covered by
  `test_api_communications_non_string_provider_message_id_returns_400`.
- Warning 1 (scoped test count) verified: `python -m pytest
  tests/test_restoricon_core/ -q` → 115 passed, matches doc claim
  exactly; doc text in `NEW_ISSUES.md`/`CODEY_MASTER_PLAN.md` explicitly
  states the scoping caveat and corrects an earlier unstable
  "full-suite 850 passed" framing.
- `git status` this round showed clean scope (no cross-round bleed from
  the concurrent `core/daemon.py`/`loader_v2.py` round, unlike round 1 —
  that round is now fully committed separately).

**Warning 3 — only partially closed, logged not blocking:**
`NEW_ISSUES.md`'s own `NEW-257` entry (the authoritative single-finding
ledger per this project's rule 8) still frames the "zero idempotency
protection" consequence paragraph as `ROLE_CUSTOMER`-specific ("this one
role") — it was written before the technician-fix paragraph later in the
same entry and never got a follow-up sentence generalizing it to *any*
actor lacking `PERM_READ_COMMUNICATIONS` (i.e. `ROLE_TECHNICIAN` too).
`PROJECT_LOG.md` (lines ~105-113) DOES carry the correctly-generalized
version ("any caller without \[`PERM_READ_COMMUNICATIONS`\]... gets no
dedup protection at all"). `CODEY_MASTER_PLAN.md` describes the
leak-fix itself correctly but doesn't restate the idempotency-tradeoff
consequence at all. Net: the three docs are inconsistent with each
other on this one point, and the authoritative one (`NEW_ISSUES.md`) has
the stalest version. Not blocking — this is a documentation-accuracy gap,
not a code or test defect — but should be tightened before the finding
is called fully closed: add one sentence to NEW-257's consequence
paragraph generalizing beyond `ROLE_CUSTOMER`.

**Reusable lesson:** when a finding's fix broadens mid-round (role-keyed
→ permission-keyed), check whether *every* prose paragraph describing
that finding's consequences was updated to match the broadened fix, not
just the paragraph directly describing the code change itself. Ledger
entries often get written incrementally as a round proceeds, and an
earlier paragraph can go stale exactly like a stale status line does —
same underlying pattern as the "stale TODO/status line shipping with its
own fix" bug class already logged in other memories.
