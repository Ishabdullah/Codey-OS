---
name: b8_16_phase4_intake_form_round2_approved
description: B8.16 Phase 4 (work-order-intake form UI) round 2 — both Critical bugs from round 1 fixed and verified genuine, APPROVED final
metadata:
  type: project
---

Reviewed 2026-09-29, round 2 of [b8_16_phase4_intake_form_changes_requested](b8_16_phase4_intake_form_changes_requested.md).
**Verdict: APPROVED (final).** Both round-1 Critical bugs fixed correctly; NEW-682 wording
fix also confirmed genuine.

1. **Focus-loss fix genuine.** `woiUpdateLineItem` now calls a new `woiUpdateDerivedTotals(index)`
   that writes `row.children[N].textContent` only — no `innerHTML` reassignment, no `<input>`
   touched. `woiAddLineItem`/`woiRemoveLineItem` correctly still call the full
   `woiRenderLineItems()` (row-count changes genuinely stale the indices baked into `oninput`
   attributes). New regression test strips `//`-comment lines before asserting and slices
   strictly between function-boundary markers — closes the exact false-failure class its own
   comment describes (an earlier draft anchored on a comment string containing the banned
   function name). **Technique note**: when a test's own commit message says "reworked after a
   false-failure," don't just trust that it's fixed — re-read the test body and confirm the
   slicing/stripping logic actually does what it claims.

2. **`logoutUser()` fix genuine — but the "matches existing convention" claim needed real
   verification, not pattern-matching on plausibility.** `logoutUser()` is defined in
   `_get_common_script()` and used at ~25 sites across `web_surfaces.py`, so a shallow grep
   would suggest it's "the convention" and the implementer's fix (switching to
   `window.location.href = '/admin/login'`) looks like it's going against the grain. The
   resolution requires tracing **which template the edited code actually renders inside** —
   `_render_work_order_intake_section`'s markup is embedded into `_render_staff_portal_base`,
   which never calls `_get_common_script()` and has its own, different, locally-consistent 401
   convention (`window.location.href`, used at 4 sites in that same function's `loadDashboard`).
   The fix matches the *actual* local convention, not the file-wide plurality. **Lesson
   reinforced from round 1**: helper-function scoping claims ("matches convention elsewhere")
   must be checked against the specific render function the new code lives inside, not the
   file as a whole — a file-wide grep majority can point the wrong way.

3. NEW-682 Impact wording confirmed reordered to lead with the real money-diversion risk,
   privilege-escalation disclaimer now trailing, not leading.

Verified: new test file `tests/test_restoricon_core/test_b8_16_phase4_intake_form.py` 20/20
passed; full `tests/test_restoricon_core/` suite run twice (HTTP_PROXY/HTTPS_PROXY unset),
1353 passed both times, zero failures — the previously-flagged
`test_api_customers_limit_non_integer_is_400_without_raw_pyexc_text` flake (see
[sandbox_http_proxy_urllib_405_env_artifact](sandbox_http_proxy_urllib_405_env_artifact.md))
did not reproduce either run this round. `NEW_ISSUES.md` diff confirmed a clean pure-append
block, no duplicate `### [NEW-682]` headers.

Files for commit: `restoricon_core/auth.py`, `restoricon_core/api/routes.py`,
`restoricon_core/api/web_surfaces.py`, `NEW_ISSUES.md`, new
`tests/test_restoricon_core/test_b8_16_phase4_intake_form.py`. Excluded
`.claude/agent-memory/code-reviewer/MEMORY.md` from the stage list — an unrelated
pre-existing working-tree change, not part of this implementer diff (see
[working_tree_cross_round_bleed](working_tree_cross_round_bleed.md)).
