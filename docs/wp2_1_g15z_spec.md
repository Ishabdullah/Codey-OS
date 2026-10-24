# WP2.1 slice G15z "closure" — technical plan/spec

Status: DRAFT (architect, 2026-10-24), written incrementally. Plan only; no source/test/ledger edits.
Base: HEAD 50f9aa2 + uncommitted G15i/G15j work in flight (not touched, not in scope here).

Sections: 1 census re-run and UNKNOWN classification; 2 verify-only hunters; 3 evidence tiers and outstanding live verification; 4 docs closeout, DoD statement, handoff; 5 staged plan, cost, risks; 6 decisions needed from Ish; 7 facts relied on. Every fact was read from an artifact (rule 12); estimates are labelled as such.

## 1. Census re-run procedure and UNKNOWN classification

### 1.0 What was run for this spec (read-only; rule 12)

`python3 -I tools/wp21_census.py --help` printed the real CLI: `--repo --rev --source {head,worktree} --out --register --seed --check --strict`
(no `--gate` flag; the gate is a pytest env var, 1.5). Two read-only runs were made, both with `--out` under the architect's scratchpad, `HOME` set to a
scratch dir, proxies unset, `docs/wp21_census/dispositions.tsv` md5 `537a75a8...` before and after (unchanged), `git status` unchanged:

* `--repo . --register docs/wp21_census/dispositions.tsv --check --seed --out <scratch>/census_head` (default `--source head` = `git archive` of
  `50f9aa28...`, so uncommitted G15i/G15j work is invisible). Result: **scan_rows 1,466** (952 py, 159 shell, 355 manifest), register entries 1,337,
  **unknown_rows 1,437**, failures 29, warnings 0, rc 1. `by_class` = UNKNOWN 1,437, NO_DISPOSITION 23, READ_NOEFFECT 5, GATED 1. The seed file has 1,360
  entries (1,337 existing + 23 new keys; the 6 stale keys are kept by `merge_seed`, which never deletes). The 29 failures: 23 `unregistered-row`
  (bench/runner.py 7, bench/verify.py 7, core/protected_paths.py 6, ccos/core/plugin_manager.py 1, core/process_identity.py 1,
  ccos/plugins/system/system_info/system_info.py 1) and 6 `stale-row` (bench/runner.py 4, bench/verify.py 1, ccos/core/plugin_manager.py 1). Reading the key lists
  (`FAIL` lines, verbatim in the scratch `stdout.txt`): all 6 stale keys have a same-callee successor under a new qualname (`bench/runner.py::run_suite::{*.mkdir,open,shutil.copytree,tempfile.TemporaryDirectory}::1`
  -> `_run_snapshotted::...`; `bench/verify.py::grade::subprocess.run::1` -> `_run_hardened::subprocess.run::1`; `ProcessSupervisor.start_external_plugin::subprocess.Popen::1` -> `...start_external_plugin.<locals>._spawn::subprocess.Popen::1`),
  so these 6 are **moves** caused by G15f-B/G15g-B refactors (positional/qualname keys, S1 in the tool docstring). The other 17 unregistered keys are **net-new boundary rows**
  (`bench/runner.py` `_snapshot` copytree, `run_suite` rmtree and `mkdtemp`; `bench/verify.py` `_expected_tests` copytree x2 and `TemporaryDirectory`, `_run_hardened` mkdir x2 and `write_text`;
  `core/protected_paths.py` six `const:` credential-path-name rows; one `sys.path.insert` in `core/process_identity.py` and one `sys.path.append` in
  `ccos/plugins/system/system_info/system_info.py`). Whether those 17 are benign is **not yet adjudicated**: the six `protected_paths.py` constants (`.env .gnupg .netrc .ssh credentials gcloud`) look like a
  deny-list naming credential path parts (FALSE_POSITIVE candidates, to be confirmed by reading the file), the bench rows are snapshot/grade temp-dir writes introduced by G15f.
* The same with `--source worktree` (informational only): 2,163 scan rows and 725 failures, because worktree mode also scans **untracked** files:
  `.live_verify_scratch/*.py` (about 40 rows) and the gitignored, locally present `ccos/data/capabilities.json` (644 rows). **Closure must use the default
  `--source head` on a clean, committed HEAD**, never `worktree`; the tool's dirty-path downgrade (failures to warnings) is applied only in worktree mode.

Count note: the handoff's "1,433 rows / 1,427 UNKNOWN" was at `941ec3f`; the tool itself (16 rows) was uncommitted then. At `50f9aa2`: 1,466 rows.

### 1.1 Preconditions (the census is only meaningful on a frozen tree)

1. Every code slice that is to be in WP2.1 is committed (G15i, G15j if Ish keeps them, plus any D-5/D-8-driven fix). The worktree currently carries
   uncommitted G15i/G15j changes (`core/tty_confirm.py` new; `core/action_gateway.py`, `core/lora_import.py`, `core/setup_dr_key.py`, `tools/file_tools.py`,
   `tools/patch_tools.py`, `tools/provision_ai_agent_auth.py`, `utils/logger.py` modified): they will add/shift rows (the worktree run already shows
   `core/tty_confirm.py` and `core/setup_dr_key.py` rows). **Classify AFTER the last code commit.** Any later edit that adds, removes or reorders a boundary
   call in a file invalidates that file's row keys (positional ordinals) and its dispositions must be re-checked by hand.
2. Disposable env for the run (the tool is parse-only and never imports Codey modules, but follow the project convention anyway):
   `env -u HTTP_PROXY -u HTTPS_PROXY HOME=<abs tmp>/home CODEY_STATE_DIR=<abs tmp>/state CODEY_ACTION_GATEWAY_AUDIT=<abs tmp>/state/audit.jsonl python3 -I tools/wp21_census.py --repo . --rev HEAD --out <abs tmp>/census --register docs/wp21_census/dispositions.tsv --check --seed`.
   `--out` must be outside the repo (the tool writes only below `--out`; verified: the register md5 did not change).

### 1.2 Step list (G15z-A, the mechanical half)

* A1 run the command above at the closing HEAD; expect `--check` to FAIL on drift (unregistered new keys, stale old keys). That is the expected first result,
  not a defect.
* A2 the coordinator (not an agent) copies the `dispositions.seed.tsv` rows for new keys into the register, **and deletes the stale keys by hand** (`merge_seed`
  never deletes; a stale key is a hard `FAIL stale-row`). Rows whose key is "stale + new" in the same file are a rename/reorder: carry the old decision across only
  after a human reads the diff (S1).
* A3 write the new `docs/wp21_census/<head8>/` outputs (scan/shell_scan/manifest_scan/env_names/cli_flags/run_meta/summary) and commit them with the register
  update; run the census twice and `cmp` the two `scan.tsv` (reproducibility claim in the scope doc 4: "independent re-run reproduces `scan.tsv`").

### 1.3 UNKNOWN is not safe; classification inventory at `50f9aa2`

UNKNOWN means "nobody classified", never "no bypass" (NEW-1009). At `50f9aa2` 1,437 scan rows resolve to UNKNOWN. Of the register, 1,331 entries are UNKNOWN
(`decided_by census-tool:initial`), only 6 are decided (5 READ_NOEFFECT `os.kill(pid, 0)` liveness probes, 1 GATED helper-of/lexical row). **No classification pass
has ever been run**: the scope doc 5 listed it as G15a sub-steps a2-a4 (6-7 classifier agents plus a sampler, 1.5-2.0M tokens), G15a shipped only the tool (a1), and the
consolidated register 8 prices G15z at 3.0-4.0M **without** a line for it. That is a budgeting gap this spec closes (section 5).

Inventory, with the realistic method per family (counts are rows from the HEAD scan; a "unit" is one agent run):

