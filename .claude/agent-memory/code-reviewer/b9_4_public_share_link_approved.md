---
name: b9_4_public_share_link_approved
description: B9.4 public unauthenticated share-link routes (estimate view/decision by raw token) — full adversarial review, APPROVED
metadata:
  type: project
---

B9.4 (2026-09-29/30) added the FIRST genuinely unauthenticated, customer-facing
API surface to `restoricon_core`: `/api/v1/public/estimate/{raw_token}[/decision]`,
resolving `estimate_share_links` rows B9.2's `transition()` `send` step created.
Files: `restoricon_core/services/estimate_service.py` (`resolve_share_link()`,
`record_share_link_view()`, `_deliver_share_link()`, `transition()`'s
`share_link_out` out-param, `record_decision()`'s new
`_DECISION_BLOCKED_STATUSES` terminal guard), `restoricon_core/api/routes.py`
(new public route block + second per-share-link-id `RateLimiter`),
`restoricon_core/api/server.py` (wires `notification_service` into
`EstimateService`), `tests/test_restoricon_core/test_b9_4_public_share_link.py`
(24 tests, all passed).

**Verdict: APPROVED.** Every one of 11 specifically-flagged risk areas was
independently verified by reading the actual code (not the implementer's
claims) and, where feasible, live-executing:

- Anti-oracle 404: confirmed byte-identical `{"error": "Not found"}` for
  nonexistent/expired/revoked tokens; route block is nested inside the
  existing `/api/v1/public/` handling (checked *before* the
  Authorization/`?token=` bearer-auth resolution logic later in the same
  function) and every branch inside the block returns explicitly — never
  falls through to the generic catch-all `f"Not found: {method} {path}"` 404
  that would echo the raw token back into a response/log.
- Token lookup: SHA-256 hash, `UNIQUE INDEX idx_estimate_share_links_token_hash`
  (confirmed in `database.py`), equality lookup — no raw-token `==`, no scan.
  Raw token never attached to `EstimateShareLink` dataclass (confirmed no such
  field exists), never audit-logged (audit payloads only carry `share_link_id`
  + delivery metadata).
- Second rate limiter genuinely keyed on the resolved row's `link.id` (a real
  int, only assignable post-lookup-success) not on caller-supplied token/IP —
  confirmed this can't be grown by guessing invalid tokens. Outer per-IP
  limiter (`self.rate_limiter`, keyed on `client_ip`) still wraps the whole
  `/api/v1/public/` block including this new route family.
- `_deliver_share_link()` genuinely runs after `transition()`'s own
  `with conn: BEGIN IMMEDIATE` block exits (confirmed by indentation: the
  call is at the same nesting level as the post-commit `after_row = conn.execute(...)`
  read, not inside the `with conn:` block) — a failed/skipped send never
  rolls back or blocks the `send` transition; share-link row + raw token
  already exist and are already in `share_link_out` regardless.
- Public decision route: `customer_user_id` is never read from the request
  body at all (grep-confirmed, only `share_link_id=link.id` is passed to
  `record_decision()`). `record_decision()`'s own XOR guard
  (`(share_link_id is None) == (customer_user_id is None)`) is real, and is
  read+enforced *inside* the same `with conn: BEGIN IMMEDIATE` block as the
  actual INSERT — TOCTOU-safe. The test asserting this
  (`test_public_decision_ignores_client_supplied_customer_user_id`) genuinely
  asserts against the persisted DB row (`SELECT customer_user_id, share_link_id
  FROM estimate_decisions WHERE id = ?`), not just HTTP status — this matters,
  a status-only test would pass even if the field were silently accepted.
- `_DECISION_BLOCKED_STATUSES` blocklist (not allowlist) reasoning verified
  against the actual pre-existing B9.2 test
  (`test_record_decision_declined_and_changes_requested_do_not_lock`,
  `test_b9_2_estimate_service.py:438`): that test calls `record_decision()`
  twice against an estimate that's still `DRAFT` at call time (never
  transitioned through SENT) — confirms DRAFT must stay unblocked and the
  blocklist shape is the only one that doesn't break it.
- `record_share_link_view()`'s `SENT -> VIEWED` flip uses a genuine
  conditional `UPDATE ... WHERE workflow_status = 'SENT'`, `rowcount == 0`
  correctly treated as an expected no-op (second-plus view), not an error —
  confirmed by test asserting no exception + `view_count` still increments on
  repeat views.
- NEW-720 (GET route doesn't re-check CANCELLED, only decision route does)
  verified genuine by reading `CustomerEstimateView.to_dict()`
  (`codey_estimator/dto.py:184`) directly — confirmed it carries no
  `workflow_status` field and no cost/margin fields, so the disclosed
  "low-moderate, stale-but-harmless" severity is accurate, not a data leak.
- NEW-721 (`current_link_url` structurally impossible) verified genuine —
  `EstimateShareLink` dataclass (models.py:749) has no raw-token field by
  design, confirming there is truly no persisted path to reconstruct it.
- Email body (`_deliver_share_link()`) contains only greeting/share-url/expiry
  — no cost/margin/other-customer data.
- Ledger (`NEW_ISSUES.md`): NEW-712 resolved cleanly, NEW-715 correction is
  honest (updates a stale "none today" to the now-real consequence and
  cross-references NEW-720 rather than duplicating it), NEW-720/721 each
  appear exactly once, no duplicate numbering.

**Test count discrepancy worth recording (not a blocker):** implementer
claimed "1442 passed"; live run got "1441 passed, 1 error" — a
`PermissionError: [Errno 1] Operation not permitted` on `socket.bind()` in
`test_api.py::test_api_business_profile_singleton`, a real HTTPServer-binding
test unrelated to this diff's files. Confirmed via `git stash` that this same
test passes in isolation both with and without the diff — this is a
full-suite-only, environment-level flakiness (Termux sandbox intermittently
refuses a socket bind under load), not a regression introduced by B9.4. Same
category as [[sandbox_http_proxy_urllib_405_env_artifact]] and
[[test_resource_bus_aging_flaky_under_load]] — always reproduce the claimed
number yourself rather than trusting it, and isolate-and-rerun before
crediting a full-suite anomaly to the diff under review.

Files to stage for commit: `NEW_ISSUES.md`, `restoricon_core/api/routes.py`,
`restoricon_core/api/server.py`, `restoricon_core/services/estimate_service.py`,
`tests/test_restoricon_core/test_b9_4_public_share_link.py` (new, untracked).
