# WP2.1 group 14 scope — self-improvement artifact boundaries

Architect handoff, 2026-10-17. Source inspection against the live tree at
`295956b` (HEAD), plus a handful of pure/offline probes (listed in "Method and
limits"). This report owns no finding IDs or completion status; blueprint WP2.1
and `NEW_ISSUES.md` remain authoritative. Provisional labels `G14-F#` below are
for the coordinator to turn into `NEW-975+` entries (last allocated ID is
`NEW-974`). No source, test or tracking document was edited. Group 13 is still
OPEN per the blueprint (`876e1b6` records NEW-971 as not live-verified and
NEW-972 as open debt); nothing here changes that status.

## Method and limits

- Read: `docs/WP2_1_HANDOFF_2026-10-17.md` (retained cases), blueprint WP2.1
  Status update, `CLAUDE.md` rule 1 / `CODEY_MASTER_PLAN.md` §2, the group-13
  gate_exec precedent (`core/action_gateway.py:126-495`: `gate_exec`,
  `gate_write`, `gate_append`, `refuse_exec`; static `action` label doubles as
  the audited `command`), `docs/wp2_1_group12_persistence_contract.md`.
- Probes run (all offline, none loaded a model, none signalled a process):
  pure functions `is_core_file`, `classify_write_action`,
  `Filesystem._validate_path`, `Sandbox._validate_path`,
  `manifest_schema_v2.normalize_manifest`, `classify_shell_command`; real
  `ruff` (installed, 0.17.1) on throwaway projects under the session scratch
  dir; reads of `ccos/data/capabilities.json`. Later imports used
  `CODEY_STATE_DIR` pointing at the scratch dir. **Disclosure:** my first two
  probes (`is_core_file`, `plugin_manager` constants) ran before I set that
  override; `~/.codeyOS/checkpoints` already existed (mtime Oct 13), so nothing
  new was created there, but I cannot rule out a default-state-dir schema
  touch from those two imports.
- NOT verified (rule 12 — do not cite from memory): behavior of `flake8` and
  `mypy` config/plugin loading (neither is installed on this device; `which`
  returns nothing); whether `/proc/net/tcp` is readable on-device (NEW-86
  ledger says it was not readable in the dev sandbox); which cwd the daemon
  process runs in; what the daemon's shell allowlist (`_shell_fn`) refuses.
  Anything depending on those is rated Suspected below.

## Verified facts (the ones the slice plan stands on)

**F1 — Classification is shallow and narrow (NEW-951, confirmed + widened).**
`core/checkpoint.py:51-64` `is_core_file` requires `relative_to(CODE_DIR/<root>)`
then `path.match("<root>/*.py")`; `Path.match` is right-anchored, so
`core/sub/x.py` fails (probe: direct `core/x.py` -> HIGH_IMPACT, `core/sub/x.py`
-> ACT). Roots are only `core, tools, utils, prompts` (`checkpoint.py:32-37`).
Currently zero nested files exist under those four roots (Python `rglob` count
0 each), so a recursive fix reclassifies no existing file. Probe with
`Filesystem(workspace=CODE_DIR)` (the situation when the CLI/daemon cwd is the
repo): `_validate_path` returns early for anything inside the workspace
(`core/filesystem.py:130-136`), so the `allow_self_modification` opt-in never
applies, and `classify_write_action` (`tools/file_tools.py:89-118`) returns
**ACT** (no *gateway* confirmation; see "Confirmation context" below) for every one of: `ccos/plugins/<newcat>/<p>/__init__.py`,
`ccos/plugins/<newcat>/<p>/manifest.json`, `bench/gate.py`, `bench/suite.lock`,
`main.py`, `codey`, `lib/service_manager.sh`, `install.sh`, `.codeyignore`,
`CODEY.md`, `ruff.toml`, `.flake8`, `mypy.ini`. `CODEY.md` is in
`WRITE_PROTECTED` (`file_tools.py:54`, separate `ask_confirm`) but
`.codeyignore` and the linter configs are not. `create_checkpoint`
(`checkpoint.py:69,100`) already backs up via `rglob("*.py")` for the four
roots, evidence the intent was recursive; backup scope and classification
scope are currently the same constant and must be decoupled before roots grow.

**Confirmation context (qualifies every "ACT" in this document).** ACT means
the gateway adds no confirmation of its own; the UI layer still prompts when
`AGENT_CONFIG["confirm_write"]`/`["confirm_shell"]` are true (default True,
`utils/config.py:156-157`): `tool_write_file` asks before gating, and `shell()`
asks for every READ/ACT command unless `yolo` or `confirm_shell` is False
(`tools/shell_tools.py:~700-745`). Those flags are forced False in the
unattended contexts: `main.py:114-115` (yolo), `main.py:2234-2235` (`--fix`),
and `core/task_executor.py:397-398` (every daemon task). Therefore the
"unconfirmed" exposures below apply under `--yolo`, `--fix` and daemon tasks;
in default interactive mode the human sees a per-write/per-command prompt
(and for the shell tool a model-issued `python3 -c` / `codeyOS --import-lora`
is likewise prompted). Whether the daemon case reaches the repo tree depends
on the cwd the operator launched it from: `core/service_lifecycle.py:92-96`
starts the daemon profile with `cwd = Path.cwd()` (no chdir) and
`WORKSPACE_ROOT = Path(os.getcwd())` (`utils/config.py:315`), so a daemon
started from inside the repo has the whole repo in its workspace, one started
elsewhere does not — **unverified on-device which one is in use**. Also,
because the model can already run `python3 -c ...` as ACT (NEW-904, deferred),
writing a plugin is not a new *execution* capability; what is new is
**delayed execution outside the originating session's confirmation** — the
file runs at the next process's first REPL prompt (F2), after the prompt that
authorized the write is long gone.

**F2 — The plugin tree is an auto-executed artifact root.**
`ccos/core/plugin_manager.py:581-610` `_discover` walks
`ccos/plugins/*/*/manifest.json` (default `plugin_dirs`, line 476), and
`_load` (636-738) `exec_module`s the entry point in-process (705-711) or, for
`external_process|isolated_daemon|remote_bridge`, `subprocess.Popen`s the
manifest's own `process_spec.start_command` with manifest-supplied env/cwd
(`start_external_plugin`, 334-374). Production path to `load_all()`:
`main.py:1977` prints `get_render_text()` after every REPL input ->
`core/dashboard_data.py:47-62` -> `get_snapshot()` -> `_plugin_manager()` ->
`load_all()` (dashboard_data.py:32-39). So any plausible plugin directory that
exists at process start is imported/spawned at the first REPL prompt, with no
authority check at activation (13h made activation transactional, not
authorized). `call_capability` stays fail-closed for unclassified names, but
import-time and spawn-time code does not go through `call_capability`.
`normalize_manifest` accepts the recombiner's generated manifest shape
(probe), so "schema rejects it" is not a defense.

**F3 — The self-improvement stack has no production caller.** Non-test,
non-demo importers of `lifecycle_manager` / `auto_improvement_loop` /
`capability_optimizer` / `skill_recombiner` / `goal_engine`: none
(grep of all `.py` + launchers). `ccos/core/sandbox.py` methods `run_command`,
`run_python` are reached only from `capability_optimizer.py:305,319` and
`skill_recombiner.py:594`; `run_plugin_test` / `install_package` /
`create_workspace` have no callers. `tools/quarantine_unsourced_ccos_metrics.py`
header independently states the same census conclusion. Everything below in
`ccos/core` is therefore "dormant-but-armed": hardening must not add callers
(precedent: groups 11, 12b).

**F4 — Recombiner shadow mode already deploys files into the auto-executed
root.** `skill_recombiner.py:577-589` writes `manifest.json`, `pipeline.py`,
`test.py` under `plugin_base` (default `ccos/plugins/compound`, line 516-518 — inside
F2's root) *before* the sandbox call (594) and *before* the `may_deploy()` check
(608), so shadow mode ("generated and sandbox-tested, not registered") and
sandbox-failure paths both leave a discoverable plugin on disk; the next
process start executes `pipeline.py` at `load_all()`. Registration (631)
checks only `self_improve.may_deploy()` (env `on`), **not** a `GateDecision` —
unlike `capability_optimizer.compare_and_upgrade` (344-396), so rule 1's
"only behind the promotion gate" is not met here. Also
`execute_compound_skill` (672-718) `exec_module`s a registry-named path in
process with no gate.

**F5 — The sandbox is not a security boundary and cannot currently run these
candidates.** `ccos/core/sandbox.py:152-196` runs `subprocess.run(command,
shell=True, env=os.environ.copy())`; confinement is a substring blocklist
(`BLOCKED_COMMANDS`) plus a best-effort path-token scan that its own docstring
says fails open (`_find_disallowed_path_token`). No rlimits, network or env
scrubbing. Separately, `ALLOWED_DIRS` (lines 24-36) deliberately excludes
`ccos/` (WP2.3a). Probe: `_validate_path` is False for
`ccos/data/staging/x` and `ccos/plugins/compound/x`, True only under the temp
dir, so both `capability_optimizer.test_improvement` (cwd = `ccos/data/staging/...`,
305-312) and the recombiner's sandbox step (cwd = plugin dir) are rejected as
`[SANDBOX VIOLATION]` today. Accurate summary: **candidate execution is
broken-safe, not working; but candidate file writes are not**.

**F6 — Optimizer deploy has no target containment, and live registry entries
make it inert.** `capability_optimizer.py:406` `shutil.copy2(new_path,
cap.implementation)`: no containment/checkpoint. `ccos/data/capabilities.json`
(161 entries): zero `implementation` values are file paths — they are
`module:function` strings or `http://127.0.0.1:...` URLs, so
`generate_improved_version` returns None on `impl_path.exists()` (`:178`) and
`optimize()` is a no-op for every live capability. Recombiner-registered
capabilities (F4) are the only ones with file-path implementations, so the
uncontained `copy2` would be pointed at generated files — and, if a path-like
`implementation` were ever hand-registered to repo code, overwrite it with no
checkpoint. `optimize()` passes `no_evaluator()` (`:478-481`), so the gate
refuses today; `compare_and_upgrade` with an approving decision is the
armed-but-unreachable path. `bench/scorecard.py:565-583` AST-checks this
function's structure (`shutil.copy2` backup write, gate check), so edits must
keep `tests/test_scorecard.py` / `tests/test_promotion_gate.py` green and must
not relabel to move a score (rule 1).

**F7 — LoRA adopt/rollback has a real promotion gate and no ActionGateway
mediation, and its override flag is shell-reachable.** `core/lora_import.py`:
`import_lora_adapter` (597-806) consults `bench.gate` (default
`no_evaluator()`, refuses unless `operator_override`), but backup
(`create_backup_before_import`, 429-462: multi-GB `shutil.copy2` beside the
model), on-device merge (`_merge_with_shell`, 237-304: `subprocess.run` of
`~/llama.cpp/convert-lora.py` / `quantize`, 3600 s each), swap
(`swap_to_finetuned_model`, 307-426: mutates `cfg.MODEL_PATH` + unload/load;
lifecycle truthfulness was 13e) and `rollback_to_backup` (465-566: copy2 over
the live model file + unlink backup) call no gateway (grep: no
`action_gateway` import in `lora_import.py`/`model_registry.py`). Production
callers: `main.py:2259-2295` (`--import-lora`, `--lora-force-adopt`) and the
documented `python3 -c "...rollback_adoption(...)"` (`main.py:2288`). Probe:
`classify_shell_command("codeyOS --import-lora X --lora-force-adopt")` and the
`rollback_adoption` one-liner are both **ACT**, i.e. the agent's own shell tool
can reach the "operator override" with no *gateway* confirmation (a per-command
shell prompt still appears in default interactive mode, but not under `--yolo`,
`--fix` or daemon tasks, where `confirm_shell` is False — see "Confirmation
context"; whether the daemon's shell allowlist `_shell_fn` refuses this is
unverified). `subprocess.run` in
`tools/shell_tools.py:634` passes no `stdin=` and captures stdout/stderr, so a
child's `input()` prompt text would be invisible; a confirm in a CLI entry
path must use `/dev/tty` for prompt and answer.

**F8 — Linters: cwd cache writes (verified) and config-executable surface
(unverified).** `core/linter.py` runs `ruff|flake8|mypy` via bare names with
the file path as argv and inherited cwd (`run_linter` 121-193, `run_all_linters`
196-256). Reached from `core/agent.py:797` (post-write lint of every model
`write_file`/`patch_file` of a `.py`) and `main.py:1375-1440` (`/review`,
operator-typed, argument path unvalidated beyond `exists()`). Verified with the
installed ruff on a scratch project: default `ruff check` creates
`.ruff_cache/` in the checked project; `--no-cache` created nothing;
`--isolated` made a workspace `ruff.toml` (selecting only E) stop applying.
`WRITE_PROTECTED` covers `pyproject.toml`/`setup.cfg` but not `.flake8`,
`tox.ini`, `mypy.ini`, `ruff.toml`, so a model can write those freely
(probe F1). Flake8 local plugins / mypy `plugins =` execute project-supplied
Python by documented design, but neither tool is installed here and I did not
read their artifacts: **config-code-execution is Suspected, not Confirmed.**
`pylint` is listed by `get_available_linters` but never executed.

**F9 — Embedding foreign-port kill is still an integer-PID SIGKILL of an
arbitrary occupant.** `core/embed_server.py:504-629` `_kill_port_occupant`:
resolves a PID by `/proc/net/tcp` inode scan or, if unreadable, by the
registered embed slot (`_find_pid_via_registered_slot`, 435-473, identity =
liveness + the substring `b"llama-server" in cmdline`), re-runs the same
lookup once (NEW-86), then `os.kill(pid, 9)`; it explicitly refuses a
"must be llama-server" gate (comment 553-562) so a non-llama squatter on the
embed port is SIGKILLed with no argv/exe/model/port/boot/start/UID check, no
TERM stage, no audit. Reachable from `EmbedServer._start` (190-197) whenever the
port is bound and not healthy-adoptable — an automatic daemon/inference path
(13f: "accounted-but-exempt, no new foreign-port authority"). NEW-969
(`876e1b6`) already built the contract and helpers for exactly this class:
`core/loader_v2.py:220-335` (`_same_foreign_identity`, `_foreign_state`,
`_capture_foreign_primary`, `_kill_single_pid_term_then_kill`) over
`core/process_identity.py` (`process_info`, `valid_pid`, boot/start/UID).

**F10 — `/undo` is an unmediated raw write.** `core/filehistory.py:65`
`p.write_text(content)` restores a snapshotted path (in-memory `_history`,
per session) with no `_validate_path` re-check (workspace may have changed via
`/cwd`), no git-metadata denial, no `is_core_file` classification and no
checkpoint — so it can silently revert an edit to a HIGH_IMPACT core file that
the gateway had confirmed. Operator-typed (`main.py:850-865`) but not in
NEW-939's list; new finding.

**F11 — NEW-939 sites, re-verified.** All operator-typed or fixed-location;
none model-selected paths. (a) `main.py:1326` `/ignore` appends to
`<cwd>/.codeyignore` (narrows what the agent sees, `core/context.py:33-86`);
(b) `main.py:494-521` `run_init` (+ `--init` at `main.py:2174`, `/init` at
`main.py:1199`) writes **LLM-generated, unreviewed** text via
`core/codeymd.py:39` into `<cwd>/CODEY.md`, which is loaded into the system
prompt; the only guard is an "Overwrite? [y/N]" if one exists. The sibling
automated CODEY.md writer `core/preferences.py:455-560` is already
**HIGH_IMPACT** with fail-closed confirm — so `/init` is the same artifact at a
lower class; (c) `core/sessions.py:71,112` (`~/.codey_sessions/<dir>_<hash>.json`,
per-turn `save_session` at nine `main.py` sites; redaction exists); (d)
`core/voice.py:56-67` `_save_config` (called from `voice.py:275-302`, config
setters); (e) `core/taskqueue.py:102` `TaskQueue.save` ->
`~/.codey_sessions/queue_<proj>_<md5>_<HHMMSS>.json`, reached from every
planned task via `core/orchestrator.py:460,576,751` (so it *is* production
reachable, including the plan path used by `core/agent.py:1785`); (f)
`core/agent.py:1695` design-note write `<cwd>/<peer>_design.md`: sits behind
the `gate_exec(HIGH, confirm_available=False)` at `agent.py:1657-1663`, which
always refuses, so the sentinel `[PEER_ERROR: blocked...]` makes
`is_peer_error` true and the branch falls through — **dormant today**, and
the only other design-file reference is a *read* (`agent.py:1127-1151`,
loads `<peer>_design.md` into context). KB: `tools/kb_semantic.py` writes
(`build_semantic_index` 350-449, `repair_failed_embeddings` 456-555) and
`tools/kb_scraper.py:114` have **no production caller** (only
`tools/setup_skills.sh` and docs); the retrieval path (`core/retrieval.py:161,
271`) calls only read-only `has_index/semantic_search/keyword_fallback`
(lines 585-690 contain no writes). Export: `core/finetune_prep.py` writes
(396-403, 718, 759) reached only from `main.py:2243` (`--finetune`) and from
unclassified plugin capabilities (fail-closed at `call_capability`, table has no
`coding.finetune_*` entries); `pipeline/` has no importer outside itself
(operator CLI `pipeline/run.py`).

**F12 — Standalone/installer scripts.** Agent-reachable only through the shell
tool, which classifies every one of these **ACT** (probe, 14 command shapes:
`bash install.sh`, `./setup_repo.sh`, `bash tools/setup_skills.sh`,
`python3 core/setup_dr_key.py --force`, `python3 core/backup_secrets.py`,
`python3 tools/provision_ai_agent_auth.py`, `python3 -m
tools.encrypt_cloudflare_token --force`, `pip install flake8`,
`gh repo create x --public`, the quarantine tool) — consistent with NEW-904's
deferred interpreter policy, which this group must not pre-empt. Non-shell
production reach: `lib/service_lifecycle.sh:170-171` runs `setup_litestream.py`
then `backup_secrets.py` inside the 13d-mediated service start; `core/
service_lifecycle.py:118` supervises `backup_documents.py --daemon` (13c/13d);
`install.sh:549` runs `setup_dr_key.py` interactively. `setup_repo.sh` can
create a `--public` GitHub repo; `provision_ai_agent_auth.py` defaults to the
live Restoricon DB path (rule: never write the live store in dev); neither has a
confirmation. Cloud/GCS behavior is NEW-943/944 and is not touched here.

## Disposition inventory

"Reach" = reachable from a production caller. "Gated" = current mediation.
Slices defined in the next section.

| # | Writer / executor | File:line | Reach | Gated today | Disposition | Slice |
|---|---|---|---|---|---|---|
| 1 | Nested-core + non-core executable classification | `core/checkpoint.py:51-64`; `tools/file_tools.py:89-118`; `core/filesystem.py:225,264,298,354` | model `write/append/patch_file`, recovery mkdir | ACT for nested core and all of `ccos/`, `bench/`, `lib/`, launchers | recursive within 4 existing roots now; wider roots = Ish fork 1 | 14a (+14a-ext) |
| 2 | `/undo` restore | `core/filehistory.py:65`, `main.py:850-865` | operator REPL | none | gate: ACT, HIGH_IMPACT with real confirm if `classify_write_action` says core; re-validate path; no double snapshot | 14b |
| 3 | Auto-lint post-write | `core/agent.py:797` -> `core/linter.py:121-193` | every model `.py` write | none (shell-free subprocess) | ACT envelope, `--no-cache`, `--` separator; flake8/mypy only if isolation verified (fork 3b) | 14c |
| 4 | `/review` linters | `main.py:1375-1440` -> `linter.py:196-256` | operator REPL | none | same as 3 | 14c |
| 5 | Embed foreign `SIGKILL` | `core/embed_server.py:504-629` | automatic embed start | none | bracketed identity + TERM->KILL + audit; unknown occupant = refuse | 14d |
| 6 | LoRA import (backup/merge/swap) | `core/lora_import.py:429-462,237-304,307-426,597-806`; `main.py:2259-2295` | operator CLI; **shell tool as ACT** | promotion gate only | HIGH_IMPACT with real `/dev/tty` confirm around the mutating span; promotion-gate logic untouched | 14e |
| 7 | LoRA rollback | `lora_import.py:465-566,569-594` | documented `python3 -c`; shell tool ACT | none | HIGH_IMPACT, same confirm | 14e |
| 8 | Recombiner file writes | `ccos/core/skill_recombiner.py:577-589` | none (F3) | none | stage outside discovered roots; promote only via HIGH gate + `GateDecision` | 14f |
| 9 | Recombiner registration | `skill_recombiner.py:608,631` | none | `may_deploy()` env only | require approving `GateDecision` (rule 1) + HIGH gate | 14f |
| 10 | `execute_compound_skill` | `skill_recombiner.py:672-718` | none | none | HIGH gate with `confirm_available=False` (fail-closed, no new caller) | 14f |
| 11 | Optimizer staging writes | `capability_optimizer.py:200-214` | none | none | keep (outside discovery root, `ccos/data/staging`), document; no change needed beyond contract test | 14f |
| 12 | Optimizer deploy `copy2` | `capability_optimizer.py:386-406` | none | gate + `may_deploy` | contain target to existing regular file under approved roots; HIGH gate; keep gate logic byte-identical | 14f |
| 13 | Sandbox | `ccos/core/sandbox.py` | none (only 11/12/8) | blocklist | docstring correction only ("not a security boundary"); no behavior change | 14f |
| 14 | Plugin-tree activation | `ccos/core/plugin_manager.py:581-738,334-374`; `dashboard_data.py:32-39` | **yes**, first REPL prompt | none | depends on fork 4: protected root (14a-ext) and/or activation allowlist | 14h (conditional) |
| 15 | `/init` CODEY.md | `main.py:494-521`; `core/codeymd.py:39` | operator REPL/CLI | none | gate like `preferences.sync_to_codeymd` (HIGH or ACT-new/HIGH-overwrite = fork 5) | 14g |
| 16 | `/ignore` | `main.py:1326` | operator REPL | none | `gate_append` ACT | 14g |
| 17 | Peer design write | `core/agent.py:1695` | dormant (always refused above) | dormant | route through `tool_write_file`-equivalent gate so a future confirm UI cannot reach a raw write | 14g |
| 18 | Session save/clear | `core/sessions.py:71,112` | every turn / `/clear` | none | fork 6 (audit volume): bookkeeping row vs ACT gate | 14i / group 15 |
| 19 | TaskQueue save | `core/taskqueue.py:102` | every planned task | none | same as 18 | 14i / group 15 |
| 20 | Voice config persist | `core/voice.py:56-67` | operator `/voice` setters | none | ACT `gate_exec` (notes.py pattern) | 14i |
| 21 | `--finetune` export | `core/finetune_prep.py:396-403,718,759`; `main.py:2243` | operator CLI | `export_hygiene` fail-closed only | ACT envelope at `prepare_finetune_data` | 14i |
| 22 | KB build/repair/scrape | `tools/kb_semantic.py:350-555`; `tools/kb_scraper.py:114` | none (setup_skills.sh only) | none | no production caller: ledger residual with evidence | group 15 |
| 23 | `pipeline/` export/storage | `pipeline/export/exporter.py`, `pipeline/storage/vector_store.py` | none (operator CLI) | none | ledger residual | group 15 |
| 24 | `install.sh`, `setup.sh`, `setup_repo.sh`, `tools/setup_skills.sh` | repo root / `tools/` | operator; shell tool ACT (NEW-904) | none | ledger residual naming each + fork 3; install.sh cannot import the gateway pre-deps | group 15 |
| 25 | `setup_dr_key.py`, `encrypt_cloudflare_token.py`, `provision_ai_agent_auth.py`, `quarantine_unsourced_ccos_metrics.py` | `core/`, `tools/` | operator; shell tool ACT | none | fork 3: ACT audit row vs HIGH confirm for key/credential minting; default = residual | group 15 |
| 26 | `setup_litestream.py`, `backup_secrets.py`, `backup_documents.py` | `core/` | inside 13d service envelope | covered by 13d row | already covered when run via lifecycle; standalone invocation = fork 3; GCS = NEW-943/944 untouched | covered / group 15 |
| 27 | `bench/runner.py`, `verify.py`, `agents.py`, `promote.py`, `lock.py` | `bench/` | operator measurement CLI only | none | out of scope (measurement); `bench/**` write protection is fork 1 | fork 1 |
| 31 | `coding.lint` / `coding.check_syntax` CCOS capabilities | `ccos/plugins/coding/static_analysis/static_analysis.py:19-21` | only via `call_capability` | unclassified in `CAPABILITY_AUTHORITY` (`plugin_manager.py:~95-165`, 40 names, none of `lint`/`finetune`/`taskqueue`/`recovery`/`git`/`peer`) => refused fail-closed | already covered; keep unclassified (classify only with a real caller) | covered |
| 28 | `ccos` goal/project/reflection/registry JSON writers | `goal_engine.py:571`, `project_engine.py:648`, `reflection_engine.py:220`, `capability_registry.py:210` | none (F3) | none | data-only recording per group-12 table; add explicit row noting `capability_registry.implementation` is an executable pointer | doc row in 14f |
| 29 | Sandbox `install_package` / `run_plugin_test` | `sandbox.py` | none | none | no callers; leave, docstring only | 14f |
| 30 | Foreign embedding (NEW-86) | row 5 | | | | 14d |

## Slice plan (ordered, each independently reviewable)

General rules for every slice: stage exact paths only; set `CODEY_STATE_DIR`,
`HOME`, `CODEY_ACTION_GATEWAY_AUDIT` to disposable temp before any import that
creates schema; guard fixtures *before* the first invocation with the pattern
in `tests/test_foreign_primary_identity.py:13-18` (monkeypatch `os.kill`,
`os.killpg`, `os.getpgid`, `subprocess.Popen`/`run`, `urllib.request.urlopen`,
`socket.socket.connect` to `pytest.fail`), then install the narrow allowed
fakes. Audit labels are static strings (`action` == `command`, e.g.
`filehistory.undo`), never paths, argv, transcripts or exception text.
Denied/declined/EOF/interrupt/callback-failure => zero execution (gateway
already does this for HIGH + `confirm`). No model is loaded by any slice; no
`free -h` cycle is required, but record it anyway for any live step.

### 14a — Recursive protected-root classification (NEW-951)

- Files: `core/checkpoint.py`, new `tests/test_core_file_classification.py`.
  (Callers `tools/file_tools.py`, `tools/patch_tools.py`, `core/recovery.py`,
  `core/filesystem.py` pick the change up; no edits expected there.)
- Change: replace direct-child `Path.match` with "resolved path is under
  `CODE_DIR/<root>` and suffix is `.py`" for the existing four roots
  (recursive). Keep `CORE_PATTERNS` as the checkpoint-backup constant; if/when
  fork 1 widens classification, introduce a separate classification constant so
  widening does not silently change backup scope. Keep the `(TypeError,
  ValueError, OSError) -> ACT` fallback in `classify_write_action`.
- Tests (temp `CODE_DIR` monkeypatched on `core.checkpoint.CODE_DIR`,
  `create_checkpoint` mocked): nested `core/a/b.py`, `tools/x/y.py`,
  `prompts/n/m.py`, `utils/…`; non-`.py` under roots (unchanged ACT);
  symlink in workspace pointing at a core file/dir (resolve => HIGH);
  `..` traversal; NUL byte; relative path with workspace != CODE_DIR;
  `__pycache__`; lookalike root (`corex/…`); confirm daemon
  (`confirm_available=False`) now REFUSES a nested core write and that the
  refusal is audited; checkpoint enforcement (`Filesystem._require_checkpoint`)
  triggers for nested files.
- Live: none (pure classification). Reviewer: standard + adversarial on path
  semantics. Risk to call out: unattended daemon writes to nested core paths
  start refusing (none exist today).
- 14a-ext (blocked on fork 1): adds `ccos/plugins/**` (execution root, F2),
  `bench/**` (promotion-gate integrity, rule 1), and the wider set Ish picks.

### 14b — `/undo` through the filesystem policy (depends on 14a)

- Files: `core/filehistory.py`, `core/filesystem.py` (small new method, e.g.
  `Filesystem.restore(path, content)`: `_validate_path`, git-metadata denial,
  checkpoint for core, no snapshot), `main.py` (the `/undo` call site only,
  lines ~850-865, to pass a confirm adapter), new
  `tests/test_filehistory_gateway.py`.
- Change: `undo()` runs the existing restore under `gate_exec` with
  `authority=classify_write_action(path)`; HIGH_IMPACT uses the same
  default-No TTY adapter style as `main.py:788-807 _voice_confirmation`
  (no `--yolo`, not daemon, not non-interactive, `stdin.isatty()`), ACT
  otherwise; history is mutated only after a confirmed successful write; the
  existing pre-undo snapshot/redo semantics are preserved without calling
  `Filesystem.write` (it would double-snapshot).
- Tests: tmp workspace + tmp `CODE_DIR`; ordinary file restore (ACT, one audit
  row); core file restore refused without confirm / declined / EOF /
  callback-raises (file bytes unchanged, history intact); outside-workspace
  path after simulated `/cwd` rejected; `.git/` target rejected; write
  failure keeps history; static audit labels only.
- Live: none required (real tmp files, no process). Reviewer: standard.

### 14c — Linter execution envelope and cache control

- Files: `core/linter.py`, new `tests/test_linter_gateway.py`;
  `core/agent.py:797` and `main.py` `/review` need no edit unless the
  "skipped tool" message wording is changed (then touch only those strings).
- Change: wrap each tool run in `gate_exec(ACT, action="linter.<tool>")`;
  add `--no-cache` to ruff (verified F8); put a `--` before the path (verify on
  ruff; the implementer must demonstrate it on the real binary) or pass an
  absolute/`./`-prefixed path; refuse to lint a path that does not resolve to an
  existing regular file. **flake8/mypy:** run only if the implementer can
  demonstrate an isolation mechanism from the actual installed artifact (a
  throwaway virtualenv install needs network => ask the coordinator/Ish first);
  otherwise skip them and report "skipped (isolation unverified)". Do not cite
  flag behavior from memory. Keep ruff's workspace config applying unless fork
  3b says otherwise (ruff has a declarative config; code execution there is
  not demonstrated).
- Tests: fixtures forbid real subprocess/network first; fake `shutil.which`
  and `subprocess.run` to capture argv (assert `--no-cache`, `--`, no
  cwd-config flags for others); refusal/failure degrade to the existing
  "linter unavailable -> continue" behavior at `agent.py:797-820` (no raise);
  audit rows static. One optional real-ruff check in tmp dir asserting no
  `.ruff_cache` appears.
- Live: lightweight live-verifier run with the real ruff in a disposable dir
  (cache absent, audit row present). No model.

### 14d — Embedding foreign-port clearing (NEW-86 residual) — lifecycle, rule 4

- Files: `core/embed_server.py`, optional shared bracketing helper (reviewer's
  call whether to factor from `core/loader_v2.py:220-335` into
  `core/process_identity.py`; do not fork a third identity scheme), existing
  `tests/test_new83_embed_server_kill.py`,
  `tests/test_new86_embed_server_pid_recycle.py`,
  `tests/test_embed_owned_lifecycle.py` (update), new
  `tests/test_embed_foreign_port_identity.py`.
- Change: before the first signal require, between matching boot/start/UID
  reads (`process_identity.process_info`), `exe == LLAMA_SERVER_BIN`, argv
  `-m <embed model>` and `--port <self.port>` exact, same UID; then TERM, wait,
  KILL with `_foreign_state` revalidation before each signal; unknown /
  unprovable / legacy / replaced occupant => refuse, log a static diagnostic,
  `_start` returns False (current behavior on "could not clear port"). Authority
  requirement: the caller is automatic and has no human, so HIGH_IMPACT would
  permanently refuse the legitimate stale-own-server case; use ACT **only for
  an occupant that passes the exact embed identity bracket**, with one audit row
  per attempt, and a `refuse_exec` row for anything else. This is a
  deliberate narrowing of the 13f "accounted-but-exempt" note, so the
  coordinator must record it. Release/refresh only the matching slot atomically
  (reuse `rg.release_slot_if_unchanged(confirm_dead=...)`).
- Tests (synthetic `/proc` tree as in `tests/test_foreign_primary_identity.py`):
  wrong exe, wrong model, wrong port, extra `-m`, UID mismatch, zombie,
  recycled PID between reads, vanishing between reads, `/proc/net/tcp`
  unreadable (identity from slot + argv only), non-llama squatter => refused and
  `os.kill` never called; TERM-then-KILL ordering; revalidation between
  signals; audit rows. Ordinary own-spawned python fixtures on a temp port
  (never 8082) for the live part; copying `sys.executable`'s path into
  `LLAMA_SERVER_BIN` lets `exe` match for a fixture child run as
  `python fixture.py -m <tmp model> --port <N>`.
- Live: **required** (lifecycle, rule 4): disposable fixtures only; no real
  llama-server, no model, no existing service; record `free -h`; reap every
  handle.

### 14e — LoRA adopt and rollback mediation — rule 4 + rule 1

- Files: `core/lora_import.py` (adapter + gates), new
  `tests/test_lora_import_action_gateway.py`; existing
  `tests/test_lora_import_gate_and_rollback.py`, `test_lora_import_swap_sync.py`,
  `test_new91_new163_rollback_preserves_finetune.py`,
  `test_new84_stale_model_path.py` must stay green.
- Change: keep the promotion-gate check, adapter validation and registry
  recording exactly as they are (code-reviewer must confirm `bench/gate.py` and
  the `no_evaluator`/`operator_override` semantics are byte-for-byte
  untouched; the scorecard AST checks at `bench/scorecard.py:527-575` must
  still hold). Wrap the mutating span — `create_backup_before_import` through
  swap + `record_adoption_attempt` — in one `gate_exec(HIGH_IMPACT,
  action="lora_import.adopt")`, and `rollback_to_backup` in
  `gate_exec(HIGH_IMPACT, action="lora_import.rollback")` (so
  `rollback_adoption` is covered once, not twice). **`lora_import` owns a
  default `/dev/tty` confirm adapter used by both adopt and rollback** (not an
  adapter supplied only by the `main.py` `--import-lora` call site): the
  documented recovery path is `python3 -c "...rollback_adoption(...)"`
  (`main.py:2288`), which has no caller able to pass a callback, so an
  adapter-only-at-CLI design would make rollback fail closed permanently and
  recovery impossible. The adapter reads and writes **`/dev/tty`** (stdout/
  stderr are captured when the shell tool spawns a CLI, F7); unavailable tty,
  EOF, empty answer, `n` => refuse, nothing copied, merged or swapped. The
  refusal is audited by the gateway, and the registry refusal record
  (`record_adoption_attempt(... adopted=False)`, NEW-811 convention) must be
  made **outside the thunk** by the caller after a `REFUSED` decision —
  inside the thunk a refusal would record nothing. Merge subprocess and loader
  lifecycle stay as in 13e. The `main.py` call site then needs no edit.
- Tests: fake `core.loader_v2.get_loader` installed before import, tiny temp
  "model" files, `subprocess.run` forbidden unless the merge test supplies a
  recording fake, `shutil.copy2` pointed at temp files only; assert zero file
  copies/loader calls on refuse; success path order (backup -> swap -> record);
  `operator_override` still recorded truthfully; rollback unlink only after
  confirmed copy; tty-unavailable path; **the `rollback_adoption` one-liner
  path (no callback supplied) approves via the default tty adapter (fake tty
  device) and refuses with no tty**; refusal record is written even though the
  thunk never ran.
- Live: limited — a pty-based check that the `/dev/tty` prompt is visible and
  answerable while stdout is captured (mirror of shell-tool spawning), with
  fake loader and tiny files; no model, no real adapter. Reviewer: adversarial.

### 14f — Generated-artifact boundaries (recombiner, optimizer, sandbox docs)

- Files: `ccos/core/skill_recombiner.py`, `ccos/core/capability_optimizer.py`,
  `ccos/core/sandbox.py` (docstring correction only),
  `docs/wp2_1_group12_persistence_contract.md` (one table row, if the
  coordinator wants the doc kept in step), tests in `ccos/tests/` and
  `tests/test_promotion_gate.py` / `tests/test_scorecard.py` (re-run, extend
  only if needed), new `ccos/tests/test_generated_artifact_boundaries.py`.
- Change: (a) recombiner generates into a staging dir **outside** every
  `PluginManager` discovery root (e.g. under `ccos/data/staging/compound/`),
  never into `ccos/plugins/compound/`. The staging dir must **also stay
  outside sandbox `ALLOWED_DIRS`** (temp dir, `~/.local/share/ccos`): putting
  it there would silently make the sandbox accept candidate execution, which
  is activation and the rule-1 escalation case, so the sandbox keeps
  rejecting it until a gated activation is deliberately granted; (b) promotion into the discovery root
  and `registry.register` require an approving `bench.gate.GateDecision`
  parameter (default `no_evaluator()`, same as `optimize()`), `may_deploy()`,
  and a HIGH_IMPACT `gate_exec` with a real confirm callback (fail-closed when
  none); shadow mode leaves staging only; (c) `execute_compound_skill` gets a
  HIGH gate with `confirm_available=False` (no caller exists; this is
  hardening, not enablement); (d) `compare_and_upgrade` requires
  `cap.implementation` to be an existing regular file whose resolved path lies
  under an approved deploy root and refuses otherwise *before* any backup or
  copy; deploy copy runs under a HIGH gate; the gate/`may_deploy` branch stays
  textually unchanged; (e) sandbox docstring states it is not a security
  boundary (F5); do not widen `ALLOWED_DIRS`.
- Tests: tmp `plugin_base`/`data_base`, `PluginManager(plugin_dirs=[tmp])`
  discovery test proving shadow output is not discovered and staged output has
  not been `exec_module`d; real-file deploy tests with `implementation` =
  `module:function` and URL strings (refuse, no file created in cwd),
  traversal and symlink targets; gate-approved path with fake confirm;
  existing CCOS suites stay green; sandbox and subprocess forbidden
  throughout. No `get_ccos_memory()` real DB: fixtures must inject tmp-path
  memory/registry (see `ccos/tests/conftest.py` isolation).
- Live: none (dormant); the discovery test uses real tmp files. Reviewer must
  explicitly state the promotion gate is unchanged and that scorecard/
  promotion-gate tests pass for the right reason (rule 1: no relabeling).

### 14g — Behavior-steering project files (pulled in from NEW-939)

State explicitly: the blueprint assigns NEW-939 and export/KB/session
persistence to group 15. This slice **moves only `/init` CODEY.md, `/ignore`
and the dormant peer design write into group 14** because they steer the agent
and match the self-improvement artifact class (model-authored persistent
instructions). Everything else from NEW-939 stays in 14i/group 15.

- Files: `main.py` (`run_init`, `/ignore` branch only), `core/codeymd.py`
  (`write_codeymd`), `core/agent.py` (the 1689-1700 design-write block only),
  new `tests/test_behavior_steering_files_gateway.py`.
- Change: `/ignore` -> `gate_append` ACT. `/init`/`--init` -> same artifact
  class as `preferences.sync_to_codeymd` (see fork 5 for HIGH vs ACT+HIGH on
  overwrite); never display or audit generated content; failure surfaces as
  the existing `[ERROR]` string. Design write -> route through the same gate as
  `tool_write_file` (workspace validation, ACT, protected-name confirm) so a
  future confirm UI cannot make a raw `open(...,"w")` reachable.
- Tests: tmp workspace/cwd, fake `infer`; refusal leaves bytes unchanged;
  `/cwd` change; protected overwrite; audit static labels.
- Live: none. Reviewer: standard.

### 14h — Plugin-tree activation authority (conditional on fork 4)

- Only if Ish chooses an activation allowlist/pin (see fork 4). Files would be
  `ccos/core/plugin_manager.py` (`_discover`/`_load`), a checked-in lock
  mechanism, `tests/test_ccos_capability_authority_coverage.py` neighbors.
  Lifecycle-adjacent (spawns children): rule 4 reviewer + disposable
  verification if it touches `start_external_plugin`. If Ish instead chooses
  "protect the tree by classification only", 14a-ext covers it and 14h is
  dropped (residual: a plugin dropped by a non-gateway path still auto-runs).

### 14i — Low-severity persistence envelopes (recommended: decide, then fold)

- Rows 18-21. Voice-config persist and `--finetune` export are cheap ACT
  `gate_exec` envelopes in the `core/notes.py:26-54` pattern (static
  `command`, re-raise original exception). Session/queue saves run every turn
  or step: either add a group-12-style "fixed-location bookkeeping" table row
  with a regression test pinning directory, filename pattern and redaction (no
  gate), or accept one ACT audit row per save (fork 6). Not blocking 14a-14g;
  safe to execute inside group 15's census if Ish prefers.

## Group-15 residuals (named, not exempt)

KB build/repair/scrape (rows 22), `pipeline/` (23), `install.sh` / `setup.sh` /
`setup_repo.sh` / `tools/setup_skills.sh` (24), operator provisioning scripts
(25) and standalone use of the 13d-covered setup/backup scripts (26),
`bench/*` operator harness (27). Each has "no production caller other than an
operator running it, or only the shell tool (ACT, NEW-904)" evidence above;
none is claimed gated. Group 15's adversarial census should re-grep for new
callers rather than trust this table.

## Product forks for Ish (not decided here)

1. **Which roots count as "Codey itself" for HIGH_IMPACT.** Minimum: recursive
   `core, tools, utils, prompts` `*.py` (14a, no files reclassified today).
   Recommended addition: `ccos/plugins/**` (auto-executed, F2) and `bench/**`
   (the promotion gate's evaluator, rule 1). Maximal: all of `ccos/`, `lib/`,
   launchers (`codey*`, `codeyOS`, `codeydOS`), `main.py`, `install.sh`,
   `restoricon_core/`. Also: extension set (`.py` only today; `tools/setup_skills.sh`
   and `lib/*.sh` are executables). Classification scope must be a separate
   constant from checkpoint backup scope.
2. **`--lora-force-adopt`.** Is the flag itself the human act (then 14e only
   adds a gateway row), or must adoption/rollback also prompt on `/dev/tty`
   (recommended; breaks scripted adoption)? Related evidence: the agent can
   currently invoke this override via the shell tool as ACT (F7).
3. **Script invocations via the shell tool and standalone operator scripts.**
   (a) Elevating `install.sh`, `setup_repo.sh` (`gh repo create --public`),
   `provision_ai_agent_auth.py` (defaults to the live DB) etc. in the shell
   classifier collides with NEW-904's deferred interpreter policy — do it
   there or accept ACT + residual? (b) Linters: if flake8/mypy isolation cannot
   be verified from the artifact, is dropping them from `/review`/auto-lint
   acceptable (they are not installed on this device), or should the
   implementer be allowed a throwaway-venv network install to verify? (c) For
   credential/key-minting operator scripts, audit-row only, HIGH confirm, or
   documented residual?
4. **Plugin-tree activation authority.** Protect the tree by write
   classification only (14a-ext), or also pin/allowlist known plugin manifests
   at `_discover`/`_load` (14h)? This changes how new plugins are added.
5. **`/init` CODEY.md class.** The generated text is shown to nobody before it
   becomes a system-prompt file. Options: HIGH with a "write generated
   CODEY.md?" confirm every time (consistent with `preferences.sync_to_codeymd`),
   or ACT for creation + HIGH only for overwrite using the existing
   "Overwrite? [y/N]" prompt.
6. **Audit volume for per-turn session/queue saves** (one ledger row per turn
   vs a bookkeeping disposition row).
7. **Embed foreign kill (only if bracketing cannot be met on-device).** The
   recommendation is exact-identity-or-refuse; after an upgrade, a legacy
   stale embed server with no recorded identity would require manual port
   cleanup. If Ish prefers diagnostic-only (13c.2 orphan precedent) say so;
   otherwise proceed.

NEW-959 (relative daemon path) and GCS NEW-943/944 are untouched by this plan.

## Findings to log (provisional labels; coordinator allocates IDs)

- G14-F1 (Confirmed mechanism; severity **Medium, High only if the daemon (or a
  `--yolo`/`--fix` run) is started from inside the repo — unverified**): the
  nested-core miss is wider than NEW-951 — the auto-executed `ccos/plugins`
  tree, `bench/**`, launchers, `lib/` and `main.py` are ACT-writable by the
  model when the workspace contains the repo, and `allow_self_modification` is
  moot then. Interactive default mode prompts per write. Not a new execution
  capability (NEW-904 already permits `python3 -c` as ACT); the new element is
  delayed execution at the next process's first REPL prompt, outside the
  originating confirmation, plus an editable `bench/` evaluator (rule 1).
- G14-F2 (Confirmed, Medium, dormant-armed): recombiner writes generated
  plugins into the discovery root before any gate; registration lacks a
  `GateDecision` (rule 1 gap).
- G14-F3 (Confirmed reachability, Medium; unconfirmed only under `--yolo`,
  `--fix`, daemon tasks): `--import-lora ... --lora-force-adopt` and
  `rollback_adoption` are reachable from the agent's shell tool classified ACT;
  default interactive mode shows a shell prompt.
- G14-F4 (Confirmed, Medium): `/undo` bypasses classification, checkpoint and
  path validation (`filehistory.py:65`).
- G14-F5 (Confirmed, Low): ruff writes `.ruff_cache` into the project on every
  auto-lint (verified); flake8/mypy config-code-execution Suspected, tools not
  installed, unverified.
- G14-F6 (Confirmed, Low, dormant): optimizer `compare_and_upgrade` has no
  deploy-target containment; live registry has no path-like `implementation`
  so `optimize()` is inert; sandbox rejects its own cwds (broken-safe).
- G14-F7 (Confirmed, informational): `ccos/core/sandbox.py` is shell=True with
  ambient env and a fail-open string filter — docstring over-promises.
- G14-F8 (Confirmed, Low): `/init` writes unreviewed LLM text into CODEY.md at
  a lower class than the automated CODEY.md writer.
- Note, not a group-14 item: 254 uuid-hex directories (counted with Python,
  32-hex names) at the repo root
  (`resource_bus.db`/`.lock`, gitignored by `.gitignore:58`) look like test
  leakage; unrelated to this group, mention in the ledger only if not already
  tracked.

## Ordering and review/verification summary

| Slice | Depends on | Review | Live |
|---|---|---|---|
| 14a | none | standard + adversarial path semantics | none |
| 14b | 14a | standard | none (real tmp files) |
| 14c | none | standard | light (real ruff, tmp dir) |
| 14d | none | rule 4 adversarial | required, disposable fixtures |
| 14e | none (fork 2 answer) | rule 4 adversarial + rule 1 check | pty confirm check, fake loader |
| 14f | 14a-ext if fork 1 includes `ccos/plugins` | adversarial; promotion gate untouched | none |
| 14g | fork 5 | standard | none |
| 14h | fork 4 | rule 4 if it touches spawn | disposable |
| 14i | fork 6 | standard | none |

Suggested execution order: fork-free slices first — 14a, 14b, 14c, 14d — so
work proceeds while forks 2 and 5 are pending; then 14e (fork 2) and 14g
(fork 5), then 14f (+14a-ext once fork 1 is answered), then 14h/14i as
decided, then group 15's census.

## Execution status (appended 2026-10-17 by the coordinator's architect; the text above is unchanged architect scope)

Provisional labels were allocated as: G14-F1 -> NEW-975, F2 -> NEW-976, F3 -> NEW-977, F4 -> NEW-978, F5 -> NEW-979, F6 -> NEW-980, F7 -> NEW-981, F8 -> NEW-982; slice residuals NEW-983 (14d), NEW-984 (14c), NEW-985 (pre-existing static_analysis test ImportError), NEW-986 (14a/14b). Repo-root hex directories were already tracked (NEW-277, NEW-451).

| Slice | State (2026-10-17) |
|---|---|
| 14a | Executed (NEW-951 partial: recursion inside the four existing roots only). Code complete, reviewer APPROVED, uncommitted. |
| 14b | Executed (NEW-978). Code complete, reviewer APPROVED round 3, uncommitted. Not live-verified. |
| 14c | Executed (NEW-979 ruff part). Code complete, reviewer APPROVED, uncommitted. flake8/mypy not executed. |
| 14d | Executed (NEW-86 rewrite). Code complete, reviewer APPROVED, live-verified on disposable stubs; uncommitted. Departs from this spec: no gate_exec/audit/refuse_exec row (NEW-983). |
| 14a-ext, 14e, 14f, 14g, 14h, 14i | Not started; blocked on Ish forks 1, 2, 5, 4, 6 respectively (14f also depends on fork 1). |

Group 14 remains OPEN.

## Execution status 2 (appended 2026-10-17 after Ish answered the forks; the text above is unchanged architect scope)

Ish's instruction: "for all your questions go with what you recommend". Decisions recorded: **fork 1** "Codey itself" for HIGH classification = `core, tools, utils, prompts` + `ccos/plugins/**` + `bench/**` (recursive `*.py`). **Fork 2** LoRA adopt AND rollback require a real per-attempt `/dev/tty` confirmation; `--lora-force-adopt` is NOT itself the human act. **Fork 3** plugin tree protected by write classification only, no activation allowlist: **14h is dropped as not-to-do** unless Ish reopens. **Forks 4/5** `/init` CODEY.md write is HIGH_IMPACT always with real confirmation. **Fork 3b** flake8/mypy stay disabled in `/review` (re-enable only if isolation is verified from an installed artifact). **Fork 7** embed foreign kill = exact-identity-or-refuse (already implemented in 14d). **Still open:** fork 6 (audit volume for per-turn session/queue saves; belongs to 14i), NEW-959, GCS NEW-943/944 (untouched).

| Slice | State (2026-10-17, later) |
|---|---|
| 14a, 14b, 14c, 14d | Committed as `249b61b` (see "Execution status" above, whose "uncommitted" wording is superseded). |
| 14a-ext (NEW-975) | Executed. `CORE_CLASSIFICATION_ROOTS` = `core, tools, utils, prompts, ccos/plugins, bench`; exactly 89 existing files ACT->HIGH (53 plugins, 36 bench), pinned by an independently derived set test; 66 passed new/changed, 156 related. Code complete, reviewer APPROVED, **committed as `96ad7f4`**, not live-verified. Backup scope (`CORE_PATTERNS`) unchanged on purpose; `--allow-self-mod` still a confirmation channel for HIGH writes; launchers, `lib/`, `main.py`, `.codeyignore` remain ACT. |
| 14e (NEW-977) | Executed (rule 4 + rule 1). `core/lora_import.py` real-`/dev/tty` gate with typeahead flush, rollback gated once, adopt span gated after gate/validation; `bench/gate.py` untouched. 36 new tests (`tests/test_lora_action_boundaries.py`; the spec named `test_lora_import_action_gateway.py`), reviewer APPROVED rounds 1 and 2, 78 passed with gateway suites, 5 clean consecutive runs. Not live-verified (real `/dev/tty` and device not tested). 4 pre-existing HEAD failures: NEW-987. **Pending commit.** |
| 14f (NEW-976/980/981) | Executed (rule 1). Recombiner staging outside discovery roots + approving `GateDecision` + HIGH confirm; `execute_compound_skill` always refused; optimizer containment + confirm-gated deploy (dormant); sandbox docstring only. 16 new tests; reviewer APPROVED; `ccos/tests` 177 passed (+ pre-existing `test_plugin_manager` failure identical at HEAD). Departs from spec: the "sandbox rejects its own cwds" premise was verified false, so no sandbox change. Deploy branch is unreachable in production by design (staging outside `ALLOWED_DIRS`). Not live-verified; **committed as `96ad7f4`**. |
| 14g (NEW-982 + NEW-939) | Executed. `/init` infer+write in one HIGH gate with real confirm; `write_codeymd` via `Filesystem.write`; `/ignore` via `gate_append` ACT; dormant peer-design write via `tool_write_file`. 21 new tests; 2346 passed across 60 related files; reviewer APPROVED. **Behavior change:** `/init`/`--init` now refuse under `--yolo`/daemon/noninteractive/non-tty (NEW-991). Not live-verified; **committed as `96ad7f4`**. |
| 14h | **Dropped** (fork 3: no activation allowlist). Reopen only on Ish's say-so. |
| 14i | **Not started** (voice config, `--finetune` export, per-turn session and queue saves; needs fork 6). |

New findings from this stretch: NEW-987 (pre-existing failing lora tests), NEW-988 (finetune plugin `test.py`/manifest drift), NEW-989 (optimizer `new_path` containment + post-copy bookkeeping), NEW-990 (14e/14f residuals), NEW-991 (`--init` behavior change, docs not updated). Updates to NEW-975/976/977/980/981/982/984 are in `NEW_ISSUES.md`.

**Group 14 remains OPEN** (14i not started; 14a-ext/14e/14f/14g uncommitted and not live-verified). Group 13 remains OPEN (NEW-972; NEW-971 not live-verified). Group 15 not started. WP2.1 not closed.

## Execution status 3 (appended 2026-10-18 after slice 14i; the text above is unchanged architect scope)

Ish's instruction (2026-10-18): "carry on as you recommend", which answers fork 6 (audit volume for per-turn session/queue saves): coalesce rows, first/changed outcome only.

| Slice | State (2026-10-18) |
|---|---|
| 14a-ext, 14e, 14f, 14g | Committed as `96ad7f4` (the "Pending commit" wording for 14e in "Execution status 2" is superseded). |
| 14h | Dropped (fork 3), unchanged. |
| 14i (NEW-939 low-severity writers + fork 6) | Executed. New `core/bookkeeping_persist.py` (`persist_coalesced`); `core/sessions.py` `save_session` (coalesced) and `clear_session` (one row per call, `_session_path(create=False)`, `mkdir` inside the mediated write); `core/taskqueue.py` `TaskQueue.save` (coalesced); `core/voice.py` `_save_config` (one row per call, failure still swallowed); `core/finetune_prep.py` `prepare_finetune_data` wrapped in one ACT envelope (old body `_prepare_finetune_data`, refusal returns `{"error": ...}`); `core/action_gateway.py` `gate_exec(..., coalesce_key=None)` + `ActionGateway._audit_exec` with a per-instance `OrderedDict` LRU (`COALESCE_MAX_KEYS=1024`) of `sha256(len(action):action NUL key)` -> last outcome, lock-protected, ACT only, rows skipped only for allowed-after-allowed / failed-after-failed, first row / changes / every refusal always written, keys never logged, default byte-identical to HEAD. Tests: `tests/test_low_severity_persistence_gateway.py`, `tests/test_action_gateway_coalesce.py`; 154 passed in the final gateway-group run; wider chunks 362, 150, 180, 90 passed. Code complete, reviewer APPROVED after 3 rounds (round 1 CHANGES REQUESTED: gate-once-per-target design did not re-consult policy and had unbounded failure volume; round 2 APPROVED with W1 key-not-ACT-restricted and W2 NUL-separator ambiguity; both fixed, round 3 APPROVED). **Pending commit; not live-verified.** |

Honest limits: finetune plugin (`ccos/plugins/coding/finetune` `export_dataset`, `generate_notebook`, `_write_jsonl`; `core/finetune_prep.py` ~718/~759) NOT enveloped (NEW-992), so finetune is not claimed covered; repeat saves not individually audited, coalesce state per process and not persisted, audit state advances even when the best-effort audit write fails, ACT has no refusal policy (audit plus future-policy hook, not enforcement), `clear_session`/`TaskQueue.save` raise `RuntimeError` on a future refusal, non-`str` action with a key would raise in `len()`; spec line drift (`main.py --finetune` ~2351, `sessions.py` ~76/134, `taskqueue.py` ~106); no live run, real REPL session-ledger flow untested (NEW-993). One test (`test_refusal_always_written_and_resets_state`) has a cosmetic stale name and expects 4 rows. 1 pre-existing HEAD-identical failing test (NEW-987). Process incident: the implementer ran `git stash -q` then `git stash pop` once; nothing lost, verified by hashes (NEW-994).

**Group 14 status:** slices executed 14a, 14b, 14c, 14d, 14a-ext, 14e, 14f, 14g, 14i; execution is complete as scoped, but the group is NOT closed. Remaining: 14i commit; live verification (only 14d has it); NEW-975 residual (launchers, `lib/`, `main.py`, `.codeyignore` not in roots); NEW-904/905/913/914 deferred; NEW-959 unanswered; fork 3b (flake8/mypy remain disabled); the finetune bypass (NEW-992); residuals NEW-983..NEW-993. Group 13 remains OPEN (NEW-972 unscoped; NEW-971 not live-verified). Group 15 (final census / adversarial verification) NOT started. WP2.1 NOT closed.
