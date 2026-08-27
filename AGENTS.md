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

`CLAUDE.md` and `ANTIGRAVITY.md` hold the same ground rules, each in the
format its own tool reads (Claude Code and Antigravity respectively —
both work on this repo). If you are a different agent, read whichever
one exists for your tool, or `CLAUDE.md` if neither does — everything in
either applies to you, and their rules 1–11 are reproduced in
`CODEY_MASTER_PLAN.md` §2 (kept tool-neutral there on any point where the
two files use different terminology for the same policy, e.g. rule 10's
subagent-registry check).

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
   logic, model load/unload, API/GUI binding and auth) needs an explicit
   adversarial code review before commit — no exceptions for small-looking
   changes.
