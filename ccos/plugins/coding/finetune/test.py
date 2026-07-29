#!/usr/bin/env python3
"""Test for finetune plugin."""

import importlib.util
import json
import hashlib
import shutil
import tempfile
from pathlib import Path

# _pathutil.py lives at ccos/plugins/_pathutil.py, two levels above this
# plugin's directory (test.py -> finetune/ -> coding/ -> plugins/).
# Loaded by file path since the ccos package isn't importable yet.
_pathutil_path = Path(__file__).resolve().parent.parent.parent / "_pathutil.py"
_spec = importlib.util.spec_from_file_location("_pathutil", _pathutil_path)
_pathutil = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_pathutil)
_pathutil.ensure_repo_root_on_path()

from ccos.plugins.coding.finetune.finetune import (
    create_backup_before_import,
    export_dataset,
    generate_notebook,
    get_adapter_info,
    print_instructions,
    rollback_to_backup,
    test,
    validate_lora_adapter,
)
import core.loader_v2 as loader_v2
import utils.config as cfg


def _make_throwaway_adapter(valid: bool = True) -> str:
    """Create a throwaway LoRA adapter directory. Caller must clean up."""
    adapter_dir = tempfile.mkdtemp(prefix="finetune_test_adapter_")
    if valid:
        config = {
            "r": 16,
            "lora_alpha": 16,
            "target_modules": ["q_proj", "v_proj"],
            "base_model_name_or_path": "unsloth/Qwen2.5-Coder-1.5B-Instruct-bnb-4bit",
        }
        (Path(adapter_dir) / "adapter_config.json").write_text(json.dumps(config))
        # Tiny placeholder weights file — not a real tensor file, just enough
        # for validate_lora_adapter's file-existence check.
        (Path(adapter_dir) / "adapter_model.safetensors").write_bytes(b"\x00" * 16)
    return adapter_dir


def test_validate_missing_adapter():
    valid, msg = validate_lora_adapter("/nonexistent/adapter/path")
    assert valid is False
    assert "not found" in msg.lower()
    print(f"[PASS] validate_lora_adapter() rejects a missing path: {msg!r}")


def test_validate_incomplete_adapter():
    adapter_dir = _make_throwaway_adapter(valid=False)
    try:
        valid, msg = validate_lora_adapter(adapter_dir)
        assert valid is False
        assert "missing required files" in msg.lower()
        print(f"[PASS] validate_lora_adapter() rejects an incomplete adapter dir: {msg!r}")
    finally:
        shutil.rmtree(adapter_dir, ignore_errors=True)


def test_validate_and_info_on_dummy_adapter():
    adapter_dir = _make_throwaway_adapter(valid=True)
    try:
        valid, msg = validate_lora_adapter(adapter_dir)
        assert valid is True, msg
        print(f"[PASS] validate_lora_adapter() accepts a well-formed dummy adapter: {msg!r}")

        info_dict = get_adapter_info(adapter_dir)
        assert info_dict["lora_r"] == 16
        assert info_dict["lora_alpha"] == 16
        assert info_dict["base_model"] == "unsloth/Qwen2.5-Coder-1.5B-Instruct-bnb-4bit"
        assert info_dict["size_mb"] > 0
        print(f"[PASS] get_adapter_info() reports dummy adapter metadata: {info_dict}")
    finally:
        shutil.rmtree(adapter_dir, ignore_errors=True)


def test_export_dataset_to_throwaway_dir():
    examples = [
        {
            "conversations": [
                {"role": "system", "content": "You are Codey."},
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "hi there"},
            ],
            "metadata": {"source": "test", "quality": 1.0},
        }
    ]
    out_dir = tempfile.mkdtemp(prefix="finetune_test_export_")
    try:
        output_file, count = export_dataset(examples, out_dir, model_variant="both")
        assert count == 1
        assert Path(output_file).exists()
        lines = Path(output_file).read_text().strip().splitlines()
        assert len(lines) == 1
        assert json.loads(lines[0])["conversations"][1]["content"] == "hello"
        print(f"[PASS] export_dataset() wrote {count} example(s) to {output_file}")
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)


def test_generate_notebook_to_throwaway_dir():
    out_dir = tempfile.mkdtemp(prefix="finetune_test_notebook_")
    try:
        notebook_path = generate_notebook("1.5b", out_dir)
        assert Path(notebook_path).exists()
        notebook = json.loads(Path(notebook_path).read_text())
        assert notebook["nbformat"] == 4
        assert len(notebook["cells"]) == 2
        print(f"[PASS] generate_notebook() wrote a real notebook to {notebook_path}")
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)


def test_print_instructions_runs():
    # Purely prints to stdout — just verify it doesn't raise.
    print_instructions("/tmp/fake-dataset.jsonl", "/tmp/fake-notebook.ipynb", "1.5b")
    print("[PASS] print_instructions() ran without raising")


