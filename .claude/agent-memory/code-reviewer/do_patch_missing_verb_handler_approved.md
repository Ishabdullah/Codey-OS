---
name: do-patch-missing-verb-handler-approved
description: server.py do_PATCH missing-handler fix (stdlib 501 before routes.py) — approved 2026-09-11
metadata:
  type: project
---

`restoricon_core/api/server.py`'s `RestoriconRequestHandler` had `do_GET`/`do_POST`/
`do_PUT`/`do_DELETE` but no `do_PATCH` — every real PATCH request (including the
Calendar UI's staff-schedule edit form, `web_surfaces.py:3737`) got a bare stdlib
501 before ever reaching `routes.py`/`APIRouter`. Unit tests that call
`APIRouter.handle_request()` directly can never catch this class of bug since they
bypass `BaseHTTPRequestHandler` entirely — only a real-socket test (the `api_server`
fixture's live `RestoriconAPIServer` + `urllib.request`) exercises the actual verb
dispatch table. Watch for this same gap on any future new HTTP verb.

Fix (`do_PATCH(self) -> None: self._dispatch("PATCH")`, 3-line diff) verified:
- matches exact style/placement of the other 4 `do_*` handlers, no special-casing
  needed elsewhere.
- verb-coverage claim re-verified independently: grepped web_surfaces.py's method:
  literals (GET/POST/PUT/DELETE/PATCH, no HEAD/OPTIONS) and every Aigentik
  `coreRequest()` call site (GET/POST only) — matches implementer's claim exactly.
- negative control self-run: reverting `do_PATCH` alone and rerunning the new test
  reproduces `json.decoder.JSONDecodeError: Expecting value` in the test's own
  `make_request()` helper (from parsing the stdlib's "501 - Server does not
  support this operation." HTML error page as JSON) — not a clean
  `assert status != 501` failure. This is the correct/expected failure signature
  for this bug class; confirm this exact signature (not a different failure mode)
  when reviewing similar "verb never reached the router" fixes.
- `api_server` fixture teardown is a tracked handle + `server.stop()`, no
  kill-by-name (rule 3 clean).
- 557 passed, `pytest tests/test_restoricon_core/` — reproduced verbatim, matches claim.

Also confirmed real: `PATCH /api/v1/staff-schedules/{id}` (`routes.py` ~line 1470-1472)
calls `updated.to_dict()` with no None-guard on `update_staff_schedule()`'s
`Optional[StaffSchedule]` return — was DEAD CODE before this fix (PATCH never
reached routes.py), now REACHABLE (real 500 risk on a bad id). Already tracked as
`NEW-491` in `NEW_ISSUES.md` (Confirmed) — this round's fix changes NEW-491 from
theoretical to live-reachable; worth a status/severity note in the ledger even
though not fixed in this round (out of scope here).

Lesson: when reviewing a "missing verb handler" fix, always (1) independently
re-grep every call-site source for the actual verb set used rather than trusting
the implementer's grep summary, and (2) self-run the negative control rather than
just reading the claimed failure signature — the exact exception type/message
matters for confirming it's really the same bug, not a coincidental different failure.
