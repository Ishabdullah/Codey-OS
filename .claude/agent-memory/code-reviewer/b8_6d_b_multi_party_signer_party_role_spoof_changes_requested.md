---
name: b8_6d_b_multi_party_signer_party_role_spoof_changes_requested
description: B8.6d-b multi-party contract signer round — CHANGES REQUESTED, real finding is an unrecoverable non-atomic status-flip data corruption bug, not the party_role spoof (which the advisor caught was a false alarm via differential)
metadata:
  type: project
---

2026-09-22, B8.6d-b (`contract_signers` table, `CRMService.add_contract_signers`,
`sign_contract` multi-party branch, `pdf_service.render_contract_pdf_multi`).
Reviewed uncommitted diff across `database.py`/`models.py`/`crm_service.py`/
`pdf_service.py`. **Corrected after advisor review — my first-pass verdict
overclaimed a privilege-escalation finding and completely missed the real
Critical. Read the whole entry before reusing any part of the initial
framing below.**

**REAL CRITICAL (the one that blocks commit): non-atomic status flip on
the final multi-party signature is an unrecoverable data-corruption bug.**
The multi-party branch does the signer-row UPDATE and the
`contracts.status='signed'` UPDATE as two SEPARATE `with conn:` blocks
(two separate commits), not one transaction. Live crash-injection proof
(manually committed only the first block, mimicking a process death
between the two): the contract is left with every `contract_signers` row
signed but `contracts.status` still `draft`, and there is NO recovery
path through any exposed service method — `sign_contract` immediately
raises `"already signed"` for every party (idempotency guard resolves to
an already-signed row), and `update_contract`'s
`ALLOWED_CONTRACT_UPDATE_FIELDS = {"title", "template_name", "content"}`
does not include `status`, so an admin cannot even manually fix it via
the service layer. Permanently stuck contract, silently. Fix: wrap both
UPDATEs (the `contract_signers` write and the `contracts.status` write)
in a single `with conn:` block, same as the legacy single-signer path
already does correctly in one commit.

**What held up:** the "legacy path byte-for-byte unchanged" claim was true —
traced the `if not signer_rows:` branch line by line against
`git show HEAD:restoricon_core/services/crm_service.py`, identical UPDATE +
Contract() construction, same position relative to the NEW-573/575
ownership check and the idempotency guard (idempotency guard still fires
before the `contract_signers` lookup, untouched). `add_contract_signers`
correctly gates on `PERM_WRITE_CONTRACTS` (not `PERM_SIGN_CONTRACTS`) +
the same rep-ownership narrowing. No CHECK constraint added anywhere
(confirmed against DDL). `PRAGMA foreign_keys = ON` confirmed at
`database.py:1239` for every connection, so `ON DELETE CASCADE` is live.
routes.py's two `/sign` call sites are unaffected (still 3 positional
args, `party_role` is a new trailing optional kwarg) — already
self-disclosed as `NEW-592` ("no route surface yet").

**Downgraded to Warning (not Critical) after a differential check the
advisor demanded:** `_resolve_contract_signer_row`'s explicit-`party_role`
branch does zero validation that the caller-supplied `party_role`
corresponds to the actor's own identity/role — live-proved a
`ROLE_PROJECT_MANAGER` actor can call `sign_contract(contract_id,
"PM_FORGED_SIGNATURE", actor_pm, party_role="customer")` and have it
recorded as the customer's signature. My first pass called this a
Critical privilege escalation. The advisor pushed back: check what a PM
signing did PRE-diff. Ran it on the legacy (zero-signer-rows) path on
this same code: `sign_contract(contract.id, "PM_SIG_LEGACY", actor_pm)`
(no `party_role`, no `add_contract_signers` call) → succeeds, and
`customer_signature_data` becomes `"PM_SIG_LEGACY"` — i.e. the existing
single-slot design has ALWAYS let any `PERM_SIGN_CONTRACTS` holder
(including PMs, deliberately exempted from ownership narrowing by
NEW-575) write into the customer's signature slot. The multi-party
explicit-`party_role` path carries the same overloaded-authorization
semantics into a per-party model, it doesn't newly introduce them. Still
worth a NEW-### and a real fix before B8.6d-c wires a route that accepts
`party_role` from a request body (multi-party's entire point is
per-party attribution, so this gap matters more there than in the
single-slot legacy case), but it is NOT what blocks this round.
**Lesson: an escalation that "looks" new in the diff may just be
existing authorization semantics carried into new code — always
differential-test the pre-diff behavior before calling something a
regression, not just the post-diff behavior in isolation.**

**Also Warning: PDF multi-signer y-stacking overflows off-page for 4+
signers.** `_MULTI_SIGNER_Y_START=200.0` / `_MULTI_SIGNER_Y_STEP=80.0`
avoids overlap between adjacent anchors (verified), but the 4th signer
(the `_ROLE_TO_PARTY_ROLE` map defines exactly 4 real roles —
customer/rep/project_manager/admin, so a 4-signer contract is a live
case, not hypothetical) lands at y=-40, off the LETTER page bottom.
reportlab doesn't error, it silently clips/hides that signature. Live
math: y-positions for 4 signers = `[200.0, 120.0, 40.0, -40.0]`.

**Also Warning: multi-party partial-sign audit entries carry no
per-party attribution.** Live-checked `audit_log.details_json` after a
partial (1-of-2) multi-party sign: `{"side_effects":
{"signature_captured": true}}` — no `party_role`, no signer name/id, and
the `before`/`after` Contract-field diff is empty (top-level Contract
fields are genuinely unchanged on a partial sign, only `contract_signers`
changed). `change_summary` text does say "N signer(s) still pending" so
partial-vs-complete is distinguishable, but which specific party signed
is not recoverable from the audit trail without cross-referencing
`contract_signers` directly. Given this project canonicalized 55 audit
sites specifically for this kind of before/after fidelity
([[b6_2b1_audit_details_canonicalization]]), and per-party attribution is
the entire point of multi-party signing, this is a real gap — fix
direction: add `party_role`/signer identity into `side_effects`.

**Technique note:** none of the four findings above (the real Critical
included) were visible from a pure diff read — the legacy-path-unchanged
trace was clean, and the code reads carefully (explicit ambiguity
handling, idempotency-shaped errors). All four needed live execution:
the atomicity bug needed a manual crash-injection (commit only the first
of the two `with conn:` blocks, then try every recovery path); the
party_role concern needed a *differential* against pre-diff legacy
behavior, not just a post-diff repro, to tell escalation from
carried-over semantics; the PDF overflow needed computing actual
y-coordinates for a 4-signer case; the audit gap needed reading the
actual `details_json` column, not trusting the `change_summary` string.
Matches this project's established pattern
([[new568_customer_rep_narrowing_changes_requested]],
[[new587_proposal_unscoped_customer_approved]]) that this bug class
survives diff-level review and only surfaces via live adversarial
execution — and adds a new lesson: **always run the differential
(pre-diff vs post-diff) before calling a live repro a regression**, not
just the post-diff behavior in isolation, or you'll overclaim a
privilege-escalation finding that's actually pre-existing behavior
carried into new code.
