"""
Implements the `codey-metrics` command (docs/telemetry_layer_design.md
§3.5, §7 T4 row). Entirely read-only and offline over
`~/.codeyOS/metrics/` except for `rollup` (writes only `rollups.db`, an
explicitly rebuildable derived cache — see `telemetry/rollup.py`'s module
docstring) and `rotate` (writes only `archive/*.tar.gz` and removes the
now-redundant raw source day directory after verifying the archive — see
`telemetry/rotate.py`'s module docstring). Neither writes a new JSONL
event into the live store; see `rotate.py` for the explicit design-vs-brief
deviation on that point.

**Default output is formatted for a 40-column phone terminal** (§3.5):
two-column key/value, no box drawing, values right-aligned and
abbreviated. `--wide` opts into the terminal's actual detected width;
`--json` emits machine-readable output for every subcommand instead
(`provenance --all --json` emits one JSON array of per-run objects,
matching `export --format json`'s convention for multi-record output;
formerly printed one pretty-printed object per run separated by blank
lines -- neither valid JSON nor valid JSONL, see NEW_ISSUES.md NEW-360).
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import statistics
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from telemetry import rollup as _rollup
from telemetry import rotate as _rotate
from telemetry import schema as _schema

DEFAULT_WIDTH = 40


# ── formatting helpers ──────────────────────────────────────────────────────


def _terminal_width(wide: bool) -> int:
    detected = shutil.get_terminal_size(fallback=(80, 24)).columns
    return detected if wide else min(detected, DEFAULT_WIDTH)


def format_bytes(n: Optional[int]) -> str:
    if n is None:
        return "null"
    value = float(n)
    for unit in ("B", "K", "M", "G", "T"):
        if abs(value) < 1024.0 or unit == "T":
            return f"{int(value)}{unit}" if unit == "B" else f"{value:.1f}{unit}"
        value /= 1024.0
    return f"{value:.1f}P"


def format_tps(x: Optional[float]) -> str:
    return f"{x:.1f}t/s" if isinstance(x, (int, float)) else "null"


def _print_kv(pairs: List[tuple], width: int) -> None:
    for key, value in pairs:
        val_str = str(value)
        key_str = str(key)
        budget = max(width - len(val_str) - 1, 1)
        if len(key_str) > budget:
            key_str = key_str[: max(budget - 1, 0)] + "…"
        line = f"{key_str}".ljust(width - len(val_str)) + val_str
        print(line[:width] if len(line) > width else line)


def _print_null(field: str, reason: str, width: int) -> None:
    """Honest-null display (constraint 5): a null field is always shown
    WITH its reason, never hidden and never left blank."""
    _print_kv([(field, f"null ({reason})")], width)


def _print_wrapped(text: str, width: int) -> None:
    """Word-wraps free text (warnings, notes) to `width` columns instead
    of truncating it — unlike the fixed key/value rows, a safety-relevant
    message (e.g. the NEW-330 duplicate-run_start warning) must never be
    silently cut off by the 40-column default."""
    words = text.split(" ")
    line = ""
    for word in words:
        candidate = f"{line} {word}".strip()
        if len(candidate) > width and line:
            print(line)
            line = word
        else:
            line = candidate
    if line:
        print(line)


# ── shared store scans ──────────────────────────────────────────────────────


def _utc_today() -> str:
    return _rotate.utc_today().strftime("%Y-%m-%d")


def _store_size_bytes(root: Path) -> int:
    total = 0
    for sub in ("events", "archive", "runs"):
        d = root / sub
        if d.is_dir():
            for f in d.rglob("*"):
                if f.is_file():
                    try:
                        total += f.stat().st_size
                    except OSError:
                        continue
    db = root / "rollups.db"
    if db.is_file():
        try:
            total += db.stat().st_size
        except OSError:
            pass
    return total


def _collect_seq_gaps(root: Path, dates: List[str]) -> Dict[str, int]:
    """
    Per-run seq-gap count (design §2.0: "a gap in seq within a run is
    proof of a dropped record"). `seq` is a single per-process monotonic
    counter shared across ALL categories (telemetry/envelope.py's
    `next_seq()`), so gap detection has to look at the union of every
    category file for a run_id, not any one file alone.

    Used both by `status` (reported as the primary drop-count signal,
    since nothing yet emits `meta`/`records_dropped` pre-T8 — see
    `cmd_status`) and by `doctor` (counted as a hard violation).
    """
    seqs_by_run: Dict[str, set] = {}
    for date_str in dates:
        for item in _rollup.iter_records_for_date(root, date_str):
            if item.kind != "record":
                continue
            rec = item.record
            run_id = rec.get("run_id")
            seq = rec.get("seq")
            if not run_id or not isinstance(seq, int):
                continue
            seqs_by_run.setdefault(run_id, set()).add(seq)

    gaps: Dict[str, int] = {}
    for run_id, seqs in seqs_by_run.items():
        if not seqs:
            continue
        expected = set(range(0, max(seqs) + 1))
        missing = expected - seqs
        if missing:
            gaps[run_id] = len(missing)
    return gaps


# ── summary (default subcommand) ────────────────────────────────────────────


def cmd_summary(root: Path, args: argparse.Namespace) -> int:
    today = _utc_today()
    width = _terminal_width(args.wide)

    category_counts: Dict[str, int] = {}
    malformed_count = 0
    gen_tps: List[float] = []
    prefill_tps: List[float] = []
    gate_admit = 0
    gate_deny = 0
    outcome_counts: Dict[str, int] = {}
    latest_interactive: Optional[bool] = None
    latest_interactive_ts: Optional[float] = None

    for item in _rollup.iter_records_for_date(root, today):
        if item.kind == "malformed":
            malformed_count += 1
            continue
        rec = item.record
        category = rec.get("category", "unknown")
        category_counts[category] = category_counts.get(category, 0) + 1
        body = rec.get("body") or {}
        if not isinstance(body, dict):
            continue

        if category == "inference" and rec.get("event_type") == "completion":
            g = body.get("generation_tps")
            if isinstance(g, (int, float)):
                gen_tps.append(float(g))
            p = body.get("prefill_tps")
            if isinstance(p, (int, float)):
                prefill_tps.append(float(p))

        if category == "gate":
            admitted = _rollup.admit_deny_key(body.get("decision") or {})
            if admitted is True:
                gate_admit += 1
            elif admitted is False:
                gate_deny += 1

        if category == "extraction" and rec.get("event_type") == "grounding_check":
            outcome = body.get("outcome")
            if isinstance(outcome, str):
                outcome_counts[outcome] = outcome_counts.get(outcome, 0) + 1

        if category == "cotenancy" and rec.get("event_type") == "interactive_transition":
            ts = rec.get("ts_wall")
            if latest_interactive_ts is None or (isinstance(ts, (int, float)) and ts > latest_interactive_ts):
                latest_interactive_ts = ts
                latest_interactive = body.get("active")

    store_bytes = _store_size_bytes(root)

    if args.json:
        print(
            json.dumps(
                {
                    "date_utc": today,
                    "category_counts": category_counts,
                    "malformed_lines": malformed_count,
                    "median_generation_tps": statistics.median(gen_tps) if gen_tps else None,
                    "median_prefill_tps": statistics.median(prefill_tps) if prefill_tps else None,
                    "gate_admitted": gate_admit,
                    "gate_denied": gate_deny,
                    "grounding_outcomes": outcome_counts,
                    "interactive": latest_interactive,
                    "store_size_bytes": store_bytes,
                },
                indent=2,
            )
        )
        return 0

    print(f"Codey-OS metrics {today} (UTC)"[:width])
    pairs: List[tuple] = []
    if not category_counts:
        pairs.append(("no records today", ""))
    for category in sorted(category_counts):
        pairs.append((category, category_counts[category]))
    if malformed_count:
        pairs.append(("malformed lines", malformed_count))
    pairs.append(("gen tps (median)", format_tps(statistics.median(gen_tps) if gen_tps else None)))
    pairs.append(("prefill tps (median)", format_tps(statistics.median(prefill_tps) if prefill_tps else None)))
    pairs.append(("gate admit/deny", f"{gate_admit}/{gate_deny}"))
    if outcome_counts:
        for outcome in sorted(outcome_counts):
            pairs.append((f"ground:{outcome}", outcome_counts[outcome]))
    pairs.append(("interactive", "unknown" if latest_interactive is None else str(latest_interactive)))
    pairs.append(("store size", format_bytes(store_bytes)))
    _print_kv(pairs, width)
    return 0


# ── export ───────────────────────────────────────────────────────────────


def cmd_export(root: Path, args: argparse.Namespace) -> int:
    start = args.date_from
    end = args.date_to or args.date_from
    malformed = 0
    records: List[Dict[str, Any]] = []
    for item in _rollup.iter_records_for_range(root, start, end, category=args.category):
        if item.kind == "malformed":
            malformed += 1
            continue
        records.append(item.record)

    fmt = args.format
    if fmt == "jsonl":
        for rec in records:
            sys.stdout.write(json.dumps(rec, separators=(",", ":"), default=str) + "\n")
    elif fmt == "json":
        json.dump(records, sys.stdout, indent=2, default=str)
        sys.stdout.write("\n")
    elif fmt == "csv":
        fieldnames = _csv_fieldnames(records)
        writer = csv.DictWriter(sys.stdout, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for rec in records:
            writer.writerow(_flatten_for_csv(rec))
    else:
        print(f"unknown --format {fmt!r}", file=sys.stderr)
        return 2

    if malformed:
        print(f"warning: skipped {malformed} malformed line(s) in range", file=sys.stderr)
    return 0


def _flatten_for_csv(rec: Dict[str, Any]) -> Dict[str, Any]:
    flat: Dict[str, Any] = {}
    for key, value in rec.items():
        if key == "body" and isinstance(value, dict):
            for bkey, bval in value.items():
                flat[f"body.{bkey}"] = json.dumps(bval, default=str) if isinstance(bval, (dict, list)) else bval
        elif key == "nulls" and isinstance(value, dict):
            flat["nulls"] = json.dumps(value)
        else:
            flat[key] = value
    return flat


def _csv_fieldnames(records: List[Dict[str, Any]]) -> List[str]:
    fields: List[str] = []
    seen = set()
    for rec in records:
        for key in _flatten_for_csv(rec):
            if key not in seen:
                seen.add(key)
                fields.append(key)
    return fields


# ── provenance ───────────────────────────────────────────────────────────


def _load_run_json(root: Path, run_id: str) -> Optional[Dict[str, Any]]:
    path = root / "runs" / f"{run_id}.json"
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _find_provenance_records(root: Path, run_id: str) -> List[Dict[str, Any]]:
    """
    `runs/<run_id>.json` only ever holds the FIRST `run_start`
    (`store.write_run_provenance()` refuses to overwrite — see
    telemetry/store.py) so it can never by itself reveal a duplicate
    (NEW-330). This scans the `provenance` category across the whole
    store for every record sharing this run_id — `run_start`,
    `run_start_amended`, and `run_end` alike — which is the only way to
    see a NEW-330 duplicate or merge in an amendment.
    """
    matches: List[Dict[str, Any]] = []
    for date_str in _rollup.get_all_dates(root):
        for item in _rollup.iter_records_for_date(root, date_str, category="provenance"):
            if item.kind != "record":
                continue
            if item.record.get("run_id") == run_id:
                matches.append(item.record)
    matches.sort(key=lambda r: (r.get("seq") if isinstance(r.get("seq"), int) else -1))
    return matches


def _latest_run_id(root: Path) -> Optional[str]:
    runs_dir = root / "runs"
    best_run_id = None
    best_ts = None
    if runs_dir.is_dir():
        for path in runs_dir.glob("*.json"):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, json.JSONDecodeError):
                continue
            body = data.get("body", data)  # runs/<id>.json is the full envelope record
            ts = body.get("started_ts_wall") if isinstance(body, dict) else None
            if isinstance(ts, (int, float)) and (best_ts is None or ts > best_ts):
                best_ts = ts
                best_run_id = data.get("run_id") or path.stem
    return best_run_id


def _print_run(
    root: Path,
    run_id: str,
    width: int,
    as_json: bool,
    collect: Optional[List[Dict[str, Any]]] = None,
) -> int:
    base = _load_run_json(root, run_id)
    stream_records = _find_provenance_records(root, run_id)
    run_starts = [r for r in stream_records if r.get("event_type") == "run_start"]
    amendments = [r for r in stream_records if r.get("event_type") == "run_start_amended"]

    if base is None and not stream_records:
        print(f"no provenance found for run_id={run_id}", file=sys.stderr)
        return 1

    record = base if base is not None else run_starts[0] if run_starts else stream_records[0]
    body = dict(record.get("body", {}))
    nulls = dict(record.get("nulls", {}))

    # NEW-330 decision (see NEW_ISSUES.md): RestoriconAPIServer.start()'s
    # missing re-entrancy guard can append a second `run_start` under the
    # SAME run_id to the JSONL stream, even though `runs/<id>.json` (the
    # file `base` came from) only ever holds the first one because
    # write_run_provenance() refuses to overwrite. Decision: never
    # silently collapse the duplicate — display the first run_start as
    # the record (matching what runs/<id>.json already shows) and
    # explicitly call out any additional ones, so a reader can tell "one
    # real process start" from "the API server's start() was re-entered".
    duplicate_note = None
    if len(run_starts) > 1:
        duplicate_note = (
            f"{len(run_starts) - 1} additional run_start record(s) for this run_id "
            f"(duplicate emission, NEW-330) — showing the first"
        )

    # run_start_amended merge (recorders.record_run_start_amended's own
    # docstring: "A later codey-metrics provenance ... is expected to
    # merge a run's run_start + any run_start_amended records"). Iterate
    # ALL amendments in `seq` order (T9): `models` (provenance.py's
    # schedule_cold_model_digests()) and `llama_server_argv`
    # (core/loader_v2.py's genuine-spawn path) can land as two SEPARATE
    # amendment records for the same run_id, so only consulting the last
    # amendment's body would silently drop whichever field wasn't in it.
    # Each field's own last writer wins independently. Also drop any
    # matching `nulls["body.<field>"]` reason (e.g. build_run_start_nulls()'s
    # "call_site_not_yet_tagged" for `llama_server_argv`) once an amendment
    # actually populates that field — leaving it would print a real value
    # next to a null-reason claiming it was never observed, a contradiction
    # nothing else here (schema.validate() included -- this merged view
    # isn't a record) would catch.
    for amendment in amendments:
        amended_body = amendment.get("body", {})
        for field in ("models", "llama_server_argv"):
            if amended_body.get(field) is not None:
                body[field] = amended_body[field]
                nulls.pop(f"body.{field}", None)

    if as_json:
        out = {"run_id": run_id, "body": body, "nulls": nulls}
        if duplicate_note:
            out["_duplicate_run_start_warning"] = duplicate_note
        if amendments:
            out["_amended_by"] = len(amendments)
        if collect is not None:
            collect.append(out)
        else:
            print(json.dumps(out, indent=2, default=str))
        return 0

    print(f"run {run_id}"[:width])
    if duplicate_note:
        _print_wrapped("WARNING: " + duplicate_note, width)
    if amendments:
        _print_wrapped(f"(models amended by {len(amendments)} background hash record(s))", width)
    pairs: List[tuple] = []
    for key in sorted(body):
        value = body[key]
        reason = nulls.get(f"body.{key}")
        if value is None:
            pairs.append((key, f"null ({reason})" if reason else "null (no reason — schema violation)"))
        elif isinstance(value, (dict, list)):
            pairs.append((key, json.dumps(value, default=str)[: max(width - len(key) - 1, 4)]))
        else:
            pairs.append((key, value))
    _print_kv(pairs, width)
    return 0


def cmd_provenance(root: Path, args: argparse.Namespace) -> int:
    width = _terminal_width(args.wide)
    if args.all:
        runs_dir = root / "runs"
        run_ids = sorted(p.stem for p in runs_dir.glob("*.json")) if runs_dir.is_dir() else []
        if not run_ids:
            print("no runs found", file=sys.stderr)
            return 1
        rc = 0
        if args.json:
            # Collect every run's object into one list and emit a single
            # JSON array (matching cmd_export's --format json convention
            # for multi-record output) instead of printing one JSON
            # object per run back-to-back, which is neither valid JSON
            # nor valid JSONL (NEW-360).
            collected: List[Dict[str, Any]] = []
            for run_id in run_ids:
                this_rc = _print_run(root, run_id, width, args.json, collect=collected)
                if this_rc:
                    rc = this_rc
            json.dump(collected, sys.stdout, indent=2, default=str)
            sys.stdout.write("\n")
            return rc
        for run_id in run_ids:
            # Unconditionally process every run — an earlier `or` short-
            # circuit here made one no-data run (nonzero rc) stop all
            # later runs from being printed even though they had real
            # data. Track the worst-seen rc instead so the overall exit
            # code still reflects "any run had no data" without skipping
            # anyone.
            this_rc = _print_run(root, run_id, width, args.json)
            if this_rc:
                rc = this_rc
            print("")
        return rc

    run_id = args.run
    if args.latest or not run_id:
        run_id = _latest_run_id(root)
        if run_id is None:
            print("no runs found", file=sys.stderr)
            return 1
    return _print_run(root, run_id, width, args.json)


# ── status ───────────────────────────────────────────────────────────────


def cmd_status(root: Path, args: argparse.Namespace) -> int:
    width = _terminal_width(args.wide)
    today = _utc_today()
    yesterday_dt = _rotate.utc_today()
    yesterday = (yesterday_dt - timedelta(days=1)).strftime("%Y-%m-%d")

    dropped_from_meta: Dict[str, int] = {}
    for date_str in (yesterday, today):
        for item in _rollup.iter_records_for_date(root, date_str, category="meta"):
            if item.kind != "record":
                continue
            rec = item.record
            if rec.get("event_type") != "records_dropped":
                continue
            run_id = rec.get("run_id")
            total = (rec.get("body") or {}).get("dropped_total")
            if run_id and isinstance(total, int):
                # cumulative per run; keep the max seen (later record = higher cumulative)
                dropped_from_meta[run_id] = max(dropped_from_meta.get(run_id, 0), total)
    known_dropped_total = sum(dropped_from_meta.values())

    seq_gaps = _collect_seq_gaps(root, [yesterday, today])
    seq_gap_total = sum(seq_gaps.values())

    emitters_seen: Dict[str, float] = {}
    for date_str in (yesterday, today):
        for item in _rollup.iter_records_for_date(root, date_str):
            if item.kind != "record":
                continue
            rec = item.record
            emitter = rec.get("emitter")
            ts = rec.get("ts_wall")
            if emitter and isinstance(ts, (int, float)):
                if ts > emitters_seen.get(emitter, -1):
                    emitters_seen[emitter] = ts

    store_bytes = _store_size_bytes(root)

    payload = {
        "schema_version": _schema.SCHEMA_VERSION,
        "schema_sha256_12": _schema.SCHEMA_SHA256_12,
        "dropped_total_from_meta_records": known_dropped_total,
        "dropped_total_meta_note": (
            "0 records_dropped meta events observed in the last 2 UTC days — this is "
            "NOT a confirmed zero-drop guarantee; no call site emits meta/records_dropped "
            "until a later sub-task wires store.Store.stats() into it (T8). See seq-gap "
            "count below for an independent, already-available drop signal."
            if known_dropped_total == 0
            else None
        ),
        "seq_gap_suspected_drops": seq_gap_total,
        "seq_gap_by_run": seq_gaps,
        "buffer_high_water": None,
        "buffer_high_water_note": (
            "not available — Store.stats() is in-process memory only and this CLI runs "
            "as a separate process; exposing it requires the meta/emit_cost record a "
            "future sub-task emits"
        ),
        "bytes_written_total": store_bytes,
        "emitters_last_write_ts": emitters_seen,
    }

    if args.json:
        print(json.dumps(payload, indent=2, default=str))
        return 0

    print("codey-metrics status"[:width])
    pairs = [
        ("schema version", _schema.SCHEMA_VERSION),
        ("schema hash", _schema.SCHEMA_SHA256_12),
        ("dropped (meta evts)", known_dropped_total),
        ("dropped (seq gaps)", seq_gap_total),
        ("buffer high-water", "n/a (in-proc)"),
        ("bytes written", format_bytes(store_bytes)),
    ]
    _print_kv(pairs, width)
    if payload["dropped_total_meta_note"]:
        print("note: 0 from meta != confirmed zero drops"[:width])
    for emitter, ts in sorted(emitters_seen.items()):
        _print_kv([(emitter, f"{ts:.0f}")], width)
    if not emitters_seen:
        print("no emitter activity in last 2 UTC days"[:width])
    return 0


# ── doctor ───────────────────────────────────────────────────────────────


def cmd_doctor(root: Path, args: argparse.Namespace) -> int:
    width = _terminal_width(args.wide)
    dates = _rollup.get_all_dates(root)

    malformed_count = 0
    null_violations: List[str] = []
    schema_mismatch: Dict[str, int] = {}
    run_ids_with_events: set = set()
    run_ids_with_run_start: set = set()
    run_ids_with_writer_stopped: set = set()
    run_start_counts: Dict[str, int] = {}

    for date_str in dates:
        for item in _rollup.iter_records_for_date(root, date_str):
            if item.kind == "malformed":
                malformed_count += 1
                continue
            rec = item.record
            run_id = rec.get("run_id")
            if run_id:
                run_ids_with_events.add(run_id)
            violations = _schema.validate(rec)
            if violations:
                null_violations.extend(f"{run_id or '?'}: {v}" for v in violations)
            rec_hash = rec.get("schema_sha256")
            if rec_hash and rec_hash != _schema.SCHEMA_SHA256_12:
                schema_mismatch[rec_hash] = schema_mismatch.get(rec_hash, 0) + 1
            if rec.get("category") == "provenance" and rec.get("event_type") == "run_start" and run_id:
                run_ids_with_run_start.add(run_id)
                run_start_counts[run_id] = run_start_counts.get(run_id, 0) + 1
            if rec.get("category") == "meta" and rec.get("event_type") == "writer_stopped" and run_id:
                run_ids_with_writer_stopped.add(run_id)

    seq_gaps = _collect_seq_gaps(root, dates)
    seq_gap_total = sum(seq_gaps.values())

    orphan_runs = sorted(run_ids_with_events - run_ids_with_run_start)
    no_clean_shutdown = sorted(run_ids_with_run_start - run_ids_with_writer_stopped)
    # NEW-330: a run_id with >1 run_start records. Judgment call (flagged,
    # not silently defaulted — see cli.py module note / handoff): this is
    # reported as a WARNING, not counted in hard_violation_count. Reasoning:
    # NEW_ISSUES.md's own fix-direction note says doctor should "treat a
    # second run_start ... as an expected-but-flagged case", and every
    # `no_clean_shutdown` run is CURRENTLY EXPECTED (nothing emits
    # writer_stopped pre-T8) — making both of these hard failures would make
    # `doctor` report a nonzero exit on essentially every real dataset today,
    # which defeats its purpose as a signal of genuine integrity problems.
    duplicate_run_start = sorted(rid for rid, count in run_start_counts.items() if count > 1)

    hard_violation_count = (
        malformed_count + len(null_violations) + sum(schema_mismatch.values())
        + seq_gap_total + len(orphan_runs)
    )

    payload = {
        "malformed_lines": malformed_count,
        "honest_null_violations": null_violations,
        "schema_hash_mismatches": schema_mismatch,
        "seq_gap_suspected_drops": seq_gap_total,
        "seq_gap_by_run": seq_gaps,
        "orphan_runs_no_run_start": orphan_runs,
        "runs_no_clean_shutdown": no_clean_shutdown,
        "runs_no_clean_shutdown_note": (
            "informational, not counted as a hard violation — nothing emits "
            "meta/writer_stopped until a later sub-task wires the daemon shutdown "
            "path (T8); every run is expected to show up here until then"
        ),
        "duplicate_run_start_runs": duplicate_run_start,
        "duplicate_run_start_note": "NEW-330 — flagged, not a hard violation" if duplicate_run_start else None,
        "known_limitation_new_327": (
            "schema.validate()'s honest-null check does not walk nested arrays "
            "(e.g. body.models[i].sha256=None on a cold model-digest cache is not "
            "flagged here) — known gap, not counted"
        ),
        "hard_violation_count": hard_violation_count,
    }

    if args.json:
        print(json.dumps(payload, indent=2, default=str))
    else:
        print("codey-metrics doctor"[:width])
        _print_kv(
            [
                ("malformed lines", malformed_count),
                ("null violations", len(null_violations)),
                ("hash mismatches", sum(schema_mismatch.values())),
                ("seq-gap drops", seq_gap_total),
                ("orphan runs", len(orphan_runs)),
                ("no clean shutdown", len(no_clean_shutdown)),
                ("dup run_start", len(duplicate_run_start)),
            ],
            width,
        )
        print(f"known gap: NEW-327 (nested nulls)"[:width])
        print(f"hard violations: {hard_violation_count}"[:width])

    return 0 if hard_violation_count == 0 else 1


# ── rollup / rotate / schema ────────────────────────────────────────────


def cmd_rollup(root: Path, args: argparse.Namespace) -> int:
    with _rotate.acquire_rotate_lock(root) as acquired:
        if not acquired:
            print("rollup: .rotate.lock is held by another process; not blocking, exiting", file=sys.stderr)
            return 2
        if args.rebuild:
            dates = _rollup.rebuild_all(root)
        else:
            target = args.date or _utc_today()
            _rollup.rebuild_dates(root, [target])
            dates = [target]
    if args.json:
        print(json.dumps({"rebuilt_dates": dates}, indent=2))
    else:
        print(f"rebuilt {len(dates)} date(s)")
    return 0


def cmd_rotate(root: Path, args: argparse.Namespace) -> int:
    with _rotate.acquire_rotate_lock(root) as acquired:
        if not acquired:
            print("rotate: .rotate.lock is held by another process; not blocking, exiting", file=sys.stderr)
            return 2
        results = _rotate.rotate_all(root, dry_run=args.dry_run)

    if args.json:
        print(
            json.dumps(
                [
                    {
                        "date": r.date_str,
                        "action": r.action,
                        "source_bytes": r.source_bytes,
                        "archive_bytes": r.archive_bytes,
                        "source_record_count": r.source_record_count,
                        "archive_record_count": r.archive_record_count,
                        "detail": r.detail,
                    }
                    for r in results
                ],
                indent=2,
            )
        )
        return 0

    if not results:
        print("nothing eligible for rotation")
        return 0
    for r in results:
        print(f"{r.date_str}: {r.action} ({format_bytes(r.source_bytes)} -> {format_bytes(r.archive_bytes)})" + (f" — {r.detail}" if r.detail else ""))
    failed = [r for r in results if r.action == "failed"]
    return 1 if failed else 0


def cmd_schema(root: Path, args: argparse.Namespace) -> int:
    if not args.verify:
        print(f"schema_version={_schema.SCHEMA_VERSION} sha256_12={_schema.SCHEMA_SHA256_12}")
        return 0

    aigentik_path = Path.home() / "Codey-Aigentik" / "telemetry" / "schema" / "v1.json"
    if not aigentik_path.is_file():
        print(f"Codey-OS: {_schema.SCHEMA_SHA256_12}")
        print("Codey-Aigentik: not present on this device")
        return 0

    import hashlib

    aigentik_bytes = aigentik_path.read_bytes()
    aigentik_hash = hashlib.sha256(aigentik_bytes).hexdigest()[:12]
    print(f"Codey-OS:       {_schema.SCHEMA_SHA256_12}")
    print(f"Codey-Aigentik: {aigentik_hash}")
    if aigentik_hash == _schema.SCHEMA_SHA256_12:
        print("MATCH")
        return 0
    print("MISMATCH — schema drift between repos")
    return 1


# ── argument parsing / entry point ──────────────────────────────────────


KNOWN_COMMANDS = (
    "summary", "export", "provenance", "status", "doctor", "rollup", "rotate", "schema",
)


def _build_parser() -> argparse.ArgumentParser:
    # `--wide`/`--json`/`--root` are defined ONLY on the subparsers (via
    # `parents=[common]` below), never also on the top-level parser.
    # argparse's default-application rule for `parse_args(args, namespace)`
    # sets an action's default whenever the namespace doesn't already carry
    # a non-None value for that dest from an EARLIER parse of the same
    # option string in a different parser object — defining the same dest
    # in both the top-level parser and every subparser silently overwrote
    # an already-parsed `--root` with the subparser's own `None` default
    # (caught empirically: `codey-metrics --root X summary` produced
    # `args.root is None`). Requiring these flags to come after the
    # subcommand (`codey-metrics summary --root X`) sidesteps the whole
    # class of bug. `main()` also accepts them before an omitted/implicit
    # "summary" by pre-pending "summary" to argv when the first token isn't
    # a known subcommand — see `main()`.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--wide", action="store_true", help="use full terminal width instead of 40 columns")
    common.add_argument("--json", action="store_true", help="machine-readable JSON output")
    common.add_argument("--root", type=str, default=None, help=argparse.SUPPRESS)  # test-only override

    parser = argparse.ArgumentParser(prog="codey-metrics")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("summary", parents=[common], help="live summary (default)")

    p_export = sub.add_parser("export", parents=[common], help="export a date range")
    p_export.add_argument("--from", dest="date_from", required=True)
    p_export.add_argument("--to", dest="date_to", default=None)
    p_export.add_argument("--category", default=None)
    p_export.add_argument("--format", choices=["csv", "json", "jsonl"], default="jsonl")

    p_prov = sub.add_parser(
        "provenance",
        parents=[common],
        help="show run provenance ('--all --json' emits one JSON array of per-run objects)",
    )
    group = p_prov.add_mutually_exclusive_group()
    group.add_argument("--run", default=None)
    group.add_argument("--latest", action="store_true")
    group.add_argument("--all", action="store_true")

    sub.add_parser("status", parents=[common], help="schema version, drop counts, silent emitters")
    sub.add_parser("doctor", parents=[common], help="integrity checks; exit non-zero on violations")

    p_rollup = sub.add_parser("rollup", parents=[common], help="build/rebuild rollups.db")
    g2 = p_rollup.add_mutually_exclusive_group()
    g2.add_argument("--date", default=None)
    g2.add_argument("--rebuild", action="store_true")

    p_rotate = sub.add_parser("rotate", parents=[common], help="archive day directories older than 7 days")
    p_rotate.add_argument("--dry-run", action="store_true")

    p_schema = sub.add_parser("schema", parents=[common], help="print/verify schema version+hash")
    p_schema.add_argument("--verify", action="store_true")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    if argv and argv[0] in ("--help", "-h"):
        # `--help`/`-h` as the very first token must reach the TOP-LEVEL
        # parser's help (the actual subcommand list), not get silently
        # rewritten into "summary --help" by the prepend below — that
        # rewrite made the top-level `codey-metrics --help` unreachable,
        # since a user would only ever see "summary"'s own help text.
        pass
    elif not argv or argv[0] not in KNOWN_COMMANDS:
        # No subcommand given (or the first token is a flag, e.g. a bare
        # `--json`) -> default subcommand is "summary" (design §3.5:
        # "codey-metrics (no args) -> summary"). Prepending here, rather
        # than making `command` default to "summary" post-parse, is what
        # lets flags like `--root`/`--json` still reach the "summary"
        # subparser that actually defines them.
        argv = ["summary"] + argv
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.root:
        root = Path(args.root)
    else:
        from utils.config import METRICS_DIR

        root = METRICS_DIR

    # args.command is never None here: main() prepends a known subcommand
    # token (defaulting to "summary") before parsing whenever the first
    # token isn't already one -- except --help/-h as the first token,
    # which is left untouched so it reaches the top-level parser's real
    # subcommand list; that path exits via argparse's own sys.exit()
    # before this line is ever reached, so the invariant still holds.
    command = args.command
    handlers = {
        "summary": cmd_summary,
        "export": cmd_export,
        "provenance": cmd_provenance,
        "status": cmd_status,
        "doctor": cmd_doctor,
        "rollup": cmd_rollup,
        "rotate": cmd_rotate,
        "schema": cmd_schema,
    }
    handler = handlers.get(command)
    if handler is None:
        parser.print_help()
        return 2
    try:
        return handler(root, args)
    except Exception as exc:  # pragma: no cover - last-resort guard
        # This CLI reads a live, possibly-being-written-to store (constraint
        # 1 of the T4 brief: "never crash"). Every read path above already
        # tolerates malformed lines/records individually; this is a final
        # backstop against anything unanticipated (e.g. an unreadable
        # directory due to a permission change mid-run) so the tool always
        # reports a clean failure instead of an unhandled traceback.
        print(f"codey-metrics: unexpected error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
