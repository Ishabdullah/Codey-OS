---
name: staff-portal-projects-name-enrichment-approved
description: NEW-660 staff-portal (PM/tech/subcontractor) Assignments table customer_name enrichment on GET /api/v1/projects — APPROVED first round
metadata:
  type: project
---

Direct follow-on to [[sales_portal_name_enrichment_approved]] (commit
4d57d50), same bug class applied to `_render_staff_portal_base()`'s
Assignments table. APPROVED first pass, 2026-09-26.

Verified directly (not trusted from implementer's summary):
- `projects` table schema (`database.py`) confirmed genuinely
  `customer_id INTEGER NOT NULL` — the claimed reason for skipping the
  leads fix's `'—'` null-fallback ternary is real, not asserted.
- Enrichment order is correct by construction: `routes.py` calls
  `self.crm.list_projects(actor, ...)` first (actor-based narrowing
  happens inside the service call) and only then iterates the
  already-narrowed `projects` list to build `proj_cust_names` — there is
  no way for the enrichment step to reach rows the narrowing excluded,
  since it never touches the DB independently.
- The implementer's new narrowing test
  (`test_list_projects_customer_name_survives_technician_actor_narrowing`)
  is genuine: constructs a real technician `AuthContext`/token, creates
  one assigned + one unassigned project, round-trips through
  `handle_request` with the technician's token, and asserts both the
  narrowing (unassigned project absent) AND the enrichment
  (`customer_name` present on the assigned one) in the same test — not a
  partial check of only one property.
- Spot-checked all 3 claimed other-consumer call sites in
  `web_surfaces.py` (Document Handoff ~2939, admin CRM panel ~3444,
  property-projects Customer 360 ~7356) — none destructure a strict key
  set; all only read `p.id/p.title/p.status/p.stage/p.project_type/
  p.contract_amount`. No breakage from the additive `customer_name` key.
- Repo-wide grep for `Cust #` reproduced independently: zero hits outside
  comments/test-string-literals across `.py/.js/.html`.
- Reproduced the proxy-artifact claim exactly:
  `tests/test_restoricon_core/test_api.py` gives 57 failures with ambient
  `HTTP_PROXY=http://127.0.0.1:44161` set in this sandbox (all
  `assert 405 == 200` on the login POST — proxy-shaped, not this diff),
  57 passed with `NO_PROXY="127.0.0.1,localhost"` set. Matches
  [[sandbox_http_proxy_urllib_405_env_artifact]] exactly, same numbers as
  the prior sales-portal round.
- 37/37 targeted tests passed
  (test_staff_portal_projects_name_enrichment.py +
  test_b6_8_staff_portals.py + test_staff_portals.py +
  test_sales_portal_leads_opportunities.py +
  test_sales_portal_name_enrichment.py); 33/33 test_b8_12b passed under
  `NO_PROXY`.

Nothing blocking found. `.claude/agent-memory/code-reviewer/MEMORY.md`
again showed modified in working tree at review start — repeat of
[[working_tree_cross_round_bleed]], unrelated noise, not blocking.
