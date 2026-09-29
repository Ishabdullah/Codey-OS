---
name: appointment-types-phase4-concurrency-cap-approved
description: Final scheduling round Phase 4 — SchedulingService concurrency-cap enforcement (_assert_within_concurrency_cap); APPROVED w/ 2 warnings
metadata:
  type: project
---

Phase 4 of the final scheduling round (2026-09-11, staged not committed at
review), following [[appointment_types_phase2_approved]] and
[[appointment_types_phase3_hours_semantics_approved]]. Adds Core's first
overlap/concurrency enforcement (`_assert_within_concurrency_cap`) called
from 3 sites: `create_appointment` (status==confirmed only),
`update_appointment` (on MERGED post-update values), `update_appointment_status`
(on transition to confirmed, using the row's stored times).

**Verdict: APPROVED, no blockers.** Independently verified, not trusted:
- Overlap predicate byte-for-byte matches `~/Codey-Aigentik/calendar.js:370-379`
  `hasConflict()` — buffer expands only the EXISTING row's window
  (`row_start - buffer`, `row_end + buffer`), new interval unbuffered,
  `new_start < aEnd && new_end > aStart`. Traced 09:30-11:30 buffered-window
  example by hand: 11:15-11:45 rejects, 11:45-12:15 allows (half-open bound
  exact, no off-by-one).
- All 3 call sites read `restoricon_core/services/scheduling_service.py`
  directly: cap check runs inside the SAME `with conn:` block as the write,
  before the INSERT/UPDATE. `update_appointment` computes merged_status/
  merged_start/merged_end/merged_type_id from `updates.get(k, row[k])`
  BEFORE the `with conn:` — checked against what the row WILL become, not
  its current state. `upsert_appointment` delegates to `update_appointment`,
  inherits the guard for free (no separate cap-check code needed there).
- **Mutation-tested 2 of the implementer's claimed guards myself** (not
  just re-read them): stripped `exclude_appointment_id=` from the
  `update_appointment_status` call → `test_reconfirming_already_confirmed_row_at_full_slot_succeeds`
  failed as expected; replaced `merged_status = updates.get("status", row["status"])`
  with `row["status"]` (i.e. lost the updates-dict override) →
  `test_update_appointment_status_only_confirm_onto_full_slot_rejected`
  failed as expected (`DID NOT RAISE`). Restored via `git checkout --`
  both times — confirmed clean via `git diff --cached --stat` unchanged
  (166 insertions) and `git diff` empty afterward. Safe because the file
  was already staged (index has the target state) — see
  [[git_checkout_path_wipes_uncommitted_diff]] for why this only works
  when nothing unstaged is at risk.
- `NEW-311` citation for the acknowledged TOCTOU (no `BEGIN IMMEDIATE`,
  two concurrent writers can both pass the check before either commits)
  is a legitimate application, not a misapplied precedent — re-read
  NEW-311's actual text: it's a general "no BEGIN IMMEDIATE DB-layer
  change, single-user-deployment tradeoff accepted, revisit if
  multi-process" ruling, and this is a straightforward instance of that
  same read-then-write race class, not a distinct new risk being waved
  through under an unrelated label.
- Live DB checked via **read-only URI connection** (`file:...?mode=ro`,
  per `NEW-472`'s lesson about accidental WAL-checkpoint side effects) —
  `appointments` table is genuinely 0 rows right now, so the
  implementer-flagged "legacy over-cap rows lock out all future edits"
  gap is theoretical today, not a live landmine.
- `pytest tests/test_restoricon_core/ -q` → `509 passed in 86.58s` verbatim,
  matches the claim exactly.
- Route-level 400: all 4 appointment write routes (`POST /appointments`,
  `/appointments/upsert`, `/appointments/{id}/status`,
  `/appointments/{id}/update`) share one `try` block ending in the same
  `except ValueError as ve: return 400, ...` at `routes.py:2188` —
  confirmed by reading the route dispatch code directly.

**Warnings handed back (non-blocking):**
- Only ONE route-level test exists (`test_route_post_appointment_over_cap_is_400`,
  the POST-create path). The `/status` and `/update` POST routes share the
  same exception handler (verified by reading the code) but have no
  dedicated route-level regression test of their own — a future edit to
  either route's dispatch code could silently stop wrapping ValueError and
  nothing would catch it until it happened in production.
- Three implementer-flagged gaps (TOCTOU distinct-from-NEW-311 note,
  pairwise-overlap over-rejection at cap>=2, legacy-over-cap rows
  permanently blocking future edits) exist only as inline code comments
  right now — NOT yet logged as their own `NEW-###` entries in
  `NEW_ISSUES.md` as rule 8 requires. Confirmed via grep: no
  "pairwise"/"legacy over-cap" hits in `NEW_ISSUES.md` as of this review.
  This is expected to happen at the coordinator's step-5 ledger update,
  not a review blocker, but flagging explicitly so it isn't silently
  skipped when the round closes.

**Pattern for future overlap/concurrency-check reviews:** don't trust a
claimed byte-for-byte JS/Python parity claim from prose — open the cited
JS function yourself and diff the actual boundary logic (which side gets
the buffer, half-open vs closed) by hand-tracing one concrete example.
Also: mutation-testing a reviewer-chosen subset of the implementer's own
"break it and watch it fail" claims is cheap (single string replace + git
checkout --) and catches wrong self-report — worth doing on every
concurrency/exclude-self-guard round, not just trusting the paragraph.
