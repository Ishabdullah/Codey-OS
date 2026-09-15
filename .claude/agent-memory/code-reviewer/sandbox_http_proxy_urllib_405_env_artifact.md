---
name: sandbox-http-proxy-urllib-405-env-artifact
description: Full pytest suite shows ~34 test_api.py 405 failures caused by ambient HTTP_PROXY/HTTPS_PROXY env vars in this Bash-tool sandbox intercepting urllib.request loopback calls -- not an app regression
metadata:
  type: project
---

**Root cause found and verified (2026-09-15, NEW-487 review):** a full-suite
run of `tests/test_restoricon_core/` in this sandbox shows ~34 failures, all
in files that drive the live HTTP test server via `urllib.request`
(`test_api.py`, `test_customer_upsert.py::TestCustomerHTTPRoutes`,
`test_business_profile_contact_fields.py`'s route tests) — typically
`assert status == 200` failing with `405` and an empty body.

**Cause:** this environment has `HTTP_PROXY`/`HTTPS_PROXY`/`http_proxy`/
`https_proxy` set (pointing at `127.0.0.1:41525`, apparently a
Claude-Code-sandbox network-egress proxy) with no `NO_PROXY` exclusion.
`urllib.request` honors these env vars for *all* requests including
`127.0.0.1` loopback targets (unlike `http.client.HTTPConnection` or a raw
socket, which bypass env-proxy config entirely) — so every
`urllib.request.urlopen()` call to the test server gets silently routed
through that sandbox proxy, which returns a bare `405` for requests it
won't forward.

**Fix/workaround, not a code bug:** run pytest with those four env vars
unset, e.g. `env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY
python -m pytest tests/test_restoricon_core/ -q`. Verified: same repo
state, same diff, 34 failed → 0 failed / all passed once unset. This is a
**sandbox environment artifact**, unrelated to whatever app diff is under
review — confirmed via `git stash` (identical failure set with and without
a pending diff) plus a standalone repro script that isolated the exact
`urllib.request` vs `http.client` behavior difference and printed
`urllib.request.getproxies()`.

**Why this matters for review:** don't accept "sandbox HTTP issue" as a
bare claim (rule 5) — but also don't assume it's a regression just because
the fail count is large and sudden. Reproduce with env vars unset before
concluding either way. If a future round reports a full-suite failure
count that doesn't match a recent "665/670/683 passed, zero failures"
baseline, check `env | grep -i proxy` first before deep-diving app code.

Related: [[working_tree_cross_round_bleed]] for the broader "verify the
apparent regression is actually caused by this diff" discipline.
