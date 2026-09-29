---
name: b8_10a_followup_actions_approved
description: B8.10a Complete/Cancel/Snooze task-action wiring on sales portal + Customer 360 -- APPROVED round1
metadata:
  type: project
---

2026-09-23. `restoricon_core/api/web_surfaces.py` (taskActionButtons/taskTypeBadge
shared renderers + completeTaskAction/cancelTaskAction/snoozeTaskAction), plus
`sales_rep_portal.md` NEW-622 doc fix and 9 new tests (2 route-level in
test_crm_sales_engine.py, 7 render-shape in new test_b8_10a_followup_actions.py).
Pure UI wiring onto pre-existing, already-tested routes (POST .../complete,
POST .../update) -- no new routes, no RBAC change, no money computation.

All claims independently verified, not just read:
- UTC timezone-consistency of snoozeTaskAction genuinely holds: live node repro
  with `TZ=America/Los_Angeles` confirmed getUTCDate/setUTCDate/toISOString are
  TZ-independent for both the existing-due_date path (`2026-09-20` ->
  `2026-09-21`) and the null-due_date fallback path (`new Date()` + UTC math).
  routes.py:3016 confirmed the server buckets via
  `datetime.now(timezone.utc).date()` -- claim about matching reference frames
  checks out.
- `escapeHtml(JSON.stringify(...))` onclick-arg pattern citation verified
  against real precedent (deleteSubcontractor line 2902, openPermModal 4197,
  deleteUser 4201, deleteAppointmentType 4743) -- genuinely the same combo, not
  superficially similar.
- update_task (crm_service.py:2333) confirmed to `setattr` only allowed_fields
  present in the update dict onto the pre-loaded `task` object before writing
  the full row -- a due_date-only POST genuinely leaves status untouched. The
  new route-level test asserts this directly (not just via comment).
- NotificationService (services/notification_service.py) confirmed to be
  outbound-email-only (send_email/send_calendar_invite/send_calendar_cancellation,
  all POST to an Aigentik HTTP endpoint) -- no notification-entity/store exists,
  so the sales_rep_portal.md doc correction is factually accurate.
- Disclosed-but-not-fixed item confirmed accurate via diff: the B8.10 exit
  criterion line ("...a rep can see and pause any pending automated follow-up
  before it fires") is genuinely untouched by this diff -- only the
  Notification-center bullet above it was corrected.
- `node --check` on the actual extracted `<script>` block from a live
  `_render_sales_portal()` call passed (not trusted from implementer's claim).
- 7 new render-shape tests are real assertions on extracted HTML/JS substrings,
  not tautologies -- e.g. the "paused" test checks the string is absent from
  the *entire rendered surface*, and the c360 Tasks-panel test explicitly notes
  and avoids a `");`-vs-`</thead>');` substring-overshoot trap.
- Full suite: 2370 passed, 1 skipped, 69 warnings in 340s -- matches claimed
  baseline 2361 -> 2370 (+9) verbatim.
- No new dependency; node was already test-time-only pre-existing
  (test_web_surfaces_js_syntax.py), not newly introduced this round.

Additional checks prompted by advisor (all cleared, no findings):
- c360 Tasks panel fetches `/api/v1/crm/tasks?customer_id=...` -> same
  `list_tasks` route as the dashboard Follow-ups panel, returns full
  `Task.to_dict()` (= `asdict()`, all fields) -- not a trimmed shape, so
  `taskActionButtons`/`taskTypeBadge`'s extra field reads (`id`, `task_type`,
  `trigger_source`, `rule_name`) are genuinely populated in both surfaces.
- `currentCustomer360Id`/`loadCustomer360` both declared inside the same
  `_render_sales_portal()` script block (line 6378), not a sibling surface --
  no ReferenceError risk.
- due_date format risk for automation-tagged tasks: only current
  trigger_source-setting Task generator is `generate_cadence_tasks`
  (trigger_source="pipeline_stage_transition"), and it never sets due_date
  (always None) -- so every live automation task today hits the
  already-UTC-verified null-due_date fallback path in snoozeTaskAction, not
  the date-only-string parse path. Not a live bug. Worth a Warning for the
  record: if a future automation rule ever sets due_date from a full
  ISO-timestamp helper (e.g. `utc_now_iso()`) instead of a date-only string,
  `currentDueDate + 'T00:00:00Z'` -> Invalid Date -> Snooze silently breaks
  on exactly the rows the feature is for. No fix needed now since nothing
  reachable produces that shape.

Recommended folding the disclosed "pause" exit-criterion doc-drift fix into
this same round rather than deferring to NEW_ISSUES.md -- it's two lines
below the bullet already rewritten this round in the same doc, and leaving
it produces a doc that says the feature does the opposite of what the code
implements.

First B8.10 sub-round to clear round 1 with zero code findings; one Warning
(due_date format fragility, not live-reachable) and one doc-scope
recommendation (fold in the exit-criterion line) noted for the coordinator.
