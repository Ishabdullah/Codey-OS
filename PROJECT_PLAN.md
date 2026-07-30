# Project Plan: Codey-OS (formerly Codey-v3 + CCOS, v4 retired)

**Status:** Active
**Started:** 2026-07-20
**Repo:** `Ishabdullah/Codey-OS` (new repo, seeded from Codey-v3, created 2026-07-27)
**Working directory:** `~/Codey-OS` on Termux/S24 Ultra
**Reference-only source:** `~/Codey-v4` (untouched, read from for migration only)
**Supersedes:** Codey-v4 Kernel migration project (retired as of this plan — see "What happened to v4" below)
**Authoritative spec:** `CODEY_OS_MASTER_VISION.md` — **signed off by Ish 2026-07-27.**
Every future decision, prompt, and restructuring step must not conflict
with it. Lives in the repo root; `QWEN.md` (repo root, once created) points
every fresh Qwen session to it.

---

## 1. Decision Summary

After auditing both Codey-v4's Kernel layer and Codey-v3's CCOS (Codey
Cognitive OS) subsystem against actual running code, we're changing the
base of future development:

- **Old plan:** Build outward from Codey-v4, with a custom Kernel
  (`ServiceRegistry` / `ManagerRegistry` / `DecisionEngine` / `PolicyEngine`)
  as the coordination layer for turning Codey into a pluggable-service
  platform.
- **New plan:** Build outward from **Codey-v3**, which already contains
  CCOS — a more complete, independently verified, six-layer cognitive
  architecture with capability registry, plugin system, sandboxed
  execution, multi-agent deliberation, and (not yet activated) self-
  improvement loops. Codey-v4 is retired as an active codebase. Its
  service-adapter pattern and any doc/changelog history worth keeping get
  migrated into this project; the Kernel classes themselves do not survive
  as the long-term routing mechanism.

**The end goal is unchanged from the original v4 vision:** a real
operating-system-like platform where coding is one pluggable capability
among several, with room to add more later, and — eventually, deliberately
— the ability for the system to begin improving itself. What changes is
which codebase we build that goal on top of.

---

## 2. What Happened to v4 (for the record)

- v4 added a Kernel layer on top of what is otherwise the same `core/` as
  v3. We fixed a blocking syntax error in `core/kernel.py` (unclosed `try`
  in `shutdown()`, duplicated dead code, missing `logging` import) and
  verified it compiles and instantiates.
- Two-pass code audit of v4 found only 2 of 12 claimed capabilities
  actually routed through the Kernel (RAG retrieval, three-model
  architecture via `conversation`/`memory`/`embedding` services). 2 more
  were partially routed (error recovery, peer CLI escalation). The
  remaining 8 (daemon, task queue, self-refinement, git, voice, static
  analysis, thermal management, fine-tuning export) were still direct-call,
  unmigrated.
- README.md was rewritten to accurately reflect this state (verified via
  literal diff, after two earlier attempts introduced unverified/fabricated
  content — a nonexistent "UnlimitedClaude" peer CLI and a fictional fourth
  model — which were caught and reverted).
- CCOS (in Codey-v3) was independently audited: all 19 core modules exist,
  compile clean, and **68 tests across 7 suites pass** on this machine,
  confirming it's substantially real, working code — not aspirational.
- `ccos/` and `core/` in Codey-v3 currently have **zero imports between
  them** — CCOS runs standalone via `ccos_main.py` and does not yet touch
  the coding-agent functionality in `core/`. That integration is the real
  work of this project.

---

## 3. Target Architecture

```
Codey-v3 (base)
├── ccos/                          ← becomes the OS layer
│   ├── core/capability_registry   ← replaces v4's ServiceRegistry
│   ├── core/plugin_manager        ← replaces v4's ManagerRegistry + adds real plugin discovery
│   ├── core/tool_router           ← replaces v4's DecisionEngine
│   ├── core/agent_orchestrator    ← replaces v4's PolicyEngine (Safety Agent veto)
│   ├── core/sandbox               ← new: isolated execution (v4 had none)
│   ├── core/[optimizer/recombiner/goal/project engines] ← present, NOT wired into
│   │                                                        live execution yet
│   └── plugins/                   ← coding-agent features get wrapped here
│       ├── coding/                ← from core/fixmode.py, core/agent.py etc.
│       ├── daemon/
│       ├── git/
│       ├── voice/
│       ├── thermal/
│       ├── finetune/
│       └── ...
└── core/                          ← existing coding-agent implementation, unchanged
                                       until wrapped as a plugin, one at a time
```

Governance moves from v4's `PolicyEngine` to CCOS's `agent_orchestrator`
Safety Agent veto (highest voting weight, can veto any plan) plus
`sandbox.py`'s enforcement rules (no destructive commands, no path escapes,
resource limits).

---

## 4. Phases

### Phase 0 — Foundation (this plan + log setup)
- [x] Audit v4 Kernel, fix `kernel.py`, verify README accuracy
- [x] Audit CCOS, confirm 68/68 tests pass
- [x] Confirm `ccos/` and `core/` are currently unconnected
- [x] Decide: build forward from v3+CCOS, retire v4
- [x] New repo `Codey-OS` created, seeded from Codey-v3, remote repointed
- [ ] Confirm disposition of `core/symbolic_graph.py` — exists in v3, was
      dropped in v4. Ask Ish whether this was intentional before deciding
      whether to keep it in the merged base.
- [ ] Migrate any still-accurate doc/changelog history from v4 into this
      project's docs (not a priority; do after Phase 1 stabilizes)

### Phase 1 — Wrap first coding-agent capability as a CCOS plugin (pilot)
**Status: COMPLETE (2026-07-28)**
Pick ONE feature to migrate first, end to end, to prove the pattern before
doing the rest. Candidate: RAG retrieval, since it's the one v4 feature we
confirmed was cleanly service-ified already (`embedding_service.py` /
`core/retrieval.py`), so there's a template to adapt from.
- [x] Confirmed real `core/retrieval.py` interface and real CCOS plugin
      pattern (manifest.json structure, test.py convention, auto-discovery)
      against actual source before writing the task prompt
- [x] Wrote `ccos/plugins/research/rag_retrieval/manifest.json` +
      implementation wrapping `core/retrieval.py`'s `retrieve()` as
      `research.retrieve` (reused the existing empty `research/` category
      rather than creating a new one — commit `028b4a6`)
- [x] Confirmed `plugin_manager` discovers and loads it — verified via
      real script: plugin count went from a known baseline of 6
      plugins/9 capabilities (cross-checked independently against the
      original repo audit) to 7/10, confirming clean addition
- [x] Confirmed the capability is queryable/invokable through
      `capability_registry` — `pm.call_capability('research.retrieve', ...)`
      returned correctly (empty string, graceful — KB has no matching
      content), use_count/success_count bumped on the registry entry
- [x] Existing direct-call path (`core/agent.py`,
      `prompts/layered_prompt.py`) confirmed untouched — `git diff --stat`
      empty on both
- [x] `test.py` added following the existing convention, 3/3 pass
- [x] Honest pattern assessment obtained: clean for ccos-internal plugins,
      but found a real bug — the copied `.parent` chain in every existing
      plugin's `test.py` lands on `ccos/` not the true repo root, silently
      shadowing top-level `core/` with `ccos/core/` (same package name,
      real collision risk) for any plugin importing from outside `ccos/`.
      Fixed locally with `parents[4]`, but flagged as needing a shared fix
      before repeating 9 more times (9 of 10 remaining capabilities live
      under `core/`/`tools/`/`utils/`/`pipeline/`).
- [x] **Follow-up complete:** shared `ccos/plugins/_pathutil.py` helper
      (commit `81a6b5f`) — anchors the walk-upward search at
      `_pathutil.py`'s own fixed location (2 levels below repo root)
      rather than the caller's, correctly sidestepping caller-nesting-
      depth entirely. `rag_retrieval` migrated to use it; regression-
      checked the one pre-existing sandbox test failure via `git stash`
      to confirm it predates this change.

