---
name: appointment-types-phase3-hours-semantics-approved
description: Final scheduling round Phase 3 — database.py/models.py comment-only doc pass + guard-rail test proving Core doesn't enforce hours; APPROVED
metadata:
  type: project
---

Phase 3 of the final scheduling round (2026-09-11, staged not committed
at review), following [[appointment_types_phase2_approved]] and
[[appointment_types_phase2_round2_unstaged_fix]]. Pure documentation +
one new test file, no behavior change:

- `restoricon_core/database.py` / `restoricon_core/models.py`: comment
  and docstring additions only, explaining that `schedule_config.
  working_hours_json` ("Business Hours") is the outer envelope and
  `appointment_types.scheduling_hours_json` narrows it per type (empty
  `{}` = inherit, not never-bookable), and documenting F3: Core never
  compares either field against `Appointment.start_time`/`end_time`
  anywhere — enforcement is entirely client-side in calendar.js.
  Verified zero-code-change by filtering the diff for non-`--`/non-string
  lines (empty result).
- `tests/test_restoricon_core/test_hours_semantics.py` (new, 204 lines):
  5 round-trip tests (business-hours full grid incl. `"sun": None`,
  per-type create/update/revert-to-empty) go through the real
  `SchedulingService` methods with re-fetch assertions, not just
  dataclass construction. Plus one guard-rail test,
  `test_core_does_not_enforce_hours_on_appointment_lifecycle`: sets a
  closed-Sunday grid + narrow per-type window, re-fetches both to prove
  persistence (rules out a false-pass from a silent empty-merge bug),
  then books/updates/status-transitions a 3am UTC Sunday appointment and
  asserts every step succeeds.

**Verdict: APPROVED.** Independently confirmed (not just trusted the
test comments):
- 2026-09-13 is in fact a Sunday (`datetime.date(2026,9,13).strftime('%A')`).
- Read `create_appointment`, `update_appointment`,
  `update_appointment_status` in `scheduling_service.py` directly — zero
  hours-vs-timestamp comparison in any of the three, matching the F3
  claim at the source rather than trusting the docstring.
- `rg -n "working_hours"` / `"scheduling_hours"` across `restoricon_core/`
  — every hit is JSON (de)serialization, DDL, docstring, or route/audit
  field-listing; nothing compares against `start_time`/`end_time`.
- `git status --short` on the 3 touched files showed clean single-letter
  status (`M `, `M `, `A `) — no `MM` index/working-tree divergence like
  the round-2 incident in [[appointment_types_phase2_round2_unstaged_fix]].
- `pytest tests/test_restoricon_core/ -q` → `493 passed in 53.52s`
  (verbatim), matches the claimed count.

**Pattern for future doc-only + guard-rail-test rounds:** the fast, high-
signal check is not re-reading the prose — it's independently opening
the *service method* the test claims has no validation and reading it
yourself. A guard-rail test asserting "X currently doesn't happen" is
only as trustworthy as an independent read of the code it's guarding;
the test author's comment describing the absence is not itself evidence.
