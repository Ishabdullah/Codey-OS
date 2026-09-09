"""
NEW-91/NEW-163 regression (NEW_ISSUES.md) — rollback_to_backup() destroying
the fine-tuned checkpoint instead of restoring the original base file.

Both entries described the same underlying bug in core/lora_import.py's
rollback_to_backup(), filed independently: NEW-91 for the "secondary"/
planner branch, NEW-163 for the "primary" branch (the two collapsed onto
one code path under the single-model migration, so it's one bug, not two).

Before the fix: rollback_to_backup() restored a backup by copying it onto
whatever cfg.MODEL_PATH/cfg.PLANNER_MODEL_PATH CURRENTLY named. After a
successful swap_to_finetuned_model(), that name has already been mutated to
point at the fine-tuned file's path — so a rollback silently overwrote the
fine-tuned checkpoint's on-disk file with base weights, destroying it with
no way to get it back, instead of restoring the original base file at its
own path.

After the fix: rollback_to_backup() derives the original base path from the
backup file's own name (create_backup_before_import() always names it
"<original_stem>.backup<suffix>" in the original file's own directory) and
restores onto THAT path, resetting cfg.MODEL_PATH/cfg.PLANNER_MODEL_PATH to
match — never touching whatever file the config pointer currently names.

No real llama-server process is spawned (CLAUDE.md rule 2, RAM discipline)
— the loader is patched with a lightweight fake, matching
tests/test_new84_stale_model_path.py's and
tests/test_lora_import_swap_sync.py's conventions.
"""
import hashlib
from unittest.mock import MagicMock, patch

import pytest

import core.loader_v2 as lv
import core.lora_import as li
import core.resource_gate as rg
import utils.config as cfg


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


def _admit_everything(monkeypatch):
    fake_decision = MagicMock(admitted=True, estimated_cost_bytes=1024, reason="ok")
    monkeypatch.setattr(rg, "reserve_slot", lambda spec, **k: (fake_decision, "slot-1"))
    monkeypatch.setattr(rg, "mark_resident", lambda *a, **k: True)
    monkeypatch.setattr(rg, "release_slot", lambda *a, **k: True)
    monkeypatch.setattr(rg, "read_meminfo", lambda *a, **k: {"MemAvailable": 10**10})
    # Without this, ModelLoader.load_primary()'s genuine-spawn branch calls
    # the real confirm_resident_and_mark_slot(), which polls actual system
    # /proc/meminfo for up to CONFIRM_RESIDENT_TIMEOUT_S (~10s) looking for a
    # MemAvailable drop a fake/no-op load will never produce, before falling
    # through to "mark resident anyway" (NEW_ISSUES.md NEW-418). Stub it to
    # go straight to the already-mocked mark_resident() above.
    monkeypatch.setattr(
        lv,
        "confirm_resident_and_mark_slot",
        lambda slot_id, baseline_meminfo, estimated_cost_bytes, timeout_s=None, poll_interval_s=None, pid=None: rg.mark_resident(slot_id, pid=pid),
    )


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_rollback_after_swap_restores_base_and_preserves_finetune(monkeypatch, tmp_path):
    """
    The actual NEW-91/NEW-163 scenario: create a backup of the base model,
    swap to a fine-tuned file (mutating cfg.MODEL_PATH/PLANNER_MODEL_PATH to
    point at it), then roll back. The fine-tuned file must survive
    UNTOUCHED, the original base file must be restored at ITS OWN path, and
    the config pointer must end up pointing at the restored base file, not
    the (now again distinct) fine-tuned path.
    """
    _admit_everything(monkeypatch)

    base_model = tmp_path / "codeyOS-4b.gguf"
    base_model.write_bytes(b"BASE-MODEL-WEIGHTS")
    base_checksum = _sha256(base_model)

    finetuned_model = tmp_path / "codeyOS-finetuned-primary.gguf"
    finetuned_model.write_bytes(b"FINETUNED-MODEL-WEIGHTS")
    finetuned_checksum = _sha256(finetuned_model)
    assert finetuned_checksum != base_checksum  # sanity

    cfg.MODEL_PATH = base_model
    cfg.PLANNER_MODEL_PATH = base_model

    # 1. Back up the base model before swapping (mirrors
    #    import_lora_adapter()'s own call order).
    backup_path = li.create_backup_before_import("primary")
    assert backup_path is not None
    from pathlib import Path

    backup_file = Path(backup_path)
    assert backup_file.exists()
    assert _sha256(backup_file) == base_checksum

    # 2. Swap to the fine-tuned file — this is what mutates
    #    cfg.MODEL_PATH/PLANNER_MODEL_PATH to the fine-tuned path, the
    #    precondition that exposes the bug.
    lv._loader = None
    with patch.object(lv, "LlamaServer", _FakeLlamaServer):
        ok, msg = li.swap_to_finetuned_model(str(finetuned_model), "primary")
    assert ok is True, msg
    assert cfg.MODEL_PATH == finetuned_model
    assert cfg.PLANNER_MODEL_PATH == finetuned_model

    # 3. Roll back. Reload is stubbed out via a fake loader so no real
    #    subprocess is spawned.
    lv._loader = None
    with patch.object(lv, "get_loader") as mock_get_loader:
        fake_loader = MagicMock()
        fake_loader.load_primary.return_value = True
        mock_get_loader.return_value = fake_loader

        ok, msg = li.rollback_to_backup(str(backup_file), "primary")
    assert ok is True, msg

    # The fine-tuned file must NOT have been overwritten/destroyed.
    assert finetuned_model.exists(), "Fine-tuned checkpoint was deleted by rollback"
    assert _sha256(finetuned_model) == finetuned_checksum, (
        "Fine-tuned checkpoint's contents were overwritten by rollback — "
        "this is the exact NEW-91/NEW-163 data-loss bug"
    )

    # The original base file must be restored at its OWN path.
    assert base_model.exists()
    assert _sha256(base_model) == base_checksum

    # The config pointer must end up pointing at the restored base file,
    # not still at the fine-tuned path.
    assert cfg.MODEL_PATH == base_model
    assert cfg.PLANNER_MODEL_PATH == base_model

    # The backup marker is consumed on a successful rollback.
    assert not backup_file.exists()


def test_rollback_without_prior_swap_still_works(monkeypatch, tmp_path):
    """
    Sanity check for the common/simple case (no swap happened yet, e.g. a
    corrupted-in-place restore): cfg.MODEL_PATH already equals the original
    path, so the fixed path-derivation-from-backup-name logic must still
    resolve to the same file and round-trip correctly.
    """
    model = tmp_path / "codeyOS-4b.gguf"
    model.write_bytes(b"ORIGINAL-BYTES")
    original_checksum = _sha256(model)

    cfg.MODEL_PATH = model
    cfg.PLANNER_MODEL_PATH = model

    from pathlib import Path

    backup_path = li.create_backup_before_import("primary")
    backup_file = Path(backup_path)
    assert _sha256(backup_file) == original_checksum

    # Simulate corruption of the live file.
    model.write_bytes(b"CORRUPTED-BYTES")
    assert _sha256(model) != original_checksum

    lv._loader = None
    with patch.object(lv, "get_loader") as mock_get_loader:
        fake_loader = MagicMock()
        fake_loader.load_primary.return_value = True
        mock_get_loader.return_value = fake_loader

        ok, msg = li.rollback_to_backup(str(backup_file), "primary")
    assert ok is True, msg

    assert _sha256(model) == original_checksum
    assert cfg.MODEL_PATH == model
    assert cfg.PLANNER_MODEL_PATH == model
    assert not backup_file.exists()
