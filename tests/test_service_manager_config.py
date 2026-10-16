"""
Unit tests for Codey-OS service manager configuration, Cloudflare token extraction,
Restoricon API config, GUI config, Aigentik config, and env var overrides.
"""

import json
from pathlib import Path

import pytest

import utils.config
from utils.config import (
    get_aigentik_config,
    get_cloudflare_tunnel_token,
    get_config_file_path,
    get_restoricon_api_config,
    get_restoricon_doc_store_path,
    load_user_config,
)


@pytest.fixture(autouse=True)
def clean_service_env(monkeypatch):
    """Ensure tests run with clean service environment variables."""
    keys_to_clear = [
        "CODEY_CONFIG_PATH",
        "CLOUDFLARE_TUNNEL_TOKEN",
        "CLOUDFLARED_TOKEN",
        "RESTORICON_API_HOST",
        "RESTORICON_API_PORT",
        "RESTORICON_DB_PATH",
        "RESTORICON_DOC_STORE_PATH",
        "AIGENTIK_DIR",
        "AIGENTIK_PORT",
        "CODEY_GUI_HOST",
        "CODEY_GUI_PORT",
        "GUI_PORT",
    ]
    for k in keys_to_clear:
        monkeypatch.delenv(k, raising=False)


def test_get_config_file_path_env_override(monkeypatch, tmp_path):
    custom_cfg = tmp_path / "custom_config.json"
    custom_cfg.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("CODEY_CONFIG_PATH", str(custom_cfg))

    resolved = get_config_file_path()
    assert resolved == custom_cfg.resolve()


def test_load_user_config_valid(tmp_path):
    cfg_file = tmp_path / "test_config.json"
    content = {
        "cloudflare": {"tunnel_token": "cf_test_token_123"},
        "restoricon": {"api_host": "0.0.0.0", "api_port": 9000},
    }
    cfg_file.write_text(json.dumps(content), encoding="utf-8")

    loaded = load_user_config(cfg_file)
    assert loaded["cloudflare"]["tunnel_token"] == "cf_test_token_123"
    assert loaded["restoricon"]["api_port"] == 9000


def test_load_user_config_missing_file(tmp_path):
    missing_file = tmp_path / "non_existent.json"
    loaded = load_user_config(missing_file)
    assert loaded == {}


def test_load_user_config_corrupt_file(tmp_path):
    corrupt_file = tmp_path / "corrupt.json"
    corrupt_file.write_text("NOT_JSON_DATA{{{", encoding="utf-8")
    loaded = load_user_config(corrupt_file)
    assert loaded == {}


