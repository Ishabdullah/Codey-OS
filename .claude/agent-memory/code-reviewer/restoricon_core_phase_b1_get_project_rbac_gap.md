---
name: restoricon_core_phase_b1_get_project_rbac_gap
description: Phase B1 Restoricon Core (auth.py/crm_service.py/api/server.py+routes.py) review round 1 — crypto/binding/injection/audit clean, blocked on implicit-permission RBAC gap in project reads
metadata:
  type: project
---

Round 1 review of Track B / Phase B1 (`restoricon_core/`), CODEY_MASTER_PLAN.md
§6.3. Verdict: CHANGES REQUESTED.

**What was clean (all independently verified, not just claimed):**
- PBKDF2-HMAC-SHA256, 100k iterations, real per-user `os.urandom(16)` salt,
  `hmac.compare_digest` verification (auth.py).
- `secrets.token_urlsafe(32)` tokens, revocation empirically re-tested and
  actually blocks re-auth.
- Server binds to `(host, port)` directly, no hardcoded 0.0.0.0; default is
  127.0.0.1:8770.
- All SQL is parameterized (`?`), including LIKE search-term construction.
- audit_log / communication_history genuinely INSERT-only — grepped for
  UPDATE/DELETE against those tables across all service files, found none.
- Thread-local sqlite connections + WAL mode, reasonable.
- stdlib-only (hashlib/hmac/secrets/sqlite3/http.server) — install.sh rule 11
  needs no update, confirmed by import grep.
- 11/11 scoped tests + 682/1 full suite passed, pasted verbatim.

**The bug (Critical, blocking):** `crm_service.py`'s `get_project()` and
`list_projects()` only special-case `ROLE_CUSTOMER` and `ROLE_TECHNICIAN`;
every other role falls through with **zero** `has_permission()` call — unlike
every other entity's read methods (`get_customer`/`list_customers` etc, which
correctly call `can_access_customer()`/`has_permission()`). Proved this
empirically by constructing a fake actor object whose `has_permission()`
always returns False and calling both methods directly — both returned full
project data with no PermissionError. Not currently live-exploitable only
because today's fixed 7-role `ROLE_PERMISSIONS` matrix happens to grant every
non-customer/non-technician role project-read permission anyway — one matrix
edit or new role away from a silent bypass, with no code path to catch it.

**Technique worth reusing:** when a service method branches on role identity
via `if actor.role == X` instead of `actor.has_permission(...)`, don't just
read the current role matrix and conclude "no gap today" — construct a
zero-permission fake actor and call the method directly. This is a cheap,
decisive way to prove/disprove an implicit-permission gap without needing to
wait for a future role to be added.

**Non-blocking findings logged, not yet added to NEW_ISSUES.md by me (task
told me not to fix, only to flag for the implementer's follow-up pass):**
`RESTORICON_API_HOST` env var can set bind host to 0.0.0.0 with zero warning
(same shape as this project's known C-2 GUI finding — see
[[gui_c2_remediation_sequence]]); generic 500 handler leaks raw exception
text to client; `sign_contract`'s PERM_SIGN_CONTRACTS is only granted to
admin+customer in the role matrix (manager/sales/PM can't sign) — flagged as
a business-rule question, not a security bug; several entities have POST but
no GET routes yet (incomplete, not insecure).
