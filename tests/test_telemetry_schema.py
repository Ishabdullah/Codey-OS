"""
Schema-file integrity: the SHA-256 of telemetry/schema/v1.json must match
a literal constant checked into this test file (NOT computed from the
same file schema.py reads — that would be circular and pin nothing). This
literal is what Codey-Aigentik's parity test (T1) matches against.

Also asserts the null-reason and category/emitter enums are closed sets,
per docs/telemetry_layer_design.md §2.0.1.
"""

from __future__ import annotations

from telemetry import schema
from utils.config import TELEMETRY_ENV_ALLOW_LIST, TELEMETRY_SECRET_PRESENCE_ONLY_ENV

# Computed once, out-of-band, from the checked-in telemetry/schema/v1.json.
# If this assertion ever fails after an intentional schema edit, the fix
# is to bump schema_version and create v2.json — NOT to update this
# constant to match a changed v1.json (§2.0: "Old records are never
# rewritten").
EXPECTED_SHA256 = "8a45d9fc8c236913bf74982f6dc774fe33833b6d2299dd735d6b89ae8898b618"
EXPECTED_SHA256_12 = "8a45d9fc8c23"


def test_schema_sha256_matches_pinned_constant():
    assert schema.SCHEMA_SHA256 == EXPECTED_SHA256
    assert schema.SCHEMA_SHA256_12 == EXPECTED_SHA256_12


def test_schema_version_is_one():
    assert schema.SCHEMA_VERSION == 1


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
    telemetry/schema/v1.json's env_allow_list (the schema file's own
    self-describing copy) must never silently diverge."""
    assert schema.ENV_ALLOW_LIST == TELEMETRY_ENV_ALLOW_LIST
    assert schema.SECRET_PRESENCE_ONLY_ENV == TELEMETRY_SECRET_PRESENCE_ONLY_ENV
