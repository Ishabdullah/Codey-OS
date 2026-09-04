"""
Builds/rebuilds ``rollups.db`` daily aggregates from raw JSONL and
archives (docs/telemetry_layer_design.md §3.2, §8 item 9).

**`rollups.db` is a rebuildable derived cache, NOT evidence** (design §8
item 9, confirmed by Ish). Every table in this module is written with
delete-then-insert-per-date semantics specifically so that dropping the
whole file and calling `rebuild_all()` again reproduces byte-identical
aggregate rows from the same raw record set — there is no append-only
guarantee anywhere in this module, and there must not be one: an
append-only requirement on this file would be over-engineering against a
constraint the design explicitly relaxed. The raw JSONL under `events/`
and the gzip archives under `archive/` are the actual evidence; this file
exists purely so `codey-metrics summary`/`status` don't have to re-scan
the entire raw record set on every invocation.

This module also owns the shared record-reading utilities used by
`cli.py` (summary/export/provenance/doctor) and by nothing else outside
`telemetry/` — reading a JSONL line that may be malformed (a torn
mid-write line from a killed process) or reading transparently from a
`.tar.gz` archive once rotation has run is common to every read-only
subcommand, so it is implemented once here rather than three times.
"""

from __future__ import annotations

import json
import sqlite3
import statistics
import tarfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from telemetry import rotate as _rotate

ROLLUPS_DB_FILENAME = "rollups.db"


# ── shared record reading (raw JSONL, transparently falling back to archive) ──


@dataclass
class ReadItem:
    kind: str  # "record" | "malformed"
    record: Optional[Dict[str, Any]]
    source: str
    line_no: int


def _iter_lines_raw(path: Path) -> Iterator[tuple]:
    """
    Yields (line_no, raw_line) for a live/raw JSONL file. `errors="replace"`
    and per-line handling (not a single `f.read()`) mean a partially-written
    final line (process killed mid-write, e.g. by a concurrent daemon
    append) shows up as one line this generator still yields — the caller
    is responsible for treating a JSON-parse failure on it as "malformed",
    never as a reason to stop reading the file; every line before it is
    still valid and must still be counted.
    """
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line_no, raw in enumerate(f, start=1):
            line = raw.rstrip("\n")
            if not line.strip():
                continue
            yield line_no, line


def _iter_lines_tar_member(tf: tarfile.TarFile, member: tarfile.TarInfo) -> Iterator[tuple]:
    fh = tf.extractfile(member)
    if fh is None:
        return
    for line_no, raw in enumerate(fh, start=1):
        line = raw.decode("utf-8", errors="replace").rstrip("\n")
        if not line.strip():
            continue
        yield line_no, line


def iter_records_for_date(
    root: Path, date_str: str, category: Optional[str] = None
) -> Iterator[ReadItem]:
    """
    Reads every record for one UTC day. If a raw `events/<date>/` directory
    still exists, it is read (and the archive for that date, if any, is
    deliberately NOT also read — advisor-flagged crash-mid-rotation case: a
    rotation that wrote a valid archive but was killed before removing the
    source would otherwise be double-counted by whoever calls this). Only
    once the raw directory is gone does the archive become this date's
    source of truth. Never raises: an unreadable/corrupt archive yields
    nothing for that date rather than propagating a `TarError`.
    """
    root = Path(root)
    raw_dir = root / "events" / date_str
    if raw_dir.is_dir():
        pattern = f"{category}.*.jsonl" if category else "*.jsonl"
        for path in sorted(raw_dir.glob(pattern)):
            for line_no, line in _iter_lines_raw(path):
                yield _parse_line(line, str(path), line_no)
        return

    archive_path = root / "archive" / date_str[:7] / f"{date_str}.tar.gz"
    if not archive_path.is_file():
        return
    try:
        with tarfile.open(archive_path, mode="r:gz") as tf:
            for member in sorted(tf.getmembers(), key=lambda m: m.name):
                if not member.isfile():
                    continue
                if category and not member.name.startswith(f"{category}."):
                    continue
                for line_no, line in _iter_lines_tar_member(tf, member):
                    yield _parse_line(line, f"{archive_path}::{member.name}", line_no)
    except (tarfile.TarError, OSError):
        return


