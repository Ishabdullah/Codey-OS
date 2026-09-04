"""
T4 — `telemetry/rotate.py`: never touches the current/previous UTC day,
is safe to run twice (idempotent — no double-compression or data loss on
a second run), verifies before removing the source, and recovers cleanly
from a crash-mid-rotation state (archive present, source also still
present). Also covers `telemetry/rollup.py`'s "genuinely rebuildable"
guarantee: delete `rollups.db`, rebuild, get the same numbers — including
through the archive read path once rotation has actually run.
"""

from __future__ import annotations

import json
import tarfile
from datetime import date, timedelta
from pathlib import Path

import pytest

from telemetry import envelope, rollup as rollup_mod, rotate as rotate_mod


@pytest.fixture(autouse=True)
def _reset_seq():
    envelope.reset_seq()
    yield
    envelope.reset_seq()


def _write_day(root: Path, date_str: str, run_id: str, n: int = 3, category: str = "meta") -> Path:
    d = root / "events" / date_str
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{category}.{run_id}.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        for i in range(n):
            rec = envelope.build_envelope(
                category=category, event_type="writer_started", emitter="codey-os.daemon",
                pid=1, run_id=run_id, body={"i": i},
            )
            f.write(json.dumps(rec, default=str) + "\n")
    return path


def _old_date_str(days_ago: int) -> str:
    return (rotate_mod.utc_today() - timedelta(days=days_ago)).strftime("%Y-%m-%d")


# ── never touches current/previous day ──────────────────────────────────


def test_rotate_never_touches_today_or_yesterday(tmp_path):
    today = rotate_mod.utc_today().strftime("%Y-%m-%d")
    yesterday = _old_date_str(1)
    _write_day(tmp_path, today, "todayrun00000001")
    _write_day(tmp_path, yesterday, "yestrun000000001")

    eligible = rotate_mod.eligible_dates(tmp_path)
    assert today not in eligible
    assert yesterday not in eligible

    results = rotate_mod.rotate_all(tmp_path)
    assert results == []
    assert (tmp_path / "events" / today).is_dir()
    assert (tmp_path / "events" / yesterday).is_dir()


def test_eligible_dates_excludes_within_retention_window(tmp_path):
    six_days_ago = _old_date_str(6)
    _write_day(tmp_path, six_days_ago, "sixdaysrun0000001")
    assert six_days_ago not in rotate_mod.eligible_dates(tmp_path, retention_days=7)


def test_eligible_dates_includes_older_than_retention(tmp_path):
    eight_days_ago = _old_date_str(8)
    _write_day(tmp_path, eight_days_ago, "eightdaysrun00001")
    assert eight_days_ago in rotate_mod.eligible_dates(tmp_path, retention_days=7)


# ── basic rotation + verification ───────────────────────────────────────


def test_rotate_day_archives_and_removes_source(tmp_path):
    old = _old_date_str(10)
    _write_day(tmp_path, old, "rotrun0000000001", n=5)

    result = rotate_mod.rotate_day(tmp_path, old)
    assert result.action == "archived"
    assert result.source_record_count == 5
    assert result.archive_record_count == 5
    assert not (tmp_path / "events" / old).exists()

    archive_path = tmp_path / "archive" / old[:7] / f"{old}.tar.gz"
    assert archive_path.is_file()
    with tarfile.open(archive_path, "r:gz") as tf:
        names = tf.getnames()
    assert f"meta.rotrun0000000001.jsonl" in names


def test_rotate_dry_run_makes_no_changes(tmp_path):
    old = _old_date_str(10)
    _write_day(tmp_path, old, "dryrun00000000001", n=2)

    result = rotate_mod.rotate_day(tmp_path, old, dry_run=True)
    assert result.action == "dry_run"
    assert (tmp_path / "events" / old).is_dir()
    assert not (tmp_path / "archive").exists()


