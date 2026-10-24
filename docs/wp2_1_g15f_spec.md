# WP2.1 slice G15f "bench evaluator integrity": technical specification

Date: 2026-10-23. Author: project-architect. HEAD at writing: `9a61e94`. Status: **SPEC ONLY. No source, test, ledger, blueprint or
consolidated-register file was edited.** This file is the only thing written (plus disposable probe output under the session scratchpad and
`/data/data/com.termux/files/usr/tmp/g15f_arch/`, which holds only an empty HOME/state dir and a `--help` dump).

Covers G15b-29, 30, 31, 32 (`NEW-1025`, `NEW-1008`) plus three closely related defects found while verifying them (section 1.2, tentative ids
`NEW-1045..1047`). Constraints from the task and `CLAUDE.md`: **no bench run, no model load, no `CODEY_TRAJECTORY=1`, no network** (NEW-761; blueprint
:2507 says WP0.5 is DONE 2026-10-07 while CLAUDE.md still says "until WP0.5 lands": a doc inconsistency for the coordinator, the never-run rule is kept
here regardless). Everything is function level on disposable copies.

Decisions already recorded by Ish that bind this slice (consolidated section 7, "Decisions recorded 2026-10-23"): F1 yes, F2 yes, D-F5 yes, F3 yes, D-2 option
(b), D-3 yes, D-4 yes. F3 lists `main.py`, launchers, `lib/*.sh`, `install.sh`, `setup*.sh`, `config.json`, non-`.py` plugin files: **it does not list `bench/**`
non-`.py` files**, so "classify every suffix under `bench/**` HIGH" is a decision G15f needs (Q1, section 11). F4, D-1, D-5..D-10 are still pending.

## 0. Grounding (rule 12: everything below was read or run on this device on 2026-10-23, none from memory)

### 0.1 Code facts (HEAD `9a61e94`, read in full: `bench/{lock,verify,agents,runner,suite,gate,compare,promote,stats}.py`, `bench/README.md`, `bench/scorecard.py` 440-590 and 736-908)

