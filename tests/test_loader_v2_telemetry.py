"""
T9 (docs/telemetry_layer_design.md §2.B, §2.G) — category-B `can_admit`
gate-decision telemetry and `llama_server_argv` run-provenance amendment at
core/loader_v2.py's ModelLoader.load_primary() / LlamaServer._spawn_locked().

Mirrors tests/test_plannd_telemetry.py's structure and fixtures. Never
touches a real /proc/meminfo admission (core.resource_gate.reserve_slot()
is mocked) and never spawns a real llama-server (subprocess.Popen is
mocked) — same "never touch the real device" posture T5/T6 already
established (CLAUDE.md rule 2).
"""
from unittest.mock import MagicMock, patch

import pytest

import core.loader_v2 as lv
import core.resource_gate as rg
import utils.config as cfg
from telemetry import envelope, recorders, schema


@pytest.fixture(autouse=True)
def reset_singleton():
    lv._loader = None
    yield
    lv._loader = None


@pytest.fixture(autouse=True)
def _capture_telemetry(monkeypatch):
    """Autouse within this file only -- see tests/test_plannd_telemetry.py's
    identical fixture for the full rationale. Forces TELEMETRY_ENABLED True
    (overriding tests/conftest.py's session-wide False default)."""
    captured = []

    def fake_record(rec):
        captured.append(rec)

    monkeypatch.setattr(recorders.store, "record", fake_record)
    monkeypatch.setattr(recorders.store, "get_run_id", lambda: "loader-telemetry-test")
    monkeypatch.setattr(recorders.store, "TELEMETRY_ENABLED", True)
    envelope.reset_seq()
    return captured


def _admitted_decision():
    return rg.GateDecision(
        admitted=True,
        hard_reject=False,
        reason="ok",
        estimated_cost_bytes=1024,
        headroom_bytes=10**10,
        device_ceiling_bytes=10**11,
    )


def _denied_decision():
    return rg.GateDecision(
        admitted=False,
        hard_reject=True,
        reason="model alone exceeds device ceiling",
        estimated_cost_bytes=10**11,
        headroom_bytes=10**10,
        device_ceiling_bytes=10**11,
    )


class FakeServerReused:
    """Stand-in for LlamaServer.start() reusing an existing server --
    self.process stays None, last_argv stays None (never spawned)."""

    def __init__(self, *a, **k):
        self.process = None
        self.last_argv = None
        self._started = True

    def start(self):
        return True

    def stop(self):
        self._started = False

    def is_running(self):
        return self._started


def _patch_gate(monkeypatch, decision, meminfo_calls=None):
    calls = meminfo_calls if meminfo_calls is not None else []

    def fake_reserve_slot(spec, **k):
        return decision, ("slot-t9" if decision.admitted else None)

    def fake_read_meminfo(*a, **k):
        meminfo = {"MemAvailable": 10**10, "MemTotal": 16 * 10**9}
        calls.append(meminfo)
        return meminfo

    monkeypatch.setattr(rg, "reserve_slot", fake_reserve_slot)
    monkeypatch.setattr(rg, "read_meminfo", fake_read_meminfo)
    monkeypatch.setattr(rg, "mark_resident", lambda *a, **k: True)
    monkeypatch.setattr(rg, "release_slot", lambda *a, **k: True)
    return calls


def test_gate_telemetry_admitted_record_fields(monkeypatch, _capture_telemetry):
    _patch_gate(monkeypatch, _admitted_decision())

    with patch.object(lv, "LlamaServer", FakeServerReused), patch(
        "pathlib.Path.exists", return_value=True
    ):
        loader = lv.get_loader()
        assert loader.load_primary() is True

    gate_records = [r for r in _capture_telemetry if r["category"] == "gate"]
    assert len(gate_records) == 1
    rec = gate_records[0]
    assert rec["emitter"] == "codey-os.loader"
    assert rec["event_type"] == "can_admit"
    assert rec["body"]["call_site"] == "loader_v2.ModelLoader.load_primary"
    assert rec["body"]["decision"]["admitted"] is True
    assert rec["body"]["meminfo"] == {"MemAvailable": 10**10, "MemTotal": 16 * 10**9}
    assert schema.validate(rec) == []


def test_gate_telemetry_emitted_unconditionally_on_denial(monkeypatch, _capture_telemetry):
    """Design §2.B: denials are recorded exactly as fully as admissions --
    the gate record must still be emitted even though load_primary() itself
    fails and never reaches spawn."""
    _patch_gate(monkeypatch, _denied_decision())

    with patch.object(lv, "LlamaServer") as MockServer, patch(
        "pathlib.Path.exists", return_value=True
    ):
        loader = lv.get_loader()
        result = loader.load_primary()

    assert result is False
    MockServer.assert_not_called()

    gate_records = [r for r in _capture_telemetry if r["category"] == "gate"]
    assert len(gate_records) == 1
    rec = gate_records[0]
    assert rec["body"]["decision"]["admitted"] is False
    assert rec["body"]["decision"]["hard_reject"] is True
    assert rec["body"]["reason"] == "model alone exceeds device ceiling"
    assert schema.validate(rec) == []

    # No provenance amendment either -- nothing was spawned.
    provenance_records = [r for r in _capture_telemetry if r["category"] == "provenance"]
    assert provenance_records == []


