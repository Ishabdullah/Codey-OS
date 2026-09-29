---
name: b8_13b_sales_portal_table_scroll_wrapper_approved
description: B8.13b mobile table-scroll-wrapper pass on sales portal — APPROVED round1, zero blocking findings; reusable verification technique for pure-markup wrap changes
metadata:
  type: project
---

B8.13b (sales-portal half): wrapped all 19 `<table>` sites inside
`_render_sales_portal()` (13 static + 6 JS-template-literal-built) in a
new shared `.table-scroll-wrapper { overflow-x: auto; ... }` div, per
Ish's explicit "horizontal scroll wrapper, not card-stacking" answer.
Reviewed strictly scoped to `restoricon_core/api/web_surfaces.py` +
`tests/test_restoricon_core/test_sales_portal_dashboard_panels.py` —
the working tree concurrently had [[b8_13a_subcontractor_audit_layering_opportunity_559_approved]]'s
uncommitted changes to `routes.py`/`crm_service.py`/three other test
files, which were explicitly out of scope and not reviewed here.

**Verification technique worth reusing for any "wrap N occurrences of X"
diff:** don't just read the diff hunks — isolate the target function's
source slice (`src.index('def _render_sales_portal()')` to the next
`\ndef `) and count `<table` vs `</table></div>` occurrences *within
that slice* for open/close parity, independent of the implementer's own
test. Then actually call the render function, extract the single
`<script>` block via regex, and run `node --check` on the real rendered
JS text — not the source template — to catch any `{{`/`}}` f-string
escaping breakage the wrap could have introduced. Both checks were clean
here (19/19 both ways, JS parsed).

**Advisor caught a real gap self-review missed:** whether the wrapper
does anything measurable depends on a pre-existing CSS fact the
implementer's own disclosed limitation ("may shrink-to-fit, deferred")
didn't establish — grep for `table { width: ... }` rules already in
scope. Found `table {{ width: 100%; ... }}` already defined right above
`_render_sales_portal()` (predates this diff). Under CSS auto
table-layout, `width: 100%` is a *minimum*, not a cap — the browser
still expands to min-content width when cell content can't shrink
further, so the wrapper does meaningfully engage on genuinely
wide/many-column tables (Follow-ups: 6 cols, Customers: id/name/phone/
email). Confirmed this makes the disclosed limitation accurate, not an
overclaim, and not a near-inert change.

Also checked and ruled out: no `position: absolute`/`sticky` elements
live inside any of the 19 tables (the `overflow-x: auto` wrapper becoming
`auto` on both axes per CSS Overflow spec could otherwise clip such
elements) — only unrelated `.erp-modal-overlay { position: fixed }`
exists in the function, outside any table. Repo-wide + sibling
Codey-Aigentik grep for `table-scroll-wrapper` confirmed no class-name
collision. Confirmed CSS class defined in shared `_get_common_styles()`
but genuinely unused (harmless) by every other surface this round.

Full regression: scoped `tests/test_restoricon_core/` = 1146 passed;
full-repo suite = 2458 passed, 1 skipped, 0 failed (389s, no hang this
run) — this full-suite number includes B8.13a's concurrent uncommitted
changes too, not attributable to this round alone since those files
weren't diffed here. No install.sh/requirements.txt change (correctly
none needed — pure CSS/HTML, `node` is pre-existing test infra).
