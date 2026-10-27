# C6 fresh classifier — complete 181/181 author packet (independent review PENDING)

Frozen source 770dc6639e4100ea3215fca07d923769a8290078 (`frozen_source_770dc66/`, read only). Author `/root/project_architect:C6_FRESH`.
All `reviewed_by` fields blank. Static source/caller reading only: no product import or execution, no tests, models, network, live state, repository edits or index operations.

## Original-author disagreement history (preserved, not replaced)
The original C6 author packet had an initial independent-review disagreement of **13/46 = 28.2609%** (seed 77020261102, random denominator 46,
`C6_REVIEW_DISAGREEMENTS.json`). That exceeded the threshold and required whole-unit fresh redo. This fresh packet does not erase or recompute that rate.
These counts mix taxonomy and caller-assumption differences; they are not counts of proven bugs.

## Final artifact
- `C6_FRESH_dispositions.tsv` SHA256 `b2aa8b12e8af1a1a9fcc1fe0ea3ea7a1f1b840f7554e1fdd02fac43fb0e84703`
- 181 exact keys == `C6_scan.tsv`; 43 files; 0 duplicates; reviewer blank on all rows; every row evidence-prefixed with `770dc663:<file>:<line> <qualname> <callee>`.
- Seal (hashes of TSV, builder, three own notes files, validator, scan, pre-22 and pre-fix TSVs): `C6_FRESH_seal.json`, written BEFORE old C6 labels were opened.
- Class counts: OPERATOR_SCRIPT_RUNNABLE 76, BOOKKEEPING 57, DORMANT 16, GATED 12, NATIVE_AUTHORITY 6, OPERATOR_BOOTSTRAP 6, UNMEDIATED 4, FALSE_POSITIVE 3, READ_NOEFFECT 1, UNKNOWN 0.
- Builder edit: one `exec(... C6_FRESH_selfimprove_notes.py ...)` line added before the final `save()` (builder SHA256 `563e7748d635f020af3036d1fab7341b5710a88cd18b554d47f418a5c3c4182e`; pre-edit copy `build_C6_FRESH.py.pre22`).
- Protection of the 159 earlier rows: `.pre22` TSV (SHA `a2f9c72e...c66`) vs final: 158 byte-identical + 1 explicit correction (below); exactly 22 new keys.

## Own source-first decisions for the final 22 (made and saved before old labels were read)
Stated rule applied uniformly: row inside a real `gate_exec` thunk -> GATED (plain `gate_exec`; scan `lexgate` is empty for all 22 so `lexical:`/`helper-of:` would fail the census check);
escaping destination with a queued severity-bearing finding owning that exact defect -> UNMEDIATED/LOW/dormant (NEW-1096, NEW-1097); other contained effects with proven non-normal reverse graph -> DORMANT (not BOOKKEEPING: executable staging / subprocess / scratch root are not group12 recording).

Reverse-caller proof (py + all-file-type string search incl. import_module/__import__): `optimize` <- `AutoImprovementLoop.after_task` (needs `_auto_optimize` and `self_improve.enabled()`) <- `LifecycleManager` (lifecycle_manager.py:195) <- `get_lifecycle_manager`, whose only non-test importers are demo_goal_engine, demo_improvement_loop, demo_skill_recombiner (plus historical G15b harness rows1.py text). `get_sandbox` consumers: only CapabilityOptimizer.__init__ and SkillRecombiner.__init__; other `ccos.core.sandbox` importers take constants only. `Sandbox.cleanup` callers: tests only. `create_workspace`, `install_package`, `execute_compound_skill`: no non-test callers. Default CODEY_SELF_IMPROVE off.

| Rows | Class | Basis |
| --- | --- | --- |
| optimizer `_deploy` x4 (449, 450, 455, 458) | GATED gate_exec, dormant | thunk via `_guarded` -> `gate_exec(HIGH_IMPACT, confirm_available=callable(confirm))`; fail-closed without confirm (action_gateway.py:529-540); preceded by promote decision, `may_deploy`, `_resolve_deploy_target`; `optimize()` hardcodes `no_evaluator()` and no confirm. Row 458 is the live-file overwrite. NEW-980/989 limits kept. |
| optimizer `generate_improved_version` x3 (236, 245, 250) | UNMEDIATED LOW dormant, NEW-1096 | `capability.replace(".","_")` does not stop an absolute dotless name; all effects precede every gate. Conditional HIGH impact, neither fixed nor accepted. |
| sandbox `create_workspace` mkdir (342) | UNMEDIATED LOW dormant, NEW-1097 | no containment of `name`; no caller. |
| sandbox `__init__` mkdtemp, `cleanup` rmtree, `install_package` mkdir, `run_command` subprocess.run, `run_python` write_text | DORMANT | contained/own-root effects or lexical-only subprocess (NEW-981: not gateway-mediated, not OS isolation, inherited env) reached only through the dormant chain. |
| recombiner `_process_pattern` mkdir + 3 write_text (623-635) | DORMANT, NEW-976/990 | contained staging dir (strict name regex, outside discovery roots and ALLOWED_DIRS) but explicitly NOT bookkeeping and NOT covered by the later deploy gate. |
| recombiner `_deploy` x3 (679, 682, 704) | GATED gate_exec, dormant | HIGH gate_exec with confirm; refuses existing/symlink dir; rmtree only a dir this call created. |
| recombiner `_execute_loaded_skill` x2 (810, 814) | GATED gate_exec, dormant | via `_run` with literal `confirm_available=False`, so the public path always refuses; no caller. |

