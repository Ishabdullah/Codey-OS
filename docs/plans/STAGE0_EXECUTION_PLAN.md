# Stage 0 Execution Plan — APPROVED by Ish 2026-10-01

Prepared 2026-10-01 by the cloud orchestrator session, from a read of
`origin/main` @ `73d2a2c`.

## 0. Ish's decisions (2026-10-01)

1. Work split: **option (c)**. Cloud writes specs, code, tests and reviews;
   everything on the device (model loads, baseline, calibration, Colab auth) is
   done by Ish / the Termux agent.
2. Colab: Codey-OS must be able to **train itself via the Colab CLI with no human
   step**. Budget: **free tier only**, so no paid compute units, no `colab pay`,
   and a T4 (or CPU) GPU only.
3. S0.3: **keep backups until an explicit `--purge-backup`**. This overrides the
   `AGI_AUDIT_LOG.md` Phase 4.2 withdrawal; rule 6 applies, and the record gets
   corrected when S0.3 lands.
4. Plan and S0.1 prompt approved.
5. Ish has uncommitted work on `main` in Termux. When it reaches `origin/main`,
   the cloud session **merges** `main` into `codey-os-dev-v2` (never rebases).

## 1. Preconditions — met

| Check | Result |
|---|---|
| Branch `codey-os-dev-v2` on GitHub | Pushed by Ish, at `73d2a2c` (= `main`) |
| Tag `rollback/2026-09-30-pre-dev-v2` | Pushed by Ish, at `73d2a2c` |
| `docs/plans/` | This file and `CODEY_OS_AGENT_HANDOFF.md` committed. **The audit, v1 plan and v2 plan files are still only on Ish's phone**; tasks that cite them wait until they're added. |

**Rollback note (correction to handoff §0.1):** the handoff's restore command
`git checkout main && git reset --hard rollback/...` would throw away any commits
made to `main` *after* the tag, including Ish's in-progress Termux work once it is
pushed. Dev work never lands on `main` without approval, so `main` itself never
needs that reset. To abandon the program, delete or ignore `codey-os-dev-v2`.
Use the tag only to inspect the pre-program state.

**Colab CLI status:** the install on Ish's phone is broken
(`ModuleNotFoundError: colab_cli.cli`), most likely because a Termux Python
upgrade orphaned the venv. Official package `google-colab-cli` 0.7.4 needs
Python >=3.12 and pulls `pydantic` (compiled `pydantic-core`). The fix
instructions were given to Ish. **Open question:** whether the CLI can provision
runtimes on a free-tier account at all. Its docs say runtimes are provisioned
"based on your active Colab plan", so this must be tested on the device with
`colab run` (CPU first) before S0.9 implementation starts. If free tier is
refused, the fallback is Kaggle (free GPU quota, official `kaggle` CLI pushes and
runs notebooks headlessly).

## 2. Handoff findings re-verified against `73d2a2c`

| Task | Handoff claim | Current code | Verdict |
|---|---|---|---|
| S0.1 | `_MAX_ARGS`=2000, `_MAX_RESULT`=1000, `...[truncated]` reaches export | `core/trajectory.py:21-22,63,218`; `finetune_prep.py:122,139` | **Confirmed** |
| S0.2 | `--import-lora` swaps with no gate check | `main.py:2086-2093` → `core/lora_import.py:559` `import_lora_adapter`; no `GateDecision`/`experiments.jsonl` lookup in that file | **Confirmed** |
| S0.3 | `rollback_to_backup` unlinks backup | `lora_import.py:513` | Confirmed, but **conflict**: `AGI_AUDIT_LOG.md` (Phase 4.2) explicitly *withdrew* this as intended behavior. The handoff reopens it, so Ish must decide. |
| S0.4 | bench agent runs `--yolo` near `hidden/`/`reference/` | `bench/agents.py:29` uses `--yolo`; `runner.py:22-24` copies only `starter` into a temp dir, but the repo (with `hidden/`) stays readable by absolute path | **Confirmed (partly mitigated)** |
| S0.5 | Docs drift | `MODEL_COMPARISON.md:20-21` (7B/1.5B); `telemetry/recorders.py:6` "dead code"; README `:16,103,152,176` (5-tier/5-agent) | **Confirmed** (wiring of recorders not yet re-checked) |
| S0.7 | gate = 0 regressions, 8 tasks | `bench/gate.py:10` `max_regressions: 0`, `min_pairs: 30`; 8 tasks t01–t08 | **Confirmed** |
| §5 | battery %/charging may need Termux:API | Already present: `resource_gate.py:787-812` → `core/sysmon.read_battery_status` | **Handoff wrong: already exists, reuse it** |
| §6/S0.9 | "No Colab CLI verified" | Official `google-colab-cli` (Google, June 2026) exists: `colab new/exec/run/upload/download/usage/stop`, Linux/macOS, auth `adc` or `oauth2`. Nothing in the repo uses it yet. | **Exists, but untested on Termux** |

### Cloud baseline (before any change, `73d2a2c`, `python -m pytest tests -q`)

2873 passed, 0 failed (x86 Python 3.11, cloud). Running pytest from the repo root
instead of `tests/` collects `bench/tasks/*/hidden/` tests, which then fail on
import by design. That root run also leaves `__pycache__/` inside `hidden/`.

