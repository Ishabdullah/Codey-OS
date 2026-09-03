"""
Envelope shape, seq monotonicity, 8 KiB truncation behaviour, and the
honest-null invariant (no null without a reason) — schema.validate() is
the mechanical check for the last one.
"""

from __future__ import annotations

import json

from telemetry import envelope, schema


def setup_function(_fn):
    envelope.reset_seq()


def _minimal_record(**overrides):
    body = {"foo": "bar"}
    kwargs = dict(
        category="meta",
        event_type="writer_started",
        emitter="codey-os.daemon",
        pid=12345,
        run_id="a" * 16,
        body=body,
    )
    kwargs.update(overrides)
    return envelope.build_envelope(**kwargs)


def test_envelope_has_all_required_fields():
    record = _minimal_record()
    for field in (
        "schema_version",
        "schema_sha256",
        "event_id",
        "run_id",
        "boot_id",
        "seq",
        "ts_wall",
        "ts_mono",
        "category",
        "event_type",
        "emitter",
        "pid",
        "correlation_id",
        "nulls",
        "body",
    ):
        assert field in record, f"missing {field}"


def test_envelope_schema_version_and_hash_match_schema_module():
    record = _minimal_record()
    assert record["schema_version"] == schema.SCHEMA_VERSION
    assert record["schema_sha256"] == schema.SCHEMA_SHA256_12


def test_event_id_is_32_lowercase_hex():
    record = _minimal_record()
    assert len(record["event_id"]) == 32
    assert record["event_id"] == record["event_id"].lower()
    int(record["event_id"], 16)  # raises if not hex


def test_seq_is_monotonic_within_a_run():
    r1 = _minimal_record()
    r2 = _minimal_record()
    r3 = _minimal_record()
    assert [r1["seq"], r2["seq"], r3["seq"]] == [0, 1, 2]


def test_reset_seq_restarts_at_zero():
    _minimal_record()
    _minimal_record()
    envelope.reset_seq()
    r = _minimal_record()
    assert r["seq"] == 0


def test_correlation_id_absent_gets_honest_null_reason():
    record = _minimal_record(correlation_id=None)
    assert record["correlation_id"] is None
    assert record["nulls"]["correlation_id"] == "correlation_id_not_yet_available"


def test_correlation_id_present_has_no_null_entry():
    record = _minimal_record(correlation_id="b" * 32)
    assert record["correlation_id"] == "b" * 32
    assert "correlation_id" not in record["nulls"]


def test_caller_supplied_body_nulls_are_preserved():
    record = _minimal_record(
        body={"cpu_percent": None},
        nulls={"body.cpu_percent": "proc_stat_permission_denied"},
    )
    assert record["nulls"]["body.cpu_percent"] == "proc_stat_permission_denied"


def test_minimal_record_passes_schema_validate():
    record = _minimal_record(correlation_id="c" * 32)
    violations = schema.validate(record)
    assert violations == []


def test_record_with_unreasoned_null_fails_validate():
    record = _minimal_record(correlation_id="d" * 32)
    record["body"]["some_field"] = None  # no matching nulls entry
    violations = schema.validate(record)
    assert any("body.some_field" in v for v in violations)


def test_oversize_record_is_truncated_not_dropped():
    huge_string = "x" * 20000
    record = _minimal_record(body={"huge": huge_string}, correlation_id="e" * 32)
    serialized = json.dumps(record, separators=(",", ":"))
    assert len(serialized.encode("utf-8")) <= schema.RECORD_SIZE_CAP_BYTES
    assert record["body"]["huge"] != huge_string
    assert record["nulls"]["body.huge"] == "truncated_oversize_record"
    assert "huge" in record["body"]["_truncated_fields"]


def test_truncated_field_is_shorter_not_null():
    """The honest-null contract is one-directional: a field in `nulls`
    for truncation is NOT expected to actually be null — it holds a
    shortened string. schema.validate() must not flag this as a
    violation the other way around."""
    huge_string = "y" * 20000
    record = _minimal_record(body={"huge": huge_string}, correlation_id="f" * 32)
    assert record["body"]["huge"] is not None
    violations = schema.validate(record)
    # No "is null with no entry in nulls" violation for `huge` — it's not
    # null at all, it's truncated.
    assert not any("body.huge is null" in v for v in violations)


def test_get_boot_id_never_raises_and_returns_str_or_none():
    result = envelope.get_boot_id()
    assert result is None or isinstance(result, str)
