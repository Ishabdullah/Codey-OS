"""NEW-458 commit B.1 — one-time disaster-recovery (DR) key escrow setup.

Generates a dedicated DR recipient keypair with `age-keygen`, writes ONLY
the public half into the active config file (config["restoricon"]
["dr_recipient_pubkey"]), and prints the private half to stdout exactly
once for the operator to store offline. The private key is never written
to disk, never logged, and never shown again.

This is an interactive, run-once script — it is invoked by install.sh, not
by any launcher / service_manager path (that would be non-interactive and
would drop the one-time private-key printout on the floor).

Style mirrors core/setup_litestream.py: plain def main() + sys.exit(main()).
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))
from utils.config import get_config_file_path, load_user_config

_PUBKEY_RE = re.compile(r"^age1[a-z0-9]+$")


def _generate_keypair():
    """Run age-keygen and return (public_key, private_key) parsed from its
    stdout in memory. Never writes a temp file. On any failure, raises
    RuntimeError WITHOUT echoing captured output — age-keygen puts the
    secret key in stdout, so surfacing stdout/stderr here would leak it.
    """
    try:
        result = subprocess.run(
            ["age-keygen"], capture_output=True, text=True, check=True
        )
    except (subprocess.CalledProcessError, OSError) as e:
        # Deliberately does NOT include e.stdout/e.stderr or str(e) beyond
        # the class name: a CalledProcessError's captured stdout contains
        # the AGE-SECRET-KEY line. Safe to swallow the detail because the
        # only actionable outcome is "age-keygen failed, nothing was
        # written" and the caller exits non-zero.
        raise RuntimeError(
            f"age-keygen failed ({type(e).__name__}); no DR key generated."
        ) from None

    public_key = None
    private_key = None
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("# public key:"):
            public_key = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("AGE-SECRET-KEY-"):
            private_key = stripped

    if not public_key or not private_key:
        raise RuntimeError(
            "age-keygen output did not contain the expected key lines; "
            "no DR key configured."
        )
    return public_key, private_key


def _print_handoff(private_key: str) -> None:
    print()
    print("=" * 72)
    print("  DISASTER-RECOVERY PRIVATE KEY — SHOWN ONCE, NEVER AGAIN")
    print("=" * 72)
    print()
    print("  " + private_key)
    print()
    print("  Store this key OFFLINE now — a password manager or a printed copy")
    print("  in a safe. It is NOT written to disk anywhere on this device and")
    print("  will NOT be displayed again.")
    print()
    print("  It is not needed on this device in normal operation. Its only job")
    print("  is to decrypt the encrypted backups in gs://<backup-bucket> after")
    print("  total device loss.")
    print()
    print("  Escrow ALONGSIDE this key a GCS credential that can READ the")
    print("  backup bucket (currently a copy of ~/.codeyOS/gcp_credentials.json;")
    print("  long-term a read-only service account). The backup blob contains")
    print("  the credentials, so you cannot fetch the blob without a separate")
    print("  credential kept next to this key.")
    print()
    print("=" * 72)
    print()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate and escrow the disaster-recovery backup key (run once)."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "Regenerate the DR keypair even if one is already configured. "
            "Every backup blob encrypted to the OLD DR key becomes "
            "undecryptable by the DR party (orphaned) — only do this "
            "deliberately."
        ),
    )
    args = parser.parse_args()

    config_path = get_config_file_path()
    config = load_user_config()

    restoricon = config.get("restoricon")
    if not isinstance(restoricon, dict):
        restoricon = {}
    existing = restoricon.get("dr_recipient_pubkey")

    if existing and str(existing).strip() and not args.force:
        print(
            "A DR recipient public key is already configured "
            f"({str(existing).strip()}).\n"
            "Nothing to do. Re-run with --force to regenerate (this orphans "
            "every backup blob encrypted to the current DR key)."
        )
        return 1

    if existing and str(existing).strip() and args.force:
        print(
            "--force: regenerating the DR keypair. Backup blobs encrypted to "
            f"the previous DR key ({str(existing).strip()}) will no longer be "
            "decryptable by the DR party."
        )

    try:
        public_key, private_key = _generate_keypair()
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    if not _PUBKEY_RE.match(public_key):
        print(
            f"ERROR: parsed public key is not a valid age recipient; "
            "no DR key configured.",
            file=sys.stderr,
        )
        return 1

    # Read-modify-write: preserve every existing key, including the other
    # keys inside config["restoricon"] (db_path, api_port, doc_store_path…).
    config.setdefault("restoricon", {})
    if not isinstance(config["restoricon"], dict):
        config["restoricon"] = {}
    config["restoricon"]["dr_recipient_pubkey"] = public_key

    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
        f.write("\n")

    print(f"DR recipient public key written to {config_path}")
    print(f"  restoricon.dr_recipient_pubkey = {public_key}")

    _print_handoff(private_key)
    return 0


if __name__ == "__main__":
    sys.exit(main())
