---
name: b2fin1_business_profile_read_cutover_changes_requested
description: B2-fin-1 business_profile Core-first read cutover (Codey-Aigentik owner-command.js) — round1 CHANGES REQUESTED
metadata:
  type: project
---

Reviewed 2026-09-02. `~/Codey-Aigentik/owner-command.js` new `readProfile()`
Core-first helper + 3 profile handlers; local file demoted to fallback;
local write/config-refresh now gated on `res.ok && res.data?.business_profile`.
**CHANGES REQUESTED round 1.**

**Blocking 1 — silent data loss + false success when Core configured but
failing.** `coreRequest` *returns* `{ok:false}` on non-2xx (does NOT throw),
so on 401/403/500 the `catch` never fires, the `if (res.ok && ...)` block is
skipped, nothing is persisted anywhere, config keeps the stale value, and
there is **no log line at all**. An expired token turns every rename/business/
owner edit into a cheerful no-op ("Done! I'll now go by X"). Sharper than the
implementer's flagged network-unreachable case. Fix must be 3 parts: (a) on
thrown OR `!res.ok`, run the same local-write + config-update as the no-Core
else branch; (b) `log.warn` with `res.status` only (never `res.data`);
(c) degraded-path reply must not claim success.

**Blocking 2 — `handleSetOwnerName` still derives a POST field from stale
cache.** `const configured = (ownerName && config.business_name) ? 1 : 0;`
overrides the correct `markConfiguredIfComplete(profile)` result (profile is
now Core-fresh) with a value from boot-time `config.business_name`. If another
client set `business_name` in Core after this instance booted — the exact
multi-client scenario the task exists for — this full-row POST overwrites
Core's `configured=1` with `0`. Same lost-update class the round fixes, in
touched code. Fix: use `profile.business_name`. Round's own tests miss it
(one asserts only `body.business_name`; the other seeds `config.business_name`
first).

**Warning 3 — parallel-Jest clobber of real prod `data/profile.json`.**
`jest.config.mjs` sets no `--runInBand`/`maxWorkers`. New
`business-profile-nocore.test.js` adds a *second* concurrent suite that
save/restores the real `data/profile.json` (its `jest.unstable_mockModule`
mock preserves `paths` from `realConfig`). If its `beforeAll` snapshots after
the other suite's `beforeEach` fixture write, it restores the fixture as
"original", clobbering real data. Fix: point mocked `paths.data_dir` at a
scratch tmpdir.

**Checked, NOT blocking:**
- `config.json.example` new `core_api` block has `//` comments — but the whole
  file is already JSONC by established convention (comments throughout);
  `install.sh:231` explicitly notes it's JSONC and does not parse it. Matches
  the file. Fine.
- Return-shape (item 4): GET `to_dict()` keys (incl `id`/`setup_date`/
  `updated_at`) are all valid `BusinessProfile` dataclass fields, and every
  POST body explicitly overrides all int-coerced fields
  (`agent_name_set`/`configured`/`onboarding_sent`). No drift. `upsert` forces
  `id=1`/`updated_at=now`. Verified against `restoricon_core` routes.py ~1024
  + models.py:739 + automation_service.py upsert.
- `getAigentikName()` now reads `config.aigentik_name` (was direct fs read).
  `config.json` has no `aigentik_name` key → pre-boot `undefined` → `|| 'Aigentik'`.
  In production `index.js loadProfile()` populates it at startup and handlers
  only run from that pipeline. Old fs read wasn't cross-client-fresh either. Benign.
- Residual GET-fails-but-POST-succeeds lost-update window: genuinely narrower
  than before, accept this round.
- No secret logging in new paths (readProfile `log.warn` / handler `log.error`
  use `e.message` only).
- Not committed — working tree only. `npm test` → 238/238 (18 suites), ran myself.

**Reusable:** `coreRequest` in these Aigentik modules returns `{ok:false}` for
non-2xx and only *throws* on network/parse failure — so a `try/catch` around it
catches only half the failure modes. Any "on failure, fall back" logic must
check `!res.ok` too, not just rely on the catch.

## Round 2 — APPROVED (2026-09-02)
All three fixes applied and negative-control verified by me:
- Crit 1: `coreConfigured`/`coreSynced` flags in all 3 handlers. `coreSynced=true`
  only inside `if (res.ok && res.data?.business_profile)`; both the `else`
  (non-2xx, `log.warn` status only) and `catch` (`log.warn` e.message) fall
  through to `if (!coreSynced) { durable local write + config.* }`. Degraded
  reply ("couldn't reach the main system") replaces "Done!". No double-write on
  happy path (coreSynced skips fallback). Disabling the handleRename fallback →
  3 tests fail. No `res.data`/token in any log.warn.
- Crit 2: `configured` now from `profile.business_name`. Reverting → the pinned
  test fails.
- Warn 3: nocore suite mocks `paths.*` to `fs.mkdtempSync`, `afterAll` rmSync,
  real-file save/restore dropped.
`npm test` → 239/239, 18 suites, ran myself. Not committed. Chain closed.
