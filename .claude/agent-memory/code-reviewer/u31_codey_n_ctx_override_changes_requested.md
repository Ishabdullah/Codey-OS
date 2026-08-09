---
name: u31-codey-n-ctx-override-changes-requested
description: U.31 CODEY_N_CTX env-var override reviewed — core logic sound, blocked on missing NEW_ISSUES.md entry for an out-of-scope finding described only in prose
metadata:
  type: project
---

Reviewed `utils/config.py`'s new `CODEY_N_CTX` env-var override (adds a
loud-fail-on-bad-value override for `MODEL_CONFIG["n_ctx"]`, default 32768
unchanged) plus `tests/test_u31_n_ctx_override.py`.

**Core logic: approved on the merits.** Verified against
`core/resource_gate.py`'s `estimate_kv_cache_bytes()`: negative `n_ctx`
actually *subtracts* from the cost estimate (not just zeroes it out),
confirming the implementer's stated reason for explicitly rejecting
`n_ctx <= 0` (not just non-numeric) was correct, not overclaimed. Grep
for hardcoded `32768` and independent readers came back clean — all
readers genuinely go through `MODEL_CONFIG["n_ctx"]`. Test suite: ran it
myself, `437 passed, 1 skipped` (tests/) and `505 passed, 1 skipped`
(full repo incl. ccos/tests) — literal match to the implementer's claim,
no leaked reload state observed.

**Blocked on: CLAUDE.md rule 8.** The task handoff described an
out-of-scope finding (`main.py`'s `--ctx` CLI flag never reaching
`core/memory_v2.py`'s `CTX_TOTAL`, because `core/context.py` — imported
eagerly at `main.py:9`, before `main.py:113`'s CLI-override line ever
runs — eagerly imports `memory_v2` at its own module level) as "surfaced,
marked Suspected." `git diff --stat -- NEW_ISSUES.md` was **empty** — the
finding existed only in the implementer's prose, not in the log rule 8
requires. I independently traced the import order and confirmed it's
real and should be filed **Confirmed**, not Suspected (import-order chain:
`main.py:9` → `core/context.py:11` → `core/memory_v2.py:38`, all execute
before `apply_overrides()`'s `config.MODEL_CONFIG["n_ctx"] = args.ctx`).
Also surfaced in the same pass: `main.py:37`'s `--ctx` (`type=int`) has no
positive-value guard, unlike the new `CODEY_N_CTX` path — same over-admit
failure mode via a different door.

**Lesson for future reviews on this project:** when a task handoff says
an out-of-scope finding was "surfaced, logged as Suspected/Confirmed,"
always run `git diff --stat -- NEW_ISSUES.md` (or equivalent) to confirm
it's actually IN the diff, not just described to you in the review
prompt. A finding described accurately in prose but never committed to
the durable doc is still a rule-8 violation — "surfaced" in a chat
message is not "logged." This is a new instance of a pattern worth
watching for: verify claimed-but-undiffed doc updates the same way you'd
verify claimed-but-unproven test results.

See also [[resource_gate_new97_plannd_registration_approved]] for the
precedent on verifying "logged to NEW_ISSUES" claims via git diff --stat
rather than trusting the reviewed file alone — same lesson, second
occurrence, now confirmed as a recurring gap worth checking by default.
