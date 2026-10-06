# CENSUS A4 — Evaluation, Gates, Tests, CI, Config, Deps, Observability

Read-only census of `/data/data/com.termux/files/home/Codey-OS` @ `main` `405df9cf`
(working tree as of 2026-10-06). Every claim cites `file:line`. No code was modified.

**Environment preamble (required disclosure):**
- `env | grep -i proxy` returned, verbatim:
  ```
  CLAUDE_CODE_PROXY_RESOLVES_HOSTS=true
  https_proxy=http://127.0.0.1:41245
  HTTPS_PROXY=http://127.0.0.1:41245
  HTTP_PROXY=http://127.0.0.1:41245
  http_proxy=http://127.0.0.1:41245
  ```
  **A proxy WAS set.** Per the known artifact, any urllib-loopback test failure
  observed in this session would be a false positive. The test run in §(e) was
  therefore executed with all four vars unset via `env -u`.
- `free -h` at start, verbatim:
  ```
                 total        used        free      shared  buff/cache   available
  Mem:            10Gi       5.8Gi       768Mi        47Mi       4.6Gi       5.0Gi
  Swap:           15Gi       2.0Gi        14Gi
  ```
- No model was loaded, no service started/stopped.

---

## (a) `bench/` inventory + evaluation-leakage risk

### Inventory — status IMPLEMENTED (harness), but never run against the real agent

8 modules + 8 tasks. `/usr/bin/find bench -type f` (excluding `__pycache__`):

| File | Lines | Role |
|---|---|---|
| `bench/suite.py` | 32 | `Task` dataclass; `load_tasks()` globs `tasks/<id>/` requiring `prompt.txt` (`bench/suite.py:30-32`) |
| `bench/lock.py` | 29 | sha256 over every task file; `verify_lock()` (`bench/lock.py:9-29`) |
| `bench/verify.py` | 24 | `grade()` — the single grading function |
| `bench/agents.py` | 34 | `null_agent`, `oracle_agent`, `make_codey_cli_agent` |
| `bench/runner.py` | 46 | `run_suite()` — appends JSONL ledger |
| `bench/stats.py` | — | McNemar exact + bootstrap CI |
| `bench/compare.py` | 31 | paired champion/challenger |
| `bench/gate.py` | 45 | the promotion gate |
| `bench/promote.py` | 28 | CLI, appends to `experiments.jsonl` |

**Tasks (8, all trivial):** `t01_slugify`, `t02_fizzbuzz`, `t03_fix_average`,
`t04_dedupe`, `t05_parse_kv`, `t06_stack`, `t07_fix_off_by_one`, `t08_roman`
(verified by executing `bench.suite.load_tasks()`). Layout per task:
`prompt.txt`, `starter/`, `hidden/`, `reference/`. Every `hidden/` dir contains
**exactly one** file — relevant to §(b).

**What `grade()` does** (`bench/verify.py:11-24`): copies the agent's workspace
into a fresh `TemporaryDirectory`, overwrites same-named files with the task's
`hidden/` tests, runs `pytest -q -x -p no:cacheprovider`, returns
`r.returncode == 0`. Wrapped in a bare `except Exception: return False`
(`bench/verify.py:23-24`) — **any** grader malfunction is indistinguishable from
an agent failure. This fail-closed choice is what makes the §(b) bug silent.

**Is the suite frozen? YES, and the lock is currently valid.** `bench/suite.lock`
contains `90e1f3804d62df38293cd3e4dea4195e1683ad1ef85c9432cea6cdc84e31f72f`;
I recomputed `bench.lock.suite_hash()` live and it matched, `verify_lock()` →
`True`. `run_suite()` refuses to run on a mismatch (`bench/runner.py:15-16`), and
`compare()` raises if base and candidate rows carry different `suite_hash`
(`bench/compare.py:18-20`). This is a genuinely well-built freeze.

**No results exist.** `ls bench/*.jsonl` → *No such file or directory*. Neither
`bench/results.jsonl` nor `bench/experiments.jsonl` has ever been written here.
Corroborated by the project's own record at `PROJECT_LOG.md:25`: a calibration
measured ~780-820 s per trivial task end-to-end, so the gate's 30-pair minimum
would cost **~13 hours of device time**; the one live attempt wrote to scratch
only, so **no champion baseline exists in any canonical ledger**.
⇒ The evaluator is PARTIAL: harness IMPLEMENTED, measurement never performed.

### Evaluation-LEAKAGE risk — CONFIRMED, and it is the headline finding

**Yes: the system can train on its own benchmark.** There is a complete,
unguarded three-hop path from the frozen benchmark into the fine-tuning dataset:

1. `bench/runner.py:32-35` — after grading, the runner labels the agent's
   trajectory episodes with the external verdict:
   ```python
   if traj_db:  # label the agent's episodes with the EXTERNAL grader verdict
       from core.trajectory import label_tag
       label_tag(f"bench:{t.id}", f"bench:{sh[:12]}", passed, since_ts=t0, path=traj_db)
   ```
   The tag is `bench:<task_id>`, the verifier string `bench:<suite_hash[:12]>`.
2. `core/trajectory.py:108-114` — `verified_episodes()` selects
   `WHERE verifier IS NOT NULL` (plus `AND passed=1`). **There is no tag or
   verifier predicate** — bench-labelled episodes are returned alongside any
   other externally-verified episode. Its docstring calls these "the only
   eligible fine-tune/eval data."
3. `core/finetune_prep.py:122-148` — `DatasetCurator.curate_verified()` calls
   `verified_episodes(path=path, only_passed=True)` (`:130`) and converts each
   row straight into a ShareGPT training example tagged `"verified": True`.