### Phase 2 — Migrate remaining coding-agent capabilities
**Status: COMPLETE (2026-07-28) — 9 of 10 items wrapped, item 7 deferred**
One capability at a time, in this order (direct-call features first, since
they're simpler wraps than the partially-routed ones):
1. Static analysis (`core/linter.py`) — **COMPLETE**. Implementation
   commit `6c2c1b3`, blocking shared bug fixed in commit `fe00218`
   (verified via isolation testing: reverting the `_pathutil.py` hardening
   alone reproduced the exact original failure, confirming it was the
   load-bearing fix). Final state: 8/8 plugins loaded, 12 capabilities
   reconciled, sandbox test remains the sole pre-existing unrelated
   failure.
2. Git integration (`core/githelper.py`) — **COMPLETE** (commit `4921c24`).
   16 of 17 functions registered as capabilities (`uses_conventional_commits`
   correctly left internal — only called by `generate_commit_message`,
   confirmed via grep, not independently useful). Real mutating-operation
   test against a throwaway repo only (never this repo), specific evidence
   (commit hashes `2f470b1`/`8147828`). Capability count reconciled: 12→28.
   **Known gap:** 2 of 16 registered capabilities never actually invoked —
   `generate_commit_message` (needs 7B model, correctly deferred) and
   `git_push` (skipped over network-call ambiguity, though testable
   offline via two local throwaway repos — not done, low priority).
3. Voice interface (`core/voice.py`) — **COMPLETE** (commit `9d9d8b8`).
   Consolidated into the existing `tts_speech` plugin rather than creating
   a new one (one-plugin-per-domain, matching `system_info`/
   `camera_capture`) — TTS stays on `tts_speech`'s richer 4-engine
   fallback, STT added from `core/voice.py`. Found and fixed an
   independent manifest bug (`implementation: "tts:speak"` pointed at the
   filename, not the plugin's registered name — capability could never
   resolve through `plugin_manager`, reproduced pre/post-fix). `install.sh`
   gap closed (`pyttsx3`, `espeak`/`termux-api` now declared). STT
   end-to-end unverifiable in this headless environment (no real mic) —
   wiring confirmed, true transcription not, honestly disclosed.
4. Thermal management (`core/sysmon.py`, `core/thermal.py`) — **COMPLETE**
   (commit `0aac59e`). New plugin `thermal_monitor` (not extending
   `system_info` — different lifecycle, background-thread state vs.
   one-shot lookups). 8 capabilities: monitor snapshot/render, thermal
   status/throttle-check/thread-count (read-only), plus
   start_inference/end_inference/reset (mutating, mirroring
   `git_integration`'s pattern). Real live values confirmed (actual
   `/proc` reads: CPU%, RAM bytes, temp; `battery_pct: None` correctly
   reflects this device having no battery sysfs/Termux:API path, not a
   mock gap). Capability count 30→38 reconciled (initial apparent
   discrepancy was Claude's own tallying error misreading a combined
   table row as one capability instead of two — not stale registry
   state; confirmed directly via `git log -p` that `capabilities.json`
   has only 2 commits total, one touching only timestamps, never
   accumulating real drift).
5. Fine-tuning export (`core/finetune_prep.py`, `core/lora_import.py`) —
   **COMPLETE, deliberately partial scope.** 7 safe capabilities wrapped
   (dataset curation/export, notebook generation, adapter
   validation/info — all generative or read-only). The 5 functions that
   directly swap/merge the live model file
   (`swap_to_finetuned_model`, `merge_lora_with_llama_cpp`,
   `create_backup_before_import`, `rollback_to_backup`,
   `import_lora_adapter`) were **deliberately left unwrapped** — real,
   well-reasoned risk distinction from git's mutating capabilities (no
   cheap undo via a separate system; a bad swap breaks the only model the
   whole system runs on; making it agent-callable risks a live-model swap
   as a side effect of planning, not just deliberate human action via the
   existing `--import-lora` CLI path, which remains the only way to
   trigger these). **Open question for Ish:** whether
   `create_backup_before_import`/`rollback_to_backup` should be added
   later. **Resolved: yes, add both** — done (commit `43c5ba7`), 47
   capabilities total. Discovered and correctly handled a subtle safety
   issue during testing: `rollback_to_backup` reloads via
   `core.loader_v2.get_loader()`, which binds the model path at import
   time — a plain `cfg.MODEL_PATH` monkeypatch alone would NOT have
   prevented it from touching the real model. Dual-patched both
   `cfg.MODEL_PATH` and `loader_v2.get_loader` (no-op fake loader),
   restored in `finally`. Verified via SHA-256 checksums that backup was
   byte-identical and rollback restored original content exactly.
6. Task queue (`core/taskqueue.py`) — **COMPLETE** (commit `dea2aaf`).
   Path-addressable design (queue JSON path passed to every capability
   call, load/save per call, no in-memory instance cache — avoids a
   redundant second source of truth alongside the file). 7 capabilities:
   create/add/mark_running/mark_done/mark_failed/status/list.
   `plan_tasks()` correctly left as `orchestrator.py`'s own concern (a
   compound LLM-driven operation, not thin persistence). Real disk
   persistence proven via actual JSON read-back; confirmed no test
   artifacts left in `~/.codey_sessions/`. 47→54 capabilities reconciled.
7. Recursive self-refinement (inside `core/agent.py`) — **DEFERRED, not
   skipped.** Doesn't fit the standalone-utility-wrap pattern the previous
   6 items used — it's part of the still-unwrapped "Coding agent (core
   intelligence)" primary capability (master vision Section 3), not a
   peripheral one. Will be tackled together with wrapping the actual
   coding agent itself, as its own dedicated, carefully-scoped task later
   in Phase 2 — not now, and not to be silently dropped. **Testing note
   for when we get there:** rather than loading the real 7B model (RAM
   risk — already caused one crash during earlier planner-fix
   verification), consider swapping in a much smaller model
   (e.g. the 1.5B planner model, or an even smaller test model) purely
   for exercising the self-refinement/tool-calling mechanics during
   development — Codey-OS can't have a full coding-agent-sized model
   running for testing purposes on top of its own already-running model
   stack (7B + 1.5B + embedding) without risking the same OOM crash.
8. Daemon mode (`core/daemon.py`, `main.py:_daemon_is_running()`) —
   **COMPLETE, deliberately partial scope** (commit `874c748`). 7 safe
   capabilities under `system.daemon_*` (category `system`, not `coding`
   — process/liveness management, same class as `thermal_monitor`).
   `shutdown` and `command` (real task-submission, triggers actual 7B
   inference) deliberately left unwrapped — same risk-class reasoning as
   `swap_to_finetuned_model`. Tested the socket protocol layer safely by
   starting a bare `DaemonServer` (not the full `Daemon` class, no model
   loading) on a temp socket — confirmed the socket layer itself is
   lightweight independent of model loading. 54→61 capabilities
   reconciled.
9. Error recovery (`core/recovery.py`) — **COMPLETE, standalone scope**
   (commit `0132e0f`). 4 capabilities: `classify_error`, `get_fallback`,
   `execute_strategy`, `record_outcome`. Overlap with
   `core/strategy_tracker.py` confirmed real and resolved at the plugin
   layer — `StrategySwitcher`'s own tracking (in-memory, capped at 100
   entries, zero callers) deliberately NOT wrapped; `recovery_record_outcome`
   routes through the already-persisted, already-used `StrategyTracker`
   instead, without modifying `core/recovery.py`'s source. Found and
   honestly documented a real pre-existing classification bug in
   `recovery.py` ("command not found" misclassifies as `file_not_found`).
   `execute_strategy` tested live only for the safe mkdir path;
   pip-install/pytest-isolation paths correctly left unexecuted during
   testing. Not wired into `agent.py`'s failure path — deferred with item
   7. 61→65 capabilities reconciled.
10. Peer CLI escalation — **COMPLETE, safest possible scope**
    (commit `ef57fed`). Found the real consent mechanism
    (`PeerCLIManager.confirm()`, a blocking interactive terminal prompt)
    and correctly concluded it has no automated-call equivalent —
    `escalate`/`confirm`/`call`/all of `peer_shell.py`'s invocation
    functions left completely unwrapped. 4 genuinely safe read-only
    capabilities exposed instead (list available CLIs, task-type
    detection, dry-run CLI selection, prompt preview without sending).
    Confirmed no real external CLI was invoked during testing — only
    `shutil.which` checks and one caught local exec failure (broken
    `claude` shebang in this environment, not an invocation). 65→69
    capabilities reconciled.

**Phase 2 summary:** 9 of 10 original items fully wrapped (item 7,
recursive self-refinement, deliberately deferred — see log). Consistent
risk-tiered judgment held across all mutating/external-facing functions
throughout — nothing risky was wrapped mechanically just because the
established pattern said "wrap it." All deliberately-unwrapped items
consolidated in `PENDING_ISH_DECISIONS.md`. One gap found and flagged
during the final reflection: `core/observability.py`'s wrap was never
actually scheduled anywhere in this list — needs its own task.

Each item gets its own checklist (manifest, registration, routing test,
CCOS test suite entry) mirroring Phase 1's pilot.

### Phase 3 — Unified entry points + retire old fragmented ones
**Status: STARTING** (per `CODEY_OS_MASTER_VISION.md` Section 6a)

Breaking into two sub-steps, same incremental philosophy as Phase 1/2
(add new alongside old, prove it, retire old separately — not a risky
big-bang replacement):

**Sub-step A — COMPLETE (commit `4477a5c`).** `codey-start` shells out to
`codeyd3 start`, reuses `codey3`'s existing GUI-PID-file coordination
mechanism (`$HOME/.codey-v3/gui-server.pid`, confirmed pre-existing in
`codey3` lines 397-415, not new). Daemon deliberately persists after TUI
exit (daemon mode's purpose — avoid repeated model-load cost);
`codey-start`'s cleanup trap only tears down what it uniquely owns (the
GUI it started). `codey-stop` confirmed via real process checks: daemon +
plannd + GUI + all 3 model servers cleanly stopped, zero orphaned
`llama-server` processes. `codey3`/`codeyd3`/`ccos_main.py`/`gui/start.sh`
confirmed byte-for-byte unchanged. `install.sh` updated (PATH check,
completion banner). **Minor open item:** a race-condition fix (`sleep
0.5` before an orphan-process pgrep check) was syntax-checked but not
live-tested, per RAM discipline — worth confirming on a future live run,
low priority.
- [x] `codey-start` brings up the daemon + TUI + GUI together, per the
      master vision (both interfaces can run simultaneously)
- [x] `codey-stop` cleanly shuts down daemon + TUI + GUI + any model
      servers
- [x] Existing `codey3`/`codeyd3`/`ccos_main.py`/`gui/start.sh` remain
      untouched and working during this step

