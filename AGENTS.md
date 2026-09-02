# Agent instructions — start here

**Read [`CODEY_MASTER_PLAN.md`](CODEY_MASTER_PLAN.md) first, every
session.** It is the single authoritative document for this project: what
it is, the non-negotiable rules, the architecture, where things actually
stand today, and every outstanding item in dependency order.

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
updates `CODEY_MASTER_PLAN.md` §4 + Appendix A, `PROJECT_LOG.md`,
`NEW_ISSUES.md`, and commits.
