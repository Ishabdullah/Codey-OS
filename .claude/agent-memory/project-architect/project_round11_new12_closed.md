---
name: round11-new12-closed
description: Round 11 (NEW-12 dual-launcher fix) closed code-complete/reviewer-approved/live-verified 2026-07-30; NEW-13 spun off and left open
metadata:
  type: project
---

Round 11 (NEW-12) is closed as of docs commit `5a142d5` (fix commit
`59f4f69`). `core/inference.py`'s independent, uncoordinated
`_start_server()` llama-server launcher was removed; its fallback path
now delegates to `core.loader_v2.get_loader().ensure_model()`, the
canonical port-checked singleton launcher. code-reviewer approved.
live-verifier confirmed via: absence of a second spawn-attempt log line,
a successful non-error fallback completion (`'Hello'`), and clean
tracked-PID teardown — NOT via a literal ps snapshot (the verifier's
in-script ps capture had a filter bug: `ps` truncates `llama-server` to
`llama-serv`, so its substring match never actually confirmed "exactly
one process" at each checkpoint). This caveat is recorded precisely in
all three docs rather than rounded up to "ps confirmed."

**Why:** CLAUDE.md rule 5 requires literal evidence, not paraphrase —
this round is a template for how to word a live-verification claim when
the evidence is solid but not the exact form originally intended.

**How to apply:** When closing a round out in PROJECT_LOG.md /
PROJECT_PLAN.md / NEW_ISSUES.md, check whether the live-verifier's
evidence has a scope caveat like this one, and preserve it precisely
rather than collapsing to a blanket "live-verified." See also
[[feedback_verification_wording_precision]].

**Spun-off issue, still open:** [NEW-13] — removing `core/inference.py`'s
launcher orphaned `ThermalManager`'s thread-reduction restart mechanism
(logged commit `6093696`, Confirmed, not fixed).

**Remaining open items after Round 11:** NEW-7 (recursive planner,
hardest, deferred), NEW-9 (deprioritized per user decision — see
[[project_new9_atfork_race_status]]), NEW-11 (daemon watchdog stale-flag
gap, logged only), NEW-13 (thermal-restart regression, logged only),
plus deferred items from NEW-12's own scoping write-up: a single named
`SERVER_PORT` constant across `loader_v2.py`/`inference.py`/
`inference_hybrid.py`, wiring the planner model's launcher
(`PLANNER_MODEL_PATH`/`PLANND_SERVER_PORT`), and a real cross-process
flock/pidfile lock to close the daemon-vs-CLI port TOCTOU race.