| family | rows | register granularity | method | reviewable by |
| --- | --- | --- | --- | --- |
| `ccos/plugins/**/manifest.json` (19 files) | 355 = 165 `implementation`, 165 `capability` (**40 authority_listed=True, 125 False**), 19 `entry_point`, 4 `permissions`, 2 `resource_limits` | exact keys | **mechanical-first**: (a) `authority_listed=True` (40 capabilities, only a name-membership test in the scan; the tool docstring says the class VALUE and manifest raise-tags are not checked) -> `NATIVE_AUTHORITY` citing `CAPABILITY_AUTHORITY` and `tests/test_ccos_capability_authority_coverage.py`, **with the class value (READ/ACT/HIGH_IMPACT) written into `evidence`**; authority is keyed by capability name, so a listed READ capability whose implementation has side effects is exactly C:M25/G15b-43, therefore a reviewer checks **100% of READ-classified listed capabilities** (`CAPABILITY_AUTHORITY` at `50f9aa2` has 40 names: 35 READ, 5 ACT, counted with `ast`, so 35 capabilities and their implementation rows) against what the implementation does; (b) `False` (125) -> mediated by the same native mechanism, which refuses unlisted names fail-closed (hunter C negative result C:M28): `NATIVE_AUTHORITY` with C:M28 and the dispatch test as evidence, **not** FALSE_POSITIVE (FALSE_POSITIVE is for `str.replace`-type non-boundaries; these are real side-effecting boundaries behind a refusing gate); (c) the 19 `entry_point` rows -> one cited disposition per file referencing the G15g containment/audited-spawn evidence (`NEW-1052`/`NEW-1053`); (d) the 6 permissions/resource_limits rows -> `UNMEDIATED`, QUEUE, finding G15b-43/NEW-1034 (limits are metadata). One script plus one adjudicating agent | 100% of READ-listed capabilities, sample 25% of the rest |
| `restoricon_core/**` py (304 rows, **192 qualname-level register entries**, only `NATIVE_AUTHORITY`/`BOOKKEEPING`/`UNKNOWN` allowed) | 304 | qualname | **table-driven**: join each qualname to `BUSINESS_MUTATION_AUTHORITY` (`restoricon_core/authority.py:69`) and the existing `tests/test_business_mutation_authority_coverage.py`; unmatched ones are BOOKKEEPING (cite group-12 persistence contract row). UNKNOWN cannot remain at closure and `QUALNAME_LEVEL_CLASSES` forbids UNMEDIATED at qualname level, so a qualname that is neither: **split it into exact `file::qualname::callee::ordinal` entries** (exact keys are matched first by `evaluate_coverage`), each `UNMEDIATED` with finding+severity+reach. Track B friction (NEW-1016): classification only, no Track B code; note `gate_restoricon` is a parameter of `evaluate_coverage` only, NOT wired to the CLI or the pytest gate, so using it means a test edit (Z-1) | sample 25% + 100% of any not matched by the table |
| shell/launcher text (13 files: `install.sh` 82, `lib/service_lifecycle.sh` 28, `tools/setup_skills.sh` 13, `lib/service_manager.sh` 9, `setup.sh` 9, `setup_repo.sh` 7, `codey` 3, workflow 2, `codey-start` 2, 1 each `codey-metrics`, `codey-stop`, `codeyOS`, `codeydOS`) | 159 | exact | `OPERATOR_BOOTSTRAP` / `OPERATOR_SCRIPT_RUNNABLE` per file (one disposition paragraph per file naming the operator act and whether the shell tool can invoke it), plus the regex false positives (comments/heredocs) as `FALSE_POSITIVE` | 100% of `UNMEDIATED`, sample of the rest |
| `core/**` py (331 rows) | 331 | exact | by sub-family: lifecycle/inference/resource (loader_v2, daemon, resource_gate/bus, process_identity, embed_server, service_lifecycle ...), state/memory/tools, persistence/CLI/peers/network. Kill rows cite their identity validator (DoD 8); network rows cite loopback evidence (`LOOPBACK_IPC`) or the remote-backend finding C:N01 | see 1.4 |
| `ccos/core/**` + `ccos/plugins/**` py + demos (about 175 rows) | ~175 | exact | `OPERATOR_SCRIPT_RUNNABLE` for demos and plugin `test.py`; `ccos/core/*` by the CCOS authority table; `dyn_code` rows individually | see 1.4 |
| `tools/` 42, `utils/` 11, `pipeline/` 25, `telemetry/` 29, `bench/` 23, `main.py` 6 | 136 | exact | one agent; `tools/` = operator scripts; `bench/` rows individually (G15f closure evidence) | see 1.4 |

Totals: py non-restoricon 648 rows in 125 files (597 distinct `(file, qualname)` groups across all non-restoricon kinds), distribution of rows per file: 34 files with 1 row,
29 with 2, 39 files with 10 or more. Rows in one function usually share a decision, so the agent classifies **per `(file, qualname)` group** and the TSV writer expands to
the ordinal keys.

### 1.4 Classification procedure (structured, reviewable)

* Seven classifier units, each owning a disjoint set of files (so there is no write collision) and writing its **own** `docs/wp21_census/classify_<unit>.tsv` in
  register column order to the scratch dir incrementally after every file (usage limits kill agents; a re-launch resumes from the last written file):
  C1 manifests (script + adjudication), C2 restoricon_core (table join), C3 shell/launchers/workflow, C4 `core` lifecycle/inference/resource,
  C5 `core` state/memory/tools/persistence/network/peers, C6 `ccos/**`, C7 `tools utils pipeline telemetry bench main.py`.
* **Rows per unit at `50f9aa2` (they sum to the 1,466 scan rows):** C1 manifests 355 (mechanical, 19 files); C2 `restoricon_core` 304 rows / 192 qualname entries (table join); C3 shell/launchers/workflow 159 rows / 13 files; C4 + C5 split of `core/**` 331 rows
  (C4 about 170 lifecycle/inference/resource, C5 about 160 state/memory/persistence/network/peers; the split is by file and is decided by the coordinator from `scan.tsv` so that no file is in both); C6 `ccos/**` py 181 rows (`ccos/core` 95, `ccos/plugins` 80, six `ccos/demo_*.py`);
  C7 `tools` 42 + `telemetry` 29 + `pipeline` 25 + `bench` 23 + `utils` 11 + `main.py` 6 = 136. The judgment units C4-C7 cover 648 rows in **373 `(file, qualname)` groups across 125 files** (`core` 331 rows / 192 groups / 51 files, `ccos` 181 / 109 / 43, `tools` 42 / 22 / 11, `telemetry` 29 / 11 / 4, `pipeline` 25 / 17 / 6, `bench` 23 / 11 / 6, `utils` 11 / 7 / 3; counted from the HEAD `scan.tsv`); cost is dominated by reading each file and its callers (about 125 files at roughly 10K tokens, times 2 for callers, tests and gate checks), so C4-C7 are budgeted at 1.8-3.2M, and C1-C3 (mechanical: a script plus an adjudicator) at 1.1-1.7M, which is how the 2.9-4.9M of S4 below is built. **Measure C7 first and rescale.**
* Each row needs: class from the 12-value taxonomy; `mediator` where GATED/NATIVE_AUTHORITY (gate vocabulary only: the check rejects anything else); `evidence`
  non-empty (the check fails `missing-evidence` otherwise) as `file:function` plus the named test, or the reverse-call-graph result for DORMANT; `reach` from the
  fixed vocabulary; for `UNMEDIATED`: `finding` (a `NEW-###`; existing G15b ids where the row IS that finding) and `severity` per the **ratified** rubric. A row
  that matches an already-ledgered finding cites it rather than minting a new id; genuinely new HIGH-class findings stop the closure (1.6).
* The classifier reads the function and its callers; it does **not** run anything (parse-only, no import, no model). It may not set `reviewed_by`.
* Independent review (rule: the author does not review itself): a different agent (R1..R3) re-classifies from scratch **25% random rows of each unit, 100% of
  `UNMEDIATED`, 100% of `GATED`/`NATIVE_AUTHORITY` rows resting on a helper rule, and 100% of kill rows** and writes `reviewed_by` plus a disagreement list; each
  disagreement is resolved by the architect/coordinator, and the reviewer's sample disagreement rate is reported verbatim (if it exceeds about 15% for a unit, the whole
  unit is redone by a fresh classifier rather than patched).
* The coordinator merges, runs `--check --strict`, then the full `tests/test_wp21_census.py` (1.5).

### 1.5 Flipping the gate

The two existing switches are **test-level env vars, not CLI flags** (`tests/test_wp21_census.py:707-746`):

* `WP21_CENSUS_GATE=1` makes `test_repo_head_snapshot_is_covered_by_register` assert `cov.ok` (unregistered rows, stale rows, bad class/reach/severity, missing
  evidence, UNMEDIATED without finding+severity, GATED mediator outside the gate vocabulary all fail). Default (unset) is warn-only (a `UserWarning` in the pytest
  warning summary). `WP21_CENSUS_SKIP_REPO=1` skips both repo-level tests.
* `WP21_CENSUS_STRICT=1` enables `test_repo_head_snapshot_has_no_unknown_rows` (`require_no_unknown=True`: any UNKNOWN row is a `unknown-remains` failure); otherwise it is
  skipped. It is the DoD 3 check.

"Flipping" has two parts that need Ish's call (decision Z-1): (a) **make the checks run blocking by default** by deleting the `os.environ.get(...)` conditions in
`tests/test_wp21_census.py` (a test edit, reviewer-approved, with a demonstration that adding a boundary without a disposition fails, DoD 3) and (b) CI:
`.github/workflows/tests.yml` can set `WP21_CENSUS_GATE=1` instead. Recommended: do (a) for the gate test only after classification completes, leave STRICT as a
**closure-time** check (run once with the env var, record the output verbatim) rather than a permanent per-commit check, because strict makes every future
boundary addition an immediate suite failure that must carry a classified disposition. Test impact to state to Ish: (i) the default suite gains a ~4 s snapshot scan
(already present, warn-only today); (ii) from then on **any commit that adds, removes or reorders a boundary call fails the suite until the register is updated in the
same commit**, which is why the Track B friction (NEW-1016; `gate_restoricon=False` exists in `evaluate_coverage` to soften `restoricon_core` qualname rows) is a
standing decision; (iii) the test scans the **committed HEAD** snapshot, so a developer's own uncommitted new row is invisible locally and fails only after the commit
(documented in `docs/wp2_1_census_report_1.md`), so the register update must ride in the same commit or the following docs-only commit will turn the suite red.

### 1.6 Stop conditions inside classification

A classifier that finds an `UNMEDIATED` HIGH row not already ledgered (a new confirm-less irreversible boundary) halts that unit and returns it to the coordinator;
it is **not** silently registered and is **not** fixed in G15z (rule 8: log; Ish decides fix vs accept, DoD 4).

## 2. Three verify-only adversarial hunters (G15z-V)

### 2.0 Definition of "verify-only" and the ground rules

* **Independent**: each verifier is a new agent that did not write or review the code under test (every implementer and reviewer of G15c..G15j is excluded for the unit
  they touched) and also did not act as a G15b hunter for the same family (a fresh eye is the point; the G15b scripts are inputs, not authority).
* **Verify-only = two activities, nothing else, and no fix**: (V) re-run **each fixed finding's original repro** against the closing HEAD and record PASS/FAIL, and (N)
  bounded new probing (cap **40 new probes per unit**, plus **10 random previously-clean (`OK`) rows re-run per hunter** with the random seed written in the TSV; this is
  the scope doc 5 "fixed High items plus 10 random previously-clean rows" rule). A verifier never edits source, tests, ledgers or `docs/` other than its own two output files.
