---
name: new465-calendar-merge-working-hours-approved
description: NEW-465 Aigentik calendar.js mergeWorkingHours fix — approved; found sibling duration_by_relationship aliasing hazard
metadata:
  type: project
---

Phase 1 final scheduling round, Codey-Aigentik/calendar.js. `mergeWorkingHours` added; `loadScheduleConfig` deep-merges Core `working_hours` over `DEFAULT_SCHEDULE_CONFIG` per DAY_KEYS. Empty `{}` from Core no longer wipes the open week (old shallow spread bug). Approved r1, 294 jest pass.

**Why:** Core sends `working_hours: {}` when never configured; shallow `{...DEFAULT, ...core}` overwrote the whole open week → bot offered zero slots.

**How to apply:** Verified: hasOwnProperty keeps explicit `null` (day off) distinct from omitted; cloneDay `{...def}` breaks nested alias; 404 branch alias claim real (`setDayOff` does `scheduleConfig.working_hours[key] = null` in place, old `{...DEFAULT_SCHEDULE_CONFIG}` shared the nested working_hours ref). catch-branch still `{...DEFAULT_SCHEDULE_CONFIG}` — same hazard, implementer flagged as new finding, deferred OK.

**Sibling hazard I found (log to NEW_ISSUES):** `duration_by_relationship` has the SAME aliasing bug in all 3 fallback branches (404, catch, and ok-branch when Core omits the key). `setRelationshipDuration` line ~238 does `scheduleConfig.duration_by_relationship[k] = minutes` in place → pollutes `DEFAULT_SCHEDULE_CONFIG.duration_by_relationship` ({}) for process lifetime. Not blocking Phase 1 (working_hours is the booking-correctness priority) but rule-8 log required.