**Codey-OS branding rename — COMPLETE (5 sub-tasks, final commit
`94b7b9b`).** Discovered mid-Sub-step-A while testing `codey-start`;
`codey3`/`codeyd3` themselves and ~90 other files still carried
"Codey-v2"/"Codey-v3" branding and naming, a real risk given this exact
pattern had already caused bugs twice. Executed as its own sequenced
5-part effort rather than one sweep, given 93 files / 463 occurrences:
1. Shared path-constant foundation (`utils/config.py`), behavior-
   preserving refactor before any renaming — commit `9e86a9c`
2. Actual file renames (`codey3`→`codeyOS`, `codeyd3`→`codeydOS`),
   constant value flip, cross-references — commit `147aafd`
   (paused mid-sequence for a real investigation — see below)
3. Cosmetic branding sweep, ~320 occurrences, plus bundled fixes (GUI
   version badge bug, HTTP-Referer headers) — commit `702b0d5`
4. Docs filename, CHANGELOG entry, remaining functional filename
   references — commits `9ec73b1`/`9dcf7a7`
5. Lowercase command-name sweep, closing a gap in sub-task 4's own
   verification grep (`main.py`'s `/help` was telling users to run a
   dead command) — commit `94b7b9b`

**Real bugs found and fixed along the way (not just branding):**
`codey3`/`codeyd3` daemon-directory mismatch (couldn't detect the real
daemon at all), GUI crash on Ctrl+C during active generation, 3
checkpoint-system bugs (`is_core_file()` scope was the entire repo not
just core dirs; `git add -A` over-staging; a test-isolation bug),
`/usr/bin/env` shebang failures (Termux-specific), orphaned
`llama-server` processes surviving `stop` (plausibly explains
unexplained high baseline RAM from early in this project). All verified,
all fixed, all logged in detail in `PROJECT_LOG.md`.

**Deliberately left alone, tracked not forgotten:**
`docs/tools-embedding-pipeline.md`'s prose content still narrates
"Codey-V3" throughout (only its filename was fixed — a content-accuracy
question, not a stale-reference one); a telemetry dedup-key collision bug
found during verification (`ccos/core/telemetry_engine.py`, causes
intermittent test flakiness, real pre-existing bug, unrelated to the
rename — fix later: `uuid.uuid4()` or an atomic counter instead of
timestamp+`id()`).

**Sub-step B — COMPLETE (commit `03182e9`).** New shared
`core/dashboard_data.py` module, imported by both TUI (`main.py`) and GUI
(`gui/server.py`) — avoids duplicating capability-call/plugin-manager
bootstrap logic in two places. `sysmon.py`'s rendering logic extracted so
it works from any snapshot dict; GUI's `get_ram()` now sources from the
same shared module instead of parsing `/proc/meminfo` independently.
Verified via simultaneous capture: TUI and GUI showed matching
`ram_total` with only expected small timing-drift on `ram_used` — genuine
same-source proof, not just "both work independently." Zero llama-server
process during the OpenRouter-only test run, zero orphaned processes
after stop.
- [x] Wire `thermal_monitor` (system-wide CPU/RAM/temp/battery, Phase 2
      item 4) and `observability` (process-specific tokens/memory/tasks/
      health, just completed) capabilities into both the TUI's status bar
      and the GUI's display, so they read from the same source and never
      diverge — this is the literal "Unified system dashboard"
      requirement from the master vision

**Sub-step C — COMPLETE (commit `314450a`).** Discovery: the file at
`README.md` was never actually a project README — it was the internal
CCOS architecture doc (12 sections, 6-layer diagram, module tables) from
very early in this project, sitting at that filename the whole time.
Genuine rewrite, not an update: 143 insertions, 365 deletions. Correctly
caught and fixed a real overclaim in the old content (a table flatly
stating "Self-improving: Yes," contradicting Section 5's gated-by-default
reality) rather than carrying it forward. Section-by-section accounting
done for all 12 old sections + License. Independent code audit (required,
not just doc cross-checking) found `docs/commands.md` missing 12 real
slash commands and ~13 real CLI flags that exist in `main.py`, plus one
possibly-stale flag (`--rollback`) — correctly left unfixed (out of
scope) but flagged, with the README's own description of
`docs/commands.md` softened so it doesn't inherit the overclaim.
**Real process gap found:** confirmed `PROJECT_PLAN.md` and
`PENDING_ISH_DECISIONS.md` were never actually committed to the repo —
only ever handed back as downloadable files. Being fixed now (see below).
- [x] Restructure README around: what Codey-OS actually is now (CCOS
      shell + coding-agent capabilities, not a standalone coding tool),
      the unified `codey-start`/`codey-stop` entry points, the 10 wrapped
      capabilities, the unified dashboard (once Sub-step B lands), and
      accurate Quick Start instructions using the real current command
      names
- [x] Cross-check against `CODEY_OS_MASTER_VISION.md` Section 3 as
      primary source, verify against actual code only where something
      seems uncertain or possibly stale (same discipline as everything
      else this project — don't just trust a doc, spot-check)
- [x] Decide what to do with the now-fixed-but-still-stale-feeling
      "Codey-v2/v3 era" framing throughout — resolved by the full
      rewrite; the rename itself gets one honest mention in the intro

**Two loose threads tracked, not blocking Phase 3 closure:**
1. `docs/architecture.md` still only documents the coding agent's
   three-model design, no CCOS-layer content — already a known gap noted
   in the master vision as a planned rewrite, not new.
2. `docs/commands.md`'s incompleteness (found above) — worth a dedicated
   follow-up, since the new README now points readers there specifically.

**Then, once B and C are both proven stable:**

**Scoping pass complete (2026-07-30, no code changed) — see
`PROJECT_LOG.md` for full evidence. Status of each item:**

- [ ] `core/kernel.py` — **ready to close, no decision needed.** File
      does not exist anywhere in this repo (`find -iname kernel.py`
      returns nothing); confirms PROJECT_PLAN's own note that v4 was
      never part of Codey-OS's lineage. Recommend marking done next
      round with this evidence.
- [ ] `codey3`/`codeyd3` — **ready to close, no decision needed.**
      Neither file exists in this repo; the only hits are historical
      mentions in `CHANGELOG.md`/`PROJECT_PLAN.md`/`PROJECT_LOG.md`/
      `QWEN.md`/`CODEY_OS_MASTER_VISION.md`. Retirement already
      happened; this half of the checklist item is stale.
- [ ] `gui/start.sh` — **genuine product decision for Ish.** File
      exists but nothing execs it (`codey-start`/`codeyOS`/`codeydOS`
      each reimplement its GUI-start/PID/trap logic independently
      instead of calling it — three copies of the same job, logged as
      [NEW-22] in `NEW_ISSUES.md`). `README.md:53`'s claim that
      `codey-start` orchestrates it is incorrect. Options: delete it
      and fix the duplication, or make the launchers actually call it.
- [ ] `ccos_main.py` — **genuine product decision for Ish, different
      shape than assumed.** Section 6a's "keep it, codey-start
      orchestrates it" rationale does not apply here — nothing in the
      current codebase execs or imports `ccos_main.py` (confirmed by
      repo-wide grep); it is an orphaned standalone MVP demo, not an
      orchestrated underlying piece. Logged as [NEW-23]. The real
      choice is delete outright vs. keep as a documented standalone demo.
- [ ] `main.py` — **genuine product decision for Ish, but with a
      constraint that rules out silent deletion.** Traced actual usage:
      `codey-start` → `codeyOS` (direct/interactive mode, `codeyOS:417-
      429`) does `from main import main; main()` with args passed through
      unfiltered (`codeyOS`'s only arg-scanning is for `--bg`/
      `--background`, which doesn't touch the direct-mode path) — so
      `main.py` is not a fragmented duplicate `codey-start` replaces, it
      is the actual interactive-REPL engine `codey-start` delegates to
      today, and all of `--init`/`--tdd`/`--fix`/`--no-resume`/
      `--clear-session` still only exist there. `python3 main.py
      --daemon` and `codeydOS start`'s `core.daemon.main()` path were
      also checked for divergence — both do `check_pid_file()` then
      `Daemon().run()`, functionally identical, just duplicated code (no
      live bug found). Given Section 6's "not going to silently drop
      working functionality" non-goal, "fully retire" is not viable
      as-is without `codey-start` first growing equivalent flag
      passthrough or subcommands; the live choice is "keep main.py
      documented as the underlying engine/advanced interface" vs.
      "invest in wiring those flags into codey-start and then retire."

### Audit Remediation — Round 1 (C-1, H-1, H-4)
**Status: H-4 FIXED AND LIVE-VERIFIED. C-1 FIXED AND LIVE-VERIFIED (short
QA prompt landed as a follow-up). H-1 still mechanism-verified only — no
live check of the shutdown path has been run.** (2026-07-29) — fixes from
`Codey-OS-audit.md`'s Critical finding C-1 and High findings H-1/H-4, the
three causally-linked issues behind the "Codey doesn't respond" live
symptom (slow first response → impatient retry → daemon-race → killed
model server). Round 1's H-4 fix (writing the daemon's own PID early)
introduced a self-race bug — the daemon always found its own PID in
`check_pid_file()` and refused to start — which is why the first live
verification attempt failed outright; that self-race is now also fixed
and confirmed live. C-1's original fix only tiered the *code paths*, not
the prompt content — the "identity" block was still the full
8,352-char tool-format prompt even on the lightweight path; a follow-up
(`get_qa_system_prompt()`) now actually shrinks it. See `PROJECT_LOG.md`
2026-07-29 entries (both the original Round 1 entry and the follow-up
above it) for full detail.
- [x] **C-1** — Tiered the system prompt: `is_qa` classification moved
      before prompt construction in `core/agent.py`, threaded into
      `build_recursive_prompt()`/`_build_draft_prompt()` as a new
      `lightweight` param (`prompts/layered_prompt.py`) that skips the
      repo_map/retrieval/skills/files/symbolic_graph code paths entirely
      for QA/smalltalk messages. Added an elapsed-time "Thinking... (Ns,
      processing N-token prompt)" ticker in `core/inference_v2.py` for the
      prompt-processing window, threaded via an `on_first_token` callback
      through `core/inference_hybrid.py` and `core/inference_openrouter.py`
      so it clears cleanly the instant real output starts streaming.