* **Subject**: `git archive <closing HEAD>` extracted to a scratch dir (never the working tree: the tree may carry foreign dirty files; the G15b hunters' A:`F-*` rows
  and Hunter A's own note show a mid-run tree change corrupts a baseline). The HEAD hash and `git status --short` go in the first lines of each report.
* **Verdict vocabulary**: `PASS` (the original repro no longer reaches the dangerous effect: refused / prompted / denied / inert), `FAIL` (still reaches it: the finding is
  **reopened**, severity per the ratified rubric), `ACCEPTED-RESIDUAL-UNCHANGED` (G15b-19/22/36 and the other register residuals: expected to still reproduce; recorded to show the
  ceiling statement is accurate, **not** counted as FAIL), `NOT-RERUNNABLE` (no retained repro; the reason is stated), `INCONCLUSIVE`, `NEW` (a new finding from activity N).
  Every PASS needs a **control** that shows the probe could have succeeded (the raw unmediated call, or the same input on the pre-fix snapshot `941ec3f`/`e167e0c`), per
  scope doc 4. No sentence of the form "no bypass exists", only "N probes tried, M reproduced".
* **Disposable environment** (handoff 5): absolute scratch `HOME`, `CODEY_STATE_DIR`, `CODEY_ACTION_GATEWAY_AUDIT`, `CODEY_CONFIG_PATH`, `RESTORICON_DB_PATH`, proxy vars
  unset, `python3 -I` with `sys.path` = the snapshot, **recording fakes installed before any import** for `subprocess.*`, `os.system/kill/killpg/exec*/spawn*/fork/popen`,
  `socket.connect/create_connection`; the pre-flight asserts each env path resolves under the scratch root and aborts otherwise. Fabricated tokens/keys only. No model load
  (`free -h` recorded for habit), no real grader/bench run, no network, no real services, no `~/.codeyOS`, no live Restoricon DB, no `pkill -f`, no `git stash/reset/checkout/clean/add -A`.
* **Mandatory pre-flight, abort if any step fails (the G15b harnesses were written against `941ec3f`; since then G15g-B moved the plugin spawn into a `_spawn` closure and G15h-A added `OwnedLaunch(env_provider=...)`, so a recorder that intercepted every spawn at `941ec3f` may miss a path now, and a missed interception means a probe could REALLY run, not merely a false PASS):**
  (1) from the snapshot's census `scan.tsv`, list every `exec_spawn`, `kill` and `network` row and confirm each primitive it uses (`subprocess.run/Popen/call/check_*`, `os.system/popen/kill/killpg/exec*/spawn*/fork`, `socket.*`) is patched **before** any snapshot module is imported, and that no module does a module-level `from subprocess import ...` / `from os import kill` that binds the original at import time (grep the snapshot for such binds; patch in the importing module's namespace too);
  (2) fire one harmless **canary** probe through each harness mode (shell, daemon, file tool, plugin load) whose real execution would create a scratch file (for example `touch <scratch>/CANARY`), and confirm the recorder captured it and the file does not exist;
  (3) assert every path the harness will write to or run in resolves under the scratch root and that none of the re-pointed constants of 2.1 still names the repo.
* **Output**: for hunter X, `docs/wp2_1_g15z_verify_X.tsv` and `docs/wp2_1_g15z_verify_X.md` (new files, committed verbatim including failed and incomplete runs, DoD 7),
  TSV columns = the G15b columns plus: `probe_id, finding (G15b-NN), original_probe, repro_source (path+sha256), head, input, observed (verbatim), control, verdict,
  severity (FAIL/NEW only), evidence`. The md carries: method, env, HEAD, a per-finding table (finding -> PASS/FAIL/RESIDUAL counts), the FAIL list, the NEW list, the
  explicit coverage statement, and an `INCOMPLETE` section if a unit was halted. Each verifier appends one TSV row + one raw JSON line **after every probe** (usage limits
  kill agents; a re-launch resumes after the last row) and writes the md skeleton first.
* **Lessons from G15b (hunter B halted by a safety classifier; C's final turn cut off; three agents lost to HTTP 429)**:
  1. Scope narrowly and **frame defensively in the prompt**: "regression verification of already-fixed findings on a snapshot, with recording fakes; no payload is executed".
     Probe inputs are strings handed to a classifier or fake-recording functions; nothing dangerous is run (G15b hunter A's design, 267 probes completed). Do not ask a hunter
     to craft working exploits, to read real credentials, or to run a grader/bench; where B's original probes did that (BN-05 graded a planted `conftest.py` through the real
     grader), the verifier checks the **argv and env the hardened grader would use** through a recording fake and re-runs the retained unit tests instead.
  2. Units are small (about 40-80 probes, at most 0.6M tokens) and each is its own agent run so a halt loses one unit.
  3. If a unit is halted by a classifier, **do not push past or evade** (handoff 5): mark it `INCOMPLETE`, write what exists, and let the coordinator relaunch only the unfinished
     probes with a narrower prompt (the way D-5 was framed). A halted unit is never reported as complete and its findings stay at their previous tier.
  4. A summarizer agent writing the md afterwards from the TSV (what happened to B) is allowed only if the md is labelled as such and the TSV is the authority.

### 2.1 Hunter inputs that exist (verified by `ls`, 2026-10-24)

* A: `/data/data/com.termux/files/usr/tmp/g15b/A/{harness.py (53 lines), probes.py (212), run_probes.py (59)}` + `out/raw.jsonl` (71 KB) + `snap/` (941ec3f). The 267 probes are
  data rows `(pid, mode, cmd, expected, effect, severity, note)` in `probes.py`, driven through `classify_shell_command`, the real `shell()` and `TaskExecutor._daemon_shell`
  with recorders. **Hazard:** `run_probes.py` hard-codes `OUT="/data/data/com.termux/files/home/Codey-OS/docs/wp2_1_g15b_hunter_A.tsv"` (the committed G15b report) and
  `exec`s `harness.py` with `SNAP = A + "/snap"`. A verifier must copy these into its own scratch dir and change both before running, or it **overwrites the committed hunter-A TSV**.
* B: `.../g15b/B/scripts/{common,p1..p17,p1b,imp_driver,imp_child,rowcli,mkrows_p2}.py`, `logs/`, `benchcopy*`, `ws`, `snap`.
* C: `.../g15b/C/{h.py,p1..p20.py,rows1.py,rows2.py,writeall.py}`, `logs/`.
* Measured size: `wc -l` of A's three files = 324; A+B+C scripts total about 1,465 lines.
* **Verified hard-coded paths (grep of `home/Codey-OS`, `docs/wp2_1_g15b_hunter_`, `.codeyOS`, `CODE_DIR`, `bench/suite.lock` across A, B, C on 2026-10-24).** Writers to the **committed** reports:
  `A/run_probes.py:4` (`OUT=.../docs/wp2_1_g15b_hunter_A.tsv`, opened `"w"`: truncates the committed file), `B/scripts/common.py:17` (`open(".../docs/wp2_1_g15b_hunter_B.tsv","a")`: appends to it), `C/h.py:10` (`OUT=.../docs/wp2_1_g15b_hunter_C.tsv`; `C/writeall.py` does
  `os.remove(OUT)` then rewrites it from `rows1.py`/`rows2.py`: deletes the committed file). Path into the **real repo**: `C/p17.py:4` (`R="/data/data/com.termux/files/home/Codey-OS"`, used to build shell strings that are only classified). Repo-relative evaluator names
  (`bench/suite.lock`, `bench/lock.py`, `core/agent.py`, `main.py`) appear in `A/probes.py:76,84` and `B/scripts/{p2,p3,p5,p6}.py`, `C/{p5,p9}.py`, built from `S`/`SNAP`/`CD`/`td` variables: they are safe **only if** those variables point at the scratch snapshot; `B/scripts/p2.py:4,9` asserts `config.CODE_DIR`
  equals the disposable copy `B/home/Codey-OS` and `B/scripts/p3.py` edits `verify.py/gate.py/lock.py` in a copy. **Every one of these must be re-pointed to the verifier's scratch root before any run, and pre-flight (3) asserts it.** `C/p6.py:45` starts a real disposable `python3 -I -c time.sleep` process carrying a fabricated `--token` in argv (the G15b-12 repro): keep it, owned by PID, torn down by PID.
* These live under `/data/data/com.termux/files/usr/tmp`, a volatile location. **Stage 0 task (cheap, docs-only, Ish go needed because it adds tracked files):** copy the three sets, **re-pointed as above before they are committed** (so the tracked copy cannot overwrite a committed report),
  into a tracked `docs/wp2_1_g15b_harness/{A,B,C}/` with a README stating "retained repro scripts, 941ec3f baseline, not product code, never import into `tests/`", so verify-A is a re-run
  instead of a rebuild. If Ish declines, the verifiers still use them while they exist and must rebuild from the TSV `input` columns otherwise (about 2-3x cost for A, B and C).

### 2.2 Verify-A: shell and interpreter (one unit, about 0.5-0.8M tokens)

Findings in scope: G15b-01..24 (the entire shell family), the daemon (`core/task_executor.py::_daemon_shell`, G15b-17/18), the G15d tables (sed/awk/sort option tables, npm/pip/python -m/node
allowlists, D-2(b) secret reads, D-3 argv[0] with `/`), and the G15e shell argv protected-path scan (`cp mv ln touch mkdir rm rmdir chmod dd` against the shared set).
* (V) Re-run all 267 A probes on the HEAD snapshot. Expected: every A probe that was BYPASS at `941ec3f` and belongs to a CLOSED finding is now not EXECUTED-SILENT; probes for
  G15b-19/22/36 still execute (RESIDUAL-UNCHANGED). Any other EXECUTED-SILENT is a FAIL. The 2 INCONCLUSIVE A rows get a fresh attempt.
* (N) Explicit named probes (do not leave to chance): (1) **`tar xf x.tar -C ...`**: consolidated 0 flags a fact conflict (the G15c fact sheet lists `tar` both as refused and as an open residual);
  one `classify_shell_command` call on the final HEAD resolves it, record the verbatim result; (2) **pinned-matrix existence**: G15c's closure is "unknown basename => HIGH", so adding any
  of `kill/pkill/killall/su/gh/crontab/at/gcloud/...` to an allowlist later silently reopens it, and the register says "the G15z matrix must pin them". The verifier greps `tests/` for a parametrized
  test that pins each named family at HIGH_IMPACT and reports any family with no pinning test as a gap (a finding, not a fix); (3) option-abbreviation class (NEW-1036): `--exe`/`--no-ver` style prefixes for each
  table tool (pip, npm, node, python, sed, sort, find, git, make, cargo); (4) PATH-shadow and relative `argv[0]` after D-3; (5) the **`ln -s` then `write_file` through the link** and
  **`python3 script.py` after `write_file` of the script** two-step forms (the script-file ceiling must still hold and be *accurately described*, not silently widen); (6) daemon prefix forms
  (`lsof`, `envsubst`, `catman`, `echo2`, bundled `-Bc/-Ic`); (7) audit-row truthfulness for a refused/classified command (the NEW-1057 masking: a secret-shaped command line must not appear verbatim in the audit
  row); (8) hard links **NOT exercisable** here (`os.link` unavailable on this device; NEW-872): recorded INCONCLUSIVE-by-construction, never PASS.
* Excluded: executing any listed command; reading any real credential file (`~/.ssh`, `.netrc`, `age.key`): the classifier is handed the string only.

### 2.3 Verify-B: filesystem, file tools, protected paths (two units, about 0.5-0.6M each; B2 only if Ish says yes to D-5)

* **V-B1 (always)**: G15b-26, 27, 28, 33, 34, 35, 37 (as implemented by G15j if committed), 38, 39, 40, 41. Targets: `core/protected_paths.py` (shared DENY/HIGH tiers), `core/filesystem.py`,
  `tools/file_tools.py`, `tools/patch_tools.py`, `core/action_gateway.py` classification, `core/checkpoint.py` roots. Re-run B's FS/FT/HM/CS/IG/NT/CM/KB rows (p1..p12, p15..p17 scripts) on copies with a
  disposable workspace and a disposable CODE_DIR copy. Specific (V): symlink at final component and mid-path, relative-path resolution against process cwd (NEW-986 fail-open `except` at
  `tools/file_tools.py:117` and NEW-1063 pre-checks using `os.getcwd()`), nested and case-variant `.git` (`.GIT`, `foo/.git/hooks`), the audit ledger and state-dir writes through `write_file`/`append_file`/`patch_file`
  (the ledger **must remain appendable by the gateway itself**), `$HOME` startup files with workspace = `$HOME`, `.codeyOS/config.json` and `age.key`, launchers/`main.py`/`lib/*.sh`/`install.sh`/`setup*.sh`
  (F3), `patch_file` read-outside-workspace and the echo (NEW-1048), `.codeyignore` boundary. (N) new: Unicode-ignorable path components in `.git` names (the G15e accepted residual: measure it), `/dev/fd/N`
  and `/proc/self/fd` aliases, directory literally named `x.py`, `..` after symlink resolution, a symlink whose target is created *after* the check (TOCTOU, measure only).
* **V-B2 (conditional on D-5 = yes; narrow, defensive, disposable copies, one probe family per sub-run)**: the unfinished G15b-B probes only: Unicode normalization (B:UN-01), planted
  `ccos/data/capabilities.json` (B:PL-04; note the file is gitignored and absent from `git archive`), session and task-queue forgery (only HM-07 was done), the retained re-run of FT11/FT12 (G15b-38, the UNSUPPORTED
  rows), HM-06's restore step into a disposable CODE_DIR copy, BN-05 **through `tool_write_file` in a temp workspace but without the grader**, the operator launch-cwd code read (does `codey-start`/`codeyOS`/`codeydOS`
  ever `cd`? decides every "cwd precondition" label in the register). NEW-872 hardlinks: `os.link` unavailable, INCONCLUSIVE-by-construction. This is what makes closure of the UNSUPPORTED rows honest; without it those rows
  close **as accepted residuals with their UNSUPPORTED label retained** (consolidated 7 D-5: "mandatory before claiming closure at G15z for the unsupported rows").

