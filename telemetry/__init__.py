"""
Codey-OS telemetry layer (docs/telemetry_layer_design.md).

T0 status: this package is dead code. Nothing outside `telemetry/` and
`tests/test_telemetry_*.py` imports it yet. Importing this package (or
any module inside it) must never start a thread, create a directory, or
touch the filesystem beyond reading its own schema JSON — see
telemetry/store.py's module docstring for the lazy-init contract that
makes that true.

This package imports nothing from `ccos.*`, ever — enforced by
tests/test_telemetry_no_ccos_imports.py (a static AST walk, not a
runtime check, so the guarantee holds even for code paths that never
execute in tests). See docs/telemetry_layer_design.md §1.3.

Public API re-exported here:
- `CODEY_TELEMETRY_ENABLED` — the kill-switch value read once at
  utils.config's import (re-exported for convenience; telemetry/store.py
  is what actually gates on it via its own `TELEMETRY_ENABLED`).
- `record_*` — the category A-G + meta emit functions (telemetry/recorders.py).
- `SCHEMA_VERSION` / `SCHEMA_SHA256_12` — from telemetry/schema.py.
"""

from __future__ import annotations

from utils.config import CODEY_TELEMETRY_ENABLED

from telemetry.recorders import (
    record_cotenancy_transition,
    record_deferral_resolved,
    record_deterministic_bypass,
    record_device_sample,
    record_dispatch_refused_human_present,
    record_extraction_attempt,
    record_gate_decision,
    record_grounding_check,
    record_inference_completion,
    record_inference_failed,
    record_meta_event,
    record_run_start,
    record_task_finished,
    record_task_started,
)
from telemetry.schema import SCHEMA_SHA256_12, SCHEMA_VERSION

__all__ = [
    "CODEY_TELEMETRY_ENABLED",
    "SCHEMA_VERSION",
    "SCHEMA_SHA256_12",
    "record_cotenancy_transition",
    "record_deferral_resolved",
    "record_deterministic_bypass",
    "record_device_sample",
    "record_dispatch_refused_human_present",
    "record_extraction_attempt",
    "record_gate_decision",
    "record_grounding_check",
    "record_inference_completion",
    "record_inference_failed",
    "record_meta_event",
    "record_run_start",
    "record_task_finished",
    "record_task_started",
]
