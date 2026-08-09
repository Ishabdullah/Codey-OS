"""
NEW-84 regression (NEW_ISSUES.md) — hot-swap staleness.

core/loader_v2.py's ModelLoader.load_primary() and
core/planner_loader.py's PlannerLoader.load() used to import MODEL_PATH /
PLANNER_MODEL_PATH as plain module-level names bound once at their own
import time. core/lora_import.py's swap_to_finetuned_model()/
rollback_to_backup() mutate `utils.config.MODEL_PATH`/`PLANNER_MODEL_PATH`
on the live config module object, which the loaders never re-read — so a
"successful" hot-swap silently kept loading the original weights.

Also covers the addendum found during sub-task 2's code-reviewer pass:
core/resource_gate.py's KNOWN_MODEL_ARCHS dict used to be keyed by the same
import-time path strings, so even after the loader staleness fix, a
post-swap load would miss the KV-cache-cost arch lookup and silently drop
that term to 0 — an admission-safety bug (underestimated cost could let the
gate over-admit a load it should reject).

All tests here use fake/mocked LlamaServer + resource_gate slot functions —
no real llama-server process is spawned (CLAUDE.md rule 2, RAM discipline).
"""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import core.loader_v2 as lv
import core.lora_import as li
import core.planner_loader as pl
import core.resource_gate as rg
import utils.config as cfg


class _CapturingLlamaServer:
    """Stand-in for LlamaServer that records the model_path it was
    constructed with, and otherwise behaves like a successful spawn."""

    captured_paths: list = []

    def __init__(self, model_path, port=None):
        type(self).captured_paths.append(model_path)
        self.model_path = model_path
        self.process = MagicMock(pid=42)
        self._started = True

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
    pl._planner_loader = None
    _CapturingLlamaServer.captured_paths = []
    original_model_path = cfg.MODEL_PATH
    original_planner_path = cfg.PLANNER_MODEL_PATH
    yield
    lv._loader = None
    pl._planner_loader = None
    cfg.MODEL_PATH = original_model_path
    cfg.PLANNER_MODEL_PATH = original_planner_path


def _admit_everything(monkeypatch, reserve_calls):
    fake_decision = MagicMock(admitted=True, estimated_cost_bytes=1024, reason="ok")
    monkeypatch.setattr(
        rg,
        "reserve_slot",
        lambda spec, **k: (reserve_calls.append(spec) or fake_decision, "slot-1"),
    )
    monkeypatch.setattr(rg, "mark_resident", lambda *a, **k: True)
    monkeypatch.setattr(rg, "release_slot", lambda *a, **k: True)
    monkeypatch.setattr(rg, "read_meminfo", lambda *a, **k: {"MemAvailable": 10**10})


# ── loader_v2: primary loader reads cfg.MODEL_PATH fresh ────────────────────


def test_load_primary_uses_swapped_model_path_not_import_time_binding(monkeypatch, tmp_path):
    reserve_calls = []
    _admit_everything(monkeypatch, reserve_calls)

    swapped_path = tmp_path / "codeyOS-finetuned-7b.gguf"
    swapped_path.write_bytes(b"x")

    # Simulate exactly what core/lora_import.py's swap_to_finetuned_model()
    # does: mutate the live utils.config module object, not re-import.
    cfg.MODEL_PATH = swapped_path

    with patch.object(lv, "LlamaServer", _CapturingLlamaServer):
        loader = lv.get_loader()
        assert loader.load_primary() is True

    assert _CapturingLlamaServer.captured_paths == [swapped_path]
    assert reserve_calls[0].path == swapped_path


def test_load_primary_missing_swapped_file_fails_cleanly(monkeypatch, tmp_path):
    """If cfg.MODEL_PATH now points at a file that doesn't exist, load_primary()
    must fail on THAT path's existence check, not silently fall back to
    whatever path was bound at this module's import time."""
    nonexistent = tmp_path / "does-not-exist.gguf"
    cfg.MODEL_PATH = nonexistent

    with patch.object(lv, "LlamaServer") as MockServer:
        loader = lv.get_loader()
        result = loader.load_primary()

    assert result is False
    MockServer.assert_not_called()


# ── planner_loader: planner loader reads cfg.PLANNER_MODEL_PATH fresh ───────


def test_planner_load_uses_swapped_model_path_not_import_time_binding(monkeypatch, tmp_path):
    reserve_calls = []
    _admit_everything(monkeypatch, reserve_calls)

    swapped_path = tmp_path / "codeyOS-finetuned-1.5b.gguf"
    swapped_path.write_bytes(b"x")

    cfg.PLANNER_MODEL_PATH = swapped_path

    with patch.object(lv, "LlamaServer", _CapturingLlamaServer):
        planner = pl.get_planner_loader()
        assert planner.load() is True

    assert _CapturingLlamaServer.captured_paths == [swapped_path]
    assert reserve_calls[0].path == swapped_path


# ── lora_import: end-to-end swap through the real swap function ─────────────