### 2.4 Verify-C: plugins, bench, credentials, gateway, REPL confirm (three units, about 0.4-0.6M each)

* **V-C1 plugins and credentials**: G15b-25 (manifest authority), G15b-11/12 (child env, tunnel token in argv), G15b-48 (secret masking), G15b-43 (CCOS authority keyed by name), the G15g spawn audit,
  `entry_point` containment/symlink/duplicate-name refusals, `start_command`/`env` residuals (R1, NEW-1054) stated accurately. Re-run C's M05-M08/M25/M26/C01/C06 scripts and the 15-shape masking
  differential (`SECRET_PATTERNS`, `mask_secrets`: every shape that G15h said was added, plus 10 new shapes). The cloudflared check uses the **stub binary and a fabricated token** only (as G15h Unit A's disposable chain
  did) and only `ps -A -o pid,args` plus `/proc/<own pid>/cmdline` of the verifier's own child; the **real token tunnel start is NOT a verifier task** (it is Ish's LIVE_TEST_QUEUE `[G15h-A]` step).
* **V-C2 bench integrity (function level, copies, no bench run)**: G15b-29, 30, 31, 32 (lock v2, evaluator hash over `bench/**/*.py`, per-task rehash, snapshot, `compare()` mixed-evaluator refusal,
  `verify_lock` exact two-line format, hardened grader argv, scrubbed env incl. `LD_PRELOAD` dropped / `SHELL USER LOGNAME` kept, `stdin=DEVNULL`). Method: edit a **copy** of `bench/`, call
  `lock.verify_lock`/`evaluator_hash`/`suite_hash`/`compare` directly, assert the raise; capture the argv/env `bench/verify.py::_run_hardened` and `bench/agents.py` would use through a recording fake
  `subprocess` (no pytest child). No `CODEY_TRAJECTORY` (NEW-1068 unresolved: until Ish reconciles `CLAUDE.md` line 29 with the blueprint's WP0.5-DONE, treat the instruction as in force). The in-process junit forgery with
  the correct count and the self-attesting `write_lock` are **accepted residuals** (NEW-1067): measure, label RESIDUAL-UNCHANGED.
* **V-C3 gateway, REPL confirm, daemon, peers, egress, kill identity**: re-run C's authority matrix (production `gate_*` call sites x `confirm_available` predicate; flipping through `ALLOW_SELF_MOD`, `--allow-self-mod`,
  `--lora-force-adopt`, `CODEY_SELF_IMPROVE`, `CODEY_LINTER`, `CODEY_LLAMA_SERVER`, `CODEY_ACTION_GATEWAY_AUDIT=/dev/null` in a child, relative `CODEY_STATE_DIR` for the audit sink = NEW-1003), the G15j REPL/non-tty
  confirmation callback (a callback returning a truthy non-`True`, an exception whose message carries path/content, ANSI/markup injection through path or content, stdin closed: the list from G15j spec 2.7), the G15i
  operator-script guards (`provision_ai_agent_auth.py` and `setup_dr_key.py` with **no controlling tty**: expected refusal, DB/config bytes unchanged, on a disposable DB only), peer default-No (`PeerCLIManager.confirm`),
  daemon IPC `peer_uid` dead check (G15b-44, still queued: record RESIDUAL), `--tdd` confirm-less (G15b-47, depends on D-9), remote-backend egress against a recording fake endpoint (C:N01, INTENTIONAL), kill rows against
  their identity validators with synthetic fixtures that forbid signaling (DoD 8; `core/process_identity.py`, embed foreign-kill NEW-983 refusals: unreadable `/proc/net/tcp`, argv lookalike, recycled PID simulated).

### 2.5 Hunter findings handling

A FAIL or a NEW HIGH **reopens** the finding (never "fixed in G15z"): it goes to Ish (fix vs accept, DoD 4) and, if fixed, becomes a small slice G15z-F run through the full pipeline; the affected verify
unit re-runs for that item only, and **every file the fix touches must be re-classified** in the census (positional keys, 1.1). NEW findings get ids allocated by the coordinator (next free after the current
tail; allocate only after `git status --short` shows nothing changed in the three tracking docs).

## 3. Evidence-tier closeout table and outstanding live verification

### 3.0 Tier vocabulary (rule 7; each tier is stated, never collapsed)

`code-complete` < `code-reviewer-approved` < `independently re-probed` (NEW tier introduced by G15z-V: a fresh agent re-ran the original repro on the closing HEAD with recording
fakes; **it is not live verification** and must never be written as "live") < `live-verified` (real process/pty/device behaviour on this phone, with the limits stated: disposable fixture vs
real service vs real token; real tty vs `pty.fork`). A row's tier is the highest tier **actually evidenced**; "approved with warnings" keeps its warnings list.

### 3.1 Per-slice tier table (as of `50f9aa2`; sources: consolidated 10-10d, blueprint WP2.1 status tail, PROJECT_LOG; `NEW_ISSUES.md` is authoritative)