## Post-validation self-correction (before any old label was read)
Own validator (census constants parsed by `ast`, not imported) flagged one previously saved row: `task_blackboard.py::TaskBlackboard.cleanup_task.<locals>.reset::*.execute::1` used mediator `helper-of:gate_exec` but its scan `lexgate` is empty, so the census would reject it. Mediator changed to plain `gate_exec`; evidence text and class unchanged. Pre-fix TSV SHA `51ea9bbb8b6f2f03c83325224d8dd1021a7c6f0fe27759aaa8c4c16fe0e1b030`; post-fix `b2aa8b12...`.

## Proposed findings (NOT logged; this classifier does not edit ledgers; need coordinator/reviewer decision)
1. **Optimizer no-test.py fallback**: `test_improvement` (capability_optimizer.py:353-360) calls `run_python` with code that `exec_module`s the staged candidate. Unlike the test.py branch (cwd in staging, refused by ALLOWED_DIRS) the command token and cwd are the sandbox's own temp root, inside ALLOWED_DIRS, so nothing fails closed: under shadow/on, with no neighbouring test.py, candidate code (existing implementation plus generated header/helpers) executes in a subprocess with inherited env before any evaluator/gate. Not stated in NEW-980/989/1096/981 as read. Dormant reach.
2. **Recombiner generated-code interpolation**: `generate_plugin_code` embeds `step.capability` unescaped in `"..."` literals; capability names are unvalidated (NEW-1086). Staged `pipeline.py` could carry injected code which a later confirmed deploy copies. Not stated in NEW-976/990/1086 as read. Dormant reach; staging itself executes nothing.
Both are static-source observations, not exploits.

## Validation (verbatim output file: `C6_FRESH_validation_output.txt`; `C6_FRESH_validation.json`)
`"ok": true` — 181 rows == 181 scan rows, exact keys match, 43 files, 0 duplicates, 0 non-blank reviewer, 0 field problems (class/reach/severity/UNMEDIATED finding+severity/GATED mediator/evidence prefix/rev/decider), 159 earlier rows preserved (158 identical + 1 correction), 22 new, 43 owning sources + 13 cited caller/gate/demo/tool files hashed against `frozen_source_manifest.json` with 0 mismatches (`C6_FRESH_hashes_final.json`).

## Reconciliation against old C6 labels (opened only after seal)
Old `C6_dispositions.tsv` vs fresh: same 181 keys; class differs on **24/181 rows**. Explanatory only, no old label copied; the 13/46 history above stands.
- Final-22 rows: 19/22 same class. Optimizer 7/7 and recombiner 9/9 equal (old recombiner staging rows carried LOW severity on DORMANT, fresh leaves blank and cites NEW-976/990; mediator wording differs only cosmetically). Sandbox: `create_workspace` old DORMANT vs fresh UNMEDIATED/LOW/NEW-1097 (matches the original reviewer's initial UNMEDIATED, and the coordinator-confirmed NEW-1097; identical effect/reach/finding either way). `__init__` mkdtemp and `cleanup` rmtree old BOOKKEEPING vs fresh DORMANT (same effect, a taxonomy choice; BOOKKEEPING would borrow the group12 recording contract for a scratch root).
- Earlier-159 differences, 21 rows, not re-decided here: git_integration/test.py 14 (old DORMANT vs fresh OPERATOR_SCRIPT_RUNNABLE; the agreed spec1.3 demo/plugin-test convention), ccos_memory StructuredDB 4 (old BOOKKEEPING vs DORMANT after no-call search), plugin_manager `_call_capability._execute` urlopen (old NATIVE_AUTHORITY vs GATED via gate_exec callback), `_remove_owned_record` os.open (BOOKKEEPING vs READ_NOEFFECT), device_manager `_run_cmd` (READ_NOEFFECT vs DORMANT).
- Of these, differences are taxonomy/reach presentation with the same findings; the reviewer should check the mandatory 100% of UNMEDIATED and GATED rows (4 and 12) and the NATIVE_AUTHORITY/helper-rule rows.

## Limitations
Static reading only (no execution, no tests); reverse-caller proof is textual search over the frozen tree, which cannot see runtime string-built imports outside the searched forms; independent review not yet done; no row is signed; the two proposed findings and the BOOKKEEPING-vs-DORMANT scratch-root choice need reviewer judgment.
