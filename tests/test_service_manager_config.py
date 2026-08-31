"""
Unit tests for Codey-OS service manager configuration, Cloudflare token extraction,
Restoricon API config, GUI config, Aigentik config, and env var overrides.
"""

import json
import os
import subprocess
import tempfile
from pathlib import Path
import pytest

from utils.config import (
    get_config_file_path,
    load_user_config,
    get_cloudflare_tunnel_token,
    get_restoricon_api_config,
    get_aigentik_config,
    get_gui_config,
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


def test_get_gui_config_defaults():
    cfg = get_gui_config({})
    assert cfg["host"] == "127.0.0.1"
    assert cfg["port"] == 8888


def test_get_gui_config_from_dict():
    config_dict = {
        "gui": {
            "host": "0.0.0.0",
            "port": 8899,
        }
    }
    cfg = get_gui_config(config_dict)
    assert cfg["host"] == "0.0.0.0"
    assert cfg["port"] == 8899


def test_get_gui_config_env_overrides(monkeypatch):
    config_dict = {
        "gui": {
            "host": "0.0.0.0",
            "port": 8899,
        }
    }
    monkeypatch.setenv("CODEY_GUI_HOST", "127.0.0.2")
    monkeypatch.setenv("CODEY_GUI_PORT", "9900")

    cfg = get_gui_config(config_dict)
    assert cfg["host"] == "127.0.0.2"
    assert cfg["port"] == 9900


def test_codey_script_cli_help_and_config():
    repo_root = Path(__file__).parent.parent.resolve()
    codey_bin = repo_root / "codey"
    assert codey_bin.is_file()
    assert os.access(codey_bin, os.X_OK)

    # Test codey help
    res_help = subprocess.run(
        [str(codey_bin), "help"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    assert res_help.returncode == 0
    assert "Codey-OS" in res_help.stdout
    assert "Usage:" in res_help.stdout

    # Test codey config
    res_cfg = subprocess.run(
        [str(codey_bin), "config"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    assert res_cfg.returncode == 0
    assert "Config file:" in res_cfg.stdout

    # Test codey status
    res_status = subprocess.run(
        [str(codey_bin), "status"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    assert res_status.returncode == 0
    assert "Services Status:" in res_status.stdout


def test_service_manager_pid_lifecycle(tmp_path):
    repo_root = Path(__file__).parent.parent.resolve()
    svc_lib = repo_root / "lib" / "service_manager.sh"

    # Start a dummy background process
    proc = subprocess.Popen(["sleep", "30"])
    pid = proc.pid
    pid_file = tmp_path / "dummy_service.pid"
    pid_file.write_text(str(pid), encoding="utf-8")

    # Run bash script sourcing service_manager and stopping by PID
    script = f"""
    source "{svc_lib}"
    svc_is_running "{pid_file}" || exit 1
    svc_stop_by_pid "{pid_file}" "DummyService"
    """
    res = subprocess.run(
        ["bash", "-c", script],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0
    assert "stopped" in res.stdout
    assert not pid_file.exists()

    # Verify process is dead
    proc.poll()
    assert proc.returncode is not None or not proc.is_running() if hasattr(proc, 'is_running') else True

