"""
NEW-754/NEW-755 — core/loader_v2.py's `_spawn_locked()` spawn-command
construction:

  Part A: `--mmap`/`--no-mmap`/`--mlock` replaced with a single
          `--load-mode <value>` (space-separated argv), mapped from the
          QWEN_MMAP/QWEN_MLOCK booleans.
  Part B: the dead `--reverse-prompt` loop (stop sequences are enforced
          per-request via the JSON body's "stop" field in the 3 real
          inference call paths, not via this CLI flag) is deleted.
  Part C: a diagnostic `--version` probe of the resolved binary is logged
          as the first lines of llama-server.log, before the real spawn.

Mirrors tests/test_loader_v2_telemetry.py's structure and fixtures --
never touches a real /proc/meminfo admission (core.resource_gate is
mocked) and never spawns a real llama-server (subprocess.Popen and
subprocess.run are mocked) — CLAUDE.md rule 2.
"""
from unittest.mock import MagicMock, patch

import pytest

import core.loader_v2 as lv
import core.resource_gate as rg


@pytest.fixture(autouse=True)
def reset_singleton():
    lv._loader = None
    yield
    lv._loader = None


def _admitted_decision():
    return rg.GateDecision(
        admitted=True,
        hard_reject=False,
        reason="ok",
        estimated_cost_bytes=1024,
        headroom_bytes=10**10,
        device_ceiling_bytes=10**11,
    )


def _patch_gate(monkeypatch):
    def fake_reserve_slot(spec, **k):
        return _admitted_decision(), "slot-load-mode-test"

    def fake_read_meminfo(*a, **k):
        return {"MemAvailable": 10**10, "MemTotal": 16 * 10**9}

    monkeypatch.setattr(rg, "reserve_slot", fake_reserve_slot)
    monkeypatch.setattr(rg, "read_meminfo", fake_read_meminfo)
    monkeypatch.setattr(rg, "mark_resident", lambda *a, **k: True)
    monkeypatch.setattr(rg, "release_slot", lambda *a, **k: True)


def _spawn_and_capture_argv(monkeypatch, tmp_path):
    """Drives a genuine (mocked) spawn through load_primary() and returns
    the resulting LlamaServer.last_argv list."""
    _patch_gate(monkeypatch)
    monkeypatch.setattr(lv, "CODEY_STATE_DIR", tmp_path)

    fake_process = MagicMock()
    fake_process.poll.return_value = None
    fake_process.pid = 5151

    fake_version_probe = MagicMock()
    fake_version_probe.stdout = "version: 0.5.0 (build 0, commit unknown)\n"
    fake_version_probe.stderr = ""

    with patch.object(lv.LlamaServer, "_is_port_in_use", return_value=False), patch.object(
        lv.LlamaServer, "_check_health", return_value=True
    ), patch("subprocess.Popen", return_value=fake_process), patch(
        "subprocess.run", return_value=fake_version_probe
    ) as mock_run, patch.object(lv.time, "sleep", return_value=None), patch(
        "pathlib.Path.exists", return_value=True
    ):
        loader = lv.get_loader()
        result = loader.load_primary()

    assert result is True
    return loader._server.last_argv, mock_run


# ---------------------------------------------------------------------------
# Part A: --load-mode mapping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "qwen_mmap,qwen_mlock,expected_mode",
    [
        (True, False, "mmap"),
        (False, True, "mlock"),
        (True, True, "mmap+mlock"),
        (False, False, "none"),
    ],
)
def test_load_mode_mapping_for_each_combo(
    monkeypatch, tmp_path, qwen_mmap, qwen_mlock, expected_mode
):
    monkeypatch.setattr("utils.config.QWEN_MMAP", qwen_mmap)
    monkeypatch.setattr("utils.config.QWEN_MLOCK", qwen_mlock)

    argv, _ = _spawn_and_capture_argv(monkeypatch, tmp_path)

    assert argv.count("--load-mode") == 1
    idx = argv.index("--load-mode")
    assert argv[idx + 1] == expected_mode

    # Old flags must never appear.
    assert "--mmap" not in argv
    assert "--no-mmap" not in argv
    assert "--mlock" not in argv
    # Part B: the dead --reverse-prompt loop must be gone too.
    assert "--reverse-prompt" not in argv


