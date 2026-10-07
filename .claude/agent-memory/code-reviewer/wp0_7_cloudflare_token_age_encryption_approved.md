---
name: wp0-7-cloudflare-token-age-encryption-approved
description: WP0.7 Cloudflare tunnel token moved from config.json plaintext to age-encrypted ~/.codeyOS/cloudflare_tunnel_token.age — APPROVED, clean pass
metadata:
  type: project
---

Reviewed 2026-10-07 (WP0.7, blueprint §21 decision 7). `utils/config.py`'s
`_decrypt_cloudflare_tunnel_token_file()` + `get_cloudflare_tunnel_token()`
precedence update, `tools/encrypt_cloudflare_token.py` one-time migration
script, `tests/test_wp0_7_cloudflare_token_encryption.py` (6 tests).
**APPROVED** — rare clean pass, no criticals.

Key verification technique: the described bug (explicit `config=` test
getting silently overridden by the real on-disk `.age` file) was fixed by
gating the encrypted-file check on `if config is None:`. I didn't just
trust that claim — grepped every call site in
`tests/test_service_manager_config.py` that passes `config=` (lines 82,
87, 93, 97, 101, 105) and confirmed all are explicit-config calls, so all
correctly skip the encrypted path. Ran the actual pytest file
(`24 passed`) plus the combined set with the new test file and
`test_backup_secrets.py` (`38 passed`) — verbatim output, not "tests
pass."

Also live-verified on the real device (not just code-read): real
`~/.codeyOS/cloudflare_tunnel_token.age` + `age.key` exist at mode 600;
real repo `config.json` (gitignored) has no plaintext token, only a
`_note`; `get_cloudflare_tunnel_token()` called with zero args returns a
real decrypted 184-char token; `lib/service_manager.sh`'s
`show_service_config()` python body (run directly, not via bash) reports
"configured" with no credential in the redacted raw dump.

No caching anywhere in `utils/config.py` (checked via grep for
`cache|lru_cache|functools`) — so the migration script's
`importlib.reload(config_module)` before its round-trip check, while
technically unnecessary, is harmless; nothing to bust.

Two **non-blocking** suggestions logged back to implementer, not bugs:
1. `_decrypt_cloudflare_tunnel_token_file()`'s except clause doesn't
   catch `UnicodeDecodeError` from `text=True` if `age -d` succeeds but
   emits non-UTF-8 stdout. Unreachable today (only ASCII tokens are ever
   encrypted via this path) but worth flagging if this helper is ever
   reused for other secret types.
2. The migration script's round-trip check calls
   `get_cloudflare_tunnel_token()` with no args, which goes through the
   *full* precedence chain including the env-var check first — if
   `CLOUDFLARE_TUNNEL_TOKEN` happens to be set in the operator's shell
   during a migration run, the round-trip compares against the env value
   instead of the just-decrypted file. Safe-fail only (aborts or
   coincidentally passes), not a security hole, but worth a comment or an
   explicit env-clear if this script is ever re-run on a dirty shell.

New project-specific pattern for future "move a plaintext secret behind
an existing at-rest encryption mechanism" tasks: the right precedence-gate
discriminator is "was `config` passed explicitly, or is this the real
zero-arg production call" — explicit-arg call sites are deliberate test
scenarios and must never have a real on-disk secret silently leak into
them. Check this gate by grepping every call site that passes the
parameter explicitly, not just the one call site the bug report named.
