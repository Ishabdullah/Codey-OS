---
name: new520-522-523-batch1-path-segment-sweep-approved
description: 26-site + 1 mechanical int()->_parse_int_path_segment/_parse_int_query_param sweep in routes.py — approved, but surfaced a route-match-looseness bug pattern worth checking on every future batch like this
metadata:
  type: project
---

2026-09-16, `restoricon_core/api/routes.py` + `tests/test_restoricon_core/test_api.py`.
Mechanical replacement of 26 bare `int(path.split(...)[n])`-style path-segment
parses (plus 1 query-param site, `NEW-523`) with the shared
`_parse_int_path_segment`/`_parse_int_query_param` helpers added by `NEW-520`.
APPROVED — verbatim `1886 passed, 1 skipped` reproduced (proxy vars unset per
[[sandbox_http_proxy_urllib_405_env_artifact]]), all 26 sites' index expressions
confirmed unchanged, DDL claim (`users.id AUTOINCREMENT`) verified directly,
test assertion is exact-dict-equality so genuinely non-vacuous (no revert
negative-control needed when the assertion already checks message body, not
just status — see [[new481_textnode_escaping_second_half_approved]] for when a
revert *is* needed).

**New bug-pattern this round taught me — check it on every future
"wrap N call sites with a shared helper" batch:** a mechanical sweep that only
touches the `int(...)` call itself, without auditing the surrounding
`startswith(...)/endswith(...)` route-match condition, can leave a
self-inflicted-looking-clean error. E.g. `POST /api/v1/users/password` (id
segment entirely omitted) still matches the `.../password` route's loose
`startswith("/api/v1/users/") and endswith("/password")` guard, and
`path.split("/")[4]` resolves to the literal word `"password"` — so the new
clean-looking error is `Invalid 'user_id' path segment: 'password'`, which
reads as "someone sent a bad id" when actually no id was sent at all. Not a
new crash (still 400, no IndexError — the endswith suffix guarantees enough
segments), just a *confidently wrong* message. This exact failure mode is
what `NEW-520`'s own fix already added a single-path-segment guard to prevent
on the `staff-schedules` PATCH/DELETE block — this batch didn't extend that
guard to sibling sites. Logged as new-Warning-worth-a-NEW-###, not a blocker.

**How to apply:** on any future "wrap the bare X() call" mechanical batch,
don't just check the call site diff — check whether the *route-match
condition itself* could match a caller who omitted the id entirely, and
whether the wrapped call's `name=`/message would then lie about what's wrong.

**Ledger-arithmetic gotcha:** `NEW-522`'s original text estimated "~51
remaining sites / 53 total" from an early scoping grep. Actual count on
re-measure: 28 remaining narrow-pattern (`int(path.split`) sites + 24 fixed
this round + 2 fixed by `NEW-520` = 54 total (off by one from the original
estimate), plus 4 more sites using other bare-int-path shapes
(`int(sub_path)`, `int(path[len(...):])`) not caught by the narrow grep, for
32 total remaining across all shapes. Always re-grep the exact pattern rather
than trusting an earlier round's count when reviewing a partial-sweep round.
