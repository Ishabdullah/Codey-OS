---
name: b8_3_lead_convert_stage_analytics_changes_requested
description: B8.3 (Lead & Pipeline UX) round 1 review — CHANGES REQUESTED, convert_lead_to_opportunity drops the customer_id writeback onto Lead
metadata:
  type: project
---

Round 1 of B8.3 (`convert_lead_to_opportunity`, NEW-557 guard,
`get_stage_duration_analytics`, `/api/v1/leads/<id>/convert`,
`/api/v1/sales/pipeline-stuck-analytics`, sales-portal kanban/lead-detail/
create-lead JS) got **CHANGES REQUESTED**, not approved, despite passing
the full suite (2118 passed, 1 skipped, verbatim reproduced) and a clean
`node --check` on the real rendered `<script>` block.

**Blocking bug (live-reproduced, not caught by the new test suite):**
`convert_lead_to_opportunity` creates a `Customer` when `lead.customer_id`
is null, links it to the new `Opportunity`, marks the lead `converted` —
but never writes the new `customer_id` back onto the `Lead` row.
`update_lead`'s `allowed_fields` already includes `"customer_id"`
(crm_service.py:905); the closing call only sends
`{"status": "converted"}`. Repro:
```
opp.customer_id = 1
lead.customer_id AFTER conversion = None
lead.status AFTER conversion = converted
```
`test_convert_lead_with_no_customer_creates_one` asserts on
`opp.customer_id` and the created `Customer`'s fields but never re-fetches
the lead to check its `customer_id` — a real coverage gap, not just an
implementation gap. Fix is one line: pass `"customer_id": customer_id`
alongside `"status": "converted"` in that final `update_lead` call. This
also closes half of the partial-failure/retry-duplication risk in the
same method (see below).

**Docstring overreach caught by advisor, not by my own read:** the
method's docstring cites `NEW-311`'s "no BEGIN IMMEDIATE, single-write
races are an accepted single-deployment tradeoff" ruling to wave off
*all* non-atomicity concerns. `NEW-311`'s actual accepted scope is
read-then-write **race windows** between concurrent requests — a
different failure class from a **sequential partial failure inside one
call** (e.g. `create_opportunity` raising after `create_customer`
committed, or `update_lead` failing after `create_opportunity`
committed). In the second case the lead never reaches `status ==
"converted"`, so a retry hits no guard and can produce two Opportunities
off one Lead — this is not covered by `NEW-311`'s reasoning and needs its
own disclosure/NEW-### (rule 8), or the docstring's claim needs
narrowing. The write order chosen (customer → opportunity → mark lead
converted last) is correct and shouldn't be reordered — marking the lead
converted before the opportunity exists would strand a "converted" lead
with nothing linked and no way to retry.

**Warning, same-round fix:** `get_stage_duration_analytics`'s `_parse_iso`
calls on the primary walk (`create_row["timestamp"]`, each
`stage_transition` row's timestamp) are bare — no try/except — while the
fallback path (`stage_entered_at`/`created_at`) is explicitly wrapped with
a comment about pre-existing malformed-data tolerance. A malformed
timestamp on a create/transition row (same data-integrity class the
author already reasoned about for `_safe_details`) raises out of an
analytics GET instead of degrading gracefully like the fallback path
does.

**Warning, doc-accuracy only:** when a stage_transition row's
`changed_fields.pipeline_stage.new` is `None` (NEW-559 shape), the walk
`break`s and buckets the opportunity as chain-broken/excluded from
`opportunities_with_full_chain` — but duration values already appended to
`stage_hours` from *earlier, valid* rows in that same opportunity's walk
are NOT retracted. So a chain-broken opportunity can still contribute
partial data points to `avg_hours_per_stage` while being counted in the
broken bucket. The docstring's "excluding that row" undersells this —
it's excluding the broken row's own duration point, not the
opportunity's prior contributions.

**Confirmed clean (full independent verification, not diff-reading):**
- `build_audit_details(after=opp.to_dict())` (no `fields=` domain) —
  traced the source: with `before=None`, every key of `after` lands in
  `changed_fields` as `{"old": None, "new": <v>}` unconditionally, so
  `changed_fields.pipeline_stage.new` is present on `create` rows. Exact
  match to the implementer's claim.
- SQL injection: chunked `IN (...)` placeholder string is pure `?`-count
  join; `batch` (real int ids) passed as bound params.
- `list_opportunities(actor)` scoping genuinely bounds the audit-log
  `entity_id IN (...)` read — traced the narrowing logic, no leak path.
- Every real `Opportunity(...)` construction site in the repo
  (`crm_service.py:1203,1377,4668`; `routes.py:993`; two test files)
  supplies `customer_id` explicitly — NEW-557's "verified via grep" claim
  holds.
- Timestamp format: `audit_log.timestamp` is written via
  `utc_now_iso()` = `datetime.now(timezone.utc).isoformat()`, which
  already carries a `+00:00` offset (never `Z`), so `.replace("Z",
  "+00:00")` is a documented no-op and `fromisoformat` parses cleanly —
  consistent with every other write site.
- `/api/v1/leads/<id>/convert` path guard correctly rejects
  `/api/v1/leads/1/2/convert` (verified with a literal Python slice
  repro) — matches the existing `/score`/`/claim`/`/update` pattern
  exactly, including that same pattern's pre-existing lack of an
  empty-segment truthy check (not a regression this diff introduced).
- `node --check` on the real rendered `<script>` block from
  `_render_sales_portal()` (extracted via calling the function directly,
  not reading the Python source) — exit 0, no syntax errors.
- Create-lead form only sends real `Lead` dataclass field names (checked
  against `models.py` directly); `claimOpportunity` is reused from
  existing code, not reimplemented; the LOST-stage prompt fires and
  populates `body.lost_reason` before the `fetch` call, not after a 400.
- NEW-558's "Claim first" kanban gate is genuinely client-side-only by
  *design* — `NEW_ISSUES.md`'s own entry documents the coordinator's
  2026-09-17 decision that this round only gates the new kanban's entry
  point, not `transition_opportunity_stage` server-side. Not a gap to
  flag; already disclosed and correctly scoped.
- `python -m pytest -q` verbatim: `2118 passed, 1 skipped, 69 warnings in
  312.75s` — matches implementer's claim exactly.

**Pattern for future reviews:** a docstring citing a prior decision
(`NEW-311`, `NEW-533`, etc.) as covering a *new* multi-write method's
non-atomicity is not automatically valid — re-derive what the cited
decision's accepted failure class actually was (concurrent race vs.
sequential partial-failure-then-retry are different animals) rather than
trusting the citation. Also: a passing new unit test suite for a
multi-write conversion method can still miss that one of the writes
silently doesn't happen — check the *other* side's post-state (here:
re-fetch the Lead, not just the Customer/Opportunity that were the
method's stated purpose), not just the object the method returns.
