"""U.39 / NEW-455: core/setup_litestream.py must generate litestream.yml
pointing at the live Restoricon DB (resolved via utils.config, the same
source api/server.py uses) and at the restoricon/restoricon_db GCS
replica prefix.
"""

import os

import pytest

import utils.config
from core import setup_litestream


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for k in ("GCS_BACKUP_BUCKET", "RESTORICON_DB_PATH"):
        monkeypatch.delenv(k, raising=False)


def test_generated_yml_targets_live_db_and_replica_prefix(monkeypatch, tmp_path):
    live_db = tmp_path / "restoricon.db"
    monkeypatch.setenv("RESTORICON_DB_PATH", str(live_db))
    # main() imports CODEY_STATE_DIR from utils.config at call time, so
    # patching the module attribute keeps the real ~/.codeyOS/litestream.yml
    # untouched.
    monkeypatch.setattr(utils.config, "CODEY_STATE_DIR", tmp_path)

    setup_litestream.main()

    yml = (tmp_path / "litestream.yml").read_text()
    expected_db = str(live_db.expanduser().resolve())
    assert f"path: {expected_db}" in yml
    assert "path: restoricon/restoricon_db" in yml
    assert "restoricon/core_db" not in yml
