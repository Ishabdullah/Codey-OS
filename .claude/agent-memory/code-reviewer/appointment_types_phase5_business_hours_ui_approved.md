---
name: appointment-types-phase5-business-hours-ui-approved
description: Final scheduling round Phase 5 — admin dashboard business-hours grid + appointment-type management UI; APPROVED w/ 1 mandatory NEW-### to log
metadata:
  type: project
---

Phase 5 (2026-09-11, staged not committed at review), following
[[appointment_types_phase3_hours_semantics_approved]] and
[[appointment_types_phase4_concurrency_cap_approved]]. Adds the business-hours
7-day grid and appointment-types table/CRUD to `render_admin_surface()` in
`restoricon_core/api/web_surfaces.py`, removes the dead `schedConcurrent`
input.

**Verdict: APPROVED.** XSS (escapeHtml wraps every name/string interp,
onclick handlers carry only numeric ids + hardcoded day constants),
full-row-replace wipe risk (both 200/404 load branches populate a complete
`currentScheduleConfig`, `saveScheduleConfig()` calls `serializeBusinessHours()`
before every POST unconditionally), null-vs-absent convention, inherit-checkbox
polarity, `sort_order` partial-update belt-and-braces claim, dead-code removal,
and 515-pass pytest count all independently verified against primary sources
(read `escapeHtml` def, read `update_appointment_type`, grepped diff for
pre-existing XSS sibling sites vs new code, ran the test suite myself).

**The one real gap (advisor caught it, I hadn't checked deeply enough):**
claim was "absent-key convention matches Phase 1's calendar.js exactly" —
it does NOT. `calendar.js`'s `DEFAULT_SCHEDULE_CONFIG.working_hours` is
`OPEN_DAY = {start:'00:00', end:'23:59'}` (fully unrestricted) per day;
Core's admin UI's `populateBusinessHours()`/`serializeBusinessHours()`
absent-key fallback is `09:00`/`17:00` (narrower) and materializes it on
EVERY save, touched-day-or-not. Traced reachability: calendar.js's own
`saveScheduleConfig()` always round-trips through `mergeWorkingHours()`
first, so bot-driven writes are always full-7-key already — the only path
to a genuinely partial `working_hours` in Core's DB is the one-time
`migrate_aigentik.py:555` import (`rec.get("working_hours") or {}`, no
normalization) before ANY save (bot or admin) touches it again. Bounded
(narrow post-migration window, not a live landmine, no data goes null/
missing — a narrowing not a wipe) but real, and it's exactly the kind of
gap a "verify X matches Y exactly" claim needs closing, not paraphrasing.
Required rule-8 log, not a blocker.

**Pattern for future review of this exact review-brief style (specific,
numbered claims to verify):** when a claim says "matches convention X
exactly," open X's actual default/fallback values and diff them by hand —
don't just confirm the shared null/absent-key STRUCTURE matches (which I
did first and treated as sufficient). Structure-matching and value-matching
are different checks; this file's own phase 3 memory even documents 3 fallback
branches with the SAME aliasing bug for `duration_by_relationship` in
calendar.js — this project's schedule-config surface has a track record of
default-value discrepancies specifically, worth extra scrutiny each time.
