# Agent instructions — start here

**Status update (Ish, 2026-10-14):** the roadmap authority split in two.
Read [`CODEY_OS_MASTER_BLUEPRINT.md`](CODEY_OS_MASTER_BLUEPRINT.md) first,
every session — it is now the **primary execution plan for Track A /
Codey-OS core** (coding agent, CCOS, the Action Gateway, model loading,
measurement/self-improvement — the scope its 2026-10-06 census actually
covered): the current-state architecture and ordered work-package roadmap
for that track (its own "Status update (2026-10-14)" note inside the
WP2.1 entry marks exactly what's done so far, so you don't restart
finished work). Read §1 (executive summary) then §21 (the
dependency-ordered roadmap).

**[`CODEY_MASTER_PLAN.md`](CODEY_MASTER_PLAN.md) §2 remains the single
authoritative source for the non-negotiable operating rules** — RAM
discipline, no name-pattern kills, mandatory adversarial review on
process-lifecycle changes, and the rest — unchanged, not superseded, not
migrated anywhere. §0 (how to read it) and §3 (product scope/direction)
are also still useful background. §4's current-state snapshot and the
Track-A/WP-numbered portions of §6/Appendix A's work register are
**superseded in full for that scope** by the blueprint above — they're
frozen, not updated further; don't plan from them. **§6.3-§6.13/Appendix
A's Track B items (Restoricon business phases B1-B9) are NOT
superseded** — this census didn't cover them, so `CODEY_MASTER_PLAN.md`
remains the live tracker for that work, except Phase B9/Codey-Estimator
(also tracked in blueprint §14). Phase B8 (Sales Rep Portal) and the
rest of Track B have no blueprint equivalent yet — flagged as an open
reconciliation question for Ish, not resolved.

Then, for context on what just happened and what's known-broken:
- `PROJECT_LOG.md` — reverse-chronological record of every round (read
  the top few entries).
- `NEW_ISSUES.md` — append-only findings ledger (`NEW-##` IDs);
  authoritative for any individual finding's status.

**`CLAUDE.md` is the single copy of this project's ground rules**,
whatever agent you are. `ANTIGRAVITY.md` is a short pointer at it listing
the only three tool-specific differences; it was a full parallel copy
until 2026-09-02, when the two were collapsed because keeping two ~16KB
files hand-consistent was a drift risk rather than a design (`U.38` step
5, `NEW-289`). The rules are also reproduced tool-neutrally in
`CODEY_MASTER_PLAN.md` §2. There is no longer a second full rules file to
cross-check.

**Superseded 2026-08-21:** `CODEY_OS_MASTER_VISION.md`, `TODO.md`,
`WORK_QUEUE.md`, `PROJECT_PLAN.md`, and `Codey-Restoricon-OS.md` were
merged into `CODEY_MASTER_PLAN.md` and moved to `docs/archive/`. They are
evidence only — the verbatim reasoning and live-test output behind each
plan line. **Never plan work from them.**

Three things that get people (and agents) into trouble here, stated up
front — the full list is `CODEY_MASTER_PLAN.md` §2:

1. This device has ~10.8GB RAM and has crashed from concurrent model
   loads. Run `free -h` before any live model test and record it. One
   model-load cycle at a time.
2. Never kill a process by bare name pattern (`pkill -f llama-server`).
   Track and kill the specific PID your own code spawned.
3. Any process-lifecycle change (daemon start/stop, PID files, kill
   logic, model load/unload, API binding and auth) needs an explicit
   adversarial code review before commit — no exceptions for small-looking
   changes.

## The delegation pipeline

Every task runs through it, with no shortcuts for changes that look small
— that assumption is what has caused this project's worst bugs.
**`CLAUDE.md` has the diagram and the step-by-step; read it there.** It
is deliberately not duplicated here: this file used to carry a third copy
of it, which is exactly the drift the 2026-09-02 consolidation removed.

In one line: architect scopes → implementer builds and unit-tests →
**code-reviewer approves before every commit** → live-verifier confirms
on-device when the change needs real (not mocked) evidence → coordinator
updates `CODEY_OS_MASTER_BLUEPRINT.md`'s relevant roadmap entry (status
update, not `CODEY_MASTER_PLAN.md` §4/Appendix A — that's now frozen),
`PROJECT_LOG.md`, `NEW_ISSUES.md`, and commits.