So the 8 frozen benchmark tasks become the training set, and a model fine-tuned
on them would then be graded by `bench.gate` on those same 8 tasks. The gate's
statistical machinery (McNemar, bootstrap CI, suite-hash pinning) is rigorous
but measures nothing meaningful once the candidate has memorised the suite.

**This is not accidental drift — it is the documented workflow.**
`AGI_AUDIT_LOG.md` (Phase 3 entry) prescribes exactly this sequence:
"No data exists yet: enable `CODEY_TRAJECTORY=1`, run the bench, label episodes."
That is an instruction to populate the fine-tune corpus *from the benchmark*.

**Not mitigated on the dev branch either.** `codey-os-dev-v2`'s new
`core/export_hygiene.py` (the natural home for such a filter) contains no
occurrence of `bench`, `tag`, or `verifier` — I grepped
`git show codey-os-dev-v2:core/export_hygiene.py` for all three and got zero
hits. It filters secrets, oversize markers and duplicates only.

**Partial countervailing evidence (reported for honesty):** the repo is
*aware* of the adoption hazard in prose — `core/finetune_prep.py:600-601` and
`:783-784` print "Do NOT adopt this adapter because training loss fell… require
an approving `python -m bench.promote` decision." But that is a printed string
(see §c), and it guards *adoption*, not *corpus construction*. It does nothing
about leakage.

**Mitigating structural facts:** `bench/` is not imported by any runtime module
(grep for `from bench`/`import bench` outside `bench/` hits only
`ccos/core/capability_optimizer.py:478`, `ccos/core/self_improve.py:6` (docstring),
`core/finetune_prep.py:601` (string), tests, and ledger prose). And
`CODEY_TRAJECTORY` is unset by default (`core/trajectory.py` `enabled()`), so no
trajectories are being recorded today. The leakage is **latent but by design**,
not currently firing.

---

## (b) `main` vs `codey-os-dev-v2` — bench diff

**Narrow answer (as scoped): `bench/` differs by exactly 3 lines in one file.**
`git diff --stat main codey-os-dev-v2 -- bench/` → `bench/verify.py | 5 +++--`.
Verbatim diff:

```diff
@@ -14,8 +14,9 @@ def grade(task: Task, workspace: Path, timeout: int = 60) -> bool:
         with tempfile.TemporaryDirectory(prefix="bench_grade_") as td:
             work = Path(td) / "w"
             shutil.copytree(workspace, work, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
-            for f in task.hidden.iterdir():  # hidden tests overwrite any agent-written file of same name
-                shutil.copy2(f, work / f.name)
+            # hidden tests (and any fixture subdirs) overwrite any agent-written file of same name
+            shutil.copytree(task.hidden, work, dirs_exist_ok=True,
+                            ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", "*.pyc"))
```

**What main is missing:** `main`'s `grade()` uses `shutil.copy2` over
`task.hidden.iterdir()`. `copy2` raises `IsADirectoryError` on a subdirectory,
which the bare `except Exception: return False` (`bench/verify.py:23-24`) converts
into `passed=False`.

**Severity: LATENT, not active — main grades correctly today.** All 8 current
`hidden/` dirs hold exactly one `.py` file each (verified by `find bench -type f`),
so `copy2` never meets a directory. The bug fires the moment anyone adds a task
whose `hidden/` has a fixture subdirectory, and when it fires it reports *every*
task as failed with no error surfaced. Do not report main as currently broken;
report it as a silent trap on suite growth.

**Wider answer (what matters more):** `97ad62d` is **not** the only unmerged
commit. `git log main..codey-os-dev-v2 --oneline`:
```
97ad62d S0.1: full-fidelity trajectories, export hygiene, bench grade() fix
8d1c37e Stage 0 kickoff: commit handoff + approved execution plan (docs only)
```
`97ad62d` carries 944 insertions across 11 files that `main` lacks, including a
**new `core/export_hygiene.py` sitting directly on the fine-tune export path** —
squarely in A4's scope. Its own commit message states: "Code-reviewer APPROVED
after 4 rounds. Not live-verified, not yet run on Termux." Per CLAUDE.md rule 7
that is code-complete + approved, tier 2 of 3.

---

## (c) Promotion gate / rollback / model registry

### Promotion gate — IMPLEMENTED, and genuinely conservative

`bench/gate.py:23-40` `decide()` requires **all** of: comparable rows (same
suite hash, via `compare()`), `n >= 30` paired results, candidate wins strictly
more pairs than champion, McNemar exact `p < 0.05`, bootstrap CI lower bound
`> 0`, and **zero** regressions (`max_regressions: 0`, `bench/gate.py:10`).
Failure accumulates reasons and `promote` is `not why` (`:40`) — fail-closed by
construction. `no_evaluator()` (`:43-45`) hard-refuses where no benchmark exists.
This is a correct, honest gate. It is the strongest piece of engineering in A4's
scope.

### Append-only ledger — IMPLEMENTED (mode `"a"`), but EMPTY

`bench/promote.py:21-22` opens the experiments file with `open(..., "a")` and
writes one JSON line per decision; `bench/runner.py:43` likewise (`# append-only`).
Caveat on the word "append-only": this is append-*mode*, not an append-only
guarantee — nothing is hash-chained, signed, or write-protected, and any process
with filesystem access can truncate or rewrite either file. As established in
§(a), **neither file exists yet**, so the ledger has zero entries.

### Rollback — **MISSING** for the self-improvement path

This is the leg of CLAUDE.md rule 1 that is not met in code.
`ccos/core/capability_optimizer.py:400-422` does set up the *materials* for a
rollback: it copies the candidate to `data/versions/<cap>/v<new>_<name>`
(`:397-400`), backs up the original to `v<old>_<name>` (`:403-405`), overwrites
the live implementation (`:409`), and records
`cap.metadata["previous_version"] = old_version` (`:422`).

