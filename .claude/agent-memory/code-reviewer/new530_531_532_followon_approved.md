---
name: new530-531-532-followon-approved
description: NEW-530 work-orders catch-all isdigit() guard + NEW-531 multi-segment 404 test extension + NEW-532 active-filter minimum=None clamp fix — approved, all three independently verified
metadata:
  type: project
---

2026-09-16, `restoricon_core/api/routes.py` + `tests/test_restoricon_core/test_api.py`.
Follow-on to [[new525_527_stray_batch3_approved]] (commit `5c559ca`), closing the
3 findings that round's own review spun off. APPROVED. Verbatim full-suite run:
`1897 passed, 1 skipped in 292.72s` — exactly +3 from the 1894 baseline, matching
the 3 net-new test functions (one test was renamed, not added).

**Trailing-slash deviation claim was correct — worth the direct verification, not
just trusting it.** Implementer claimed `GET /api/v1/operations/work-orders/`
normalizes via `handle_request`'s `path = parsed_url.path.rstrip("/")` (line 339,
top of the function, before all route matching) to the bare list-endpoint path,
so it hits the exact-match list route (`if path ==
"/api/v1/operations/work-orders":`, line 2197) before ever reaching the catch-all
(line 2286) — both pre- and post-fix. Verified by reading both line numbers and
confirming the list route appears earlier in the same `if/elif` chain. Correct;
dropping the untestable trailing-slash assertion and documenting the reasoning in
the test docstring instead was the right call, not a coverage gap.

**Query-param-fix safety check that generalizes: when a shared helper's default
changes (e.g. `minimum: int = 0` → `Optional[int] = 0`), grep every call site for
positional args past the ones that changed meaning, not just the new call site.**
Extracted all ~57 `_parse_int_query_param(...)` call expressions via a `python3`
regex (Termux's `grep`/`find` are broken here — aliased, crash with `-G:` /
`-S:` shared-library errors, see [[project_termux_grep_find_alias_broken]] in
user memory) and confirmed zero positional 4th-argument calls exist; the only
`minimum=` keyword usage besides the new `minimum=None` is pre-existing
`minimum=1, maximum=1000` on limit params. This is the check that would have
caught a latent bug if any call site had passed `minimum` positionally where
`None` now flows in silently.

**Test genuinely discriminates the bug (traced the underlying query, not just
trusted the assertion reads right):** `restoricon_core/auth.py`'s `list_users`
does `WHERE active = ?` whenever `active is not None`. Pre-fix, `?active=-1`
clamps to 0 → returns the real inactive user (looks like a plausible, wrong,
non-empty result — the dangerous kind of bug). Post-fix, `-1` passes through
unclamped → `WHERE active = -1` → matches nothing. The test's positive control
(seed one genuinely inactive user, confirm `?active=0` finds it) before the
negative assertion (`?active=-1` → empty) is exactly right — it rules out the
test passing vacuously because no inactive user existed.

**Cross-referencing the site-inventory table against the source finding's own
ledger entry, not just eyeballing plausibility, is the right verification
method for "did you cover all N sites" claims (same pattern as
[[new526_batch2_segment_guard_approved]]'s regex-literal-matching).** The
NEW-531 10-row table was checked against NEW-525's own "14 sites total" ledger
breakdown (5 users + 4 projects + 5 work-orders, with `/stage`/`/transition`
as one compound site) rather than trusted at face value.
