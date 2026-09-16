---
name: new526-batch2-segment-guard-approved
description: NEW-526 27-site segment-count-guard + _parse_int_path_segment fix in routes.py — approved, fully machine-verified via regex + live negative-control repro on 2 sites
metadata:
  type: project
---

2026-09-16, `restoricon_core/api/routes.py` + `tests/test_restoricon_core/test_api.py`.
27 sub-action routes previously matched via bare `startswith(PREFIX) and
endswith(SUFFIX)` with no check on segment count between them, then parsed
the id via `path.split("/")[-2]` — a malformed path with an extra numeric
segment (e.g. `POST /api/v1/customers/5/99/update`) silently acted on the
LAST segment (99), not the URL-named one (5), no 404. APPROVED.

**Verification method that scaled well for a 27-site sweep — reuse this
pattern:** rather than manually spot-checking 8-10 of 27 near-identical
sites (error-prone, easy to get bored and miss one), wrote a regex that
extracted the `startswith`/`endswith` literals from all 27 blocks AND the
guard's `path[len(...):-len(...)]` literals AND the final
`_parse_int_path_segment(path[len(...):-len(...)], "varname")` call's
literals, and asserted all three literal-pairs match per site. Caught
100% of sites (27/27) programmatically, zero mismatches — stronger
evidence than manual spot-checking and much faster. Cross-checked the
extracted site list against the new test's `_NEW526_BATCH2_SITES` table
(also 27 entries) — exact 1:1 match by prefix+suffix+varname.

**Live negative-control repro (the highest-value check on this task) —
reproduced independently, not just read about:** stashed the working
diff, spun up a live `RestoriconAPIServer`, created two distinct records,
sent the malformed path against the PRE-fix code, and got silent
wrong-record writes both times: `POST /api/v1/customers/1/2/update` (200,
renamed customer 2, not 1) and `POST /api/v1/subcontractors/1/2/qualification`
(200, qualified subcontractor 2, not 1). Popped the stash, re-ran the
identical requests against the fixed code: both now 404, neither record
touched. This is the gold-standard verification pattern for "prove the
described bug was real" claims — see also
[[new481_textnode_escaping_second_half_approved]] for the general
negative-control principle.

**New test's assertions are non-vacuous:** `test_api_new526_batch2_malformed_extra_segment_is_404_and_no_write_happens`
seeds two distinguishable records per case (5 cases: 2 writes, 2 deletes,
1 read-only), asserts 404, THEN re-fetches both records and asserts
neither changed (or, for the read-only finance/pnl case, asserts the
route still works on the correct single-segment path). Not a
status-only test.

**Caught one thing worth flagging in every batch of this kind:** two
routes at `restoricon_core/api/routes.py` ~1599/1612
(`POST /api/v1/contacts/{id}/update` and the `/delete`+`DELETE` pair)
share the exact same missing-guard/`[-2]`-index bug but intentionally
accept a non-numeric `external_id` in the id slot, branching on
`id_str.isdigit()` before falling back to `get_contact_by_external_id`.
A bare `_parse_int_path_segment` swap would break that legitimate
external-id path — confirmed `_parse_int_path_segment` (line 106) raises
on non-digit input with no such fallback. Correctly left out of this
batch and needs its own new `NEW-###` (told coordinator to log, not fix).

**Test suite: exact verbatim reproduction** — `1888 passed, 1 skipped`
(vs `1886` from the prior batch-1 round, i.e. exactly +2 for the two new
test functions), proxy vars unset per
[[sandbox_http_proxy_urllib_405_env_artifact]].

**Gotcha:** attempted `pkill -f "pytest tests/ -q"` to clean up a
redundant duplicate background test run I'd started while waiting — was
denied by the sandbox's auto-mode classifier ("Interfere With Workloads").
Correctly did not retry/work around it; just let the duplicate run finish
on its own. Reinforces CLAUDE.md rule 3 even for a reviewer's own
scratch processes, not just daemon-lifecycle code under review.