**New finding (to log as NEW-### once on the branch):** `bench/verify.py:17-18`
`shutil.copy2`'s every entry of `hidden/`, so any subdirectory (e.g. a stray
`__pycache__`) raises `IsADirectoryError`. `grade()` swallows that and returns
False, which silently scores every task as failed, even for the oracle agent.
Reproduced here. Fix belongs in S0.4 (evaluator hardening).

## 3. Ish's new direction: autonomous self-training via Colab CLI

This conflicts with handoff §9 ("Colab cost/credential steps → escalate").
Reconciliation (approved; budget = free tier):

- **Autonomous:** dataset export, upload, `colab run --gpu <capped tier>`,
  checkpoint download, manifest write, bench eval of the candidate.
- **Hard limits in config, which the agent cannot edit (Gateway-owned):** free
  tier only (`colab pay` never called; launch refused if `colab usage` shows a
  paid balance would be consumed), GPU tier capped at T4, max runs/day (default
  1, tunable), Run Policy (on charge for downloads and evals).
- **Still gated, never autonomous:** live model swap. It requires an approving
  `GateDecision` (S0.2). That keeps training autonomous but adoption verified,
  which matches CLAUDE.md rule 1.
- **Credentials** stay in Termux (`~/.config/gcloud` or the CLI's OAuth file),
  never in the repo, and never sent to Playground or peers.

## 4. Proposed order (dependency-driven, safest first)

1. **S0.5 docs drift**: no runtime change; warm-up.
2. **S0.1 trajectory fidelity**: data layer; behind the existing `CODEY_TRAJECTORY` flag.
3. **S0.2 gate before swap**: must land before any autonomous training (§3).
4. **S0.3 backup retention**: approved (keep until `--purge-backup`); rule 4 reviewer required.
5. **S0.4 evaluator protection**: needed before S0.6/S0.7 results mean anything.
6. **S0.6 bench v2 → S0.7 gate statistics**.
7. **S0.9 Colab CLI workflow** (expanded per §3): research is done; Ish verifies the CLI on Termux; implementation includes budget guard + manifests; dry run with `colab run` on CPU (no GPU spend).
8. **S0.10 Action Gateway + Run Policy**: the biggest piece; reuses `resource_gate` samplers.
9. **S0.11 dual grading**.
10. **S0.8 baseline**: run on the phone by the live-verifier, on charge. It goes last so it measures the final S0 harness. (The handoff put it at #8; running it before S0.10 would mean re-running it.)

## 5. Cloud vs phone split (option c)

| Who | Tasks |
|---|---|
| Cloud (this session) | Specs, code, unit tests, and reviews for S0.1–S0.7, S0.9 code, S0.10, S0.11. Pushes to `codey-os-dev-v2` only. |
| Ish / Termux agent | §0.1 tag/branch push, Colab CLI install + auth test, every model-loading or device check (S0.8, Run Policy calibration, S0.9 dry run, live-verify of S0.2/S0.3). |
| Rule | Only **one** writer on the branch at a time (CLAUDE.md "Working alongside another agent"). |

## 6. Risks

- **Concurrent agents** (Termux Claude, Antigravity) editing `PROJECT_LOG.md`/`NEW_ISSUES.md` → silent overwrite / duplicate NEW-ids. Mitigation: `git status` + fetch before every ledger write; findings go to a scratch file first.
- **Cloud tests ≠ device tests.** Cloud is x86 Python 3.x; the phone is aarch64 Termux. Anything touching `/proc`, battery or temp is verified on device only.
- **Autonomous Colab spend**: a bug could burn compute units. Mitigation: budget guard reads `colab usage`, plus a hard per-run cap, a kill file and dry-run-first.
- **Colab CLI on Termux** is officially "Linux" only and unproven on Android; `uv`/deps may need a native build. Ish must test it before S0.9 implementation.
- **S0.3 conflict** with the earlier audit decision: resolved by Ish (§0.3).
- **Free-tier Colab via CLI is unproven.** It may be refused or heavily
  rate-limited; the Kaggle fallback stays on the table.
- **Uncommitted Termux work on `main`.** The longer it stays unpushed, the bigger
  the eventual merge into `codey-os-dev-v2`. Ish pushes it as soon as it's
  stable; the cloud session merges `main` in before starting each new task.

## 7. Prompt for S0.1 (new context)

> Model: Sonnet 5.5, thinking medium, NEW context, branch `codey-os-dev-v2`.
> Read CLAUDE.md, `docs/plans/CODEY_OS_AGENT_HANDOFF.md` §S0.1, `core/trajectory.py`,
> `core/finetune_prep.py`, `tests/test_trajectory.py`, `tests/test_finetune_phase3.py`.
> Task: store full tool args/results for episodes (remove the 2000/1000 caps at
> record time; keep `record_teacher_trace`'s 20000 cap unchanged unless the spec
> says otherwise); truncate only at export; export skips any example containing a
> truncation marker; add a secret-scrubbing hook (pattern list in one place) and
> exact-duplicate dedup at export. Behind the existing `CODEY_TRAJECTORY` flag, fail-open.
> Tests: >8 KB `write_file` round-trips intact into the exported example; a
> marker-containing legacy row is excluded; a scrubbed secret never appears in output;
> duplicates collapse. Run `python -m pytest tests -q`, report the last 15 lines verbatim.
> Do not touch daemon lifecycle, `restoricon_core/`, or `resource_gate.py`.