def test_get_cloudflare_tunnel_token_from_env_override(monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_TUNNEL_TOKEN", "token_from_env_primary")
    token = get_cloudflare_tunnel_token(config={"cloudflare": {"tunnel_token": "token_from_cfg"}})
    assert token == "token_from_env_primary"

    monkeypatch.delenv("CLOUDFLARE_TUNNEL_TOKEN")
    monkeypatch.setenv("CLOUDFLARED_TOKEN", "token_from_cloudflared_env")
    token = get_cloudflare_tunnel_token(config={"cloudflare": {"tunnel_token": "token_from_cfg"}})
    assert token == "token_from_cloudflared_env"


def test_get_cloudflare_tunnel_token_from_config():
    # Nested dict format
    cfg = {"cloudflare": {"tunnel_token": "cf_sec_token_99"}}
    assert get_cloudflare_tunnel_token(cfg) == "cf_sec_token_99"

    # Flat fallback key format
    cfg_flat = {"cloudflare_tunnel_token": "cf_flat_token_88"}
    assert get_cloudflare_tunnel_token(cfg_flat) == "cf_flat_token_88"

    # Empty / whitespace token
    cfg_empty = {"cloudflare": {"tunnel_token": "   "}}
    assert get_cloudflare_tunnel_token(cfg_empty) is None

    # Empty config
    assert get_cloudflare_tunnel_token({}) is None


def test_get_restoricon_api_config_defaults():
    cfg = get_restoricon_api_config({})
    assert cfg["host"] == "127.0.0.1"
    assert cfg["port"] == 8770
    assert cfg["db_path"].endswith("restoricon.db")


def test_default_db_path_matches_api_config_db_path(monkeypatch):
    """U.39 / NEW-455: restoricon_core.database.DEFAULT_DB_PATH (the path
    migrate_aigentik and any bare DatabaseManager() use) must be the same
    file the API server actually serves from — otherwise backups and
    migrations target a DB nobody reads. This single assertion is what
    would have caught the ~/.codey_restoricon/core.db vs
    ~/.codeyOS/restoricon.db divergence.

    DEFAULT_DB_PATH is frozen at module import, so the autouse
    clean_service_env fixture's delenv does not affect it; the guard
    below (no RESTORICON_DB_PATH, {} config so no restoricon.db_path
    override) is what keeps this hermetic.

    NEW-855: the root conftest.py redirects CODEY_STATE_DIR to a per-session
    temp dir for the whole test session (so import-time state stores never
    touch the real ~/.codeyOS), but restoricon_core.database.DEFAULT_DB_PATH
    independently re-derives "~/.codeyOS" from Path.home() rather than from
    utils.config.CODEY_STATE_DIR (same class as NEW-455 itself — logged
    separately, not fixed here). Pin utils.config.CODEY_STATE_DIR back to
    the real ~/.codeyOS for this one comparison so it still tests what it
    always tested: the two shipped defaults agreeing with each other.
    """
    from restoricon_core.database import DEFAULT_DB_PATH

    monkeypatch.setattr(utils.config, "CODEY_STATE_DIR", Path.home() / ".codeyOS")

    # (the autouse fixture already cleared RESTORICON_DB_PATH; DEFAULT_DB_PATH
    # was bound at import anyway, so this compares the shipped fallbacks)
    resolved_default = str(Path(DEFAULT_DB_PATH).expanduser().resolve())
    api_db_path = get_restoricon_api_config({})["db_path"]
    assert resolved_default == api_db_path


def test_doc_store_path_matches_across_sources(monkeypatch):
    """NEW-460: the Restoricon document store root must resolve from a single
    source (utils.config.get_restoricon_doc_store_path) to ~/.codeyOS/
    restoricon_documents, and no call site or installer step may still point
    at the dead ~/.codey_restoricon/documents tree (same class as U.39's DB
    path divergence).
    """
    repo_root = Path(__file__).parent.parent.resolve()

    # 1. Default (no env / no config override).
    # NEW-855: pin CODEY_STATE_DIR back to the real ~/.codeyOS for this
    # assertion — the root conftest.py redirects it to a per-session temp
    # dir for the whole test session, so without this pin "default" would
    # mean "wherever this session's temp dir is", not ~/.codeyOS.
    monkeypatch.setattr(utils.config, "CODEY_STATE_DIR", Path.home() / ".codeyOS")
    default_path = get_restoricon_doc_store_path({})
    assert default_path == str(
        (Path.home() / ".codeyOS" / "restoricon_documents").resolve()
    )

    # 2. install.sh creates the new dir, not the dead one.
    install_sh = (repo_root / "install.sh").read_text(encoding="utf-8")
    assert ".codeyOS/restoricon_documents" in install_sh
    assert ".codey_restoricon/documents" not in install_sh

    # 3. Neither Python call site still hardcodes the dead tree.
    for rel in ("core/backup_documents.py", "restoricon_core/api/routes.py"):
        text = (repo_root / rel).read_text(encoding="utf-8")
        assert ".codey_restoricon/documents" not in text, rel

    # 4. Env override wins.
    monkeypatch.setenv("RESTORICON_DOC_STORE_PATH", "/tmp/custom_doc_store")
    assert get_restoricon_doc_store_path({}) == str(
        Path("/tmp/custom_doc_store").resolve()
    )


def test_get_restoricon_api_config_from_dict():
    config_dict = {
        "restoricon": {
            "api_host": "192.168.1.50",
            "api_port": 8800,
            "db_path": "/tmp/custom_restoricon.db",
        }
    }
    cfg = get_restoricon_api_config(config_dict)
    assert cfg["host"] == "192.168.1.50"
    assert cfg["port"] == 8800
    assert cfg["db_path"] == str(Path("/tmp/custom_restoricon.db").resolve())


def test_get_restoricon_api_config_env_overrides(monkeypatch):
    config_dict = {
        "restoricon": {
            "api_host": "192.168.1.50",
            "api_port": 8800,
            "db_path": "/tmp/custom_restoricon.db",
        }
    }
    monkeypatch.setenv("RESTORICON_API_HOST", "0.0.0.0")
    monkeypatch.setenv("RESTORICON_API_PORT", "9999")
    monkeypatch.setenv("RESTORICON_DB_PATH", "/var/lib/restoricon.db")

    cfg = get_restoricon_api_config(config_dict)
    assert cfg["host"] == "0.0.0.0"
    assert cfg["port"] == 9999
    assert cfg["db_path"] == str(Path("/var/lib/restoricon.db").resolve())


def test_get_aigentik_config_defaults():
    cfg = get_aigentik_config({})
    assert cfg["dir"] == str(Path.home() / "Codey-Aigentik")
    assert cfg["port"] == 8000


def test_get_aigentik_config_from_dict():
    config_dict = {
        "aigentik": {
            "dir": "/opt/aigentik",
            "port": 8100,
        }
    }
    cfg = get_aigentik_config(config_dict)
    assert cfg["dir"] == str(Path("/opt/aigentik").resolve())
    assert cfg["port"] == 8100


def test_get_aigentik_config_env_overrides(monkeypatch):
    config_dict = {
        "aigentik": {
            "dir": "/opt/aigentik",
            "port": 8100,
        }
    }
    monkeypatch.setenv("AIGENTIK_DIR", "/srv/codey-aigentik")
    monkeypatch.setenv("AIGENTIK_PORT", "8200")

    cfg = get_aigentik_config(config_dict)
    assert cfg["dir"] == str(Path("/srv/codey-aigentik").resolve())
    assert cfg["port"] == 8200


# Public lifecycle coverage moved to test_service_public_lifecycle.py. The old
# fixtures signalled numeric PID-file contents, killed discovery matches, and
# could leave children unreaped on assertion failure; none may run unchanged.