| slice | commit | covers (G15b ids) | code-complete | reviewer | live | G15z-V adds |
| --- | --- | --- | --- | --- | --- | --- |
| G15a census tool | `90646ff` | NEW-1009 etc. | yes | APPROVED | n/a (parse-only) | independent byte-identical `scan.tsv` re-run (1.2 A3) |
| G15c shell default-deny | `e167e0c` | 01-05, 17 | yes | APPROVED round 3 (rounds 1-2 CHANGES REQUESTED) | NO (recording-fake through real `shell()`/`_daemon_shell`) | verify-A re-run |
| G15d classifier tail (A,B,C) | `890d4b9` | 06, 09 (narrowed), 10 (scope), 13, 14, 15, 16, 20, 23, 24 (W5), 45, 46 | yes | APPROVED (A after a Critical re-review; B incl. node `--inspect` re-review) | NO; the **D-4 pty check (G15d spec 5.3) is still not done** | verify-A; L1-c (3.3) |
| G15f-A grader hardening, G15g-A discovery containment | `e9f593f` | 31, 32, 25 (containment half), 43 (narrowed) | yes | APPROVED | NO | verify-C1/C2 |
| G15e protected-path set (A,B,C) | `c842d97` | 07, 08, 26, 27, 28 (D-7 set), 29 (classification half), 33, 34, 35, 38 | yes | APPROVED (A after 1 CHANGES REQUESTED, Critical C1) | NO (not required by spec 12) | verify-B1 |
| G15g-B audited spawn | `f4353cf` | 25 (spawn audit half) | yes | APPROVED with warnings | **YES, disposable fixture plugins only** (real `PluginManager`+`Popen`; real aigentik/private_agent NOT exercised) | verify-C1 |
| G15h-A cloudflared token out of argv | `f4353cf` | 12 | yes | APPROVED | **disposable chain only** (stub, and real binary with a fake token); **real token NOT run** | verify-C1 (stub only) |
| G15h-B secret masking | `f4353cf` | 48 | yes | APPROVED (2 rounds) | NO | verify-C1 |
| G15f-B bench lock v2 | `623e4c7` | 29 (hash half), 30 | yes | APPROVED (round 2) | NO (bench never run with scrubbed env/hardened grader/lock v2) | verify-C2 |
| G15i operator-script guards | UNCOMMITTED (in flight, not covered by this spec) | 21 | per its own state | per its own state | pty harness recommended (spec 1.7) | verify-C3 once committed |
| G15j HIGH file-write confirmation | UNCOMMITTED (in flight; Ish GO recorded) | 37, 27 residual | per its own state | per its own state | pty harness required (spec 2.7) | verify-B1/C3 once committed |
| Groups 13/14 (earlier) | `876e1b6`, `249b61b`, `96ad7f4`, `3981457` ... | NEW-969/970/971, 14a-i | yes | APPROVED | 969/970/971 and 14b/c/d/e live-verified; **14a, 14a-ext, 14f, 14g, 14i have no individual live run** (scope doc 6 table; Ish to accept the tier or request runs) | none (earlier groups are outside the 49) |

Do not write the G15i/G15j rows from this table: their state belongs to the in-flight work and is to be filled by whoever commits them.

### 3.2 Preliminary status of the 49 G15b items at `50f9aa2` (architect derivation from consolidated 3 and 10-10d; **the coordinator recounts at G15z**, because those sections each say "counts not recomputed")

* **Closed at code-complete+reviewer-approved (28):** 01, 02, 03, 04, 05, 06, 07 (argv-visible forms), 08, 10 (classifier/daemon scope; option (c) env scrub deferred), 12 (severity corrected to MEDIUM), 14, 15, 16, 17, 18, 20, 23, 26, 27 (confirm-less modes), 29 (hash and classification halves), 30 (except self-attestation), 31, 32, 33, 34 (named forms), 35, 38 (rule-6 corrected from UNSUPPORTED), 48 (sessions, audit ledger, file logger, config show, CCOS `system.processes`).
* **Accepted residuals (4, Ish D-1 2026-10-24 or earlier decision):** 19, 22, 36; 13 (rest: bare-name/local-path/`-r` pip forms, pnpm/yarn conservative only).
* **Partial / narrowed / open with a stated remainder (9):** 09 (D-3 + PATH-shadow done, NEW-1037 remains), 11 (shell and plugin children inherit all env; D-2 option (c) deferred), 21 (G15i), 24 (W5 fixed; ruby/perl unverified, accepted false positives), 25 (start_command/env arbitrary R1), 28 (3 ambiguity-only files queued), 43 (C:M24/M26/N03 and runtime handlers untouched), 45 (dormant interactivity part only), 46 (spec 5.3 pty check not done).
* **Open, QUEUE or awaiting a decision (8):** 37 (G15j), 39, 40, 41, 42, 44, 47 (D-9), 49.
(28 + 4 + 9 + 8 = 49; the recount must reproduce this or explain each difference; severity totals at post-G15c were HIGH 33 / MEDIUM 9 / LOW 7; **G15b-12 was corrected from HIGH to MEDIUM by rule 6 (G15h Unit A), so the current totals are HIGH 32 / MEDIUM 10 / LOW 7**; the recount must not flag that as a discrepancy, and any other severity change needs its own ledger line.)

### 3.3 Live verification still outstanding, split by who can do it

**L1: a live-verifier agent can run these (disposable everything; real `pty.fork`, real subprocess, the NEW-971 pattern, `docs/wp2_1_new971_live_verification.md`).** None needs Ish at the keyboard.
* L1-a G15i-B: `provision_ai_agent_auth.py` and `setup_dr_key.py` under a pty (n -> rc 2 and no DB row, y -> mint/revoke, no ctty -> refusal, captured stdout -> refused), shim `age-keygen`, disposable DB/config (G15i/j spec 1.7).
* L1-b G15j: HIGH new-file/append prompt on a real pty: y / n / Enter / `^D`; ACT and DENY controls; `stdin=DEVNULL` and piped `y\n` must be `[BLOCKED]` (spec 2.7).
* L1-c G15d D-4 peer default-No: pty harness with fake peer scripts and a fakes-only PATH; Enter must now decline, `y` must still dispatch (G15d spec 5.3 / section 10).
* L1 limit to state in the report: NEW-996: on this device a real `^C` on a pty does not interrupt `input()`, so "Ctrl-C at the prompt" stays **unverified on-device**; say so rather than "verified". A `pty.fork` check and a human typing at the phone's own terminal are **different claims**; each row says which.
* Cost/RAM: no model load; `free -h` recorded for habit. Each is one unit of about 0.3-0.5M tokens.

