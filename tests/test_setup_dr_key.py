"""NEW-458 commit B.1 — tests for core/setup_dr_key.py.

No real age keys: subprocess.run (age-keygen) is mocked with a canned
keypair. Asserts the public key lands in config while the private key
appears only on stdout and in no file the script writes.
"""

import json
import sys
from unittest.mock import MagicMock, patch

import pytest

from core import setup_dr_key

CANNED_PUB = "age1testpub00000000000000000000000000000000000000000000000000"
CANNED_PRIV = "AGE-SECRET-KEY-1TESTTESTTESTTESTTESTTESTTESTTESTTESTTESTTESTTEST99"
CANNED_STDOUT = (
    "# created: 2026-01-01T00:00:00Z\n"
    f"# public key: {CANNED_PUB}\n"
    f"{CANNED_PRIV}\n"
)


@pytest.fixture
def cfg_file(tmp_path, monkeypatch):
    resolved = tmp_path.resolve()
    path = resolved / "config.json"
    path.write_text(
        json.dumps({"restoricon": {"db_path": "/keep/me.db"}, "toplevel": 7}),
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEY_CONFIG_PATH", str(path))
    return path


def _mock_keygen_ok():
    m = MagicMock()
    m.stdout = CANNED_STDOUT
    return m


def test_happy_path_writes_pubkey_only(cfg_file, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["setup_dr_key"])
    with patch("core.setup_dr_key.subprocess.run", return_value=_mock_keygen_ok()):
        rc = setup_dr_key.main()

    assert rc == 0
    data = json.loads(cfg_file.read_text())
    assert data["restoricon"]["dr_recipient_pubkey"] == CANNED_PUB
    # Pre-existing keys preserved (sibling inside restoricon + top level).
    assert data["restoricon"]["db_path"] == "/keep/me.db"
    assert data["toplevel"] == 7

    out = capsys.readouterr().out
    assert CANNED_PRIV in out

    # The private key must not have been written to ANY file under tmp_path.
    resolved = tmp_path.resolve()
    for p in resolved.rglob("*"):
        if p.is_file():
            assert "AGE-SECRET-KEY" not in p.read_text(errors="ignore"), p
    assert cfg_file.exists()


def test_second_run_without_force_is_noop(cfg_file, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["setup_dr_key"])
    with patch("core.setup_dr_key.subprocess.run", return_value=_mock_keygen_ok()):
        assert setup_dr_key.main() == 0
    after_first = cfg_file.read_text()

    # Second run: pubkey already set, no --force.
    run_mock = MagicMock(return_value=_mock_keygen_ok())
    with patch("core.setup_dr_key.subprocess.run", run_mock):
        rc = setup_dr_key.main()

    assert rc == 1
    run_mock.assert_not_called()
    assert cfg_file.read_text() == after_first


def test_force_regenerates(cfg_file, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["setup_dr_key"])
    with patch("core.setup_dr_key.subprocess.run", return_value=_mock_keygen_ok()):
        assert setup_dr_key.main() == 0

    new_pub = "age1regenerated1111111111111111111111111111111111111111111111"
    new_stdout = (
        "# public key: " + new_pub + "\n"
        "AGE-SECRET-KEY-1NEWNEWNEWNEWNEWNEWNEWNEWNEWNEWNEWNEWNEWNEWNEW00\n"
    )
    m = MagicMock()
    m.stdout = new_stdout
    monkeypatch.setattr(sys, "argv", ["setup_dr_key", "--force"])
    with patch("core.setup_dr_key.subprocess.run", return_value=m):
        rc = setup_dr_key.main()

    assert rc == 0
    data = json.loads(cfg_file.read_text())
    assert data["restoricon"]["dr_recipient_pubkey"] == new_pub
    assert data["restoricon"]["db_path"] == "/keep/me.db"


def test_keygen_failure_writes_nothing(cfg_file, monkeypatch):
    import subprocess as _sp

    monkeypatch.setattr(sys, "argv", ["setup_dr_key"])
    before = cfg_file.read_text()
    err = _sp.CalledProcessError(1, ["age-keygen"], output=CANNED_STDOUT)
    with patch("core.setup_dr_key.subprocess.run", side_effect=err):
        rc = setup_dr_key.main()

    assert rc == 1
    assert cfg_file.read_text() == before
