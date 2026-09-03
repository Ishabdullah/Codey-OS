"""
The category A-G + meta `record_*()` functions that map domain objects
(GateDecision, ResourceSnapshot, llama-server `timings`, etc.) into
schema records and hand them to telemetry/store.py.

Nothing in Codey-OS calls any function in this module yet (T0 — dead code
until T1+ wires call sites in). It is written now so those sub-tasks only
need to import and call, not design the record shape.

Deliberately does NOT import core.resource_gate (§1.1, §1.3): the design
takes decision objects by `dataclasses.asdict()`, never by importing the
dataclass type itself, so this module never touches `core.*`. A future
call site (which already imports core.resource_gate for its own reasons)
passes the already-constructed dict or dataclass instance in; this module
treats it as `Any` and calls `dataclasses.asdict()` only when it receives
a real dataclass instance (tests may also pass a plain dict fixture).
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any, Container, Dict, List, Optional

from telemetry import envelope, store
from telemetry.schema import SCHEMA_SHA256_12, SCHEMA_VERSION


def _as_dict(obj: Any) -> Dict[str, Any]:
    """Accepts a dataclass instance, a plain dict, or None. Never raises
    on an unexpected type — returns {} rather than propagating a
    TypeError into an instrumented call site."""
    if obj is None:
        return {}
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return dataclasses.asdict(obj)
    if isinstance(obj, dict):
        return obj
    return {}


def _emit(
    *,
    category: str,
    event_type: str,
    emitter: str,
    pid: int,
    run_id: Optional[str],
    body: Dict[str, Any],
    correlation_id: Optional[str] = None,
    nulls: Optional[Dict[str, str]] = None,
    always_keep_null: Container[str] = (),
) -> Dict[str, Any]:
    """
    Builds and hands a record to telemetry/store.py.

    `body` fields whose value is None are pruned before the envelope is
    built UNLESS the caller either (a) supplied a matching `nulls[f"body.{field}"]`
    reason — a genuine honest-null the design wants visible — or (b)
    listed the field in `always_keep_null` — a field the design wants
    recorded as null even with no per-call reason (currently only
    `device.device_uptime_sec`, which is a permanent, device-wide null
    per fact 0.2, not a per-call observation failure).

    Implementation choice, flagged for review: the honest-null contract
    (§2.0.1) is for facts the layer attempted to observe and couldn't.
    It is a different thing from a field that simply isn't meaningful yet
    at this event_type (e.g. `task_finished`-only fields on a
    `task_started` record, or a decision dataclass not defining a field
    another decision type has). The design's closed reason-code set has
    no code for "not applicable to this event_type", so rather than
    inventing one, such fields are omitted from the body entirely instead
    of being written as an unreasoned null.

    Returns the built record (T2: record_run_start() needs it to also
    write runs/<run_id>.json; every other existing caller ignores the
    return value, so this is additive, not a behaviour change for them).
    """
    nulls = nulls or {}
    pruned_body = {
        key: value
        for key, value in body.items()
        if value is not None or key in always_keep_null or f"body.{key}" in nulls
    }

    resolved_run_id = run_id if run_id is not None else store.get_run_id()
    record = envelope.build_envelope(
        category=category,
        event_type=event_type,
        emitter=emitter,
        pid=pid,
        run_id=resolved_run_id,
        body=pruned_body,
        correlation_id=correlation_id,
        nulls=nulls,
    )
    store.record(record)
    return record


# ── A. Inference ─────────────────────────────────────────────────────────

def record_inference_completion(
    *,
    emitter: str,
    pid: int,
    backend: str,
    wall_ms: float,
    stream: bool,
    max_tokens_requested: int,
    prompt_chars: int,
    message_count: int,
    role: Optional[str] = None,
    thinking_mode: Optional[bool] = None,
    model_file: Optional[str] = None,
    model_quant: Optional[str] = None,
    model_sha256: Optional[str] = None,
    n_ctx: Optional[int] = None,
    prompt_tokens: Optional[int] = None,
    completion_tokens: Optional[int] = None,
    cached_prompt_tokens: Optional[int] = None,
    prefill_tps: Optional[float] = None,
    generation_tps: Optional[float] = None,
    prefill_ms: Optional[float] = None,
    generation_ms: Optional[float] = None,
    prompt_per_token_ms: Optional[float] = None,
    predicted_per_token_ms: Optional[float] = None,
    ttft_ms: Optional[float] = None,
    queue_wait_ms: Optional[float] = None,
    finish_reason: Optional[str] = None,
    interactive: bool = False,
    server_request_id: Optional[str] = None,
    server_fingerprint: Optional[str] = None,
    prompt_sha256: Optional[str] = None,
    correlation_id: Optional[str] = None,
    run_id: Optional[str] = None,
    nulls: Optional[Dict[str, str]] = None,
) -> None:
    body = {
        "role": role,
        "thinking_mode": thinking_mode,
        "backend": backend,
        "model_file": model_file,
        "model_quant": model_quant,
        "model_sha256": model_sha256,
        "n_ctx": n_ctx,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "cached_prompt_tokens": cached_prompt_tokens,
        "prefix_cache_hit": (cached_prompt_tokens or 0) > 0 if cached_prompt_tokens is not None else None,
        "prefill_tps": prefill_tps,
        "generation_tps": generation_tps,
        "prefill_ms": prefill_ms,
        "generation_ms": generation_ms,
        "prompt_per_token_ms": prompt_per_token_ms,
        "predicted_per_token_ms": predicted_per_token_ms,
        "ttft_ms": ttft_ms,
        "wall_ms": wall_ms,
        "queue_wait_ms": queue_wait_ms,
        "finish_reason": finish_reason,
        "interactive": interactive,
        "server_request_id": server_request_id,
        "server_fingerprint": server_fingerprint,
        "stream": stream,
        "max_tokens_requested": max_tokens_requested,
        "prompt_sha256": prompt_sha256,
        "prompt_chars": prompt_chars,
        "message_count": message_count,
        # error_class is a completion_failed-only field (§2.A) — omitted
        # here rather than always set to None, so a successful completion
        # never needs a `nulls` entry for a field that isn't applicable to
        # it in the first place.
    }
    _emit(
        category="inference",
        event_type="completion",
        emitter=emitter,
        pid=pid,
        run_id=run_id,
        body=body,
        correlation_id=correlation_id,
        nulls=nulls,
    )


def record_inference_failed(
    *,
    emitter: str,
    pid: int,
    backend: str,
    error_class: str,
    wall_ms: float,
    max_tokens_requested: int,
    prompt_chars: int,
    message_count: int,
    stream: bool = False,
    role: Optional[str] = None,
    correlation_id: Optional[str] = None,
    run_id: Optional[str] = None,
    nulls: Optional[Dict[str, str]] = None,
) -> None:
    body = {
        "role": role,
        "thinking_mode": None,
        "backend": backend,
        "model_file": None,
        "model_quant": None,
        "model_sha256": None,
        "n_ctx": None,
        "prompt_tokens": None,
        "completion_tokens": None,
        "cached_prompt_tokens": None,
        "prefix_cache_hit": None,
        "prefill_tps": None,
        "generation_tps": None,
        "prefill_ms": None,
        "generation_ms": None,
        "prompt_per_token_ms": None,
        "predicted_per_token_ms": None,
        "ttft_ms": None,
        "wall_ms": wall_ms,
        "queue_wait_ms": None,
        "finish_reason": None,
        "interactive": False,
        "server_request_id": None,
        "server_fingerprint": None,
        "stream": stream,
        "max_tokens_requested": max_tokens_requested,
        "prompt_sha256": None,
        "prompt_chars": prompt_chars,
        "message_count": message_count,
        "error_class": error_class,
    }
    _emit(
        category="inference",
        event_type="completion_failed",
        emitter=emitter,
        pid=pid,
        run_id=run_id,
        body=body,
        correlation_id=correlation_id,
        nulls=nulls,
    )


# ── B. Gate ──────────────────────────────────────────────────────────────

def record_gate_decision(
    *,
    event_type: str,
    emitter: str,
    pid: int,
    decision: Any,
    call_site: str,
    reason: str,
    snapshot: Any = None,
    meminfo: Optional[Dict[str, Any]] = None,
    repeat_count: int = 1,
    dedup_window_ms: Optional[float] = None,
    retry_count: Optional[int] = None,
    wait_ms: Optional[float] = None,
    correlation_id: Optional[str] = None,
    run_id: Optional[str] = None,
    nulls: Optional[Dict[str, str]] = None,
) -> None:
    """`decision` and `snapshot` are dataclasses.asdict()'d verbatim
    (§2.B: "no reshaping") — accepts either a dataclass instance
    (GateDecision/DispatchDecision/ContextBudgetDecision/TripDecision) or
    a plain dict, never imports the dataclass types themselves."""
    decision_dict = _as_dict(decision)
    body = {
        "decision": decision_dict,
        "snapshot": _as_dict(snapshot) or None,
        "meminfo": meminfo,
        "reason": reason,
        "admitted_via_swap": decision_dict.get("admitted_via_swap"),
        "dispatched_via_swap": decision_dict.get("dispatched_via_swap"),
        "swap_bytes_claimed": decision_dict.get("swap_bytes_claimed"),
        "budget_ceiling_exceeded": decision_dict.get("budget_ceiling_exceeded"),
        "call_site": call_site,
        "retry_count": retry_count,
        "wait_ms": wait_ms,
        "repeat_count": repeat_count,
        "dedup_window_ms": dedup_window_ms,
    }
    _emit(
        category="gate",
        event_type=event_type,
        emitter=emitter,
        pid=pid,
        run_id=run_id,
        body=body,
        correlation_id=correlation_id,
        nulls=nulls,
    )


# ── C. Device ────────────────────────────────────────────────────────────

def record_device_sample(
    *,
    emitter: str,
    pid: int,
    snapshot: Any,
    mem_free_bytes: Optional[int] = None,
    mem_available_bytes: Optional[int] = None,
    zram_compression_ratio: Optional[float] = None,
    zram_orig_data_bytes: Optional[int] = None,
    zram_compr_data_bytes: Optional[int] = None,
    inference_active: bool = False,
    inference_seconds_this_run: float = 0.0,
    throttle_level: Optional[str] = None,
    run_id: Optional[str] = None,
    nulls: Optional[Dict[str, str]] = None,
) -> None:
    snap = _as_dict(snapshot)
    swap_total = snap.get("swap_total_bytes", 0) or 0
    swap_free = snap.get("swap_free_bytes", 0) or 0
    body = {
        "ram_total_bytes": snap.get("ram_total_bytes", 0),
        "ram_headroom_bytes": snap.get("ram_headroom_bytes", 0),
        "mem_free_bytes": mem_free_bytes,
        "mem_available_bytes": mem_available_bytes,
        "swap_total_bytes": swap_total,
        "swap_free_bytes": swap_free,
        "swap_used_bytes": swap_total - swap_free,
        "zram_compression_ratio": zram_compression_ratio,
        "zram_orig_data_bytes": zram_orig_data_bytes,
        "zram_compr_data_bytes": zram_compr_data_bytes,
        "temperature_c": snap.get("temperature_c"),
        "cpu_percent": snap.get("cpu_percent"),
        "battery_percent": snap.get("battery_percent"),
        "battery_charging": snap.get("battery_charging", False),
        "queue_pending": snap.get("queue_pending", 0),
        "queue_running": snap.get("queue_running", 0),
        "inference_active": inference_active,
        "inference_seconds_this_run": inference_seconds_this_run,
        "throttle_level": throttle_level,
        "device_uptime_sec": None,  # always null — fact 0.2
    }
    merged_nulls = dict(nulls) if nulls else {}
    merged_nulls.setdefault("body.device_uptime_sec", "proc_uptime_permission_denied")
    _emit(
        category="device",
        event_type="sample",
        emitter=emitter,
        pid=pid,
        run_id=run_id,
        body=body,
        nulls=merged_nulls,
        # device_uptime_sec is a permanent, device-wide null (fact 0.2),
        # not a per-call observation failure — always recorded as null +
        # reason rather than pruned, so the restriction stays visible in
        # every device-category record (design §2.C's explicit intent).
        always_keep_null={"device_uptime_sec"},
    )


# ── D. Co-tenancy ────────────────────────────────────────────────────────

def record_cotenancy_transition(
    *,
    emitter: str,
    pid: int,
    active: bool,
    previous_active: bool,
    live_session_pids: List[int],
    state_duration_ms: float,
    correlation_id: Optional[str] = None,
    run_id: Optional[str] = None,
    nulls: Optional[Dict[str, str]] = None,
) -> None:
    body = {
        "detector": "tui",
        "detector_available": ["tui"],
        "active": active,
        "previous_active": previous_active,
        "live_session_pids": live_session_pids,
        "session_count": len(live_session_pids),
        "state_duration_ms": state_duration_ms,
        "refused_task_id": None,
        "refusal_reason": None,
        "deferral_ms": None,
        "deferral_refusal_count": None,
        "task_state_preserved": None,
    }
    _emit(
        category="cotenancy",
        event_type="interactive_transition",
        emitter=emitter,
        pid=pid,
        run_id=run_id,
        body=body,
        correlation_id=correlation_id,
        nulls=nulls,
    )


def record_dispatch_refused_human_present(
    *,
    emitter: str,
    pid: int,
    refused_task_id: int,
    refusal_reason: str,
    correlation_id: Optional[str] = None,
    run_id: Optional[str] = None,
    nulls: Optional[Dict[str, str]] = None,
) -> None:
    body = {
        "detector": "tui",
        "detector_available": ["tui"],
        "active": True,
        "previous_active": True,
        "live_session_pids": [],
        "session_count": 0,
        "state_duration_ms": 0.0,
        "refused_task_id": refused_task_id,
        "refusal_reason": refusal_reason,
        "deferral_ms": None,
        "deferral_refusal_count": None,
        "task_state_preserved": None,
    }
    _emit(
        category="cotenancy",
        event_type="dispatch_refused_human_present",
        emitter=emitter,
        pid=pid,
        run_id=run_id,
        body=body,
        correlation_id=correlation_id,
        nulls=nulls,
    )


def record_deferral_resolved(
    *,
    emitter: str,
    pid: int,
    deferral_ms: float,
    deferral_refusal_count: int,
    correlation_id: Optional[str] = None,
    run_id: Optional[str] = None,
    nulls: Optional[Dict[str, str]] = None,
) -> None:
    body = {
        "detector": "tui",
        "detector_available": ["tui"],
        "active": False,
        "previous_active": True,
        "live_session_pids": [],
        "session_count": 0,
        "state_duration_ms": 0.0,
        "refused_task_id": None,
        "refusal_reason": None,
        "deferral_ms": deferral_ms,
        "deferral_refusal_count": deferral_refusal_count,
        # Structurally always true today — there is no preemption path
        # (fact 0.11); recorded rather than assumed so a future real
        # preemption path would show False instead of the field simply
        # not existing.
        "task_state_preserved": True,
    }
    _emit(
        category="cotenancy",
        event_type="deferral_resolved",
        emitter=emitter,
        pid=pid,
        run_id=run_id,
        body=body,
        correlation_id=correlation_id,
        nulls=nulls,
    )


# ── E. Task outcomes ─────────────────────────────────────────────────────

def record_task_started(
    *,
    emitter: str,
    pid: int,
    task_id: int,
    task_type: str,
    needs_planning: bool,
    started_ts_wall: float,
    correlation_id: Optional[str] = None,
    run_id: Optional[str] = None,
    nulls: Optional[Dict[str, str]] = None,
) -> None:
    body = {
        "task_id": task_id,
        "task_type": task_type,
        "needs_planning": needs_planning,
        "started_ts_wall": started_ts_wall,
        "finished_ts_wall": None,
        "duration_ms": None,
        "terminal_status": None,
        "step_count": None,
        "max_steps": None,
        "hit_max_steps": None,
        "tools_called": None,
        "tool_call_total": None,
        "retries": None,
        "escalated": None,
        "escalation_reason": None,
        "escalation_outcome": None,
        "inference_ms_total": None,
        "inference_call_count": None,
        "error_class": None,
        "timeout_sec": None,
    }
    _emit(
        category="task",
        event_type="task_started",
        emitter=emitter,
        pid=pid,
        run_id=run_id,
        body=body,
        correlation_id=correlation_id,
        nulls=nulls,
    )


def record_task_finished(
    *,
    emitter: str,
    pid: int,
    task_id: int,
    task_type: str,
    needs_planning: bool,
    finished_ts_wall: float,
    duration_ms: float,
    terminal_status: str,
    step_count: Optional[int] = None,
    max_steps: Optional[int] = None,
    hit_max_steps: Optional[bool] = None,
    tools_called: Optional[Dict[str, int]] = None,
    retries: Optional[int] = None,
    escalated: Optional[bool] = None,
    escalation_reason: Optional[str] = None,
    escalation_outcome: Optional[str] = None,
    error_class: Optional[str] = None,
    timeout_sec: Optional[int] = None,
    correlation_id: Optional[str] = None,
    run_id: Optional[str] = None,
    nulls: Optional[Dict[str, str]] = None,
) -> None:
    body = {
        "task_id": task_id,
        "task_type": task_type,
        "needs_planning": needs_planning,
        "started_ts_wall": None,
        "finished_ts_wall": finished_ts_wall,
        "duration_ms": duration_ms,
        "terminal_status": terminal_status,
        "step_count": step_count,
        "max_steps": max_steps,
        "hit_max_steps": hit_max_steps,
        "tools_called": tools_called,
        "tool_call_total": sum(tools_called.values()) if tools_called else None,
        "retries": retries,
        "escalated": escalated,
        "escalation_reason": escalation_reason,
        "escalation_outcome": escalation_outcome,
        # Computed at rollup time from category-A records sharing this
        # correlation_id (§2.E) — never tracked separately here.
        "inference_ms_total": None,
        "inference_call_count": None,
        "error_class": error_class,
        "timeout_sec": timeout_sec,
    }
    _emit(
        category="task",
        event_type="task_finished",
        emitter=emitter,
        pid=pid,
        run_id=run_id,
        body=body,
        correlation_id=correlation_id,
        nulls=nulls,
    )


# ── F. Extraction (Aigentik-side data reaching Codey-OS, if ever) ─────────
# Aigentik's own emission path is telemetry.mjs (T1), not this module. A
# Python-side recorder is included for parity/tests only — nothing calls
# it from T0.

def record_extraction_attempt(
    *,
    emitter: str,
    pid: int,
    extractor: str,
    requested_fields: List[str],
    returned_fields: List[str],
    null_fields: List[str],
    dropped_schema_echo_fields: List[str],
    parse_ok: bool,
    source_chars: int,
    model_backend: str,
    parse_error_class: Optional[str] = None,
    correlation_id: Optional[str] = None,
    run_id: Optional[str] = None,
    nulls: Optional[Dict[str, str]] = None,
) -> None:
    body = {
        "extractor": extractor,
        "requested_fields": requested_fields,
        "returned_fields": returned_fields,
        "null_fields": null_fields,
        "dropped_schema_echo_fields": dropped_schema_echo_fields,
        "parse_ok": parse_ok,
        "parse_error_class": parse_error_class,
        "source_chars": source_chars,
        "model_backend": model_backend,
    }
    _emit(
        category="extraction",
        event_type="extraction_attempt",
        emitter=emitter,
        pid=pid,
        run_id=run_id,
        body=body,
        correlation_id=correlation_id,
        nulls=nulls,
    )


def record_grounding_check(
    *,
    emitter: str,
    pid: int,
    field: str,
    outcome: str,
    numeric_tokens_in_value: int,
    numeric_tokens_matched: int,
    value_chars: int,
    source_chars: int,
    action_taken: str,
    value_sha256: Optional[str] = None,
    correlation_id: Optional[str] = None,
    run_id: Optional[str] = None,
    nulls: Optional[Dict[str, str]] = None,
) -> None:
    body = {
        "field": field,
        "outcome": outcome,
        "numeric_tokens_in_value": numeric_tokens_in_value,
        "numeric_tokens_matched": numeric_tokens_matched,
        "value_sha256": value_sha256,
        "value_chars": value_chars,
        "source_chars": source_chars,
        "action_taken": action_taken,
    }
    _emit(
        category="extraction",
        event_type="grounding_check",
        emitter=emitter,
        pid=pid,
        run_id=run_id,
        body=body,
        correlation_id=correlation_id,
        nulls=nulls,
    )


def record_deterministic_bypass(
    *,
    emitter: str,
    pid: int,
    rule_id: str,
    rule_source: str,
    would_have_called_model: bool,
    correlation_id: Optional[str] = None,
    run_id: Optional[str] = None,
    nulls: Optional[Dict[str, str]] = None,
) -> None:
    # estimated_tokens_avoided / estimated_ms_avoided are deliberately
    # NOT fields here — §2.F: they are derived-only, computed by the
    # rollup pass from a trailing-7-day median, and have no place in an
    # immutable raw observation.
    body = {
        "rule_id": rule_id,
        "rule_source": rule_source,
        "would_have_called_model": would_have_called_model,
    }
    _emit(
        category="extraction",
        event_type="deterministic_bypass",
        emitter=emitter,
        pid=pid,
        run_id=run_id,
        body=body,
        correlation_id=correlation_id,
        nulls=nulls,
    )


# ── G. Provenance ────────────────────────────────────────────────────────

def record_run_start(
    *,
    emitter: str,
    pid: int,
    repo: str,
    started_ts_wall: float,
    repo_dir: Optional[Path] = None,
    models: Optional[List[Dict[str, Any]]] = None,
    llama_server_bin: Optional[str] = None,
    run_id: Optional[str] = None,
) -> None:
    """
    Builds and emits the `run_start` record via
    telemetry.provenance.build_run_start_body(). T2 wires this in at the
    non-lifecycle process entry points (Core API, TUI, Aigentik's JS
    equivalent).

    In addition to the normal JSONL emission (via _emit -> store.record),
    this:
      1. Writes runs/<run_id>.json once (design §3.1) via
         store.write_run_provenance() — the record is never reopened for
         write after this.
      2. Schedules a background hash of any `models` entry whose digest
         is cold (sha256_source == "not_computed") — never synchronously
         (fact 0.23: ~5.2s for the primary model) — via
         provenance.schedule_cold_model_digests(). A completed hash is
         reported later as a separate, append-only `run_start_amended`
         record, not by editing runs/<run_id>.json.

    `models` should already be built via
    telemetry.provenance.build_model_entries() (or an equivalent
    cache-read-only shape) — this function does not hash anything itself.

    Kill switch: checked FIRST, before any of the git/getprop/meminfo
    collection work below or the background digest scheduling — design
    §5.3's "checked once ... a single predictable branch with no object
    construction" and §5.4's OFF-arm-must-be-zero measurement procedure
    both require this. Without this early return, a disabled run would
    still spawn subprocesses for git/getprop and still spawn a background
    thread that hashes the full model file, which is exactly the
    synchronous-adjacent cost the kill switch exists to eliminate.
    """
    if not store.TELEMETRY_ENABLED:
        return

    from telemetry import provenance as _provenance  # local: avoids a hard
    # module-load-order dependency between recorders.py and provenance.py
    # for callers that only need the other half of this module.

    resolved_run_id = run_id if run_id is not None else store.get_run_id()
    boot_id = envelope.get_boot_id()
    body = _provenance.build_run_start_body(
        run_id=resolved_run_id,
        boot_id=boot_id,
        emitter=emitter,
        pid=pid,
        started_ts_wall=started_ts_wall,
        repo=repo,
        repo_dir=repo_dir,
        models=models,
        llama_server_bin=llama_server_bin,
        schema_version=SCHEMA_VERSION,
        schema_sha256=SCHEMA_SHA256_12,
    )
    nulls = _provenance.build_run_start_nulls(body)
    record = _emit(
        category="provenance",
        event_type="run_start",
        emitter=emitter,
        pid=pid,
        run_id=resolved_run_id,
        body=body,
        nulls=nulls,
        # device_uptime_sec is a permanent, device-wide null (fact 0.2),
        # not a per-call observation failure — always recorded as null +
        # reason rather than pruned, mirroring record_device_sample.
        always_keep_null={"device_uptime_sec"},
    )
    store.write_run_provenance(record)
    _provenance.schedule_cold_model_digests(
        models=body.get("models") or [],
        run_id=resolved_run_id,
        emitter=emitter,
        pid=pid,
    )


def record_run_start_amended(
    *,
    emitter: str,
    pid: int,
    run_id: str,
    models: List[Dict[str, Any]],
    correlation_id: Optional[str] = None,
) -> None:
    """
    Design §3.4: a background-thread model-digest computation that
    completes after the original `run_start` record was already written
    amends the record stream with this follow-up event — never by
    reopening runs/<run_id>.json (append-only). Emitted only into the
    normal JSONL stream via _emit/store.record; NOT written to
    runs/<run_id>.json itself. A later `codey-metrics provenance` (T4,
    out of this sub-task's scope) is expected to merge a run's
    `run_start` + any `run_start_amended` records sharing a run_id when
    displaying it.
    """
    _emit(
        category="provenance",
        event_type="run_start_amended",
        emitter=emitter,
        pid=pid,
        run_id=run_id,
        body={"models": models},
        correlation_id=correlation_id,
    )


# ── meta ─────────────────────────────────────────────────────────────────

def record_meta_event(
    *,
    event_type: str,
    emitter: str,
    pid: int,
    run_id: Optional[str] = None,
    **body_fields: Any,
) -> None:
    _emit(
        category="meta",
        event_type=event_type,
        emitter=emitter,
        pid=pid,
        run_id=run_id,
        body=dict(body_fields),
    )
