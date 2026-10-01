"""
provision_ai_agent_auth.py — one-off Restoricon Core auth provisioning
for an `ai_agent`-role caller (e.g. Codey-Aigentik's do-not-contact.js
write-through pilot, CODEY_MASTER_PLAN.md §6.4 task 4).

Named without "token" in the filename deliberately: this repo's
.gitignore has a broad `*token*` pattern (meant to keep actual secret
files out of version control) that would otherwise silently exclude
this source file from git entirely.

Creates (or reuses, if already present) a single `ai_agent` user in the
Core's real persistent DB (`restoricon_core.database.DEFAULT_DB_PATH`,
overridable via `RESTORICON_DB_PATH` like the rest of `restoricon_core`)
and issues a fresh bearer token for it. Connecting a `DatabaseManager` to
that path creates the schema via `CREATE TABLE IF NOT EXISTS` if it
doesn't exist yet — this script does not start the HTTP API server itself,
since token issuance only needs direct DB access (there is no HTTP route
for creating users, by design — see `restoricon_core/api/routes.py`).

The printed token is a secret. This script never writes it to any
Codey-OS-tracked file; the caller is responsible for putting it in
`~/Codey-Aigentik/config.json`'s `core_api.token` field (gitignored,
never committed).

Usage:
    python -m tools.provision_ai_agent_auth [--username NAME] [--email EMAIL]

Idempotent: re-running with the same --username reuses the existing user
and revokes every prior unrevoked token for that user before issuing a
fresh one (NEW-227) — so a rerun never leaves more than one live token
for the same `ai_agent` identity. Revoke-then-reissue was chosen over
reusing an existing unexpired token because `restoricon_core/auth.py`'s
`AuthService` has no "look up existing valid token(s) for a user" query
(only `revoke_token(token)`, which takes a specific token string); this
script already reads `api_tokens` directly (see `provision()`), so
querying then revoking each pre-existing, non-revoked token id for the
user via the existing per-token `revoke_token()` call is the smaller
addition, with no new `AuthService` method needed.

**Operational consequence of this behavior change:** rerunning this
script now invalidates whatever token is currently deployed (e.g. the
one pasted into `~/Codey-Aigentik/config.json`'s `core_api.token`
field) immediately, not just "eventually on its own expiry schedule."
`do-not-contact.js` is Core-only with no local-file fallback and throws
on a failed Core call by design, so a casual rerun without immediately
updating that deployed config with the freshly-printed token will break
the do-not-contact write-through path until it's updated. This was not
a risk before this fix (old tokens were left valid) and is a real
tradeoff of closing NEW-227, not an oversight.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Dict, Optional

from restoricon_core.auth import (
    PERM_GLOBAL_SEARCH,
    PERM_READ_ALL_CUSTOMERS,
    PERM_READ_CRM,
    PERM_READ_ESTIMATE_COSTS,
    PERM_READ_FINANCIALS,
    PERM_READ_LEADS,
    PERM_READ_OPPORTUNITIES,
    PERM_READ_TEAM_COMMISSIONS,
    PERM_READ_TEAM_SALES_DATA,
    PERM_VIEW_REPORTS,
    ROLE_AI_AGENT,
    ROLE_PERMISSIONS,
    AuthService,
    _validate_custom_permissions,
    utc_now_iso,
)
from restoricon_core.database import DatabaseManager

DEFAULT_USERNAME = "codey-aigentik-agent"
DEFAULT_EMAIL = "codey-aigentik-agent@local.invalid"

# CODEY_MASTER_PLAN.md 12.x Part B: a second, deliberately separate
# ai_agent identity for CCOS's new read-only CRM query plugin
# (ccos/plugins/crm/core_query/) -- a DISTINCT username from
# DEFAULT_USERNAME/codey-aigentik-agent is required because provision()
# revokes every prior unrevoked token for a given username on each rerun
# (NEW-227); reusing Aigentik's username here would silently kill its
# live write-through token.
CRM_READER_USERNAME = "codey-ccos-crm-reader"
CRM_READER_EMAIL = "codey-ccos-crm-reader@local.invalid"

# Permissions that MUST stay granted for the CRM read capabilities
# (ccos/plugins/crm/core_query/) to work at all -- most notably
# PERM_READ_TEAM_SALES_DATA: crm_service.py's _scoped_assignee_filter
# forces any actor WITHOUT this permission to actor.user_id-only scoping,
# so denying it would not error, it would silently narrow every
# cross-rep query to empty/own-only results. Asserted against the
# computed deny-list below so a future edit here can never deny one of
# these by accident.
_CRM_READER_MUST_NOT_DENY = frozenset({
    PERM_READ_LEADS,
    PERM_READ_OPPORTUNITIES,
    PERM_READ_CRM,
    PERM_READ_ALL_CUSTOMERS,
    PERM_READ_TEAM_SALES_DATA,
})

# Read permissions ROLE_AI_AGENT holds that are explicitly denied for this
# narrower, read-only-CRM identity even though they're not write/manage --
# they mix RBAC tiers or carry financial/commission data this token should
# never see (CODEY_MASTER_PLAN.md 12.x Part B).
_CRM_READER_EXTRA_DENY = frozenset({
    PERM_VIEW_REPORTS,
    PERM_READ_TEAM_COMMISSIONS,
    PERM_READ_FINANCIALS,
    PERM_READ_ESTIMATE_COSTS,
    PERM_GLOBAL_SEARCH,
})


def _compute_crm_reader_deny_permissions() -> Dict[str, bool]:
    """Derive the CRM-reader deny-list from ROLE_PERMISSIONS[ROLE_AI_AGENT]
    directly (never a hardcoded literal copy, so it can't silently drift
    out of sync if that grant changes later -- same reasoning as
    restoricon_core/auth.py's own ROLE_SALES-derived sales_manager grant).

    Denies every permission whose string starts with the "write:" or
    "manage:" verb prefix (restoricon_core/auth.py's own naming
    convention), PLUS "score:leads"/"dispatch:work_orders"/
    "log:communication" -- three ROLE_AI_AGENT grants that are
    write-capable (run/persist an action) despite not using either
    prefix (verified directly against PERMISSIONS_CATALOG's descriptions,
    not assumed) -- PLUS _CRM_READER_EXTRA_DENY's five read permissions.

    Denying "score:leads" does not break crm.score_lead: crm_service.py's
    score_lead() permission check is
    `SCORE_LEADS or WRITE_LEADS or READ_LEADS or READ_CRM`, and
    PERM_READ_LEADS/PERM_READ_CRM both stay granted.
    """
    write_or_manage = {
        p for p in ROLE_PERMISSIONS[ROLE_AI_AGENT]
        if p.startswith("write:") or p.startswith("manage:")
    }
    action_write_capable = {"score:leads", "dispatch:work_orders", "log:communication"} & ROLE_PERMISSIONS[ROLE_AI_AGENT]
    deny = write_or_manage | action_write_capable | _CRM_READER_EXTRA_DENY
    assert not (deny & _CRM_READER_MUST_NOT_DENY), (
        "CRM-reader deny-list must never include a must-not-deny permission: "
        f"{deny & _CRM_READER_MUST_NOT_DENY}"
    )
    return {p: False for p in deny}


CRM_READER_DENY_PERMISSIONS: Dict[str, bool] = _compute_crm_reader_deny_permissions()


def provision(
    username: str = DEFAULT_USERNAME,
    email: str = DEFAULT_EMAIL,
    db_path: str | None = None,
    custom_permissions: Optional[Dict[str, bool]] = None,
) -> str:
    """Create (or reuse) the ai_agent user and return a fresh bearer token.

    `db_path` defaults to `restoricon_core.database.DEFAULT_DB_PATH` (the
    real persistent Core DB) when not given — tests pass an explicit
    `:memory:` or scratch path instead so they never touch that file.

    `custom_permissions`, when given, is validated against
    `PERMISSIONS_CATALOG` (`_validate_custom_permissions()`, raises
    `ValueError` on an unknown key) and applied to the user's
    `custom_permissions_json` on every call — both on first creation and
    on every subsequent rerun for an already-existing user — so a
    deny-list identity like `CRM_READER_USERNAME` can never drift back
    toward the bare `ROLE_AI_AGENT` grant just because a rerun's reuse
    path happened to skip re-applying it.
    """
    if custom_permissions is not None:
        _validate_custom_permissions(custom_permissions)

    db = DatabaseManager(db_path) if db_path is not None else DatabaseManager()
    try:
        auth = AuthService(db)
        conn = db.get_connection()
        row = conn.execute("SELECT * FROM users WHERE username = ?;", (username.strip().lower(),)).fetchone()
        if row is None:
            # A random, never-used password: this identity authenticates via
            # bearer token only, never via username/password login.
            import secrets

            full_name = (
                "Codey-Aigentik (ai_agent)" if username == DEFAULT_USERNAME else f"{username} (ai_agent)"
            )
            user = auth.create_user(
                username=username,
                plain_password=secrets.token_urlsafe(32),
                full_name=full_name,
                email=email,
                role=ROLE_AI_AGENT,
                custom_permissions=custom_permissions,
            )
        else:
            from restoricon_core.models import User

            user = User(
                id=row["id"],
                username=row["username"],
                password_hash=row["password_hash"],
                full_name=row["full_name"],
                email=row["email"],
                phone=row["phone"],
                role=row["role"],
                department=row["department"],
                customer_id=row["customer_id"],
                active=row["active"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            if user.role != ROLE_AI_AGENT:
                raise ValueError(
                    f"User '{username}' already exists with role '{user.role}', not '{ROLE_AI_AGENT}'"
                )
            # Revoke every prior unrevoked token for this user before issuing
            # a new one, so reruns don't accumulate live credentials
            # (NEW-227). No bulk-revoke method exists on AuthService, so
            # revoke each one individually via the existing per-token API.
            stale_tokens = conn.execute(
                "SELECT token FROM api_tokens WHERE user_id = ? AND is_revoked = 0;",
                (user.id,),
            ).fetchall()
            for stale_row in stale_tokens:
                auth.revoke_token(stale_row["token"])
            if stale_tokens:
                # Loud on the actual footgun path (code-reviewer finding,
                # 2026-08-27): the docstring warns about this, but a normal
                # run only ever printed the new token to stdout -- nothing
                # said the old one just died. do-not-contact.js/
                # email-rules.js/sms-rules.js are Core-only with no local
                # fallback, so an old deployed token going dead silently
                # breaks their write-through until the new one is pasted
                # into config.json.
                print(
                    f"Revoked {len(stale_tokens)} prior token(s) for "
                    f"'{username}' -- update every deployed config.json's "
                    f"core_api.token now, or its write-through calls will "
                    f"start failing.",
                    file=sys.stderr,
                )
            if custom_permissions is not None:
                # Reapply the deny-list on every rerun for an already-
                # existing user too, so it can never silently drift back
                # toward the bare ROLE_AI_AGENT grant. AuthService's own
                # set_user_permissions() requires an actor_context holding
                # PERM_MANAGE_USERS (auth.py:1684) -- this script already
                # operates with direct, trusted DB access (see module
                # docstring: there is no HTTP route for user provisioning
                # by design), so it writes custom_permissions_json directly
                # via the connection it already holds, after the same
                # _validate_custom_permissions() check set_user_permissions
                # itself would run, rather than constructing a throwaway
                # admin AuthContext just to satisfy that RBAC check.
                with conn:
                    conn.execute(
                        "UPDATE users SET custom_permissions_json = ?, updated_at = ? WHERE id = ?;",
                        (json.dumps(custom_permissions), utc_now_iso(), user.id),
                    )
        return auth.create_token(user)
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", default=DEFAULT_USERNAME)
    parser.add_argument("--email", default=DEFAULT_EMAIL)
    parser.add_argument("--db-path", default=None, help="Override the Core DB path (defaults to the real persistent DB)")
    args = parser.parse_args()

    # Mechanical, not a generic flag: this specific, hardcoded username
    # gets the hardcoded CRM-reader deny-list (and a sane default email,
    # if the caller didn't override it) automatically. Deliberately not
    # exposed as a general --custom-permissions CLI flag -- see
    # CODEY_MASTER_PLAN.md 12.x Part B.
    is_crm_reader = args.username.strip().lower() == CRM_READER_USERNAME
    custom_permissions = CRM_READER_DENY_PERMISSIONS if is_crm_reader else None
    email = CRM_READER_EMAIL if (is_crm_reader and args.email == DEFAULT_EMAIL) else args.email

    token = provision(args.username, email, db_path=args.db_path, custom_permissions=custom_permissions)
    print(token)
    return 0


if __name__ == "__main__":
    sys.exit(main())