def test_rotate_failed_verification_leaves_source_in_place(tmp_path, monkeypatch):
    old = _old_date_str(10)
    _write_day(tmp_path, old, "failrun00000000001", n=3)

    # Force a verification mismatch by making the tar-line-counter report
    # fewer records than are actually in the source, simulating a corrupt
    # write without needing to hand-craft a broken tar.gz.
    monkeypatch.setattr(rotate_mod, "_count_lines_in_tar", lambda p: 0)

    result = rotate_mod.rotate_day(tmp_path, old)
    assert result.action == "failed"
    assert (tmp_path / "events" / old).is_dir()  # source NOT removed


# ── idempotency / crash-mid-rotation recovery ───────────────────────────


def test_rotate_is_idempotent_running_twice(tmp_path):
    old = _old_date_str(10)
    _write_day(tmp_path, old, "idemrun0000000001", n=4)

    first = rotate_mod.rotate_day(tmp_path, old)
    assert first.action == "archived"
    archive_path = tmp_path / "archive" / old[:7] / f"{old}.tar.gz"
    first_bytes = archive_path.read_bytes()

    second = rotate_mod.rotate_day(tmp_path, old)
    assert second.action == "verified_existing"
    assert archive_path.read_bytes() == first_bytes  # not re-written


def test_rotate_recovers_when_archive_and_source_both_present(tmp_path):
    """Simulates a process killed after writing a valid archive but
    before removing the source directory. Restores the EXACT original
    bytes (not freshly-generated records with new event_ids) — a
    same-content restore is the only thing that should let rotate_day
    trust the existing archive without rebuilding it."""
    old = _old_date_str(10)
    path = _write_day(tmp_path, old, "crashrun0000000001", n=3)
    original_bytes = path.read_bytes()

    first = rotate_mod.rotate_day(tmp_path, old)
    assert first.action == "archived"
    archive_path = tmp_path / "archive" / old[:7] / f"{old}.tar.gz"
    archive_bytes_after_first = archive_path.read_bytes()

    # Re-create the source directory with the exact original bytes
    # (simulating "archive was written, but rmtree never ran").
    d = tmp_path / "events" / old
    d.mkdir(parents=True)
    (d / "meta.crashrun0000000001.jsonl").write_bytes(original_bytes)

    second = rotate_mod.rotate_day(tmp_path, old)
    # The existing archive's records are identical to the source's
    # (same event_ids) -> trusted as-is, NOT rebuilt.
    assert second.action == "verified_existing"
    assert not (tmp_path / "events" / old).exists()
    assert archive_path.read_bytes() == archive_bytes_after_first


def test_rotate_rebuilds_archive_when_source_changed_after_crash(tmp_path):
    """The actual bug this guards against: if the source directory's
    records DIFFER from what the existing archive holds (e.g. new/
    different records appeared after the archive was written), rotate_day
    must rebuild the archive rather than trust a stale one and destroy the
    new records by removing the source out from under them."""
    old = _old_date_str(10)
    _write_day(tmp_path, old, "changedrun00000001", n=2)

    first = rotate_mod.rotate_day(tmp_path, old)
    assert first.action == "archived"
    archive_path = tmp_path / "archive" / old[:7] / f"{old}.tar.gz"
    archive_ids_after_first = rotate_mod._collect_event_ids_in_tar(archive_path)

    # Source re-appears with DIFFERENT records (different event_ids) --
    # e.g. a bug re-created the directory with new content.
    new_path = _write_day(tmp_path, old, "changedrun00000001", n=2)
    source_ids = rotate_mod._collect_event_ids_in_dir(new_path.parent)
    assert source_ids != archive_ids_after_first  # precondition of this test

    second = rotate_mod.rotate_day(tmp_path, old)
    assert second.action == "archived"  # rebuilt, not blindly trusted
    archive_ids_after_second = rotate_mod._collect_event_ids_in_tar(archive_path)
    assert archive_ids_after_second == source_ids
    assert not (tmp_path / "events" / old).exists()


