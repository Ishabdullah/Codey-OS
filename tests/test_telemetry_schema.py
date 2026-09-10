"""
Schema-file integrity: the SHA-256 of the current schema file
(telemetry/schema/v2.json) must match a literal constant checked into this
test file (NOT computed from the same file schema.py reads — that would be
circular and pin nothing). Codey-Aigentik's parity test (T1) pins the
same v2.json hash and reads v2.json (T10 commit 2, `a71e4d1`) — its
pinned literal must equal EXPECTED_SHA256 here. v1.json is frozen forever
and its hash is pinned separately in KNOWN_SCHEMA_SHA256_12 /
test_known_schema_hashes_table.

Also asserts the null-reason and category/emitter enums are closed sets,
per docs/telemetry_layer_design.md §2.0.1.
"""

from __future__ import annotations

import json
from pathlib import Path

from telemetry import schema
from utils.config import TELEMETRY_ENV_ALLOW_LIST, TELEMETRY_SECRET_PRESENCE_ONLY_ENV

# Computed once, out-of-band, from the checked-in current schema file
# (telemetry/schema/v2.json). If this assertion ever fails after an
# intentional schema edit, the fix is to bump schema_version and create
# v<N+1>.json — NOT to update this constant to match an in-place edit of an
# existing version file (§2.0: "Old records are never rewritten"). Updating
# these two literals is correct ONLY as part of a deliberate version bump.
EXPECTED_SHA256 = "13285c51ee6a3cdc1d96d80791f2100da3f3e00aee2e2f8177e5c8572af536e3"
EXPECTED_SHA256_12 = "13285c51ee6a"


def test_schema_sha256_matches_pinned_constant():
    assert schema.SCHEMA_SHA256 == EXPECTED_SHA256
    assert schema.SCHEMA_SHA256_12 == EXPECTED_SHA256_12


def test_schema_version_is_two():
    assert schema.SCHEMA_VERSION == 2


def test_category_enum_matches_design():
    assert schema.CATEGORIES == [
        "inference",
        "gate",
        "device",
        "cotenancy",
        "task",
        "extraction",
        "provenance",
        "meta",
    ]


def test_emitter_enum_matches_design():
    assert schema.EMITTERS == [
        "codey-os.daemon",
        "codey-os.tui",
        "codey-os.core-api",
        "codey-os.plannd",
        "codey-os.loader",
        "aigentik",
        "codey-os.cli",
    ]


def test_null_reason_codes_is_closed_and_nonempty():
    assert schema.NULL_REASON_CODES
    assert len(schema.NULL_REASON_CODES) == len(set(schema.NULL_REASON_CODES)), (
        "duplicate reason codes"
    )


def test_every_category_has_at_least_one_event_type():
    for category in schema.CATEGORIES:
        event_types = schema.SCHEMA["categories"][category]["event_types"]
        assert event_types, f"category {category} has no event_types"


def test_record_size_cap_is_8192_bytes():
    assert schema.RECORD_SIZE_CAP_BYTES == 8192


def test_env_allow_list_excludes_known_secret_names():
    secret_names = {"OPENROUTER_API_KEY", "UNLIMITEDCLAUDE_API_KEY", "CLOUDFLARE_TUNNEL_TOKEN"}
    assert secret_names.isdisjoint(set(schema.ENV_ALLOW_LIST))
    assert secret_names == set(schema.SECRET_PRESENCE_ONLY_ENV)


def test_schema_env_allow_list_matches_utils_config_copy():
    """utils/config.py's TELEMETRY_ENV_ALLOW_LIST (what
    telemetry/provenance.py actually reads operationally) and
    the schema file's own self-describing env_allow_list copy must never
    silently diverge."""
    assert schema.ENV_ALLOW_LIST == TELEMETRY_ENV_ALLOW_LIST
    assert schema.SECRET_PRESENCE_ONLY_ENV == TELEMETRY_SECRET_PRESENCE_ONLY_ENV


_SCHEMA_DIR = Path(schema.__file__).parent / "schema"


def _load(name: str) -> dict:
    with open(_SCHEMA_DIR / name, "r", encoding="utf-8") as f:
        return json.load(f)


def test_schema_v2_is_additive_over_v1():
    v1 = _load("v1.json")
    v2 = _load("v2.json")

    assert set(v1["envelope"]["fields"]) <= set(v2["envelope"]["fields"])
    assert set(v1["envelope"]["fields"]["category"]["enum"]) <= set(
        v2["envelope"]["fields"]["category"]["enum"]
    )
    assert set(v1["null_reason_codes"]) <= set(v2["null_reason_codes"])
    assert set(v1["envelope"]["fields"]["emitter"]["enum"]) <= set(
        v2["envelope"]["fields"]["emitter"]["enum"]
    )


def test_known_schema_hashes_table():
    assert schema.KNOWN_SCHEMA_SHA256_12[1] == "8a45d9fc8c23"
    assert schema.KNOWN_SCHEMA_SHA256_12[2] == schema.SCHEMA_SHA256_12