**Nothing ever reads any of it.** I grepped
`previous_version|def rollback|def revert|versions/` across `ccos/`, `bench/`
and `core/` excluding `tests/`. The complete result set is three lines:
- `ccos/core/capability_optimizer.py:422` — the **write** of `previous_version`
- `core/checkpoint.py:184` — `def rollback(checkpoint_id)`, the agent's unrelated
  file-checkpoint system
- `core/lora_import.py:451` — `def rollback_to_backup(backup_path, model_variant)`,
  for LoRA adapter files

There is **no reader of `previous_version`, no restore path from
`data/versions/`, and no capability-level revert function anywhere.** Once
`compare_and_upgrade` overwrites a live capability implementation, the only
recovery is a human copying a file back by hand.

⇒ **Verdict: rule 1's required "candidate vs baseline on the frozen benchmark,
regression slice, append-only ledger, rollback" is 3-of-4 in code.** Rollback is
MISSING. (Mitigation, and the reason this is latent rather than live: the
deployment branch is currently unreachable in practice — see §i.)

### Model / adapter registry — MISSING

There is **no registry binding a model or adapter to a gate verdict.** The
`register_version` / `deprecate_version` calls at
`ccos/core/capability_optimizer.py:428-429` are a CCOS *capability* version
tracker, not a model registry.

For adapters specifically, the gate requirement is **DOCS-ONLY**:
`core/finetune_prep.py:601` and `:783-784` *print* the instruction to require an
approving `python -m bench.promote` decision before adopting an adapter. I then
grepped `core/lora_import.py` — the module that actually swaps an adapter — for
`gate|promote|bench`: **zero hits**. Nothing in the adapter-swap code path
consults a `GateDecision`. An adapter can be adopted with no gate verdict at all;
the only barrier is a human reading a printed warning.

### `CODEY_SELF_IMPROVE` kill switch — IMPLEMENTED and correctly wired

`ccos/core/self_improve.py:12-22`: `mode()` reads the env var, defaults `"off"`,
and treats unknown values as `off` (`:14`) — fail-safe. Enforced at:
`ccos/core/capability_optimizer.py:453` (`optimize()` early-returns `None`),
`:388-390` (`may_deploy()` check after gate approval),
`ccos/core/goal_engine.py:135`, `ccos/core/skill_recombiner.py:528`.
Double-gated correctly: `compare_and_upgrade` requires *both* an approving
`gate_decision` (`:378-385`) *and* `_si.may_deploy()` (`:386-390`).

Note `ccos/tests/conftest.py:40-44` sets `CODEY_SELF_IMPROVE=on` for CCOS tests
by default, with a `si_default` marker to opt out — so the CCOS suite does **not**
exercise the shipped default. Deliberate and documented, but worth knowing.

---

## (d) AGI audit plan reconciliation

Both files read in full. `AGI_AUDIT_PLAN.md` (7698 bytes), `AGI_AUDIT_LOG.md`
(12208 bytes). **These two documents are unusually honest** — they repeatedly
self-correct, withdraw overclaims under rule 6, and refuse to claim reviewer
approval that wasn't obtained. My reconciliation found the plan's claims
substantially *match* source. Specific checks:

| Plan claim | Source check | Verdict |
|---|---|---|
| 2.1 bench harness, 8 tasks, sha256 lock, null/oracle agents | `bench/` as inventoried in §(a); lock verified live | **CONFIRMED** |
| 2.1 "Not imported by runtime. Agent cannot write to it" | grep for `from bench`/`import bench` outside `bench/`: only `capability_optimizer.py:478` (a CCOS, non-runtime module), tests, and strings | **CONFIRMED** |
| 2.3 switch checked in optimizer, loop, goal engine, recombiner | `capability_optimizer.py:453`, `goal_engine.py:135`, `skill_recombiner.py:528` | **CONFIRMED** (3 of 4 seen directly) |
| 2.4 "fake `+5` removed; new_score = old_score" | `ccos/core/capability_optimizer.py:432-433`: `new_score = old_score` with comment "2.4: no fabricated bump" | **CONFIRMED** |
| 2.4 "optimizer cannot deploy anything today" | `capability_optimizer.py:476-481` passes `no_evaluator()`, which always refuses | **CONFIRMED** |
| 3.2 curator reads trajectory store, only verifier-graded | `core/finetune_prep.py:127-130` → `verified_episodes(only_passed=True)` | **CONFIRMED** (but see §a leakage) |
| Gate: ">=30 pairs, McNemar p<0.05, bootstrap CI lower bound >0, zero regressions" | `bench/gate.py:10,30-39` | **CONFIRMED** |
| Risk register: "Bench results not comparable across hardware → pin GGUF hash, sampler settings, suite version in the ledger" | `bench/runner.py:38-41` pins `suite_hash` and a free-form `meta` dict; GGUF hash and sampler settings are **not** structurally pinned — they'd have to be passed in `meta` by the caller, and no caller does | **PARTIAL / unmet** |

### The scorecard itself is MISSING — the baseline is unreproducible

This is a consequential gap, not a nitpick. `AGI_AUDIT_PLAN.md:9` cites "the
2026-09-30 source-level AGI alignment audit (score 18/100)" and says "Findings
are cited by section in that report." **That report is not in the repository.**
`find . -maxdepth 3 -iname "*agi*" -not -path "./.git/*"` returns exactly two
files: `AGI_AUDIT_LOG.md` and `AGI_AUDIT_PLAN.md`. I also grepped
`18/100|scorecard|/100` across all `*.md` (including the untracked
`CODEY_OS_MASTER_BLUEPRINT.md` and `docs/directives/`): the only hits are the two
prose citations (`AGI_AUDIT_PLAN.md:9`, `AGI_AUDIT_LOG.md:66`) and
`CLAUDE.md:121-122`.

