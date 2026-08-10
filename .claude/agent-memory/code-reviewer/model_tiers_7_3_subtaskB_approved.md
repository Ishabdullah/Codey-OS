---
name: model-tiers-7-3-subtaskB-approved
description: core/model_tiers.py + tests/test_model_tiers.py (TODO 7.3 sub-task B) review outcome and coverage-gap pattern
metadata:
  type: project
---

APPROVED (with non-blocking Warning + Suggestion). Pure data module,
`(domain, role, tier) -> ModelTierEntry`, only imports `utils.config` +
stdlib (no ccos import, satisfies the core/->ccos one-way-edge rule).
Verified against source, not just docstring claims:
- All cited `utils/config.py` constants (`MODEL_PATH`,
  `PLANNER_MODEL_PATH`, `PRIMARY_SERVER_PORT`, `PLANND_SERVER_PORT`,
  `is_remote_backend()`, `is_remote_planner_backend()`,
  `CODEY_PLANNER_BACKEND`, `OPENROUTER_MODEL`/`_PLANNER_MODEL`,
  `UNLIMITEDCLAUDE_MODEL`/`_PLANNER_MODEL`) exist and match.
- `SECONDARY_MODEL_PATH` correctly absent from the table (NEW-84 dead
  config) — grepped `core/lora_import.py` lines 25-41, comment block is
  real and says what the docstring claims.
- NEW-125 same-physical-model claim checked against the actual
  (uncommitted, WIP) `core/orchestrator.py` — `plan_tasks()` still at
  line 344, still routes through `recursive_infer()`/the 7B model; the
  docstring citation wasn't stale despite that file having an unrelated
  276-line uncommitted diff sitting in the tree at review time.
- Not wired into any loader/dispatch path (`grep -rn model_tiers`
  outside the new two files = nothing) — matches the stated scope.

**Bug pattern worth remembering**: a large uncommitted diff to a file a
docstring cites (`core/orchestrator.py` here) is not automatically
out-of-scope WIP bleed — check `TODO.md`/`WORK_QUEUE.md` diff text
first. Here it turned out to be a *different, already-approved*
sub-task (7.3 sub-task A) sharing the same working tree, not stray
leftovers. Don't assume [[working_tree_cross_round_bleed]] every time;
verify via the tracking-doc diff before flagging it as a problem.

**Coverage gap pattern to check for in future data/config-table
reviews**: tests asserting `has_remote == cfg.is_remote_backend()` are
tautological under a single fixed test-run env — they pass on both
branches without checking entry *content*, and any branch not exercised
by the one `monkeypatch.setenv` reload test (here: planner's remote
branch entirely, and the `unlimitedclaude` arm of both ternaries) has
zero real coverage despite "N passed". Ask for the reload test to be
parametrized over every backend x role combination the ternary
branches on, not just one.

**Design note (judgment call, not a defect)**: local tiers are listed
unconditionally in the table while the remote tier is listed only when
that backend is actually active (`cfg.is_remote_backend()` true at
import time) — this is an intentional asymmetry ("formalize today's
fixed assignment", not "declare all possible backends"). Consequence:
`get_tier(domain, role, "remote")` raises `KeyError` whenever the
process is running on the local backend. Flagged as a Suggestion: any
later sub-task (C/E) that calls `get_tier(..., "remote")` must guard
with `("domain","role","remote") in MODEL_TIERS` or `is_remote_backend()`
first — worth one contract line in the module docstring so it isn't
rediscovered as a bug later.
