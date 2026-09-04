"""
T4 — `codey-metrics` CLI (telemetry/cli.py) coverage: summary on an empty
and a populated store, malformed-trailing-line resilience, CSV/JSON/JSONL
export, provenance display (honest nulls + the NEW-330 duplicate
run_start decision), doctor's exit code, status, schema, and the
40-column default-output contract (design §3.5).

Records are written directly to `events/<date>/<category>.<run_id>.jsonl`
via `telemetry.envelope.build_envelope()` rather than through
`telemetry.store.Store`'s background thread, so each test controls
exactly which UTC day a record lands under and doesn't need to wait on a
flush cadence.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from telemetry import cli, envelope, rotate as rotate_mod


@pytest.fixture(autouse=True)
def _reset_seq():
    envelope.reset_seq()
    yield
    envelope.reset_seq()


def _today() -> str:
    return rotate_mod.utc_today().strftime("%Y-%m-%d")


def _make_record(category, event_type, emitter, pid, run_id, body, nulls=None, correlation_id=None):
    return envelope.build_envelope(
        category=category,
        event_type=event_type,
        emitter=emitter,
        pid=pid,
        run_id=run_id,
        body=body,
        correlation_id=correlation_id,
        nulls=nulls,
    )


def _write_jsonl(root: Path, date_str: str, category: str, run_id: str, records) -> Path:
    d = root / "events" / date_str
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{category}.{run_id}.jsonl"
    with open(path, "a", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, default=str) + "\n")
    return path


def _write_run_json(root: Path, record: dict) -> Path:
    d = root / "runs"
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{record['run_id']}.json"
    path.write_text(json.dumps(record, default=str), encoding="utf-8")
    return path


# ── summary ──────────────────────────────────────────────────────────────


def test_summary_empty_store(tmp_path, capsys):
    rc = cli.main(["summary", "--root", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "no records today" in out
    assert "store size" in out


def test_summary_with_real_records(tmp_path, capsys):
    today = _today()
    run_id = "sumrun0000000001"
    records = [
        _make_record(
            "inference", "completion", "codey-os.daemon", 100, run_id,
            {"backend": "local", "wall_ms": 50.0, "generation_tps": 40.0, "prefill_tps": 60.0},
        ),
        _make_record(
            "gate", "can_dispatch_task", "codey-os.daemon", 100, run_id,
            {"decision": {"allowed": True, "reason": "ok"}, "reason": "ok",
             "call_site": "x", "repeat_count": 1},
        ),
        _make_record(
            "extraction", "grounding_check", "aigentik", 200, run_id,
            {"outcome": "rejected", "numeric_tokens_in_value": 1, "numeric_tokens_matched": 0,
             "value_chars": 5, "source_chars": 20, "action_taken": "discarded"},
        ),
    ]
    _write_jsonl(tmp_path, today, "inference", run_id, [records[0]])
    _write_jsonl(tmp_path, today, "gate", run_id, [records[1]])
    _write_jsonl(tmp_path, today, "extraction", run_id, [records[2]])

    rc = cli.main(["summary", "--root", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "inference" in out and "1" in out
    assert "40.0t/s" in out
    assert "60.0t/s" in out
    assert "1/0" in out  # gate admit/deny
    assert "ground:rejected" in out


def test_summary_json_output(tmp_path, capsys):
    rc = cli.main(["summary", "--root", str(tmp_path), "--json"])
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out)
    assert payload["date_utc"] == _today()
    assert payload["category_counts"] == {}


# ── malformed-line resilience ────────────────────────────────────────────


def test_malformed_trailing_line_does_not_crash_summary(tmp_path, capsys):
    today = _today()
    run_id = "malformedrun0001"
    rec = _make_record("meta", "writer_started", "codey-os.daemon", 1, run_id, {"x": 1})
    path = _write_jsonl(tmp_path, today, "meta", run_id, [rec])
    with open(path, "a", encoding="utf-8") as f:
        f.write('{"truncated": "mid-writ')  # no closing brace/newline — torn write

    rc = cli.main(["summary", "--root", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "malformed lines" in out
    assert "1" in out


def test_malformed_line_not_present_after_valid_lines_still_all_read(tmp_path):
    """A malformed line in the middle, not just at the end, must not stop
    reading of lines after it (advisor point 6)."""
    today = _today()
    run_id = "midmalformed0001"
    d = tmp_path / "events" / today
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"meta.{run_id}.jsonl"
    rec1 = _make_record("meta", "writer_started", "codey-os.daemon", 1, run_id, {"x": 1})
    rec2 = _make_record("meta", "writer_started", "codey-os.daemon", 1, run_id, {"x": 2})
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(rec1, default=str) + "\n")
        f.write("not json at all\n")
        f.write(json.dumps(rec2, default=str) + "\n")

    from telemetry import rollup as rollup_mod

    kinds = [item.kind for item in rollup_mod.iter_records_for_date(tmp_path, today)]
    assert kinds == ["record", "malformed", "record"]


# ── export ───────────────────────────────────────────────────────────────


def test_export_jsonl(tmp_path, capsys):
    today = _today()
    run_id = "exportrun0000001"
    rec = _make_record("meta", "writer_started", "codey-os.daemon", 1, run_id, {"x": 1})
    _write_jsonl(tmp_path, today, "meta", run_id, [rec])

    rc = cli.main(["export", "--from", today, "--to", today, "--format", "jsonl", "--root", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    lines = [l for l in out.splitlines() if l.strip()]
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["run_id"] == run_id


def test_export_json_is_valid_array(tmp_path, capsys):
    today = _today()
    run_id = "exportrun0000002"
    rec = _make_record("meta", "writer_started", "codey-os.daemon", 1, run_id, {"x": 1})
    _write_jsonl(tmp_path, today, "meta", run_id, [rec])

    rc = cli.main(["export", "--from", today, "--to", today, "--format", "json", "--root", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    parsed = json.loads(out)
    assert isinstance(parsed, list) and len(parsed) == 1


def test_export_csv_has_flattened_body_columns(tmp_path, capsys):
    today = _today()
    run_id = "exportrun0000003"
    rec = _make_record(
        "inference", "completion", "codey-os.daemon", 1, run_id,
        {"backend": "local", "wall_ms": 12.5},
    )
    _write_jsonl(tmp_path, today, "inference", run_id, [rec])

    rc = cli.main(["export", "--from", today, "--to", today, "--format", "csv", "--root", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    header = out.splitlines()[0]
    assert "body.backend" in header
    assert "body.wall_ms" in header


def test_export_category_filter(tmp_path, capsys):
    today = _today()
    run_id = "exportrun0000004"
    rec_a = _make_record("meta", "writer_started", "codey-os.daemon", 1, run_id, {"x": 1})
    rec_b = _make_record("inference", "completion", "codey-os.daemon", 1, run_id, {"backend": "local", "wall_ms": 1.0})
    _write_jsonl(tmp_path, today, "meta", run_id, [rec_a])
    _write_jsonl(tmp_path, today, "inference", run_id, [rec_b])

    rc = cli.main(["export", "--from", today, "--to", today, "--category", "inference",
                   "--format", "jsonl", "--root", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    lines = [json.loads(l) for l in out.splitlines() if l.strip()]
    assert all(r["category"] == "inference" for r in lines)
    assert len(lines) == 1


# ── provenance ───────────────────────────────────────────────────────────


def test_provenance_shows_null_with_reason_not_hidden(tmp_path, capsys):
    run_id = "provnullrun00001"
    rec = _make_record(
        "provenance", "run_start", "codey-os.core-api", 1, run_id,
        body={
            "run_id": run_id, "started_ts_wall": 1000.0, "repo": "Codey-OS",
            "git_commit_sha": None, "device_uptime_sec": None, "models": [],
        },
        nulls={"body.git_commit_sha": "git_command_unavailable",
               "body.device_uptime_sec": "proc_uptime_permission_denied"},
    )
    _write_run_json(tmp_path, rec)
    _write_jsonl(tmp_path, _today(), "provenance", run_id, [rec])

    rc = cli.main(["provenance", "--run", run_id, "--root", str(tmp_path), "--wide"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "git_command_unavailable" in out
    assert "proc_uptime_permission_denied" in out
    # Never rendered as a bare/blank value:
    assert "git_commit_sha" in out


def test_provenance_new330_duplicate_run_start_flagged_not_hidden(tmp_path, capsys):
    """NEW-330 decision: a second run_start under the same run_id (the
    RestoriconAPIServer.start() re-entrancy gap) must be surfaced as an
    explicit warning, never silently collapsed or silently dropped."""
    run_id = "duprun0000000001"
    rec1 = _make_record(
        "provenance", "run_start", "codey-os.core-api", 100, run_id,
        body={"run_id": run_id, "started_ts_wall": 1000.0, "repo": "Codey-OS",
              "device_uptime_sec": None, "models": []},
        nulls={"body.device_uptime_sec": "proc_uptime_permission_denied"},
    )
    rec2 = _make_record(
        "provenance", "run_start", "codey-os.core-api", 101, run_id,
        body={"run_id": run_id, "started_ts_wall": 1001.0, "repo": "Codey-OS",
              "device_uptime_sec": None, "models": []},
        nulls={"body.device_uptime_sec": "proc_uptime_permission_denied"},
    )
    _write_run_json(tmp_path, rec1)  # only the first is ever persisted here
    _write_jsonl(tmp_path, _today(), "provenance", run_id, [rec1, rec2])

    # --wide (not the 40-column default) so the assertion checks the full
    # warning text rather than whatever survives column truncation.
    rc = cli.main(["provenance", "--run", run_id, "--root", str(tmp_path), "--wide"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "NEW-330" in out
    assert "additional run_start" in out

    # Also confirmed via --json, where nothing is truncated for width.
    rc_json = cli.main(["provenance", "--run", run_id, "--root", str(tmp_path), "--json"])
    out_json = capsys.readouterr().out
    payload = json.loads(out_json)
    assert rc_json == 0
    assert "NEW-330" in payload["_duplicate_run_start_warning"]


def test_provenance_latest_picks_most_recent_run(tmp_path, capsys):
    older = _make_record(
        "provenance", "run_start", "codey-os.tui", 1, "olderrun00000001",
        body={"run_id": "olderrun00000001", "started_ts_wall": 100.0, "repo": "Codey-OS",
              "device_uptime_sec": None, "models": []},
        nulls={"body.device_uptime_sec": "proc_uptime_permission_denied"},
    )
    newer = _make_record(
        "provenance", "run_start", "codey-os.tui", 2, "newerrun00000001",
        body={"run_id": "newerrun00000001", "started_ts_wall": 200.0, "repo": "Codey-OS",
              "device_uptime_sec": None, "models": []},
        nulls={"body.device_uptime_sec": "proc_uptime_permission_denied"},
    )
    _write_run_json(tmp_path, older)
    _write_run_json(tmp_path, newer)
    _write_jsonl(tmp_path, _today(), "provenance", "olderrun00000001", [older])
    _write_jsonl(tmp_path, _today(), "provenance", "newerrun00000001", [newer])

    rc = cli.main(["provenance", "--latest", "--root", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "newerrun00000001" in out
    assert "olderrun00000001" not in out


def test_provenance_all_prints_every_run_even_when_one_has_no_data(tmp_path, capsys):
    """A `_print_run` short-circuit via `rc = rc or _print_run(...)` made
    the --all loop stop printing after the first run with no provenance
    data (nonzero rc), silently skipping every later run even when they
    had real data. Confirm all 3 runs are processed regardless of
    ordering, and the run with no data is still flagged in the exit code."""
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)

    # run1: alphabetically first, but its runs/<id>.json is corrupt and it
    # has no matching provenance stream records either -> _print_run
    # returns 1 ("no provenance found").
    (runs_dir / "run1nodata0000001.json").write_text("not valid json{{{", encoding="utf-8")

    # run2 and run3: real data, both should still print despite run1's
    # no-data result coming first in sorted order.
    rec2 = _make_record(
        "provenance", "run_start", "codey-os.tui", 2, "run2hasdata000001",
        body={"run_id": "run2hasdata000001", "started_ts_wall": 200.0, "repo": "Codey-OS",
              "device_uptime_sec": None, "models": []},
        nulls={"body.device_uptime_sec": "proc_uptime_permission_denied"},
    )
    rec3 = _make_record(
        "provenance", "run_start", "codey-os.tui", 3, "run3hasdata000001",
        body={"run_id": "run3hasdata000001", "started_ts_wall": 300.0, "repo": "Codey-OS",
              "device_uptime_sec": None, "models": []},
        nulls={"body.device_uptime_sec": "proc_uptime_permission_denied"},
    )
    _write_run_json(tmp_path, rec2)
    _write_run_json(tmp_path, rec3)
    _write_jsonl(tmp_path, _today(), "provenance", "run2hasdata000001", [rec2])
    _write_jsonl(tmp_path, _today(), "provenance", "run3hasdata000001", [rec3])

    rc = cli.main(["provenance", "--all", "--root", str(tmp_path)])
    out = capsys.readouterr().out
    # Both later runs must still be printed even though the first (in
    # sorted order) had no data.
    assert "run2hasdata000001" in out
    assert "run3hasdata000001" in out
    # Overall exit code still reflects the no-data run.
    assert rc != 0


# ── doctor ───────────────────────────────────────────────────────────────


def test_doctor_exit_zero_on_clean_run_with_writer_stopped(tmp_path, capsys):
    run_id = "cleanrun00000001"
    today = _today()
    run_start = _make_record(
        "provenance", "run_start", "codey-os.daemon", 1, run_id,
        body={"run_id": run_id, "started_ts_wall": 1.0, "repo": "Codey-OS",
              "device_uptime_sec": None, "models": []},
        nulls={"body.device_uptime_sec": "proc_uptime_permission_denied"},
    )
    stopped = _make_record("meta", "writer_stopped", "codey-os.daemon", 1, run_id, {})
    _write_jsonl(tmp_path, today, "provenance", run_id, [run_start])
    _write_jsonl(tmp_path, today, "meta", run_id, [stopped])

    rc = cli.main(["doctor", "--root", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "hard violations: 0" in out


def test_doctor_exit_nonzero_on_orphan_run(tmp_path, capsys):
    run_id = "orphanrun0000001"
    today = _today()
    # An event with no matching run_start anywhere -- a real integrity gap.
    rec = _make_record("inference", "completion", "codey-os.daemon", 1, run_id,
                        {"backend": "local", "wall_ms": 1.0})
    _write_jsonl(tmp_path, today, "inference", run_id, [rec])

    rc = cli.main(["doctor", "--root", str(tmp_path)])
    assert rc == 1


def test_doctor_reports_seq_gap_as_hard_violation(tmp_path, capsys):
    run_id = "seqgaprun0000001"
    today = _today()
    r0 = _make_record("meta", "writer_started", "codey-os.daemon", 1, run_id, {"x": 0})
    # r1 is skipped -- simulates a dropped record. The shared seq counter
    # (telemetry/envelope.py's next_seq()) would naturally assign 1 here
    # since only two records are built; force it to 2 to leave an explicit
    # gap at seq=1, which is the actual signal being tested.
    r2 = dict(_make_record("meta", "writer_started", "codey-os.daemon", 1, run_id, {"x": 2}))
    r2["seq"] = 2
    _write_jsonl(tmp_path, today, "meta", run_id, [r0, r2])

    rc = cli.main(["doctor", "--root", str(tmp_path), "--json"])
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["seq_gap_suspected_drops"] >= 1
    assert rc == 1


def test_doctor_null_without_reason_is_a_violation(tmp_path, capsys):
    run_id = "unreasoned0000001"
    today = _today()
    rec = envelope.build_envelope(
        category="meta", event_type="writer_started", emitter="codey-os.daemon", pid=1,
        run_id=run_id, body={"reason": None},  # null with no matching `nulls` entry
    )
    _write_jsonl(tmp_path, today, "meta", run_id, [rec])

    rc = cli.main(["doctor", "--root", str(tmp_path), "--json"])
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert len(payload["honest_null_violations"]) >= 1
    assert rc == 1


# ── status ───────────────────────────────────────────────────────────────


def test_status_reports_schema_version_and_hash(tmp_path, capsys):
    from telemetry import schema as schema_mod

    rc = cli.main(["status", "--root", str(tmp_path), "--json"])
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out)
    assert payload["schema_version"] == schema_mod.SCHEMA_VERSION
    assert payload["schema_sha256_12"] == schema_mod.SCHEMA_SHA256_12


def test_status_dropped_meta_note_present_when_no_meta_seen(tmp_path, capsys):
    rc = cli.main(["status", "--root", str(tmp_path), "--json"])
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["dropped_total_from_meta_records"] == 0
    assert payload["dropped_total_meta_note"] is not None  # honest, not a bare claimed zero


# ── schema ───────────────────────────────────────────────────────────────


def test_schema_default_prints_version_and_hash(tmp_path, capsys):
    from telemetry import schema as schema_mod

    rc = cli.main(["schema", "--root", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert str(schema_mod.SCHEMA_VERSION) in out
    assert schema_mod.SCHEMA_SHA256_12 in out


# ── 40-column default output ────────────────────────────────────────────


def test_summary_default_output_fits_40_columns(tmp_path, capsys):
    today = _today()
    run_id = "widthrun00000001"
    rec = _make_record(
        "inference", "completion", "codey-os.daemon", 1, run_id,
        {"backend": "local", "wall_ms": 1.0, "generation_tps": 12345.6789, "prefill_tps": 1.0},
    )
    _write_jsonl(tmp_path, today, "inference", run_id, [rec])

    rc = cli.main(["summary", "--root", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    for line in out.splitlines():
        assert len(line) <= 40, f"line exceeds 40 columns: {line!r}"


def test_status_default_output_fits_40_columns(tmp_path, capsys):
    rc = cli.main(["status", "--root", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    for line in out.splitlines():
        assert len(line) <= 40, f"line exceeds 40 columns: {line!r}"


# ── top-level --help/-h ─────────────────────────────────────────────────


def test_help_shows_top_level_subcommand_list_not_summary_help(capsys):
    """`codey-metrics --help` must reach the top-level parser's help (the
    real subcommand list) rather than being silently rewritten into
    "summary --help" by main()'s implicit-subcommand-prepend logic, which
    would only ever show "summary"'s own (subcommand-specific) help."""
    with pytest.raises(SystemExit) as exc_info:
        cli.main(["--help"])
    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    for cmd in cli.KNOWN_COMMANDS:
        assert cmd in out, f"top-level help missing subcommand {cmd!r}: {out!r}"
    # Not just the "summary" subparser's own help text (which has no
    # subcommand list of its own).
    assert "{summary,export,provenance,status,doctor,rollup,rotate,schema}" in out


def test_h_short_flag_shows_top_level_subcommand_list(capsys):
    with pytest.raises(SystemExit) as exc_info:
        cli.main(["-h"])
    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    for cmd in cli.KNOWN_COMMANDS:
        assert cmd in out, f"top-level help missing subcommand {cmd!r}: {out!r}"
