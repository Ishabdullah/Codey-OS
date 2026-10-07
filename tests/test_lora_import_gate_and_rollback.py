"""
WP1.3 (CODEY_OS_MASTER_BLUEPRINT.md §21, CLAUDE.md rule 1's missing 4th
element): core/lora_import.py's new promotion-gate consultation and
registry-keyed rollback, isolated from the real on-device state DB and
without spawning a real llama-server (CLAUDE.md rule 2).

Composes fixtures from two existing files:
- tests/test_lora_import_swap_sync.py: reset_state autouse fixture,
  _admit_everything() resource-gate stub, _FakeLlamaServer.
- tests/test_model_registry.py: the isolated state-store fixture that
  points core/model_registry.py's underlying StateStore at a scratch DB.
"""
import json
from unittest.mock import MagicMock, patch

import pytest

import core.loader_v2 as lv
import core.lora_import as li
import core.resource_gate as rg
import core.state as state_module
import utils.config as cfg
from core.state import StateStore


class _FakeGateDecision:
    def __init__(self, promote, reasons=None, stats=None):
        self.promote = promote
        self.reasons = reasons or []
        self.stats = stats or {}


class _FakeLlamaServer:
    """Always reports a successful spawn; never touches a real model file."""

    def __init__(self, model_path, port=None, n_ctx=None, allow_upgrade=False):
        self.model_path = model_path
        self.process = MagicMock(pid=42)
        self._started = True
        self.last_argv = ["fake-llama-server", "-m", str(model_path)]

    def start(self):
        return True

    def stop(self):
        self.process = None
        self._started = False

    def is_running(self):
        return self._started


@pytest.fixture(autouse=True)
def reset_state():
    lv._loader = None
    original_model_path = cfg.MODEL_PATH
    original_planner_path = cfg.PLANNER_MODEL_PATH
    yield
    lv._loader = None
    cfg.MODEL_PATH = original_model_path
    cfg.PLANNER_MODEL_PATH = original_planner_path


@pytest.fixture
def isolated_registry(tmp_path, monkeypatch):
    """Points the shared state store at a scratch DB so these tests never
    touch this device's real ~/.codeyOS state (mirrors
    tests/test_model_registry.py's fixture exactly -- order matters: the
    monkeypatch must happen BEFORE core.model_registry is imported /
    _extend_state_schema() is called)."""
    store = StateStore(db_path=tmp_path / "test_state.db")
    monkeypatch.setattr(state_module, "_state_store", store)
    import core.model_registry as reg

    reg._extend_state_schema()
    yield reg
    store.close()


def _admit_everything(monkeypatch):
    fake_decision = MagicMock(admitted=True, estimated_cost_bytes=1024, reason="ok")
    monkeypatch.setattr(rg, "reserve_slot", lambda spec, **k: (fake_decision, "slot-1"))
    monkeypatch.setattr(rg, "mark_resident", lambda *a, **k: True)
    monkeypatch.setattr(rg, "release_slot", lambda *a, **k: True)
    monkeypatch.setattr(rg, "read_meminfo", lambda *a, **k: {"MemAvailable": 10**10})
    monkeypatch.setattr(
        lv,
        "confirm_resident_and_mark_slot",
        lambda slot_id, baseline_meminfo, estimated_cost_bytes, timeout_s=None, poll_interval_s=None, pid=None: rg.mark_resident(slot_id, pid=pid),
    )


def _make_valid_adapter(adapter_dir, merged_model_bytes=b"MERGED-FINETUNED-WEIGHTS"):
    """Build a minimal valid LoRA adapter directory (passes
    validate_lora_adapter()) with a pre-merged .gguf file inside it, so
    the non-merge-on-device branch of import_lora_adapter() is exercised
    (the on-device-merge branch needs real llama.cpp tooling)."""
    adapter_dir.mkdir(parents=True, exist_ok=True)
    (adapter_dir / "adapter_config.json").write_text(
        json.dumps({"r": 8, "target_modules": ["q_proj", "v_proj"]})
    )
    (adapter_dir / "adapter_model.safetensors").write_bytes(b"fake-lora-weights")
    merged = adapter_dir / "merged.gguf"
    merged.write_bytes(merged_model_bytes)
    return merged


def test_gate_refusal_is_free(isolated_registry, monkeypatch, tmp_path):
    """No gate_decision supplied -> defaults to no_evaluator() -> always
    refused -- and the refusal must cost nothing: validate_lora_adapter()
    must never even be reached."""
    reg = isolated_registry

    base_model = tmp_path / "models" / "base.gguf"
    base_model.parent.mkdir(parents=True)
    base_model.write_bytes(b"BASE-WEIGHTS")
    cfg.MODEL_PATH = base_model
    cfg.PLANNER_MODEL_PATH = base_model

    adapter_dir = tmp_path / "adapter"
    _make_valid_adapter(adapter_dir)

    def _boom(*a, **k):
        raise AssertionError("validate_lora_adapter() must not be reached on gate refusal")

    monkeypatch.setattr(li, "validate_lora_adapter", _boom)

    results = li.import_lora_adapter(str(adapter_dir), gate_decision=None)

    assert results["success"] is False
    assert results["error"].startswith("Refused by promotion gate")

    rows = reg.list_adoptions(limit=100)
    assert len(rows) == 1
    assert rows[0]["adopted"] is False
    assert rows[0]["gate_promote"] == 0


