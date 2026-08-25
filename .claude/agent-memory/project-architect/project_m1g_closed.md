---
name: m1g-closed
description: M1-G (prompt re-check for Qwen3.5-4B migration) closed DONE 2026-08-25 after G2b live run; NEW-182 stays open as standing methodology gap
metadata:
  type: project
---

M1-G (Appendix A, `CODEY_MASTER_PLAN.md` §4.2) is closed DONE as of
2026-08-25, third round. G2b (a `.cfg`-fixture read-before-patch test
designed to dodge `core/context.py`'s auto-preload) ran live: grounding
3/3, sequencing 3/3, clean, with full RAM-discipline and precondition-gate
evidence recorded in §4.2. Combined with G1 (desk, baseline confirmed),
G2 (live, grounding 3/3 in the real `.py`-preload domain), and G3 (live,
5/5 clean on `NEW-50`), this was judged — explicitly as an
architect-level call, not a pre-registered pass/fail — sufficient to
close item 1 (system_prompt.py tool-calling format) and item 3's residual
(jinja template) with "measured, no edit needed."

**Why closed rather than left `[ ]` with residual scope noted inline
only:** the one remaining gap — `.py`/`.json`-domain read-before-patch
*sequencing* specifically (grounding was already measured there via G2)
— has no reachable test design at HEAD without either fixing
`core/context.py`'s preload (out of scope, itself `NEW-182`/`NEW-185`
work) or building an explicit harness-side preload bypass (considered,
deprioritized). An item with no achievable next step is worse doc hygiene
held open than closed with the residual documented. That residual lives
permanently in `NEW-182`, which stays Confirmed/open independent of
M1-G's status — `NEW-182` is a standing methodology-gap finding, not a
task-blocking item.

**How to apply:** if a future round revisits `core/context.py`'s
`auto_load_from_prompt()`/`detect_filenames()` (e.g. fixing `NEW-185`'s
extension-truncation bug, or adding a real word-boundary anchor), that is
the point at which a genuine `.py`-domain read-before-patch sequencing
test becomes possible for the first time — worth flagging to whoever
picks up `NEW-182`/`NEW-185` next. Do not reopen M1-G itself for that;
route it through `NEW-182` instead, since M1-G's own question (does
system_prompt.py's tool-calling format work on Qwen3.5-4B) is answered.

See also [[project_round_daemon_control_4_1_scoping]] and the M1-E/M1-F
memory entries in `MEMORY.md` for the migration's broader arc.
