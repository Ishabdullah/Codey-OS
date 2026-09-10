---
name: new436-doc-round-4546-typo
description: NEW-436 doc-only round (2026-09-10) — mechanism correction sound, but a digit-transposition typo in the finding citation earned CHANGES REQUESTED
metadata:
  type: project
---

NEW-436 (NEW-206 concurrency saga residual) resolved doc-only 2026-09-10: confirmed
real, mechanism re-derived and corrected per rule 6, accepted not-fixed. Spin-offs
NEW-441 (dead `legacy_reserved` in `acquire_context_lease`) and NEW-442 (Core API
`routes.py` calls `release_context_budget(port, reservation_id)` against 1-arg
signature — real reservation leak) logged.

**Why:** The corrected NEW-436 mechanism (concurrent request A double-counted in
`/slots` sum + its still-held ACQUIRED lease; caller's own lease INSERTed after the
ceiling check so "exclude own reservation" is a no-op) traced clean against
`core/resource_bus.py:acquire_context_lease` (SELECT at ~360 has no
lease_id/pid/dispatched filter; INSERT at ~411 after `combined > ceiling` at ~396).
Fail-closed "not leaning on NEW-208" argument also verified against current
`reserve_context_budget` (returns before `acquire_context_lease` when `/slots`
unreachable). NEW-441/442 both verified by grep + signature read.

**How to apply:** The block was CHANGES REQUESTED for one thing only: the NEW-436
entry described the live repro as "two 4546-token requests" when every other
reference across the whole saga (PROJECT_LOG, master plan, NEW-430/431/435 entries)
says **4246**. Digit transposition, conclusion unaffected, but this project holds
finding-citation wording to a high bar (previous round NEW-434 also CR'd for doc
wording). When reviewing doc rounds in this saga, cross-check every restated number
against the other saga entries — the numbers are load-bearing identifiers here.
Minor non-blockers also noted: "~8.5% footprint (§8 Q11)" is a touch above what
Q11 actually derived (~8% / "7-8%"); NEW-442 cites resource_gate.py:4760 for a
signature actually at :4771 (line drift).
