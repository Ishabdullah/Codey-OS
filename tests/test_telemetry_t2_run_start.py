"""
Sub-task T2 — category-G `run_start` wiring: runs/<run_id>.json, the
model-digest background-hash scheduler, and the env/config allow-list
enforced end-to-end through record_run_start() itself (not just
provenance.build_env_overrides() in isolation, which
tests/test_telemetry_provenance.py already covers from T0).
See docs/telemetry_layer_design.md §2.G, §3.1, §3.4, §8 item 4.
"""

from __future__ import annotations

import hashlib
import json
import time

import pytest

from telemetry import envelope, provenance, recorders, schema, store


SECRET_NAMES = ["OPENROUTER_API_KEY", "UNLIMITEDCLAUDE_API_KEY", "CLOUDFLARE_TUNNEL_TOKEN"]


@pytest.fixture(autouse=True)
def _reset_telemetry_state(monkeypatch, tmp_path):
    envelope.reset_seq()
    store.reset_for_tests()
    monkeypatch.setattr(store, "TELEMETRY_ENABLED", True)
    monkeypatch.setattr(store, "METRICS_DIR", tmp_path)
    yield
    store.reset_for_tests()


def _wait_for(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return predicate()


# ── runs/<run_id>.json (design §3.1) ────────────────────────────────────


def test_record_run_start_writes_runs_json_once(tmp_path):
    recorders.record_run_start(
        emitter="codey-os.core-api",
        pid=999,
        repo="Codey-OS",
        started_ts_wall=time.time(),
        run_id="fixedrunid000001",
    )
    run_file = tmp_path / "runs" / "fixedrunid000001.json"
    assert _wait_for(run_file.exists)
    record = json.loads(run_file.read_text(encoding="utf-8"))
    assert record["run_id"] == "fixedrunid000001"
    assert record["category"] == "provenance"
    assert record["event_type"] == "run_start"
    assert record["body"]["repo"] == "Codey-OS"


def test_write_run_provenance_never_overwrites_existing_file(tmp_path):
    first = {"run_id": "samerunid0000001", "body": {"marker": "first"}}
    second = {"run_id": "samerunid0000001", "body": {"marker": "second"}}
    store.write_run_provenance(first, root=tmp_path)
    store.write_run_provenance(second, root=tmp_path)

    run_file = tmp_path / "runs" / "samerunid0000001.json"
    on_disk = json.loads(run_file.read_text(encoding="utf-8"))
    assert on_disk["body"]["marker"] == "first"


def test_write_run_provenance_noop_when_telemetry_disabled(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "TELEMETRY_ENABLED", False)
    store.write_run_provenance({"run_id": "disabledrun00001", "body": {}}, root=tmp_path)
    assert not (tmp_path / "runs").exists()


def test_write_run_provenance_never_raises_on_write_failure(tmp_path, monkeypatch):
    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("builtins.open", boom)
    # Must not raise.
    store.write_run_provenance({"run_id": "boomrun00000001", "body": {}}, root=tmp_path)


# ── honest-null closure for a real run_start body (constraint 2) ────────


def test_run_start_record_passes_schema_validate(tmp_path):
    recorders.record_run_start(
        emitter="codey-os.tui",
        pid=1,
        repo="Codey-OS",
        started_ts_wall=time.time(),
        run_id="validaterun00001",
    )
    run_file = tmp_path / "runs" / "validaterun00001.json"
    assert _wait_for(run_file.exists)
    record = json.loads(run_file.read_text(encoding="utf-8"))
    violations = schema.validate(record)
    assert violations == [], violations


def test_build_run_start_nulls_covers_llama_fields_left_null_at_process_start():
    """T0's build_run_start_body() left llama_build_info/llama_server_argv
    as unreasoned None — the first real call site (T2) must close that gap
    rather than reintroduce it."""
    body = {
        "git_commit_sha": "a" * 40,
        "git_dirty": False,
        "git_dirty_file_count": 0,
        "git_branch": "main",
        "ram_total_bytes": 123,
        "swap_total_bytes": 456,
        "device_uptime_sec": None,
        "llama_build_info": None,
        "llama_server_argv": None,
    }
    nulls = provenance.build_run_start_nulls(body)
    assert nulls["body.llama_build_info"] == "call_site_not_yet_tagged"
    assert nulls["body.llama_server_argv"] == "call_site_not_yet_tagged"


# ── env/config allow-list, end-to-end through record_run_start ──────────


def test_record_run_start_env_overrides_never_leak_out_of_allow_list(tmp_path, monkeypatch):
    monkeypatch.setenv("SOME_RANDOM_UNRELATED_VAR", "should-not-appear")
    for name in SECRET_NAMES:
        monkeypatch.setenv(name, "super-secret-value-do-not-leak")

    recorders.record_run_start(
        emitter="codey-os.core-api",
        pid=2,
        repo="Codey-OS",
        started_ts_wall=time.time(),
        run_id="envallowlist0001",
    )
    run_file = tmp_path / "runs" / "envallowlist0001.json"
    assert _wait_for(run_file.exists)
    record = json.loads(run_file.read_text(encoding="utf-8"))
    overrides = record["body"]["env_overrides"]

    serialized = json.dumps(overrides)
    assert "super-secret-value-do-not-leak" not in serialized
    assert "SOME_RANDOM_UNRELATED_VAR" not in overrides
    for name in SECRET_NAMES:
        assert name not in overrides
        assert overrides[f"{name.lower()}_set"] is True


def test_record_run_start_config_snapshot_is_a_projection(tmp_path):
    recorders.record_run_start(
        emitter="codey-os.core-api",
        pid=3,
        repo="Codey-OS",
        started_ts_wall=time.time(),
        run_id="configsnap00001",
    )
    run_file = tmp_path / "runs" / "configsnap00001.json"
    assert _wait_for(run_file.exists)
    record = json.loads(run_file.read_text(encoding="utf-8"))
    snapshot = record["body"]["config_snapshot"]
    assert snapshot["_policy"] == "v1"
    for key in snapshot:
        assert "key" not in key.lower() and "token" not in key.lower() and "secret" not in key.lower()


# ── model-digest cache: background hashing, never inline ────────────────


def test_build_model_entries_never_hashes_synchronously(tmp_path, monkeypatch):
    calls = []
    real_sha256 = hashlib.sha256

    def spy_sha256(*args, **kwargs):
        calls.append(True)
        return real_sha256(*args, **kwargs)

    monkeypatch.setattr(hashlib, "sha256", spy_sha256)

    model_file = tmp_path / "fake-model.gguf"
    model_file.write_bytes(b"x" * 10000)
    entries = provenance.build_model_entries(
        [("primary", model_file)], cache_path=tmp_path / "model_digests.json"
    )
    assert calls == []
    assert entries[0]["sha256_source"] == "not_computed"
    assert entries[0]["role"] == "primary"


def test_schedule_cold_model_digests_computes_once_in_background_and_caches(tmp_path):
    model_file = tmp_path / "fake-model.gguf"
    model_file.write_bytes(b"y" * 50000)
    cache_file = tmp_path / "model_digests.json"

    entries = provenance.build_model_entries([("primary", model_file)], cache_path=cache_file)
    assert entries[0]["sha256_source"] == "not_computed"

    captured = {}

    def fake_record_run_start_amended(*, emitter, pid, run_id, models, **_kw):
        captured["models"] = models

    import telemetry.recorders as recorders_mod

    original = recorders_mod.record_run_start_amended
    recorders_mod.record_run_start_amended = fake_record_run_start_amended
    try:
        provenance.schedule_cold_model_digests(
            models=entries, run_id="digestrun0000001", emitter="codey-os.core-api", pid=4,
            cache_path=cache_file,
        )
        assert _wait_for(lambda: "models" in captured)
    finally:
        recorders_mod.record_run_start_amended = original

    amended_models = captured["models"]
    assert amended_models[0]["sha256_source"] == "computed"
    assert amended_models[0]["sha256"] == hashlib.sha256(b"y" * 50000).hexdigest()

    cache = json.loads(cache_file.read_text(encoding="utf-8"))
    assert cache[str(model_file)]["sha256"] == amended_models[0]["sha256"]

    # A second call with a freshly cache-read entry must now report
    # "cached", not hash again.
    entries_again = provenance.build_model_entries([("primary", model_file)], cache_path=cache_file)
    assert entries_again[0]["sha256_source"] == "cached"
    assert entries_again[0]["sha256"] == amended_models[0]["sha256"]


def test_schedule_cold_model_digests_noop_when_nothing_cold(tmp_path):
    """No background thread at all should be spawned when every entry is
    already cached — asserted indirectly via record_run_start_amended
    never being called."""
    cache_file = tmp_path / "model_digests.json"
    model_file = tmp_path / "fake-model.gguf"
    model_file.write_bytes(b"z" * 100)
    stat = model_file.stat()
    cache_file.write_text(
        json.dumps(
            {
                str(model_file): {
                    "size_bytes": stat.st_size,
                    "mtime_ns": stat.st_mtime_ns,
                    "sha256": "c" * 64,
                    "computed_at": 1.0,
                }
            }
        ),
        encoding="utf-8",
    )
    entries = provenance.build_model_entries([("primary", model_file)], cache_path=cache_file)
    assert entries[0]["sha256_source"] == "cached"

    called = {"amended": False}

    import telemetry.recorders as recorders_mod

    original = recorders_mod.record_run_start_amended

    def fake(*args, **kwargs):
        called["amended"] = True

    recorders_mod.record_run_start_amended = fake
    try:
        provenance.schedule_cold_model_digests(
            models=entries, run_id="nocoldrun0000001", emitter="codey-os.core-api", pid=5,
            cache_path=cache_file,
        )
        time.sleep(0.3)  # give a would-be thread a chance to fire
    finally:
        recorders_mod.record_run_start_amended = original
    assert called["amended"] is False


def test_record_run_start_amended_never_written_to_runs_json(tmp_path):
    """§3.4: runs/<run_id>.json is never reopened for write — only the
    JSONL stream gets the follow-up record."""
    recorders.record_run_start(
        emitter="codey-os.core-api",
        pid=6,
        repo="Codey-OS",
        started_ts_wall=time.time(),
        run_id="amendnotinrun01",
    )
    run_file = tmp_path / "runs" / "amendnotinrun01.json"
    assert _wait_for(run_file.exists)
    before = run_file.read_text(encoding="utf-8")

    recorders.record_run_start_amended(
        emitter="codey-os.core-api",
        pid=6,
        run_id="amendnotinrun01",
        models=[{"role": "primary", "path": "/x", "sha256": "d" * 64, "sha256_source": "computed"}],
    )
    time.sleep(0.2)
    after = run_file.read_text(encoding="utf-8")
    assert before == after  # byte-identical -- never reopened for write