def test_argv_provenance_emitted_on_genuine_spawn(monkeypatch, _capture_telemetry):
    _patch_gate(monkeypatch, _admitted_decision())

    fake_process = MagicMock()
    fake_process.poll.return_value = None
    fake_process.pid = 4242

    with patch.object(lv.LlamaServer, "_is_port_in_use", return_value=False), patch.object(
        lv.LlamaServer, "_check_health", return_value=True
    ), patch("subprocess.Popen", return_value=fake_process) as mock_popen, patch.object(
        lv.time, "sleep", return_value=None
    ), patch("pathlib.Path.exists", return_value=True):
        loader = lv.get_loader()
        result = loader.load_primary()

    assert result is True

    provenance_records = [r for r in _capture_telemetry if r["category"] == "provenance"]
    assert len(provenance_records) == 1
    rec = provenance_records[0]
    assert rec["emitter"] == "codey-os.loader"
    assert rec["event_type"] == "run_start_amended"
    assert rec["run_id"] == "loader-telemetry-test"
    argv = rec["body"]["llama_server_argv"]
    assert argv[0] == str(lv.LLAMA_SERVER_BIN)
    assert "-m" in argv
    assert "--jinja" in argv
    assert "--reasoning-format" in argv
    assert schema.validate(rec) == []

    # The real verification that T9 actually captured what was spawned: the
    # amended argv must equal the exact list subprocess.Popen() was called
    # with -- not just "looks plausible" (the checks above alone wouldn't
    # catch `self.last_argv = list(cmd)` being placed before the mmap/mlock
    # flags were appended, which would silently drop them from the capture
    # while every assertion above still passed).
    assert argv == list(mock_popen.call_args[0][0])
    assert loader._server.last_argv == argv


def test_argv_provenance_not_emitted_on_reuse_branch(monkeypatch, _capture_telemetry):
    """FakeServerReused never runs _spawn_locked() -- last_argv stays None,
    so load_primary() must not emit a run_start_amended record at all."""
    _patch_gate(monkeypatch, _admitted_decision())

    with patch.object(lv, "LlamaServer", FakeServerReused), patch(
        "pathlib.Path.exists", return_value=True
    ):
        loader = lv.get_loader()
        result = loader.load_primary()

    assert result is True
    provenance_records = [r for r in _capture_telemetry if r["category"] == "provenance"]
    assert provenance_records == []


def test_no_telemetry_calls_when_disabled(monkeypatch, _capture_telemetry):
    """Kill switch: checked first, before any telemetry work -- with
    TELEMETRY_ENABLED False, load_primary() must never even reach
    telemetry.recorders (not just "no record ended up in the store", which
    would also pass if the enabled-check lived inside recorders instead of
    check-first in the loader's own helpers)."""
    monkeypatch.setattr(recorders.store, "TELEMETRY_ENABLED", False)
    mock_gate = MagicMock()
    mock_amended = MagicMock()
    monkeypatch.setattr(recorders, "record_gate_decision", mock_gate)
    monkeypatch.setattr(recorders, "record_run_start_amended", mock_amended)
    _patch_gate(monkeypatch, _admitted_decision())

    fake_process = MagicMock()
    fake_process.poll.return_value = None
    fake_process.pid = 4244

    with patch.object(lv.LlamaServer, "_is_port_in_use", return_value=False), patch.object(
        lv.LlamaServer, "_check_health", return_value=True
    ), patch("subprocess.Popen", return_value=fake_process), patch.object(
        lv.time, "sleep", return_value=None
    ), patch("pathlib.Path.exists", return_value=True):
        loader = lv.get_loader()
        result = loader.load_primary()

    assert result is True
    assert _capture_telemetry == []
    mock_gate.assert_not_called()
    mock_amended.assert_not_called()


def test_gate_telemetry_failure_never_propagates(monkeypatch, _capture_telemetry):
    """A telemetry-internals exception must never affect load_primary()'s
    return value or control flow -- broad except + warning log only."""
    _patch_gate(monkeypatch, _admitted_decision())

    def boom(*a, **k):
        raise RuntimeError("telemetry backend exploded")

    monkeypatch.setattr(recorders, "record_gate_decision", boom)

    with patch.object(lv, "LlamaServer", FakeServerReused), patch(
        "pathlib.Path.exists", return_value=True
    ):
        loader = lv.get_loader()
        result = loader.load_primary()

    assert result is True


def test_argv_provenance_failure_never_propagates(monkeypatch, _capture_telemetry):
    _patch_gate(monkeypatch, _admitted_decision())

    def boom(*a, **k):
        raise RuntimeError("telemetry backend exploded")

    monkeypatch.setattr(recorders, "record_run_start_amended", boom)

    fake_process = MagicMock()
    fake_process.poll.return_value = None
    fake_process.pid = 4243

    with patch.object(lv.LlamaServer, "_is_port_in_use", return_value=False), patch.object(
        lv.LlamaServer, "_check_health", return_value=True
    ), patch("subprocess.Popen", return_value=fake_process), patch.object(
        lv.time, "sleep", return_value=None
    ), patch("pathlib.Path.exists", return_value=True):
        loader = lv.get_loader()
        result = loader.load_primary()

    assert result is True
