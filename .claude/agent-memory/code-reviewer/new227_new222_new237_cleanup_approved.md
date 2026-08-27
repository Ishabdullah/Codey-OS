---
name: new227_new222_new237_cleanup_approved
description: NEW-227 token-revoke-on-rerun fix + NEW-222/NEW-237 by-id GET route tightening — approved w/ 1 warning (runtime warning not loud enough)
metadata:
  type: project
---

Reviewed 2026-08-27: `tools/provision_ai_agent_auth.py` (revoke-every-
stale-token-before-reissue on rerun), `restoricon_core/api/routes.py`
(4 generic by-id GET branches tightened to reject a further `/`-segment
after the id, closing the `.../{id}/qualification` etc. 400-not-404
misparse). Tests: `tests/test_provision_ai_agent_auth.py`,
`tests/test_restoricon_core/test_api.py`. **Approved** (one Warning, not
blocking).

Verified directly, not from implementer's summary:
- `revoke_token()` targets `WHERE token = ?` (exact string), never by
  user_id/bulk pattern — no risk of cross-user or wrong-token revocation.
  Sequencing is revoke-stale-then-create-new, only in the existing-user
  branch (new users have no stale tokens) — sane for a single-threaded
  offline script.
- `test_provision_rerun_does_not_accumulate_unrevoked_tokens` genuinely
  load-bearing: 3x `provision()` calls, asserts exactly 1 live + 2
  revoked tokens after. Against pre-fix code this would see 3 live/0
  revoked — confirmed by reading the old revoke-nothing docstring/code.
- Fix-2 completeness claim verified independently: grepped every
  `path.startswith("/api/v1/` in routes.py (11 total). 4 fixed (customers,
  projects, subcontractors, appointments GET-by-id), the other 7 are all
  `.endswith("/<action>")`-qualified POST routes — a structurally
  different, unaffected shape. Matches implementer's claim exactly.
- `test_api_by_id_get_routes_404_not_400_on_action_suffix` is genuinely
  load-bearing: pre-fix, `GET .../{id}/qualification` matches the bare
  `startswith` + GET branch, then `int("qualification")` raises
  `ValueError`, caught at routes.py's generic handler and turned into a
  400 (traced the actual except Valueable -> 400 path). Post-fix it falls
  through to the 404 catch-all. Covers 2 resource types (subcontractors,
  appointments) plus a positive-case regression check that plain
  `GET .../{id}` still 200s.
- The logged-not-fixed trailing-slash quirk (`GET .../customers/` bare,
  still 400s via `int("")`) is accurately described: the guard is
  `"/" not in path[len(prefix):]`, and an empty string trivially satisfies
  `"/" not in ""`, so this case still falls into the by-id branch. Real,
  pre-existing, and a genuinely different shape (missing segment, not an
  extra one) — correctly out of scope for this round, correctly logged
  per rule 8.
- Zero touch to `~/Codey-Aigentik`/`~/Aigentik-CLI` confirmed via
  `git status --short` in both directories; the referenced commit
  `0398396` (NEW-226 docs fix) is confirmed already committed separately
  in `~/Codey-Aigentik`, not part of this diff.
- Full suite run live: `python -m pytest tests/ -q` → 814 passed, 1
  skipped, verbatim matches implementer's claim.

**One Warning, not blocking:** the operational-consequence warning
(rerunning this script kills the token currently deployed in
`~/Codey-Aigentik/config.json`, breaking the Core-only do-not-contact/
email-rules/sms-rules write-through paths until the deployed config is
updated) lives *only* in the module docstring, which only surfaces via
`--help` (confirmed `argparse.ArgumentParser(description=__doc__)`).
`main()` just does `print(token)` on a normal run — no stderr warning
fires at the moment the risk is actually live, i.e. when someone reruns
the script without reading `--help` first. Recommend a stderr print
alongside the revoke loop (e.g. "Revoked N prior token(s) — update
deployed configs now") so the warning is loud on the actual footgun path,
not just in documentation someone has to think to ask for.
