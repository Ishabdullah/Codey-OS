---
name: t10-commit1-schema-v2-migration
description: T10 commit 1 telemetry schema v1->v2 additive migration + version-aware doctor hash check — round 1 CHANGES REQUESTED (doc-only)
metadata:
  type: project
---

T10 commit 1 (2026-09-10, Codey-OS): telemetry schema v2 migration. Round 1 = CHANGES REQUESTED, doc/comment-only. Code is sound.

**Why v2 exists:** must be strictly additive over v1 so `schema.validate()` stays unchanged and old on-disk records still validate. Only `doctor`'s per-record `schema_sha256` check becomes version-aware.

**Verified clean:**
- `diff v1.json v2.json` = exactly 3 line changes: `schema_version` 1->2, appended sentence to top-level `_doc`, `"codey-os.cli"` appended to `envelope.fields.emitter.enum`. No reindent/reorder. Both 276 lines, both end `\n}\n`.
- v2 real sha256 = `13285c51ee6a3cdc...` (12: `13285c51ee6a`) — matches `EXPECTED_SHA256`/`_12` pin AND `schema.KNOWN_SCHEMA_SHA256_12[2]`.
- v1 real sha256 12 = `8a45d9fc8c23` — matches `KNOWN_SCHEMA_SHA256_12[1]` literal; `test_known_schema_hashes_table` asserts it literally.
- `_ENVELOPE_REQUIRED_FIELDS` = `[k for k in envelope.fields if k != "body"]` — key-derived, does NOT read `nullable`. validate() never enforces non-nullability, so the additivity comment (lists _ENVELOPE_REQUIRED_FIELDS/CATEGORIES/EMITTERS/NULL_REASON_CODES) is accurate and `test_schema_v2_is_additive_over_v1` genuinely guards exactly those four via subset checks.
- `cmd_doctor`: `expected_hash = KNOWN_SCHEMA_SHA256_12.get(rec.get("schema_version", 1))`. Unknown version -> None -> any hash mismatches. Missing version -> defaults to 1. `hard_violation_count` wiring unchanged. Aigentik emits `schema_version` as JSON number 1 -> `json.load` int 1 -> int-keyed `.get(1)` works (no str-key no-op).
- `cmd_schema --verify` rewrite necessary: old code compared Aigentik v1.json to the currently-loaded schema hash, which breaks once loaded schema is v2. New per-version file-to-file full-hash compare; missing Aigentik `v{n}.json` -> "not yet migrated" (not failure); "not present on this device" early return kept. `Path.home()` honors monkeypatched HOME.
- No test asserts old `--verify` output format (only new `v1: MATCH` assertion). No non-test consumer of `schema_hash_mismatches` dict beyond doctor.
- Tests: schema+cli 39 passed; `-k "telemetry or schema"` 205 passed.

**Blocking (doc-only):** `tests/test_telemetry_schema.py` docstring lines 5-6 now say "This literal [= the v2 hash `EXPECTED_SHA256`] is what Codey-Aigentik's parity test (T1) matches against." FALSE: Codey-Aigentik `tests/telemetry.test.js:27` pins `'8a45d9fc8c23'` (v1) and `telemetry.mjs:36` reads `telemetry/schema/v1.json` (only v1.json exists there). The diff changed the literal to v2 but left the claim standing -> stale-as-current, the exact class this project repeatedly CRs (T8a, NEW-436, m1a). Fix: reword to note Aigentik still pins v1 until its own v2 migration (later T10 commit).

**Also required (rule 8):** `docs/telemetry_layer_design.md` lines ~710 ("`telemetry/schema/v1.json` is the single source of truth"), ~801 ("`telemetry/schema.py` | Loads `v1.json`") and similar (~648, ~800, ~822, ~1098) are now false about current state — update or log a NEW_ISSUES line + Appendix A.

**Non-blocking sweep-or-log:** stale "v1.json" docstring refs at `telemetry/envelope.py:3` and `:13`, `telemetry/provenance.py:511`, `tests/test_telemetry_schema.py:91` — those blocks are byte-identical v1<->v2 so not functionally wrong.

**Live-verifier:** against real `~/.codeyOS/metrics`, run `codey-metrics doctor --json` and confirm existing v1 records (schema_version 1 / hash 8a45d9fc8c23, incl. Aigentik-emitted) produce zero `schema_hash_mismatches`; run `codey-metrics schema --verify` and confirm `v1: MATCH` / `v2: not yet migrated` / exit 0.
