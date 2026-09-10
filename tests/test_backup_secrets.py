"""NEW-458 commit B.2 — tests for core/backup_secrets.py.

No live GCS, no real age keys: subprocess (age / age-keygen) and
google.cloud.storage.Client are mocked. Covers the fail-closed guard, the
two-recipient encryption, and the try/finally plaintext-tar cleanup.
"""

import json
import os
import subprocess
import sys
import tarfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core import backup_secrets

REPO_ROOT = Path(__file__).parent.parent.resolve()

AT_REST_PUB = "age1atrest000000000000000000000000000000000000000000000000000"
DR_PUB = "age1drpub00000000000000000000000000000000000000000000000000000"


@pytest.fixture
def home(tmp_path, monkeypatch):
    h = (tmp_path / "home").resolve()
    (h / ".codeyOS").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(h))
    return h


def _write_cfg(home, monkeypatch, cfg):
    path = home / ".codeyOS" / "config.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    monkeypatch.setenv("CODEY_CONFIG_PATH", str(path))
    return path


def _seed_secret_files(home):
    d = home / ".codeyOS"
    (d / "age.key").write_text("AGE-SECRET-KEY-1REALIDENTITY\n", encoding="utf-8")
    (d / "gcp_credentials.json").write_text('{"type":"service_account"}', encoding="utf-8")
    (d / "vertex-express.json").write_text('{"vertex":true}', encoding="utf-8")


def test_missing_dr_pubkey_fails_closed(home, monkeypatch):
    _write_cfg(home, monkeypatch, {})
    _seed_secret_files(home)

    with patch("core.backup_secrets.storage.Client") as mock_client, \
         patch("core.backup_secrets.subprocess.run") as mock_run:
        rc = backup_secrets.main()

    assert rc == 1
    assert mock_client.call_count == 0
    mock_run.assert_not_called()


def test_malformed_dr_pubkey_fails_closed(home, monkeypatch):
    _write_cfg(home, monkeypatch, {"restoricon": {"dr_recipient_pubkey": "notanage"}})
    _seed_secret_files(home)

    with patch("core.backup_secrets.storage.Client") as mock_client, \
         patch("core.backup_secrets.subprocess.run") as mock_run:
        rc = backup_secrets.main()

    assert rc == 1
    assert mock_client.call_count == 0
    mock_run.assert_not_called()


def test_happy_path_two_recipients_and_file_list(home, tmp_path, monkeypatch):
    _write_cfg(
        home, monkeypatch,
        {"restoricon": {"dr_recipient_pubkey": DR_PUB}, "gcs_backup_bucket": "my-bucket"},
    )
    _seed_secret_files(home)

    work_dir = str((tmp_path / "workdir").resolve())
    os.makedirs(work_dir)

    mock_run = MagicMock()
    mock_run.return_value.stdout = AT_REST_PUB + "\n"
    rmtree_calls = []

    with patch("core.backup_secrets.tempfile.mkdtemp", return_value=work_dir), \
         patch("core.backup_secrets.shutil.rmtree",
               side_effect=lambda p, **kw: rmtree_calls.append(p)), \
         patch("core.backup_secrets.subprocess.run", mock_run), \
         patch("core.backup_secrets.storage.Client") as mock_client:
        rc = backup_secrets.main()

    assert rc == 0

    # age called with BOTH recipients.
    age_args = mock_run.call_args[0][0]
    assert age_args[0] == "age"
    assert age_args.count("-r") == 2
    assert AT_REST_PUB in age_args
    assert DR_PUB in age_args

    # Tar (still present because rmtree was stubbed) holds age.key + vertex.
    names = tarfile.open(os.path.join(work_dir, "secrets.tar.gz")).getnames()
    assert "age.key" in names
    assert "vertex-express.json" in names

    # Uploaded to the configured bucket + fixed blob path.
    mock_client.return_value.bucket.assert_called_once_with("my-bucket")
    mock_client.return_value.bucket.return_value.blob.assert_called_once_with(
        backup_secrets.GCS_BLOB_PATH
    )
    # finally-block cleanup ran.
    assert work_dir in rmtree_calls


def test_script_process_exit_code_nonzero_when_fail_closed(tmp_path):
    """service_manager.sh branches on the PROCESS exit status, not a return
    value — verify `sys.exit(main())` is actually wired so the fail-closed
    path produces a non-zero exit (NEW-259: correct mechanism, untested
    call site = permanent no-op). Returns before any age/GCS call.
    """
    empty_cfg = tmp_path / "config.json"
    empty_cfg.write_text("{}", encoding="utf-8")
    res = subprocess.run(
        [sys.executable, "core/backup_secrets.py"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        env={**os.environ, "CODEY_CONFIG_PATH": str(empty_cfg)},
    )
    assert res.returncode != 0, res.stderr


def test_get_bucket_name_env_var_wins(monkeypatch):
    # W1: GCS_BACKUP_BUCKET overrides config, matching setup_litestream.py.
    monkeypatch.setenv("GCS_BACKUP_BUCKET", "env-bucket")
    assert backup_secrets.get_bucket_name({"gcs_backup_bucket": "cfg-bucket"}) == "env-bucket"
    monkeypatch.delenv("GCS_BACKUP_BUCKET", raising=False)
    assert backup_secrets.get_bucket_name({"gcs_backup_bucket": "cfg-bucket"}) == "cfg-bucket"
    assert backup_secrets.get_bucket_name({}) == "codey-os-backups"


def test_get_at_rest_public_key_missing_binary_returns_none(home, monkeypatch):
    # W4/W5: a missing age-keygen (OSError) is caught, returns None, no raise.
    (home / ".codeyOS" / "age.key").write_text("AGE-SECRET-KEY-1X\n", encoding="utf-8")
    with patch("core.backup_secrets.subprocess.run", side_effect=FileNotFoundError("age-keygen")):
        assert backup_secrets.get_at_rest_public_key() is None


def test_sigterm_handler_restored_after_main(home, monkeypatch):
    # W3: main() must not leak its process-global SIGTERM handler.
    import signal as _signal
    sentinel = _signal.getsignal(_signal.SIGTERM)
    _write_cfg(home, monkeypatch, {})
    _seed_secret_files(home)
    with patch("core.backup_secrets.storage.Client"), \
         patch("core.backup_secrets.subprocess.run"):
        backup_secrets.main()
    assert _signal.getsignal(_signal.SIGTERM) is sentinel


def test_upload_failure_still_cleans_up_temp_dir(home, tmp_path, monkeypatch):
    _write_cfg(
        home, monkeypatch,
        {"restoricon": {"dr_recipient_pubkey": DR_PUB}},
    )
    _seed_secret_files(home)

    work_dir = str((tmp_path / "workdir2").resolve())
    os.makedirs(work_dir)

    mock_client = MagicMock()
    mock_client.return_value.bucket.return_value.blob.return_value.upload_from_filename.side_effect = RuntimeError("boom")

    mock_run = MagicMock()
    mock_run.return_value.stdout = AT_REST_PUB + "\n"

    with patch("core.backup_secrets.tempfile.mkdtemp", return_value=work_dir), \
         patch("core.backup_secrets.subprocess.run", mock_run), \
         patch("core.backup_secrets.storage.Client", mock_client):
        with pytest.raises(RuntimeError):
            backup_secrets.main()

    # try/finally removed the whole temp dir (both .tar.gz and .age).
    assert not os.path.exists(work_dir)