def test_load_mode_not_emitted_space_separated_not_equals(monkeypatch, tmp_path):
    """Confirmed empirically (per the architect's scoping pass) that
    `--load-mode=value` is rejected — must be two separate argv elements."""
    monkeypatch.setattr("utils.config.QWEN_MMAP", True)
    monkeypatch.setattr("utils.config.QWEN_MLOCK", False)

    argv, _ = _spawn_and_capture_argv(monkeypatch, tmp_path)

    assert not any(a.startswith("--load-mode=") for a in argv)


def test_load_mode_omitted_on_import_failure(monkeypatch, tmp_path):
    """Matches existing behavior: if utils.config can't be imported for
    QWEN_MMAP/QWEN_MLOCK, no --load-mode is emitted at all and the binary's
    own "auto" default applies. Deleting the attributes makes the real
    `from utils.config import QWEN_MLOCK, QWEN_MMAP` statement genuinely
    raise ImportError, rather than mocking the exception path."""
    import utils.config as cfg

    monkeypatch.delattr(cfg, "QWEN_MMAP", raising=False)
    monkeypatch.delattr(cfg, "QWEN_MLOCK", raising=False)

    argv, _ = _spawn_and_capture_argv(monkeypatch, tmp_path)

    assert "--load-mode" not in argv
    assert "--mmap" not in argv
    assert "--no-mmap" not in argv
    assert "--mlock" not in argv


# ---------------------------------------------------------------------------
# Part B: dead --reverse-prompt loop deleted
# ---------------------------------------------------------------------------


def test_reverse_prompt_never_emitted_regardless_of_stop_config(monkeypatch, tmp_path):
    monkeypatch.setattr("utils.config.QWEN_MMAP", True)
    monkeypatch.setattr("utils.config.QWEN_MLOCK", False)
    monkeypatch.setitem(lv.MODEL_CONFIG, "stop", ["<|im_end|>", "<|im_start|>", "\nUser:"])

    argv, _ = _spawn_and_capture_argv(monkeypatch, tmp_path)

    assert "--reverse-prompt" not in argv


# ---------------------------------------------------------------------------
# Part C: diagnostic --version log line
# ---------------------------------------------------------------------------


def test_version_diagnostic_logged_before_spawn(monkeypatch, tmp_path):
    monkeypatch.setattr("utils.config.QWEN_MMAP", True)
    monkeypatch.setattr("utils.config.QWEN_MLOCK", False)

    argv, mock_run = _spawn_and_capture_argv(monkeypatch, tmp_path)

    mock_run.assert_called_once()
    probe_cmd = mock_run.call_args[0][0]
    assert probe_cmd == [str(lv.LLAMA_SERVER_BIN), "--version"]
    assert mock_run.call_args.kwargs.get("timeout") is not None

    log_file = tmp_path / "llama-server.log"
    contents = log_file.read_text()
    assert "Resolved llama-server binary:" in contents
    assert "--version output:" in contents
    assert "0.5.0" in contents
    # The diagnostic lines must come before the real spawn line.
    assert contents.index("Resolved llama-server binary:") < contents.index(
        "Starting llama-server:"
    )


def test_version_diagnostic_failure_does_not_block_real_spawn(monkeypatch, tmp_path):
    """Fail-open: if the --version probe itself raises, the real spawn must
    still proceed and the failure must be logged, not swallowed silently."""
    monkeypatch.setattr("utils.config.QWEN_MMAP", True)
    monkeypatch.setattr("utils.config.QWEN_MLOCK", False)
    _patch_gate(monkeypatch)
    monkeypatch.setattr(lv, "CODEY_STATE_DIR", tmp_path)

    fake_process = MagicMock()
    fake_process.poll.return_value = None
    fake_process.pid = 5152

    def fake_run(*a, **k):
        raise FileNotFoundError("binary not found for probe")

    with patch.object(lv.LlamaServer, "_is_port_in_use", return_value=False), patch.object(
        lv.LlamaServer, "_check_health", return_value=True
    ), patch("subprocess.Popen", return_value=fake_process), patch(
        "subprocess.run", side_effect=fake_run
    ), patch.object(lv.time, "sleep", return_value=None), patch(
        "pathlib.Path.exists", return_value=True
    ):
        loader = lv.get_loader()
        result = loader.load_primary()

    assert result is True  # the real spawn was not blocked

    log_file = tmp_path / "llama-server.log"
    contents = log_file.read_text()
    assert "--version probe failed" in contents
    assert "Starting llama-server:" in contents