**There is no itemised rubric anywhere.** Consequences: the 18/100 baseline
cannot be reproduced or audited; no one can compute a current score; and
CLAUDE.md rule 1's objective ("as close to the AGI-research alignment
scorecard's ceiling as engineering allows") references a document that does not
exist in the repo. Rule 1 also warns against "a number that was pushed up by
relabeling" — without a rubric there is no defence against exactly that.
`AGI_AUDIT_LOG.md:66` does list the audit's *key findings* in prose, which is
partial compensation, but it is not a scorecard.

### What has actually been done since 2026-09-30

`AGI_AUDIT_LOG.md`'s newest entry is dated **2026-09-30** — the file has not
been updated in the ~6 days since, despite `97ad62d` (dated 2026-10-01) being
explicitly AGI-track work ("S0.1", referencing `AGI_AUDIT_PLAN.md`). The AGI log
has drifted out of currency; `PROJECT_LOG.md` and `NEW_ISSUES.md` carry the newer
record instead (e.g. `NEW_ISSUES.md:19946-19947` documents NEW-731/733).

Phase status per `AGI_AUDIT_PLAN.md`'s own table: Phases 1-4 all
"Code-complete 2026-09-30", merged to `main` at `ef5c86d`, explicitly
"**NOT live-verified with the model**". Phase 4.2 withdrawn as not-a-defect under
rule 6 (`AGI_AUDIT_LOG.md`, Phase 4 entry) — I spot-checked this: the withdrawal
reasoning about `core/lora_import.py` consuming the backup after a successful
restore is consistent with `rollback_to_backup` existing at `:451`. Good
rule-6 discipline.

Flags `CODEY_TRAJECTORY`, `CODEY_SELF_IMPROVE`, `CODEY_USE_FIX_MEMORY` remain
unset everywhere (`PROJECT_LOG.md:1212`), so **none of Phases 2-4 changes runtime
behaviour today.** The honest summary: the AGI track built measurement
*machinery* and then never took a measurement.

---

## (e) Test inventory, coverage gaps, verbatim run output

### Inventory

- **197** `test_*.py` files total (`find tests ccos/tests -name "test_*.py"`):
  107 in `tests/*.py`, 15 in `ccos/tests/*.py`, remainder in `tests/security/`
  and `tests/test_restoricon_core/`.
- **2854** test functions (`grep -c "^\s*def test_\|^\s*async def test_"`, summed).
- Directories: `tests/`, `tests/security/`, `tests/test_restoricon_core/`,
  `ccos/tests/`.

**No pytest configuration exists at all.** `ls pytest.ini setup.cfg
pyproject.toml tox.ini conftest.py` → all five *No such file or directory*.
There is no root `conftest.py`, no `[tool.pytest]` section, no marker registry,
no `testpaths`, no coverage config. Markers are registered imperatively instead
(`ccos/tests/conftest.py:48` calls `config.addinivalue_line("markers", ...)`).
Practical effect: test invocation is entirely convention-dependent, nothing
pins the Python path or test discovery root, and there is no project-wide way to
deselect slow/device tests.

### Verbatim run output

**I did NOT run the full suite. Reasons, stated explicitly per rule 5:**
2854 tests; the project's own cloud baseline was 336 s (`AGI_AUDIT_LOG.md`
baseline section) so on-device would be far longer; `~686Mi`-class free RAM
(768Mi measured); `tests/test_loader_resource_gate.py` creates a ~2.74 GB sparse
placeholder model file (`AGI_AUDIT_LOG.md` item 1.2); `tests/test_restoricon_core/`
risks touching `~/.codeyOS/restoricon.db`, which the task forbids; and the
ambient proxy would produce the known false ~34-failure result.

I ran the **A4-scoped subset** with the proxy vars unset. Command:
```
env -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy \
python3 -m pytest tests/test_bench_harness.py tests/test_promotion_gate.py \
  tests/test_trajectory.py ccos/tests/test_improvement_loop.py -q -p no:cacheprovider
```
Verbatim output, complete:
```
..................................                                       [100%]
34 passed in 26.52s
```

I also ran `bench.lock.verify_lock()` and `bench.suite.load_tasks()` directly;
verbatim:
```
verify_lock: True
computed: 90e1f3804d62df38293cd3e4dea4195e1683ad1ef85c9432cea6cdc84e31f72f
tasks: 8 ['t01_slugify', 't02_fizzbuzz', 't03_fix_average', 't04_dedupe', 't05_parse_kv', 't06_stack', 't07_fix_off_by_one', 't08_roman']
```

### Coverage gaps

`ccos/core/` — **every** module name appears somewhere under `tests/` or
`ccos/tests/`. But name-presence is a weak proxy: `ccos/tests/` has only 15 files
for a 20+-module subsystem, and §(h) shows `telemetry_engine.py`'s only test is
`ccos/tests/test_telemetry.py` exercising a dormant subsystem.