def test_promote_then_rollback_restores_exactly(isolated_registry, monkeypatch, tmp_path):
    """A passing gate decision lets the swap through; rollback_adoption()
    must restore the prior baseline exactly (byte-identical), reset the
    config pointers, and mark the registry row rolled back."""
    reg = isolated_registry
    _admit_everything(monkeypatch)

    base_model = tmp_path / "models" / "base.gguf"
    base_model.parent.mkdir(parents=True)
    base_bytes = b"ORIGINAL-BASE-WEIGHTS"
    base_model.write_bytes(base_bytes)
    cfg.MODEL_PATH = base_model
    cfg.PLANNER_MODEL_PATH = base_model

    adapter_dir = tmp_path / "adapter"
    merged = _make_valid_adapter(adapter_dir)

    passing_decision = _FakeGateDecision(
        True, reasons=["beat champion on frozen bench"], stats={"n": 30, "p_value": 0.01}
    )

    with patch.object(lv, "LlamaServer", _FakeLlamaServer):
        results = li.import_lora_adapter(
            str(adapter_dir), merge_on_device=False, gate_decision=passing_decision
        )

    assert results["success"] is True, results
    assert cfg.MODEL_PATH == merged
    assert cfg.PLANNER_MODEL_PATH == merged

    registry_id = results["registry_id"]
    entry = reg.get_adoption(registry_id)
    assert entry["adopted"] is True
    assert entry["rolled_back"] is False

    lv._loader = None
    with patch.object(lv, "get_loader") as mock_get_loader:
        fake_loader = MagicMock()
        fake_loader.load_primary.return_value = True
        mock_get_loader.return_value = fake_loader

        ok, msg = li.rollback_adoption(registry_id)

    assert ok is True, msg
    assert cfg.MODEL_PATH == base_model
    assert cfg.PLANNER_MODEL_PATH == base_model
    assert base_model.read_bytes() == base_bytes

    entry = reg.get_adoption(registry_id)
    assert entry["rolled_back"] is True


def test_rollback_adoption_refuses_invalid_targets(isolated_registry, monkeypatch, tmp_path):
    reg = isolated_registry
    _admit_everything(monkeypatch)

    # 1. Unknown registry id.
    ok, msg = li.rollback_adoption("does-not-exist")
    assert ok is False
    assert "No registry entry found" in msg

    # 2. A refused (never-adopted) entry's id.
    refused_id = reg.record_adoption_attempt(
        "primary", _FakeGateDecision(False), adapter_path="/tmp/a", adopted=False
    )
    ok, msg = li.rollback_adoption(refused_id)
    assert ok is False
    assert "never adopted" in msg

    # 3. Roll back a successfully-adopted entry twice; the second call
    # must refuse.
    base_model = tmp_path / "models" / "base.gguf"
    base_model.parent.mkdir(parents=True)
    base_model.write_bytes(b"BASE-WEIGHTS")
    cfg.MODEL_PATH = base_model
    cfg.PLANNER_MODEL_PATH = base_model

    adapter_dir = tmp_path / "adapter"
    _make_valid_adapter(adapter_dir)

    passing_decision = _FakeGateDecision(True)
    with patch.object(lv, "LlamaServer", _FakeLlamaServer):
        results = li.import_lora_adapter(
            str(adapter_dir), merge_on_device=False, gate_decision=passing_decision
        )
    assert results["success"] is True, results
    registry_id = results["registry_id"]

    lv._loader = None
    with patch.object(lv, "get_loader") as mock_get_loader:
        fake_loader = MagicMock()
        fake_loader.load_primary.return_value = True
        mock_get_loader.return_value = fake_loader

        ok, msg = li.rollback_adoption(registry_id)
    assert ok is True, msg

    ok, msg = li.rollback_adoption(registry_id)
    assert ok is False
    assert "already rolled back" in msg


def test_adoption_refused_without_backup(isolated_registry, monkeypatch, tmp_path):
    """If create_backup_before_import() can't make a backup (original
    model missing), import_lora_adapter() must refuse before ever
    reaching swap_to_finetuned_model() -- never adopt an unrollbackable
    model."""
    reg = isolated_registry

    # Point cfg.MODEL_PATH at a file that doesn't exist, so
    # create_backup_before_import() returns None.
    missing_model = tmp_path / "models" / "does-not-exist.gguf"
    cfg.MODEL_PATH = missing_model
    cfg.PLANNER_MODEL_PATH = missing_model

    adapter_dir = tmp_path / "adapter"
    _make_valid_adapter(adapter_dir)

    def _boom(*a, **k):
        raise AssertionError("swap_to_finetuned_model() must not be reached without a backup")

    monkeypatch.setattr(li, "swap_to_finetuned_model", _boom)

    passing_decision = _FakeGateDecision(True)
    results = li.import_lora_adapter(
        str(adapter_dir), merge_on_device=False, gate_decision=passing_decision
    )

    assert results["success"] is False
    assert results["backup_path"] is None
    assert "backup" in results["error"].lower()

    rows = reg.list_adoptions(limit=100)
    assert len(rows) == 1
    assert rows[0]["adopted"] is False
    assert rows[0]["gate_promote"] == 1  # gate passed; it was the backup step that refused