def _parse_line(line: str, source: str, line_no: int) -> ReadItem:
    try:
        rec = json.loads(line)
    except json.JSONDecodeError:
        return ReadItem(kind="malformed", record=None, source=source, line_no=line_no)
    if not isinstance(rec, dict):
        return ReadItem(kind="malformed", record=None, source=source, line_no=line_no)
    return ReadItem(kind="record", record=rec, source=source, line_no=line_no)


def _date_range(start_date: str, end_date: str) -> List[str]:
    start = datetime.strptime(start_date, "%Y-%m-%d").date()
    end = datetime.strptime(end_date, "%Y-%m-%d").date()
    if end < start:
        start, end = end, start
    out = []
    d = start
    while d <= end:
        out.append(d.strftime("%Y-%m-%d"))
        d += timedelta(days=1)
    return out


def iter_records_for_range(
    root: Path, start_date: str, end_date: str, category: Optional[str] = None
) -> Iterator[ReadItem]:
    for date_str in _date_range(start_date, end_date):
        yield from iter_records_for_date(root, date_str, category=category)


def get_all_dates(root: Path) -> List[str]:
    """Every UTC date with data anywhere — raw `events/` or `archive/`."""
    root = Path(root)
    dates = set(_rotate.list_event_day_dirs(root))
    archive_dir = root / "archive"
    if archive_dir.is_dir():
        for month_dir in archive_dir.iterdir():
            if not month_dir.is_dir():
                continue
            for f in month_dir.glob("*.tar.gz"):
                if f.name.endswith(".tar.gz"):
                    dates.add(f.name[: -len(".tar.gz")])
    return sorted(dates)


# ── rollups.db schema + rebuild ─────────────────────────────────────────────

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS event_counts (
    date TEXT NOT NULL,
    category TEXT NOT NULL,
    event_type TEXT NOT NULL,
    count INTEGER NOT NULL,
    PRIMARY KEY (date, category, event_type)
);
CREATE TABLE IF NOT EXISTS gate_decisions (
    date TEXT NOT NULL,
    event_type TEXT NOT NULL,
    admitted_count INTEGER NOT NULL,
    denied_count INTEGER NOT NULL,
    PRIMARY KEY (date, event_type)
);
CREATE TABLE IF NOT EXISTS extraction_outcomes (
    date TEXT NOT NULL,
    outcome TEXT NOT NULL,
    count INTEGER NOT NULL,
    PRIMARY KEY (date, outcome)
);
CREATE TABLE IF NOT EXISTS inference_stats (
    date TEXT PRIMARY KEY,
    completion_count INTEGER NOT NULL,
    median_generation_tps REAL,
    median_prefill_tps REAL
);
CREATE TABLE IF NOT EXISTS rollup_meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA_SQL)


def admit_deny_key(decision: Dict[str, Any]) -> Optional[bool]:
    """
    `body.decision` is `dataclasses.asdict()` of whichever decision type
    fired (GateDecision.admitted, DispatchDecision.allowed,
    ContextBudgetDecision.admitted, TripDecision.should_trip — the field
    NAME differs per type, verbatim per design §2.B). Only the two
    admit/deny-shaped types are bucketed here; `should_trip_shutdown`'s
    `should_trip` is a different kind of boolean (trip vs. no-trip, not
    admit vs. deny) and is deliberately excluded from this bucket rather
    than mislabeled.
    """
    if not isinstance(decision, dict):
        return None
    if "admitted" in decision:
        return bool(decision["admitted"])
    if "allowed" in decision:
        return bool(decision["allowed"])
    return None


