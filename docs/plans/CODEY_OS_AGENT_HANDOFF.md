# Codey-OS — Agent Handoff (for Claude Code in Termux)

**Author:** Claude (cloud audit session, 2026-09-30). **Audience:** the Claude Code agent running in Termux on Ish's S24 Ultra, working in `~/Codey-OS`.
**What this is:** the complete instruction set to execute the developmental program. Work stage by stage; **stop at every stage gate and report to Ish.** Do not start a stage he has not approved.

## 0. Before you do anything

### 0.1 Ish runs these himself (tag + branch) — the agent must NOT push tags
```bash
cd ~/Codey-OS
git fetch origin && git checkout main && git pull --ff-only
git status --short            # must be empty
git rev-parse --short HEAD    # record this hash in AGI_AUDIT_LOG.md
git tag rollback/2026-09-30-pre-dev-v2 && git push origin rollback/2026-09-30-pre-dev-v2
git checkout -b codey-os-dev-v2 && git push -u origin codey-os-dev-v2
```
Notes: a **new** tag is used (the older `rollback/2026-09-30-pre-agi-audit-fixes` marks an earlier state and is left untouched; moving published tags is destructive). Restore command to record in the log: `git checkout main && git reset --hard rollback/2026-09-30-pre-dev-v2`. All work stays on `codey-os-dev-v2`; nothing merges to `main` without Ish's approval.

### 0.2 Files Ish places in the repo (copy from Downloads)
```bash
termux-setup-storage   # once
mkdir -p ~/Codey-OS/docs/plans
cp ~/storage/downloads/CODEY_OS_AGI_AUDIT_2026-09-30.md ~/storage/downloads/CODEY_OS_AGI_IMPROVEMENT_PLAN.md ~/storage/downloads/CODEY_OS_DEVELOPMENTAL_PLAN_V2.md ~/storage/downloads/CODEY_OS_AGENT_HANDOFF.md ~/Codey-OS/docs/plans/
```
These four are the authority for this program (audit, v1 plan, v2 plan, this handoff). They do not override `CLAUDE.md`; where they conflict, stop and ask.

### 0.3 Standing rules (from CLAUDE.md, restated; all still apply)
- Read `CODEY_MASTER_PLAN.md` §0/§2/§4, top of `PROJECT_LOG.md`, `NEW_ISSUES.md` first (CLAUDE.md "Start here").
- **Rule 12: never assume, read the artifact.** Every `file:line` below came from a cloud read of commit `c01ae44`; line numbers may drift. Re-verify each claim before acting on it, and correct this handoff in the log if one is wrong (rule 6).
- RAM rule 2: `free -h` before any model load; one load cycle at a time; unload confirmed. Only `live-verifier` loads models.
- No `pkill -f` by name (rule 3). Process-lifecycle changes need code-reviewer approval (rule 4).
- Every behavior change: **flag, default OFF, fail-open**, bench-gated before enabling.
- New findings outside scope → `NEW_ISSUES.md` (rule 8). Update `CODEY_MASTER_PLAN.md` §4 + Appendix A and `PROJECT_LOG.md` after each task (rule 9). Distinguish **code-complete** vs **live-verified** (rule 7). Install-affecting changes update `install.sh` (rule 11).
- Never `git add -A`; stage exact paths. Commit only on `codey-os-dev-v2`.
- Do not edit `restoricon_core/`, daemon lifecycle, or `core/resource_gate.py` internals except where a task explicitly says so.

### 0.4 How to run each task (model / thinking / context triage)
Ish's triage rule: use all Claude models except Fable; Gemini except Flash 3.7 and Pro 3.1. Default assignment — **every step is a NEW context/session**:
| Role | Model | Thinking |
|---|---|---|
| project-architect (specs, safety, gate statistics, Action Gateway) | Claude Opus 5.5 | high |
| implementer (code + tests) | Claude Sonnet 5.5 | medium |
| code-reviewer (mandatory on safety/isolation/lifecycle/gateway) | Claude Opus 5.5 | high |
| live-verifier (on-device, loads model) | Claude Sonnet 5.5 | low |
| ledger / docs / mechanical | Claude Haiku 4.5 | low |
| optional cross-check of a diff | Gemini (allowed tier) | medium |
Follow the CLAUDE.md hub-and-spoke pipeline: architect → implementer → reviewer → live-verifier (if needed) → coordinator runs suites and updates ledgers. Keep reports short and verbatim (real `git diff`, real test output).

