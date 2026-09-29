---
name: admin-dashboard-round3-chrome-wiring-approved
description: NEW-450/449/466 admin-dashboard chrome wiring + owner_name/aigentik_name/booking_window_days form fields — APPROVED (committed pre-review, 3 local commits 7aad57b/c16209b/aec94ee)
metadata:
  type: project
---

Round 3 admin-dashboard. All changes in `restoricon_core/api/web_surfaces.py` + 2 test files. APPROVED r1.

**Verified facts:**
- `agent_name_set` co-write is one-directional: `if (an) window.currentBusinessProfile.agent_name_set = 1;` — no path sets 0; clearing the AI Agent Name field leaves the GET-loaded value intact (POSTs full `currentBusinessProfile`).
- Aigentik `index.js` (separate repo Codey-Aigentik) is byte-untouched by this diff. `onboarding_sent` only appears in the pre-existing 404 literal (unchanged line). Onboarding email guarded by `if (profile.onboarding_sent) return;` — a live business has onboarding_sent=1, so no re-fire.
- `patchBusinessChrome`: `.textContent` only, never `.innerHTML`. tel href = `'tel:'+phone.replace(/\D/g,'')` digits-only. mailto href set only when `/^[^@\s]+@[^@\s]+$/.test(email)` (anchored), else `removeAttribute('href')`. Weird-but-matching emails can't execute (mailto scheme, setAttribute doesn't parse HTML). javascript:/`"><script` rejected (no `@`).
- Rendered JS regex correct: source non-raw triple-quote has `\\D`/`\\s` → renders `\D`/`\s`. No SyntaxWarning (`python -W error::SyntaxWarning` import clean).
- `patchBusinessChrome` count == 4 (def + load-200 + load-404 + save-success), none in dead branch.
- ScheduleConfig fields: id, working_hours, default_duration_minutes, buffer_minutes, booking_window_days, duration_by_relationship, updated_at — 404 literal constructs cleanly via `ScheduleConfig(**that)`.
- BusinessProfile fields include owner_name/aigentik_name/agent_name_set; `_row_to_business_profile` lines 253-255 carry all three; upsert 4-site lockstep intact (automation_service.py:296-318).
- business-profile 404 → `businessProfileLoaded=false` + button disabled + inline msg (asymmetry commented). schedule-config 404 → populates+enables (legit first-row create, commented).
- Tests use SENTINEL values, round-trip through route + service layers. `test_schedule_config_route_is_full_row_replace` genuinely pins full-row-replace blanking.
- `pytest tests/test_restoricon_core/` → 446 passed.

**Minor non-blocking:** business-profile 404 JS literal omits the `owner_name` key (harmless — save double-guarded off in that branch). `booking_window_days` `|| 365` coerces a user-entered 0 to 365 (min="1" on input; nonsensical value anyway). 404 chrome-blank wipes the static nav fallback phone/license for an admin viewing a 404 state (cosmetic, commented as deliberate).
