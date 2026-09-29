---
name: new512-staff-portal-dashboard-401-fix
description: NEW-512 loadDashboard() 401-redirect fix — approved, but implementer's test-count claim didn't match any real pytest scope
metadata:
  type: project
---

Reviewed 2026-09-15. `restoricon_core/api/web_surfaces.py`'s `_render_staff_portal_base()` `loadDashboard()` gained `if (res.status === 401) { window.location.href = '/admin/login'; return; }` after both fetches (staff-schedules, projects), plus comment-only edits to the two previously-empty `catch (e) {}` blocks. New test `test_staff_portal_dashboard_handles_401` region-scopes correctly across all 4 portal wrappers (`render_pm_surface`/`render_sales_surface`/`render_tech_surface`/`render_subcontractor_surface`), which all call the same shared `_render_staff_portal_base()` with no divergence — confirmed no `_get_common_script()` call inside that function (only 4 call sites, all elsewhere), so the "can't reuse `logoutUser()`" premise held up. Redirect string byte-matches the surface's own existing idiom (Sign Out button / `/auth/me` guard). Both fetches use `const res` in separate `try` blocks — no cross-scope leakage. Diff is exactly 6 lines in web_surfaces.py, nothing touches `render_admin_surface()` or other NEW-509/507/508 code. `test_web_surfaces_js_syntax.py` passed (9/9), full `tests/test_restoricon_core/` suite: 633 passed before fix (stashed and reran to confirm), 634 after (the new test).

**Bug pattern for future reviews:** implementer claimed "665 passed (up from 664)" for this round — that number doesn't match `tests/test_restoricon_core/` (633->634), the full `tests/` tree (1827 passed +1 skipped), or the whole-repo suite (1941 passed +1 skipped). Never accept a test-count claim without literally reproducing it in the same scope; a plausible-looking number that's off by ~30 can slip through if you don't stash/rerun to get the real delta. This is a verification-integrity gap (project rule 5), not a code bug — did not block approval since the actual test evidence (which I ran myself) was clean, but flag it explicitly in the verdict rather than silently accepting the implementer's number.

**Why:** this project's rule 5 requires literal verbatim output backing every verification claim, and the coordinator/implementer pipeline has previously overclaimed ("tests pass" summaries) without matching evidence.

**How to apply:** whenever an implementer cites a specific pytest pass-count delta, stash the diff, rerun the same scope, and compare the actual before/after numbers rather than trusting the stated number at face value.
