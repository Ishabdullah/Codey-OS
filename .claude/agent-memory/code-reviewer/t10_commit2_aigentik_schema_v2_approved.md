---
name: t10-commit2-aigentik-schema-v2-approved
description: T10 commit 2 (Codey-Aigentik) telemetry schema v2 migration — round 1 APPROVED
metadata:
  type: project
---

T10 commit 2 (2026-09-10, Codey-Aigentik repo). APPROVED round 1. Resolves the doc-only CR from [[t10-commit1-schema-v2-migration]] (Aigentik was still pinning v1).

**Verified clean:**
- `cmp` Aigentik `telemetry/schema/v2.json` vs Codey-OS's = silent. sha256 = `13285c51ee6a3cdc...` (12 = `13285c51ee6a`), matches `EXPECTED_SCHEMA_SHA256_12` pin.
- v1.json untouched: silent vs Codey-OS v1.json AND vs `git show HEAD:`.
- `telemetry.mjs`: `SCHEMA_VERSION = SCHEMA.schema_version` (derived, =2), `SCHEMA_SHA256_12` computed from bytes. Emit sites :132/:1059 use both. Line 7 + line 36 comments/path updated.
- Path-fix real: jest `process.cwd()` = repo root; old `path.dirname(path.dirname(process.cwd()))` → `/data/data/com.termux/files` (dropped `home/`) so cross-repo `it()` blocks skipped vacuously; new `path.dirname(process.cwd())` → `/data/data/com.termux/files/home` correct. BOTH cross-repo blocks use fixed form.
- New `it()` byte-compares v1.json across repos (frozen-forever guard). Old block converted v1→v2.
- Targeted run `-t "byte-for-byte"`: 2 passed, 0 skipped of those 2. Full `npm test`: 276 passed / 19 suites.
- No stale `v1.json` / `toBe(1)` / `8a45d9fc8c23` refs remain (line 69/74 v1.json refs are the intentional new v1 test).