def test_swap_to_finetuned_model_primary_reaches_new_path(monkeypatch, tmp_path):
    """swap_to_finetuned_model("primary") must result in the loader actually
    being asked to spawn the NEW file, not the original."""
    reserve_calls = []
    _admit_everything(monkeypatch, reserve_calls)

    new_model = tmp_path / "finetuned-primary.gguf"
    new_model.write_bytes(b"x")

    lv._loader = None
    with patch.object(lv, "LlamaServer", _CapturingLlamaServer):
        ok, msg = li.swap_to_finetuned_model(str(new_model), "primary")

    assert ok is True, msg
    assert cfg.MODEL_PATH == new_model
    assert _CapturingLlamaServer.captured_paths == [new_model]


def test_swap_to_finetuned_model_secondary_reaches_new_path_via_planner_model_path(
    monkeypatch, tmp_path
):
    """
    The critical NEW-84 case for the "secondary" branch: lora_import.py used
    to mutate cfg.SECONDARY_MODEL_PATH, a config name PlannerLoader.load()
    has never read (it reads PLANNER_MODEL_PATH — two distinct names,
    identical only by coincidental default value). Fixed to mutate
    cfg.PLANNER_MODEL_PATH instead. This test would have passed even before
    the loader-staleness fix landed, and failed on the pre-fix
    SECONDARY_MODEL_PATH mismatch — it specifically targets that mismatch,
    not just the import-time-binding staleness the primary-side test covers.
    """
    reserve_calls = []
    _admit_everything(monkeypatch, reserve_calls)

    new_model = tmp_path / "finetuned-secondary.gguf"
    new_model.write_bytes(b"x")

    pl._planner_loader = None
    with patch.object(lv, "LlamaServer", _CapturingLlamaServer):
        ok, msg = li.swap_to_finetuned_model(str(new_model), "secondary")

    assert ok is True, msg
    assert cfg.PLANNER_MODEL_PATH == new_model
    assert _CapturingLlamaServer.captured_paths == [new_model]


def test_swap_to_finetuned_model_secondary_does_not_rely_on_secondary_model_path(
    monkeypatch, tmp_path
):
    """Pin the specific mismatch: cfg.SECONDARY_MODEL_PATH must be left
    untouched by a "secondary" swap (it's not what the planner loader
    reads), confirming the fix targets the right config name rather than
    setting both and papering over the bug."""
    reserve_calls = []
    _admit_everything(monkeypatch, reserve_calls)

    original_secondary = cfg.SECONDARY_MODEL_PATH
    new_model = tmp_path / "finetuned-secondary-2.gguf"
    new_model.write_bytes(b"x")

    pl._planner_loader = None
    try:
        with patch.object(lv, "LlamaServer", _CapturingLlamaServer):
            ok, msg = li.swap_to_finetuned_model(str(new_model), "secondary")
        assert ok is True, msg
        assert cfg.SECONDARY_MODEL_PATH == original_secondary
    finally:
        cfg.SECONDARY_MODEL_PATH = original_secondary


# ── resource_gate: KNOWN_MODEL_ARCHS keyed by model_id, swap-proof ──────────


def test_resource_gate_arch_lookup_survives_model_path_swap(tmp_path):
    """
    Before the fix, KNOWN_MODEL_ARCHS was keyed by str(MODEL_PATH) bound at
    resource_gate.py's own import time — a ModelSpec built with the swapped
    path would miss the dict lookup entirely and silently compute
    kv_cache_bytes == 0. Now keyed by ModelSpec.model_id ("primary"/
    "planner"), which core/loader_v2.py and core/planner_loader.py always
    pass regardless of which file is currently configured.
    """
    swapped_path = tmp_path / "finetuned-primary.gguf"
    swapped_path.write_bytes(b"x" * 1000)

    spec = rg.ModelSpec(model_id="primary", path=swapped_path, n_ctx=32768)
    cost = rg.estimate_model_load_cost(spec)

    expected_kv = rg.estimate_kv_cache_bytes(rg.QWEN25_7B_ARCH, n_ctx=32768)
    assert cost.kv_cache_bytes == expected_kv
    assert cost.kv_cache_bytes != 0


def test_resource_gate_arch_lookup_survives_planner_path_swap(tmp_path):
    swapped_path = tmp_path / "finetuned-planner.gguf"
    swapped_path.write_bytes(b"x" * 1000)

    spec = rg.ModelSpec(model_id="planner", path=swapped_path, n_ctx=32768)
    cost = rg.estimate_model_load_cost(spec)

    expected_kv = rg.estimate_kv_cache_bytes(rg.QWEN25_1_5B_ARCH, n_ctx=32768)
    assert cost.kv_cache_bytes == expected_kv
    assert cost.kv_cache_bytes != 0


def test_resource_gate_unknown_model_id_still_omits_kv_term(tmp_path):
    """Sanity check that the re-keying didn't accidentally make every
    model_id resolve — an unrelated model_id must still degrade to
    kv_cache_bytes == 0 with no exception."""
    other_path = tmp_path / "some-other-model.gguf"
    other_path.write_bytes(b"x" * 1000)
    spec = rg.ModelSpec(model_id="not-primary-or-planner", path=other_path, n_ctx=32768)
    cost = rg.estimate_model_load_cost(spec)
    assert cost.kv_cache_bytes == 0