def rebuild_dates(root: Path, dates: List[str], db_path: Optional[Path] = None) -> None:
    """Recomputes and upserts (delete-then-insert) rollup rows for exactly
    the given UTC dates. Safe to call repeatedly for the same date — that
    IS what "rebuildable" means operationally (module docstring)."""
    root = Path(root)
    db_path = Path(db_path) if db_path is not None else (root / ROLLUPS_DB_FILENAME)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        _ensure_schema(conn)
        for date_str in dates:
            _rebuild_one_date(conn, root, date_str)
        conn.execute(
            "INSERT INTO rollup_meta (key, value) VALUES ('last_rebuilt_ts', ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (datetime.now(timezone.utc).isoformat(),),
        )
        conn.commit()
    finally:
        conn.close()


def rebuild_all(root: Path, db_path: Optional[Path] = None) -> List[str]:
    """Rebuilds every date currently present under `events/` or
    `archive/`. Returns the list of dates rebuilt."""
    dates = get_all_dates(root)
    rebuild_dates(root, dates, db_path=db_path)
    return dates


def _rebuild_one_date(conn: sqlite3.Connection, root: Path, date_str: str) -> None:
    conn.execute("DELETE FROM event_counts WHERE date = ?", (date_str,))
    conn.execute("DELETE FROM gate_decisions WHERE date = ?", (date_str,))
    conn.execute("DELETE FROM extraction_outcomes WHERE date = ?", (date_str,))
    conn.execute("DELETE FROM inference_stats WHERE date = ?", (date_str,))

    event_counts: Dict[tuple, int] = {}
    gate_counts: Dict[str, List[int]] = {}  # event_type -> [admitted, denied]
    outcome_counts: Dict[str, int] = {}
    gen_tps: List[float] = []
    prefill_tps: List[float] = []
    completion_count = 0

    for item in iter_records_for_date(root, date_str):
        if item.kind != "record":
            continue
        rec = item.record
        category = rec.get("category")
        event_type = rec.get("event_type")
        if not category or not event_type:
            continue
        key = (category, event_type)
        event_counts[key] = event_counts.get(key, 0) + 1

        body = rec.get("body") or {}
        if not isinstance(body, dict):
            continue

        if category == "gate":
            admitted = admit_deny_key(body.get("decision") or {})
            if admitted is not None:
                bucket = gate_counts.setdefault(event_type, [0, 0])
                bucket[0 if admitted else 1] += 1

        if category == "extraction" and event_type == "grounding_check":
            outcome = body.get("outcome")
            if isinstance(outcome, str):
                outcome_counts[outcome] = outcome_counts.get(outcome, 0) + 1

        if category == "inference" and event_type == "completion":
            completion_count += 1
            g = body.get("generation_tps")
            if isinstance(g, (int, float)):
                gen_tps.append(float(g))
            p = body.get("prefill_tps")
            if isinstance(p, (int, float)):
                prefill_tps.append(float(p))

    for (category, event_type), count in event_counts.items():
        conn.execute(
            "INSERT INTO event_counts (date, category, event_type, count) VALUES (?, ?, ?, ?)",
            (date_str, category, event_type, count),
        )
    for event_type, (admitted, denied) in gate_counts.items():
        conn.execute(
            "INSERT INTO gate_decisions (date, event_type, admitted_count, denied_count) "
            "VALUES (?, ?, ?, ?)",
            (date_str, event_type, admitted, denied),
        )
    for outcome, count in outcome_counts.items():
        conn.execute(
            "INSERT INTO extraction_outcomes (date, outcome, count) VALUES (?, ?, ?)",
            (date_str, outcome, count),
        )
    if completion_count:
        conn.execute(
            "INSERT INTO inference_stats (date, completion_count, median_generation_tps, "
            "median_prefill_tps) VALUES (?, ?, ?, ?)",
            (
                date_str,
                completion_count,
                statistics.median(gen_tps) if gen_tps else None,
                statistics.median(prefill_tps) if prefill_tps else None,
            ),
        )