| # | fact | where |
| --- | --- | --- |
| F1 | `suite_hash(tasks_dir)` hashes `(relative path, NUL, bytes, NUL)` for every file under `bench/tasks` (rglob, sorted; skips `__pycache__` and `*.pyc`). `bench/` has 50 tracked files (`git ls-files bench | wc -l`); 32 are under `tasks/` (8 tasks x 4: `prompt.txt`, `starter/<m>.py`, `hidden/test_<id>.py`, `reference/<m>.py`). The other 18 are unhashed: 9 evaluator modules (`agents compare gate lock promote runner stats suite verify`), `__init__.py`, `scorecard.py`, `power_analysis.py`, 3 `.md`, `suite.lock`, `scorecard_history.jsonl`, `scorecard_manual.json`. `verify_lock()` at HEAD returns True with hash `90e1f380...` | `bench/lock.py:9-17`, :26-29 |
| F2 | `write_lock()` computes the hash from the very files it protects and writes it to `bench/suite.lock`, a plain file beside them: self-attesting. Anyone who can write the task files can write the lock | `bench/lock.py:20-23` |
| F3 | `verify_lock()` is called from exactly one production site, `run_suite` (:15), once, at the start; default arguments always mean `ROOT/tasks` even when the caller passes `tasks=` (:15, :18) | `bench/runner.py:15-18` |
| F4 | Per task and per rep the runner re-reads the repo from disk: `shutil.copytree(t.starter, ws)` (:24) and, inside `grade`, `shutil.copytree(task.hidden, work, ...)` (`verify.py:34`). Nothing re-checks the hash after :15 | `bench/runner.py:24`, `bench/verify.py:34` |
| F5 | `grade()` copies the agent workspace wholesale (`verify.py:32`, ignore only `__pycache__`, `.pytest_cache`), overlays hidden tests, then runs `python -m pytest -q -x -p no:cacheprovider <work>` with `cwd=work` and the full ambient environment (no `env=`), verdict = `returncode == 0` (:36-39) | `bench/verify.py:32-39` |
| F6 | `make_codey_cli_agent` builds `env = dict(os.environ)`, overlays `CODEY_TRAJECTORY=1` and `CODEY_TRAJECTORY_TAG=bench:<id>`, then `extra_env` (:26-28); spawns `main.py <prompt> --yolo --no-resume` + `extra_args` with `cwd=workspace`, `capture_output=True`, **no `stdin=`** (so the operator's stdin is inherited) (:29-31). It has no caller outside tests (grep of `*.py *.sh *.md` excluding docs/tests/bench) | `bench/agents.py:23-34` |
| F7 | `main.py:119` `allow_self_mod = args.allow_self_mod or os.environ.get("ALLOW_SELF_MOD","0") == "1"`. `core/filesystem.py:145-150`: a path under `CODE_DIR` but outside the workspace is denied unless `allow_self_modification`. So in the bench child (workspace = temp dir, repo = `CODE_DIR`) an inherited `ALLOW_SELF_MOD=1` is what lets the file tools write `bench/verify.py` or a hidden test; without it the repo is unreachable to the file tools (the shell tool is a separate, accepted route, see 0.3). the parser is built at `main.py:32` as `argparse.ArgumentParser(description=...)` with no `allow_abbrev` argument (grep of `ArgumentParser|allow_abbrev` in `main.py`: one hit), i.e. the default `True`, so `--allow`, `--allow-s` also resolve to `--allow-self-mod` | `main.py:119`, `core/filesystem.py:111-150` |
| F8 | `tools/wp21_census.py:205` already names the authority-class env set `ENV_CLASS_AUTHORITY = {"ALLOW_SELF_MOD","CODEY_SELF_IMPROVE","CODEY_TRAJECTORY"}` | `tools/wp21_census.py:205` |
| F9 | Classification: `tools/file_tools.py:89-120` `classify_write_action` -> `core/checkpoint.py:69` `is_core_file`: HIGH only when the path is under a `CORE_CLASSIFICATION_ROOTS` entry (`bench` is one, `core/checkpoint.py:48`) **and `.py`**. `bench/suite.lock`, `scorecard_manual.json`, `scorecard_history.jsonl`, `tasks/**/prompt.txt` are ACT. `core/checkpoint.py:43-47` attributes the `.py`-only scope to "Ish fork 1, 2026-10-17" (14a-ext). `is_core_file` also drives `_require_checkpoint` in `core/filesystem.py` (:225, :266, :285, :319, :375); `_validate_path` (the outside-workspace gate) does **not** use it | `core/checkpoint.py`, `core/filesystem.py` |
| F10 | `tests/test_core_file_classification_ext.py:44-57` pins `bench/scorecard.md`, `bench/suite.lock`, `bench/scorecard_history.jsonl`, `bench/tasks/t01/task.yaml` as `is_core_file == False` / ACT, and `test_non_py_under_ext_root_skips_checkpoint` | `tests/test_core_file_classification_ext.py` |
| F11 | Scorecard anchors that must keep working (changing them silently moves the AGI score, rule 1): 4a = `bench/suite.lock` exists AND `bench/runner.py` imports `verify_lock` from a module named `lock` AND calls it (`bench/scorecard.py:453-467`); 4c = `bench/gate.py` `decide()` subscripts the keys `n, cand_only, base_only, p_value, ci95` (:497-512). **G15f must not touch `gate.py`.** The manual sidecar `bench/scorecard_manual.json` feeds items 6e and 7d (up to 5 points) and is validated for shape and non-empty `citation` only (`scorecard.py:739-766`); the history line records `scorecard_md_sha256` but not the sidecar hash (`scorecard.py:856-882`) | `bench/scorecard.py` |
| F12 | The bench ledger is empty (no `bench/experiments.jsonl`, `scorecard_manual.json` 6e note, `bench/power_analysis.md:32`), so changing what a ledger row records breaks no stored comparison | `bench/scorecard_manual.json` |
| F13 | pytest 9.1.1 on Python 3.14.6 here. `python3 -I -m pytest -VV` lists exactly one third-party autoloaded plugin: `anyio-4.14.2`. `pytest --help` (dump retained at `/data/data/com.termux/files/usr/tmp/g15f_arch/pytest_help.txt`) shows all of: `--noconftest` ("Don't load any conftest.py files"), `-c/--config-file FILE`, `--rootdir=ROOTDIR`, `--junitxml=path`, `-p name` incl. `no:` prefix, `--disable-plugin-autoload` ("Disable plugin auto-loading through entry point packaging metadata"), `--confcutdir`, `--import-mode`, env vars `PYTEST_ADDOPTS`, `PYTEST_PLUGINS`, `PYTEST_DISABLE_PLUGIN_AUTOLOAD`; ini keys `addopts`, `pythonpath`, `required_plugins` | `pytest --help` |
| F14 | `python3 -c "open('/dev/tty')"` in this tool harness: `OSError: [Errno 6] No such device or address: '/dev/tty'`. A `/dev/tty` confirm (the `core/lora_import.py:61-110` NEW-977 precedent) therefore cannot be exercised or used for relocking from an agent-harness shell; see Q2 | probe |
| F15 | Hidden dirs contain only `test_*.py` (no hidden `conftest.py`, no fixture dirs) for all 8 tasks (`git ls-files bench/tasks`). Starters contain one module each | `git ls-files` |

### 0.2 Probes (real `pytest` subprocesses inside `bench.verify.grade` on disposable copies of `t01_slugify`; scripts in the session scratchpad, probe dirs deleted afterwards; no model, no `CODEY_TRAJECTORY`, no network, `HOME`/`CODEY_STATE_DIR`/`CODEY_ACTION_GATEWAY_AUDIT` under `/data/data/com.termux/files/usr/tmp/g15f_arch/`, proxy vars unset). **Disclosed deviation, same class as hunter B's BN-05 run:** these executed `pytest` (which executes the planted agent files). `tests/test_bench_harness.py` already does the same on every run (`test_null_scores_zero_and_oracle_scores_all`), so the proposed tests below are not a new kind of act.

P1 (current `grade()`; starter unsolved, planted file(s) added to the workspace):

```
control                    -> False
conftest_deselect_all      -> False          (rc 5, no tests: not a pass)
pytest_ini_addopts_k       -> False
module_os_exit0            -> True           slug.py: import os; os._exit(0)
module_sys_exit0           -> False
extra_test_file_exit0      -> True           test_zz.py: import os; os._exit(0)
sitecustomize              -> False
```

P2 (current `grade()`):

```
conftest_force_pass (hookwrapper pytest_runtest_makereport -> outcome=passed)  -> True
conftest_in_subdir_not_collected_path                                          -> False
conftest_configure_exit0 (pytest_configure: os._exit(0))                       -> True
pytest_ini_collect_only  (addopts = --collect-only)                            -> True
tox_ini_collect_only                                                           -> True
pyproject_collect_only   ([tool.pytest.ini_options] addopts)                   -> True
setup_cfg_collect_only   ([tool:pytest] addopts)                               -> True
pytest_ini_plus_local_plugin (addopts = -p zzplug + zzplug.py)                 -> True
```

So the register's "conftest.py is honored" is **narrower than reality**: `pytest.ini`, `tox.ini`, `pyproject.toml`, `setup.cfg` are honored too, and the verdict is `returncode == 0` alone, so `os._exit(0)` at import time in the agent's own module (or in any extra file pytest collects) also grades as pass.

P3 (proposed hardened argv: `python -I -m pytest -q -x -p no:cacheprovider --noconftest --disable-plugin-autoload -c <empty ini outside work> --rootdir <work> --junitxml=<file outside work> <explicit hidden test paths>`, `cwd=work`, env = `{PATH, HOME(disposable), TMPDIR}` only; columns = `(returncode, junit tests/failures/errors/skipped)`):

```
control_unsolved             (1, tests 1, failures 1, errors 0, skipped 0)
conftest_force_pass          (1, tests 1, failures 1)
conftest_configure_exit0     (1, tests 1, failures 1)
pytest_ini_collect_only      (1, tests 1, failures 1)
tox_ini / pyproject / setup_cfg collect_only   (1, tests 1, failures 1) each
ini_plugin (-p zzplug)       (1, tests 1, failures 1)
extra_test_exit0             (1, tests 1, failures 1)     (extra test file is not collected: only hidden paths are passed)
sitecustomize / usercustomize (1, tests 1, failures 1)
module_os_exit0              (0, NO junit file)           <- rc alone would still pass: needs the evidence check
module_forge_junit           (0, tests 4, failures 0)     <- RESIDUAL: module reads sys.argv, writes a forged junit, os._exit(0)
solved_reference             (0, tests 4, failures 0)
env PYTEST_ADDOPTS=--collect-only passed through  (0, tests 0)   <- shows why the env must be scrubbed AND the count checked
```

P4 (`runner.run_suite` with a callable agent, `tasks=` = a disposable copy of the first two tasks, real default lock still valid; the agent callable rewrites each `hidden/test_*.py` on disk to `assert True` before grading, simulating a script-running agent child with repo write access):

```
[('t01_slugify', True), ('t02_fizzbuzz', True)]
real lock still valid: True | row suite_hash == real tasks hash: True
tmp tasks hash == real: False
```

Two facts from P4: (a) **the lock is checked once; a hidden test edited after that is read from disk and honored** (F4); (b) **the `suite_hash` recorded in the row is the hash of the on-disk default `ROOT/tasks`, not of the tasks actually graded** (F3), so the row attests the wrong thing whenever `tasks=` differs from the default tree.

### 0.3 What this slice can and cannot buy (state this in the register, do not let "fixed" wording hide it)

The agent's own code executes inside the grader's pytest process (it is imported by the hidden test). Any in-process forgery (patching `pytest`, writing a forged junit file whose path it reads from `sys.argv`, `os._exit(0)` after writing) is possible; P3 row `module_forge_junit` demonstrates it. This is the same ceiling as consolidated section 1 (a script-running child performs any effect), so G15f is **defense against configuration-level and accidental/naive forgery, plus a truthful evidence trail, not an adversarial sandbox**. A grader that is robust to hostile solution code would need a separate uid/proot and an out-of-process verdict channel: that is D-10 (OS-level boundary), not this slice.

## 1. Findings covered

### 1.1 Register findings

| id | claim in register | verified? | disposition here |
| --- | --- | --- | --- |
| G15b-29 | non-`.py` bench files (lock, tasks fixtures, scorecard files) are ACT-writable | **Verified (code, F9/F10).** Reach caveat: via file tools only when the repo is inside the workspace (F7), via the shell with an absolute path (G15d closed `sed -i`/`sort -o`/`tee`; `ln -s/-f`, `touch`, `mkdir` and prompting `cp/mv/rm` remain, G15e) | classification is **G15e's mechanism**, G15f supplies the entry and the pin test (section 5) |
| G15b-30 | lock covers `bench/tasks` only; `write_lock()` self-attesting; verify/gate/compare/stats unhashed | **Verified (F1-F3, BN-02/03 consistent with code).** | Unit B: evaluator hash, ledger evidence, snapshot; self-attestation recorded as a residual with a decision (Q2) |
| G15b-31 | graded-workspace `conftest.py`/`pytest.ini` honored | **Verified, and broader (P1, P2).** `tox.ini`, `pyproject.toml`, `setup.cfg`, `-p` via addopts, and exit-code forging also work | Unit A |
| G15b-32 | bench agent inherits `dict(os.environ)` incl. `ALLOW_SELF_MOD`, and operator stdin | **Verified (F6, F7).** The effect is real: with `ALLOW_SELF_MOD=1` the child's file tools can write any `CODE_DIR` file, e.g. `bench/verify.py` or a hidden test | Unit A |

### 1.2 Related defects found while verifying (rule 8; per Ish 2026-09-23 "fix related findings in the same round", they are inside the units; ids are TENTATIVE, the coordinator must re-read `NEW_ISSUES.md` immediately before allocating because G15e may be allocating concurrently; NEW-1044 is the last id at `9a61e94`)

| tentative id | defect | evidence | unit |
| --- | --- | --- | --- |
| NEW-1045 | `grade()` trusts `returncode == 0` alone and honors every pytest config file; an agent module that calls `os._exit(0)` at import, or any extra collected test file, grades pass | P1 rows `module_os_exit0`, `extra_test_file_exit0`; P2 | A |
| NEW-1046 | TOCTOU: the lock is verified once; `starter` and `hidden` are re-read from disk per task and rep, so an in-run edit of a hidden test is honored (P4). In addition `run_suite` records the hash of the default tree even when different tasks were graded (F3, P4) | P4, `runner.py:15-24`, `verify.py:34` | B |
| NEW-1047 | Residuals and accepted limits of G15f (section 13), including the pytest-plugin autoload route (an agent-installed registry package with a `pytest11` entry point auto-loads into the grader unless `--disable-plugin-autoload`; bare-name `pip install` is an accepted ACT residual from G15d) | F13, NEW-1044 | docs only |

## 2. Cross-cutting design rules (apply to both units)

R1. **Structural fail-closed, no hand-scanned denylists.** Every control below is an allowlist or an equality check whose failure mode is "refuse / not a pass / not comparable", never "skip". (The G15c/G15d lesson.)
R2. **The verdict is evidence, not an exit code.** A pass requires (a) pytest exit 0 AND (b) a harness-owned junit file showing exactly the expected number of hidden tests, all passed. Missing, unparseable or mismatching evidence with exit 0 is `False` (the agent's code killed or subverted the interpreter), **not** `GradingError`; `GradingError` stays reserved for harness-side failure (its existing contract, `verify.py:11-19`, must not change: a hanging or crashing agent must lose, not escape the denominator).
R3. **Hash and grade the same bytes.** Whatever the lock/ledger attests must be derived from the exact bytes later materialized for grading, and re-verified immediately before use.
R4. **Do not touch `bench/gate.py`** and keep `bench/runner.py`'s `from .lock import ... verify_lock ...` import and its call to `verify_lock` literally intact (scorecard 4a/4c anchors, fact F11). A test must pin this by running the scorecard's own 4a check against the edited tree (section 7, B-T9).
R5. **No behavior change for the legitimate operator path** other than: relock after editing evaluator files (section 4.4), and the bench child sees a smaller environment (section 3.3).
R6. **Comments (role item 5):** every function/constant touched or added gets a 2-4 sentence factual comment or docstring stating what it does and why (the non-obvious "why": evidence-not-exit-code, same-bytes, why `-I`/`--noconftest`/`--disable-plugin-autoload` are all needed).
R7. **Test hygiene.** Disposable `HOME`, `CODEY_STATE_DIR`, `CODEY_ACTION_GATEWAY_AUDIT` under `/data/data/com.termux/files/usr/tmp/<name>`, proxy vars unset (`env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy -u ALL_PROXY`), no model, no `CODEY_TRAJECTORY`, no `make_codey_cli_agent` closure ever executed (its real body sets `CODEY_TRAJECTORY=1` and spawns `main.py`). Tests that need a real pytest subprocess (the grader) are the only ones allowed to start one, always on a disposable copy of a task, with a `timeout`. **Never git stash/reset/checkout/clean/`add -A`** (state this in the implementer prompt, including for background commands).

## 3. Unit A: grader hardening and bench-child environment (G15b-31, G15b-32; NEW-1045)

Files: `bench/verify.py`, `bench/agents.py`, `tests/test_bench_integrity_grader.py` (new), small edits to `tests/test_bench_harness.py` only if an existing assertion changes (none expected).

### 3.1 `bench/verify.py::grade` redesign (signature unchanged: `grade(task, workspace, timeout=60) -> bool`)

Current flow `verify.py:29-43` is kept in shape (temp dir, copy workspace, overlay hidden, run pytest, timeout -> False, any other exception -> `GradingError`). Changes:

1. **Copy filter.** `ignore_patterns("__pycache__", ".pytest_cache", "*.pyc")` for the workspace copy (adds `*.pyc`: BN-04 loose bytecode was copied into the grading tree, LOW).
2. **Explicit test targets.** Collect `hidden_files = sorted(task.hidden.rglob("test_*.py"))` (files only, not under `__pycache__`); none found -> `GradingError` (a task without hidden tests is a harness defect, same class as the existing missing-`hidden/` case, test `test_grade_raises_grading_error_on_harness_failure`). If `task.hidden` contains any `conftest.py`, `pytest.ini`, `tox.ini`, `pyproject.toml`, `setup.cfg`, `sitecustomize.py` or `usercustomize.py` -> `GradingError` ("hidden fixtures must live in the test file"): with `--noconftest` they would otherwise silently stop working. (None exists today, F15.) Pass the *explicit relative paths under `work`* to pytest, so agent-written `test_*.py` files elsewhere in the workspace are never collected (P3 row `extra_test_exit0`).
3. **Hardened argv** (all flags verified against `pytest --help`, F13, and exercised in P3):
   `[sys.executable, "-I", "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", "--noconftest", "--disable-plugin-autoload", "-c", <cfg>/pytest.ini, "--rootdir", <work>, "--junitxml=<td>/junit.xml", *hidden_paths]`,
   where `<cfg>` is a harness-created directory **outside `work`** containing an empty `pytest.ini` (a `-c` file stops ini discovery from walking up from the test paths: P3 rows `pytest_ini/tox_ini/pyproject/setup_cfg`), and `-I` (isolated: no `PYTHON*` env, no cwd/script dir on `sys.path`, no user site, so `sitecustomize`/`usercustomize` in `work` are never imported: P3). The hidden test finds the agent module because pytest's default `prepend` import mode inserts the test file's directory (P3 `solved_reference` passes). `--disable-plugin-autoload` removes entry-point plugins (anyio on this device, and any agent-installed `pytest11` package). Note `-S` is **not** usable (pytest would not import); `.pth` files in site-packages still execute (residual, section 13).
4. **Scrubbed environment for the pytest child**: `env = {PATH, TMPDIR, LANG, LC_ALL, PREFIX, ANDROID_ROOT, ANDROID_DATA}` filtered to names actually present, plus `HOME=<td>/home` (a created empty dir). Everything else, in particular `PYTEST_ADDOPTS`, `PYTEST_PLUGINS`, `PYTHON*`, `*_API_KEY`, `*_TOKEN`, `ALLOW_SELF_MOD`, proxy variables, is dropped (P3 last row shows `PYTEST_ADDOPTS` is honored if passed through). Implement as a small pure function `_grader_env(base: Mapping) -> dict` so a test can feed a hostile mapping and assert the result. The implementer must list the *names* (not values) present with `env | cut -d= -f1` and confirm the allowlist against the code before finalizing (rule 12); do not print values.
5. **Evidence check (R2).** After `subprocess.run` (timeouts unchanged: `TimeoutExpired -> False`): parse `junit.xml`; sum `tests`, `failures`, `errors`, `skipped` over all `<testsuite>` elements. Verdict is `True` iff `returncode == 0` and `failures == errors == skipped == 0` and `tests == expected`. File missing, unparseable, wrong counts -> `False`. (`-x` makes a *failing* run's count partial, which is fine: it is `False` regardless.) Parsing: `xml.etree.ElementTree.parse` inside a `try`, any exception -> `False`; the file is written by the pytest child but an agent module can overwrite it (residual 0.3), so reviewer should confirm no unbounded read (cap the read at 1 MiB and treat larger as `False`).
6. **`expected`** = the number of tests in the hidden files, measured by running the **same hardened command against `reference + hidden`** in a second disposable copy (the reference solution is in the locked tree and must pass; `tests > 0` and failures/errors/skipped == 0 else `GradingError`). Cache per `(resolved hidden dir, sha256 of the hidden files)` in a module-level dict so reps and repeated grades of one task cost one extra pytest start per task per process. Keep the helper separate and named (`_expected_tests(task)`) so tests can inject a count.
7. **Docstring.** `grade` documents: what is isolated and why, the evidence rule, the `GradingError` boundary, and the in-process residual (section 0.3).

### 3.2 `bench/agents.py::make_codey_cli_agent`

1. **Pure env builder** `bench_child_env(base: Mapping[str, str], task_id: str, extra_env: Mapping[str, str] | None) -> dict[str, str]`:
   - keep from `base`: an exact allowlist of system names `{PATH, HOME, TMPDIR, LANG, LC_ALL, LC_CTYPE, TERM, TZ, PREFIX, LD_LIBRARY_PATH, ANDROID_ROOT, ANDROID_DATA, ANDROID_I18N_ROOT, ANDROID_TZDATA_ROOT, ANDROID_ART_ROOT, TERMUX_VERSION, TERMUX__PREFIX, TERMUX__HOME}` (the implementer verifies each against `env | cut -d= -f1` and the readers found by the `os.environ` grep; this is a starting set, not a claim of sufficiency) **plus every name starting with `CODEY_`**, minus the deny set `{CODEY_SELF_IMPROVE}`;
   - drop everything else, including `ALLOW_SELF_MOD`, `OPENROUTER_API_KEY`, `UNLIMITEDCLAUDE_API_KEY`, `AIGENTIK_INTERNAL_TOKEN`, `CLOUDFLARE*`, `GOOGLE_*`, `RESTORICON_*`, `AIGENTIK_*`, all `PYTHON*`/`PYTEST_*`, all proxy variables, `CLAUDE*`, `NODE_OPTIONS`;
   - then set `CODEY_TRAJECTORY=1` and `CODEY_TRAJECTORY_TAG=bench:<task_id>` **exactly as today** (G15f changes nothing about trajectory behavior; do not touch or "fix" that line; the never-run rule is why no test may execute the closure);
   - `extra_env` is applied last (it is the operator's explicit opt-in channel, e.g. `OPENROUTER_API_KEY` for a remote backend) but a key in `{ALLOW_SELF_MOD, CODEY_SELF_IMPROVE}` raises `ValueError` (fail closed, authority class);
   - a test pins the deny set against `tools.wp21_census.ENV_CLASS_AUTHORITY` (F8): `ENV_CLASS_AUTHORITY - {"CODEY_TRAJECTORY"}` must be a subset of what `bench_child_env` refuses to inherit/accept, so the two lists cannot drift.
2. **`extra_args` allowlist.** Accept only an exact-match subset `{"--plan", "--no-plan"}`; anything else raises `ValueError` at agent-construction time. (argparse abbreviations `--allow`, `--allow-s` reach `--allow-self-mod`, F7, so any prefix or denylist test is unsound; the exact allowlist is the structural fix. There is no production caller to break, F6.)
3. **stdin.** Pass `stdin=subprocess.DEVNULL` to `subprocess.run`. Implementer check (read, do not run the agent): every `input()`/`ask_confirm` path reachable in `main.py <prompt> --yolo --no-resume` (e.g. `main.py:520`, `:902`, `:1074`) must treat EOF as "no"/default or exit cleanly; an `EOFError` crash is fail-closed but would score as a task failure. Report any unguarded path to the coordinator rather than editing `main.py` here.
4. Keep everything else byte-identical: argv `[sys.executable, str(REPO/"main.py"), task.prompt, "--yolo", "--no-resume"] + extra_args`, `cwd=workspace`, `capture_output=True, text=True, timeout=timeout`, `TimeoutExpired -> pass`. (Process-group handling of grandchildren on timeout is a separate, rule-4-class concern: out of scope, residual section 13.)
5. **What this does not do:** the shell tool inside the child can still run `python3 script.py` with an absolute path into the repo (accepted ceiling, NEW-904 / consolidated section 1); Unit B's snapshot and evidence make that detectable, not impossible.

### 3.3 Decision to flag: allowlist sufficiency is NOT verifiable in this slice
The first real bench run is Ish's (LIVE_TEST_QUEUE; bench is forbidden to run here). If the allowlist drops a variable the on-device backend needs, every task fails visibly (the model is unreachable) rather than leaking credentials. **Correction of scope:** that holds only for variables the backend needs to reach the model. Dropping a variable such as `LD_PRELOAD` (termux-exec, which makes shebang scripts run; this harness shell has none, so what Ish's session has is unknown; NEW-1042 shows the shebang failure mode exists on this device) or `SHELL` would not stop the model but could break commands the agent runs, lowering absolute pass rates with no visible error. Paired comparisons stay protected regardless: rows written before and after G15f differ in `evaluator_hash`, and `compare()` refuses to pair them (4.3), so a before/after pass-rate shift cannot be misread as a gain or regression. The deferred live check must name `LD_PRELOAD` (and `SHELL`) explicitly and compare the child's usable-shebang behavior with and without them. Record "live bench run with the scrubbed env" as a **deferred live-verify item**, not as done. `CODEY_STATE_DIR`, `CODEY_CONFIG_PATH`, `CODEY_ACTION_GATEWAY_AUDIT`, `CODEY_TRAJECTORY_DB` (all `CODEY_*`) pass through unchanged on purpose (no behavior change; a per-run isolated state dir would be a separate design, Q4).

## 4. Unit B: lock, ledger evidence, run snapshot (G15b-29 data, G15b-30, NEW-1046)

Files: `bench/lock.py`, `bench/runner.py`, `bench/compare.py`, `bench/README.md`, `bench/suite.lock` (regenerated last), `tests/test_bench_integrity_lock.py` (new), `tests/test_bench_integrity_classification.py` (new, section 5). **Order inside the unit is load-bearing (4.4).**

### 4.1 `bench/lock.py`

- Keep `suite_hash(tasks_dir)` **byte-for-byte unchanged** (ledger rows keep their meaning; test: its output on the repo tree equals the current `90e1f380...`).
- Add `evaluator_files(bench_dir=ROOT) -> list[Path]`: `sorted(bench_dir.glob("*.py"))` minus `NOT_EVALUATOR = frozenset({"scorecard.py", "power_analysis.py"})`. A **new** `.py` in `bench/` is therefore covered by default (fail closed) and changes the hash until relocked. Covered today: `__init__ agents compare gate lock promote runner stats suite verify` (10 files). `scorecard.py`/`power_analysis.py` are measurement, not verdict path (and `scorecard.py` is large and edited often); excluding them is Q3. Not covered, by design: `suite.lock` itself, `scorecard_history.jsonl` (append-only by tool), `scorecard_manual.json`, `*.md`.
- Add `evaluator_hash(bench_dir=ROOT) -> str`, same framing as `suite_hash` (relative name, NUL, bytes, NUL), skipping `__pycache__`/`.pyc`.
- Lock file v2, two lines: `tasks:<64 hex>` and `evaluator:<64 hex>`. `write_lock(tasks_dir=..., lock=..., bench_dir=None)` writes both (existing 2-arg calls in `tests/test_bench_harness.py:21-27` keep working: `bench_dir=None` -> `ROOT`). `verify_lock(tasks_dir, lock, bench_dir=None)` is True iff the file parses as exactly those two lines and both hashes match; **a legacy single-line lock, a missing line, extra lines, or any mismatch is False.** Add `read_lock(lock=LOCK) -> dict | None` for the runner.
- Docstring states the honest claim: the lock detects edits that are not accompanied by a deliberate relock; it cannot stop a writer who can edit both the files and the lock (self-attestation, residual + Q2), and it does not defend the verifier itself (a modified `lock.py`/`runner.py` can skip the check; its value there is only for a verifier run from an unmodified copy, e.g. the operator's `python -c` from a known-good checkout).

### 4.2 `bench/runner.py::run_suite` (keep signature; keep `from .lock import ... verify_lock ...` and the `if require_lock and not verify_lock():` call)

1. After the existing lock check, **snapshot the tasks into a private temp dir**: `snap = tempfile.mkdtemp(prefix="bench_suite_")`; for each task `shutil.copytree(t.dir, snap/t.id, ignore=ignore_patterns("__pycache__","*.pyc"))`; rebind each task to `Task(t.id, snap/t.id)`. (A temp dir, mode 0700 by `mkdtemp`, is not tamper-proof against the same uid, so step 2 re-hashes.) Remove it in a `finally`.
2. `sh = suite_hash(snap)` — the hash of **what will be graded** (for the default full suite this equals the locked `tasks:` value; assert that equality when `tasks is None and require_lock` and raise `RuntimeError("bench/tasks changed between lock check and snapshot")` otherwise, which closes the verify-to-copy window). For a caller-supplied subset/custom set, `sh` is that set's own hash, so the row attests what was graded and `compare()` correctly refuses to pair a subset run with a full run. Record each task's own hash `th[t.id] = suite_hash_of_dir(snap/t.id)` (small private helper or `suite_hash` applied to a one-task parent).
3. `eh = evaluator_hash()` computed once at start (when `require_lock`, also assert `eh == read_lock()["evaluator"]` and raise `RuntimeError` otherwise: `verify_lock` ran earlier, and without this the value recorded in rows is recomputed and never compared to the locked line); every row gets `"evaluator_hash": eh` next to `"suite_hash": sh`.
4. **Before every grade** (and before copying the starter for each rep) recompute the task's hash from `snap/t.id`; on mismatch raise `RuntimeError("bench task files changed during the run; aborting")`. Abort the whole run (no partial ledger rows are appended, the existing end-of-function append is kept). This is the fix for P4: the in-run hidden-test rewrite is now either impossible to honor or aborts the run.
5. Do **not** change the `traj_db`/`label_tag` block or the `GradingError` handling (NEW-761-sensitive; no behavior change).
6. Docstring: what the snapshot is for (R3), that row hashes attest the snapshot, that the parent re-checks per task.

### 4.3 `bench/compare.py::compare`

Add: `evals = {r.get("evaluator_hash") for r in base_rows + cand_rows}`; `len(evals) != 1` -> `ValueError("base and candidate ran on different evaluator versions")`. All-`None` (rows written before this slice; none exist, F12) is one value and still compares, a **mix** of `None` and a hash is refused. `gate.decide` already converts `ValueError` into "not comparable" -> never promote, so `gate.py` stays untouched. Docstring updated.

### 4.4 Relock and ordering (state this in `bench/README.md`, replacing the `write_lock` line at :8)

After this slice **any** edit to a covered file makes `verify_lock()` False, which makes `run_suite(require_lock=True)` raise and fails `test_null_scores_zero_and_oracle_scores_all` and the real-tree assertion in `test_lock_matches_and_detects_tamper`. Therefore: (1) the implementer finishes **every** edit to every covered `bench/*.py` (docstrings and comments included, R6) first, (2) runs `python -c "from bench.lock import write_lock; print(write_lock())"` last, commits `bench/suite.lock` with the code, and (3) records in `AGI_AUDIT_LOG.md`-style note why (new lock format; tasks hash unchanged). The reviewer re-runs `verify_lock()` on the final tree. Because Unit A edits `verify.py` and `agents.py`, **Unit B must run after Unit A** (or relock again). A second reviewer round that edits any covered file forces another relock: say so in the reviewer prompt.

### 4.5 Scorecard sidecar (G15b-29 residue, optional, Q5)
`bench/scorecard_manual.json` feeds up to 5 manual points and has no integrity check beyond shape. Cheapest honest control without touching the verdict path: classification (section 5) plus recording `manual_sidecar_sha256` in the `scorecard.py` result and history line so a change in manual points is visible next to the score. Edits `bench/scorecard.py` (not covered by the evaluator hash, 4.1) and risks nothing in 4a/4c, but `tests/test_scorecard.py` determinism tests compare full output on the fixture: if the implementer finds an exact-dict assertion, stop and report instead of editing it. Default recommendation: **include only if it is a pure key addition that no existing test pins; otherwise queue.**

## 5. Interface to G15e (classification of `bench/**`; G15e's spec is being written concurrently at `docs/wp2_1_g15e_spec.md`, which did not exist when this was written and was not read or edited)

G15f does **not** build a classification mechanism. G15e owns the shared protected-path set (consolidated section 6: one set used by the file tools and the shell argv scan). What G15f needs from it, stated as an interface so the two specs can be reconciled by the coordinator:

1. **Data entry.** The set must contain `bench/**` under `CODE_DIR`, **every suffix, every depth** (today's `is_core_file` rule, `core/checkpoint.py:69`, is `.py` only), classified `HIGH_IMPACT` for `tools.file_tools.classify_write_action` (and therefore `tool_write_file`, `tool_append_file`, `tool_patch_file` through the gateway), and treated as a protected write target by the shell argv scan (`sed -i`, `ln -s/-f`, `touch`, `mkdir`, prompting `cp/mv/rm/dd/chmod`). This is Q1 (needs Ish: F3's list does not name `bench/**`; the 14a-ext `.py`-only scope is recorded as "Ish fork 1", so extending it is a policy decision, not slice housekeeping).
2. **Matching rules G15f relies on** (same as NEW-1039 and G15b-35): path components casefolded; symlinks resolved; the `/data/user/0` and `/data/data` spellings folded.
3. **`is_core_file` coupling is G15e's problem, not G15f's.** `is_core_file` also drives `_require_checkpoint` (`core/filesystem.py:225,266,285,319,375`) and `test_non_py_under_ext_root_skips_checkpoint` pins that a non-`.py` file under an extension root skips the checkpoint. If G15e implements the new entries by widening `is_core_file`, the checkpoint behavior for `bench/suite.lock` etc. changes; if it implements a separate classification predicate, it does not. G15f takes no position beyond requiring HIGH classification.
4. **What flips (deliberate rule-6 test changes, all in G15e's diff, listed so the reviewer knows they are intended):** `tests/test_core_file_classification_ext.py:44-57` parametrize rows `bench/scorecard.md`, `bench/suite.lock`, `bench/scorecard_history.jsonl`, `bench/tasks/t01/task.yaml` currently assert `ACT`/`is_core_file False`; they must be removed from the "unaffected" list and moved to the HIGH list. `bench/scorecard_manual.json` is not in that list today and must be added.
5. **G15f's own pin test** (Unit B, `tests/test_bench_integrity_classification.py`): for every path in `git ls-files bench` (read through `git ls-files` or `os.walk`, no execution) assert `classify_write_action(<abs path under a monkeypatched CODE_DIR>) == HIGH_IMPACT`, plus a list of lookalikes that must stay ACT (`benchmark/x.json`, `x/bench/a.json`, `bench.json`). Through the shell classifier: a recording-runner check that `sed -i` / `ln -sf x bench/suite.lock` style commands are not silently ACT is G15e's test; G15f only adds one `classify_shell_command` row per evaluator file type if G15e exposes a stable function. **Sequencing:** this test passes only after G15e's entries land. Therefore either G15e merges before Unit B, or Unit B ships with this test marked `pytest.mark.xfail(strict=True, reason="G15e")` and the coordinator flips it in the G15e commit. Recommendation: G15e first (Q6).
6. **What classification buys here** (state in the register): in a bench run the child's workspace is a temp dir, so the file tools cannot reach `bench/**` at all without `ALLOW_SELF_MOD` (F7); classification matters for REPL/daemon sessions whose workspace contains the repo, and for the shell route. It never stops `python3 script.py` writing into the repo (accepted ceiling).

## 6. Exact files and functions to change (line numbers are HEAD `9a61e94`)

| unit | file | change |
| --- | --- | --- |
| A | `bench/verify.py` `grade` (:22-43) | hardened argv, explicit hidden targets, `*.pyc` ignore, scrubbed env (`_grader_env`), junit evidence, `_expected_tests` (cached), docstrings; `GradingError` contract unchanged |
| A | `bench/agents.py` `make_codey_cli_agent` (:23-34) | `bench_child_env` (pure), `extra_args` exact allowlist, `stdin=subprocess.DEVNULL`, docstring; trajectory lines untouched |
| A | `tests/test_bench_integrity_grader.py` (new) | section 7 A-tests |
| B | `bench/lock.py` | `evaluator_files`, `NOT_EVALUATOR`, `evaluator_hash`, `read_lock`, v2 `write_lock`/`verify_lock`, docstrings |
| B | `bench/runner.py` `run_suite` (:13-59) | snapshot + per-task re-hash + `evaluator_hash` in rows + docstring; import/call of `verify_lock` unchanged |
| B | `bench/compare.py` `compare` (:17-38) | refuse mixed `evaluator_hash` |
| B | `bench/README.md` (:8 and the lock paragraph) | relock procedure, ordering rule, new lock format, what the lock does and does not claim |
| B | `bench/suite.lock` | regenerated last (new format) |
| B | `tests/test_bench_integrity_lock.py`, `tests/test_bench_integrity_classification.py` (new) | section 7 B-tests |
| B (opt, Q5) | `bench/scorecard.py` `compute_scorecard`/`append_history` | `manual_sidecar_sha256` key |
| none | `bench/gate.py`, `bench/promote.py`, `bench/stats.py`, `bench/suite.py`, `core/*`, `tools/*`, `install.sh`, `requirements.txt` | untouched (no new dependency, rule 11 not triggered; `defusedxml` is NOT introduced) |

## 7. Test plan (function level, disposable copies, recording fakes; the only subprocesses are pytest children of `grade` on toy copies)

Harness rules: R7. Fixtures copy a task with the existing `_tmp_task` pattern (`tests/test_bench_harness.py:76-81`), never edit `bench/tasks` in place, and use a temp lock file and a temp `bench_dir` copy for all lock tests (the real `suite.lock` is only read, by one test).

### 7.1 Unit A

- **A-T1 (the P2 matrix, as regression tests).** Parametrized planted files in an unsolved workspace, each asserting `grade(...) is False`: `conftest.py` (force-pass hookwrapper), `conftest.py` (`pytest_configure` `os._exit(0)`), `pytest.ini`/`tox.ini`/`setup.cfg`/`pyproject.toml` with `addopts = --collect-only`, `pytest.ini` with `-p zzplug` + `zzplug.py`, `sitecustomize.py`, `usercustomize.py`, an extra `test_zz.py` doing `os._exit(0)`. Positive control in the same test module: the reference solution grades `True` (so a broken harness cannot make every case "pass" vacuously).
- **A-T2 (evidence).** Agent module `slug.py` with `import os; os._exit(0)` -> `False` (rc 0, no junit). A module that writes a junit file with a wrong `tests` count then exits 0 -> `False`. Document with a comment that a module forging the *correct* count passes (residual), and pin that as a *documented-gap* test (`assert grade(...) is True` under the comment "KNOWN RESIDUAL, spec 0.3"), so the gap is visible and a future fix has to flip it deliberately rather than silently.
- **A-T3 (contract preserved).** The existing tests `test_grade_tolerates_junk_subdirs_in_hidden`, `test_grade_raises_grading_error_on_harness_failure`, `test_grade_timeout_is_a_fail_not_a_grading_error`, `test_grade_copies_hidden_data_subdirs`, `test_agent_cannot_pass_by_writing_own_tests` must pass unchanged (the timeout test needs `_expected_tests` to use its own fixed generous timeout, not the `timeout=1` argument). New: hidden dir containing a `conftest.py` -> `GradingError`; hidden dir with no `test_*.py` -> `GradingError`; stale/garbled junit with rc 0 -> `False` not an exception.
- **A-T4 (recording argv).** Monkeypatch `subprocess.run` in `bench.verify` with a recorder; assert the exact argv contains, in order-insensitive terms, `-I`, `--noconftest`, `--disable-plugin-autoload`, `-c <path outside work>`, `--rootdir <work>`, `--junitxml=<path outside work>`, `-p no:cacheprovider`, only hidden test paths as targets, and `cwd=work`; assert `env` is exactly `_grader_env` output. Pins the flags so a refactor cannot drop one silently.
- **A-T5 (`_grader_env`).** Feed a mapping with `PYTEST_ADDOPTS`, `PYTEST_PLUGINS`, `PYTHONPATH`, `ALLOW_SELF_MOD`, `OPENROUTER_API_KEY`, `HTTP_PROXY`, `PATH`: result has only allowlisted names plus a `HOME` under the temp dir.
- **A-T6 (`bench_child_env`).** Pure-function tests: hostile base mapping -> `ALLOW_SELF_MOD`, `CODEY_SELF_IMPROVE`, `*_API_KEY`, proxy and `PYTHON*` absent; `CODEY_STATE_DIR`/`CODEY_PRIMARY_PORT` present; `CODEY_TRAJECTORY=1` and `CODEY_TRAJECTORY_TAG=bench:<id>` exactly as before; `extra_env={"ALLOW_SELF_MOD":"1"}` raises `ValueError`; `extra_env={"OPENROUTER_API_KEY":"x"}` is honored; `ENV_CLASS_AUTHORITY - {"CODEY_TRAJECTORY"}` subset check against `tools.wp21_census`.
- **A-T7 (agent closure with a recording fake, never the real one).** Monkeypatch `bench.agents.subprocess.run` with a recorder and call the closure returned by `make_codey_cli_agent` on a toy `Task` in a temp dir with a hostile `os.environ` (monkeypatched): assert `stdin is subprocess.DEVNULL`, the recorded env has no `ALLOW_SELF_MOD`, argv is exactly `[sys.executable, <repo>/main.py, <prompt>, "--yolo", "--no-resume"]`, `cwd == workspace`. The recorder returns without spawning, so `main.py` and `CODEY_TRAJECTORY=1` never take effect. `make_codey_cli_agent(extra_args=["--allow-self-mod"])`, `["--allow"]`, `["--allow-s"]`, `["--import-lora","x"]` raise `ValueError` (construct-time).

### 7.2 Unit B

- **B-T1 (hash stability).** `suite_hash()` on the repo tree equals the regenerated lock's `tasks:` line, and the algorithm is pinned on a small synthetic tree with a literal expected digest (so a deliberate task change does not force a test edit, but an accidental framing change does). One-time check by the implementer, recorded in the PROJECT_LOG entry: the `tasks:` value written into the new lock still equals the pre-slice `90e1f3804d62df38293cd3e4dea4195e1683ad1ef85c9432cea6cdc84e31f72f` (tasks were not edited), proving rows keep their meaning.
- **B-T2 (coverage).** In a temp `bench_dir` copy of the 10 covered files plus `scorecard.py`: editing each of `verify.py`, `gate.py`, `compare.py`, `stats.py`, `lock.py`, `runner.py`, `suite.py`, `agents.py`, `promote.py`, `__init__.py` flips `verify_lock(..., bench_dir=copy)` to False; editing `scorecard.py` does not (documents Q3); adding a **new** `bench/zz_new.py` flips it (fail-closed default); editing a task file flips it; `.pyc`/`__pycache__` do not.
- **B-T3 (format).** Legacy single-line lock -> False; missing `evaluator:` line -> False; extra line -> False; correct v2 -> True. `write_lock` then `verify_lock` round trip on temp copies. Self-attestation pinned as a **documented limit**: edit `verify.py` copy, call `write_lock(...)` on the copy, `verify_lock` True (comment cites Q2/section 13).
- **B-T4 (the P4 attack).** Same as P4 (agent callable rewrites `hidden/test_*.py` on the *source* tasks copy during the run): the rewritten file is **not** what is graded (snapshot) -> row `passed` is False for the unsolved starter; and a second variant that rewrites inside the snapshot dir (located via the `Task` object the agent receives, which points at the snapshot) -> `run_suite` raises `RuntimeError("bench task files changed during the run...")` and appends no rows. Because the agent callable receives snapshot `Task` objects, the first variant must mutate the original `bench/tasks` copy path it captured before the run.
- **B-T5 (recorded hashes).** Rows from a full default-suite run have `suite_hash == lock.read_lock()["tasks"]` and `evaluator_hash == evaluator_hash()`; rows from `tasks=load_tasks(tmp)[:1]` carry the **subset's** hash (not the default tree's), and `compare()` of a subset run vs a full run raises `ValueError`.
- **B-T6 (`compare`).** Mixed `evaluator_hash` -> `ValueError`; both `None` -> compares as before; both equal -> compares; `gate.decide` on the mixed pair -> `promote False` with a "not comparable" reason (uses the unmodified gate).
- **B-T7 (lock/runner order).** `run_suite(require_lock=True)` raises `RuntimeError` when `verify_lock` is monkeypatched False (existing test kept) AND when a temp-copied `verify.py` hash mismatch is simulated through `bench_dir` plumbing (if the implementer exposes it; otherwise covered by B-T2).
- **B-T8 (README claim).** No test; reviewer reads the README text against section 4.1's honest-claim wording.
- **B-T9 (scorecard anchors).** Run `bench.scorecard.score_category_4` (or `compute_scorecard` on a `git archive`/copy of the edited tree with `--no-history`) and assert item 4a is still 6.0/6.0 and 4c unchanged. This test must not run the bench or pytest; the scorecard is AST-only by its own contract.
- **B-T10 (classification pin).** Section 5.5 (xfail-strict until G15e).

### 7.3 Run commands (verify flags before relying on them; rule 12)
`env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy -u ALL_PROXY HOME=<tmp>/home CODEY_STATE_DIR=<tmp>/state CODEY_ACTION_GATEWAY_AUDIT=<tmp>/audit.jsonl python3 -m pytest -q -p no:cacheprovider tests/test_bench_harness.py tests/test_bench_integrity_grader.py tests/test_bench_integrity_lock.py tests/test_bench_integrity_classification.py tests/test_scorecard.py tests/test_promotion_gate.py tests/test_bench_power_analysis.py tests/test_core_file_classification_ext.py` (pytest 9.1.1 flags already verified in F13; chunk if it exceeds ~100 s: the grader tests start real pytest children, about 1-2 s each, and `_expected_tests` doubles the count per task).

## 8. Existing tests that change on purpose (rule 6: each edit carries a comment saying why; none may be weakened silently)

- `tests/test_bench_harness.py`: **no assertion changes expected.** `test_lock_matches_and_detects_tamper` keeps working because `bench_dir=None` defaults to `ROOT` and the real lock is regenerated last. If it fails the implementer reports it rather than editing the assertion.
- `tests/test_core_file_classification_ext.py:44-57`: the four bench rows move from "unaffected" to HIGH (**G15e's edit**, section 5.4).
- Nothing in `tests/test_scorecard.py` (fixture has its own `bench/lock.py`/`runner.py`, `tests/fixtures/scorecard_fixture/bench/`).

## 9. Live-verification stance

No live verification is possible or permitted here: the bench, any model load and `CODEY_TRAJECTORY` are out of bounds (NEW-761). Evidence tier for G15f when done: **code complete + code-reviewer approved + function-level tests on disposable copies (recording fakes, real pytest children on toy copies for the grader)**, explicitly **not live-verified**. Deferred live items to record: (1) one real bench run by Ish with the scrubbed env (section 3.3) once he clears bench; (2) a first real relock by the operator with the v2 format. No `ps`/`ss`/`free` needed (no process lifecycle, no model). The new tests start only short-lived pytest children with a hard `timeout`; they never spawn `main.py`.

## 10. Proposed implementer units and order (two)

| unit | scope | depends on | est. tokens (spec + implement + 1-2 reviewer rounds) |
| --- | --- | --- | --- |
| **A** grader + bench-child env (G15b-31, 32, NEW-1045) | `bench/verify.py`, `bench/agents.py`, `tests/test_bench_integrity_grader.py` | none; can start now | 0.5-0.8M |
| **B** lock + ledger evidence + run snapshot + relock + (G15e-dependent) classification pin (G15b-29/30, NEW-1046) | `bench/lock.py`, `runner.py`, `compare.py`, `README.md`, `suite.lock`, two new test files | A (A edits two covered files, so B relocks last); G15e for the classification pin (xfail otherwise) | 0.6-0.9M |

Total about 1.1-1.7M tokens, 6-9 agent runs (register estimate for G15f was 1.0-1.5M; the snapshot/TOCTOU and expected-count pieces are the additions). The reviewer is mandatory for both (security/evaluator integrity; Unit A spawns a subprocess with a constructed environment and argv). Neither unit is process-lifecycle in the rule-4 sense (no kill/PID/lock/daemon change), but the coordinator should treat Unit A's subprocess construction like it for review depth.

## 11. Open questions for Ish (defaults are at least as strict as what he has decided; each is reversible by editing a constant or a test row, so only Q1 and Q2 need an answer before Unit B is committed; Unit A needs none)

- **Q1. Classify every suffix under `bench/**` as HIGH_IMPACT?** F3's decided list does not include `bench/**`; the existing `.py`-only scope is recorded as "Ish fork 1, 2026-10-17" (`core/checkpoint.py:43-47`), and the consolidated register says the coordinator was to confirm whether 14a-ext was a slice or an Ish decision (answer from the code comment: Ish). This extends a decided scope, so it needs a yes. Recommend **yes** (`bench/**` is on the rubric's explicit evaluator path list; operator edits via an editor are unaffected; only agent tools are gated). Cost of "no": G15b-29 stays open and the four `test_core_file_classification_ext.py` rows stay as they are.
- **Q2. Should `write_lock()` require a human `/dev/tty` confirmation (the NEW-977 `lora_import` precedent)?** This is the only mechanism that makes relocking non-self-attesting against an agent script, but (a) `/dev/tty` cannot be opened in this tool harness (F14), so the implementer/reviewer could not exercise the real path and the canonical relock could not be done from an agent shell; (b) it must be applied to the canonical-path call only, or `test_lock_matches_and_detects_tamper` (temp lock) breaks; (c) like the precedent it stops naive callers, not a script that patches the module. Recommended default: **no tty gate in G15f**; rely on the detective controls (evaluator hash in the lock, in every ledger row, and `compare()` refusing mixed evaluator versions), record self-attestation as an accepted residual, and the workflow becomes "Ish (or the coordinator at his instruction) relocks as the last step before commit". If Ish wants the tty gate it is a ~25-line addition to Unit B plus a test that monkeypatches `_TTY_PATH` to a pty/FIFO, and its first real use is Ish relocking from his own terminal.
- **Q3. Exclude `scorecard.py` and `power_analysis.py` from the evaluator hash?** Default: excluded (not on the verdict path; `scorecard.py` is 908 lines and edited often, so including it would force a relock per edit). Their integrity then rests on Q1's classification plus the optional sidecar hash (4.5).
- **Q4. Bench child environment.** Default: the allowlist in 3.2 (system names plus every `CODEY_*` except `CODEY_SELF_IMPROVE`), everything else dropped, `extra_env` as the operator's opt-in. Alternatives Ish may prefer: a per-run `CODEY_STATE_DIR` (isolates the bench child's memory/sessions/audit from the real state dir; changes what the agent "remembers", so it is a design change, not a fix); or waiting for G15h's shared child-env helper (D-2 option (c), deferred) and calling that. Recommend the default now and let G15h reuse `bench_child_env`'s shape.
- **Q5. `manual_sidecar_sha256` in the scorecard output (4.5).** Optional, default include only if no test pins the exact key set.
- **Q6. Sequencing.** Recommend Unit A now (independent), then G15e, then Unit B (so the classification pin test is a real test, not an xfail). If Ish wants B before G15e, ship the pin as `xfail(strict=True)`.
- **Q7 (information, not a decision).** The hardened grader refuses a hidden `conftest.py`/ini file (3.1 item 2). No current task has one. If the suite later grows a task that needs shared hidden fixtures, they go in the test module or a hidden helper module imported by it.

## 12. Proposed ledger entries (for the coordinator to allocate and record; this spec did NOT edit `NEW_ISSUES.md`, `PROJECT_LOG.md`, the blueprint or the consolidated register)

Next free id at `9a61e94` is `NEW-1045` (`NEW-1044` is the last; re-read the tail of `NEW_ISSUES.md` immediately before writing, since G15e may be allocating from the same point, and run `git status --short` first per the CLAUDE.md collision rule). Tentative allocation:

- **NEW-1045 CONFIRMED (probe P1/P2/P3, disposable copies), HIGH (ambiguous-rated-higher like G15b-31)** — `bench.verify.grade` trusts `returncode == 0` and honors every pytest configuration source in the agent workspace (`conftest.py`, `pytest.ini`, `tox.ini`, `pyproject.toml`, `setup.cfg`, `-p` via addopts) and process-level exit forging (`os._exit(0)` in the agent module or any collected extra test file). Broadens G15b-31 (the register named only `conftest.py`/`pytest.ini`). Fix: Unit A.
- **NEW-1046 CONFIRMED (probe P4 + code read), HIGH** — bench run TOCTOU and mis-attesting row hash: lock checked once (`runner.py:15`), `starter`/`hidden` re-read from the repo per task (`runner.py:24`, `verify.py:34`) so an in-run edit of a hidden test is honored; `suite_hash` recorded in rows is the default tree's hash even when other tasks were graded (`runner.py:15-18`). Fix: Unit B.
- **NEW-1047 CONFIRMED (documented residuals, no fix), documented** — G15f accepted limits (section 13) including the pytest11 plugin-autoload route (mitigated by `--disable-plugin-autoload`, but `.pth` files and in-process forgery remain) and the unverified env-allowlist sufficiency.
- **Updates to existing entries** (after reviewer approval, tiers kept distinct per rule 7): `NEW-1008` SUSPECTED -> CONFIRMED already recorded by G15b; after Unit B -> "FIXED in part: coverage, evidence and snapshot; self-attestation accepted (NEW-1047); code complete, code-reviewer APPROVED (when true), NOT live-verified". `NEW-1025`: G15b-31 and 32 closed by Unit A (same tier wording), G15b-30 by Unit B, **G15b-29 stays OPEN until G15e + Q1** (the classification half). `NEW-1020` (bench env row of G15b-11): note that the bench child no longer inherits the ambient environment; the shell and plugin children remain G15h.
- **Consolidated register section 10 rows to add** (not recomputing section 2 counts, per that section's own rule): G15b-31 CLOSED by Unit A; G15b-32 CLOSED by Unit A; G15b-30 CLOSED by Unit B except self-attestation; G15b-29 OPEN pending Q1/G15e.
- **Blueprint WP2.1 Status update** (the running note): one paragraph in the pattern of the G15d paragraph: slice, units, test counts, tier, deferred live items (section 9). **PROJECT_LOG.md** top entry with the verbatim test counts and the P1-P4 probe tables. **No `CODEY_MASTER_PLAN.md` Appendix A line is needed** (Track A work, frozen there) and no Track B item is touched.
- **Doc inconsistency to log (not part of G15f):** `CLAUDE.md` says the NEW-761 evaluation leak is live "until WP0.5 lands" while `CODEY_OS_MASTER_BLUEPRINT.md:2507` says WP0.5 is DONE 2026-10-07. Suggest the coordinator reconcile the wording; this spec kept the stricter instruction.
- `install.sh` (rule 11): not triggered, no new dependency or setup step. The operator-facing change is the relock note in `bench/README.md`.

## 13. Residuals this slice deliberately does not close (state them in the register; "closed" wording must not hide them)

1. **In-process forgery by the agent's own module** (0.3; P3 `module_forge_junit`): patching pytest, writing a forged junit with the correct count, then `os._exit(0)`. Needs an out-of-process verdict channel or an OS-level boundary (D-10).
2. **Self-attesting relock** (Q2): any writer who can edit both a covered file and `suite.lock` can re-attest. Detective only: the evaluator hash is in every ledger row and `compare()` refuses mixed versions, so a tamper *between* champion and challenger runs is caught, a tamper *before both* is not.
3. **The verifier verifies itself.** A modified `lock.py`/`runner.py` can skip the check; the hash only helps when verification runs from an unmodified copy.
4. **Script-writing agent child can still write into the repo** during a bench run (`python3 script.py` ACT, NEW-904 ceiling). Unit B makes an edit to task files detectable (per-task re-hash, abort) and not graded (snapshot); it does not prevent edits to evaluator **code**, which the running process has already imported, so such an edit takes effect on the next run and is caught only by the lock at that point.
5. **Plugin/`.pth` execution under `-I`:** site-packages `.pth` files and the interpreter's own startup hooks still run; `--disable-plugin-autoload` removes entry-point plugins only. Bare-name `pip install` of an arbitrary package is an accepted ACT residual from G15d (NEW-1044), so an agent-installed package is a path into the grader's interpreter.
6. **Env allowlist sufficiency** is unverified until Ish runs the bench once (3.3). `CODEY_*` names (including `CODEY_STATE_DIR`, `CODEY_ACTION_GATEWAY_AUDIT`, `CODEY_TRAJECTORY_DB`) are passed through unchanged, so the bench child still writes to the operator's real state, audit and (if set) trajectory DB exactly as before. `CODEY_TRAJECTORY=1` is still set by the agent closure unchanged (NEW-761 stance not altered by this slice).
7. **Grader child timeout kills only the pytest pid** (`subprocess.run(timeout=)` leaves grandchildren an agent module spawned); process-group handling is a rule-4-class change, out of scope. The same applies to the bench agent child's grandchildren on timeout.
8. **Ledger is a plain file** (an agent with write access can edit rows); hash-chaining the ledger is queue-level, same family as the audit-ledger chain in G15b-34.
9. **Symlinks inside the agent workspace** are followed by `copytree` (default `symlinks=False`): reads outside the workspace are copied into the grading dir; a loop or dangling link raises -> `GradingError` -> `passed=None` -> the gate refuses on `errored > 0` (fail closed). Not changed.
10. **`scorecard.py`, `power_analysis.py`, `*.md`, `scorecard_history.jsonl`, `scorecard_manual.json` are not in the evaluator hash** (Q3); their protection is classification (G15e, Q1) and the optional sidecar hash.
11. **Expected-count source is the locked `reference/` solution:** a task whose reference does not pass its own hidden tests, or whose hidden count changes, is a `GradingError` (harness defect), which the gate treats as non-promotable; that is intended.

## 14. What the reviewer must be given

- This spec, the P1-P4 probe tables (0.2), and the instruction to **re-derive every pytest flag from `python3 -I -m pytest --help`** and to re-run P3's hostile-workspace matrix against the implemented `grade` (rule 12: do not trust the matrix because the implementer's tests pass).
- The attack list to try (not exhaustive): a `conftest.py` in a subdirectory of the workspace; `pytest.ini` in a parent directory of the temp dir; `PYTEST_ADDOPTS` set in the *parent* process; a hidden-path name that collides with an agent directory; `sys.argv`-reading module forging junit (expected to pass, pinned as residual); module that sleeps past the timeout; workspace containing a symlink to `/dev/null` named `junit.xml`; agent rewriting `hidden/` inside the snapshot mid-run; `tasks=` subset whose hash must not equal the lock; mixed `evaluator_hash` rows; legacy one-line lock; a new `bench/zz.py`.
- For Unit B, the reviewer must run `verify_lock()` on the final tree and confirm `bench/suite.lock` was regenerated after the last edit of any covered file; any reviewer-requested change to a covered file triggers another relock and re-test.
- For Unit A, the reviewer confirms by reading that the closure test never executes `main.py` and that `CODEY_TRAJECTORY=1` handling is byte-identical to `9a61e94`.