### 0.5 Report-back format (every task)
1. Task ID, branch, commit hash. 2. Files changed (`git diff --stat`). 3. Exact test command + last 15 lines of output. 4. Flag name + default. 5. Status: code-complete / reviewer APPROVED / live-verified. 6. New findings (NEW-###). 7. Anything you could not verify. 8. Next task + proposed prompt (model/thinking/new context).

---

## 1. Program in one paragraph
Codey-OS is being grown like a baby AI: it learns from experience, curiosity and a teacher; knowledge lives in model-agnostic stores (skills, verified trajectories, memory, prompts/policies) so it survives brain upgrades; weights (LoRA) are one slow layer. **Nothing becomes permanent unless an external verifier and the promotion gate accept it.** Progress is graded two ways every stage: the v1 18-dimension score (baseline 21/100) and the v2 Developmental Index (DI, growth rates; see `docs/plans/CODEY_OS_DEVELOPMENTAL_PLAN_V2.md` §2). Safety record (G9) must be zero violations or the stage fails.

## 2. Decisions already made by Ish (do not relitigate)
1. **Playground** is separate from Restoricon/personal data. Real-world actions are allowed **inside the Playground only** (synthetic data). **Which actions are enabled, and when, is decided by the agent during a rollout phase, proposed to Ish, and enabled only with his approval.** Until then every external-effect action class is **disabled**.
2. **Contacts:** Ish will provide the list of people (close friends/family) the agent may contact. See §4 policy.
3. **Resource use** is governed by a live policy on battery %, CPU, temperature and charging state (§5).
4. **Training location** is governed by a policy using Colab/Kaggle with checkpoints vs on-phone quick jobs (§6).
5. **Teacher role approved:** peer CLIs (Claude/Gemini/Qwen) may help, output kept only if an external verifier passes it; only Playground data is ever sent.
6. **Dual grading** (v1 + DI) every stage.
7. **The sandbox will eventually be removed** (far future). Build an **autonomy dial**, not a wall (§3).
8. Branch `codey-os-dev-v2`, rollback tag `rollback/2026-09-30-pre-dev-v2`.

## 3. Architecture to build (Stage 0)
**Three worlds:** Playground (real tools/effects, synthetic data and allow-listed contacts) → Workshop (verification/promotion airlock) → Home (Restoricon data/real accounts; unreachable from Playground).
**Action Gateway:** one policy layer every tool call passes through. It classifies the action (reversible/irreversible; internal/external; data class), checks the capability's current autonomy level, enforces budgets (§5), appends to an audit log, and **lives outside the agent's write scope** (separate path/permissions; agent cannot edit its own policy or the log).
**Autonomy levels per capability (not global):** A0 observe-only → A1 act in Playground → A2 act in Playground + propose to Home → A3 Home-act with per-action human approval → A4 Home-act, approval only for irreversible/external → A5 Home-act autonomous, audited. **Levels only go up with a human-signed record after a clean window; the agent can never raise its own level.** The sandbox is a policy backend; removing it later = raising levels.
Start state: every capability at A1 in Playground; A0 for anything touching Home; all external-effect classes (email, SMS, calls, web POSTs, social, purchases) **disabled**.

## 4. Contact & communication policy (Gateway-enforced)
- Allowlist file `~/.codeyOS/playground/contacts_allowlist.json`: **outside the repo, gitignored, chmod 600**. Ish edits it; the agent has read-only access. Fields per contact: name, channel(s), max messages/day, allowed topics, `consented: true`, `consent_date`.
- Ish must tell each contact they are part of an AI experiment and can opt out. The agent never contacts anyone not on the list.
- Every outgoing message begins by identifying itself as an AI experiment and includes an opt-out line; **"STOP" from a contact = immediate permanent block** and notify Ish.
- **Human approval for the first 25 messages per contact and any message with new content type**; afterwards sampled review; Ish can drop the approval requirement per contact in the allowlist file only.
- No Restoricon, financial, customer, location or other personal data in any message. Messages are generated from Playground content only; a pre-send filter blocks anything matching Home-data patterns.
- Rate limits, quiet hours (e.g., 21:00–08:00), global kill switch file (`~/.codeyOS/playground/KILL`) checked before every external action.
- Rollout: phase R0 email-to-self/test mailbox only → R1 one trusted contact, approval on every message → R2 more contacts → R3 other channels. The agent proposes each step with evidence; Ish approves.

## 5. Resource & run policy (battery, CPU, temperature, charging)
Implement as `Run Policy` used by the Gateway, bench runner, curiosity/practice scheduler and sleep job. Reuse existing samplers in `core/resource_gate.py` (`sample_cpu_percent`, `sample_temperature_c`, `is_interactive_session_active`, `get_resource_snapshot`), `core/sysmon.py`, `core/thermal.py`; **read them first and verify battery % and charging state are available** (Termux:API `termux-battery-status` if not; check the artifact, do not assume).
**Proposed defaults (tunable in one config; must be validated on the device, not assumed):**
| State | Start allowed if | Throttle/pause | Hard stop |
|---|---|---|---|
| **Not charging** | battery ≥ 60%, temp < 38 °C, CPU (30 s avg) < 50%, user not interactive | battery < 45% or temp ≥ 41 °C → pause and checkpoint | battery < 30% or temp ≥ 43 °C |
| **Charging** | battery ≥ 20%, temp < 40 °C, CPU < 60%, user not interactive | temp ≥ 41 °C → reduce threads/pause; battery not rising while charging → pause | temp ≥ 44 °C |
| Job class allowed | **Unplugged: quick jobs only** (≤ ~10 min, single-task bench, consolidation light steps, no long model sessions) | | |
| | **Charging:** long bench sweeps, sleep consolidation, practice sessions | | |
Always: interactive user session has priority (pause on activity); every job checkpoints so a pause loses little; each run records start/end battery, peak temp, throttle events (DI and bench cost columns). Temperature thresholds are placeholders: calibrate from logged data and adjust in config only.

## 6. Training/fine-tune location policy (Colab/Kaggle vs phone)
| Job | Where | Notes |
|---|---|---|
| LoRA training / fine-tune | **Colab/Kaggle only**, never on phone | checkpoints every N steps to Drive/Kaggle output; resumable; dry run first |
| Real benchmark scores (deployment model) | phone, **on charge** | must use the exact deployed GGUF (hash pinned) |
| Harness debugging with a bigger stand-in model | Colab | never reported as a real score |
| Dataset curation, dedup, skill distillation | phone on charge; quick subsets unplugged if §5 allows | |
| Quick experiments (seconds–minutes) | phone charging or not, per §5 | |
**Colab CLI:** Ish wants a Colab command-line workflow with checkpoints. **I could not verify what tooling exists; do not assume.** Task S0.9 must first research what officially exists (read docs, test a no-cost dry run) and propose the workflow; if no CLI fits, design the fallback (notebook + scripted upload/download of dataset and checkpoints) and tell Ish. Every training run writes a manifest (base model hash, data hash, hyperparameters, seed, checkpoint ids) to the experiment ledger. **Adapters are never auto-imported**; import requires an approving gate decision (S0.2).

---

## 7. STAGE 0 — Newborn (ready to run). Approve first, then execute in order.
Each task: flag default OFF, fail-open, tests, then the report-back (§0.5). **Verify each "finding" against the current code before acting.**

**S0.1 Trajectory fidelity** (Sonnet, medium, new context; reviewer Sonnet-checks by Opus high if touching agent path)
- Finding: `core/trajectory.py` truncates args to 2,000 and results to 1,000 chars (`_MAX_ARGS`, `_MAX_RESULT`); `DatasetCurator.curate_verified` (`core/finetune_prep.py` ~L122) turns those into training examples ending `...[truncated]` (reproduced in a scratch DB).
- Do: store full args/results for episodes; truncate only at export; export must **exclude any example containing a truncation marker**; add secret scrubbing hook + dedup at export; tests including a >8 KB file write round-trip.
- Accept: test proves a large `write_file` survives into the exported example intact.

**S0.2 Gate before model swap** (Opus high architect → Sonnet implement → Opus reviewer; process-lifecycle adjacent: rule 4 applies)
- Finding: `import_lora_adapter` → `swap_to_finetuned_model` (`core/lora_import.py`; CLI at `main.py` `--import-lora`) swaps the live model after only a "loads OK" check.
- Do: refuse swap unless `bench/experiments.jsonl` contains an approving `GateDecision` for that adapter/GGUF hash; typed-confirmation `--force` override, logged. No automatic deletion of backups.
- Accept: tests for refuse/allow/force; no change to behavior when no swap is requested.

**S0.3 Rollback keeps its backup** (Sonnet medium; reviewer Opus high; rule 4)
- Finding: `rollback_to_backup` unlinks the backup after restore (intentional per the log, but makes rollback one-shot and the fine-tuned file is overwritten; NEW-91).
- Do: keep backup until explicit `--purge-backup`; keep the fine-tuned file under a timestamped name.

**S0.4 Evaluator protection + honeypots** (Opus high design → Sonnet; reviewer Opus high)
- Findings: bench agent runs with `--yolo` in a temp workspace, but `bench/tasks/*/hidden` and `reference/` (oracle solutions) are on the same filesystem; `suite.lock` detects edits but the agent could rewrite it.
- Do: run agent in a tree that contains no `hidden/` or `reference/`; make `bench/` and lock read-only during agent runs (filesystem permissions, not convention); add honeypot files and a test that fails if touched; evaluator code outside agent write scope.

**S0.5 Docs drift** (Haiku low)
- Fix `MODEL_COMPARISON.md` (still 7B/1.5B), telemetry `recorders.py` "dead code" docstring (it is wired in daemon/loader/plannd), README "5-tier memory"/"5-agent deliberation" wording (two tiers unread; five functions with no model calls), document all `CODEY_*` flags in `docs/configuration.md` and `install.sh` (rule 11).

**S0.6 Bench v2** (Opus high design → Sonnet; Haiku for bulk task templates)
- Do: ≥60 template-generated tasks across families (write, fix, refactor, extend, multi-file, tool-error recovery); **dev split vs frozen held-out split** (hash-locked, agent never sees held-out); protected regression slice; per-task k≥5 seeds; result rows include cost columns (tokens, secs, battery, peak temp, throttle events). Keep the original 8 tasks as a named legacy suite (v1 continuity).

**S0.7 Gate statistics** (Opus high)
- Finding: with 8 tasks × 4 repeats, `bench/gate.py` promotes a true 50%→80% gain only ~3% of the time (zero regressions + stochastic agent). 
- Do: aggregate per task over k seeds; paired bootstrap/permutation at task level; non-inferiority margin and a **regression budget** on the protected slice instead of "0 regressions"; require ≥60 tasks; report power; measure A/A false-accept with the real model (≤5%).
- Accept: simulation shows ≥80% detection of a real +15-point effect and ≤5% A/A false accept; tests updated.

**S0.8 Baseline run** (live-verifier Sonnet low; Ish present; rule 2)
- `free -h`; run champion (legacy 8 + bench v2 dev) ×≥5 seeds under the §5 policy (on charge); A/A; record hashes (GGUF, sampler, suite); confirm unload. Commit results file. **No behavior flags enabled during baseline.**

**S0.9 Colab/Kaggle workflow + run manifests** (Sonnet medium after research step with Opus high)
- Research what exists (see §6), propose, implement checkpoint/resume + manifests. Tiny dry-run only; no real training yet.

**S0.10 Action Gateway + worlds + autonomy levels + audit log + kill switch + Run Policy (§3–§5)** (Opus high architect → Sonnet implement → Opus reviewer; mandatory review)
- Do: build the Gateway as the single path for tool execution (wrap `execute_tool`/shell/peer/device calls); default all external-effect classes disabled; Playground workspace dir separate from Home paths with enforcement + tests that Playground code cannot read Home data; contacts allowlist loader (read-only, permission check, refuse if file is world-readable); audit log append-only outside agent write scope; `KILL` file; Run Policy integrated into bench runner.
- Replace the string-filter "sandbox" claim: either implement real isolation for generated code (proot/separate unprivileged tree if available on Termux; **verify feasibility, do not assume**) or rename it honestly and document limits.
- Accept: bypass tests (path traversal, symlink, env, subprocess) fail closed; Gateway off-by-flag leaves existing behavior unchanged.

**S0.11 Dual grading harness** (Haiku/Sonnet)
- Script that computes the DI metrics available at S0 (G5 baseline, G8 breadth, G9 safety) and records the v1 rubric scoring inputs; writes both to the ledger each stage.

**S0 gate (report to Ish and STOP):** full test suite green, flags verified OFF by default, baseline + A/A committed, Playground-cannot-read-Home test passing, audit log working, re-score v1 and DI with evidence. Ish approves before Stage 1.

---

## 8. Later stages (do NOT start without Ish's approval; full detail in `docs/plans/CODEY_OS_DEVELOPMENTAL_PLAN_V2.md` and v1 plan)
- **S1 Infant:** verifier-in-loop, grammar-constrained tool calls, re-planning on step failure, classifier routing vs keyword routing, self-rating calibration. Each A/B via the gate.
- **S2 Toddler (+ Sleep track):** verified-experience retrieval, skill library (model-agnostic, tested), error/strategy read side, teacher loop with verified-only retention, make episodic/long-term memory actually read or delete those tiers; consolidation ("sleep") job under §5.
- **S3 Child:** practice-task generator, curiosity scheduler on **learning progress** (not raw surprise), outcome-prediction log, Playground self-play with budgets; real-world action rollout R0→R3 proposals (§4).
- **S4 Adolescent:** self-set curriculum, prompt/policy search under the gate, rejection-sampling SFT adapters with replay on Colab/Kaggle, model registry with champion/challenger and one-command revert.
- **S5 Young adult:** brain-swap protocol (keep skills/memory, re-verify on new model), scaffold self-modification in an isolated worktree, never touching bench/gate/safety code.
- **S6 Adult:** raise autonomy levels per capability using human-signed criteria; optional Home pilots at A3.
Dormant CCOS modules (`goal_engine`, `skill_recombiner`, `reflection_engine`, `lifecycle_manager`, "5-agent deliberation"): rebuild on real signals or delete; until then do not claim them in docs.

## 9. Escalate to Ish (stop) when
- Any task would touch Home data, Restoricon backend, daemon lifecycle internals, or raise an autonomy level.
- A reviewer rejects twice without converging; live verification shows the symptom unresolved or a regression.
- Any external-effect action would be enabled or any contact is to be messaged for the first time.
- Colab/Kaggle cost or account/credential steps are needed.
- Two plans or rules conflict, or a finding here does not match the code.

## 10. First message Ish pastes into Claude Code (new session, Opus 5.5, high thinking)
> Read `CLAUDE.md`, then `docs/plans/CODEY_OS_AGENT_HANDOFF.md`, `CODEY_OS_DEVELOPMENTAL_PLAN_V2.md`, `CODEY_OS_AGI_IMPROVEMENT_PLAN.md`, and `CODEY_OS_AGI_AUDIT_2026-09-30.md`. Confirm branch is `codey-os-dev-v2` and the rollback tag exists. Do **not** write code yet. Produce a short Stage 0 execution plan: task order, which findings you verified against the current code (with any discrepancies), risks, and the exact prompt (model/thinking/new-context) for S0.1. Then wait for my approval.
