# Work Queue — One Ordered List, Everything Outstanding

**Purpose:** every other tracking doc (`PENDING_ISH_DECISIONS.md`,
`PROJECT_PLAN.md`, `PROJECT_LOG.md`, `NEW_ISSUES.md`,
`CODEY_OS_MASTER_VISION.md`) still holds its own detail and stays the
source of truth for that detail — this file doesn't duplicate it. What
this file adds is the thing none of them have: **one sequence to actually
work through**, across all of them, so a session can start here instead
of re-deriving order from four separate documents each time.

Built 2026-07-30 from a full read-through of all four tracking docs
(see `PROJECT_LOG.md`'s 2026-07-30 entry for the inventory this was based
on). Update this file's checkboxes and "Currently here" pointer as items
close — don't let it go stale the way a couple of the source docs' own
checkboxes had (Phase 0's `symbolic_graph` box, Section 5's Open Question
#3 — both already resolved in substance, never ticked).

---

## How new issues get logged as we go

Keep using `NEW_ISSUES.md` exactly as it already works — next sequential
`NEW-##` ID (currently next free: **NEW-43**, after `NEW-27` through
`NEW-42` were logged across this session's hygiene, Track 1 audit,
NEW-19, NEW-10, and NEW-8 rounds), rated Confirmed or Suspected, same
format as existing entries.
**ID-collision note (2026-07-30):** an interrupted session's
code-reviewer pass logged two NEW-8-adjacent findings under `NEW-24`
and `NEW-25` — both already taken (by the `load_secondary()` bug and
the `codeyOS` arg-forwarding fix, respectively). Renumbered the two new
ones to `NEW-41`/`NEW-42` before they could ship as a second collision
of the exact kind Track 0 already fixed once this session. Lesson: a
background agent's own count of "next free ID" can go stale if another
round advances it after that agent's context was formed — always
re-grep `NEW_ISSUES.md` for the actual current max before trusting a
remembered number.
The only addition: if a newly-found issue blocks or changes a specific
item in this queue, **cross-reference the queue item's name/number
inline** in both directions — a line in the `NEW_ISSUES.md` entry pointing
at the queue item, and a note added under that queue item here pointing
at the new `NEW-##`. That's the "logical place" — new issues don't get a
separate log; they get a normal `NEW_ISSUES.md` entry plus a two-way
pointer if they touch active queue work.

Per CLAUDE.md rule 8, anything found outside a task's current scope still
gets logged, not silently fixed or dropped, even mid-queue-item.

---

## Track 0 — Hygiene (do first; cheap, no dependencies, clears noise)

- [x] Fix `NEW-24` ID collision (two unrelated issues shared one ID) —
      done this round: renumbered the `codey3`/`codeyd3` naming-drift
      issue to **NEW-26**.
- [x] Tick `PROJECT_PLAN.md` Phase 0's stale `core/symbolic_graph.py`
      checkbox — the underlying question was answered 2026-07-27
      (Section 5, Open Question 1), the box was just never checked.
- [x] Close `PROJECT_PLAN.md` Section 5, Open Question 3 ("confirm Phase
      1's pilot choice") — moot in practice (Phase 1 shipped and
      downstream work already built on it); struck through rather than
      left looking open.
- [x] Revisit the paused "small cleanup list" (6 confirmed-safe-to-delete
      files from the original repo audit) — 5 of 6 were already deleted
      in commit `dd49c1d`; the 6th (`ccos/plugins/research/__init__.py`)
      turned out to be a required package marker, not actually
      safe-to-delete (the original audit's UNUSED classification was
      wrong — it's structurally identical to the equally-empty
      `__init__.py` in every sibling plugin dir). `CODEY_OS_MASTER_VISION.md`
      Section 8 corrected to reflect this.
- [x] Revisit the paused root-level/`docs/` UNCLEAR files from the same
      audit — handed to `project-architect`: `TODO.md` deleted (fully
      superseded by `NEW_ISSUES.md`/`WORK_QUEUE.md`), `QWEN.md`'s stale
      tree partially fixed, everything else kept. Two items need Ish's
      input (logged as `NEW-27`, Suspected): `AUDIT_REPORT.md`'s
      archive-vs-delete disposition, and `docs/TODO2.md`'s staleness
      needing scoped re-verification. Also surfaced a Confirmed
      discoverability gap (three real docs missing from README's docs
      table) — also under `NEW-27`.

## Track 1 — Audits (new this round; do before deeper Phase 5 work since findings feed into it)

- [x] **Tool/capability audit** — done 2026-07-30 via `agent-tool-designer`.
      Fixed 3 stale/wrong manifest descriptions (`coding.finetune_rollback_backup`,
      `coding.git_commit`, `peer_escalation`'s stale call-site citations).
      Logged `NEW-34` (Confirmed, needs Ish's call): the 3 `skill_*`
      compound plugins under `ccos/plugins/compound/` are broken by
      construction (no data piped between pipeline steps) **and** are
      live, agent-callable output of the permanently-gated
      `skill_recombiner` — the recombiner engine being gated doesn't stop
      `plugin_manager._discover()` from auto-loading its pre-generated
      output. This is a rule-1-adjacent question, not resolved
      unilaterally. Also logged `NEW-35` (Suspected): `vision.camera_capture`'s
      default `/tmp/...` output path likely wrong under Termux.
      Recommendations (not executed): add `coding.git_commit_paths` as a
      safer sibling; wrap `static_analysis`'s read-only linter functions;
      consolidate `system_info`/`thermal_monitor`/`observability`'s
      overlapping CPU/RAM reads eventually (not urgent). Everything else
      audited (`error_recovery`, `task_queue`, `daemon_control`,
      `observability`, `thermal_monitor`, `rag_retrieval`, `tts_speech`,
      `camera_capture`, `system_info`) checked out accurate — kept as-is.
- [x] **Prompt audit** — done 2026-07-30 via `prompt-engineer`. Fixed 2
      real gaps: `system_prompt.py`'s word→tool mapping tables had no
      entry for "Edit" (both `PLANNER_PROMPT` and `orchestrator.py`'s
      `PLAN_PROMPT` emit "Edit <file>:" steps) — added as a `patch_file`
      synonym. `critique_prompts.py`'s 3 templates didn't actually
      instruct plain-text-only output despite the module docstring
      claiming they do — added explicit no-tool-call-tags/no-code-blocks
      wording (verified `core/recursive.py:460` uses the literal
      `<tool>` string as a hard stop sequence, so this was a real
      truncation risk, not cosmetic). Logged 5 follow-ups: `NEW-28`
      (`plannd.py`'s `_TOOL_VERBS` regex still missing "edit"), `NEW-29`
      (`orchestrator.py`'s `PLAN_PROMPT` format diverges from
      `PLANNER_PROMPT`, out of this audit's 4-file scope), `NEW-30` (this
      round's Edit-mapping fix enables a step needing two tool calls,
      contradicting the "exactly one tool call per response" rule — needs
      a design call + live-verifier), `NEW-31` (`CRITIQUE_TOOL`/`CRITIQUE_PLAN`
      defined but never invoked), `NEW-32` (Suspected — `LayeredPrompt`
      doesn't enforce layer-name uniqueness, likely to bite Phase 5b's
      tier-specific layers). No live model-load test run (static analysis
      only, per rule 2).
- [x] Compare `core/recovery.py`'s built-in success-rate tracking against
      `core/strategy_tracker.py` (flagged possible duplicate tracking,
      `CODEY_OS_MASTER_VISION.md` Section 8) — **already resolved**, found
      2026-07-30: Phase 2 (commit `0132e0f`) already wrapped
      `ccos/plugins/coding/error_recovery/error_recovery.py` with this
      exact decision documented in its module docstring —
      `recovery.py`'s own tracking is in-memory/non-persisted, while
      `strategy_tracker.py` is the already-live, disk-persisted path
      (imported by `core/learning.py`), so the plugin's
      `recovery_record_outcome()` routes through `strategy_tracker.py`'s
      `record_attempt()`, not `recovery.py`'s `record_error()`.
      `core/recovery.py` itself is untouched. No further action needed;
      the "Section 8" flag in `CODEY_OS_MASTER_VISION.md` predates this
      plugin and is now stale — corrected there too.
- [x] Scope `NEW-19` (design question: is `[PATCH_FAILED]`'s bypass of
      retry/escalation logic correct, does it need its own transcript
      marker) — **decision recorded 2026-07-30 (Ish, direct):** repeated
      same-file `[PATCH_FAILED]` failures within a turn escalate to the
      existing peer-CLI path; add a new distinct transcript marker for
      the unresolved-within-turn case (not a reuse of NEW-2's marker).
      Re-verified the underlying gap is still current before recording
      (`core/agent.py:1715`). Now a scoped Track 2 task, see below.

## Track 2 — Independent bug/security fixes (real risk exposure now; not blocked by Phase 5, can run in parallel with Track 1/3)

- [x] `NEW-19` implementation — **code-complete, 2026-07-30**, per the
      decision recorded above: `core/agent.py` now tracks a per-turn,
      per-path `patch_failed_counts` dict; a repeated (>1) same-path
      `[PATCH_FAILED]` in a turn routes into the existing peer-CLI
      escalation path (mirrors the exhausted-retries call site at
      ~line 1798); a new `[PATCH_FAILED, UNRESOLVED]` marker (distinct
      wording from NEW-2's `[EDIT NOT APPLIED]`) fires if still
      unresolved after that. 5 new unit tests added in
      `tests/test_new19_patch_failed_repeat_escalation.py`, covering the
      redirect/peer-ran/skipped escalation branches and the single- vs.
      repeated-failure marker distinction (263/263 full suite passing).
      **code-reviewer: APPROVED, 2026-07-30** — independently re-verified
      scoping, key population, elif-chain mutual exclusivity, and ran the
      tests live (confirmed 5/5 and full-suite 263/263 match the
      implementer's claims, not just re-stated them). Surfaced 2 adjacent
      findings during review, logged (not fixed) per rule 8: `NEW-36`
      (Confirmed — the pre-existing verbatim-duplicate-tool-call guard
      bypasses this fix entirely for the more common exact-repeat LLM
      failure mode) and `NEW-37` (Suspected — minor `peer_cli.py`
      keyword-matching/wording side effects from `error_log` now
      containing `[PATCH_FAILED]` file-content text).
      **live-verifier: CONFIRMED, 2026-07-30** — drove `core/agent.py`'s
      real `run_agent()` entry point, and separately `main._run_with_plan
      (..., no_plan=True)` (the actual dispatch `main.py`'s REPL loop
      calls), with a scripted/mocked `infer` returning two (then, in a
      2nd run, three) `patch_file` calls with a nonexistent `old_str` on
      the same path within a turn, `_in_subtask=False`, and **did not
      mock `core.peer_cli.escalate`** — its real `confirm()` interactive
      `console.input()` prompt fired for real ("⚠ Codey hit max
      retries and needs help... Suggest: Gemini CLI (Google)...");
      answered "n" via real stdin to decline. Confirmed live: (1) the
      escalation prompt fires on the 2nd same-path `[PATCH_FAILED]`, and
      fires again on a 3rd — no double-fire for the same failure, no
      infinite loop; (2) declining falls through each time to the
      `[PATCH_FAILED, UNRESOLVED]` marker, not NEW-2's
      `[EDIT NOT APPLIED]`; (3) no crash, `git status` clean afterward
      both runs (patch never matched, so no file was ever mutated, as
      expected). No local 7B/1.5B/embedding model was loaded for this
      test — verified via `ps aux | grep llama-server` showing nothing
      before and after both runs (this test exercises `run_agent()`/
      `_run_with_plan()`/`peer_cli.escalate()` wiring directly, not model
      inference, per the task's own scoping — a full 7B session was
      judged unnecessary since the mocked-`infer` path through the real
      entry point already proves the wiring).
      **Correction (rule 6):** an initial pass over-claimed the marker
      was "confirmed present in `history`" without actually checking —
      a follow-up check disproved it: the marker is folded only into the
      in-turn `messages` list, not into the `history` returned/saved by
      `run_agent()`, so it does not survive into a reopened session's
      transcript. **Positively re-confirmed live** (not just re-read from
      code) that the marker does reach the in-turn `messages` list seen
      by the model on the next call — a 3rd driver run printed the exact
      `messages` passed to the mocked `infer()` and the marker text was
      present verbatim. Logged the persistence gap as `NEW-38` — Confirmed
      for the `[PATCH_FAILED, UNRESOLVED]` case (live-reproduced),
      Suspected-by-code-inspection only for NEW-2's `[EDIT NOT APPLIED]`
      (same append site, not separately live-reproduced) — rather than
      fixed here (out of this task's scope).
      **Scope caveat:** all three driver runs used deliberately
      non-identical `old_str` values per attempt (dodging the pre-existing
      exact-duplicate-tool-call guard, `NEW-36`, same convention the unit
      tests use) — so this verifies the varied-old_str repeat path only;
      `NEW-36` (Confirmed) notes the exact-repeat case, which it calls the
      *more* common real-LLM failure mode, still bypasses this escalation
      entirely, unchanged.
      **NEW-19's core escalation/marker-firing logic (console/log +
      in-turn model context, varied-old_str repeat path) is fully
      live-verified working as designed; NEW-19 is done for that scope —
      the transcript-persistence gap is tracked as `NEW-38` (not fixed),
      and the exact-repeat gap remains `NEW-36` (not fixed), both
      pre-existing/adjacent, not regressions from this round.**
- [x] `NEW-25` — `codeyOS --daemon` forwards a literal `$@` string
      instead of real args (backslash-escape bug outside the heredoc).
      **Resolved 2026-07-30, code-reviewer approved** — 1-character fix
      (removed stray backslash), matches the already-correct direct-mode
      pattern elsewhere in the same file. See `NEW_ISSUES.md`'s `NEW-25`
      entry for the review detail.
- [x] `NEW-10` — `main.py` has no `SIGTERM` handler at all. **Resolved
      2026-07-30, code-reviewer approved.** Installed a module-level
      `_sigterm_handler` that only `raise SystemExit(128 + signum)` (no
      I/O/cleanup inside the handler itself), registered as the first
      statement in `main()` — reuses the 4 real
      `try/except (KeyboardInterrupt, SystemExit): shutdown()` guards
      around `loader.load_primary()` (not 14 as originally scoped; only
      4 of the 14 `shutdown()` call sites are actually exception-guarded,
      caught during implementation). Mirrors how `SIGINT` already works
      via Python's default handler — zero new shutdown-calling logic.
      code-reviewer independently confirmed placement, guard reuse,
      `shutdown()`/`SIGINT` untouched, the daemon-mode handoff (`core/daemon.py`
      installs its own `SIGTERM` handler shortly after, verified no
      unsafe window), and reproduced real signal delivery
      (`kill -TERM` → `SystemExit(143)` caught) independently. **Caught
      and corrected a rule-6 issue before commit:** the implementer's own
      self-flagged follow-up (`NEW-40`) originally claimed the REPL's
      `input()`-wait guard was "same as SIGINT already does today" —
      code-reviewer found this false (that guard DOES catch/clean up
      `SIGINT` today, so `SIGTERM` is newly asymmetric there, not at
      parity) — corrected in both `NEW_ISSUES.md` and the code comment
      before commit. Two adjacent gaps logged, not fixed: `NEW-39`
      (unrelated pre-existing test fragility found along the way) and
      `NEW-40` (two REPL code paths outside the 4 model-load guards still
      don't run `shutdown()` on `SIGTERM`, not a regression but a real
      gap). No live-verifier pass needed for the mid-load orphan-prevention
      claim specifically (real signal delivery was independently
      reproduced by both implementer and code-reviewer without a model
      load, per rule 2) — the model-load window itself remains
      reasoned-not-live-exercised, consistent with RAM discipline.
- [ ] `NEW-12` residual items 2–4 (only item 1 was fixed in Round 11):
      no single named `SERVER_PORT` constant across
      `loader_v2.py`/`inference.py`/`inference_hybrid.py`; the 1.5B
      planner's config (`PLANNER_MODEL_PATH`/`PLANND_SERVER_PORT`) is
      defined but never wired into any launcher, and `docs/configuration.md`
      documents the wrong default; no real cross-process flock/pidfile
      lock closes the daemon-vs-CLI port race (only an HTTP probe exists).
      Worth doing alongside Phase 5a below since 5a is also touching the
      loader/config surface.
- [ ] `NEW-22` residual — `codey-start` and `codeyOS` each still
      independently reimplement the same GUI-launch/PID-file/trap-kill
      pattern (confirmed still present at HEAD). Adjacent to `NEW-12`'s
      dual-launcher class.
- [x] `NEW-8` — `ccos/tests/test_ccos.py::test_sandbox` fails on this
      device. **Resolved 2026-07-30, code-reviewer approved.** Root
      cause: `ccos/core/sandbox.py`'s `ALLOWED_DIRS` hardcoded `"/tmp"`,
      but `Sandbox.__init__`'s own `tempfile.mkdtemp()`-created working
      directory resolves under Termux's real temp dir
      (`tempfile.gettempdir()`, i.e. `$PREFIX/tmp`) — the sandbox's own
      directory failed its own allowlist check, so every command
      (even `echo hello`) failed before running. Fixed by using
      `tempfile.gettempdir()` instead of the hardcoded string. 334/334
      full suite passing. code-reviewer independently confirmed the
      determinism of the `gettempdir()`/`mkdtemp()` pairing, assessed the
      security tradeoff (not a regression — the allowlist was never real
      containment; see `NEW-42`), and reproduced the test pass itself.
      2 adjacent findings logged, not fixed: `NEW-41` (pre-existing
      `Sandbox.cleanup()` `NameError` from a missing `import shutil`,
      silently swallowed) and `NEW-42` (the allowlist only gates `cwd`,
      not what a command actually touches — a design gap if this sandbox
      is ever relied on as a real security boundary).
- [ ] `NEW-7` — `[Recursive]` planner synthesizes whole duplicate
      functions instead of targeted patches (Confirmed, ~67% failure
      rate, not recursion-specific). Characterization is incomplete —
      the b3/b4 draws (loader_v2 error-handling and patch_tools rename
      prompts on the plain path) were never finished. Finish
      characterizing, then fix.
- [ ] Security hardening backlog (from `NEW_ISSUES.md`'s bottom section,
      never assigned NEW-IDs — give them IDs when picked up):
      command-injection-via-filename in `agent.py:863-865` (partially
      addressed, finish it); daemon shell allowlist too broad in
      `task_executor.py:47-52` (documented, not changed); Unix socket
      auth in `core/daemon.py` (peer-UID check exists, token-based auth
      recommended as a real enhancement, not yet built).
- [ ] `PROJECT_PLAN.md` Round 1's H-1 fallback path — mechanism-verified
      only, never live-triggered. Finish the live verification (rule 5:
      no claim stands on mechanism-verification alone).
- [ ] **Flag to Ish, don't default-fix:** `NEW-9`'s residual atfork race
      has already been escalated twice (Rounds 9 and 10, each an improvement
      but neither a full close, per CLAUDE.md's stop-and-escalate rule).
      This queue item is "get Ish's call on accept-residual-risk vs. a
      third attempt with a new angle," not "attempt fix #3" by default.

## Track 3 — Foundational architecture (the big one; strictly sequential, each step depends on the last)

This is `PROJECT_PLAN.md` Phase 5 (5a–5f) plus the two related
`PENDING_ISH_DECISIONS.md` items that share its foundation — sequenced
together here because building them separately would duplicate the
resource-awareness work twice.

1. [ ] **Phase 5a — Resource gate + slot-aware loader.** Foundation;
       everything below depends on it. Give `loader_v2` a slot concept;
       build the single resource-gate authority (device_manager + live
       sysmon/thermal/observability, headroom-minus-margin, never a
       hardcoded number); migrate `core/daemon.py`'s three existing
       direct `get_loader()` calls onto it. Fold in `NEW-24`
       (`load_secondary()` doesn't exist) as part of this work. Use
       `NEW-14`/`NEW-18`/`NEW-21`'s swap/RAM observations as validation
       data for the safety-margin sizing.
2. [ ] **`PENDING_ISH_DECISIONS.md` item 2 — daemon control redesign.**
       Sequence directly alongside/after 5a since it needs the same
       resource-gate authority: `daemon_shutdown` becomes an autonomous
       thermal/CPU tripwire, `command` becomes queue-only, daemon never
       runs while TUI/GUI is active, queue consumption gated on the same
       live headroom check 5a builds. `core/observability.py`'s wrap
       (item 4) folds in here. **Status: currently 100% decisions-on-paper,
       zero implementation** (confirmed by inspecting the live
       `daemon_control/manifest.json` — still pre-decision shape).
3. [ ] **Phase 5b — Task classifier + tier config**, coding domain only.
       Reconcile with (don't duplicate) `core/orchestrator.py:is_complex()`
       and the daemon's separate `planner_client`/`planner_v2`/
       `planner_service` paths. Planner model family choice stays
       deferred to this phase's on-device validation. Benefits directly
       from Track 1's prompt audit having already landed.
4. [ ] **Phase 5c — Wrap `core/agent.py` as a real CCOS capability**,
       migrating both existing call paths (`main.py` for CLI/GUI,
       `core/task_executor.py` for the daemon) onto one boundary, with
       the wrapper owning its own permission surface explicitly. This
       is also where Phase 2 item 7's deferred work (wrapping recursive
       self-refinement) gets picked back up — same capability boundary.
       Benefits from Track 1's tool audit having already landed.
5. [ ] **Phase 5d — In-flight context-passing fix + task-context
       blackboard**, designed together: `plugin_manager.call_capability`
       gets a threaded context argument (fixing `skill_recombiner.py`'s
       generator, not hand-patching generated files); new scoped
       task-context table for durable cross-step handoffs — not a
       general shared-memory grant, not a repurposing of `ccos_memory`'s
       existing tables.
6. [ ] **`PENDING_ISH_DECISIONS.md` item 3 — peer CLI escalation redesign.**
       Sequence here, after item 2's queue and 5d's blackboard exist,
       since its design (daemon pulls an item needing escalation out of
       the main queue, parks it on a separate review list, notifies the
       user, keeps working the rest of the queue) directly reuses both.
       Currently 100% design-only, zero implementation.
7. [ ] **Phase 5e — Wire `agent_orchestrator`'s deliberation to real
       execution.** Cheap (heuristic, not model-backed) but the Safety
       Agent's veto becomes live against real actions for the first
       time — treat that as a behavior change to flag, not just a wiring
       task. Depends on 5c (coding agent must be a capability to be a
       routing target).
8. [ ] **Phase 5f — Multi-domain request splitting** (e.g. "research X,
       then implement it"). Depends on 5c, 5d, and 5e — first point
       where capability-as-plugin, context-passing, and the durable
       blackboard all compose.

## Track 4 — Docs & lower-priority cleanup (interleave anytime; no hard blockers on Tracks 0–3)

- [ ] `docs/architecture.md` rewrite — best done after Phase 5c lands, so
      it can describe the coding agent as an actual CCOS capability
      instead of describing a pre-Phase-5 state that's already stale by
      then.
- [ ] `docs/commands.md` gaps — 12 missing slash commands, ~13 missing
      CLI flags, one possibly-stale flag (`--rollback`).
- [ ] `ccos/core/telemetry_engine.py` dedup-key collision bug (uses
      timestamp+id() instead of uuid4()/an atomic counter) — real,
      pre-existing, causes intermittent test flakiness. Found during an
      unrelated rename-verification pass; still not fixed.
- [ ] TTS — both `core/voice.py` and `ccos/plugins/speech/tts_speech` are
      confirmed broken. Get one working, verify it, remove the other.
      STT has no CCOS equivalent at all regardless of the TTS outcome.
- [ ] Code quality backlog: unused imports (129 F401), line length
      (1343 E501), comparison style (74 E712) — none addressed yet.
- [ ] Testing gaps: no daemon-mode integration tests, no path-traversal
      tests.
- [ ] Security guide docs — unclear whether they reflect recent changes;
      needs a read-through to confirm.

## Parked — gated, not part of the active sequence

- **`PROJECT_PLAN.md` Phase 4 — self-improvement activation**
  (`auto_improvement_loop`, `capability_optimizer`, `skill_recombiner`,
  `goal_engine`). Per CLAUDE.md rule 1 and the phase's own gate: do not
  start until Phases 1–3 (done) plus a meaningful period of observed
  real-task operation through the sandbox/safety-veto path has actually
  elapsed, and Ish gives explicit, direct, in-session sign-off — not
  inferred from this queue reaching the end of Track 3. Revisit the
  activation criteria themselves (compound-skill approval gate, goal
  approval gate) when that time comes; don't pre-decide them here.
  **Update 2026-07-30 (`NEW-34`):** the Track 1 tool audit found 3
  compound plugins under `ccos/plugins/compound/` (`skill_camera_capture_tts`,
  `skill_info_info`, `skill_info_processes`) that were already-generated
  output of `skill_recombiner`, sitting in the repo since the initial
  CCOS commit, live and agent-callable despite the engine itself never
  having run this session — the gate on the *engine* didn't stop
  `plugin_manager._discover()` from auto-loading its *pre-existing
  output*. Ish asked for these turned off now as an interim safety
  measure, separate from any Phase 4 activation decision: renamed the 3
  directories with a leading `_` (an existing, already-supported
  exclusion path in `_discover()`, zero code changes, fully reversible,
  nothing deleted). Their final disposition — permanently remove, or
  keep and fix the broken pipeline-argument-passing bug — is still open
  and deferred to whenever Phase 4 activation is actually taken up; see
  `NEW-34` for full detail and the verification performed.

---

## Currently here

**Tracks 0 and 1 are now genuinely fully done (2026-07-30)** — the
earlier "fully done" claim was corrected mid-session per rule 6 when it
turned out 2 of Track 1's 4 items were still open; both are now closed:
the `recovery.py`/`strategy_tracker.py` comparison turned out to already
be resolved in Phase 2 (just undocumented until now), and `NEW-19` got a
direct decision from Ish, now a scoped Track 2 task. Next up: Track 2's
independent bug/security fixes (starting with the freshly-scoped `NEW-19`
implementation), which can run in parallel with starting Track 3's
Phase 5a.