def test_fail_closed_default_unchanged_without_override(isolated_registry, monkeypatch, tmp_path):
    """No operator_override and no real gate_decision -> still always
    refuses via no_evaluator(), exactly as before this round's change."""
    reg = isolated_registry

    base_model = tmp_path / "models" / "base.gguf"
    base_model.parent.mkdir(parents=True)
    base_model.write_bytes(b"BASE-WEIGHTS")
    cfg.MODEL_PATH = base_model
    cfg.PLANNER_MODEL_PATH = base_model

    adapter_dir = tmp_path / "adapter"
    _make_valid_adapter(adapter_dir)

    def _boom(*a, **k):
        raise AssertionError("validate_lora_adapter() must not be reached -- fail-closed default broke")

    monkeypatch.setattr(li, "validate_lora_adapter", _boom)

    results = li.import_lora_adapter(str(adapter_dir), gate_decision=None, operator_override=False)

    assert results["success"] is False
    assert results["error"].startswith("Refused by promotion gate")

    rows = reg.list_adoptions(limit=100)
    assert len(rows) == 1
    assert rows[0]["adopted"] is False
    assert rows[0]["gate_promote"] == 0
    assert rows[0]["operator_override"] is False


def test_operator_override_never_recorded_as_real_gate_pass(isolated_registry, monkeypatch, tmp_path):
    """operator_override=True lets the import through WITHOUT fabricating
    a passing gate decision: the stored row must show gate_promote == 0
    (the real, honest "no evidence" verdict) AND operator_override is
    True at the same time -- never a row that looks like a genuine
    benchmark pass. Mirrors main.py's --lora-force-adopt wiring: no
    gate_decision is passed, just operator_override=True."""
    reg = isolated_registry
    _admit_everything(monkeypatch)

    base_model = tmp_path / "models" / "base.gguf"
    base_model.parent.mkdir(parents=True)
    base_bytes = b"ORIGINAL-BASE-WEIGHTS"
    base_model.write_bytes(base_bytes)
    cfg.MODEL_PATH = base_model
    cfg.PLANNER_MODEL_PATH = base_model

    adapter_dir = tmp_path / "adapter"
    merged = _make_valid_adapter(adapter_dir)

    with patch.object(lv, "LlamaServer", _FakeLlamaServer):
        results = li.import_lora_adapter(
            str(adapter_dir), merge_on_device=False, gate_decision=None, operator_override=True
        )

    assert results["success"] is True, results
    assert cfg.MODEL_PATH == merged

    registry_id = results["registry_id"]
    entry = reg.get_adoption(registry_id)
    # The real gate verdict is honest -- no evidence exists, so it reads
    # exactly like a refusal would, never fabricated into a pass.
    assert entry["gate_promote"] == 0
    assert entry["gate_reasons"] == ["no evaluator exists for this target; refusing to promote"]
    # ...but the operator's explicit bypass is visible as its own,
    # independent fact.
    assert entry["operator_override"] is True
    assert entry["adopted"] is True


def test_merge_on_device_failure_is_recorded(isolated_registry, monkeypatch, tmp_path):
    """merge_on_device=True branch, previously at zero coverage. By the
    time merge_lora_with_llama_cpp() runs, the gate already passed (or
    was overridden), validate_lora_adapter() passed, and
    create_backup_before_import() succeeded -- real work happened, so a
    failed on-device merge must still be recorded (same condition
    NEW-811's fix covers at the other two post-gate early returns)."""
    reg = isolated_registry

    base_model = tmp_path / "models" / "base.gguf"
    base_model.parent.mkdir(parents=True)
    base_model.write_bytes(b"BASE-WEIGHTS")
    cfg.MODEL_PATH = base_model
    cfg.PLANNER_MODEL_PATH = base_model

    adapter_dir = tmp_path / "adapter"
    _make_valid_adapter(adapter_dir)

    monkeypatch.setattr(
        li, "merge_lora_with_llama_cpp", lambda *a, **k: (False, "merge failed: llama.cpp not found")
    )

    def _boom(*a, **k):
        raise AssertionError("swap_to_finetuned_model() must not be reached on merge failure")

    monkeypatch.setattr(li, "swap_to_finetuned_model", _boom)

    passing_decision = _FakeGateDecision(True)
    results = li.import_lora_adapter(
        str(adapter_dir), merge_on_device=True, gate_decision=passing_decision
    )

    assert results["success"] is False
    assert results["error"] == "merge failed: llama.cpp not found"

    rows = reg.list_adoptions(limit=100)
    assert len(rows) == 1
    assert rows[0]["adopted"] is False
    assert rows[0]["gate_promote"] == 1  # the gate passed; the merge is what failed
    assert rows[0]["operator_override"] is False
