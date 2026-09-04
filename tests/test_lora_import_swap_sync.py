"""
Regression for the "primary"/"secondary" swap-branch asymmetry found by
code-reviewer against the M1-B/C/D working tree diff (pre-commit fix,
2026-08-23).

core/lora_import.py's swap_to_finetuned_model() "secondary" branch mutates
BOTH cfg.MODEL_PATH and cfg.PLANNER_MODEL_PATH together, and rolls both back
together on failure. The "primary" branch used to mutate only
cfg.MODEL_PATH, leaving cfg.PLANNER_MODEL_PATH stale after a "primary"
swap. Since M1-D collapsed "primary" and "secondary" onto the same physical
model file, and import_lora_adapter()'s secondary branch reads
cfg.PLANNER_MODEL_PATH as `base_model` for an on-device LoRA merge, a stale
PLANNER_MODEL_PATH after a "primary" swap could point a later merge at the
wrong base file.

This file only covers the "primary" branch's now-dual mutate/rollback
behavior (the "secondary" branch's equivalent behavior is already covered
by tests/test_new84_stale_model_path.py). No real llama-server process is
spawned (CLAUDE.md rule 2, RAM discipline) — LlamaServer is patched with a
lightweight fake.
"""
from unittest.mock import MagicMock, patch

import pytest

import core.loader_v2 as lv
import core.lora_import as li
import core.resource_gate as rg
import utils.config as cfg


class _FakeLlamaServer:
    """Always reports a successful spawn."""

    def __init__(self, model_path, port=None, n_ctx=None, allow_upgrade=False):
        self.model_path = model_path
        self.process = MagicMock(pid=42)
        self._started = True
        # T9: real LlamaServer._spawn_locked() sets this; this fake stands
        # in for a genuine spawn, so it must too.
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


def _admit_everything(monkeypatch):
    fake_decision = MagicMock(admitted=True, estimated_cost_bytes=1024, reason="ok")
    monkeypatch.setattr(rg, "reserve_slot", lambda spec, **k: (fake_decision, "slot-1"))
    monkeypatch.setattr(rg, "mark_resident", lambda *a, **k: True)
    monkeypatch.setattr(rg, "release_slot", lambda *a, **k: True)
    monkeypatch.setattr(rg, "read_meminfo", lambda *a, **k: {"MemAvailable": 10**10})


def test_primary_swap_success_syncs_both_paths(monkeypatch, tmp_path):
    """A successful "primary" swap must update cfg.MODEL_PATH AND
    cfg.PLANNER_MODEL_PATH together, mirroring the "secondary" branch."""
    _admit_everything(monkeypatch)

    original_model = cfg.MODEL_PATH
    new_model = tmp_path / "finetuned-primary.gguf"
    new_model.write_bytes(b"x")

    lv._loader = None
    with patch.object(lv, "LlamaServer", _FakeLlamaServer):
        ok, msg = li.swap_to_finetuned_model(str(new_model), "primary")

    assert ok is True, msg
    assert cfg.MODEL_PATH == new_model
    assert cfg.PLANNER_MODEL_PATH == new_model
    assert original_model != new_model  # sanity: the swap actually changed something


def test_primary_swap_failure_rolls_back_both_paths(monkeypatch, tmp_path):
    """If load_primary() fails, both cfg.MODEL_PATH and
    cfg.PLANNER_MODEL_PATH must be restored to their pre-swap values —
    not just cfg.MODEL_PATH."""
    original_model = cfg.MODEL_PATH
    original_planner = cfg.PLANNER_MODEL_PATH

    new_model = tmp_path / "finetuned-primary.gguf"
    new_model.write_bytes(b"x")

    lv._loader = None
    with patch.object(lv, "get_loader") as mock_get_loader:
        fake_loader = MagicMock()
        fake_loader.load_primary.return_value = False
        mock_get_loader.return_value = fake_loader

        ok, msg = li.swap_to_finetuned_model(str(new_model), "primary")

    assert ok is False, msg
    assert cfg.MODEL_PATH == original_model
    assert cfg.PLANNER_MODEL_PATH == original_planner
