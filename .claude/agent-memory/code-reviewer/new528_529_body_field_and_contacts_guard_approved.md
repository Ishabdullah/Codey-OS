---
name: new528-529-body-field-and-contacts-guard-approved
description: NEW-528 _parse_int_body_field (14 sites) + NEW-529 contacts segment-count guard — approved w/ 1 Warning (undisclosed missing test for one behavior-change arm)
metadata:
  type: project
---

2026-09-16, `restoricon_core/api/routes.py` + `tests/test_restoricon_core/test_api.py`.
Follow-on to [[new525_527_stray_batch3_approved]], closing the two findings that
round explicitly logged as out-of-scope. APPROVED. Verbatim full-suite run:
`1903 passed, 1 skipped in 241.15s` — exactly +6 from the 1897 baseline
(`a77287d`), matching the 6 new test functions, proxy vars unset per
[[sandbox_http_proxy_urllib_405_env_artifact]].

**NEW-528 core mechanism verified two ways, not just read:** confirmed
`int(None)` raises `TypeError` (not `ValueError`) directly in this Python
version, confirmed `handle_request`'s except-clause order is
`PermissionError` → `ValueError` → `Exception` (so bare `TypeError` falls to
the generic 500), then did a live stash/pop negative-control repro against 2
of the 11 "unguarded" sites (`compliance/scan` threshold_days=null,
`marketing/reviews/request` customer_id=null) — both returned raw
`Internal server error: int() argument must be a string...` (500) pre-fix.
Also verified all 14 `_parse_int_body_field(json_body, name, default)` call
sites' `name`/`default` pairs match the original `json_body.get(name,
default)` shape exactly via a regex extraction — no silently-mismatched key
or changed default anywhere.

**NEW-529's fix correctly diverges from NEW-526's bare-swap shape and was
verified live, not just read.** Same stash/pop repro: pre-fix,
`POST /api/v1/contacts/{a}/{b}/update` silently renamed contact B to
"HACKED" (real misrouting, not just a message issue); post-fix, 404 + both
contacts unchanged. The new segment-count guard
(`path[len(PREFIX):-len(SUFFIX)]` truthy + no `/`) added to the route-match
condition only, leaving the `isdigit()`/`get_contact_by_external_id`
branching inside the body completely untouched — confirmed the external_id
path (`aigentik-abc-123`) still resolves correctly post-fix.

**Gap the advisor caught that I'd have missed without a second pass: the
disclosed "intentional behavior change" (DELETE on a path literally ending
in `/delete`, e.g. `DELETE /api/v1/contacts/5/delete`, pre-fix deleted the
contact via Python's `and`/`or` operator-precedence quirk in the original
one-liner condition) has NO test covering it at all** — grepped every
`method="DELETE"` in the diff's new tests, only one exists
(`/{cid}/99` multi-segment). A brief that explicitly asks "confirm the new
dedicated test covers exactly this case" deserves an actual check that the
test exists, not just that the reasoning about precedence is correct. Live
stash/pop repro on this exact case: pre-fix `DELETE .../{id}/delete` →
`200 {"deleted": true}`, contact actually gone; post-fix → `404 Endpoint not
found`, contact confirmed still present via a follow-up GET. The narrowing
itself is correct and intentional (confirmed live), but it removed a
previously-functional (if accidental) delete path with zero test coverage
of the removal — logged as a Warning requiring one added test row
(`DELETE {id}/delete` → 404 + record-intact), not a blocker, since the
live repro closes the "is the behavior actually right" question that the
missing test should have closed.

**Two NEW-### log-only items surfaced, correctly left unfixed in this
round:**
1. `DELETE /api/v1/contacts/delete` (a literal path where the id segment
   IS the string `"delete"`) is broken both pre- and post-fix — the bare
   arm's guard matches (`path[len(PREFIX):]` = `"delete"`, truthy,
   slash-free), but the unchanged ternary then sees `endswith("/delete")`
   and derives `id_str = path.split("/")[-2]` = `"contacts"`, not
   `"delete"`. Pre-existing bug, untouched by this diff, needs its own
   `NEW-###`.
2. `/api/v1/ai/chat`: `max_tokens: null` now cleanly 400s but the adjacent
   `temperature: null` still raw-500s via untouched
   `float(json_body.get(...))` — same endpoint, split fix coverage. Worth
   noting in the eventual float-sites finding rather than just "13 float
   sites, unscoped."

**Reused pattern, reconfirmed useful:** stash/pop live negative-control
repro (not just literal-matching the diff or trusting a single
self-reported repro) is the right tool whenever a fix's claimed severity
or claimed pre-fix behavior is the load-bearing evidence — see also
[[new526_batch2_segment_guard_approved]] and
[[new525_527_stray_batch3_approved]]. This round additionally shows the
tool must be pointed at *every* disclosed behavior change in the brief,
not just the headline one — the 500-leak and misrouting claims were both
well-tested already; the operator-precedence DELETE claim was the one
with a coverage gap, and it wasn't the one that looked most novel.
