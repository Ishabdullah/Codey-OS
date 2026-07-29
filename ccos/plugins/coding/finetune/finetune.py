"""
Fine-tuning Export Plugin — thin CCOS adapter over core/finetune_prep.py
and the safe, read-only functions of core/lora_import.py.

Wraps the generative fine-tuning data-prep pipeline (dataset curation,
export, notebook generation, instructions) plus adapter inspection.

Deliberately NOT wrapped: merge_lora_with_llama_cpp, swap_to_finetuned_model,
create_backup_before_import, rollback_to_backup, and import_lora_adapter from
core/lora_import.py. Those mutate the live model file the daemon runs on —
see manifest.json's description for the reasoning. They remain callable via
main.py's existing --import-lora path; this plugin does not touch that.

`DatasetCurator` is a class, not a plain function, so it isn't exposed
directly as a capability implementation; `curate_examples` below is a thin
functional wrapper around it, following the same function-only convention
as the other coding plugins.
"""

from ccos.plugins._pathutil import ensure_repo_root_on_path

ensure_repo_root_on_path()

from typing import Dict, List

from core.finetune_prep import (
    DatasetCurator,
    export_dataset,
    generate_notebook,
    prepare_finetune_data,
    print_instructions,
)
from core.lora_import import get_adapter_info, validate_lora_adapter


def curate_examples(days: int = 30, min_quality: float = 0.7, max_examples: int = 500) -> List[Dict]:
    """Curate ShareGPT-format fine-tuning examples from episodic interaction history."""
    return DatasetCurator().curate_examples(days, min_quality, max_examples)


def test() -> bool:
    """Plugin self-test — verify a read-only capability runs without raising."""
    valid, msg = validate_lora_adapter("/nonexistent/adapter/path")
    assert isinstance(valid, bool), "Expected bool"
    assert isinstance(msg, str), "Expected str"
    return True
