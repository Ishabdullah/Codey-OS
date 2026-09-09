"""
Fine-tuning Export Plugin — thin CCOS adapter over core/finetune_prep.py
and the safe, read-only functions of core/lora_import.py.

Wraps the generative fine-tuning data-prep pipeline (dataset curation,
export, notebook generation, instructions) plus adapter inspection.

Deliberately NOT wrapped: merge_lora_with_llama_cpp, swap_to_finetuned_model,
and import_lora_adapter from core/lora_import.py. Those replace/reload the
live model file the daemon runs on — see manifest.json's description for the
reasoning. They remain callable via main.py's existing --import-lora path;
this plugin does not touch that.

create_backup_before_import and rollback_to_backup ARE wrapped (Ish's
decision). create_backup_before_import is file-copy-only. rollback_to_backup
is NOT file-copy-only — it overwrites the live, configured model file and
deletes its own backup, then reloads the model via core/loader_v2.py.
manifest.json's `coding.finetune_rollback_backup` capability description
(dated 2026-07-30) still describes the `model_variant="secondary"` branch
as hitting `NEW-24`'s `AttributeError` (`loader.load_secondary()` doesn't
exist) — that was true when the description was written but is stale:
NEW-24 was fixed (2026-08-09, corrected 2026-09-04) and M1-D (2026-08-23)
collapsed "primary"/"secondary" onto the same `core.loader_v2.get_loader()`
reload path (see rollback_to_backup()'s own comment on this). Both variants
reload the same way today; there is no load_secondary() call anywhere.
The real residual risk on this now-reachable capability is narrower and
already handled: a `backup_path` not matching create_backup_before_import()'s
own naming convention falls back to restoring onto the CURRENT config
pointer rather than the derived original path — reproducing NEW-91/NEW-163's
data-loss shape for that one input shape — and is already logged via a
`warning()` at that fallback site, not silent. manifest.json's description
itself still needs updating to drop the stale NEW-24 claim (not done here —
out of this file's scope, flag for whoever next touches that manifest).

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
    print_instructions,
)
from core.lora_import import (
    create_backup_before_import,
    get_adapter_info,
    rollback_to_backup,
    validate_lora_adapter,
)


def curate_examples(days: int = 30, min_quality: float = 0.7, max_examples: int = 500) -> List[Dict]:
    """Curate ShareGPT-format fine-tuning examples from episodic interaction history."""
    return DatasetCurator().curate_examples(days, min_quality, max_examples)


def test() -> bool:
    """Plugin self-test — verify a read-only capability runs without raising."""
    valid, msg = validate_lora_adapter("/nonexistent/adapter/path")
    assert isinstance(valid, bool), "Expected bool"
    assert isinstance(msg, str), "Expected str"
    return True
