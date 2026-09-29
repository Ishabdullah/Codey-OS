---
name: appointment-types-phase6-aigentik-calendar-alignment-approved
description: Final scheduling round Phase 6 — Aigentik calendar.js/index.js/owner-command.js alignment with Core scheduling + NEW-467 graceful 400 handling; APPROVED
metadata:
  type: project
---

Phase 6 (2026-09-11, staged not committed at review in `~/Codey-Aigentik`),
following [[appointment_types_phase4_concurrency_cap_approved]] and
[[appointment_types_phase5_business_hours_ui_approved]]. Generalizes
`calendar.js`'s `hasConflict` to a same-type capacity cap parity with Core's
`_assert_within_concurrency_cap`, adds `effectiveHoursForType` (business
hours ∩ per-type `scheduling_hours`), and adds NEW-467 400-recovery
(re-offer alternatives) at 3 confirm/schedule/reschedule call sites.

**Verdict: APPROVED, no blockers.** All 12 review-brief items independently
verified against primary sources, not the implementer's prose:
- Opened `restoricon_core/services/scheduling_service.py`'s
  `_assert_within_concurrency_cap` directly (found under
  `~/Codey-OS/restoricon_core/`, NOT `~/restoricon/` — that path doesn't
  exist, don't assume from the dir name) and byte-compared the overlap
  predicate to `calendar.js`'s new `hasConflict` capacity branch: same
  `status === 'confirmed'` filter, same buffer-expands-existing-row-only
  math, same half-open `new_start < aEnd && new_end > aStart` bound, same
  `count >= max_concurrent` threshold. True parity, not approximate.
- The fail-open (Core, missing/unresolved type id) vs fail-closed
  (calendar.js, falls back to legacy cap-1-any-type) asymmetry is real but
  harmless: confirmed by diffing old vs new `hasConflict` line-by-line that
  every EXISTING caller (none pass a type) is byte-identical pre/post-diff.
  The asymmetry only ever fires for a NEW caller passing a stale/unresolved
  type id, where it can only under-offer (fewer re-offered slots), never
  over-book — consistent with the review brief's regression bar (identical
  behavior for old callers) being satisfied.
- `effectiveHoursForType`'s "day absent in non-empty grid = closed that
  day" interpretation is documented in-code (not just the report), and
  intersection-after-narrowing is structurally guaranteed by
  `intersectHours` (min of two end times, max of two starts) — a type can
  never widen the business day.
- `excludeId` on `generateOfferSlots` genuinely threads through
  `findNextAvailableSlot` → `isSlotAvailable` → `hasConflict`, and is used
  identically at the two real call sites that need it (index.js's
  `confirmAndClose` re-offer, owner-command.js's reschedule 400-recovery)
  — the owner-command.js `excludeId: appt.id` call site is itself NEW in
  this diff, not a pre-existing use the brief's "leak into other call
  sites" concern should worry about.
- `err.status` tagging on `createAppointment`/`updateAppointment` throws:
  grepped every `.message` use in both files — 100% are log/reply string
  interpolation, zero string-matching on error text, so nothing could
  break. `confirmNegotiation`/`rescheduleAppointment` both delegate to
  `updateAppointment`, inheriting `.status` for free.
- `confirmAndClose` read directly: genuinely the single choke point (3
  call sites — `processIntakeReply` line 551, both `negotiateTime`
  branches lines 572/632); on 400 it calls real `generateOfferSlots` with
  the negotiation's actual `appointmentTypeId` (not a generic retry); all
  invite/notification sends are physically below the try/catch block in
  the file (verified by reading, not summary); non-400 rethrows
  unconditionally.
- `owner-command.js`'s two handlers mirror this exactly (same non-400
  rethrow, same real re-offer, same no-false-success ordering).
- `executeInterpretedCommand` export: grepped all callers — only the new
  test file imports it, no HTTP route or dispatcher wires it externally.
  Sanity-checked, no new attack surface.
- `mapCoreToJS`/`mapJSToCore` `appointment_type_id` round-trip uses the
  identical `?? null` pattern as the pre-existing `appointment_type` field
  on both sides.
- `intersectHours`'s string comparison of zero-padded `"HH:MM"`: confirmed
  BOTH the business-hours grid and the new per-type scheduling-hours grid
  in `restoricon_core/api/web_surfaces.py` use `<input type="time">`
  (HTML5-guaranteed zero-padded), and `DEFAULT_SCHEDULE_CONFIG`'s own
  `OPEN_DAY` literals (`'00:00'`/`'23:59'`) are already zero-padded — no
  unpadded-string edge case reaches this comparison.
- `formatWorkingHours`'s `DAY_KEYS.filter(k => k !== 'sun' || true)` is
  confirmed a genuine no-op (the `|| true` unconditionally short-circuits
  the whole predicate to `true`) — pre-existing code, untouched by this
  diff, correctly flagged for the ledger only.
- Ran the full jest suite myself: `326 passed, 21 suites` verbatim, matches
  the claim exactly. The new end-to-end `generateOfferSlots({appointmentTypeId})`
  test genuinely mocks `/api/v1/appointment-types` + fetch-resolves by id
  + threads through `isSlotAvailable`/`hasConflict` — not a pre-resolved
  shortcut; verified by reading the mock implementation, not just the
  assertion block.

**Pattern for future reviews in this repo pairing:** `~/Codey-OS` and
`~/restoricon` are DIFFERENT directories — Core's actual source
(`restoricon_core/`) lives under `~/Codey-OS/restoricon_core/`, not under
a top-level `~/restoricon/restoricon_core/` (that path 404s). Don't assume
from a directory name that looks like it should hold a project's code.