- [x] **H-1** — Removed `main.py`'s blanket `pkill -9 -f llama-server`
      shutdown fallback. `core/loader_v2.py`'s `ModelLoader` gained a
      `get_pid()` accessor; `main.py`'s `shutdown()` now captures that PID
      before calling `unload()` and, only if `unload()` itself throws,
      falls back to killing that one PID's process group — never a bare
      name pattern.
- [x] **H-4** — `codeydOS`'s `start_daemon()` now writes the PID file
      (atomic write-then-`mv`) immediately after capturing `$DAEMON_PID`,
      from the shell itself, instead of waiting for `core/daemon.py`'s own
      later `write_pid_file()` call. Closes the race where a concurrent
      `codeydOS start` during the 7B's load window passed the stale/absent
      PID guard and pre-killed the first instance's loading model server.
      Also cleans up the PID file on the daemon-failed-to-start path (a new
      failure mode introduced by writing it earlier).
- [x] **H-4 self-race fix** — `check_pid_file()` in `core/daemon.py` now
      returns `False` (not a duplicate) when the PID in the file is its
      own, since Round 1's fix made that the expected case on every
      startup. Live-verified: `codeydOS start` succeeds cleanly, a
      concurrent `codeydOS start` during model load correctly reports
      "already running" and does not kill the loading instance
      (confirmed exactly one `llama-server` PID via `pgrep` once loading
      finished).
- [x] **C-1 follow-up: short QA identity prompt** — added
      `get_qa_system_prompt()` (`prompts/system_prompt.py`, ~280 chars,
      no tool-format instructions) and wired it into
      `_build_draft_prompt()`'s `identity` layer for `lightweight=True`.
      Lightweight prompt dropped from 8,947 → 849 chars. Live-verified in
      a single warm session: QA turns ("hello", "what can you do?") both
      returned plain text with no `<tool>` leakage in ~14-20s
      first-token time; a real coding request in the same session
      correctly took the full path (file loaded, recursive draft/review,
      tool call generated). See `PROJECT_LOG.md` for the full numbers and
      the caveat that the ~15s-vs-~180s comparison isn't a clean
      isolation of the char-count savings alone (warm vs. cold session).
- [ ] **H-1 live verification — NOT YET DONE.** Only C-1 and H-4 got a
      real live check this round. H-1 (scoped process kill on shutdown)
      is still verified at the mechanism level only (`get_pid()` exists,
      the blanket `pkill` is gone) — nobody has yet triggered the
      `unload()`-throws fallback path live and confirmed it kills only
      the one captured PID's process group.

### Audit Remediation — Round 2 (C-2)
**Status: FULLY LIVE-VERIFIED** (2026-07-29) — fix from
`Codey-OS-audit.md`'s Critical finding [C-2] (GUI server: unauthenticated
command execution, bound to `0.0.0.0` by default, no WebSocket Origin
check). Three sub-tasks, each committed and code-reviewer-approved
separately, then confirmed end-to-end by a live-verifier pass through the
real `gui/start.sh` launch path. See `PROJECT_LOG.md` 2026-07-29 entries
for full detail.
- [x] Default GUI bind host changed `0.0.0.0` → `127.0.0.1`
      (`CODEY_GUI_HOST` env override preserved) — commit `d29468f`
- [x] `handle_ws` rejects connections with missing or mismatched `Origin`
      header (allowlist: `http://localhost:<port>` /
      `http://127.0.0.1:<port>`, port read from module-level `PORT`, not
      hardcoded) — commit `ca94ab5`
- [x] Per-process session token (`secrets.token_urlsafe(32)`) required as
      a query param on the `/ws` upgrade, timing-safe comparison,
      independent AND with the Origin check, both checked before
      `ws.prepare()`. `GET /` intentionally left ungated (loopback-only,
      no real second security boundary to gain) — commit `1198ba1`
- [x] Verified by code-reviewer against a real running instance on a
      scratch port: all 4 token/Origin combinations behaved as expected
      (no-token 403, wrong-token 403, correct+correct 101,
      correct-token+bad-Origin 403), clean PID-tracked teardown
- [x] **Fully live-verified through the actual `gui/start.sh` launch
      path** (real daemon startup, not a scratch instance). Model load
      confirmed (7B, PID 25675, `/health` → 200). Loopback-only bind
      confirmed via direct connectivity: `127.0.0.1:8888` → 200, real LAN
      IP `192.168.1.111` → connection refused on both 8888 and 8080. WS
      auth re-checked against the real served token (fetched live from
      the actual `index.html`, not reused): missing Origin → 403,
      correct Origin + wrong token → 403, correct Origin + missing token
      → 403, correct Origin + correct token → 101 + real metrics
      broadcast frame. All 5 real processes (`gui/server.py`,
      `llama-server`, `main.py`, `start.sh` wrapper, plus the test
      harness's FIFO-holder helper) torn down individually by tracked
      PID. `free -h`: 4.0Gi used pre-launch → 3.4Gi used post-teardown
      (healthier than baseline). Single model-load cycle, confirmed
      unloaded. See `PROJECT_LOG.md` for full numbers.
- Follow-up logged, not fixed: `NEW_ISSUES.md` [NEW-3] (Suspected) —
  GUI session token could leak into access logs if logging is ever
  configured for `gui/server.py` (dormant today).
- New follow-up logged during this live-verification pass:
  `NEW_ISSUES.md` [NEW-4] (Confirmed) — `gui/start.sh` unconditionally
  chains into `main.py`, forcing a full 7B model load with zero user
  interaction just to view the dashboard.

**Round 2 (C-2) is now fully closed** — all 3 sub-tasks committed and
code-reviewer-approved, plus a full live-verifier pass through the real
launch path. No open items remain under Round 2.

### Audit Remediation — Round 3 (NEW-4)
**Status: FULLY LIVE-VERIFIED** (2026-07-29) — fix for `NEW_ISSUES.md`
[NEW-4], found during Round 2's live-verification pass: `gui/start.sh`
unconditionally chained into `main.py`, forcing a full 7B model load with
zero user interaction just to view the dashboard.
- [x] Added an opt-in `--dashboard-only` flag (or
      `CODEY_GUI_DASHBOARD_ONLY=1` env var) to `gui/start.sh` that skips
      `main.py` entirely and waits on the GUI server's own PID instead,
      reusing the existing trap/kill logic unchanged (no second kill
      path introduced). Default (no-flag) behavior byte-for-byte
      unchanged. Commit `ea954eb`.
- [x] code-reviewer approved, with one non-blocking suggestion: the new
      arg-parsing loop makes the last non-flag positional arg win
      instead of the first — latent, no current caller passes multiple
      positional args, not required to fix before merge.
- [x] Live-verified both paths directly:
      - Default path: real model-load cycle observed (`free -h`: 8.3Gi
        used during load → 3.1Gi used after teardown), `main.py` +
        `llama-server` both running as before, confirmed unloaded after
        stop.
      - `--dashboard-only` path: `pgrep` confirmed no `main.py`/
        `llama-server` process ever started; `curl` to the dashboard
        returned 200. Teardown by tracked PID clean in both cases.
      - Single model-load cycle run for this round, confirmed unloaded
        afterward per RAM-discipline rule.
- Follow-up logged, not fixed: `NEW_ISSUES.md` [NEW-5] (Suspected) — a
  `llama-server` child possibly briefly outliving `gui/start.sh`'s parent
  on a mid-load `TERM` kill, observed once during this round's default-
  path verification. code-reviewer confirmed it's unrelated to this
  round's diff (lives in `main.py`'s own spawn/kill path, untouched here,
  and unreachable in `--dashboard-only` mode).

**Round 3 (NEW-4) is now fully closed** — code-complete, code-reviewer-
approved, and live-verified on both the default and `--dashboard-only`
paths. No open items remain under Round 3 itself; [NEW-5] is a separate,
unscoped follow-up tracked in `NEW_ISSUES.md`.

### Audit Remediation — Round 4 (NEW-3)
**Status: CODE COMPLETE, code-reviewer-approved** (2026-07-29) — fix for
`NEW_ISSUES.md` [NEW-3], found during Round 2 (C-2) sub-task 3's review:
the GUI session token could leak into aiohttp's default access log if
`logging.basicConfig()` (or any handler) is ever configured for
`gui/server.py`'s process in the future — dormant, not currently
exploitable, but fragile.
- [x] `gui/server.py`'s `web.run_app()` call now passes `access_log=None`,
      disabling aiohttp's default `AccessLogger` outright. Commit
      `efe9f5c`.
- [x] code-reviewer approved: confirmed `access_log` is a genuine
      documented `aiohttp` kwarg (aiohttp 3.14.3 installed), verified no
      other log call site in `gui/server.py` could leak the token.
