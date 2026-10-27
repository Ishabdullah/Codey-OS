# Supplementary dispositions (NEW-1101, Ish decision 2026-10-27, option 2) - final revision after independent review rounds 1-3

`supplementary_dispositions.tsv` holds 15 rows for `exec_module` execution sites (frozen revision 770dc66, scratch copy):

1. `ccos/core/plugin_manager.py::PluginManager._load::*.exec_module::1` (line 1208): class **UNMEDIATED**, reach
   prod-confirmless, severity MEDIUM, finding NEW-1102 (execution trust boundary; no content integrity check, no
   gate_exec) plus NEW-1101 (scanner gap), NEW-1086, NEW-1069. Re-classed from the first draft's OPERATOR_BOOTSTRAP after
   independent review (CHANGES REQUESTED). NEW-953 is related only (partial registration after spawn), not cited as the
   boundary. Structural containment (enabled flag, discovery refusals, resolve_plugin_file) is partial mitigation, not a
   gate; mediator column is empty per UNMEDIATED convention.
2. `ccos/core/skill_recombiner.py::SkillRecombiner._execute_loaded_skill::*.exec_module::1` (line 815): class GATED
   (gate_exec HIGH_IMPACT, confirm_available=False), dormant. Approved by the independent review; unchanged except an
   evidence note on the marker-file discriminator and finding cross-references.
3. 13 OPERATOR_SCRIPT_RUNNABLE `<module>::*.exec_module::1` rows, reach operator-only, one per `ccos/plugins/**/test.py`
   (coding/{agent,error_recovery,finetune,git_integration,peer_escalation,static_analysis,task_queue}, crm/core_query,
   device/bridge, research/rag_retrieval, system/{daemon_control,observability,thermal_monitor}). Each executes the fixed
   repo-relative `ccos/plugins/_pathutil.py`. Each file, qualname (`<module>`), line and the key form `*.exec_module` was
   verified from the frozen tree by extracting `_resolve`/`_collect_aliases` from the frozen scanner via ast (not
   imported), see `_verify13.py`. Findings NEW-1101;NEW-1069, same conventions as the sibling test.py rows.

## Status, generation, validation

- Independently reviewed in rounds 1-3 (`SUPPLEMENTARY_REVIEW.json`): round 1 CHANGES REQUESTED (class fix, 13 rows,
  mentions), round 2 required reach/first_seen fixes, round 3 APPROVED content SHA256
  5911d423e4150cbc2f92ae9d6d193f0962e030b5189a4403b863ebb74a89d349. Final step then set `reviewed_by` =
  `/root/code_reviewer:SUPP_NEW1101` on all 15 rows (only that column changed vs the approved file; kept as
  `supplementary_dispositions.tsv.pre_reviewedby`).
  Final `supplementary_dispositions.tsv` SHA256: 50fa9ba0cac5cb324daed87bb48a33c7019d9b0dea631a064cee82a9661b3e2a.
- Reach: the 13 operator-script rows keep `operator-only` (closed vocabulary); the agent-shell ACT via python script
  (NEW-904 ceiling) statement is in their evidence. `first_seen_rev` = 941ec3fb076d97e6e0998c0ea98eee086e6b0915 on all
  15 rows (each file contains `exec_module(` at that revision, verified with `git show`); evidence line numbers are 770dc66.
- Generation: `python3 -I _build.py [OUT] [--reviewed-by VALUE]` regenerates the TSV from `*.pre_review` (draft evidence
  text), the merged candidate (sibling tails) and `_verify13.json`. Without `--reviewed-by` it reproduces the
  round-3-approved file byte-for-byte (cmp verified); with `--reviewed-by /root/code_reviewer:SUPP_NEW1101` it produces the final file.
- Validation in the script: vocabulary asserts (class/reach/severity, gate names, UNMEDIATED needs finding+severity),
  `parse_register` round trip with identical re-render. `--check` is NOT run over these rows (see Limitation 2).

Same columns (`REGISTER_COLUMNS`) and `file::qualname::callee::ordinal` key format, rendered through frozen
`render_register`, validated by `parse_register` round trip.

## Sibling rows unchanged (coordinator decision)

Candidate lines 66-67 (`_load::importlib.util.spec_from_file_location` / `::module_from_spec`, OPERATOR_BOOTSTRAP,
C6_FRESH) and the C6 `spec_from_file_location`/`module_from_spec` rows of the test.py scripts stay as they are. They only
PREPARE the module and execute nothing; the executing step is the supplementary `exec_module` row (per the NEW-1102
classification note). The class difference between the plugin_manager siblings and the new row is therefore deliberate and logged.

## Limitation (accepted, not fixed)

1. The scanner constant `DYN_EXACT` (tools/wp21_census.py:146-150) lacks `exec_module` / `load_module`, so `scan.tsv` has
   NO rows for these calls. The scanner and frozen inventory are intentionally NOT extended; dynamic-module-execution
   inventory relies on these supplementary rows plus this recorded limitation. Key form confirmed `*.exec_module` by the
   independent reviewer using the frozen `_resolve` (receiver root `spec`/`_spec` is not an import alias).
2. These rows are OUTSIDE the scan-checked register and must not be merged into `dispositions_candidate.tsv`:
   `evaluate_coverage` (wp21_census.py ~1304-1308) reports every register key absent from the scan as a `stale-row`
   failure, which would fail `--check` on the passing candidate. Nothing in --check verifies these rows; a later edit that
   moves/renames a call would not be detected.

## Cross-referenced mentions (no rows)

- `ccos/core/capability_optimizer.py:356-357`: a string passed to `self._sandbox.run_python` does
  spec_from_file_location + exec_module of the candidate `new_path` (no-test-file fallback). Inside a string literal so the
  scanner cannot see it. Tracked as NEW-1099 (candidate code executed pre-gate in a sandbox subprocess).
- `ccos/core/skill_recombiner.py:428-452`: string literals emitting `exec_module` into GENERATED test.py source. Not calls,
  not executed there. Tracked as NEW-976 (generated plugin content written into the discovery root).
- `tools/encrypt_cloudflare_token.py:65` `importlib.reload(config_module)`: re-executes in-repo `utils/config.py` only; no
  attacker input; operator-run tool. LOW / operator-only. Same scanner-gap class as NEW-1101 (`importlib.reload` not in
  DYN_EXACT); no row.
- Test-only sites outside the scan (`tests/` and `ccos/tests/` are EXCLUDED_COMPONENTS): `ccos/tests/test_ccos.py:19`,
  `ccos/tests/test_sandbox_path_validation.py:17`, many `tests/*.py` exec_module sites (test_g15h_masking_redaction,
  test_git_* , test_main_peer_gateway, test_s2_flush_seam, ...), and `importlib.reload` in tests/test_74b_*,
  test_config_llama_server_bin, test_model_tiers, test_new855, test_u31_*.
- `docs/wp2_1_g15b_harness/*` probe scripts contain `exec(open(...))` / `__import__`; whether the scanner covers `docs/` is
  UNVERIFIED, so their register status is unknown.
- `core/cli_client.py:129` `importlib.import_module('main')`: NOT a gap. Already covered by register row
  `core/cli_client.py::_direct::importlib.import_module::1` (OPERATOR_BOOTSTRAP, candidate line 607). Removed from the
  author's earlier "uncovered" list.
- Not verified by the reviewer: `install.sh:525` `python3 -c` content was not read in full.
