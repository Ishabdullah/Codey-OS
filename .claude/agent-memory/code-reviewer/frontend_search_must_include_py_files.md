---
name: frontend-search-must-include-py-files
description: repo-wide "does any frontend consumer exist" searches must include .py, not just .js/.html — this project's dashboard UI is rendered from Python f-strings
metadata:
  type: project
---

This project's admin/staff/sales-portal frontend JS/HTML is embedded in
Python f-string blocks inside route/surface files (`web_surfaces.py` is
~5700+ lines and is the primary example), not standalone `.js`/`.html`
files. A repo scan for "does any consumer read field X" that only globs
`.js`/`.html` will silently miss the real consumers and can produce a false
"zero consumers" conclusion.

**Why this matters:** on the [[new643_646_technician_operations_write_narrowing_approved]]
round, a `.js`/`.html`-only scan for `active-references`/`active_references`
came back empty, and "no consumer exists, so an additive JSON field is safe"
was nearly written into a memory file as a *stronger* claim than the
evidence supported. A `.py`-inclusive scan found the real consumer inside
`web_surfaces.py`'s `deleteSubcontractor()`. The safety conclusion happened
to still hold (the consumer accesses fields by name, not via strict-key
iteration) — but it was reached by verifying the actual code, not by
absence of a hit.

**How to apply:** any time a review needs to answer "is there a live
consumer of this API response / field / route", scan `.py` files in the
same sweep as `.js`/`.html` (or just scan `.py` first, since it's the more
likely location in this repo). Absence of a `.js`/`.html` hit is not
evidence of absence here — see also [[new470_staff_portal_fstring_escape_approved]]
and [[b8_13b_sales_portal_table_scroll_wrapper_approved]] for the same
render-from-Python pattern in different subsystems.
