"""
WP0.7 (CODEY_OS_MASTER_BLUEPRINT.md §21, Ish's decision 7): the
Cloudflare tunnel token used to live in config.json plaintext -- the
last plaintext credential on device. Covers the new
~/.codeyOS/cloudflare_tunnel_token.age decrypt precedence in
utils/config.py, mocking the `age` subprocess call (no real binary
dependency in CI).
"""
from unittest.mock import MagicMock, patch

import pytest

import utils.config as config_module
from utils.config import get_cloudflare_tunnel_token


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for key in ("CLOUDFLARE_TUNNEL_TOKEN", "CLOUDFLARED_TOKEN"):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def isolated_state_dir(tmp_path, monkeypatch):
    """Points CODEY_STATE_DIR at a scratch dir so these tests never touch
    this device's real ~/.codeyOS files."""
    monkeypatch.setattr(config_module, "CODEY_STATE_DIR", tmp_path)
    return tmp_path


def _fake_age_success(stdout: str):
    result = MagicMock()
    result.stdout = stdout
    return result


def test_decrypts_when_both_files_exist(isolated_state_dir):
    (isolated_state_dir / "cloudflare_tunnel_token.age").write_bytes(b"fake-ciphertext")
    (isolated_state_dir / "age.key").write_text("fake-identity")

    with patch("subprocess.run", return_value=_fake_age_success("real-decrypted-token\n")) as mock_run:
        token = get_cloudflare_tunnel_token()

    assert token == "real-decrypted-token"
    args = mock_run.call_args.args[0]
    assert args[0] == "age"
    assert "-d" in args


def test_falls_back_to_plaintext_config_when_encrypted_file_missing(isolated_state_dir):
    (isolated_state_dir / "age.key").write_text("fake-identity")
    # No cloudflare_tunnel_token.age written.

    with patch("subprocess.run") as mock_run:
        token = get_cloudflare_tunnel_token(config={"cloudflare": {"tunnel_token": "plaintext_fallback"}})

    mock_run.assert_not_called()
    assert token == "plaintext_fallback"


def test_falls_back_to_plaintext_config_when_age_key_missing(isolated_state_dir):
    (isolated_state_dir / "cloudflare_tunnel_token.age").write_bytes(b"fake-ciphertext")
    # No age.key written.

    with patch("subprocess.run") as mock_run:
        token = get_cloudflare_tunnel_token(config={"cloudflare": {"tunnel_token": "plaintext_fallback"}})

    mock_run.assert_not_called()
    assert token == "plaintext_fallback"


def test_falls_back_to_plaintext_config_when_decrypt_fails(isolated_state_dir):
    import subprocess as subprocess_module

    (isolated_state_dir / "cloudflare_tunnel_token.age").write_bytes(b"fake-ciphertext")
    (isolated_state_dir / "age.key").write_text("fake-identity")

    with patch("subprocess.run", side_effect=subprocess_module.CalledProcessError(1, ["age"])):
        token = get_cloudflare_tunnel_token(config={"cloudflare": {"tunnel_token": "plaintext_fallback"}})

    assert token == "plaintext_fallback"


def test_env_var_wins_over_encrypted_file(isolated_state_dir, monkeypatch):
    (isolated_state_dir / "cloudflare_tunnel_token.age").write_bytes(b"fake-ciphertext")
    (isolated_state_dir / "age.key").write_text("fake-identity")
    monkeypatch.setenv("CLOUDFLARE_TUNNEL_TOKEN", "token_from_env")

    with patch("subprocess.run") as mock_run:
        token = get_cloudflare_tunnel_token()

    mock_run.assert_not_called()
    assert token == "token_from_env"


def test_explicit_config_override_never_consults_the_real_device_file():
    """Regression: an explicit `config=` dict (how every existing
    precedence test in tests/test_service_manager_config.py calls this
    function) must not be silently overridden by whatever real encrypted
    file happens to exist on THIS device -- caught during this round's
    own implementation when the real on-device file (created to verify
    this fix end-to-end) broke an unrelated, pre-existing test."""
    with patch("subprocess.run") as mock_run:
        token = get_cloudflare_tunnel_token(config={"cloudflare": {"tunnel_token": "explicit_config_value"}})

    mock_run.assert_not_called()
    assert token == "explicit_config_value"