- No live-verification performed for this fix specifically — scoped as a
  negative/absence assertion with no new live-session behavior to
  exercise, already covered by Round 2 (C-2)'s prior full live
  verification of normal GUI start.

**Round 4 (NEW-3) is now fully closed** — code-complete and
code-reviewer-approved. No open items remain under Round 4 itself.

### Audit Remediation — Round 5 (NEW-1)
**Status: FULLY LIVE-VERIFIED** (2026-07-29) — fix for `NEW_ISSUES.md`
[NEW-1], root-cause Confirmed in Round 5's diagnostic investigation:
`pytest tests/` spawned a real 7B `llama-server` and orphaned it because
`tests/test_memory.py::TestMemoryCompressSummary::test_compress_summary_handles_inference_failure`
called `compress_summary()` with no mocking of inference at all.
- [x] `tests/test_memory.py`'s
      `test_compress_summary_handles_inference_failure` now mocks
      `core.inference_v2.infer` to return the real failure-return
      convention, and asserts the actual failure-path fallback behavior.
      Commit `c65be95`.
- [x] code-reviewer approved: independently re-ran both the targeted test
      and the full `tests/test_memory.py` file, confirmed no orphan
      `llama-server` after either.
- [x] **live-verifier ran the full suite**: `pytest tests/ -q` → 253
      passed in 0.43s (previously ~42s due to the hidden real model
      load). No orphan `llama-server` after (`ps -eo pid,ppid,comm | grep
      llama`, clean — `pgrep -af` avoided due to a false-positive
      self-match issue in this shell). `free -h` stable before/after
      (563Mi→816Mi free, swap unchanged at 1.6Gi). `NEW_ISSUES.md`
      [NEW-1] updated to Resolved.

**Round 5 (NEW-1) is fully closed.** Both code-complete and live-verified
criteria are met per Ground Rule 7.

### Audit Remediation — Round 6 (NEW-5)
**Status: FULLY LIVE-VERIFIED** (2026-07-30) — fix for `NEW_ISSUES.md`
[NEW-5]: `llama-server` could be orphaned indefinitely if `SIGINT`
landed while the model was still loading in `main.py`'s `repl()`,
because `KeyboardInterrupt` is a `BaseException` not caught by
`loader_v2.py`'s `load_primary()`'s own `except Exception`, and
`llama-server` is spawned with `preexec_fn=os.setsid`, insulating it
from the terminal's signal group.
- [x] `main.py`'s `repl()` (~line 1267-1274) wraps `loader.load_primary()`
      in `try/except (KeyboardInterrupt, SystemExit)`, calling the
      existing `shutdown()` (~line 125-144, unchanged) and returning
      cleanly. No new kill path introduced. Commit `eed29dc`.
- [x] code-reviewer approved, with one Warning: live-verification output
      wasn't yet recorded in `PROJECT_LOG.md` at approval time.
- [x] **live-verifier independently reproduced a genuine mid-load
      `SIGINT`** via `pty.fork()` (tracked child PID, not `timeout`, not
      a name-pattern kill), sent directly to the tracked PID before
      `llama-server` finished loading. Result: clean "Interrupted during
      model load, cleaning up..." message, `shutdown()` ran, and
      `ps -eo pid,ppid,pgid,comm | grep -E "python|llama"` was empty
      afterward — no orphan. `free -h` recovered from 3.3Gi used/4.3Gi
      free (mid-teardown) baseline of 4.2Gi used/892Mi free. An earlier
      backgrounded attempt was voided by live-verifier itself as
      inconclusive (model loaded before the `SIGINT` command ran) and
      not counted as a pass.
      - Regression check (normal-completion cycle, sequenced after the
        model was confirmed unloaded): full model load, one real
        inference exchange, clean `/exit` — no orphan process, RAM fully
        recovered (2.7Gi used/6.0Gi free after).
      - Single model-load cycle boundary respected: Test 2 only started
        once Test 1's `llama-server` was confirmed fully unloaded.
- [x] `NEW_ISSUES.md` [NEW-5] updated to Resolved, citing `eed29dc` and
      this live-verification.

**Round 6 (NEW-5) is now fully closed** — code-complete, code-reviewer-
approved, and independently live-verified (a real live-verifier
confirmation, not implementer-reported or code-complete-only evidence),
per Ground Rule 7. Of the user's original four-item punch list, NEW-3,
NEW-1, and NEW-5 are now all done. `NEW_ISSUES.md` [NEW-6] (same
unguarded pattern at three sibling call sites: `args.init` ~line 1458,
`args.tdd` ~line 1465-1466, `args.fix` ~line 1485-1486) remains open,
Suspected, unscoped — not fixed as part of this round. **NEW-2 remains
as Round 7, the hardest and final item on the punch list.**

### Audit Remediation — Round 7 (NEW-2)
**Status: CODE COMPLETE, code-reviewer approved** (2026-07-29/30) — fix
for `NEW_ISSUES.md` [NEW-2]. Root cause was corrected twice during
investigation (per Ground Rule 6) before landing on the confirmed
mechanism: live-verifier reproduced the bug live with the real 7B model
and found it is **not** a JSON-parse failure and **not** a false
success claim, but a **patch-application failure** — the `[Recursive]`
planner emits a well-formed `patch_file` call with `old_str=""` and a
whole duplicate `shutdown()` function as `new_str`; `tools/patch_tools.py`
correctly rejects it (existing guard since commit `8ab96e1`); the retry
budget (`max_retries(1)`) is exhausted on an identical second attempt
with no second warning printed; peer-CLI escalation is unavailable and
returns `None`; the loop falls through to a generic fallback that
re-invokes the model, which then asks an honest clarification question
instead of surfacing that the edit never applied. `git diff main.py`
confirmed empty (`shutdown()` at `main.py:125` unmodified) — the
silent no-op.
- [x] `core/agent.py`'s fallthrough branch (~line 1831+, after retries
      and escalation are both exhausted for a `write_file`/`patch_file`/
      `append_file` call still in an error state per `is_error()`) now
      logs and transcribes an explicit `[EDIT NOT APPLIED] <tool> on
      <path> failed after retries and escalation were exhausted — no
      file was modified.` marker before the generic fallback turn.
      Added `tests/test_new2_edit_not_applied.py`. Commit `55e408c`.
- [x] code-reviewer independently ran `git diff`, traced
      `last_tool_result`'s per-iteration freshness (reassigned every
      loop iteration — no staleness risk), confirmed the new test's
      `infer` monkeypatch targets the real module-level import at
      `core/agent.py:9` (explicitly checked against — and confirmed
      distinct from — the NEW-1 deferred-import-mismatch bug class),
      ran the targeted test itself (`1 passed in 0.19s`) and the full
      suite itself (`321 passed, 1 failed` — the one failure being the
      pre-existing, unrelated `ccos/tests/test_ccos.py::test_sandbox`,
      in a file this diff never touches). Approved, no Critical or
      Warning findings. One non-blocking Suggestion logged (pre-existing
      `("write_file", "patch_file")` tuple at `core/agent.py:1671`
      excludes `append_file`, unlike the new marker code's three-tuple —
      not fixed here, own future ticket).
- [ ] **Not live-verified with the real model post-fix.** The pre-fix
      bug reproduction was live (real 7B model); the post-fix
      confirmation is via code-reviewer's static/control-flow analysis
      plus mocked-test verification only, which is the appropriate bar
      for a logging/control-flow change (not a process-lifecycle
      change requiring live-verifier per Ground Rule 4/7). Not marked
      "live verified" per Ground Rule 7.

**Round 7 (NEW-2) is code complete and code-reviewer-approved — this
closes the final item of the user's original four-item punch list
(NEW-3, NEW-1, NEW-5, NEW-2), all now resolved.** `NEW_ISSUES.md`
[NEW-6] (sibling `load_primary()` gap) and [NEW-7] (recursive planner
synthesizing whole functions instead of targeted patches) remain open,
both Suspected/unscoped, discovered along the way but not originally
requested.

### Audit Remediation — Round 8 (NEW-6)
**Status: CODE COMPLETE, code-reviewer approved, LIVE-VERIFIED with one
residual gap identified and separately logged as NEW-9** (2026-07-30) —
fix for `NEW_ISSUES.md` [NEW-6]: the same unguarded `loader.load_primary()`
pattern NEW-5 fixed at `repl()` also existed, unguarded, at three sibling
call sites in `main.py` (`args.init`, `args.tdd`, `args.fix`).
- [x] `main.py`'s `args.init`/`args.tdd`/`args.fix` sites each now wrap
      `loader.load_primary()` in `try/except (KeyboardInterrupt,
      SystemExit)`, calling the existing `shutdown()` and returning
      cleanly — identical pattern to NEW-5's `repl()` fix (`eed29dc`), no
      new kill logic. Commit `435c120`.
- [x] code-reviewer approved.
- [x] **live-verifier tested all three new sites plus a rerun of
      `--init`.** 3 of 4 site-tests came back clean (`--init` rerun x2,
      `--tdd`, `--fix`): guard fired correctly, `ps` empty afterward,
      `free -h` recovered RAM each time (settling around 3.7Gi used /
      5.0Gi free). **1 of 4 (`--init` attempt 1) reproduced a genuine
      orphan**: real `llama-server` (PID 27124, PPID 1) survived a tracked
      `SIGINT`, confirmed via `ps -p 27124 -o pid,ppid,pgid,etimes,cmd`;
      killed directly by tracked PID, RAM recovered.
