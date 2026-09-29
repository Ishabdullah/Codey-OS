---
name: business-profile-contact-fields-approved
description: business_profile phone/email/license_number additive columns + frontend load-guard rewrite — APPROVED round 1
metadata:
  type: project
---

Round adding business_phone/business_email/license_number to `business_profile` (admin dashboard public-contact fields). APPROVED round 1, clean.

**Why:** implementer followed all the established patterns correctly — rare for a first pass here.

**How to apply:** if this area is touched again, the verified facts:
- `_migrate_schema()` runs 3x per `init_schema()` (before executescript, executescript, after). Idempotent guard `if existing_columns and column not in existing_columns` handles fresh (empty set → skip) and legacy (adds) correctly.
- `upsert_business_profile` 4-site lockstep verified: 12 `?` after literal `1`, params tuple order exact-matches column list. `updated_at` param is `now` not `profile.updated_at`.
- `BusinessProfile.to_dict()` = `asdict()`, exactly the 13 dataclass field names → round-trips through `BusinessProfile(**json_body)` with no unknown-key TypeError.
- `_row_to_profile` accesses by column name, so fresh-vs-migrated column order is irrelevant.
- Frontend: `saveBusinessProfile()`/`saveScheduleConfig()` now guarded by `!window.businessProfileLoaded` / `!window.scheduleConfigLoaded` (undefined = falsy = fail-safe blocked). 404 default object has all 13 fields. `bpBtn`/`scBtn` `const` declared before their `try`, referenced in `catch` — no TDZ.
- schedule-config 404 default is only 2 fields but harmless (no pre-existing row to blank).
- phone/email/license are *public* published fields, not sensitive PII — no audit allow-list concern.
- restoricon_core suite: 431 passed.

**Round 2 (2026-09-10, Aigentik repo) — APPROVED.** Email signature now carries business_phone/business_email/license_number. Verified: escapeHtml replaces `&` first (order-safe), HTML branch escapes all 3 via `.toString()`, text branch raw (matches spec, same trust model as existing taglineText). All 4 `buildEmailSignature(` live call sites updated (llama.js:375/826/899, index.js:898) — grep-confirmed zero missed. `buildEmailSignature` stays pure (contact defaults `{}`); `businessContactFromConfig()` is the only config reader. `has()` guard `(v||'').toString().trim().length>0` — no literal null/undefined/dangling separator for any partial combo (each line `\n`/`<br>` prefixed, appended after identity+tagline). config.json ESM singleton shared between index.js loadProfile mutation and llama.js reader. 285 jest passed.
Minor non-blocking: dashboard-set values interpolated raw into plain-text branch — newline in a value could inject fake sig lines; acceptable (owner-controlled, same as existing fields).
