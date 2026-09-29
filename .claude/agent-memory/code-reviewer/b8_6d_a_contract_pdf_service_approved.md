---
name: b8_6d_a_contract_pdf_service_approved
description: B8.6d-a reportlab PDF renderer + sign_contract wiring, new reportlab/Pillow dependency — APPROVED
metadata:
  type: project
---

2026-09-22, APPROVED no round 2 needed. New `restoricon_core/services/pdf_service.py`
(reportlab canvas-based renderer, signature-anchor model) wired into `sign_contract`
(`crm_service.py`) as a best-effort side effect strictly after the existing
authorization/idempotency gate and after the sign UPDATE/audit-log commit.

What held up under adversarial verification (not just diff-read):
- Gate logic in `sign_contract` (customer isolation, NEW-573 rep-ownership narrowing,
  NEW-575 exemption, idempotency guard) traced line-by-line: genuinely untouched, new
  block starts after `self.audit.log(action="sign", ...)`.
- `try/except Exception` around the PDF side effect is real non-silent handling: logs
  `action="pdf_generation_failed"` audit entry with real actor + error detail, no
  re-raise, function still returns `_signed` normally either way.
- System-actor pattern (`user_id=1, role=ROLE_ADMIN, actor_type="agent"`) for
  `create_document` exactly matches the pre-existing `create_lead_from_web_form`
  precedent (verified via read, not just "resembles") — this is an established
  codebase pattern, not new risk introduced by this diff.
- `ROLE_CUSTOMER` confirmed via `auth.py` to hold `PERM_SIGN_CONTRACTS` +
  `PERM_READ_OWN_DOCUMENTS` but NOT `PERM_WRITE_DOCUMENTS` — the stated reason a
  system actor is needed for the internal `create_document` call is real.
- `document_type='contract'` confirmed present in the `documents` table's CHECK
  constraint in `database.py`.
- Image-vs-text-stamp regex (`^data:image/...;base64,`) correctly generalizes to any
  non-data-URL token, not just the one named sentinel — traced the regex and the
  `binascii.Error/ValueError/OSError` fallback path for a malformed image-shaped URL.
- Dependency claim verified independently, not just trusted: `reportlab` has 0 `.so`
  files in its installed tree (walked it myself); Pillow's installed dist-info
  `WHEEL` file literally says `Tag: cp314-cp314-android_24_arm64_v8a`, confirming a
  prebuilt wheel was used, not a source build — matches the `requirements.txt`
  comment's claim.
- Test-isolation leak fix (moving the doc-store fixture from a
  `tests/test_restoricon_core/`-scoped conftest to the repo-root `tests/conftest.py`)
  independently re-verified: snapshotted the real `~/.codeyOS/restoricon_documents/`
  tree, ran the full suite, confirmed zero new/modified files afterward via
  `find -newer` against a fresh marker file — not just trusting the implementer's own
  prior check.
- Full suite reproduced verbatim: `2214 passed, 1 skipped, 69 warnings in 350.98s`,
  matching the implementer's claim exactly (contrast [[new565_575_rbac_sign_contract_approved]]
  where this same full-suite run reportedly hung in-sandbox — it did not hang this
  time, so treat that as circumstantial/flaky, not a fixed rule about this repo).
- New test file (`test_b8_6d_a_contract_pdf.py`) spot-checked non-vacuous: real
  PDF-magic-byte assertions, real file-existence checks, real document-count and
  route-status assertions, not tautologies.

No findings, no NEW-### logged. Confirms the general pattern from
[[b8_6a_estimates_contracts_rep_ownership_approved]] that this contract-sign codepath
is now solidly gated and audited across several rounds of scrutiny.
