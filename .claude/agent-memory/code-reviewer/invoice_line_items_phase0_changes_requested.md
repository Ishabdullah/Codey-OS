---
name: invoice-line-items-phase0-changes-requested
description: Adding a field to a dataclass that's populated from a DB row at more than one hand-rolled construction site — one site gets missed silently
metadata:
  type: feedback
---

Reviewed Phase 0-slim `Invoice.line_items` + server-side `create_invoice`
amount computation (restoricon_core, 2026-09-27). CHANGES REQUESTED.

**The bug:** `CRMService.create_invoice`/`_row_to_invoice` were correctly
updated to read/write the new `line_items_json` column, but a *second*,
unrelated hand-rolled `Invoice(...)` construction inside
`record_payment` (~crm_service.py:5550, building `_updated` from `row`
to return from the pay endpoint) was never touched. It doesn't call
`_row_to_invoice` — it lists fields out by hand — so it silently
defaulted `line_items` to `[]`. Live-reproduced: DB row and a fresh
`get_invoice()` both correctly retained line items after a payment;
the object `record_payment` *returned* (serialized directly in
`POST /api/v1/invoices/{id}/pay`'s response body) did not.

**Why this matters generally, not just for this diff:** whenever a
task adds a new field to a dataclass that's populated by reading a DB
row, grep for *every* place that dataclass gets built from a row —
`grep -n "= Invoice("` (or whatever the class is), not just the
canonical `_row_to_X` helper. `_row_to_invoice` is not the only
construction site in this file; `record_payment` had its own. The
task's own scope hint ("check other invoice-amount-trusting paths")
described exactly this shape of gap but for `amount`, not `line_items`
— the same technique (grep for hand-rolled constructions, not just the
canonical reader) generalizes to any newly-added field, not just the
one the task named.

**Technique that caught it:** the advisor flagged it purely from a
`grep -n "amount="` match earlier in my own transcript
(`amount=row["amount"]` at crm_service.py:5556) that I'd seen but not
followed up on — a stray grep hit adjacent to the diff's blast radius
is worth chasing even when it looks unrelated to the line you're
checking.

**Also verified clean in this round (don't re-litigate if this file
resurfaces):** malformed-line-item TypeError→500 is genuine pre-existing
precedent (byte-for-byte identical no-validation pattern in
`OperationsService.create_work_order`/`WorkOrder(**json_body)`);
negative line items (real SCF credit, -75.00) net correctly, live test
passes; `_recalculate_invoice_balance`'s `max(0.0, ...)` clamp is a
real but non-firing edge case for a *net-negative* invoice total —
worth naming as a Suggestion even when the shipped case doesn't trigger
it, not worth dropping. Migration correctness (ADD COLUMN ... NOT NULL
DEFAULT on a real pre-existing SQLite file, not just `:memory:` fresh
schema) is worth spot-checking with a scratch DB when rule 12 applies —
takes under a minute, catches a class of bug that in-memory fixture
tests structurally cannot exercise.

See also [[new259_txn_boundary_missed_site]] if that memory exists —
same bug class (construction/call site missed when a related one was
correctly fixed) as the `_config`/`port=` kwarg bug NEW-259 caught.
