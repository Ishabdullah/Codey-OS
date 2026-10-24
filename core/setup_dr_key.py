"""NEW-458 commit B.1 — one-time disaster-recovery (DR) key escrow setup.

Generates a dedicated DR recipient keypair with `age-keygen`, writes ONLY
the public half into the active config file (config["restoricon"]
["dr_recipient_pubkey"]), and prints the private half to stdout exactly
once for the operator to store offline. The private key is never written
to disk, never logged, and never shown again.

This is an interactive, run-once script — it is invoked by install.sh, not
by any launcher / service_manager path (that would be non-interactive and
would drop the one-time private-key printout on the floor).

G15i: generating the key (first time AND --force) requires a per-attempt human
"y" on /dev/tty and a terminal stdout, checked before age-keygen runs or the
config is touched. The private key goes to stdout, so a captured/redirected
stdout (agent shell tool, `| tee`, a daemon) is refused outright: it would
defeat the "shown once" contract regardless of any prompt. This is a
human-presence check, not a boundary against a same-uid script. It
deliberately uses core.tty_confirm directly (no audit row, and no import of
the file-tool layer; see tests/test_filesystem_protected_paths.py).

Style mirrors core/setup_litestream.py: plain def main() + sys.exit(main()).
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))
from core import tty_confirm
from utils.config import get_config_file_path, load_user_config

_PUBKEY_RE = re.compile(r"^age1[a-z0-9]+$")


_REFUSED_NO_TTY = (
    "Refused: no human confirmation on /dev/tty (declined, unavailable or "
    "interrupted); no DR key was generated and the config is unchanged. "
    "Run it directly in a terminal: python3 core/setup_dr_key.py"
)
_REFUSED_STDOUT = (
    "Refused: stdout is not a terminal. The DR private key is printed once "
    "on stdout and must not be captured or redirected; no DR key was "
    "generated and the config is unchanged. Run it directly in a terminal: "
    "python3 core/setup_dr_key.py"
)


def _open_tty() -> int:
    """Seam: tests substitute a pty by patching this module attribute."""
    return tty_confirm.open_tty()


def _confirm_on_tty(prompt: str) -> bool:
    """Ask the human on /dev/tty (call-time seam lookup). True only for y/yes."""
    return tty_confirm.confirm_on_tty(prompt, open_tty=_open_tty)


def _stdout_is_terminal() -> bool:
    """Seam: tests/CI can inject; the real check is isatty()."""
    return sys.stdout.isatty()


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

    # G15i guard. Everything below (keygen, config write, private-key print)
    # lives in a local closure so there is no module-level function that
    # generates and stores a key without having passed this check. The
    # benign "already configured" return above never prompts.
    if not _stdout_is_terminal():
        print(_REFUSED_STDOUT, file=sys.stderr)
        return 1

    prompt = (
        "\n[HIGH IMPACT] Generate the disaster-recovery keypair.\n"
        f"  config file: {str(config_path)!a}\n"
    )
    if existing and str(existing).strip():
        prompt += (
            f"  REPLACES DR public key {str(existing).strip()!a}: every backup "
            "blob encrypted to it becomes undecryptable by the DR party\n"
        )
    prompt += (
        "  the PRIVATE key will be printed once on this terminal's stdout and "
        "is not stored anywhere\n"
        "Proceed? [y/N]: "
    )
    try:
        approved = _confirm_on_tty(prompt) is True
    except (Exception, KeyboardInterrupt):  # noqa: BLE001 - fail closed
        # Safe to swallow: every failure (no controlling terminal / ENXIO, EOF,
        # tcflush failure, Ctrl-C, unexpected error) means a human did not
        # affirmatively approve, and the only consequence of "not approved" is
        # the refusal below -- nothing has been generated or written yet.
        approved = False
    if not approved:
        print(_REFUSED_NO_TTY, file=sys.stderr)
        return 1

    def _generate_and_store() -> int:
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

    return _generate_and_store()


if __name__ == "__main__":
    sys.exit(main())
