---
name: wp0_6_quarantine_metrics_approved
description: WP0.6 cap_metrics/reflections.jsonl quarantine + singleton test-isolation fix — APPROVED, two Warnings logged
metadata:
  type: project
---

Fixed the real root cause behind CODEY_OS_MASTER_BLUEPRINT.md §15.4's
"no reachable writer" finding: six production classes (AgentOrchestrator,
AutoImprovementLoop, GoalEngine, CapabilityOptimizer, LifecycleManager,
SkillRecombiner) call `get_performance_tracker()`/`get_reflection_engine()`
module-level singletons with no constructor override, so every CCOS test
constructing them with defaults was silently writing real rows into the
real on-device `ccos/data/ccos_memory.db`/`reflections.jsonl`. Fix: extract
`REFLECTIONS_PATH` as a module constant (mirroring `performance_tracker.py`'s
existing `DB_PATH`), add autouse conftest fixtures in both `ccos/tests/` and
top-level `tests/` that reset the module-global singleton (`_tracker`/
`_engine`) to `None` AND redirect `DB_PATH`/`REFLECTIONS_PATH` to `tmp_path`.
Plus a one-time `tools/quarantine_unsourced_ccos_metrics.py` that actually
ran on-device (cap_metrics 467→renamed, reflections.jsonl moved aside).

**Techniques worth reusing:**
1. **Data-attribute vs function-object monkeypatch distinction, settled by
   throwaway repro, not reasoning.** When a fix patches a module-global
   *data* variable (`_tracker`, `DB_PATH`) that a function reads via
   `global x` at call time, the patch takes effect for every caller
   regardless of which module imported the *function* by reference
   (`from origin import get_tracker`) — because the function's global
   lookups resolve against its *defining* module's namespace, not the
   importer's. Patching the function object itself would NOT have this
   property (confirmed via negative-control repro: patching
   `origin.get_tracker` to a lambda did NOT redirect a consumer that had
   already bound `get_tracker` by name via `from origin import
   get_tracker`). This distinction is easy to get backwards when reasoning
   abstractly — write the 10-line throwaway repro.
2. **Grep every demo/manual entry point, not just pytest-collected files,
   for the same writer pattern.** `ccos/demo_*.py` (4 files) call the same
   getters with defaults and are real, reachable (if manual) writers the
   conftest-only fix can never reach. Logged as a Warning/follow-up
   NEW-###, not a blocker — demos aren't automated — but it means a
   census's "no reachable writer" framing can still be incomplete even
   after careful grepping, if manual/demo entry points aren't included in
   the scope of "reachable."
3. **Quarantine/rename scripts for real on-device data need their
   destination path checked against `.gitignore`, not just the source
   path.** `ccos/data/reflections.jsonl` was gitignored by exact name
   (`.gitignore:46`); the renamed `reflections.jsonl.quarantined-<date>`
   was NOT matched by that pattern (`git check-ignore` confirmed one
   matches, the other doesn't) — same substring/exact-match-gitignore
   fragility class as `NEW-797` (`*token*` missing legitimate files). Two
   consequences worth checking on any "move aside, don't delete" script:
   the renamed file can get swept into a broad `git add`, and the script's
   own stated "rollback: restore from the moved copy" silently depends on
   a file `git clean -fd` would delete with no warning.
4. **Ledger-update timing is NOT a reviewer blocker here** — CLAUDE.md's
   own hub-and-spoke section puts ledger updates (blueprint DONE
   annotation, PROJECT_LOG entry) at step 5, explicitly after the
   code-reviewer gate at step 3. Confirmed via git log that WP0.5/WP0.7's
   blueprint DONE annotations were added in a *later* session than the
   commits that did the actual work (`f3459b0`/`9fa5594`), i.e. this
   lagging-ledger pattern is the project's actual rhythm, not an
   oversight to block on. Advisor caught me about to block on this
   incorrectly — note it as a handback reminder instead.

See also [[working_tree_cross_round_bleed]] (recurred again this round:
WP0.6's own diff was sitting in the same tree as WP0.5/WP0.7's blueprint
catch-up and a pile of new `.claude/agent-memory/` files) and
[[wp0_3_sibling_test_py_regression_changes_requested]] (same genre of
"grep every entry point, not just the pytest-collected ones" check, which
came back clean this time after grepping `ccos/plugins/`/`bench/`/
`pipeline/`).