class _FakeLoader:
    """
    Stand-in for core.loader_v2's real ModelLoader. rollback_to_backup()
    calls get_loader().unload()/.load_primary() as its final step to reload
    the (just-restored) model. The real loader spawns a llama-server
    subprocess against whatever path is baked into core.loader_v2's
    module-level MODEL_PATH constant (captured at import time, so it does
    NOT follow our cfg.MODEL_PATH monkeypatch below) — so for this test we
    swap in a no-op fake to guarantee no subprocess is spawned and no real
    model file is ever touched, regardless of what path is configured.
    """

    def unload(self):
        pass

    def load_primary(self):
        return True

    def load_secondary(self):
        return True


def test_create_backup_and_rollback_on_dummy_model():
    """
    create_backup_before_import/rollback_to_backup read the model path from
    utils.config (MODEL_PATH/SECONDARY_MODEL_PATH), not from an argument —
    so this test points cfg.MODEL_PATH at a throwaway dummy .gguf file for
    the duration of the test and restores it afterward. The real model in
    ~/models/ is never touched. The model-reload step is also stubbed out
    (see _FakeLoader) so no llama-server subprocess is spawned.
    """
    work_dir = Path(tempfile.mkdtemp(prefix="finetune_test_backup_"))
    dummy_model = work_dir / "dummy-model.gguf"
    dummy_model.write_bytes(b"ORIGINAL-MODEL-BYTES-v1")
    original_checksum = hashlib.sha256(dummy_model.read_bytes()).hexdigest()

    original_model_path = cfg.MODEL_PATH
    original_get_loader = loader_v2.get_loader
    try:
        cfg.MODEL_PATH = dummy_model
        loader_v2.get_loader = lambda: _FakeLoader()

        # Before: only the dummy model file exists.
        before_listing = sorted(p.name for p in work_dir.iterdir())
        assert before_listing == ["dummy-model.gguf"]
        print(f"[BEFORE] {work_dir}: {before_listing}")

        backup_path = create_backup_before_import("primary")
        assert backup_path is not None, "Expected a backup path"
        backup_file = Path(backup_path)
        assert backup_file.exists(), "Backup file was not created"
        assert backup_file.parent == work_dir
        backup_checksum = hashlib.sha256(backup_file.read_bytes()).hexdigest()
        assert backup_checksum == original_checksum, "Backup content mismatch"

        after_backup_listing = sorted(p.name for p in work_dir.iterdir())
        assert backup_file.name in after_backup_listing
        assert len(after_backup_listing) == 2
        print(f"[AFTER create_backup_before_import] {work_dir}: {after_backup_listing}")
        print(f"[PASS] create_backup_before_import() created a real backup: {backup_path} (sha256={backup_checksum[:12]}...)")

        # Simulate the "live model" getting overwritten/corrupted after backup.
        dummy_model.write_bytes(b"CORRUPTED-OR-NEW-MODEL-BYTES-v2")
        corrupted_checksum = hashlib.sha256(dummy_model.read_bytes()).hexdigest()
        assert corrupted_checksum != original_checksum
        print(f"[SIMULATED CORRUPTION] dummy-model.gguf sha256={corrupted_checksum[:12]}...")

        success, msg = rollback_to_backup(str(backup_file), "primary")
        assert success is True, msg
        print(f"[PASS] rollback_to_backup() reported success: {msg!r}")

        restored_checksum = hashlib.sha256(dummy_model.read_bytes()).hexdigest()
        assert restored_checksum == original_checksum, "Rollback did not restore original content"
        print(f"[AFTER rollback_to_backup] dummy-model.gguf sha256={restored_checksum[:12]}... (matches original)")

        # rollback_to_backup deletes the backup marker file after restoring.
        after_rollback_listing = sorted(p.name for p in work_dir.iterdir())
        assert after_rollback_listing == ["dummy-model.gguf"]
        print(f"[AFTER rollback_to_backup] {work_dir}: {after_rollback_listing}")
        print("[PASS] create_backup_before_import()/rollback_to_backup() round-trip verified on dummy .gguf file")
    finally:
        cfg.MODEL_PATH = original_model_path
        loader_v2.get_loader = original_get_loader
        shutil.rmtree(work_dir, ignore_errors=True)


def test_self_test():
    result = test()
    assert result is True
    print("[PASS] Self-test passed")


if __name__ == "__main__":
    test_validate_missing_adapter()
    test_validate_incomplete_adapter()
    test_validate_and_info_on_dummy_adapter()
    test_export_dataset_to_throwaway_dir()
    test_generate_notebook_to_throwaway_dir()
    test_print_instructions_runs()
    test_create_backup_and_rollback_on_dummy_model()
    test_self_test()
    print("\nAll finetune tests passed!")
