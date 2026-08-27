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
import sys

from restoricon_core.auth import ROLE_AI_AGENT, AuthService
from restoricon_core.database import DatabaseManager

DEFAULT_USERNAME = "codey-aigentik-agent"
DEFAULT_EMAIL = "codey-aigentik-agent@local.invalid"


def provision(username: str = DEFAULT_USERNAME, email: str = DEFAULT_EMAIL, db_path: str | None = None) -> str:
    """Create (or reuse) the ai_agent user and return a fresh bearer token.

    `db_path` defaults to `restoricon_core.database.DEFAULT_DB_PATH` (the
    real persistent Core DB) when not given — tests pass an explicit
    `:memory:` or scratch path instead so they never touch that file.
    """
    db = DatabaseManager(db_path) if db_path is not None else DatabaseManager()
    try:
        auth = AuthService(db)
        conn = db.get_connection()
        row = conn.execute("SELECT * FROM users WHERE username = ?;", (username.strip().lower(),)).fetchone()
        if row is None:
            # A random, never-used password: this identity authenticates via
            # bearer token only, never via username/password login.
            import secrets

            user = auth.create_user(
                username=username,
                plain_password=secrets.token_urlsafe(32),
                full_name="Codey-Aigentik (ai_agent)",
                email=email,
                role=ROLE_AI_AGENT,
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
        return auth.create_token(user)
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", default=DEFAULT_USERNAME)
    parser.add_argument("--email", default=DEFAULT_EMAIL)
    parser.add_argument("--db-path", default=None, help="Override the Core DB path (defaults to the real persistent DB)")
    args = parser.parse_args()

    token = provision(args.username, args.email, db_path=args.db_path)
    print(token)
    return 0


if __name__ == "__main__":
    sys.exit(main())
