---
name: new_issues_cleanup_batch4_round2_new407_approved
description: NEW_ISSUES.md ledger closeout batch 4 (telemetry) round 2 — NEW-327 doctor message fix + NEW-407 ledger entry, APPROVED
metadata:
  type: project
---

Round 2 of [[new_issues_cleanup_batch4_telemetry_js_mirror_gap]]. Round 1
requested changes because `cli.py`'s `known_limitation_new_327` doctor
message unconditionally claimed the nested-null gap was "closed" when only
the Python emission side was fixed; `telemetry.mjs` (Codey-Aigentik,
cross-repo, out of this session's write scope) was never touched.

**Fix taken (option (b) from round 1):** rewrote the doctor message to say
"partially closed" and explicitly name that `telemetry.mjs`'s
`recordRunStart()` was not updated, cross-referencing new ledger entry
`NEW-407`. Did not attempt to mirror the JS fix (blocked by session
write-tooling scope).

**Verdict: APPROVED.** Verified beyond just reading the diff:

1. **Live-reproduced the actual mechanism against the real on-disk store**
   (`~/.codeyOS/metrics`), not just a hand-built record. `git stash` of the
   3 changed telemetry files showed pre-diff `doctor` already exits 1
   (`hard_violation_count: 143`, driven by unrelated seq-gap/orphan-run
   noise, `null_violations: []`). Post-diff (current code):
   `hard_violation_count: 148`, with exactly 5 new
   `body.models[i].sha256 is null with no entry in nulls` violations
   across 3 real run records. Confirmed these 3 records predate this
   session's edits (`stat` mtime 2026-09-03 vs `provenance.py`'s edit
   today, 2026-09-08) — they're historical artifacts written by
   pre-fix code (one is even `emitter: codey-os.core-api`, i.e.
   Python-side, from before NEW-327 existed), not proof current Python
   code emits invalid records. This matters: **the doctor exit-1 today is
   not solely "JS mirror broke a healthy store"** — the store was already
   unhealthy for unrelated reasons — but the mechanism NEW-407 describes
   (schema tightening retroactively flags any pre-fix cold-cache record,
   Python or JS, that lacks the matching per-index `nulls` entry) is
   real and currently firing, which is what the doctor message and
   NEW-407 both actually claim — neither overclaims "0 to 1 on an
   otherwise healthy store" in a way contradicted by this data.
2. **Re-opened `~/Codey-Aigentik/telemetry.mjs` directly** (reads aren't
   scope-blocked, only writes) to check NEW-407's specifics rather than
   trusting its prose: `getModelDigest()` at line 810 with
   `sha256: null` default — confirmed. `resolvedModels` (the variable
   NEW-407's fix direction tells the next implementer to iterate) exists
   verbatim at line 999 — confirmed, not a wrong-variable-name ledger
   entry. `recordRunStart()` spans roughly 965-1062, matching the cited
   range. Grepped the whole file for `nulls[` — no `body.models[i].sha256`
   entry exists anywhere, confirming the gap is real and total, not
   partial.
3. **Checked schema.py's recursion for unnamed blast radius** (the
   `isinstance(value, list)` recursion is generic, not models-specific).
   Grepped every `body = {...}` construction site in `recorders.py` and
   `provenance.py`, and every list literal in `telemetry.mjs`: `models`
   is the only list-of-dict body field either side ever builds (the one
   other list found, `live_session_pids`, is a list of ints, skipped by
   the `isinstance(item, dict)` guard). NEW-407 does not understate the
   blast radius.
4. Confirmed `NEW-407` is the correct next free ID (grepped `NEW-40[0-9]`,
   next entry after `NEW-406`) — no dual-agent ID collision.
5. `git status --short` shows exactly the same 12 files as round 1 — no
   new file rode along in round 2.
6. Full suite re-run: `1500 passed, 1 skipped in 236.53s` — matches
   round-1 baseline exactly.

**One warning, not blocking:** the round-2 diff also deleted the doctor's
default-text-mode `print(f"known gap: NEW-327 (nested nulls)")` line
without replacing it. JSON mode still carries the full "partially closed
... see NEW-407" string, but an operator running plain `codey-metrics
doctor` (not `--json`) who hits a new violation from this gap sees only a
bare `hard violations: N` with no pointer to why or to NEW-407. Low
severity since JSON mode carries the full explanation and this is a
docs/UX gap, not a correctness bug — but worth a follow-up one-line
`print` restoring a pointer to NEW-407 in text mode.

**Process lesson:** for a ledger-entry-only "fix" (no code change, just
honest documentation of a cross-repo gap), the round-1 mistake (asserting
overclaim) doesn't fully resolve just because a docstring reads better —
verify against the live store and the actual cross-repo file, the same
standard as any live-verified finding. A "doc-only" round-2 fix is not
automatically low-risk to approve on read-through alone.
