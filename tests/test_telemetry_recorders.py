"""
Round-trips real GateDecision/DispatchDecision/ContextBudgetDecision/
ResourceSnapshot fixtures into valid schema records. `telemetry/store.py`
is monkeypatched to a capture list so these tests exercise
telemetry/recorders.py + telemetry/envelope.py end-to-end without
touching a real writer thread or the filesystem.

Note: this test file imports core.resource_gate to build realistic
fixtures — that is fine (core.resource_gate is not `ccos.*`); the module
under test, telemetry/recorders.py, does NOT import core.resource_gate
itself (see its module docstring) — that's what
tests/test_telemetry_no_ccos_imports.py and the dataclasses.asdict()-only
contract in recorders.py enforce.
"""

from __future__ import annotations

import dataclasses

import pytest

from core.resource_gate import DispatchDecision, GateDecision, ResourceSnapshot
from telemetry import envelope, recorders, schema


@pytest.fixture(autouse=True)
def _capture_store(monkeypatch):
    captured = []

    def fake_record(rec):
        captured.append(rec)

    monkeypatch.setattr(recorders.store, "record", fake_record)
    monkeypatch.setattr(recorders.store, "get_run_id", lambda: "recordertest0001")
    # T2: record_run_start() also calls store.write_run_provenance() (the
    # runs/<run_id>.json write) unconditionally. Left unpatched, that call
    # bypasses this fixture's fake_record() entirely and writes a real
    # file under the real METRICS_DIR — silently breaking this file's
    # stated "without touching a real writer thread or the filesystem"
    # contract. No-op it the same way fake_record() no-ops the JSONL path.
    monkeypatch.setattr(recorders.store, "write_run_provenance", lambda rec, root=None: None)
    # tests/conftest.py's session-wide autouse fixture defaults
    # TELEMETRY_ENABLED to False (so tests that hit real run_start call
    # sites don't spawn background model-digest hashing). This file's
    # record_run_start() tests need it True since record_run_start()
    # checks the flag first, before anything else.
    monkeypatch.setattr(recorders.store, "TELEMETRY_ENABLED", True)
    envelope.reset_seq()
    return captured


def test_record_gate_decision_round_trips_gate_decision(_capture_store):
    decision = GateDecision(
        admitted=True,
        hard_reject=False,
        reason="ok: sufficient headroom",
        estimated_cost_bytes=2_000_000_000,
        headroom_bytes=3_000_000_000,
        device_ceiling_bytes=8_000_000_000,
        admitted_via_swap=True,
        swap_bytes_claimed=500_000_000,
    )
    recorders.record_gate_decision(
        event_type="can_admit",
        emitter="codey-os.loader",
        pid=111,
        decision=decision,
        call_site="loader_v2.LlamaServer.start",
        reason=decision.reason,
        correlation_id="c" * 32,
    )
    assert len(_capture_store) == 1
    record = _capture_store[0]
    assert record["category"] == "gate"
    assert record["event_type"] == "can_admit"
    assert record["body"]["decision"] == dataclasses.asdict(decision)
    assert record["body"]["admitted_via_swap"] is True
    assert record["body"]["swap_bytes_claimed"] == 500_000_000
    assert schema.validate(record) == []


def test_record_gate_decision_round_trips_dispatch_decision(_capture_store):
    decision = DispatchDecision(allowed=False, reason="human present", dispatched_via_swap=False)
    recorders.record_gate_decision(
        event_type="can_dispatch_task",
        emitter="codey-os.daemon",
        pid=222,
        decision=decision,
        call_site="daemon._check_dispatch_gate",
        reason=decision.reason,
        correlation_id="d" * 32,
    )
    record = _capture_store[0]
    assert record["body"]["decision"] == dataclasses.asdict(decision)
    assert schema.validate(record) == []


def test_record_gate_decision_accepts_plain_dict_decision(_capture_store):
    decision = {"allowed": True, "reason": "queue empty"}
    recorders.record_gate_decision(
        event_type="can_dispatch_task",
        emitter="codey-os.daemon",
        pid=333,
        decision=decision,
        call_site="daemon._check_dispatch_gate",
        reason="queue empty",
        correlation_id="e" * 32,
    )
    record = _capture_store[0]
    assert record["body"]["decision"] == decision


def test_record_device_sample_round_trips_resource_snapshot(_capture_store):
    snapshot = ResourceSnapshot(
        cpu_percent=None,
        ram_headroom_bytes=1_000_000_000,
        ram_total_bytes=10_000_000_000,
        temperature_c=45.5,
        queue_pending=1,
        queue_running=0,
        battery_percent=80,
        battery_charging=True,
        timestamp=1234.5,
        swap_total_bytes=16_000_000_000,
        swap_free_bytes=8_000_000_000,
    )
    recorders.record_device_sample(
        emitter="codey-os.daemon",
        pid=444,
        snapshot=snapshot,
        nulls={"body.cpu_percent": "proc_stat_permission_denied"},
    )
    record = _capture_store[0]
    assert record["category"] == "device"
    assert record["body"]["ram_total_bytes"] == 10_000_000_000
    assert record["body"]["swap_used_bytes"] == 8_000_000_000
    assert record["body"]["device_uptime_sec"] is None
    assert record["nulls"]["body.device_uptime_sec"] == "proc_uptime_permission_denied"
    assert record["nulls"]["body.cpu_percent"] == "proc_stat_permission_denied"
    assert schema.validate(record) == []


