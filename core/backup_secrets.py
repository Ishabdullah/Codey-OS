"""NEW-458 commit B.2 — encrypted off-device backup of the irrecoverable secrets.

Tars the small set of files that cannot be regenerated after device loss
(the age identity key, the Vertex credential, the active config, the GCS
credential), age-encrypts the tar to TWO recipients — the at-rest key's
own public key AND the disaster-recovery (DR) escrow public key from
core/setup_dr_key.py — and uploads it to the backup bucket.

Fails closed: if the DR recipient pubkey is missing / malformed, this
exits non-zero BEFORE creating any tar or touching GCS. A silent
single-recipient fallback here would look successful while producing a
blob only the (lost) device can decrypt — the NEW-259 / b0d2d86 trap.

The plaintext tar is written 0600 inside a fresh mkdtemp() dir (never
$HOME) and the whole dir is removed unconditionally in a finally block.

Style mirrors core/setup_litestream.py: plain script, def + sys.exit(main()).
"""

import json
import logging
import os
import re
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

from google.cloud import storage

sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))
from utils.config import get_config_file_path, load_user_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

_PUBKEY_RE = re.compile(r"^age1[a-z0-9]+$")

GCS_BLOB_PATH = "restoricon/secrets_backup/secrets.tar.gz.age"


def get_at_rest_public_key():
    """Derive the at-rest recipient pubkey from ~/.codeyOS/age.key, using the
    same stdin idiom as core/backup_documents.py:get_public_key(). Returns
    None on failure (caller fails closed).
    """
    key_path = os.path.expanduser("~/.codeyOS/age.key")
    if not os.path.exists(key_path):
        logging.error(f"At-rest identity key not found at {key_path}")
        return None
    try:
        with open(key_path, "rb") as f:
            # capture_output=True so a malformed-key error message on
            # age-keygen's stderr never inherits into $LITESTREAM_LOG_FILE
            # (W4/W5 — risk of key-material fragments in a local log).
            result = subprocess.run(
                ["age-keygen", "-y"],
                stdin=f,
                capture_output=True,
                text=True,
                check=True,
            )
        pubkey = result.stdout.strip()
    except (subprocess.CalledProcessError, OSError) as e:
        # Log the exception TYPE only — never e / e.stderr / e.output, any
        # of which could carry fragments of the identity key.
        logging.error("could not derive at-rest public key from age.key (%s)", type(e).__name__)
        return None
    if not _PUBKEY_RE.match(pubkey):
        logging.error("Derived at-rest public key is not a valid age recipient")
        return None
    return pubkey


def get_bucket_name(config):
    # Same precedence as core/setup_litestream.py:15-17 — env var wins over
    # config so the two backups can't target different buckets (W1).
    bucket = os.environ.get("GCS_BACKUP_BUCKET")
    if not bucket:
        bucket = config.get("gcs_backup_bucket", "codey-os-backups")
    return bucket


def _term_handler(signum, frame):
    # service_manager.sh runs this script under `timeout`, which sends
    # SIGTERM on expiry. Python's default SIGTERM disposition kills the
    # process WITHOUT unwinding the stack, which would skip the finally
    # block that deletes the 0600 plaintext-secrets tar. Raising SystemExit
    # forces the unwind so cleanup still runs.
    raise SystemExit(1)


def main() -> int:
    # Restore the previous SIGTERM disposition on the way out (W3): tests
    # call main() in-process, and a leaked process-global handler would
    # follow into the pytest session.
    old_sigterm = signal.signal(signal.SIGTERM, _term_handler)
    try:
        return _run()
    finally:
        signal.signal(signal.SIGTERM, old_sigterm)


def _run() -> int:
    config = load_user_config()

    # ── Fail closed on the DR recipient pubkey, before any tar / GCS work ──
    restoricon = config.get("restoricon")
    if not isinstance(restoricon, dict):
        restoricon = {}
    dr_pubkey = str(restoricon.get("dr_recipient_pubkey") or "").strip()
    if not _PUBKEY_RE.match(dr_pubkey):
        logging.error(
            "restoricon.dr_recipient_pubkey is missing or malformed — refusing "
            "to write a backup only this device could decrypt. Run "
            "`python3 core/setup_dr_key.py` and escrow the printed private key."
        )
        return 1

    at_rest_pubkey = get_at_rest_public_key()
    if not at_rest_pubkey:
        logging.error("Cannot derive the at-rest recipient pubkey — aborting.")
        return 1

    codey_os_dir = Path.home() / ".codeyOS"
    backup_files = [
        get_config_file_path(),
        codey_os_dir / "gcp_credentials.json",
        codey_os_dir / "age.key",
        codey_os_dir / "vertex-express.json",
    ]
    present = []
    for f in backup_files:
        if f.exists():
            present.append(f)
        else:
            logging.warning(f"Skipping {f} — does not exist")
    if not present:
        logging.error("None of the backup source files exist — nothing to back up.")
        return 1

    cred_path = codey_os_dir / "gcp_credentials.json"
    if cred_path.exists():
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(cred_path)

    bucket_name = get_bucket_name(config)

    work_dir = tempfile.mkdtemp(prefix="codey-secrets-backup-")
    try:
        tar_path = os.path.join(work_dir, "secrets.tar.gz")
        enc_path = os.path.join(work_dir, "secrets.tar.gz.age")

        with tarfile.open(tar_path, "w:gz") as tar:
            for f in present:
                tar.add(str(f), arcname=f.name)
        os.chmod(tar_path, 0o600)  # don't trust umask for a cleartext-secrets file

        # BOTH recipients — a dropped -r silently makes the blob
        # undecryptable by one party.
        subprocess.run(
            ["age", "-r", at_rest_pubkey, "-r", dr_pubkey, "-o", enc_path, tar_path],
            check=True,
        )

        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(GCS_BLOB_PATH)
        blob.upload_from_filename(enc_path)

        logging.info(
            f"Secrets backup uploaded to gs://{bucket_name}/{GCS_BLOB_PATH} "
            f"({len(present)} file(s), 2 recipients)."
        )
        return 0
    finally:
        # Unconditional: removes both the plaintext .tar.gz and the .age,
        # whether we succeeded or raised mid-way. NOT ignore_errors — a
        # failure to delete a cleartext-credentials dir is safety-relevant
        # and must be logged loudly, never swallowed, so an operator can
        # remove it by hand.
        try:
            shutil.rmtree(work_dir)
        except OSError as e:
            logging.error(
                f"FAILED to remove plaintext secrets scratch dir {work_dir}: {e} "
                "— delete it manually; it may contain unencrypted credentials."
            )


if __name__ == "__main__":
    sys.exit(main())
