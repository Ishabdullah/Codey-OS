"""
Loads telemetry/schema/v1.json once at import and exposes the constants and
validation helper every other telemetry module needs.

`SCHEMA_SHA256_12` is what every record's `schema_sha256` envelope field is
set from (see envelope.py). It exists so schema drift between Codey-OS and
Codey-Aigentik is visible per-record, not just detectable by inspection
(docs/telemetry_layer_design.md §3.3).

`validate(record)` is deliberately NOT called on the hot path (constraint 3
of T0's brief — no per-event validation cost). It exists for tests and for
the later `codey-metrics doctor` subcommand (T4).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List

_SCHEMA_PATH = Path(__file__).parent / "schema" / "v1.json"

with open(_SCHEMA_PATH, "r", encoding="utf-8") as _f:
    _SCHEMA_BYTES = _f.read().encode("utf-8")
    SCHEMA: Dict[str, Any] = json.loads(_SCHEMA_BYTES)

SCHEMA_VERSION: int = SCHEMA["schema_version"]
SCHEMA_SHA256: str = hashlib.sha256(_SCHEMA_BYTES).hexdigest()
SCHEMA_SHA256_12: str = SCHEMA_SHA256[:12]

CATEGORIES: List[str] = SCHEMA["envelope"]["fields"]["category"]["enum"]
EMITTERS: List[str] = SCHEMA["envelope"]["fields"]["emitter"]["enum"]
NULL_REASON_CODES: List[str] = SCHEMA["null_reason_codes"]
RECORD_SIZE_CAP_BYTES: int = SCHEMA["envelope"]["record_size_cap_bytes"]
ENV_ALLOW_LIST: List[str] = SCHEMA["env_allow_list"]
SECRET_PRESENCE_ONLY_ENV: List[str] = SCHEMA["secret_presence_only_env"]

_ENVELOPE_REQUIRED_FIELDS: List[str] = [
    name for name in SCHEMA["envelope"]["fields"] if name != "body"
]


class SchemaViolation(str):
    """A single human-readable violation string. Subclassing str keeps
    callers that just want to print/count violations simple, while still
    letting `validate()` return a typed list."""


def validate(record: Dict[str, Any]) -> List[str]:
    """
    Off-hot-path structural + honest-null check. Returns a list of
    human-readable violation strings; an empty list means the record is
    valid. Never raises on a malformed record — a malformed record IS the
    thing being reported, not a reason to crash the caller (tests /
    `codey-metrics doctor`).
    """
    violations: List[str] = []

    if not isinstance(record, dict):
        return ["record is not a JSON object"]

    for field in _ENVELOPE_REQUIRED_FIELDS:
        if field not in record:
            violations.append(f"missing envelope field: {field}")

    category = record.get("category")
    if category is not None and category not in CATEGORIES:
        violations.append(f"category {category!r} not in closed enum {CATEGORIES}")

    emitter = record.get("emitter")
    if emitter is not None and emitter not in EMITTERS:
        violations.append(f"emitter {emitter!r} not in closed enum {EMITTERS}")

    body = record.get("body", {})
    if not isinstance(body, dict):
        violations.append("body is not a JSON object")
        body = {}

    nulls = record.get("nulls", {})
    if not isinstance(nulls, dict):
        violations.append("nulls is not a JSON object")
        nulls = {}

    # Every reason code used must be in the closed set.
    for field_path, reason in nulls.items():
        if reason not in NULL_REASON_CODES:
            violations.append(
                f"nulls[{field_path!r}] reason {reason!r} not in closed set"
            )

    # Honest-null contract (§2.0.1): a null value anywhere in the record
    # must have a matching entry in `nulls`. This is a one-directional
    # check — null implies a reason. The converse does NOT hold: a field
    # may appear in `nulls` while holding a non-null (e.g. truncated, not
    # null) value — see the 8 KiB truncation path in envelope.py, which
    # records `nulls: {"<field>": "truncated_oversize_record"}` for a
    # field that was shortened, not nulled.
    for field in _ENVELOPE_REQUIRED_FIELDS:
        if field in ("nulls", "body"):
            continue
        if record.get(field, "__missing__") is None and field not in nulls:
            violations.append(f"{field} is null with no entry in nulls")

    for key, value in body.items():
        if value is None and f"body.{key}" not in nulls:
            violations.append(f"body.{key} is null with no entry in nulls")
        # NEW-327: the top-level check above is invisible to nulls nested
        # one level down inside a list-of-dicts body field (e.g.
        # record_run_start()'s `models`, where an individual entry's
        # `sha256` can be null). Recurse exactly one level into any body
        # value that is a list of dicts, using the per-index path
        # `body.{key}[{i}].{subkey}` — unambiguous and not worth a
        # generic deep-walker for a single known case.
        elif isinstance(value, list):
            for i, item in enumerate(value):
                if not isinstance(item, dict):
                    continue
                for subkey, subvalue in item.items():
                    path = f"body.{key}[{i}].{subkey}"
                    if subvalue is None and path not in nulls:
                        violations.append(f"{path} is null with no entry in nulls")

    return violations