def test_record_inference_completion_produces_valid_record(_capture_store):
    recorders.record_inference_completion(
        emitter="codey-os.daemon",
        pid=555,
        backend="local",
        wall_ms=812.3,
        stream=False,
        max_tokens_requested=512,
        prompt_chars=240,
        message_count=3,
        prompt_tokens=120,
        completion_tokens=64,
        cached_prompt_tokens=40,
        prefill_tps=310.5,
        generation_tps=48.2,
        finish_reason="stop",
        correlation_id="f" * 32,
    )
    record = _capture_store[0]
    assert record["category"] == "inference"
    assert record["body"]["prefix_cache_hit"] is True
    assert schema.validate(record) == []


def test_record_inference_completion_null_cache_tokens_gives_null_prefix_hit(_capture_store):
    recorders.record_inference_completion(
        emitter="codey-os.daemon",
        pid=556,
        backend="local",
        wall_ms=10.0,
        stream=False,
        max_tokens_requested=10,
        prompt_chars=1,
        message_count=1,
        cached_prompt_tokens=None,
        correlation_id="g" * 32,
        nulls={
            "body.role": "call_site_not_yet_tagged",
            "body.model_file": "remote_backend_no_local_metrics",
            "body.model_quant": "remote_backend_no_local_metrics",
            "body.model_sha256": "model_sha256_not_computed",
            "body.n_ctx": "remote_backend_no_local_metrics",
            "body.prompt_tokens": "server_timings_absent",
            "body.completion_tokens": "server_timings_absent",
            "body.cached_prompt_tokens": "server_timings_absent",
            "body.prefix_cache_hit": "server_timings_absent",
            "body.prefill_tps": "server_timings_absent",
            "body.generation_tps": "server_timings_absent",
            "body.prefill_ms": "server_timings_absent",
            "body.generation_ms": "server_timings_absent",
            "body.prompt_per_token_ms": "server_timings_absent",
            "body.predicted_per_token_ms": "server_timings_absent",
            "body.ttft_ms": "server_timings_absent",
            "body.queue_wait_ms": "call_site_not_yet_tagged",
            "body.finish_reason": "server_timings_absent",
            "body.server_request_id": "server_timings_absent",
            "body.server_fingerprint": "server_timings_absent",
            "body.prompt_sha256": "value_redacted_by_policy",
            "body.thinking_mode": "call_site_not_yet_tagged",
        },
    )
    record = _capture_store[0]
    assert record["body"]["prefix_cache_hit"] is None
    assert schema.validate(record) == []


def test_record_task_started_and_finished_produce_valid_records(_capture_store):
    recorders.record_task_started(
        emitter="codey-os.daemon",
        pid=777,
        task_id=1,
        task_type="direct",
        needs_planning=False,
        started_ts_wall=1000.0,
        correlation_id="h" * 32,
    )
    recorders.record_task_finished(
        emitter="codey-os.daemon",
        pid=777,
        task_id=1,
        task_type="direct",
        needs_planning=False,
        finished_ts_wall=1005.0,
        duration_ms=5000.0,
        terminal_status="done",
        step_count=3,
        tools_called={"write_file": 2, "shell": 1},
        correlation_id="h" * 32,
    )
    started, finished = _capture_store
    assert started["event_type"] == "task_started"
    assert finished["event_type"] == "task_finished"
    assert finished["body"]["tool_call_total"] == 3
    assert schema.validate(started) == []
    assert schema.validate(finished) == []


def test_record_extraction_and_grounding_produce_valid_records(_capture_store):
    recorders.record_extraction_attempt(
        emitter="aigentik",
        pid=888,
        extractor="contact_details",
        requested_fields=["name", "phone"],
        returned_fields=["name"],
        null_fields=["phone"],
        dropped_schema_echo_fields=[],
        parse_ok=True,
        source_chars=500,
        model_backend="local",
        correlation_id="i" * 32,
    )
    recorders.record_grounding_check(
        emitter="aigentik",
        pid=888,
        field="address",
        outcome="passed_numeric_match",
        numeric_tokens_in_value=1,
        numeric_tokens_matched=1,
        value_chars=20,
        source_chars=500,
        action_taken="kept",
        value_sha256="a" * 64,
        correlation_id="i" * 32,
    )
    attempt, check = _capture_store
    assert schema.validate(attempt) == []
    assert schema.validate(check) == []


def test_record_deterministic_bypass_has_no_derived_fields(_capture_store):
    recorders.record_deterministic_bypass(
        emitter="aigentik",
        pid=999,
        rule_id="do-not-contact",
        rule_source="email-rules",
        would_have_called_model=True,
        correlation_id="j" * 32,
    )
    record = _capture_store[0]
    assert "estimated_tokens_avoided" not in record["body"]
    assert "estimated_ms_avoided" not in record["body"]
    assert schema.validate(record) == []


