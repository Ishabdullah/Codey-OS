---
name: new525-527-stray-batch3-approved
description: NEW-525 (14 verb-suffix segment guards) + NEW-527 (34 query-param wraps) + Part 3 stray leads/score site in routes.py — approved, but NEW-525's own ledger severity was wrong and got corrected
metadata:
  type: project
---

2026-09-16, `restoricon_core/api/routes.py` + `tests/test_restoricon_core/test_api.py`.
Follow-on to [[new520_522_523_batch1_path_segment_sweep_approved]] and
[[new526_batch2_segment_guard_approved]]. APPROVED, 2 independent verbatim
full-suite runs both reproduced `1894 passed, 1 skipped` (vs 1888 pre-round,
exactly +6 new test functions), proxy vars unset per
[[sandbox_http_proxy_urllib_405_env_artifact]].

**Rule-6 ledger correction made this round — the original NEW-525 finding
undersold its own severity.** `NEW-525`'s ledger text characterized the bug
as "low impact... not a new bug... purely a misleading error-message
framing, no information disclosure." A live negative-control repro (stash
diff, hit a live server pre-fix) proved this wrong for the
`startswith(prefix)+endswith(suffix)`-matched **multi-segment** case
specifically: `POST /api/v1/operations/work-orders/1/2/dispatch` pre-fix
returned `200 {"status": "dispatched"}` and **actually dispatched work
order 1** (silently ignoring the "2" and acting on the wrong record) —
this is the `NEW-526` misrouting class, not a cosmetic message issue. Same
mechanism on `/api/v1/users/1/2/password` would have called
`change_password(user_id=1, ...)` on a malformed path — a credential
mutation, the highest-impact instance. Always distinguish "omitted id
segment" (genuinely low-impact per NEW-525's original scope) from
"multi-segment id" (real misrouting, same severity as NEW-526) when a
round's own ledger entry conflates the two failure modes under one guard
fix — reread what the fix's guard actually blocks before trusting the
original impact rating.

**Live negative-control repro is the load-bearing evidence, not the
regex/grep checks.** Wrote a live server script creating two distinct work
orders, hit the multi-segment path pre-fix (git stash the 2 changed files)
→ 200 + real mutation of the wrong record; popped the stash, re-ran
identical request post-fix → 404, neither record touched. This is the
pattern to reuse: a "does the guard actually block a real bug" question
needs a live repro, not just literal-matching the diff.

**Verification method reused from NEW-526 (regex literal-matching)
partially broke on the one non-literal site:** the compound-suffix
`/stage`|`/transition` route uses a local var
(`_proj_stage_suffix = "/stage" if path.endswith("/stage") else
"/transition"`) inside the slice, not a literal string — a naive regex
for `path\[len\("..."\):-len\("..."\)\]` silently returns no match for
that one site (13/14 machine-verified, not 14/14). Don't report "all N
sites verified programmatically" without checking whether every site
actually matched the extraction pattern — verify by eye whenever a site's
match count looks short, then say "13 automated + 1 manually traced," not
round up. Manually traced this one: prefix len 28, so `.../5/stage` →
`path[28:-6]` → `"5"`, `.../5/transition` → `path[28:-11]` → `"5"`;
omitted-id (`.../stage` alone) → `path[28:-6]` → `""` on both arms,
correctly rejected.

**Test-rigor question (status-code-only vs NEW-526's write-verification
requirement) — worth restating the general rule:** NEW-526's malformed-path
test needed to assert neither record changed because post-fix the request
still entered a handler that *could* theoretically still write (matched a
different, more permissive route). Here, post-fix the 404 comes from the
router's terminal catch-all — the block doesn't match at all, and the
sibling single-segment catch-all (`.../work-orders/{id}`) also requires a
slash-free remainder, so literally no handler runs. Status-code-only
assertions are sufficient when you've independently confirmed (by reading
every intervening route, not assuming) that no other route can match the
malformed path either — that confirmation is the part that must be done
explicitly, not skipped because "it looks like NEW-526's pattern."

**Real remaining gaps, logged as Warnings, not blocking:**
1. The new `test_api_new525_work_orders_multi_segment_id_is_generic_404_not_misrouted`
   test only covers the 5 work-orders verb sites. The 9 users/* and
   projects/* sites sharing the identical vulnerable shape (confirmed via
   the live repro's `/password` reasoning) are untested for the
   multi-segment case specifically — only the omitted-id case is tested
   for those 9. Cheap to add 3 rows (`users/.../password`,
   `operations/projects/.../summary`, and specifically
   `operations/projects/.../transition` — the compound suffix's other
   arm, since the existing 404 table only exercises `/stage`).
2. `_parse_int_query_param`'s `minimum=0` default clamp is harmless for
   33 of the 34 NEW-527 sites (all are entity ids where 0 never matches a
   real row) but is NOT harmless for `GET /api/v1/users?active=`: `active`
   is a real boolean-ish column where 0 is meaningful. Post-fix,
   `?active=-1` clamps to 0 and returns **all inactive users**, where
   pre-fix it returned an empty list — a malformed input silently produces
   a plausible-but-wrong result set instead of an empty one. Not an authz
   bypass (the caller can already request `?active=0` directly), no test
   regression. Worth a `NEW-###` for the record, not a fix in this round.

**Confirmed genuinely out of scope, not silently touched:** grepped the
diff for `contacts` and `json_body.get(` int-wraps — `NEW-528`
(`int(json_body.get("subcontractor_id", 0))` at the work-orders dispatch
site) and `NEW-529` (the 2 contacts external-id routes) are both
untouched, as claimed.