`core/` modules with **no name match** anywhere in either suite (heuristic:
name-based grep, so treat as "likely untested", not proof):
```
core/dashboard_data.py
core/githelper.py
core/inference_openrouter.py
core/summarizer.py
core/symbolic_graph.py
core/sysmon.py
core/taskqueue.py
```
Most notable: **`core/symbolic_graph.py`** (the "Mentalese Engine", a
headline architectural component) and **`core/taskqueue.py`** (feeds the daemon's
background execution — a lifecycle-adjacent area that CLAUDE.md rule 4 flags as
this project's worst bug source).

Well-covered by contrast: the promotion gate (`tests/test_promotion_gate.py`, 10
tests incl. an assertion that runtime `core/`/`tools/`/`utils/` import none of
the self-improvement modules), the bench harness
(`tests/test_bench_harness.py`, 8 tests incl. null=0/8, oracle=8/8, tamper
detection, and A/A p=1.0), and telemetry (`tests/test_telemetry_*.py`, 5 files).

---

## (f) CI analysis — **MISSING entirely**

**There is no CI of any kind in this repository.** Nothing runs on push.

- `ls -laR .github/` contains exactly **one** file: `REPOSITORY_DESCRIPTION.md`
  (231 bytes). **There is no `.github/workflows/` directory at all.**
- `ls .gitlab-ci.yml .circleci Makefile .pre-commit-config.yaml .travis.yml` →
  all five *No such file or directory*.

So: not a stub — absent. The 2854-test suite is never executed automatically;
every run is manual and discretionary. Combined with §(e)'s finding that there
is no pytest config, there is no reproducible, declared way to run this project's
tests at all.

**Doc drift (rule 6 territory):** `CLAUDE.md`'s own repo map claims
`.github/   GitHub workflows + repo description`. The workflows half is false.
`install.sh:100` does `pkg install ... ruff`, so a linter is installed on-device,
but nothing automated invokes it.

---

## (g) Config, dependencies, `install.sh` currency

- `utils/config.py` — 838 lines, 35 `os.environ`/`getenv` references. It is the
  **single canonical owner of the telemetry root**, which is what links §(g) to
  §(h): `utils/config.py:789` defines `METRICS_DIR = CODEY_STATE_DIR / "metrics"`,
  preceded at `:786-788` by an explicit instruction — *"Do not hardcode
  `"metrics"` or `".codeyOS/metrics"` anywhere else; import […]"*. The on-disk
  layout inspected in §(h) is this constant resolved. Good discipline: one
  definition, a stated no-duplication rule, and the live `telemetry/` package
  consumes it rather than re-deriving the path.
- `requirements.txt` — 91 lines, heavily commented with Termux-specific install
  ordering (`requirements.txt:44-68`): `pkg install python-pyarrow python-pandas`
  must precede pip, `fsspec` pinned to `==2026.2.0` (`:73`) because datasets
  4.8.4 breaks on newer, `pyarrow`/`pandas` explicitly marked DO-NOT-pip-install
  on aarch64 (`:89-90`). This file is genuinely well-maintained.
- `install.sh` — 632 lines; system packages at `:100` (Termux),
  `:123/:126` (apt), `:131/:133` (dnf), `:138/:140` (pacman); pip install of
  `requirements.txt` at `:199`.

### Rule 11 violation — CONFIRMED: an ad-hoc on-device dependency

**`python_multipart` is imported at runtime, is installed on this device, and
appears in neither `requirements.txt` nor `install.sh`.**

- Import site: `restoricon_core/api/routes.py:2414` — `import python_multipart`,
  immediately followed by `parser = python_multipart.MultipartParser(boundary, callbacks)`
  at `:2415`. This is the multipart file-upload request path.
- **It is NOT guarded.** I inspected `routes.py:2380-2416` for `try:`/`except`
  around it; the only match in that window is the `import python_multipart` line
  itself. An `ImportError` here propagates.
- Installed on device: `pip list --format=freeze` contains
  `python-multipart==0.0.32`.
- Absent from `requirements.txt` (91 lines, no `multipart` match) and from
  `install.sh` (grep for `multipart` → no hits).

⇒ **A fresh clone running `install.sh` once would NOT get a fully working
system**, which is precisely what rule 11 requires. The file-upload route would
raise `ImportError` on first use. This is the exact failure mode rule 11 was
written to prevent: "installed ad hoc on the device without also being captured
in the script."

### Other imports cross-checked (all legitimate — reported to avoid false alarms)

I enumerated third-party imports across `core/ ccos/ tools/ utils/
restoricon_core/ bench/ pipeline/ prompts/ main.py` and resolved each:

| Module | Site | Verdict |
|---|---|---|
| `unsloth`, `trl`, `transformers` | `core/finetune_prep.py:410,441,442` | **Not real deps.** Inside generated Colab-notebook source *strings* (confirmed by reading `:405-415` and `:438-445` — surrounding lines are notebook cell text with `{model_loading_code}` f-string placeholders). Correctly absent from requirements. |
| `cv2` | `ccos/plugins/vision/camera_capture/camera.py:61` | Lazy, inside function; optional plugin |
| `fastembed`, `sentence_transformers` | `tools/kb_semantic.py:68,75`, `core/embeddings.py:64` | Lazy optional fallbacks; `requirements.txt:66-68` documents the deliberate exclusion (needs PyTorch, unavailable on Termux) |
| `psutil` | `core/sysmon.py:138,189`, `core/observability.py:22` | Lazy; `requirements.txt:34-35` documents deliberate exclusion with `/proc/` fallback |
| `pexpect` | `core/peer_shell.py:80,104` | Lazy, with `# noqa: F401` probe at `:80` |
| `llama_cpp` | `core/lora_import.py:204` | Lazy; `requirements.txt:23-24` deliberately commented out |
| `networkx`, `watchdog`, `hnswlib`, `reportlab`, `numpy`, `requests`, `rich` | various | Present in requirements ✓ |

So the dependency hygiene on the *missing* side is good overall —
`python_multipart` is the single real gap, and it is a genuine one.

### Unused / orphaned declared dependencies — 5 confirmed

I grepped every declared package's top-level import name across `core/ ccos/
tools/ utils/ restoricon_core/ pipeline/ bench/ telemetry/ prompts/ main.py`,
using both `import X` and `from X.`/`from X import` forms, and excluding
`core/preferences.py:103-113` — that file lists dep names inside a *regex
detection table* (`"typer": [r"import typer", r"from typer import"]`), which is
string data, not an import.

**Zero import sites anywhere in the repo:**

| Declared | Where declared | Note |
|---|---|---|
| `typer>=0.9.0` | `requirements.txt:76` | No CLI uses it; `bench/promote.py:14` and the rest use stdlib `argparse`, and the API is stdlib `http.server` |
| `tqdm>=4.65.0` | `requirements.txt:11` **and** `:77` (declared twice) | — |
| `filelock>=3.13.0` | `requirements.txt:10` **and** `:84` (declared twice) | Locking is done with a hand-rolled `.rotate.lock` (`~/.codeyOS/metrics/.rotate.lock`) instead |
| `pyyaml>=6.0` | `requirements.txt:9` **and** `:83` (declared twice) | No `import yaml` anywhere |
| `httpx>=0.27.0` | `requirements.txt:8` **and** `:78` (declared twice) | HTTP is done with `requests` (`ccos/plugins/crm/core_query/client.py:38`) and stdlib `urllib` |

Note four of the five are **declared twice** in the same file (once in the Core
block, once in the Pipeline block) — a sign the two halves of
`requirements.txt` were maintained independently.

**Deliberately-pinned transitives, NOT orphans** (reported so they aren't
mistaken for the above): `aiohttp`, `dill`, `xxhash`, `multiprocess`, `fsspec`,
`huggingface_hub`, `pyarrow`, `pandas` all have zero direct import sites but are
transitive deps of `datasets` (1 import site), pinned on purpose —
`requirements.txt:79` says so explicitly ("transitive via fsspec[http]/datasets")
and `:73` pins `fsspec==2026.2.0` for a documented compatibility break.

**Verified in use (checked specifically to avoid a false positive):** `rich` has
zero `import rich` hits but is used via submodule form — `core/display.py:8-9`
(`from rich import box`, `from rich.console import Console`),
`core/sysmon.py:21`. `google-cloud-storage` (`requirements.txt:91`) has 3 sites
and is used by the backup tests that `AGI_AUDIT_LOG.md`'s baseline run excluded.

Also worth noting the API server uses stdlib `http.server`
(`restoricon_core/api/server.py:13` — `from http.server import
BaseHTTPRequestHandler, ThreadingHTTPServer`), not FastAPI/uvicorn. That is
consistent with requirements and explains why `python_multipart` is hand-wired
rather than framework-provided.

---

## (h) Telemetry / observability — **two unrelated systems, one live, one dormant**

This is the single biggest architectural surprise in A4's scope, and it is
mis-described in CLAUDE.md.

### The LIVE system is the top-level `telemetry/` package — IMPLEMENTED

`telemetry/` is **not listed in CLAUDE.md's repo-structure map at all.** It is
~160 KB across 9 modules: `__init__.py`, `cli.py` (39938 B), `envelope.py`,
`provenance.py` (22206 B), `recorders.py` (32245 B), `rollup.py`, `rotate.py`,
`schema.py`, plus `schema/`.

**It is genuinely reachable and running.** `grep -rln "from telemetry\|import
telemetry"` across runtime dirs returns real production callers:
`core/inference_hybrid.py`, `core/plannd.py`, `core/daemon.py`,
`core/task_executor.py`, `core/loader_v2.py`, `restoricon_core/api/server.py`,
`restoricon_core/api/routes.py`, `tools/ensure_model_cli.py`, `main.py`.

**And it has real, current data on disk.** `~/.codeyOS/metrics/` layout
(read-only inspection):
```
~/.codeyOS/metrics/
├── .rotate.lock            (0 bytes, 2026-09-08)
├── model_digests.json      (521 B)
├── model_digests.node.json (248 B)
├── events/                 25 date-named dirs, 2026-09-03 … 2026-10-06
│   └── <YYYY-MM-DD>/provenance.<run_id>.jsonl
└── runs/                   250 files, <run_id>.json
```
Events are dated-directory-partitioned JSONL, one file per category per run.
Verbatim head of `runs/68a3f3a534ba4565.json`:
```json
{"schema_version":1,"schema_sha256":"8a45d9fc8c23","event_id":"57039896999549cf
a39a341e334f7f6c","run_id":"68a3f3a534ba4565","boot_id":"85304233-7aa7-40ea-ba9b
-7e36c4dd5fa0","seq":0,"ts_wall":1788472938.1931484,"ts_mono":66962.038842214,
"category":"provenance","event_type":"run_start","emitter":"codey-os.core-api",
"pid":14664,"correlation_id":null,"nulls":{"body.device_uptime_sec":"proc_uptime_
permission_denied","body.llama_build_info":"call_site_not_yet_tagged","body.llama
_server_argv":"call_site_not_yet_tagged","correlation_id":"correlation_id_not_yet
_available"},"body":{"run_id":"68a3f3a534…
```
Note the `nulls` map: every null carries a *reason* string. That is the
"honest-null invariant" the design doc describes
(`docs/telemetry_layer_design.md:822`) — **implemented as documented.** The
envelope fields (`schema_version`, `schema_sha256`, `run_id`, `boot_id`, `seq`,
`ts_wall`, `ts_mono`, `category`, `event_type`, `emitter`, `pid`,
`correlation_id`, `nulls`, `body`) match the doc's §2.0 shared-envelope spec.

### `docs/telemetry_layer_design.md` vs implementation — ACCURATE

1310 lines. It documents the `telemetry/` package, not the CCOS engine:
`:86` cites `telemetry/store.py`, `telemetry/envelope.py`, `telemetry/schema/`;
`:813-816` tabulates `envelope.py` (8 KiB record cap), `store.py` (bounded ring
buffer, background writer, `O_APPEND` JSONL, drop counting), `recorders.py`
(category A-G `record_*()` mapping `GateDecision`/`ResourceSnapshot`/llama-server
`timings`); `:196` specifies `ts_mono` as the sole duration basis, "never from
`ts_wall` deltas". Every file it names exists at the stated path, and the
on-disk envelope matches. Named tests exist too
(`tests/test_telemetry_envelope.py`, `test_telemetry_recorders.py`,
`test_telemetry_store.py`, `test_telemetry_t2_run_start.py`,
`test_telemetry_t10_cli_run_start.py`, `tests/test_loader_v2_telemetry.py`).
`:834` describes a JS emitter `telemetry.mjs` sharing the envelope — I did not
locate or verify that file; flagged as unverified, not as absent.

**Verdict: the telemetry design doc is one of the few docs here that has NOT
drifted.** Consistent with memory note "Telemetry rollout T0-T9 complete"
(code-complete + approved 2026-09-04, `f81af2f`), whose stated next step is a
live-verify cycle on T9 — still outstanding.

### `ccos/core/telemetry_engine.py` — **DORMANT**

728 lines. `grep -rln "telemetry_engine\|get_telemetry\|TelemetryEngine"
--include=*.py .` returns **exactly three** files:
```
./ccos/core/telemetry_engine.py   (itself)
./ccos/demo_telemetry.py          (demo script)
./ccos/tests/test_telemetry.py    (its own test)
```
**No production caller path exists.** Searched: all `*.py` repo-wide for the
class name, module name, and the `get_telemetry` accessor. ⇒ DORMANT.

**Correction made during this census (rule 6):** an earlier pass of mine read a
`goal_engine` grep hit in this file as evidence it calls the goal engine. It is
not. `grep -n "goal_engine" ccos/core/telemetry_engine.py` returns exactly one
line — `:550    def get_insights_for_goal_engine(self) -> List[Dict[str, Any]]:`
— a **method name**, not an import or call. So `telemetry_engine.py` offers an
API *for* the goal engine that the goal engine never consumes. The consequence
cuts the other way and is stronger: `ccos/core/goal_engine.py` has **no non-test
caller at all** (see §i).

Also checked and negative: `grep -ni "metrics" ccos/core/telemetry_engine.py`
returns **nothing**. This module does not touch `~/.codeyOS/metrics/` and does
not collide with the live `telemetry/` package's storage — the flat DORMANT
verdict holds without qualification.

**Net observability picture:** real telemetry exists and works, but 728 lines of
a second, parallel telemetry implementation sit dormant inside the CCOS layer,
and CLAUDE.md's map points readers at `ccos/core/telemetry_engine.py` while
omitting the `telemetry/` package that is actually doing the work.

---

## (i) DORMANT findings

Reachability method for each: repo-wide `grep -rln` on module name, class name,
and accessor function across all `*.py`, then exclusion of the module itself,
`tests/`, `ccos/tests/`, and `demo_*.py`.

| Target | Status | Evidence / what I searched |
|---|---|---|
| `ccos/core/telemetry_engine.py` (728 lines) | **DORMANT** | Only referents: itself, `ccos/demo_telemetry.py`, `ccos/tests/test_telemetry.py`. Searched `telemetry_engine`, `TelemetryEngine`, `get_telemetry`. |
| `bench/` as a whole | **DORMANT from runtime** (by design, correctly) | Only non-bench Python referents: `ccos/core/capability_optimizer.py:478` (`from bench.gate import no_evaluator`), `ccos/tests/test_improvement_loop.py:236`, `core/finetune_prep.py:601` (string). `tests/test_promotion_gate.py` asserts runtime `core/`/`tools/`/`utils/` import none of it. |
| `bench/promote.py` CLI | **DORMANT** | Entry point is `__main__` only (`bench/promote.py:27-28`); no caller, and its output file `bench/experiments.jsonl` has never been created. |
| Self-improvement cluster | **DORMANT** (closed loop, no external entry) | `capability_optimizer` ← only `ccos/core/auto_improvement_loop.py`; `skill_recombiner` ← only `ccos/core/goal_engine.py`; **`goal_engine` ← no non-test caller at all** (its sole other grep hit, `ccos/core/telemetry_engine.py:550`, is the method name `get_insights_for_goal_engine`, not a call — corrected mid-census, see §h); `auto_improvement_loop` ← only `ccos/core/lifecycle_manager.py`. The cluster references only itself plus `lifecycle_manager`. Additionally gated off by `CODEY_SELF_IMPROVE` default `off`. |
| `compare_and_upgrade`'s deployment branch (`capability_optimizer.py:392-440`) | **DORMANT / unreachable in practice** | Sole in-tree caller is `optimize()` (`:476-481`), which hardcodes `gate_decision=no_evaluator()` — guaranteed `promote=False`. The live-overwrite code at `:409` cannot execute via `optimize()`. **This is what makes the §(c) missing-rollback latent rather than live** — but the function is public and a future caller passing a real `GateDecision` reaches the unprotected overwrite. |
| `data/versions/` backup artifacts | **DORMANT (write-only)** | Written at `capability_optimizer.py:397-405`; no reader anywhere (grep `versions/` across `ccos/ bench/ core/` minus tests). |
| `cap.metadata["previous_version"]` | **DORMANT (write-only)** | Single occurrence repo-wide outside tests: the write at `capability_optimizer.py:422`. |
| `core/finetune_prep.py` notebook generation | **DOCS-ONLY / unverified** | `AGI_AUDIT_LOG.md` Phase 3 lists as UNVERIFIED: notebook never run, LoRA `target_modules` vs Qwen3.5 hybrid layers unconfirmed, llama.cpp Qwen3.5-LoRA conversion unconfirmed. |
| Adapter-adoption gate requirement | **DOCS-ONLY** | Printed at `core/finetune_prep.py:601,783-784`; `core/lora_import.py` grep for `gate|promote|bench` → zero hits. |
| Capability-level rollback | **MISSING** | See §(c). |
| Model/adapter registry | **MISSING** | See §(c). |
| CI | **MISSING** | See §(f). |
| AGI scorecard rubric | **MISSING** | See §(d). |

---

## (j) Open questions

1. **Leakage decision (highest priority).** Should `verified_episodes()` exclude
   `verifier LIKE 'bench:%'` / `tag LIKE 'bench:%'`, or should bench runs write
   to a separate trajectory DB? As it stands the documented workflow
   (`AGI_AUDIT_LOG.md` Phase 3) builds the fine-tune corpus *from* the eval set.
   A held-out split is also needed: 8 tasks cannot be both train and test.
   Needs Ish's call — it changes the prescribed Phase 3 workflow.
2. **Rollback for `compare_and_upgrade`.** Rule 1 names rollback as a gate
   requirement and there is none. Does Ish want it built before any
   `CODEY_SELF_IMPROVE=on` run, given the deployment branch is currently
   unreachable? Note this touches a rule-1 module and arguably rule 4.
3. **The missing scorecard.** Where is the 2026-09-30 audit report? Without its
   rubric the 18/100 baseline is unreproducible and progress toward rule 1's
   ceiling is unmeasurable. Should the rubric be reconstructed and committed?
4. **The ~13-hour measurement cost** (`PROJECT_LOG.md:25`) vs the gate's 30-pair
   minimum is the binding constraint on the whole AGI track. Options: more
   tasks but fewer reps, a cheaper proxy evaluator, or accepting that gated
   self-improvement is not reachable on-device. Product-direction question.
5. **Should `97ad62d`/`8d1c37e` merge to `main`?** The `grade()` fix is latent-bug
   insurance and `export_hygiene.py` is on the fine-tune export path. Approved,
   not live-verified.
6. **`ccos/core/telemetry_engine.py` (728 dormant lines)** — delete, or wire to
   the live `telemetry/` package? Two telemetry systems is a standing trap.
7. **CLAUDE.md map corrections (rule 6):** `.github/` has no workflows, and the
   live `telemetry/` package is absent from the map. Worth an explicit
   correction given rule 6 and the NEW-26/NEW-27 precedent on stale trees.
8. **No pytest config / no CI.** Should `pyproject.toml` + a workflow be added?
   `ruff` is already installed by `install.sh:100` but nothing runs it.
9. **`python_multipart`** must be added to `requirements.txt` and `install.sh`
   (rule 11). Should the import also be guarded, or is hard-failing the upload
   route acceptable?
10. **Unverified:** `telemetry.mjs` (`docs/telemetry_layer_design.md:834`) — I did
    not locate this file; whether it exists is open.

---

### Findings worth a `NEW_ISSUES.md` entry (rule 8)

Flagged for the coordinator; I did not write to any ledger (read-only census).

| # | Finding | Rating |
|---|---|---|
| 1 | Benchmark→fine-tune evaluation leakage: `bench/runner.py:32-35` → `core/trajectory.py:108-114` (no tag predicate) → `core/finetune_prep.py:127-130` | **Confirmed** |
| 2 | No capability-level rollback; `previous_version` and `data/versions/` are write-only (`ccos/core/capability_optimizer.py:397-422`); rule 1 requirement unmet | **Confirmed** |
| 3 | `python_multipart` imported unguarded at `restoricon_core/api/routes.py:2414`, installed on-device, absent from `requirements.txt` + `install.sh` — rule 11 | **Confirmed** |
| 4 | No CI anywhere; `.github/` has no `workflows/`; CLAUDE.md map claims otherwise | **Confirmed** |
| 5 | AGI scorecard rubric absent from repo; 18/100 unreproducible | **Confirmed** |
| 6 | `ccos/core/telemetry_engine.py` DORMANT (728 lines) while `telemetry/` is the live system | **Confirmed** |
| 7 | `bench/verify.py:17-18` on `main`: `copy2` over `iterdir()` fails every task if a `hidden/` subdir is added; masked by `except Exception: return False` (`:23-24`). Fixed on `codey-os-dev-v2` | **Confirmed (latent)** |
| 8 | No pytest config (`pytest.ini`/`pyproject.toml`/root `conftest.py` all absent) | **Confirmed** |
| 9 | `AGI_AUDIT_LOG.md` not updated since 2026-09-30 despite 2026-10-01 AGI-track work | **Confirmed** |
| 10 | `core/symbolic_graph.py`, `core/taskqueue.py` + 5 other `core/` modules have no name match in either suite | **Suspected** (name-based heuristic) |
| 11 | Adapter adoption gate is DOCS-ONLY: printed at `core/finetune_prep.py:601,783-784`; `core/lora_import.py` consults no gate | **Confirmed** |
| 12 | `telemetry/` package missing from CLAUDE.md repo map | **Confirmed** |
| 13 | 5 declared deps with zero import sites (`typer`, `tqdm`, `filelock`, `pyyaml`, `httpx`); 4 of them declared twice in `requirements.txt` (Core block + Pipeline block maintained independently) | **Confirmed** |
| 14 | `ccos/core/goal_engine.py` has no non-test caller at all; `ccos/core/telemetry_engine.py:550` exposes `get_insights_for_goal_engine()` that nothing consumes | **Confirmed** |
