#!/usr/bin/env python3
"""WP0.7 (CODEY_OS_MASTER_BLUEPRINT.md §21, Ish's decision 7): one-time
migration of the Cloudflare tunnel token from config.json plaintext to
~/.codeyOS/cloudflare_tunnel_token.age, age-encrypted to the device's
existing at-rest identity (core/backup_secrets.py's ~/.codeyOS/age.key --
no new key material, no rotation).

Run once from a Codey-OS checkout:
    python3 -m tools.encrypt_cloudflare_token

Refuses to overwrite an existing encrypted file without --force (same
idempotency convention as tools/provision_ai_agent_auth.py). Never
touches or deletes config.json's plaintext value -- per the blueprint's
own rollback plan, that stays in place as a fallback until the operator
confirms the encrypted path works, then removes it manually.
"""
import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))
from core.backup_secrets import get_at_rest_public_key
from utils.config import get_cloudflare_tunnel_token, load_user_config, CODEY_STATE_DIR


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="overwrite an existing encrypted file")
    args = parser.parse_args()

    out_path = CODEY_STATE_DIR / "cloudflare_tunnel_token.age"
    if out_path.exists() and not args.force:
        print(f"{out_path} already exists -- pass --force to overwrite.")
        return 0

    cfg = load_user_config()
    cf_section = cfg.get("cloudflare", {}) if isinstance(cfg, dict) else {}
    plaintext = cf_section.get("tunnel_token") if isinstance(cf_section, dict) else None
    if not plaintext or not isinstance(plaintext, str) or not plaintext.strip():
        print("No plaintext cloudflare.tunnel_token found in config.json -- nothing to encrypt.")
        return 1
    plaintext = plaintext.strip()

    pubkey = get_at_rest_public_key()
    if not pubkey:
        print("Could not derive the at-rest public key from ~/.codeyOS/age.key -- aborting.")
        return 1

    try:
        result = subprocess.run(
            ["age", "-r", pubkey, "-o", str(out_path)],
            input=plaintext, capture_output=True, text=True, timeout=10, check=True,
        )
    except (subprocess.CalledProcessError, OSError) as e:
        print(f"age encryption failed: {type(e).__name__}")
        return 1
    out_path.chmod(0o600)

    # Round-trip check with the real decrypt path before declaring success --
    # a migration that "succeeds" but can't actually be read back is worse
    # than not migrating at all (the tunnel would silently stop starting).
    import importlib
    import utils.config as config_module
    importlib.reload(config_module)
    roundtrip = config_module.get_cloudflare_tunnel_token()
    if roundtrip != plaintext:
        out_path.unlink(missing_ok=True)
        print("Round-trip verification failed -- decrypted value did not match. Aborting, nothing written.")
        return 1

    print(f"Encrypted token written to {out_path} (mode 600), verified by decrypting it back.")
    print("config.json's plaintext cloudflare.tunnel_token was NOT touched.")
    print("Once you've confirmed the tunnel starts correctly with this file in place,")
    print("remove the plaintext tunnel_token value from config.json yourself.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
