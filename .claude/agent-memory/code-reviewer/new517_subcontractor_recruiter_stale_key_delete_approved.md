---
name: new517-subcontractor-recruiter-stale-key-delete-approved
description: NEW-517 mapJSToCore stale-key delete fix (Codey-Aigentik subcontractor-recruiter.js) — approved
metadata:
  type: project
---

2026-09-15: NEW-517 fix approved (Codey-Aigentik repo, not Codey-OS). `mapJSToCore()`
was spreading the JS object and adding renamed Core-side keys (`external_id`,
`last_contact_at`) without deleting the JS-side originals (`subcontractor_id`,
`last_contact`), so every real `/api/v1/subcontractors/upsert` POST carried
both old and new key names — which, after NEW-515's allow-list fix on the
Core side, now 400s. Fix adds two unconditional `delete` lines right after
the two rename assignments.

Verification done, not just trusted:
- Read `mapJSToCore` in full: confirmed exactly two stale-key pairs exist
  (`subcontractor_id`/`external_id`, `last_contact`/`last_contact_at`); the
  third rename `coreObj.id = jsObj.id` is genuinely name-unchanged (verified
  by reading, not taking the implementer's word for it).
- Deletes are unconditional straight-line code, nothing between assignment
  and delete could re-add the stale key.
- Test (`tests/subcontractor-recruiter.test.js`) imports `mapJSToCore`
  directly (line 22) and calls it directly (not through a mocked-fetch
  wrapper) at line 306; asserts `.not.toHaveProperty(...)` for absence.
- **Correction to implementer's stated rationale** (harmless, doesn't affect
  the fix's correctness): the implementer claimed `not.toHaveProperty` was
  necessary because an undefined-valued-but-present key would pass
  `toBeUndefined()` yet still appear in `JSON.stringify()`. This is
  factually wrong — `JSON.stringify({a: undefined})` → `{}`, confirmed live
  (`node -e "console.log(JSON.stringify({a: undefined, b: 1}))"` → `{"b":1}`).
  Also moot here regardless, since the stale key in the actual bug held a
  real string value (`'sub_0042'`), not `undefined`, so `toBeUndefined()`
  would have failed on the unpatched code too. `not.toHaveProperty` is still
  the *better* assertion style, just not for the reason given.
- Ran the test suite myself verbatim: `node --experimental-vm-modules
  node_modules/jest/bin/jest.js --config jest.config.mjs
  tests/subcontractor-recruiter.test.js` → `Tests: 22 passed, 22 total`.
  Confirms this exact invocation genuinely works in the Termux sandbox —
  an earlier "jest doesn't run here" finding really was about wrong
  invocation syntax, not a real environment limitation.
- Traced every caller of `mapCoreToJS` (the reverse function, which has the
  same-shaped stale-key leak but was correctly left unfixed as "benign")
  by grepping `mapCoreToJS(` in subcontractor-recruiter.js:
  `getSubcontractorById`, `findSubcontractor`,
  `createOrUpdateSubcontractorLead`'s `finalRecord`, and
  `updateSubcontractor`'s `existing`/`updatedRecord`. Confirmed genuinely
  benign: (a) any path that re-sends data to Core goes back through
  `mapJSToCore` first (e.g. `updateSubcontractor`'s
  `{...existing, ...updates}` merge picks up stale `external_id`/
  `last_contact_at` from `existing`, but `mapJSToCore` unconditionally
  overwrites those two keys from `jsObj.subcontractor_id`/`last_contact`
  before deleting the JS names, so the merge is self-correcting); (b) the
  only non-Core consumers (`syncWithContacts`, `formatSubcontractorSummary`,
  `formatPipelineReport` in owner-command.js/index.js/role-router.js) all
  read specific named fields off the object rather than spreading/iterating
  it, so extra stale keys are inert. No new ledger entry needed — this was
  investigated and is not a live bug, just asymmetric-looking code.

Lesson: when an implementer states *why* a test assertion choice matters
(not just *that* it should be used), verify the stated mechanism
independently (e.g. actually run `JSON.stringify` on an object with an
`undefined` value) rather than accepting plausible-sounding JS semantics
claims — this one was wrong but harmless since it didn't change what needed
testing.
