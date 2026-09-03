---
name: telemetry-t1-aigentik-extraction-grounding-approved
description: Cross-repo JS telemetry writer T1 (Codey-Aigentik category F extraction/grounding) — approved, verified against Python T0 source
metadata:
  type: project
---

Sub-task T1 (Category F — Aigentik extraction/grounding telemetry) in the
separate `~/Codey-Aigentik` repo, depending on Codey-OS's just-committed
T0 schema foundation — APPROVED (2026-09-03). `telemetry.mjs`,
`classifyAddressGrounding()` in `llama.js`, wiring at both extraction call
sites, 17 new tests, 256/256 suite green (live-run, matched implementer's
claim exactly).

**Why this needed extra digging, and the reusable lesson:** a stronger
reviewer (advisor) flagged 3 apparent bugs by reading only the JS diff:
(1) `nulls` never populated at emission sites → honest-null fields
silently omitted, (2) `nulls: {}` always present contradicting the design
doc's "present only when non-empty" wording, (3) `getLlmProvider()` moved
outside a pre-existing `try` block, backward-compat risk. **All three
were false alarms once I read the actual Python counterpart
(`telemetry/envelope.py`, `telemetry/recorders.py`) instead of just the
design doc's prose** — Python's own `_emit()` does exactly the same
null-omission-for-not-applicable-fields thing (documented in its own
docstring) and `build_envelope()` always sets `nulls` too. The JS module
mirrors Python's actual behavior, not the design doc's slightly looser
summary wording. **Lesson: when a cross-language parity claim is under
review and only one side's source is in front of you, go read the other
side's source before trusting either the diff's comments or the design
doc's prose — the two languages' actual code is the ground truth for
"do they match," not the doc.**

A 4th flag — `recordDeterministicBypass()` unwired, claimed out of T1
scope — looked like a real scope gap because design §7's summary table
row for T1 says "deterministic_bypass emission at the rule sites."
Resolved by reading §4.4 ("every file modified" table, the authoritative
list), which lists only `llama.js`/`logger.js` for T1 and does NOT
include the rule-dispatch files (`subcontractor-form.js`,
`email-rules.js`, `sms-rules.js`, `do-not-contact.js`, `index.js`).
**Lesson: this design doc has both a summary/rationale table (§7) and an
authoritative file-manifest table (§4) that can read as contradictory —
§4 wins when they conflict.**

Non-blocking follow-ups logged, not silently dropped: `recordDeterministicBypass`
wiring is a genuine future sub-task; `Store.shutdown()` never called from
`index.js`'s existing SIGINT/SIGTERM handler (bounded ~2s record loss on
restart, detectable via seq gap, but touches shutdown path so a fix needs
rule-4 review); size-cap truncation only handles string body fields
(extraction_attempt's all-array body would ship oversize untruncated —
currently unreachable given fixed small key lists); interlock test
comment overclaims "deliberately NEVER calls the real pruneOldLogs()" when
`logger.js` module-load-time `pruneOldLogs()` does fire on every import
(harmless — same as normal app start — but should be corrected per rule 6).