def test_rotate_all_returns_one_result_per_eligible_date(tmp_path):
    d1 = _old_date_str(10)
    d2 = _old_date_str(15)
    _write_day(tmp_path, d1, "multirun00000001", n=1)
    _write_day(tmp_path, d2, "multirun00000002", n=1)

    results = rotate_mod.rotate_all(tmp_path)
    assert {r.date_str for r in results} == {d1, d2}
    assert all(r.action == "archived" for r in results)


# ── rollup: genuinely rebuildable, including from the archive path ─────


def test_rollup_rebuild_is_deterministic(tmp_path):
    today = rotate_mod.utc_today().strftime("%Y-%m-%d")
    run_id = "rollupdet0000001"
    d = tmp_path / "events" / today
    d.mkdir(parents=True, exist_ok=True)
    with open(d / f"inference.{run_id}.jsonl", "w", encoding="utf-8") as f:
        for tps in (10.0, 20.0, 30.0):
            rec = envelope.build_envelope(
                category="inference", event_type="completion", emitter="codey-os.daemon",
                pid=1, run_id=run_id,
                body={"backend": "local", "wall_ms": 1.0, "generation_tps": tps, "prefill_tps": tps},
            )
            f.write(json.dumps(rec, default=str) + "\n")

    rollup_mod.rebuild_dates(tmp_path, [today])
    db_path = tmp_path / "rollups.db"
    assert db_path.is_file()

    import sqlite3

    conn = sqlite3.connect(str(db_path))
    row = conn.execute(
        "SELECT completion_count, median_generation_tps FROM inference_stats WHERE date = ?", (today,)
    ).fetchone()
    conn.close()
    assert row == (3, 20.0)

    # Delete and rebuild — must reproduce the identical aggregate (the
    # whole point of "rebuildable derived cache, not evidence").
    db_path.unlink()
    rollup_mod.rebuild_dates(tmp_path, [today])
    conn = sqlite3.connect(str(db_path))
    row2 = conn.execute(
        "SELECT completion_count, median_generation_tps FROM inference_stats WHERE date = ?", (today,)
    ).fetchone()
    conn.close()
    assert row2 == row


def test_rollup_rebuild_survives_rotation(tmp_path):
    """rollup -> rotate -> rollup --rebuild must produce identical
    aggregates, proving the archive read path is exercised, not just the
    raw-directory path."""
    old = _old_date_str(10)
    run_id = "rollrotrun000001"
    d = tmp_path / "events" / old
    d.mkdir(parents=True, exist_ok=True)
    with open(d / f"inference.{run_id}.jsonl", "w", encoding="utf-8") as f:
        for tps in (5.0, 15.0):
            rec = envelope.build_envelope(
                category="inference", event_type="completion", emitter="codey-os.daemon",
                pid=1, run_id=run_id,
                body={"backend": "local", "wall_ms": 1.0, "generation_tps": tps, "prefill_tps": tps},
            )
            f.write(json.dumps(rec, default=str) + "\n")

    rollup_mod.rebuild_dates(tmp_path, [old])
    import sqlite3

    conn = sqlite3.connect(str(tmp_path / "rollups.db"))
    before = conn.execute(
        "SELECT completion_count, median_generation_tps FROM inference_stats WHERE date = ?", (old,)
    ).fetchone()
    conn.close()
    assert before == (2, 10.0)

    result = rotate_mod.rotate_day(tmp_path, old)
    assert result.action == "archived"
    assert not (tmp_path / "events" / old).exists()

    (tmp_path / "rollups.db").unlink()
    rollup_mod.rebuild_dates(tmp_path, [old])
    conn = sqlite3.connect(str(tmp_path / "rollups.db"))
    after = conn.execute(
        "SELECT completion_count, median_generation_tps FROM inference_stats WHERE date = ?", (old,)
    ).fetchone()
    conn.close()
    assert after == before


# ── lock ─────────────────────────────────────────────────────────────────


def test_acquire_rotate_lock_prevents_concurrent_holder(tmp_path):
    with rotate_mod.acquire_rotate_lock(tmp_path) as first:
        assert first is True
        with rotate_mod.acquire_rotate_lock(tmp_path) as second:
            assert second is False
