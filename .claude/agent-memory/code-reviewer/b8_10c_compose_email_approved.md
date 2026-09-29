---
name: b8-10c-compose-email-approved
description: B8.10c sales-portal compose/send-email route (real Gmail SMTP side effect) — APPROVED round1, zero blocking findings
metadata:
  type: project
---

2026-09-24, APPROVED round1. Highest-risk B8.10 sub-phase (only one with a
real external side effect — actual email via Aigentik's live Gmail SMTP).
All headline claims independently re-verified, not trusted from the diff
read alone:

- **Send-then-log ordering**: read routes.py line-by-line — `record_communication()`
  is reachable only after `sent is True`; all 4 failure-mode tests
  (non-200, URLError, TimeoutError, bare-except) assert zero
  `CommunicationRecord` rows, not just a status code. Confirmed correct.
- **Recipient locking**: `to_email` comes only from `customer.email`
  (never `json_body`) — ran my OWN independent repro (separate script, not
  just their test), POSTing `to`/`to_email`/`recipient` attacker fields and
  inspecting the mocked `urlopen` call's actual payload — outbound `to`
  was genuinely the DB customer email in every case.
- **ThreadingHTTPServer claim in the route comment** ("a slower response
  here does not block any other in-flight request") — grepped
  `restoricon_core/api/server.py:201`, confirmed
  `ThreadingHTTPServer((self.host, self.port), CustomHandler)` is the real
  constructor used by the live entry point. Comment is accurate, not
  asserted-away; the 2.0s→15.0s change does NOT create an availability
  regression on other requests.
- **`_post_request`'s except block read in full**: `URLError` and bare
  `Exception` both `logger.warning(...)` then `return False` — not a
  silent swallow, pre-existing code, unchanged by this diff.
- **ROLE_CUSTOMER exclusion is load-bearing, not decorative**: `ROLE_CUSTOMER`
  genuinely holds `PERM_LOG_COMMUNICATION` (auth.py:578, for portal
  messages) — without the explicit role exclusion a customer actor could
  reach this staff-only route.
- **Found and live-reproduced an edge case NOT in the implementer's own
  test suite**: `ROLE_TECHNICIAN` holds `PERM_LOG_COMMUNICATION`
  (auth.py:501) but NOT `PERM_READ_ALL_CUSTOMERS` (auth.py:497-507 block) —
  so `self.crm.get_customer()`'s internal `can_access_customer()` check
  raises `PermissionError`. This is NOT caught locally in the new route
  block; it propagates to the router's outer `except PermissionError: return
  403` (routes.py:3348) — same pattern already relied on by the
  pre-existing `GET /customers/<id>` route (routes.py:829, no local
  try/except there either). Live-repro'd: 403, zero urlopen calls, no
  crash. Not a bug, but this project's routes lean on a shared outer
  exception handler for permission-vs-ownership mismatches rather than
  each route re-deriving reachability from first principles — worth
  checking for on any future customer/lead/project-scoped route: does the
  route's own explicit permission gate actually imply the callee's
  internal `can_access_customer`-style check will pass, or is it silently
  depending on the global catch?
- **NEW-623 (timeout) claim verified against the actual sibling repo**,
  not trusted: read `Codey-Aigentik/http-server.js` (`/send-email` handler
  awaits `emailProvider.sendEmail()` before responding) and
  `email-provider.js` (`sendEmail` does `await transporter.sendMail(...)`
  via real `nodemailer`) directly — confirms the pre-existing 2.0s Python
  timeout genuinely races a real blocking SMTP round trip. The new
  route's `timeout=15.0` is additive/scoped correctly (grepped every
  `send_email`/`_post_request` call site — only the new route passes a
  non-default timeout; the 3 pre-existing calalers, PM-assignment +
  2 calendar-invite paths, are untouched at 2.0s).
- `c360PanelSection`'s new `headerAction` param: grepped all 6 call sites,
  the other 5 pass only 5 args, default `''` — additive, no regression.
- `node --check` run on the ACTUAL extracted `<script>` block from a live
  `render_sales_surface()` call (not just an import-only Python check) —
  syntax OK.
- Full suite: 2398 passed, 1 skipped — matches implementer's claimed
  2383→2398 (+15) exactly, verbatim, no hang.
- Ledger note for coordinator: NEW-623 should be split on update — mark
  the compose route (B8.10c) as mitigated (15s timeout, root cause now
  confirmed not just suspected), but the 3 pre-existing call sites remain
  genuinely open at the original 2.0s, unchanged by this round. NEW-620
  already explicitly anticipated this round leaving the PM-assignment
  call site unlogged ("a separate decision on whether to backfill this
  existing internal call site") — no new NEW-### needed for that,
  re-surfacing it doesn't create a new fact.
