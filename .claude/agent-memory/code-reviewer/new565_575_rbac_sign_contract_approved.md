---
name: new565-575-rbac-sign-contract-approved
description: NEW-565 (ROLE_SALES financials grant) + NEW-575 (sign_contract PM ownership-narrowing exemption) — both APPROVED; full-repo pytest run hangs in this sandbox independent of the diff, don't let that block review
metadata:
  type: project
---

2026-09-22, commit not yet made at review time. Both RBAC fixes in
`restoricon_core/auth.py` / `restoricon_core/services/crm_service.py` /
`tests/test_restoricon_core/test_services.py` verified clean and APPROVED.

**Grep-the-value-not-the-name caught nothing new here, but do it anyway.**
Implementer's claim ("PERM_READ_FINANCIALS gates nothing else") was verified
by grepping the literal string `"read:financials"` across *all* file
extensions, not just the Python constant name in `.py` files — per rule 12
("don't grep for the keys you expect"). Came back clean this time, but this
is the check that would have caught a JS/template gate site comparing by
raw permission string. Always do the value-grep, not just the
constant-name-grep, for any permission-set change.

**Derived-role grants are a real, recurring blind spot.** `ROLE_SALES_MANAGER`
is computed as `ROLE_PERMISSIONS[ROLE_SALES] | {...extra...}` *after* the
main `ROLE_PERMISSIONS` dict — so any permission added to `ROLE_SALES` also
silently reaches `ROLE_SALES_MANAGER`, and the implementer's summary didn't
mention it. Same shape as [[new549_global_search_rep_scoping_approved]]'s
"undisclosed narrowing" catch. Whenever a role's permission set changes,
grep for `ROLE_PERMISSIONS[ROLE_X] = ROLE_PERMISSIONS[ROLE_Y] | {...}`
derived-role lines and check whether the change also reaches the derived
role — log it as a Warning even when it's probably fine.

**A boolean-rewrite security predicate needs algebraic verification, not
eyeballing.** `elif not (A or not B):` reduces via De Morgan to
`(not A) and B` — reviewed by deriving this explicitly and walking every
role against the reduced form, not by reading the original `or`/`not`
nesting and guessing. This is also the right technique to check that an
`or`-widened bypass condition doesn't accidentally net-narrow some other
role (it didn't here, but the reduction is what proves it).

**A permission-based exemption's safety can depend on an invariant miles
away from the diff.** NEW-575's rationale ("actor lacking
PERM_WRITE_CONTRACTS can never own a contract") isn't obviously true from
reading `sign_contract` alone — it required tracing `create_contract`
(forces `assigned_user_id = actor.user_id` server-side, gated on
`PERM_WRITE_CONTRACTS`) AND `update_contract`'s
`ALLOWED_CONTRACT_UPDATE_FIELDS` allow-list (excludes `assigned_user_id`
entirely — no reassignment path exists at all). Both had to be checked
before trusting the comment. Logged a Warning that the exemption's safety
is contingent on `assigned_user_id` staying non-reassignable — not a bug
today, but undocumented as a dependency.

**Full-repo `python -m pytest -q` hangs in this sandbox, independent of the
diff — don't treat it as a regression signal.** Two separate attempts hung
at different points (`futex_wait_queue` at ~94%, `hrtimer_nanosleep` at 3%),
both in process/signal-timing test territory (shell service-manager PID
lifecycle, aigentik start/stop) that this diff never touched. Piping through
`tail` also silently launders the real exit code — `pytest | tail -30`'s
`$?` is `tail`'s, not pytest's; that "exited with code 0" evidence is
worthless, don't cite it. When the full suite won't complete: (1) run the
specific test file with `-k` for the changed behavior, (2) run the smallest
directory that contains all files touched by the diff
(`tests/test_restoricon_core/` here: 886 passed in 98s, clean), (3) report
the full-repo number as explicitly unverified rather than trusting the
implementer's claimed count — matches the NEW-512 lesson in
[[admin_dashboard_partB_kpi_consolidation_approved]]. Kill hung pytest
processes by their exact PID (`kill -9 <pid>`), never by name pattern.
