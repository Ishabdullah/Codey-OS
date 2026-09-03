"""
Builds the shared envelope every telemetry record carries (schema
v1.json's `envelope` block) and enforces the 8 KiB record cap.

Design decisions / implementation details the design doc left
unspecified, resolved here (flag for review):

- `nulls` keys use dotted paths relative to the record root: a bare
  envelope field name (e.g. "boot_id") or "body.<field>" for a body
  field. The design doc's examples were ambiguous about this.
- `boot_id` unreadable and `correlation_id` "no ambient context yet" had
  no matching reason code in the design doc's closed set (§2.0.1). Two
  codes were added to the v1.json set itself (this is schema v1's first
  and only implementation, so the set is being defined, not amended):
  `boot_id_unreadable` and `correlation_id_not_yet_available`.
- `seq` is assigned HERE, at envelope-build time (i.e. at the `record_*()`
  call site), not by the writer thread after the record is dequeued.
  This is load-bearing: §2.0 states "a gap in seq within a run is proof
  of a dropped record" — if seq were assigned post-dequeue, a dropped
  record would leave no gap and that guarantee would be false.
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from telemetry.schema import RECORD_SIZE_CAP_BYTES, SCHEMA_SHA256_12, SCHEMA_VERSION

_BOOT_ID_PATH = "/proc/sys/kernel/random/boot_id"

_seq_lock = threading.Lock()
_seq_counter = 0

_boot_id_lock = threading.Lock()
_boot_id_cache: Optional[Tuple[Optional[str]]] = None  # sentinel: None = not yet read


def next_seq() -> int:
    """Thread-safe per-process monotonic counter starting at 0."""
    global _seq_counter
    with _seq_lock:
        value = _seq_counter
        _seq_counter += 1
        return value


def reset_seq() -> None:
    """Test-only: reset the seq counter to 0 for a fresh 'run'."""
    global _seq_counter
    with _seq_lock:
        _seq_counter = 0


def get_boot_id() -> Optional[str]:
    """
    Reads /proc/sys/kernel/random/boot_id once per process and caches the
    result (fact 0.3: this file is readable on this device, unlike
    /proc/stat and /proc/uptime — but the read is still wrapped, since a
    permission or platform difference elsewhere must not raise into a
    record-building call). Returns None if unreadable.
    """
    global _boot_id_cache
    with _boot_id_lock:
        if _boot_id_cache is None:
            try:
                with open(_BOOT_ID_PATH, "r", encoding="utf-8") as f:
                    _boot_id_cache = (f.read().strip() or None,)
            except OSError:
                # Honest-null path, not a crash: boot_id is a nice-to-have
                # grouping key (fact 0.3), never required for a record to
                # be emitted. See schema.py NULL_REASON_CODES for the
                # reason this maps to.
                _boot_id_cache = (None,)
        return _boot_id_cache[0]


def build_envelope(
    *,
    category: str,
    event_type: str,
    emitter: str,
    pid: int,
    run_id: str,
    body: Dict[str, Any],
    correlation_id: Optional[str] = None,
    nulls: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Assembles one full envelope + body record. `nulls` is the caller-
    supplied map of body-field null reasons (recorders.py knows why its
    own fields are null; envelope.py does not). Envelope-level nulls
    (boot_id, correlation_id) are added here.
    """
    record_nulls: Dict[str, str] = dict(nulls) if nulls else {}

    boot_id = get_boot_id()
    if boot_id is None:
        record_nulls.setdefault("boot_id", "boot_id_unreadable")

    if correlation_id is None:
        record_nulls.setdefault("correlation_id", "correlation_id_not_yet_available")

    record: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "schema_sha256": SCHEMA_SHA256_12,
        "event_id": uuid.uuid4().hex,
        "run_id": run_id,
        "boot_id": boot_id,
        "seq": next_seq(),
        "ts_wall": time.time(),
        "ts_mono": time.monotonic(),
        "category": category,
        "event_type": event_type,
        "emitter": emitter,
        "pid": pid,
        "correlation_id": correlation_id,
        "nulls": record_nulls,
        "body": body,
    }

    return _enforce_size_cap(record)


def _enforce_size_cap(record: Dict[str, Any]) -> Dict[str, Any]:
    """
    §2.0: a record exceeding RECORD_SIZE_CAP_BYTES has its longest string
    fields truncated to fit, gaining `nulls: {"<field>": "truncated_oversize_record"}`
    plus `body._truncated_fields: [...]`. Nothing is ever dropped for size
    alone. Truncation targets `body` string fields only (the envelope
    itself is small and fixed-shape, so it is never the cause of an
    oversize record).
    """
    serialized = json.dumps(record, separators=(",", ":"), default=str)
    if len(serialized.encode("utf-8")) <= RECORD_SIZE_CAP_BYTES:
        return record

    body = record["body"]
    truncated_fields: List[str] = []

    # Repeatedly halve the currently-largest string field until the
    # record fits or there is nothing left worth truncating. Bounded
    # iteration count as a belt-and-braces guard against a pathological
    # shape (e.g. a single field larger than the cap) never converging —
    # if that bound is hit the record is written oversize rather than
    # spinning forever, which is the safer failure mode for a hot path.
    max_iterations = 64
    for _ in range(max_iterations):
        serialized = json.dumps(record, separators=(",", ":"), default=str)
        if len(serialized.encode("utf-8")) <= RECORD_SIZE_CAP_BYTES:
            break

        string_fields: List[Tuple[str, int]] = [
            (k, len(v)) for k, v in body.items() if isinstance(v, str) and v
        ]
        if not string_fields:
            break  # nothing left to shrink; record ships oversize

        field_name, _length = max(string_fields, key=lambda kv: kv[1])
        original = body[field_name]
        body[field_name] = original[: len(original) // 2]
        record["nulls"][f"body.{field_name}"] = "truncated_oversize_record"
        if field_name not in truncated_fields:
            truncated_fields.append(field_name)

    if truncated_fields:
        body["_truncated_fields"] = truncated_fields

    return record