- [x] **Root-caused the one failure, not just observed it:** the orphan
      occurred because the `SIGINT` landed inside `subprocess.Popen()`'s
      internal `os.fork()` call in `core/loader_v2.py` (~lines 116-130);
      CPython's own atfork exception handling silently discarded the
      `KeyboardInterrupt` before it ever reached the guard's `try/except`.
      This is a **pre-existing, shared gap** in the underlying Popen/fork
      mechanism used by all four guarded sites (`repl()` included) — **not
      a regression introduced by this round's diff.**
- [x] `NEW_ISSUES.md` [NEW-6] marked Resolved, citing `435c120`, with an
      honest caveat that the fix works exactly as scoped and the residual
      gap is a separate, already-logged concern (NEW-9).
- [x] `NEW_ISSUES.md` [NEW-5] corrected per CLAUDE.md rule 6: added a
      caveat that the same residual race can bypass its own `repl()`
      guard too, without downgrading its Resolved status (the guard
      demonstrably works for the vast majority of the interrupt window).
- [x] New `NEW_ISSUES.md` [NEW-9] entry added, Confirmed: the
      atfork/fork-window race itself, root-caused, affecting all four
      guarded call sites, with full reproduction evidence. Flagged as
      needing its own dedicated scoping/fix pass — deliberately not
      scoped or fixed in this round.

**Round 8 (NEW-6) is code complete, code-reviewer-approved, and
live-verified — with one residual gap independently found during that
same live-verification pass and separately logged as `NEW_ISSUES.md`
[NEW-9], not silently folded into this round's "done" claim.** Per
Ground Rule 7, this round's own scope (the three sibling call sites) is
genuinely fully resolved; NEW-9 is a distinct, deeper problem in shared
code that needs its own future round. Queue position for NEW-9 relative
to the already-queued NEW-4/NEW-7 is an open question for Ish, not
decided unilaterally here.

### Audit Remediation — Round 9 (NEW-9)
**Status: NOT COMPLETE — NOT RESOLVED.** code-reviewer approved a fix
that live-verification subsequently showed does not close the bug it
targeted. `NEW_ISSUES.md` [NEW-9] remains open. A follow-up round is
needed to widen the guarded window; do not proceed with a new fix
attempt without Ish's direction (this is a CLAUDE.md "stop and
escalate" situation — live-verifier showed the original symptom isn't
actually resolved).
- [x] Fix attempt: commit `1a1c0b7` wrapped `core/loader_v2.py`'s
      `subprocess.Popen()` call in
      `signal.pthread_sigmask(SIG_BLOCK/SIG_UNBLOCK)` around exactly
      that call, based on project-architect's investigation of NEW-9's
      root cause (the atfork/fork-window race).
- [x] code-reviewer approved — correctly, based on the specific call
      site it was asked to review. That approval is not itself in
      question.
- [ ] **live-verifier ran 16 valid, independent repeated-attempt tests
      (one model-load cycle at a time, each confirmed unloaded before
      the next, per CLAUDE.md rule 2) and reproduced the identical
      orphan in 3/16 (~19%) — statistically indistinguishable from the
      original ~1-in-4 rate this fix was supposed to close to ~0.**
- [x] Root cause of the fix's incompleteness identified: the vulnerable
      window starts ~70 lines earlier than where the mask was placed.
      `"Starting llama-server..."` logs at `core/loader_v2.py` ~line 55;
      `pthread_sigmask(SIG_BLOCK)` wasn't applied until ~line 125, right
      before `Popen()`. Command-list construction, mmap/mlock config
      lookup, and log-file open all happen in between, unguarded. A
      `SIGINT` landing in that gap is delivered normally before the mask
      is applied, and can still surface inside the forked child's atfork
      callback, reproducing the exact original symptom.
- [ ] `1a1c0b7` is **not** being reverted (it's a harmless partial
      mitigation, not a regression) but must **not** be described as
      having fixed NEW-9 anywhere in the docs.
- [x] `NEW_ISSUES.md` [NEW-9] corrected per CLAUDE.md rule 6: a
      "Status: STILL OPEN" block added explaining the fix attempt and
      why it failed, with the 13/16 clean, 3/16 orphan aggregate and
      root cause.

**Round 9 (NEW-9) is NOT resolved.** The fix committed in `1a1c0b7` was
reasoned soundly for the specific `Popen()` call site under review, but
live-verification's 16-attempt aggregate shows the actual vulnerable
window is wider than what got wrapped, and the bug's real-world hit
rate is unchanged. Per CLAUDE.md rule 6, this is logged honestly rather
than left as a false "done." Next step (widening the guarded window to
start at or before the `"Starting llama-server..."` log line) needs its
own dedicated scoping pass and is being brought to Ish for a decision on
how to proceed, not unilaterally re-attempted here.

### Audit Remediation — Round 10 (NEW-9)
**Status: code complete, code-reviewer approved, live-verified with
continued residual failure (2/22) — improvement over Round 9 but not
closed. NEW-9 remains open pending a different fix approach.**
- [x] Fix attempt: commit `2aaabb1` widened
      `signal.pthread_sigmask(SIG_BLOCK/SIG_UNBLOCK)` in
      `core/loader_v2.py` to cover the full window from at/before
      `"Starting llama-server..."` through the `Popen()` call, per
      Round 9's root-cause correction (the previous mask started too
      late).
- [x] code-reviewer approved.
- [ ] **live-verifier ran 22 valid, independent repeated-attempt tests
      (`pty.fork()`-based harness, tracked child PID, real
      `os.kill(pid, SIGINT)`, delay varied 0.0s-0.3s; 4 additional
      attempts excluded as invalid/contaminated). Result: 20/22 clean,
      2/22 FAILED — both at delay=0.0s, reproducing the identical
      atfork-swallowed-`KeyboardInterrupt` orphan.** This is a real,
      substantial improvement over Round 9's 3/16 (~19%) rate — 2/22
      (~9%), clustered only at the absolute earliest timing — but not
      zero.
- [x] Root cause of the residual failure is not yet understood: both
      failures show `KeyboardInterrupt` raised inside
      `logging._afterFork` even while `pthread_sigmask(SIG_BLOCK)` is
      active for the entire widened region — suggesting a deeper
      mechanism (possibly Termux/Android-specific signal-delivery
      behavior) than "the window was too narrow," which was Round 9's
      diagnosis and which Round 10 correctly addressed for the vast
      majority of the timing range.
- [ ] `2aaabb1` is **not** being reverted (genuine improvement, not a
      regression) but must **not** be described as having fixed NEW-9
      anywhere in the docs.
- [x] `NEW_ISSUES.md` [NEW-9] corrected per CLAUDE.md rule 6: a Round 10
      block added documenting the fix attempt, the improvement, and the
      residual 2/22 failure with verbatim reproduction evidence.

**Round 10 (NEW-9) is NOT resolved.** This is the second consecutive
fix attempt on NEW-9 to be live-verified as incomplete. The Round
9→Round 10 pattern (progressively widening the masked region) has shown
diminishing but nonzero returns and does not appear to be converging to
zero through mask-widening alone. Per CLAUDE.md's escalation rules,
this is being brought to Ish directly for a decision on how to proceed
— no third fix attempt has been scoped here.

### Audit Remediation — Round 11 (NEW-12)
**Status: code complete, code-reviewer approved, live-verified.**
"Live-verified" here means confirmed via log-line/completion/teardown
evidence (absence of a second spawn-attempt log line, a successful
non-error inference result, and clean tracked-PID teardown), not a
literal multi-checkpoint `ps` table — see caveat below.
- [x] Fix: commit `59f4f69` removed `core/inference.py`'s independent,
      uncoordinated `_start_server()` launcher (no port-in-use check, no
      `os.setsid`, `stop_server()` never called from anywhere) and routed
      its fallback path through `core.loader_v2.get_loader().ensure_model()`
      instead — the same canonical, port-checked, singleton-guarded
      launcher already used by the daemon and CLI.