def test_record_cotenancy_transition_and_deferral(_capture_store):
    recorders.record_cotenancy_transition(
        emitter="codey-os.daemon",
        pid=1010,
        active=True,
        previous_active=False,
        live_session_pids=[1234],
        state_duration_ms=60000.0,
        correlation_id="k" * 32,
    )
    recorders.record_deferral_resolved(
        emitter="codey-os.daemon",
        pid=1010,
        deferral_ms=15000.0,
        deferral_refusal_count=30,
        correlation_id="k" * 32,
    )
    transition, deferral = _capture_store
    assert transition["body"]["detector"] == "tui"
    assert deferral["body"]["task_state_preserved"] is True
    assert schema.validate(transition) == []
    assert schema.validate(deferral) == []


def test_as_dict_never_raises_on_unexpected_type():
    assert recorders._as_dict(None) == {}
    assert recorders._as_dict(42) == {}
    assert recorders._as_dict("not a dataclass") == {}
    assert recorders._as_dict({"a": 1}) == {"a": 1}


def test_record_run_start_produces_valid_record_happy_path(_capture_store, monkeypatch):
    from telemetry import provenance

    monkeypatch.setattr(
        provenance,
        "get_git_provenance",
        lambda repo_dir=None: {
            "commit_sha": "a" * 40,
            "dirty": False,
            "dirty_file_count": 0,
            "branch": "main",
        },
    )
    monkeypatch.setattr(
        provenance,
        "get_ram_swap_bytes",
        lambda: {"ram_total_bytes": 10_000_000_000, "swap_total_bytes": 16_000_000_000},
    )

    recorders.record_run_start(
        emitter="codey-os.daemon",
        pid=555,
        repo="codey-os",
        started_ts_wall=1234.5,
    )
    assert len(_capture_store) == 1
    record = _capture_store[0]
    assert record["category"] == "provenance"
    assert record["event_type"] == "run_start"
    assert record["run_id"] == "recordertest0001"
    assert record["body"]["schema_version"] == schema.SCHEMA_VERSION
    assert record["body"]["git_commit_sha"] == "a" * 40
    assert record["body"]["git_dirty"] is False
    assert record["body"]["git_branch"] == "main"
    # device_uptime_sec is a permanent honest null (fact 0.2), even on a
    # fully successful run.
    assert record["body"]["device_uptime_sec"] is None
    assert record["nulls"]["body.device_uptime_sec"] == "proc_uptime_permission_denied"
    assert "body.git_commit_sha" not in record["nulls"]
    assert schema.validate(record) == []


def test_record_run_start_git_failure_produces_named_nulls(_capture_store, monkeypatch):
    from telemetry import provenance

    monkeypatch.setattr(
        provenance,
        "get_git_provenance",
        lambda repo_dir=None: {
            "commit_sha": None,
            "dirty": None,
            "dirty_file_count": None,
            "branch": None,
        },
    )
    monkeypatch.setattr(
        provenance,
        "get_ram_swap_bytes",
        lambda: {"ram_total_bytes": 10_000_000_000, "swap_total_bytes": 16_000_000_000},
    )

    recorders.record_run_start(
        emitter="codey-os.daemon",
        pid=666,
        repo="codey-os",
        started_ts_wall=1234.5,
    )
    record = _capture_store[0]
    # The git-failure fields must still appear in the body (as named
    # nulls), not be silently pruned by _emit()'s no-nulls-entry path.
    assert record["body"]["git_commit_sha"] is None
    assert record["body"]["git_dirty"] is None
    assert record["body"]["git_dirty_file_count"] is None
    assert record["body"]["git_branch"] is None
    for field in ("git_commit_sha", "git_dirty", "git_dirty_file_count", "git_branch"):
        assert record["nulls"][f"body.{field}"] == "git_command_unavailable"
    # device_uptime_sec is unconditionally a named null, git failure or not.
    assert record["nulls"]["body.device_uptime_sec"] == "proc_uptime_permission_denied"
    assert schema.validate(record) == []


def test_record_run_start_meminfo_failure_produces_state_store_unreadable_nulls(
    _capture_store, monkeypatch
):
    from telemetry import provenance

    monkeypatch.setattr(
        provenance,
        "get_git_provenance",
        lambda repo_dir=None: {
            "commit_sha": "a" * 40,
            "dirty": False,
            "dirty_file_count": 0,
            "branch": "main",
        },
    )
    monkeypatch.setattr(
        provenance,
        "get_ram_swap_bytes",
        lambda: {"ram_total_bytes": None, "swap_total_bytes": None},
    )

    recorders.record_run_start(
        emitter="codey-os.daemon",
        pid=777,
        repo="codey-os",
        started_ts_wall=1234.5,
    )
    record = _capture_store[0]
    assert record["body"]["ram_total_bytes"] is None
    assert record["body"]["swap_total_bytes"] is None
    for field in ("ram_total_bytes", "swap_total_bytes"):
        assert record["nulls"][f"body.{field}"] == "state_store_unreadable"
    assert schema.validate(record) == []
