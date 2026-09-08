"""
T4: compresses day directories under ``events/<YYYY-MM-DD>/`` older than the
retention threshold into verified ``archive/<YYYY-MM>/<YYYY-MM-DD>.tar.gz``
files (docs/telemetry_layer_design.md §6.3).

**Contains no deletion code path for archives, ever** (§6.3 / §8 item 8,
confirmed). The one thing this module *does* remove is the now-redundant
*raw source day directory* after its archive has been written, fdatasync'd,
and re-read/line-counted successfully — that is the literal
"raw kept 7 days, then rotated to a permanent archive" policy, not a
deletion of evidence: the archive is the same bytes, just compressed. If the
verification read fails for any reason, the source directory is left in
place untouched and the failure is reported; nothing is ever removed on an
unverified archive.

**Deliberate deviation from design §6.3's literal wording:** the design
text says rotation emits a ``meta``/``rotation`` JSONL record. This module
does NOT do that. Rotation is a periodic offline CLI operation invoked as a
fresh process with its own would-be ``run_id`` and no ``run_start`` for that
process — emitting a JSONL event under that orphan run_id would itself be
flagged by `codey-metrics doctor`'s "orphan runs with no run_start" check on
every single rotate invocation, which is a worse outcome than not recording
the rotation as an event. `rotate_all()` instead returns a structured
`RotationResult` list that `codey-metrics rotate` prints to stdout — this is
flagged in the T4 handoff as an explicit design-vs-brief conflict resolved
in the brief's favor (rule 8: "flag it, don't silently pick a behavior"; T4
brief constraint 2: "never write new JSONL events").

**Never touches the current or previous UTC day's directory.** Two
independent guards enforce this: (1) `RAW_RETENTION_DAYS` (7) already keeps
a wide berth, and (2) `eligible_dates()` explicitly excludes today and
yesterday regardless of the retention window, so a misconfigured retention
value can never make rotation race a live writer. `store.py`'s own
`_date_for_record()` computes the day directory from `ts_wall` in UTC
(`datetime.fromtimestamp(ts, tz=timezone.utc)`) with a malformed-input
fallback of "now" — meaning every write this process makes lands in
*today's* UTC directory, never an old one — so this module uses UTC dates
throughout for the same reason: comparing a UTC-partitioned store against a
locally-computed "today" would open an hours-wide window (worse on this
device's US timezone) where rotation could touch a directory the store still
considers "today".
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import shutil
import tarfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

RAW_RETENTION_DAYS = 7
ROTATE_LOCK_FILE = ".rotate.lock"


def utc_today() -> date:
    return datetime.now(tz=timezone.utc).date()


@contextlib.contextmanager
def acquire_rotate_lock(root: Path, shared: bool = False):
    """
    Non-blocking flock on ``<root>/.rotate.lock`` (design §3.5: "rollup and
    rotate take ~/.codeyOS/metrics/.rotate.lock (flock, non-blocking, exits
    with a clear message if held)"). Shared between `rotate.py` and
    `rollup.py` so the two can never run concurrently against the same
    store and race each other's reads of a day directory mid-archive.

    Yields True if the lock was acquired, False if it is already held
    elsewhere. Never raises — a lock-file open/flock failure (e.g. a
    read-only filesystem) is treated the same as "lock held", since either
    way it is not safe to proceed.

    NEW-336: pass ``shared=True`` for a read-only caller (e.g. a CLI
    summary/export/status/doctor/provenance command) to take a shared
    (LOCK_SH) lock instead of the default exclusive (LOCK_EX) lock used by
    `rotate`/`rollup` — this lets concurrent reads proceed against each
    other while still being blocked by (and blocking) an in-progress
    rotate/rollup.
    """
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    lock_path = root / ROTATE_LOCK_FILE
    fh = None
    try:
        fh = open(lock_path, "a+")
        try:
            flags = (fcntl.LOCK_SH if shared else fcntl.LOCK_EX) | fcntl.LOCK_NB
            fcntl.flock(fh.fileno(), flags)
        except OSError:
            yield False
            return
        try:
            yield True
        finally:
            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
    except OSError:
        yield False
    finally:
        if fh is not None:
            fh.close()


def _events_dir(root: Path) -> Path:
    return Path(root) / "events"


def _archive_path(root: Path, date_str: str) -> Path:
    month = date_str[:7]  # "YYYY-MM"
    return Path(root) / "archive" / month / f"{date_str}.tar.gz"


def list_event_day_dirs(root: Path) -> List[str]:
    """All ``YYYY-MM-DD`` directory names currently present under
    ``events/``, sorted. Directories are named by the store's own UTC
    date-string convention (`store._date_for_record`), so no parsing beyond
    a lexical sort is needed to order them chronologically."""
    events_dir = _events_dir(root)
    if not events_dir.is_dir():
        return []
    names = []
    for child in events_dir.iterdir():
        if child.is_dir() and _looks_like_date(child.name):
            names.append(child.name)
    return sorted(names)


def _looks_like_date(name: str) -> bool:
    try:
        datetime.strptime(name, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def eligible_dates(
    root: Path,
    retention_days: int = RAW_RETENTION_DAYS,
    today: Optional[date] = None,
) -> List[str]:
    """
    Day directories eligible for rotation: present on disk, strictly older
    than `retention_days`, AND never today or yesterday (belt-and-braces —
    see module docstring). `today` is injectable for tests; production
    callers get `utc_today()`.
    """
    today = today or utc_today()
    cutoff = today - timedelta(days=retention_days)
    yesterday = today - timedelta(days=1)
    out = []
    for name in list_event_day_dirs(root):
        d = datetime.strptime(name, "%Y-%m-%d").date()
        if d >= today or d == yesterday:
            continue
        if d < cutoff:
            out.append(name)
    return out


def _count_lines_in_dir(dir_path: Path) -> int:
    total = 0
    for f in sorted(dir_path.glob("*.jsonl")):
        try:
            with open(f, "rb") as fh:
                total += sum(1 for line in fh if line.strip())
        except OSError:
            # Unreadable member file — counted as 0 lines from it; the
            # caller compares this total against the archive's own count,
            # so an unreadable source file surfaces as a verification
            # mismatch rather than a silent pass.
            continue
    return total


def _count_lines_in_tar(tar_path: Path) -> int:
    total = 0
    with tarfile.open(tar_path, mode="r:gz") as tf:
        for member in tf.getmembers():
            if not member.isfile():
                continue
            fh = tf.extractfile(member)
            if fh is None:
                continue
            total += sum(1 for line in fh if line.strip())
    return total


def _collect_event_ids_in_dir(dir_path: Path) -> set:
    """
    `event_id` (32 hex, `uuid4().hex` per record — envelope.py) is the
    per-record idempotency key the design defines for export/dedupe; it
    doubles here as a strong content fingerprint for the archive-exists
    crash-recovery branch, which a bare line count cannot provide (a line
    count cannot distinguish "same bytes, rmtree just didn't run yet" from
    "the source directory picked up different records after the archive
    was written" — the two crash states rotate_day must never treat the
    same way). A malformed/unparseable line contributes nothing to the
    set rather than raising — an unreadable line is exactly the kind of
    thing that SHOULD make the sets fail to match and trigger a rebuild.
    """
    ids: set = set()
    for f in sorted(dir_path.glob("*.jsonl")):
        try:
            with open(f, "r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    eid = rec.get("event_id") if isinstance(rec, dict) else None
                    if eid:
                        ids.add(eid)
        except OSError:
            continue
    return ids


def _collect_event_ids_in_tar(tar_path: Path) -> set:
    ids: set = set()
    with tarfile.open(tar_path, mode="r:gz") as tf:
        for member in tf.getmembers():
            if not member.isfile():
                continue
            fh = tf.extractfile(member)
            if fh is None:
                continue
            for raw in fh:
                line = raw.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                eid = rec.get("event_id") if isinstance(rec, dict) else None
                if eid:
                    ids.add(eid)
    return ids


def _archive_matches_source(archive_path: Path, source_dir: Path) -> bool:
    """True only if the archive's records are EXACTLY the source
    directory's records (by `event_id` set), including the case where
    both are empty. Used only in the "archive already exists, source
    also still exists" crash-recovery branch of `rotate_day()` to decide
    whether the existing archive can be trusted as-is or must be
    rebuilt."""
    return _collect_event_ids_in_tar(archive_path) == _collect_event_ids_in_dir(source_dir)


def _dir_size_bytes(dir_path: Path) -> int:
    total = 0
    for f in dir_path.glob("*.jsonl"):
        try:
            total += f.stat().st_size
        except OSError:
            continue
    return total


@dataclass
class RotationResult:
    date_str: str
    action: str  # "archived" | "verified_existing" | "skipped_no_source" | "failed" | "dry_run"
    source_bytes: int = 0
    archive_bytes: int = 0
    source_record_count: int = 0
    archive_record_count: int = 0
    detail: str = ""


def _write_archive(source_dir: Path, archive_final: Path) -> None:
    """
    Atomic write: build the full tar.gz at a `.tmp` sibling, fdatasync it
    while still open, then `Path.replace()` into the final name — the same
    tmp-file-then-atomic-rename idiom already used by
    `telemetry/store.py:write_run_provenance()` and
    `telemetry/provenance.py:_write_digest_cache_entry()`, so a crash
    mid-write can never leave a half-written ``.tar.gz`` at the real path
    for a later run to mistake for a valid archive.
    """
    archive_final.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = archive_final.with_name(archive_final.name + ".tmp")
    with open(tmp_path, "wb") as raw_f:
        with tarfile.open(fileobj=raw_f, mode="w:gz") as tf:
            for f in sorted(source_dir.glob("*.jsonl")):
                tf.add(f, arcname=f.name)
        raw_f.flush()
        os.fdatasync(raw_f.fileno())
    tmp_path.replace(archive_final)


def rotate_day(root: Path, date_str: str, dry_run: bool = False) -> RotationResult:
    """
    Rotate one day directory. Idempotent and safe to call twice in a row,
    including the crash-mid-rotation case where a previous run wrote a
    (possibly valid) archive but was killed before removing the source:

      - archive absent, source present  -> build archive, verify, remove source
      - archive present, source present -> verify the EXISTING archive first
                                            (never blindly re-archive over a
                                            possibly-good file); only
                                            rebuild if verification fails
      - archive present, source absent  -> already rotated cleanly; no-op
      - archive absent, source absent   -> nothing to do for this date
    """
    root = Path(root)
    source_dir = _events_dir(root) / date_str
    archive_final = _archive_path(root, date_str)

    source_exists = source_dir.is_dir()
    archive_exists = archive_final.is_file()

    if not source_exists and not archive_exists:
        return RotationResult(date_str=date_str, action="skipped_no_source")

    if not source_exists and archive_exists:
        return RotationResult(
            date_str=date_str,
            action="verified_existing",
            archive_bytes=archive_final.stat().st_size,
            detail="already rotated; no source directory remains",
        )

    source_record_count = _count_lines_in_dir(source_dir)
    source_bytes = _dir_size_bytes(source_dir)

    if dry_run:
        return RotationResult(
            date_str=date_str,
            action="dry_run",
            source_bytes=source_bytes,
            source_record_count=source_record_count,
            detail="would archive and remove source" if not archive_exists
            else "would verify existing archive and remove source",
        )

    try:
        rebuilt = False
        if archive_exists:
            # Crash-mid-rotation recovery: verify what's already there
            # before deciding whether to rebuild it. A bare line-count
            # comparison cannot distinguish "same bytes, rmtree just
            # didn't run yet" from "the source directory picked up
            # DIFFERENT records that happen to be the same count" — an
            # exact event_id-set match is the actual guarantee needed
            # before trusting an existing archive over rebuilding it.
            try:
                archive_ok = _archive_matches_source(archive_final, source_dir)
            except (tarfile.TarError, OSError):
                archive_ok = False
            if not archive_ok:
                _write_archive(source_dir, archive_final)
                rebuilt = True
        else:
            _write_archive(source_dir, archive_final)
            rebuilt = True

        archive_record_count = _count_lines_in_tar(archive_final)

        if archive_record_count != source_record_count:
            return RotationResult(
                date_str=date_str,
                action="failed",
                source_bytes=source_bytes,
                archive_bytes=archive_final.stat().st_size if archive_final.is_file() else 0,
                source_record_count=source_record_count,
                archive_record_count=archive_record_count,
                detail=(
                    f"verification mismatch: source had {source_record_count} records, "
                    f"archive has {archive_record_count} — source left in place"
                ),
            )

        archive_bytes = archive_final.stat().st_size
        shutil.rmtree(source_dir)
        return RotationResult(
            date_str=date_str,
            # "archived" only when this call actually wrote the archive;
            # when an existing archive already matched the source exactly
            # (event_id-set equal) and nothing was rewritten, that is
            # honestly "verified_existing" — the source was still removed,
            # but no compression work happened.
            action="archived" if rebuilt else "verified_existing",
            source_bytes=source_bytes,
            archive_bytes=archive_bytes,
            source_record_count=source_record_count,
            archive_record_count=archive_record_count,
        )
    except Exception as exc:
        # Any failure (disk full mid-write, permission error, corrupt
        # tarfile on read-back) leaves the source directory untouched —
        # rmtree() above is only ever reached after a successful record-
        # count verification, so this except block can only be entered
        # before the source has been removed. Reported, never raised: this
        # is invoked from the CLI's `rotate` subcommand, which must finish
        # its pass over all eligible dates rather than aborting on the
        # first failure.
        return RotationResult(
            date_str=date_str,
            action="failed",
            source_bytes=source_bytes,
            source_record_count=source_record_count,
            detail=f"{type(exc).__name__}: {exc}",
        )


def rotate_all(
    root: Path,
    retention_days: int = RAW_RETENTION_DAYS,
    dry_run: bool = False,
    today: Optional[date] = None,
) -> List[RotationResult]:
    """Rotate every eligible day directory. Does not take the lock itself —
    callers (the CLI) are expected to wrap this in `acquire_rotate_lock()`
    so `rotate` and `rollup` can never interleave against the same store."""
    results = []
    for date_str in eligible_dates(root, retention_days=retention_days, today=today):
        results.append(rotate_day(root, date_str, dry_run=dry_run))
    return results