- [x] code-reviewer approved. Reviewer separately flagged, during that
      same review (not in NEW-12's original scope), that removing
      `core/inference.py`'s launcher orphaned `ThermalManager`'s
      thread-reduction restart mechanism — logged as `NEW_ISSUES.md`
      [NEW-13] in commit `6093696`, not silently fixed or dropped.
- [x] live-verifier: `free -h` before — `4.5Gi` used, `2.9Gi` free,
      `6.2Gi` available. Started the primary model via
      `get_loader().ensure_model()` (llama-server PID 30405), then called
      `core.inference.infer()` (the fallback path) in the same process.
      No second `"Loading model:"`/`"Starting llama-server..."`/
      `"llama-server PID:"` log line appeared — `ensure_model()`
      short-circuited on its already-running check, no second `Popen()`
      was invoked. The fallback call returned a real completion
      (`'Hello'`), not an `[ERROR]` string. Teardown used the tracked PID
      (30405) via `loader.unload()`. `free -h` after — `4.5Gi` used,
      `3.2Gi` free, `6.1Gi` available — RAM recovered, no leak.
- [x] **Honest caveat (per CLAUDE.md rule 5):** the verifier's own
      in-script `ps` capture had a filter bug (matched on the literal
      substring `"llama-server"`, but `ps`'s COMMAND column truncates to
      `llama-serv`), so the in-script three-checkpoint `ps` table did not
      actually confirm "exactly one llama-server process" via a literal
      `ps` snapshot at each checkpoint. The verifier chose not to re-run a
      second full model-load cycle just to fix this cosmetic script bug,
      per the one-cycle-only RAM discipline rule (CLAUDE.md rule 2). The
      verdict rests on (a) absence of a second spawn-attempt log line —
      a direct, literal code-path artifact, not an inference — (b) the
      successful non-error completion, and (c) confirmed clean teardown
      with only the tracked primary PID remaining. This is solid
      evidence but is not identical to a literal `ps`-table confirmation
      at the "during fallback" moment.
- [x] `NEW_ISSUES.md` [NEW-12] marked Resolved, citing `59f4f69`, with
      the same precise live-verification description (not overclaimed).
- [x] `NEW_ISSUES.md` [NEW-13] (thermal-restart regression, found outside
      NEW-12's scope during code review) logged Confirmed in commit
      `6093696` — not fixed here, per CLAUDE.md rule 8.

**Round 11 (NEW-12) is closed: code complete, code-reviewer approved,
and live-verified** (with the ps-filter-gap caveat above honestly
recorded rather than rounded up to "ps confirmed"). Deferred, not
scoped here: quarantining/deleting dead scaffolding, a single named
`SERVER_PORT` constant across `loader_v2.py`/`inference.py`/
`inference_hybrid.py`, wiring `PLANNER_MODEL_PATH`/`PLANND_SERVER_PORT`
into an actual launcher, and a real cross-process flock/pidfile lock to
close the daemon-vs-CLI port TOCTOU race (all noted as future candidates
in `NEW_ISSUES.md` [NEW-12]'s own write-up). Remaining open items after
this round: NEW-7 (recursive planner, hardest, deferred), NEW-9
(deprioritized per user decision), NEW-11 (daemon watchdog stale-flag
gap, logged only), NEW-13 (thermal-restart regression, logged only).

### Audit Remediation — Round 12 (NEW-13)
**Status: code complete, code-reviewer approved, fully live-verified.**
- [x] Fix: commit `0935cbd` wired `ThermalManager`'s thread-reduction
      restart mechanism into `core/loader_v2.py`'s `ensure_model()` —
      when `restart_recommended` is set, it stops the running primary
      `llama-server` and restarts it with the updated thread count, then
      clears the flag. Closes the gap NEW-13 identified after Round 11's
      NEW-12 fix removed `core/inference.py`'s independent launcher (the
      flag's only prior consumer).
- [x] code-reviewer approved, with two non-blocking Warnings: no lock
      around the check-then-act sequence (not currently exploitable —
      only one call site today), and no unit test coverage of the new
      branch.
- [x] live-verifier: `free -h` before — `4.9Gi` used, `2.0Gi` free,
      `5.7Gi` available. Started the primary model (PID 14619), forced
      `restart_recommended = True`, called `ensure_model()` again in the
      same process. Confirmed a real restart, not a short-circuit: PID
      changed 14619 → 14800, old PID gone (`ps -p 14619` returncode 1),
      `restart_recommended` correctly cleared afterward, a real
      inference call post-restart returned `'OK'` (not an error), clean
      teardown (`ps -p 14800` returncode 1 after `unload()`). `free -h`
      after — `3.3Gi` used, `5.6Gi` free, `7.3Gi` available — RAM fully
      recovered, no leak.
- [x] Verified via exact-PID `ps -p <pid>` checks rather than a
      `comm`-substring grep for `"llama-server"`, since Termux's `ps`
      truncates `COMMAND` to `llama-serv` and would false-negative such a
      grep — noted as an environmental wrinkle, not a code defect.
      live-verifier also cleaned up an unrelated test artifact (the
      inference call's side-effect embed server, PID 15580, killed by
      its own tracked PID and confirmed gone), not part of NEW-13's own
      code path.
- [x] `NEW_ISSUES.md` [NEW-13] marked Resolved, citing `0935cbd`, with
      the same precise live-verification description (not overclaimed).

**Round 12 (NEW-13) is closed: code complete, code-reviewer approved, and
fully live-verified.** Remaining open items: NEW-7 (recursive planner,
hardest, deferred), NEW-9 (deprioritized per user decision), NEW-11
(daemon watchdog stale-flag gap, logged only), plus the two deferred
items from NEW-12's own scoping (cross-process port lock, planner
auto-launcher). Next round to be decided with the user.

### Audit Remediation — Round 13 (NEW-11)
**Status: code complete, code-reviewer approved, fully live-verified**
(via a lighter daemon-only harness after the full 3-model stack proved
too RAM-heavy to safely test on this device).
- [x] Fix: commit `ab13a8d` changed the daemon's 30s watchdog to check
      real process liveness instead of the stale `get_loaded_model()`
      in-memory flag.
- [x] code-reviewer approved (static/unit-test evidence at review time;
      live-verification was pending).
- [x] live-verification history (recorded in full per CLAUDE.md rule 6 —
      not just the final pass/fail):
      1. First attempt, via the full `codeydOS start` (daemon + 7B +
         1.5B plannd + embed server, all concurrently), crashed Termux
         entirely, apparently right at 7B model-load time.
      2. Second attempt, same full stack, also crashed — possibly
         compounded by the app being backgrounded during the test
         (unconfirmed which factor dominated).
      3. Third attempt, full stack again with Termux kept foregrounded,
         did not crash but self-aborted proactively per the
         live-verifier's own safety instructions, after observing swap
         climb from a ~1Gi baseline to 7.5-8.5Gi within ~40 seconds of
         steady-state startup with all three models running — before
         reaching the actual kill/restart test. Verbatim:
         `check 1: used 9.0Gi available 1.5Gi swap 4.6Gi` →
         `check 2: used 9.0Gi available 1.5Gi swap 7.1Gi` → settled
         around `swap 7.5Gi`. Logged as `NEW_ISSUES.md` [NEW-14]
         (Confirmed, observational device-capacity finding, not a code
         bug).
      4. Fourth attempt used a lighter, isolated harness instead:
         `python3 main.py --daemon` directly (bypassing the `codeydOS`
         wrapper, which is what spawns the separate 1.5B plannd
         process), running only the 7B primary + embed server. This
         succeeded cleanly and safely — see `NEW_ISSUES.md` [NEW-11]'s
         Resolved write-up for the full verbatim evidence (baseline/
         post-load `free -h`, watchdog log lines showing PID 921 → 3034
         after `kill -9 921`, real post-restart inference returning
         `PONG`, clean `SIGTERM` teardown, final `free -h`).
- [x] `NEW_ISSUES.md` [NEW-11] marked Resolved, citing `ab13a8d`, with
      the full live-verification summary (including the crash history).
- [x] `NEW_ISSUES.md` [NEW-14] logged Confirmed — the full 3-model
      `codeydOS start` stack is a genuine, previously-undocumented
      RAM/swap-pressure risk on this ~10.8GB device, not a code bug.

**Round 13 (NEW-11) is closed: code complete, code-reviewer approved,
fully live-verified.** This closes the last item from the second-wave
punch list (NEW-4/NEW-12/NEW-13 already done). Remaining open: NEW-7
(recursive planner, hardest, still deferred), NEW-9 (fork-window race,
deprioritized), NEW-14 (device swap-pressure finding, observational —
not scoped as a fix), plus the two earlier-deferred items from NEW-12
(cross-process port lock, planner auto-launcher). Next round to be
decided with the user.

### Audit Remediation — Round 14 (NEW-7)
**Status: investigation-complete but partial (6 of 8 planned draws) —
NOT a fix round. No code changed. No implementer task scoped this
round, per explicit instruction.**
- [x] Desk scoping pass (mechanism re-verification, reproduction plan
      design) — no live session.
- [x] Live-reproduction pass: two sequential single-model-load REPL
      sessions (Session A recursive/default env, Session B
      `CODEY_RECURSIVE=0`/plain, confirmed via absent `[Recursive]`
      labels), 4 prompts planned per session (8 draws total).
- [x] 6 of 8 draws completed; stopped early at genuine swap-thrashing
      (swap 8.9Gi, `llama-server` RSS collapsed to ~2MB) per CLAUDE.md
      rule 2's explicit instability instruction — a safe, correct stop.
- [x] Settled the open "is it recursion-specific" question: **no** — the
      literal `old_str: ""` bug reproduced once on each path (a2
      recursive, b1 plain); a related hallucinated-`old_str` variant
      reproduced twice more (a1, b2). Combined 4/6 completed draws (67%)
      failed the docstring-insertion prompt.
- [ ] Not yet run: b3/b4 (loader_v2 error-handling and patch_tools
      rename prompts on the plain path) — needed for a clean same-path
      comparison across all 3 prompt styles before NEW-7 can be called
      fully characterized. Deferred to a future round.
- [x] `NEW_ISSUES.md` [NEW-7] updated: status upgraded from Suspected to
      Confirmed, reproducible, ~67% failure rate on the docstring
      prompt, confirmed not recursion-specific — still open, still
      unfixed.
- [x] Four additional structural findings logged (none fixed, no
      implementer task scoped): `NEW_ISSUES.md` [NEW-15] (a
      `write_file` full-file-reconstruction escalation after
      `patch_file` failure, placed in the wrong location in one draw —
      flagged as likely higher priority than NEW-7 itself given its
      full-file-data-loss potential), [NEW-16] (the patch-preview UI
      panel renders as success even when the underlying patch failed,
      in all 4 failed draws), [NEW-17] (the post-edit commit offer
      scopes to all working-tree changes, not just the current turn's),
      [NEW-18] (a single lightweight REPL session hit the same severe
      swap-thrashing as the full 3-model stack, after only 2 model calls
      with retries).

**Round 14 (NEW-7) is NOT closed — investigation-complete-but-partial,
not a completed fix.** NEW-7 itself remains open/unfixed (much better
characterized now). NEW-15 through NEW-18 are newly open, unfixed, with
no implementer tasks scoped. Next round (continue NEW-7's remaining 2
draws vs. prioritize NEW-15's severity) to be decided with the user.

### Round 15 (NEW-15)
- [x] `tools/file_tools.py`'s `tool_write_file()` — syntax-check
      guardrail added, refusing to overwrite an existing `.py` file with
      syntactically invalid content (via `core/linter.py`'s
      `check_syntax()`); fails open if the linter import fails.
- [x] `tools/patch_tools.py`'s `[PATCH_FAILED]` message reworded to
      de-emphasize `write_file` and warn against partial-memory
      reconstruction (`write_file` itself remains available).
- [x] `tests/test_file_tools.py` (new) — 4 unit tests covering
      blocked/allowed/new-file/fail-open behavior; full suite 258
      passed.
- [x] Code-reviewer approved: no Critical/Warning findings, one
      Suggestion (test coverage) addressed in follow-up.

**Round 15 (NEW-15) is code complete, code-reviewer approved with
direct live-behavioral verification of the guardrail logic (not an
on-device model session — reviewer explicitly assessed one wasn't
warranted for this class of change), full unit test coverage added.**
Commit `7756581`. Narrowly scoped to the `write_file`
full-file-corruption risk; does not address NEW-16/NEW-17/NEW-18 (still
open, unscoped) or NEW-7 itself (still open, b3/b4 draws outstanding).

### Round 16 (NEW-16)
- [x] `core/agent.py` — both `show_patch()` and `show_file_write()`
      call sites now pass `error=is_error(result, name)`.
- [x] `core/display.py` — both functions gained an `error=False` param;
      red border + "PATCH FAILED"/"WRITE FAILED" title on error,
      unchanged happy-path styling otherwise.
- [x] `show_patch()` call site also gained a narrow inline check for
      `tools/patch_tools.py`'s `[PATCH_FAILED]` prefix — deliberately
      not via widening the shared `is_error()`, to avoid breaking that
      function's deliberate exclusion of `[PATCH_FAILED]` from the
      retry/escalation logic.
- [x] Code-reviewer approved: `is_error()` and all four
      retry/escalation call sites confirmed untouched, happy-path
      output byte-for-byte unchanged, full suite 325 passed (1
      pre-existing unrelated failure).

**Round 16 (NEW-16) is code complete, code-reviewer approved via direct
`execute_tool()`-level verification (no live model session needed for
this class of change).** Commit `99d922f`. Bundled the identical
`show_file_write()` bug into the same fix (same file, same pattern).
Spun off [NEW-19] (`NEW_ISSUES.md`) — a deferred design question about
whether `[PATCH_FAILED]`'s retry/escalation bypass needs its own
transcript marker distinct from `[EDIT NOT APPLIED]`. Does not address
NEW-17/NEW-18 (still open, unscoped) or NEW-7 itself (still open,
b3/b4 draws outstanding).

### Round 17 (NEW-17)
- [x] `core/githelper.py` — added `git_status_paths(paths)` and
      `git_commit_paths(message, paths)`, mirroring
      `core/checkpoint.py`'s already-reviewed scoped-staging pattern
      (`git add -- <paths>`, never `-A`; pathspec on both `add` and
      `commit`). `git_commit()`/`git_status()` themselves untouched.
- [x] `core/agent.py` — `check_git_and_offer_commit()` now takes the
      already-existing per-turn `files_touched` list and uses the
      scoped functions; prompt text updated to honestly describe what
      will be committed.
- [x] Code-reviewer approved: independently traced `files_touched` as
      genuine per-turn local state, ran its own adversarial
      scratch-repo test (pre-staged unrelated file survived untouched
      by the scoped commit — proving the commit-level pathspec is
      load-bearing, not just the add-level one), reconfirmed the
      existing `ccos` `git_integration` self-test passes unchanged.

**Round 17 (NEW-17) is code complete, code-reviewer approved via direct
scratch-repo verification (no live model session needed for this class
of change).** Commit `f4f51fa`. One Suggestion accepted as a footnote,
not spun off: `files_touched` includes paths from any tool call with a
`path` arg (e.g. `read_file`), not strictly write/patch tools — harmless
today since the scoped git functions no-op on unchanged files. Does not
address NEW-18 (swap-thrashing recurrence, unscoped), NEW-19
(PATCH_FAILED design question, unscoped), or NEW-7 itself (still open,
b3/b4 draws outstanding).

### Round 18 (NEW-18 live-reproduction attempt) — inconclusive investigation, NOT a fix round
- [ ] NEW-18's original question (context size vs. turn count/retries as
      the swap-thrashing driver) — attempted live-reproduction via a
      small-file-vs-large-file comparison harness. **No code changed
      this round.**
- [x] Comparison could not run: harness hit a new bug in `main.py`'s
      stdin paste-detection (`select()` on non-TTY stdin), logged as
      NEW-20 (Confirmed, not fixed).
- [x] NEW-18 itself corrected per Ground Rule 6 — remains open/
      unanswered, this round is not evidence either way.
- [x] Incidental finding logged: model-load-alone swap spike, NEW-21
      (Confirmed, observational, not fixed).

**Round 18 is an inconclusive investigation round, not a fix round —
no source files were modified.** NEW_ISSUES.md, PROJECT_LOG.md updated
with the corrected NEW-18 status and the two new findings (NEW-20,
NEW-21). NEW-20 is flagged as a clean, well-isolated candidate for a
near-future fix round. NEW-7, NEW-9, NEW-17 (deferred item), NEW-18,
NEW-19, NEW-20, and NEW-21 all remain open.

### Round 19 (NEW-20) — code complete, code-reviewer approved, fully live-verified with a real main.py invocation
- [x] `main.py`'s paste-detection `select()` loop (`~1346-1359`) wrapped
      in `if sys.stdin.isatty():` so it's skipped entirely for non-TTY
      stdin, eliminating the drain-whole-file-then-spin-forever bug.
      TTY paste-glue behavior unchanged. Commit `ac732e9`.
- [x] Code-reviewer approved: independently reproduced pre-fix hang,
      post-fix clean processing, and pty-based TTY paste-glue behavior
      via its own scratch harness; checked all launcher scripts for
      stdin wrapping that could affect `isatty()` in real use — none
      found. No Critical/Warning findings.
- [x] Live-verified: real `python3 main.py --no-resume` invocation with
      piped multi-line stdin, `real 0m27.791s`, exit code 0, two piped
      lines processed as two distinct correctly-answered turns (not
      garbled), clean `/exit` teardown, no orphaned `llama-server`
      process afterward. Single model-load cycle confirmed unloaded.
- [x] NEW-18's harness guidance relaxed as a direct consequence: future
      NEW-18 reproduction attempts can now use plain stdin piping again,
      since the bug that made piping unsafe is fixed.

Remaining open after this round: NEW-7 (partially characterized), NEW-9
(deprioritized), NEW-18 (inconclusive, harness constraint now relaxed),
NEW-19 (unscoped design question), NEW-21 (observational), plus the two
earlier-deferred NEW-12 items (cross-process port lock, planner
auto-launcher).

### Phase 4 — Self-improvement activation (deliberate, not automatic)
Do NOT start this phase until Phases 1–3 are stable and you've watched the
system run real coding tasks through the sandbox/safety-veto path for a
meaningful period.
- [ ] Review `auto_improvement_loop.py` and `capability_optimizer.py`
      behavior in a controlled test, not live
- [ ] Review `skill_recombiner.py` — decide what "compound skill" creation
      should require before it's allowed to register something new
      automatically (approval gate?)
- [ ] Review `goal_engine.py` — decide whether generated goals require
      explicit approval before entering the planner queue, at least
      initially
- [ ] Only after explicit sign-off, wire these into the live execution path

---

## 5. Open Questions (need your input before proceeding)

1. ~~`core/symbolic_graph.py` disposition~~ **Resolved 2026-07-27:**
   confirmed it's real, active code (691 lines, compiles clean) — a
   SQLite-backed concept-graph module actively imported by `core/agent.py`,
   `core/memory_v2.py`, `core/finetune_prep.py`, the fine-tuning exporter,
   and `prompts/layered_prompt.py`. It's load-bearing, not dead code.
   **Decision: keep it.** It was apparently dropped from v4 without being
   a deliberate decision — worth treating as a caution about doing
   file-by-file deletion carefully rather than by inference.
2. ~~Do we rename the project?~~ **Resolved 2026-07-27:** new repo created
   as `Codey-OS`.
3. Confirm Phase 1's pilot choice (RAG retrieval) makes sense to you, or
   would you rather pilot with something else first?

---

## 6. Ground Rules (carried over from your standing preferences)

- Every code change comes with a clear explanation and your approval
  before anything is written — no exceptions.
- All code must run on Termux/S24 Ultra; anything needing more compute
  gets flagged with GitHub/Colab/Kaggle options.
- Claude writes precise instructions for Qwen; Qwen's output gets reviewed
  for fabrications before being trusted (per the earlier README incidents
  in this same project — Qwen invented a fake CLI and a fake model once
  already, so every migration step's completion claim gets checked against
  a real diff or test run, not just Qwen's summary).
- This plan and the accompanying log get updated after every meaningful
  change, not just at phase boundaries.
