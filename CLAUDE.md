# Codey-OS — Project Ground Rules

## What this project is
Local-first AI agent OS for Android/Termux (Samsung S24 Ultra). Canonical
spec: `CODEY_OS_MASTER_VISION.md` — read it, don't contradict it without
an explicit, logged decision.

## Non-negotiable rules

1. **Self-improvement mechanisms** (`goal_engine`, `auto_improvement_loop`,
   `capability_optimizer`, `skill_recombiner`) are permanently gated off
   from live execution. Never activate, wire up, or remove this gate
   without an explicit, direct instruction from Ish given in that exact
   session — not inferred, not implied by a task description.

2. **RAM discipline.** This device has ~10.8GB RAM and has crashed before
   from concurrent model loads. Before any live test that loads the local
   7B/1.5B/embedding models: run `free -h` and record it. Never run more
   than one live model-load cycle at a time — a cycle isn't done until the
   model is confirmed unloaded (`ps aux | grep llama-server` showing
   nothing but the grep itself). Batch multiple test messages into one
   interactive session rather than separate invocations.

3. **Never kill processes by bare name pattern** (`pkill -f <name>`).
   Always track and kill a specific PID your own code spawned. This
   project has been bitten by this exact bug before (a blanket
   `pkill -f llama-server` killed unrelated model servers).

4. **Any process-lifecycle change** (daemon start/stop, PID files, kill
   logic, locks, the GUI server's binding/auth) requires the
   code-reviewer subagent's explicit approval before commit, regardless
   of how small the change looks. This category has produced this
   project's worst bugs — including a well-intentioned, already-reviewed
   fix that introduced a new self-race (a daemon reading its own
   preemptively-written PID as evidence a duplicate was running).

5. **Verification means real, verbatim output** — actual `git diff`
   text, actual timings, actual `free -h` numbers — never a paraphrase
   or a "tests pass" summary. A claim isn't verified unless the literal
   output backing it exists.

6. **Correct the record when a claim doesn't hold up.** If a
   re-investigation shows an earlier finding was overclaimed, downgrade
   it explicitly in the docs rather than leaving the stronger claim
   standing. This has happened before and handling it honestly was the
   right call.

7. **Distinguish "code complete" from "live verified"** in
   `PROJECT_PLAN.md` and `PROJECT_LOG.md`. Never mark something fully
   done on code-complete/mock-tested evidence alone.

8. **Anything found outside a task's scope** — even something small —
   gets logged to `NEW_ISSUES.md` (rated Confirmed or Suspected based on
   actual certainty) and is not silently fixed or silently dropped.

9. **Update `PROJECT_PLAN.md` and `PROJECT_LOG.md`** after every
   completed round, with specifics — not "improved" or "done."

## Workflow

For a new piece of work: delegate to **project-architect** first to scope
it, then **implementer** to build it, then **code-reviewer** to approve
or reject it (loop back to implementer on rejection), then
**live-verifier** if on-device confirmation is needed. project-architect
updates the tracking docs once a round is fully done.

## When to stop and escalate instead of proceeding

- code-reviewer rejects the same fix twice without converging
- live-verifier shows the original symptom isn't actually resolved, or
  shows a new regression
- The work would touch `CODEY_OS_MASTER_VISION.md`'s own architecture, or
  any of the gated self-improvement mechanisms (see rule 1)
- Repeated Termux/device-specific failures suggesting an environment
  problem, not a code problem
- Anything genuinely ambiguous about product direction, not
  implementation detail