**L2: Ish only (agents must not do these).**
* L2-a Real-token tunnel start: `LIVE_TEST_QUEUE.md [G15h-A / NEW-1021]` (3 steps; no model; rollback = revert `f4353cf` Unit A). It registers with Cloudflare and fronts the public API.
* L2-b A real bench run with lock v2 + hardened grader + scrubbed env: **blocked on NEW-1068** (CLAUDE.md line 29 says not to run the bench with `CODEY_TRAJECTORY=1` until WP0.5 lands; blueprint ~line 2507 says WP0.5 is DONE 2026-10-07 with `verified_training_episodes()` / `verified_eval_episodes()` and a regression test). Agents do not edit CLAUDE.md. A read-only verifier can first confirm the WP0.5 leakage regression test exists and passes on HEAD (cheap, 0.1M), then Ish reconciles the two documents. The run itself loads a model (rule 2: `free -h`, one model cycle, confirm unload), must name **`LD_PRELOAD` (dropped), `SHELL`, `USER`, `LOGNAME` (kept)**, compare shebang-script behavior (NEW-1047 item 6, NEW-1042), re-run **every** existing baseline (legacy rows lack `evaluator_hash`) and relock last. This is the only way to learn whether the env allowlist starves the on-device backend; until then G15b-32 is "closed at code-complete, allowlist sufficiency unverified".
* L2-c Real aigentik/private_agent plugin spawn: blocked on (i) stale `~/.codeyOS/plugins/{aigentik,private_agent}.pid` (Oct 7; they make real spawns refuse in production; G15g R13: cleanup is Ish's call) and (ii) the G15g question on the fate of the dead manifests (if they are dead, drop them and there is nothing to live-verify). The G15g-B disposable-fixture live run stands in the meantime and is labelled as such.
* L2-d Real escrow DR key (a PENDING ISH item in the G15i/G15j spec, 3.2 of that file: `setup_dr_key.py --force`; nothing in WP2.1 creates it), not WP2.1 work, but G15i changes that script: the first real run after G15i is the real-device check of the new guard.
* L2-e Optional: five group-14 slices without a live run (accept the tier or request).

### 3.4 "Implemented on the spec default, Ish's answer not recorded" (unratified defaults; each must be ratified or carried as residual R18)

Source: consolidated 10-10d, the slice specs and `NEW_ISSUES.md`. G15d spec Q1-Q4, Q6, Q7 (Q5 "trim" was accepted by Ish and applied); G15f Q2 (no `/dev/tty` gate on `write_lock`); G15g Q2 (capability-name collisions refused for in-memory manifests only),
the G15g spawn policy (ACT + audit), lazy activation, and the fate of the dead `private_agent`/`aigentik` manifests; G15h Q-b (other services keep the operator's exported token names); G15i/G15j Q-A (no audit row for
`setup_dr_key.py`), Q-B (HIGH new-file/append prompts under `--allow-self-mod` in the REPL), Q-C (stdin `ask_confirm` + `isatty()` rather than the `/dev/tty` primitive for file prompts), Q-D (DR key requires a terminal stdout), Q-E (lora delegation edit),
Q-F (patches keep the legacy `Apply patch?` prompt). Formal confirmations also missing: D-6, D-7 (+ NEW-1016), D-8, D-9, D-5. (Ish's recorded answers: F1, F2, D-F5, F3, F4, D-1, D-2(b), D-3, D-4, D-10 candidate-WP log, G15j GO.)

## 4. Docs closeout, the DoD statement and the handoff (G15z-D, coordinator-owned)

### 4.1 Which documents (and one conflict to confirm)

Track A (WP2.1) closeout goes to **`CODEY_OS_MASTER_BLUEPRINT.md`** (WP2.1 status note, mirroring the existing running "Status update" paragraphs), **`PROJECT_LOG.md`** (new top entry,
reverse-chronological) and **`NEW_ISSUES.md`** (per-finding status lines). The request text and `CLAUDE.md` rule 9 / workflow step 5 still say "`CODEY_MASTER_PLAN.md` §4 + Appendix A"; `CLAUDE.md`'s own "Start here" item 0 and the
banners in `CODEY_MASTER_PLAN.md` say §4 and the Track-A portions of Appendix A are **frozen/superseded for Track A**. This spec follows the banners: **do not edit `CODEY_MASTER_PLAN.md` §4 or Track-A Appendix A rows**; add
Appendix A lines only for Track-B-adjacent queue items (rule 8): NEW-1016 (blocking census coverage test vs Track B development), the `provision_ai_agent_auth.py` guard (G15i), `restoricon_core/authority*.py` now HIGH-classified
(D-7), and the `restoricon_core` qualname-level census rows. Decision Z-9 asks Ish to confirm this reading (and, separately, only Ish edits `CLAUDE.md` itself, e.g. its stale rule-9 wording).

Collision rule: run `git status --short` on the three tracking docs immediately before each save; write drafts to a scratch file first if another agent might be editing; stage exact paths, never `-A`, never `git stash`.

### 4.2 Edits (checklist)

1. **Blueprint** (`CODEY_OS_MASTER_BLUEPRINT.md`): (a) rewrite the WP2.1 headline (line ~2943, "SLICES 1-29 DONE ... full DoD not yet met") to the closed-with-accepted-residuals state **only after Ish signs 4.3**; (b) add the final
   status paragraph at the end of the WP2.1 status tail with the tier table of 3.1 (code-complete / approved / independently re-probed / live, kept distinct) and the residual list; (c) replace the stale DoD sentence ("no destructive call site bypasses the
   gateway; the section 16.1 three-surface split is gone", see the status tail near line 3432 and the DoD line) with the restated DoD (NEW-1013); (d) edit §16.1's three-surface wording to name the three mechanisms; (e) update the
   "Group 15: ... G15i, G15j and G15z open" tail line; (f) leave WP2.1's old running paragraphs intact (append-only convention) and say which they supersede.
2. **`PROJECT_LOG.md` top entry** with verbatim numbers (rule 5): closing HEAD hash; the census `--check --strict` command line and its output (`scan_rows`, `register_entries`, `unknown_rows`, `failures`, `warnings`, rc); the
   per-class row counts from `summary.json`; each verify unit's probe/PASS/FAIL/RESIDUAL/INCONCLUSIVE counts and any INCOMPLETE; the reviewer sample disagreement rates; the test commands **run fresh by the coordinator** (not copied from
   earlier entries; the stale-count warning from earlier rounds applies) with their pass/fail numbers; live verification list with what was *not* run. Honest tiers per row.
3. **`NEW_ISSUES.md`**: (a) DoD 5: every row in scope doc section 3 and every G15b-linked entry gets a final `Update` line saying fixed / accepted-residual / deferred-with-owner / excluded, with the tier; (b) **NEW-1013**: its
   heading still says "Ish decision F1 pending" and its Status says "Open, awaiting Ish"; an `Update` already records F1 = YES, so add the closure update and resolve the heading by an update line (entries are append-only, the correction is dated and explicit, rule 6); (c) **NEW-1018**
   (umbrella) closeout with the recounted table; NEW-1009 (UNKNOWN inventory) final count; NEW-1068 resolution or "still open"; new ids for verifier findings (next free id: verify the tail first; the last id seen at `50f9aa2` is NEW-1069
   but the in-flight G15i/G15j entries may already have taken more).
4. **`CODEY_MASTER_PLAN.md`**: only the Track-B-adjacent Appendix A lines in 4.1. Nothing else.
5. **Docs sweep** (scope doc 5 G15z): `docs/security.md` has **no** mention of the default-deny shell classifier, the protected-path set, the audited plugin spawn, secret masking or the census (grep for `default-deny|G15|HIGH_IMPACT|protected_paths` = 0 hits): add a short
   section (visible behaviour changes for operators: which commands are refused in confirm-less modes, DENY/HIGH path tiers, `WP21_CENSUS_*`); `docs/commands.md:161` and `docs/architecture.md:163` (the linter lines `CODEY_LINTER ruff|flake8|mypy` and
   the `linter.py` description; stale per NEW-984/991, re-read the code first); `docs/configuration.md` for any env switch added (`WP21_CENSUS_GATE/STRICT/SKIP_REPO/SOURCE`); `docs/troubleshooting.md` for "command refused in --yolo" (the D-F5 list).
   Any `CODEY.md`-related doc mention is checked by grep first. Suggest (for Ish, who owns `CLAUDE.md`) adding the new directories to the repo-structure section.
6. **`install.sh` (rule 11)**: G15 added no dependency (`tools/wp21_census.py` is stdlib-only; `core/tty_confirm.py` has none): state "install.sh unchanged, checked" explicitly in the log; if any slice added a PATH shim or a package, update it in the same round.
7. **`LIVE_TEST_QUEUE.md`**: add the L2 items of 3.3 with exact steps (the file already has `[G15h-A]`), so Ish's manual steps are written down; do not mark any of them done.
8. **Handoff** `docs/WP2_1_CLOSURE_HANDOFF_<date>.md` (supersedes `docs/WP2_1_HANDOFF_2026-10-23.md`): closing HEAD, the residual list, how to keep the register current (below), the L2 list, decisions still open, the next-WP pointer (4.5), and a paste-able resume prompt.

### 4.3 The DoD statement (draft for Ish's sign-off; closure is not an agent's call, scope doc 4)

> **WP2.1 (Action Gateway): CLOSED WITH ACCEPTED RESIDUALS, <date>, closing HEAD `<hash>`.** Restated definition of done (F1, Ish 2026-10-23): every effectful boundary in Codey-OS is either mediated by an authority
> mechanism that fails closed and audits truthfully (the Action Gateway `core/action_gateway.py`; CCOS `CAPABILITY_AUTHORITY` in `ccos/core/plugin_manager.py`; `restoricon_core` `BUSINESS_MUTATION_AUTHORITY`), or carries a documented
> bookkeeping / operator-bootstrap / loopback / dormant / read-only disposition in `docs/wp21_census/dispositions.tsv`, or is on the accepted-residual list below; the register is mechanically re-checkable
> (`python3 -I tools/wp21_census.py --check --strict`, zero UNKNOWN rows at the closing HEAD). This is **not** "no destructive call site bypasses the gateway": the shell tool remains an audited ACT opaque-execution surface (F2) that closes
> named dangerous forms, and only an OS-level boundary (candidate WP, NEW-1069) removes that ceiling. Evidence tiers are listed per slice and are not all "live verified".

**Accepted-residual list (starting point; the coordinator regenerates it from `NEW_ISSUES.md` at closure and Ish signs the final list; ids are the ones in the register, nothing here is invented):**

| # | residual | id(s) | basis |
| --- | --- | --- | --- |
| R1 | script-file / `-m` / interpreter opaque execution at ACT (the F2 ceiling) | G15b-19, NEW-904, NEW-1028 | D-1 2026-10-24 |
| R2 | self-launch of a more-privileged agent child (after the G15e narrowing) | G15b-22, NEW-1028 | D-1 |
| R3 | `--allow-self-mod --yolo` writes HIGH files unprompted | G15b-36, NEW-975, NEW-986 | D-1 (and Ish 2026-10-08) |
| R4 | OS-level boundary not built (candidate WP) | NEW-1069 | D-10 default |
| R5 | package-spec rest: pip bare-name / local path / `-r` by precedent, pnpm/yarn conservative only (not installed) | G15b-13 rest, NEW-1044 | G15d, not yet formally decided by Ish as a list |
| R6 | hard links (NEW-872, `os.link` unavailable here), `/dev/fd/N`, opaque execution, Unicode-ignorable `.git` aliasing | NEW-872, NEW-1051 | G15e residuals |
| R7 | PATH shadowing: agent-uid-writable system/PATH dirs, repo root stays on PATH (decided friction), `/system/bin` unlistable | G15b-09 (narrowed), NEW-1037, NEW-1050 | Q3 decided |
| R8 | ruby/perl allowlists unverified, accepted false positives | G15b-24, NEW-1044 | G15d |
| R9 | child env inherit-all for shell and plugin children (D-2 option (c) deferred); plugin `start_command`/`env` arbitrary | G15b-11, NEW-1020, NEW-1053, NEW-1054 | D-2(b) chosen |
| R10 | secret masking not applied to trajectory DB, checkpoints, telemetry, recovery history, `episodic_log`, memory tiers, console; positional secrets in argv/audit rows; same-uid readers of `environ`/`age.key` | NEW-1060, NEW-1066 | G15h residuals |
| R11 | bench lock self-attesting; same-uid windows; symlink-following snapshot copy; unchecked-hash `.pyc`; disk-bytes hash; all-absent `evaluator_hash` accepted by `compare()`; `suite_hash` NUL framing; sidecar hash not done; in-process junit forgery | NEW-1067 | G15f-B |
| R12 | queued Medium/Low: 39, 40, 41, 42, 43 (rest), 44, 45 (rest), 47 (D-9), 49, and the 3 ambiguity-only authority files (telemetry/store.py, pipeline/run.py, codey_estimator/__init__.py) | NEW-1031/1032/1034/1029/1030/1035, NEW-1016 | QUEUE |
| R13 | deferred: async speech child ownership; GCS bucket actions; classification/mediation deferrals | NEW-972; NEW-943, NEW-944; NEW-904/905/913/914 | Ish deferrals |
| R14 | content trust of persistent notes (prompt injection) and track assignment of privacy/ownership items | NEW-846; NEW-753, NEW-936 | scope doc 6 table |
| R15 | the census tool's own limits: attribute-name receivers, no `partial`/`getattr`/env indirection, shell scan is a line regex, static only (no dynamic complement), positional ordinals | NEW-1009 | G15a |
| R16 | the full test suite is not runnable on this device (OOM); verification is by bounded chunks, with a stated list of pre-existing unrelated failures | NEW-791, NEW-906 | device limit |
| R17 | the L2 live-verification gaps of 3.3 (real tunnel token, real bench run, real aigentik/private_agent spawn, five group-14 slices) until Ish runs them | NEW-1021, NEW-1046, NEW-1068 | tier honesty |
| R18 | "implemented on spec default, Ish's answer not recorded" (3.4 list) unless ratified before closure | see 3.4 | rule 7 honesty |

### 4.4 Keeping the register current after closure

The census is only a control while it stays blocking. Ongoing rule: a commit that adds, removes or reorders a boundary call updates `docs/wp21_census/dispositions.tsv` in the same commit (run the command in 1.1 with `--seed`, copy the new rows, **delete stale keys by hand**, classify the new row, never leave UNKNOWN);
a reviewer reads any diff that reorders same-callee calls in one function (S1). Put this sentence in the handoff and in `docs/security.md`.

### 4.5 What comes after WP2.1 (blueprint §21, read 2026-10-24)

WP2.1 is the only open item in P2 that the other P2 items depend on. After closure the **unblocked set** (do not pick for Ish; present it) is:
* **WP2.2 Worlds / Playground isolation** (`Deps: WP2.1`): the live store must be unreachable from any non-production configuration. Premise confirmed in code at HEAD: `restoricon_core/database.py:18-20` still defaults
  `DEFAULT_DB_PATH` to `~/.codeyOS/restoricon.db` when `RESTORICON_DB_PATH` is unset. This is the natural next item: smallest, Track-A/B boundary, and it directly serves `CLAUDE.md`'s binding constraint (data integrity).
* **WP2.3 Registry and validator cleanup** (`Deps: WP2.1`): needs **re-scoping first**, because G15c-G15e made `classify_shell_command` the live validator and added a pinned classification matrix (its text still says "make one shell validator live
  (or delete both)", `tests/security/test_shell_injection.py` retarget, purge 3 leaked fixtures and 4 orphan `speech.*` rows); check what is already true before scoping (WP2.3a is DONE).
* **WP2.4 Snapshot before patch**: already marked "largely already true; rescope needed" (verify the revert path end-to-end, delete the NEW-840 dead duplicate).
* Not P2 but gated on "P2 Gateway complete": **WP5.1** (split `restoricon_core/` into its own repo; also needs P0, done) and **P6 track D** (self-extension; also needs WP1.3 rollback proven and a non-empty bench ledger, so it also waits on the L2-b real bench run). P3 (BrainManager/NPU) and P4 (memory read-back) have no WP2.1 dependency and can be interleaved at Ish's choice.

## 5. Staged execution order, estimates, risks

All token figures are order-of-magnitude budgets per stage, **not measured** (same caveat as consolidated 8). Measure the first unit of each kind (V-A and C7 are the best probes) and rescale the rest. Pipeline for every unit:
architect (this spec) -> Sonnet agent (explicit model override; `.claude/agents/code-reviewer.md`, `live-verifier.md` and `code-hygiene-auditor.md` declare `model: haiku`, contrary to the Sonnet default of 2026-10-06, so state the model in the dispatch) -> coordinator. Rule 10: no new agent is created; **no dedicated
"hunter" or "classifier" agent exists**: the G15b hunters were ad-hoc. The verify-only hunters should use `code-reviewer` (adversarial, has Bash) with Write via its Bash, or a general-purpose Sonnet agent; classifiers likewise; live checks use `live-verifier`; coordinator's call, but say in the dispatch which.

### 5.1 Stages

| stage | what | agents | tokens | parallel? | needs from Ish first |
| --- | --- | --- | --- | --- | --- |
| S0 | prerequisites: G15i and G15j committed through their own pipeline (not G15z work); preserve G15b harness to `docs/wp2_1_g15b_harness/` (Z-3); read-only check that the WP0.5 leakage regression test exists and passes on HEAD (NEW-1068 prep); decisions Z-3/Z-4, D-8/D-9/G15f-Q2/G15g items | coordinator + 1 small agent | ~0.2M (excluding G15i/j) | independent items parallel | Z-3, Z-4, D-9, G15f Q2, G15g items (they decide whether code changes happen BEFORE the freeze) |
| S1 | verify-only hunters V-A, V-B1, V-C1, V-C2, V-C3 (+V-B2 if D-5 yes), each writes `docs/wp2_1_g15z_verify_X.{tsv,md}` incrementally | 5-6 fresh Sonnet agents | 2.7-3.6M (+0.5-0.7M for V-B2) | yes: disjoint outputs and snapshots, no model, cap **3 concurrent** (HTTP 429 history); start after S0 so they hunt the final HEAD | Z-4 (D-5) |
| S1b | L1 live checks: L1-a (G15i-B), L1-b (G15j), L1-c (G15d D-4), real pty via `pty.fork`, disposable everything | 3 `live-verifier` runs | 0.9-1.5M | L1-c anytime; L1-a/b after G15i/j commit; parallel with S1 | none (not Ish-attended) |
| S2 | triage: every FAIL / NEW HIGH goes to Ish; accepted ones to the residual list, fixed ones become small slices G15z-F (architect -> implementer -> code-reviewer, rule 4 where lifecycle) and re-verify that item | per slice | 0-1.6M (0-2 slices, unknown until S1) | slices sequential if they share files | per-finding fix vs accept |
| S3 | **freeze**: the last code commit lands; `git status` clean for scanned paths; census re-run `1.1/1.2` (A1-A3), register drift fixed, scan reproducibility `cmp` by a second agent | coordinator + 1 agent | 0.2-0.3M | no | none |
| S4 | classification C1-C7 (1.3-1.4), each its own scratch TSV, append-after-every-file | 7 Sonnet agents | 2.9-4.9M | yes, disjoint files, cap 3 concurrent; C2 (`restoricon_core`) and C3 (shell/launchers) need only their own file families frozen, so they may start before S2 ends if S2's fixes touch none of them; **C1 (manifests) also depends on `ccos/core/plugin_manager.py`**, because each manifest capability row's `authority_listed` detail is computed from `CAPABILITY_AUTHORITY` in that file (`_authority_keys`), so any S2 fix to it invalidates C1. Re-run `--check` at S3 to prove nothing drifted | Z-2 (scope of classification) |
| S5 | independent review R1-R3 (re-classify 25% + 100% UNMEDIATED / helper-based GATED / kill rows; 100% of the 35 READ-listed capabilities; mutation check per distinct mediator); disagreement resolution | 3 fresh agents + architect | 0.9-1.5M | R units parallel after their C unit | none |
| S6 | merge to `dispositions.tsv`, `--check --strict` rc 0, `WP21_CENSUS_STRICT=1 pytest tests/test_wp21_census.py`, gate flip (test edit, code-reviewer, demonstration that an undispositioned boundary fails), coverage test blocking | coordinator, implementer, code-reviewer | 0.4-0.6M | no | Z-1 |
| S7 | docs closeout 4.2, handoff, `LIVE_TEST_QUEUE` entries, ledgers (about 49 + new entries) | coordinator | 0.5-0.8M | no | Z-6, Z-7, Z-8, Z-9 (residual list, DoD text, tiers, doc target) |
| S8 | fresh regression run in bounded chunks (never copy old counts), Ish's explicit closure sign-off, commit (stage exact paths) | coordinator | 0.1-0.2M | no | the closure decision itself |

**Totals.** Base G15z as consolidated 8 priced it (S0, S1, S3, S7, S8): **3.7-5.1M** (priced there at 3.0-4.0M, slightly low even before classification). Classification S4-S6: **4.2-7.0M, which consolidated 8 did not price at all** (scope doc 8 had priced the equivalent
G15a classification at 1.5-2.0M, but that pass was never run). L1: 0.9-1.5M. Fixes: 0-1.6M. V-B2: 0-0.7M. **Whole of G15z: about 8.8-15.9M tokens, 40-60 agent runs**, versus 3.0-4.0M in the register. A bounded "G15z-lite" (S0, S1, S3 drift-only, S7, S8; no classification, so DoD 3 unmet) is about
3.5-5M, but it is **not** the DoD as written (zero UNKNOWN) and would need Ish's explicit Z-2 amendment with the statement "UNKNOWN rows are unclassified, not safe, and are listed as residual R-unclassified".

### 5.2 Gates (stop points)

* After S1: if any FAIL or NEW HIGH, stop and take it to Ish (S2) before any classification.
* Before S3: nothing scanned changes after the freeze commit; a later edit to a scanned file invalidates that file's dispositions (positional keys).
* After S5: if a unit's reviewer disagreement exceeds about 15%, redo that unit with a fresh classifier rather than patching it.
* S8: Ish decides closure; an agent never declares WP2.1 closed.
* CLAUDE.md stop conditions apply: a code-reviewer rejecting the same fix twice without converging, a live-verifier showing the symptom is not resolved, or product-direction ambiguity -> escalate.

### 5.3 Risks and mitigations

1. **Usage limits / HTTP 429** (three agents died in G15b). Units <= 0.6M, incremental TSV/raw appends, resume-after-last-row, cap 3 concurrent agents, finish S1 before S4 so a stall is cheap.
2. **Hunter halted by a safety classifier** (G15b hunter B, C's final turn). Defensive framing, recording fakes, strings only, no grader/bench/network/credentials; a halted unit is INCOMPLETE and re-launched narrower, never pushed past (2.0).
3. **Rubber-stamp classification**: 1,437 rows of confident-looking `evidence` that nobody re-derives would convert "unknown" into false assurance, the exact failure the register exists to prevent. Mitigations: evidence must be `file:function` plus a named test or a reverse-call-graph result; independent re-classification samples with the disagreement rate printed; mutation check per distinct mediator; 100% review of UNMEDIATED, kill, helper-based GATED and READ-listed capabilities; the tool's known blind spots (R15) stated in the report.
4. **Positional keys**: any late fix shifts ordinals; sequencing S2 before S3/S4 and the `--check` drift run at the freeze.
5. **Gate flip breaks development**: after S6 every boundary-adding commit must carry its disposition; Track B friction (NEW-1016). Z-1 decides default-blocking vs CI-only vs closure-time-only.
6. **Concurrent edits to tracked docs / foreign dirty files** (941ec3f appeared mid-pause; 5 shell files were foreign for 4 days). `git log -3` and `git status --short` before each stage; stage exact paths only.
7. **Worktree vs head**: `--source worktree` scans untracked files (644 rows from the local `ccos/data/capabilities.json`, about 40 rows of `.live_verify_scratch`); closure uses `head` only (1.0).
8. **Hunter scripts hard-code the committed G15b output path** (`run_probes.py` OUT): copy and re-point before running (2.1) or the committed report is overwritten.
9. **Findings in G15z reopening "closed" items** (a FAIL): expected, handled in S2; the report keeps failed runs (DoD 7).
10. **Known failing tests** (handoff 6) will obscure regressions: record the exact pre-existing failure list at S8 and run the chunks fresh.

## 6. Decisions needed from Ish (none is recorded as decided here)

Already decided by Ish and **not** to be re-asked: F1 (WP2.1 may close as "closed with accepted residuals"), F2, D-F5, F3, F4 (rubric ratified), D-1 (G15b-19/22/36 accepted), D-2 option (b), D-3, D-4, D-10 candidate-WP log (NEW-1069), G15j GO.

### 6.1 Needed BEFORE S0/S1 (they decide what code changes before the freeze, or which units run)

| id | question | recommended default | effect if the answer is the non-default |
| --- | --- | --- | --- |
| Z-4 (= D-5) | Run V-B2 (narrow, defensive relaunch of the unfinished hunter-B probes)? | yes, narrow, disposable copies, no grader/bench/model; 0.5-0.7M | "no": the UNSUPPORTED rows (FT11/FT12, HM-06 restore step, BN-05 via `tool_write_file`, UN-01, PL-04, session/task-queue forgery, launch-cwd read) close as **accepted residuals labelled UNSUPPORTED**, never as verified; consolidated 7 says V-B2 is mandatory before claiming closure for those rows |
| Z-3 | Preserve the G15b repro harnesses (`/data/data/com.termux/files/usr/tmp/g15b/{A,B,C}`, about 1,465 lines, verified by `wc -l`) into tracked `docs/wp2_1_g15b_harness/`? | yes (volatile location; makes verify a re-run, saves ~2-3x on A/B/C if lost) | verifiers rebuild from the TSV inputs |
| D-9 | Is `--tdd` meant to be confirm-less without `--yolo`? | document it as intended (it is existing behaviour; Medium) unless Ish says no | "no": G15b-47 becomes a one-line code fix that must land before the freeze |
| G15f Q2 | `/dev/tty` gate on `write_lock` (lock stays self-attesting today)? | no (as implemented) | "yes": code change in `bench/lock.py` + relock + re-run of verify-C2 |
| G15g | (i) spawn policy ACT+audit vs a higher class, (ii) lazy activation, (iii) the dead `private_agent`/`aigentik` manifests: drop them or keep? | as implemented; if dead, drop/disable them (removes L2-c) | code/data change before the freeze; census rows move |
| D-6, D-7, D-8 | formal confirmation: D-6 `manifest.json` classified HIGH (implemented by G15e on F3 yes); D-7 root set for non-root authority files, incl. the Track B friction (NEW-1016); D-8 keep HIGH for 07/31/35/37 (04 closed regardless, 10/11 follow D-2, 28 follows D-7) | confirm all as implemented | a lowered rating changes severities in the register (no code), a reversed D-6/D-7 changes classification code |
| NEW-1068 | `CLAUDE.md` line 29 ("do not enable CODEY_TRAJECTORY=1 and run the bench until WP0.5 lands") vs blueprint ~2507 (WP0.5 DONE 2026-10-07). Which is right, and Ish edits CLAUDE.md | blueprint is right if the read-only check in S0 confirms the leakage regression test is green; Ish corrects CLAUDE.md | until then verifiers and the manual bench run treat the CLAUDE.md instruction as in force |
| deferrals | confirm as accepted/deferred residuals rather than WP2.1 work: NEW-972, NEW-943/944, NEW-904/905/913/914, NEW-846, NEW-753/936 track assignment | accept as residual R13/R14 with owners | any "no" becomes a slice and delays the freeze |

### 6.2 Needed BEFORE S4 (classification)

| id | question | recommended default |
| --- | --- | --- |
| Z-2 | Classification scope: (a) **full zero-UNKNOWN** (DoD 3 as written; 4.2-7.0M) or (b) risk-ordered partial (exec/kill/network/credential/dyn_code/env_mut categories, about 215 rows over all dirs, plus manifests, restoricon, shell first) with the remainder listed as residual "unclassified, not safe" and the strict gate left off | (a), delivered tranche by tranche so partial progress is durable; (b) only as an explicit DoD amendment |
| Z-1 | Form of the gate flip: make `test_repo_head_snapshot_is_covered_by_register` blocking by default (edit the env condition); keep STRICT closure-time-only; wire `gate_restoricon` to the test or leave `restoricon_core` qualname rows hard | blocking default for the coverage test; STRICT as a closure-time run; `restoricon_core` qualname rows stay hard (NEW-1016 friction accepted) unless Ish says Track B development should be exempt |

### 6.3 Needed BEFORE S7/S8 (closure itself)

| id | question |
| --- | --- |
| Z-6 | Sign the accepted-residual list R1-R18 (4.3). This includes ratifying or carrying as residual the unratified spec defaults of 3.4 (R18). |
| Z-7 | Sign the DoD statement text (4.3) and the closure form. Closure is Ish's call, not an agent's. |
| Z-8 | Group-14 slices 14a, 14a-ext, 14f, 14g, 14i: accept reviewer-approved tier, or request live runs. |
| Z-5 | Schedule the Ish-only live items L2-a (real-token tunnel), L2-b (real bench run, after NEW-1068, with `free -h`/one model cycle), L2-c (real aigentik/private_agent spawn after the stale `.pid` cleanup, or drop the manifests), L2-d (real DR key). Closure may precede them only if they are on the residual list (R17). |
| Z-9 | Doc-target confirmation: Track A closeout goes to the blueprint, `PROJECT_LOG.md` and `NEW_ISSUES.md`, **not** `CODEY_MASTER_PLAN.md` §4/Appendix A (4.1); Appendix A gets Track-B-adjacent lines only; Ish owns any `CLAUDE.md` wording fix. |
| next | Which of the unblocked set (4.5) starts next. Recommendation: WP2.2, then a re-scope of WP2.3/WP2.4. |

## 7. Facts this spec rests on (for the reviewer)

* CLI: `python3 -I tools/wp21_census.py --help` output (flags above). `--check` returns rc 1 on any failure; `--strict` adds `unknown-remains`; `--seed` writes `dispositions.seed.tsv` under `--out` only and never deletes stale keys (`merge_seed`, read).
* Counts: two read-only runs on 2026-10-24 into the architect's scratchpad (`census_head` for `50f9aa28`, `census_wt` for the worktree); register md5 unchanged; numbers quoted in 1.0.
* Gate semantics: `tests/test_wp21_census.py:707-746` (env vars only; no CLI flag).
* Taxonomy and coverage rules: `tools/wp21_census.py:85-100, 1203-1318` (`QUALNAME_LEVEL_CLASSES`, `evaluate_coverage`).
* Hunter inputs: `ls` of `/data/data/com.termux/files/usr/tmp/g15b/{A,B,C}`; `run_probes.py` hard-codes the committed hunter-A TSV as its output path (read).
* Slice states and hashes: `git log --oneline -30`, consolidated 10-10d, blueprint status tail (lines ~3646-3705), `LIVE_TEST_QUEUE.md`, `docs/wp2_1_g15i_g15j_spec.md` (G15i/j are **not** evaluated here beyond what their spec says they need).
* Next-WP facts: blueprint §21 WP2.2/2.3/2.4/WP5.1/P6-D dependency lines; `restoricon_core/database.py:18-20` default DB path.
* Not done: no hunter was run, no classification was attempted, no test suite was run, no ledger/source/test file was edited by this spec; the only files written are this spec and scratch outputs.
