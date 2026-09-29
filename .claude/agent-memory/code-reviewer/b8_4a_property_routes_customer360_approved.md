---
name: b8_4a_property_routes_customer360_approved
description: B8.4a Property API routes + sales-portal Customer 360 fan-out modal — APPROVED via live JS execution, not just diff-reading
metadata:
  type: project
---

2026-09-17. Reviewed uncommitted diff: `restoricon_core/api/routes.py` (3 new
Property routes) + `restoricon_core/api/web_surfaces.py` (Customer 360
client-side fan-out modal inside `_render_sales_portal()`). APPROVED, no
Warnings.

What made this round solid, worth repeating:
- Route diff was a byte-for-byte structural match of the existing
  `/opportunities/<id>/update` etc. pattern (`_parse_int_path_segment` on
  the stripped-suffix substring guarded by `"/" not in ...`). Confirmed
  malformed `/api/v1/properties/1/2/update` genuinely 404s via a live
  `router.handle_request()` call, not just by reading the guard.
- `Property(**json_body)` construction verified against the real
  dataclass (`models.py` — field is `existing_systems`, not
  `existing_systems_json`, matching implementer's own disclosed catch).
- **Went beyond [[vm_harness_silent_stub_gaps]] risk**: rather than
  trusting the file's string-shape JS tests (`assert "Promise.allSettled("
  in fanout_js` etc — the exact style that let NEW-538/join('\n') through
  before), extracted the real rendered `<script>` block and ran
  `loadCustomer360()`/`renderCustomer360()` live under Node with a mocked
  `fetch`/DOM, across 3 scenarios: (1) one panel 403s → only that panel
  shows "No access.", others render fine; (2) one panel 401s → redirect
  to `/admin/login` fires; (3) one panel's fetch literally throws → no
  uncaught rejection, that panel alone degrades to "Failed to load.".
  All 3 behaved exactly as claimed. This is the reusable pattern other
  reviews should copy for any new `Promise.allSettled`/fan-out claim in
  this file — a passing string-shape test does not prove the runtime
  behavior graph, only that certain substrings exist.
- `node --check` on the actual extracted script: clean.
- Full suite re-run with proxy vars unset: `2129 passed, 1 skipped, 0
  failed` — matches implementer's claimed baseline exactly (their 2127
  passed + 2 "flaky" failures = 2129 total; this run's flaky
  `test_resource_bus.py` case happened to pass). `git diff --stat --
  tests/test_resource_bus.py core/resource_bus.py` confirmed empty
  (genuinely untouched), matching [[test_resource_bus_aging_flaky_under_load]].
- New "Customers" list panel (not explicitly speced) judged reasonable,
  necessary plumbing — a `View 360` entry point had to live somewhere,
  and it's the same shape as every other portal list panel.
- NEW-568 (`list_customers` has no per-rep scoping) correctly disclosed
  in an in-code comment rather than silently fixed or silently dropped,
  matching rule 8.

Harness note: a background Node process kept running after the async
IIFE finished (this file's known 12s `setInterval` periodic refresh, see
[[d3_sales_portal_periodic_refresh_approved]]) — don't be alarmed if a
live-repro harness against this file's rendered script doesn't exit on
its own; kill it once you have the output rather than waiting on it.
