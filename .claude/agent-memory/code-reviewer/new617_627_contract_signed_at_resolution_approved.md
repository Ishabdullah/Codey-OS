---
name: new617_627_contract_signed_at_resolution_approved
description: NEW-617 multi-party contract "Signed At" resolution + NEW-627 communications int-field validation — both APPROVED round1
metadata:
  type: project
---

Two small unrelated fixes reviewed together (2026-09-25), both APPROVED round1, zero findings:

- **NEW-627**: `POST /api/v1/communications`'s `project_id`/`opportunity_id`/`lead_id`
  now go through the router's existing `_parse_int_body_field` helper (already used
  at 15+ other call sites) instead of raw `json_body.get(...)`. Confirmed the helper's
  ValueError is caught by `handle_request`'s top-level `except ValueError` → clean 400.
  Trivial, matched established pattern exactly.

- **NEW-617**: implementer's initial finding-text citation (`pdf_service.py:252`,
  single-signer `render_contract_pdf`) was correctly identified as NOT the bug — the
  real gap was `render_contract_pdf_multi` having no "Signed At" field at all. Verified
  by reading `sign_contract`: the multi-party branch (`signer_rows` non-empty) never
  writes `Contract.customer_signed_at` — confirmed by reading both branches directly,
  not trusting the docstring claim alone. The "only resolve once every signer has
  signed" gate (`all(s.signed_at for s in signer_rows)`) matches `sign_contract`'s own
  `all_signed = remaining == 0` gate by construction: `signed_contract_signers` list
  passed into the PDF renderer carries `None` for not-yet-signed rows, so `all()`
  naturally requires full completion — traced this end-to-end rather than assuming the
  claimed correspondence.

Verification notes worth keeping:
- Scoped batch (`-k "contract or pdf or communicat"`) matched implementer's claim
  exactly (233/233). Full clean suite ran to completion this round (2526 passed, 1
  skipped, ~421s) — no hang, unlike some earlier rounds in this project's history.
  Implementer's own full-suite count (1213) didn't match my from-scratch run, but per
  established project pattern (see MEMORY.md test-count-mismatch entries) this is
  routine scope/exclusion drift, not a red flag, as long as the reviewer's own clean
  run is 0 failures.
- Cross-repo consumer-grep claim (Codey-Aigentik, Private-Codey-Agent/lib for
  `customer_signed_at`/`api/v1/contracts`) verified directly — zero hits in either,
  confirming no missed consumers of the renamed/added field.
- `DocumentField.value: str` confirmed — `resolved_signed_at or ""` correctly coerces
  `None` to `""` for the still-pending-signature PDF case, matching the test's
  `assert any(text == "" ...)` expectation.

Unrelated findings (NEW-617, NEW-627) bundled in one working tree — recommend staging
as two separate commits per this project's usual one-finding-per-commit convention,
even though both touch `routes.py` (different sections, hunks are cleanly separable).
