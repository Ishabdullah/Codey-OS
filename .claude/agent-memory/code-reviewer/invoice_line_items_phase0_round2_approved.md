---
name: invoice-line-items-phase0-round2-approved
description: Round-2 close of the record_payment missing-line_items bug from invoice_line_items_phase0_changes_requested — confirms the "grep all hand-rolled constructions" fix pattern converges cleanly in one round
metadata:
  type: feedback
---

Round 2 of [[invoice_line_items_phase0_changes_requested]] (restoricon_core,
2026-09-27). APPROVED.

Implementer's fix was minimal and correct: added the same
`line_items=json.loads(row["line_items_json"]) if row["line_items_json"]
else []` line to the second hand-rolled `Invoice(...)` construction inside
`record_payment` (crm_service.py ~5564), in the right field position, no
other field disturbed. Verified by direct read of the live file (not the
diff snippet alone) plus `grep -n "Invoice("` across the whole file to
confirm there are exactly two construction sites and both now carry the
field.

**Confirms a reusable verification recipe for "missed construction site"
findings:** (1) re-read the fixed function directly rather than trusting
the diff hunk in isolation — diffs can look right while being misplaced
in surrounding context; (2) grep the class constructor name file-wide to
prove no third site was missed; (3) re-run the implementer's own claimed
test command yourself and diff the verbatim pass count, don't just accept
the paraphrase.

Also logged in this round: `NEW-666` (audit_service.py's
`_AUDITABLE_INVOICE_FIELDS` frozenset excludes the new `line_items`
field) — correctly handled as log-only/non-blocking rather than scope
creep into fixing it. Verified the ledger append was clean (no ID
collision, no corruption of adjacent entries) by reading the file tail
and `git diff` on `NEW_ISSUES.md` before approving — worth doing every
time a subagent writes to a shared tracking doc, per CLAUDE.md's
doc-write-collision policy.
