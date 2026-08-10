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

**As of 2026-08-08, `TODO.md` is the plain-checkbox view of this same
sequence** — start a new session there for "what's left and in what
order" without the evidence/history; come back to this file for the "why"
behind any specific `TODO.md` line.

---

## How new issues get logged as we go

Keep using `NEW_ISSUES.md` exactly as it already works — next sequential
`NEW-##` ID (currently next free, re-grepped 2026-07-31 during `NEW-7`
Round 22 scoping: **NEW-75**, the prior "NEW-60" note in this section
had already gone stale by the time it was last read — always re-grep
`NEW_ISSUES.md` for the actual current max rather than trusting a
remembered number, per the lesson two paragraphs below), rated
Confirmed or Suspected, same format as existing entries.
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
      Logged `NEW-34` (Confirmed): the 3 `skill_*` compound plugins under
      `ccos/plugins/compound/` were broken by construction (no data piped
      between pipeline steps) **and** were live, agent-callable output of
      the permanently-gated `skill_recombiner` — the recombiner engine
      being gated didn't stop `plugin_manager._discover()` from
      auto-loading its pre-generated output. Interim-disabled via `_`-prefix
      rename 2026-07-30, then **permanently deleted 2026-07-31 on Ish's
      direct instruction** (`git rm -r`) — NEW-34 closed. Also logged
      `NEW-35` (Suspected): `vision.camera_capture`'s
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
- [x] `PLANNER_PROMPT` rewrite (`core/plannd.py`) — **round done
      2026-07-31, CODE COMPLETE + LIVE-VERIFIED, COMMITTED (`d674a0c`,
      2026-07-30 22:29 local) — stale "UNCOMMITTED, pending Ish" note
      corrected 2026-07-31 after verifying `git log -- core/plannd.py`
      directly; the commit already matches this entry's description
      verbatim, nothing was actually pending.** A live-verifier session
      ran a real, RAM-disciplined
      1.5B-only planner test against port 8081 (2 clean model-load
      cycles, 7B never loaded), cross-referencing the Track 1 prompt
      audit above (`NEW-28`/`NEW-29`/`NEW-30`/`NEW-31`/`NEW-32`).
      Live-confirmed `NEW-28` with a sharpened mechanism (traced to
      `core/plannd.py:162`'s `return kept if len(kept) > 1 else
      steps[:2]` — a well-formed Create → Edit → Run plan is exactly the
      shape where the surviving Run step suppresses the `steps[:2]`
      fallback that would otherwise rescue the dropped Edit step; status
      unchanged, still Confirmed/not fixed). prompt-engineer then went
      through 4 iterations of `PLANNER_PROMPT` edits (plus one implementer
      fix to `_TOOL_VERBS` for `NEW-28`), each reviewed by code-reviewer
      and re-tested by live-verifier. Resolved this session, live-verified
      against the current **uncommitted** prompt text:
      - `NEW-28` (`_TOOL_VERBS` regex fix) — supported/confirmed fixed.
      - Repeated-`Run` under-generation regression (introduced by iter 1,
        fixed by iter 2) — live-confirmed 3/3.
      - `NEW-47` (unrequested `Run:` step) — its decisive case now
        **5/5 pass** after iter 4 (pinned config, deletion-only fix); see
        `NEW_ISSUES.md`'s corrected `NEW-47` entry for the full
        4-iteration oscillation history before landing here.
      - `NEW-46` (few-shot content leakage on edit-only prompts) — its
        specific original trigger (surface-form mismatch vs. the
        `Edit <file>:` template) is fixed, 2/3 pass on the regression
        guard. **The 1/3 failure was a different leak source, not a
        return of the same bug — now tracked as new finding `NEW-50`,
        still open. Do not read `NEW-46` as fully closed.**
      New findings surfaced and left open this session (see
      `NEW_ISSUES.md`'s new 2026-07-31 "`PLANNER_PROMPT` 4-iteration
      rewrite" section):
      - [ ] `NEW-50` (Confirmed, mechanism verbatim-traced, 1/3 on this
            prompt) — worked examples leak verbatim content into
            unrelated requests regardless of ✓/✗ labeling; broader than
            the specific instance `NEW-46` fixed. Not yet scoped to an
            implementer.
      - [ ] `NEW-51` (Confirmed, deterministic 0/3; causal link to this
            session's changes NOT established) — Rule 9 peer-CLI
            delegation format fails entirely on a fresh, previously
            untested phrasing ("Have gemini check payment_processor.py
            for race conditions") — no delegation step emitted at all,
            treated as a Create task instead. Open question: pre-existing
            gap vs. this session's regression — settling test (run same
            prompt against pre-session `HEAD`) not yet done.
      - `NEW-48` (Confirmed, code not prompt — `parse_steps()`'s
        truncation-warning heuristic false-positived 8/8 times on
        well-formed plans) remains open, out of this rewrite's scope.
- [ ] `NEW-48` — `core/plannd.py`'s `parse_steps()` truncation-warning
      heuristic (last-step-final-character check) false-positived on
      8/8 test prompts during the same 2026-07-31 live-verifier session,
      including plans independently judged clean/correct. Code, not
      prompt text — separate from the `PLANNER_PROMPT` rewrite above.
      Recommend loosening or dropping the heuristic; not yet scoped to
      an implementer.
- [ ] `NEW-49` — new Suspected finding from code-reviewer's review of the
      same session's `PLANNER_PROMPT`/`_TOOL_VERBS` fix: `core/daemon.py`
      lines ~166-194 hardcode step-1 = Create/full-rewrite semantics by
      position (`i == 0`) regardless of the step's actual verb, so an
      Edit-first multi-step plan (now more reachable thanks to the
      `NEW-46`/`NEW-47` planner-prompt rewrite) gets told to overwrite the
      whole file instead of making a targeted edit. Not live-reproduced;
      not yet scoped to an implementer. See `NEW_ISSUES.md`.
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
- [x] `NEW-12` — **fully closed 2026-07-31.** Items 2 (named port
      constant) and the docs/install.sh mismatch part of item 3 turned
      out to already be fixed in an earlier, unlogged round — corrected
      the record (rule 6) before starting. Items 3's core ask (real
      planner launcher) and 4 (real cross-process lock) implemented:
      `core/loader_v2.py`'s `LlamaServer.start()` now takes an flock'd
      per-port lock closing the daemon-vs-CLI TOCTOU race; a new
      `core/planner_loader.py` gives the 1.5B planner a real launcher,
      wired into `core/plannd.py:get_plan()`, with a `SWAP_GUARD`-backed
      sequential swap ensuring the primary 7B and planner are never both
      resident (Ish's direct decision — sequential-only, not concurrent,
      deferring true resource-gating to Track 3 Phase 5a). First
      code-reviewer pass rejected 3 real bugs (thermal-restart bypassing
      the swap guard; asymmetric fail-open eviction; a test that could
      spawn a real model); all fixed and independently re-verified
      (reviewer hand-reverted the fix to prove the regression test
      actually catches it). Committed `ea14d7f`. **Live-verified on real
      hardware** (`cea15a6`) — full round-trip 7B↔1.5B swap, no
      double-residency at any sampled checkpoint, the flock
      contention/timeout branch exercised live for the first time (unit
      tests only, before). `NEW-68`'s ~190s timing estimate held up
      under real measurement. 4 new minor findings logged along the way
      (`NEW-71`–`NEW-74`), none blocking. One deliberately-deferred gap,
      not fixed: `NEW-69` — interactive-CLI direct loads (`main.py`)
      bypass the swap arbiter entirely; a naive fix would break normal
      CLI use whenever the daemon has a planner loaded, so this needs a
      real cross-process arbitration mechanism, not a quick patch —
      flagged for Ish/project-architect, adjacent to Track 3 Phase 5a.
- [x] `NEW-22` — **fully closed 2026-07-31.** `codey-start` and `codeyOS`
      each independently reimplemented the GUI-launch/PID-file/trap-kill
      pattern; extracted into a shared `lib/gui_launch.sh`, sourced by
      both. Also converged a real drift between the two (trap signal set:
      `EXIT`-only vs `EXIT INT TERM`) onto `EXIT`-only, after live-testing
      showed no promptness benefit and that trapping INT was actively
      wrong given how `main.py` catches `KeyboardInterrupt` and keeps
      running. Code-reviewer approved after independently re-testing the
      fresh-start, already-running short-circuit, and SIGTERM-trap paths
      directly. Committed `caf83f1`. No model load involved, so no
      live-verifier pass needed for this one. `NEW-67` logged, not
      fixed: `codey-stop` has its own third, separate stop-by-PID-file
      block for the same PID file — a project-architect scoping call for
      a future round, not part of this fix.
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
      functions instead of targeted patches (Confirmed, not
      recursion-specific). Characterization COMPLETE on the
      `old_str`-grounding question (Round 20). A prompt fix landed
      (`0026565`, `prompts/system_prompt.py`/`critique_prompts.py` —
      explicit verbatim-`old_str` instructions, worked wrong/correct
      examples) and was LIVE-VERIFIED in Round 21 (2026-07-30,
      NEW_ISSUES.md) with a MIXED result — confirmed the fix text is
      actually present in the rendered draft prompt, so this is a real
      measurement, not a null test. Re-running the same
      docstring-insertion prompt 6x: on the narrow `old_str`-grounding
      metric, failure rate dropped 67% (4/6, pre-fix) → 50% (3/6,
      post-fix); but on the baseline's own originally-stated
      task-completion metric ("failed to produce a valid patch on the
      prompt"), the rate is UNCHANGED at 67% (4/6 both before and
      after), because a new failure mode — wrong-function targeting
      (2/6 draws edited `run_agent`/`parse_args` instead of `shutdown`,
      one with a real/correctly-grounded `old_str` for the wrong
      function) — replaced one instance of the old grounding failure.
      The current fix's verbatim-`old_str` instructions do nothing for
      wrong-function targeting even in principle. The loader_v2 prompt
      style (a3, b3)'s distinct no-`patch_file`-attempt finding remains
      separately unresolved. Related, out-of-scope findings from Round
      20 logged separately as `NEW-43`; new findings from Round 21
      logged as `NEW-44` (wrong-function targeting) and `NEW-45`
      (undocumented second "Stage and commit" confirm, a test-harness
      gap).

      **Round 22 scoped 2026-07-31 (project-architect, desk only, no
      live session run this pass): decided (b) — a larger, pre-registered
      sample re-run FIRST, not a prompt iteration.** At n=6 a 2/6
      observation has a ~6%-71% confidence interval; landing a
      target-identification prompt edit now and re-verifying at n=6
      again would be unfalsifiable — a 2/6→1/6 result is indistinguishable
      from noise. This round is a **live-verifier task, no code change**,
      to be run before any further prompt edit. Task, handed to
      live-verifier for the next live session:
        1. **Pre-registered 4-bucket taxonomy per draw**, not pass/fail:
           (i) grounding failure (empty/nonexistent `old_str`), (ii)
           wrong-target (real `old_str`, wrong function — `NEW-44`),
           (iii) no `patch_file` attempt at all (loader_v2's separate
           finding — count, don't fold into "failure"), (iv) success.
           Round 21's confusion came from two silently-different metrics.
        2. **Two fixtures, interleaved draws** (not all-of-A-then-all-of-B,
           so an inference-budget truncation mid-run — as already
           happened to `NEW-30`'s pass — still leaves an interpretable
           result): (a) the existing `main.py` (68174 chars, many
           candidate `def`s — the current confound `NEW-44` flags), and
           (b) one new small, few-function fixture file with an
           unambiguous `shutdown`-style target, to separate fixture
           complexity from base-model tendency.
        3. **State the outcome's claim size up front, in the handoff and
           in the log afterward**: if achievable n this cycle is ~12, the
           round's claim is "does wrong-function-targeting reproduce
           across a second session and a second fixture" (a yes/no
           reproducibility verdict promoting `NEW-44` Suspected→Confirmed
           or not) — NOT a rate estimate. Do not write a percentage into
           `PROJECT_LOG.md`/`NEW_ISSUES.md` this sample can't support.
        4. **Pre-run blockers, both must be verified before the model
           loads:** (a) every fixture file path resolves inside
           `WORKSPACE_ROOT`/passes `_validate_path()` — two prior live
           passes (`NEW-30`) were invalidated by exactly this, don't
           repeat it; (b) the scripted harness answers BOTH confirms per
           `NEW-45` (`--yolo` to suppress `Apply patch?`, explicit `n`
           answers to the "Stage and commit" confirm, `/undo <file>`
           between draws instead of `git checkout`) — get code-reviewer
           eyes on the harness script itself before running, since a
           harness bug on this exact issue already produced 3 unintended
           real commits in Round 21.
        5. RAM discipline per CLAUDE.md rule 2: `free -h` before/after,
           one model-load cycle, confirm unload via
           `ps aux | grep llama-server` before considering the cycle
           done.
      Only after this reproducibility verdict lands should a
      target-function-identification prompt iteration (option (a)) be
      scoped to prompt-engineer — deliberately deferred, not decided
      against.
      **Minor doc-hygiene finding, logged not fixed:** `NEW_ISSUES.md`'s
      `NEW-7` entry header says "(Confirmed...)" but its first bullet
      still reads "**Confidence: Suspected.**" — original Round 1 text,
      now stale/inconsistent with the header. Needs a "history only"
      marker next time this entry is touched.

      **Round 22 EXECUTED 2026-07-31 (live-verifier, real on-device
      session) — verdict: `NEW-44` did NOT reproduce.** 12 draws (6
      interleaved per fixture) run in one model-load cycle via
      `core/task_executor.py`'s `TaskExecutor._execute_task` (harness
      deviated from the literally-specified `--yolo`+scripted-confirms
      mechanism — safer alternative, both confirms structurally
      unreachable via `_in_subtask=True`; deviation and rationale fully
      disclosed in `NEW_ISSUES.md`'s Round 22 write-up). Result: **0/12
      wrong-target, 0/12 no-attempt, 3/12 (25%) grounding-failure — all 3
      on `main.py`, all the same hallucinated one-line-`pass`-stub variant
      seen in the original pre-`0026565` baseline — 9/12 (75%) success.**
      Fixture B (new small fixture) was 6/6 success with zero failures of
      any kind. Full per-draw table, raw `old_str` values, RAM numbers, and
      methodology disclosure in `NEW_ISSUES.md`'s "Round 22 (`NEW-7`/
      `NEW-44`) pre-registered reproducibility pass" section and
      `NEW-44`'s entry (downgraded per CLAUDE.md rule 6, not closed).
      **Recommended next step: do NOT scope the target-function-
      identification prompt iteration (option (a)) now** — no confirmed
      problem for it to fix at this sample size. If any future round wants
      to strengthen `NEW-7` further, the evidence points at reinforcing the
      EXISTING `0026565` grounding fix against the specific
      hallucinated-one-line-stub assumption (recurred 3/3 times it
      occurred, always on `main.py`, never on the small fixture), not at
      adding new wrong-target-identification instructions. `NEW-7` stays
      open on this narrower grounding-failure basis.
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

- [ ] **7B coder system-prompt round (`prompts/system_prompt.py` +
      `prompts/layered_prompt.py`) — scoped 2026-07-31; first live pass
      done 2026-07-31, result bigger than scoped, round NOT done.**
      **CORRECTION, 2026-07-31 (rule 6): a second live pass also ran this
      session and BOTH passes are now invalidated by a workspace-boundary
      contamination bug (scratch test files placed outside
      `_validate_path()`'s allowed root) — see the "Currently here"
      section below and `NEW_ISSUES.md`'s new `NEW-30`/`NEW-56`/`NEW-60`
      correction section for the corrected, current status. The
      "first live pass" detail retained just below this line is history,
      not current status.**
      Analogous to the just-completed 1.5B `PLANNER_PROMPT` round above,
      but targets the 7B coder's own prompt, with only the 7B model ever
      loaded. Full scope, mechanism, test matrix, and explicit
      in-scope/deferred decisions below. Anchor finding: `NEW-30`
      (corrected framing, see `NEW_ISSUES.md`). Adjacent findings pulled
      in from this round's desk scoping: `NEW-49`, `NEW-52`, `NEW-53`,
      `NEW-54`.
      **First live pass (2026-07-31, 7B-only port 8080, one clean
      load/unload cycle, PID-tracked):** ran `NEW-30`'s test — hand-crafted
      `daemon.py`-style step-enrichment strings fed to
      `TaskExecutor._execute_task`'s real entry point. 5 of 6 attempted
      trials reached a terminal state before an inference-time budget
      forced a stop before the planned case 3. Result: `NEW-30`'s original
      hypothesis ("Done." right after `read_file`) did NOT reproduce, but
      `patch_file` was also never called in any completed trial —
      including a control case needing no read-then-edit resolution at
      all — so the intended fix outcome didn't occur either. **`NEW-30` is
      NOT fixed; the prompt diff stays code-reviewer-approved but held
      back, unstaged/uncommitted.** A recursive critique/refine layer
      (`core/recursive.py`) hypothesis was raised and has since been
      **investigated and refuted for the observed trials** (see the
      desk-investigation note directly below) — do not read the phrase
      "root cause suspected" as still live; the corrected next steps are
      below. `NEW-49`'s planned test (case 3) was
      never reached — still Suspected, undetermined, needs its own load
      cycle. Two new Confirmed findings surfaced and logged, not fixed:
      `NEW-55` (unguarded `input()`/`EOFError` crash at
      `core/agent.py:1676`, a real production daemon-path crash risk,
      being scoped as its own fix task separately) and `NEW-56` (7B
      `write_file` calls at wrong/fabricated paths on an Edit step, with
      one trial silently dropping the target file's existing content —
      distinct from `NEW-44`/`NEW-46`). See `NEW_ISSUES.md`'s corrected
      `NEW-30` entry and new `NEW-55`/`NEW-56` entries for full detail.
      **Desk investigation into the recursive critique/refine hypothesis
      (2026-07-31, project-architect, no code changed): hypothesis
      REFUTED for the observed trials, not confirmed.** Two gates rule
      it out: (1) `agent.py:1489`'s `_use_recursive = step == 1 and
      not is_qa` only fires on the agent loop's first turn — NEW-56's bad
      `write_file` calls were the loop's 5th turn (trial 1) and 2nd turn
      (trial 2), both plain `infer()` with full history, not recursion;
      (2) even on turn 1, `recursive.py`'s refine phase is unreachable
      for a standard single-file Edit message — `classify_breadth_need()`
      returns `"standard"` (not `"deep"`) absent long/complex messages,
      giving `max_depth=1`, and the `cycle >= max_depth` break
      (`recursive.py:485-498`) fires before refine's code
      (`:512-532`) ever runs. `recursive.py:388`'s
      `get_adaptive_depth(max_depth)` can additionally force `max_depth`
      to 0 under thermal-critical/battery-critical device state
      (`:171-220`), which would make even critique's own loop
      (`range(1, max_depth+1)`) empty — sharpening how reachability-gated
      this whole layer is. **`NEW-30`/`NEW-56`'s true mechanism is still
      unestablished.** Two real-but-latent bugs were found and logged
      anyway (`NEW-58` refine-blindness, `NEW-59` critique
      double-truncation) — worth fixing as hardening, NOT claimed to fix
      NEW-56. A third candidate, `NEW-57` (a context-surfacing gap in
      `agent.py`'s `read_file` handling), was initially framed as a
      `write_file`/`read_file` asymmetry and had to be corrected on a
      second pass — `core/memory_v2.py`'s store (used by `write_file`)
      and `core.context`'s store (used by the layered prompt's "files"
      block) turned out to be separate systems, and neither branch
      populates the latter in `agent.py`'s normal tool loop. `NEW-57` is
      now Suspected, not Confirmed — see the corrected entry.
      **Scoped next sub-tasks (implementer, in this order — reordered
      2026-07-31 after the recursive-hypothesis refutation left no
      established mechanism for NEW-56):**
        1. **Attribution logging (do this first, before any of the fixes
           below).** Log, per agent-loop turn, whether that turn's
           response came from recursion (draft/critique/refine) or plain
           `infer()`, and which tool name (not content) it produced.
           `_log_phase` already exists as a pattern to extend. With the
           anchor hypothesis refuted and no confirmed mechanism for
           NEW-56, this is the only item with a known payoff right now —
           spending a live-verifier cycle (260-450s/trial, this device)
           testing 2-3 speculative fixes blind would reproduce exactly
           the ambiguity that made the first live pass uninterpretable.
        2. `NEW-59` fix — remove `recursive.py:440`'s dead outer
           `draft[:2000]` truncation and raise/replace
           `layered_prompt.py:378`'s binding `prior_draft[:1500]` cut so
           a `<tool>{...}</tool>` JSON block isn't split mid-string
           (exempt the tool-call span from truncation, or truncate only
           surrounding prose). Cheap, contained, real even though latent.
        3. `NEW-58` fix — thread a `prior_draft` parameter through
           `_build_refine_prompt`/`build_recursive_prompt`'s refine
           dispatch (mirroring critique's existing `prior_draft` path),
           so refine can see and revise its own actual proposal instead
           of blind regeneration if/when refine is ever reached.
           Docstrings on `_build_refine_prompt` (`:390-409`),
           `_build_critique_prompt` (`:353-365`), and
           `build_recursive_prompt` (`:460-461`) must be updated to
           match once any of these land — they currently state priority
           maps and char caps that a fix would change.
        4. `NEW-57` — **held, not yet a fix task.** Needs the two-store
           question (`core.memory_v2` vs. `core.context`) reconciled
           first, and ideally one attribution-logged live pass (item 1)
           showing whether a read file's content is actually still
           attended to/reflected correctly at the turn a bad `write_file`
           occurs, before committing implementer time here. If a fix is
           later scoped, it must account for `core.context.load_file()`'s
           recurring prompt-budget cost (persistent re-injection at
           priority 4 into every later prompt, `layered_prompt.py:338`/
           `:432`), not just wire the call in.
      **Live-verifier pass after 1-3 land should re-run NEW-56's exact
      two cases** (genuinely-unread-file Edit step; control with file
      content already in prompt context) **plus read the new attribution
      log as the primary read-out**, not just the final tool call.
      Success criterion is unchanged from the last pass: `patch_file`
      actually gets called end-to-end on both cases — a pass that
      doesn't reach it is a failed fix, not inconclusive, per the
      already-established 4/4 no-`patch_file` baseline.

  **Mechanical definition of "act as the planner" (traced from code, not
  assumed):** production plan steps reach the 7B coder by exactly one of
  two paths, and they build the step prompt differently —
    1. `core/daemon.py`'s `_handle_command` (~lines 156-194) enriches each
       plannd step into a string (step 0: `"User's full request: {prompt}
       \n\nYour task (step 1/N): {step}\n\nWrite the COMPLETE file with ALL
       features described above. Do not skip any requirement."`; step
       i>0: `"Previous context: {prompt[:200]}\n\nYour task (step {i+1}/
       {total}): {step}\n\nComplete only this step."`), queues it as a
       task, and the daemon's task loop hands that exact string to
       `core/task_executor.py`'s `TaskExecutor._execute_task(prompt)`,
       which calls `run_agent(prompt, history=[], yolo=True,
       no_plan=True, _in_subtask=True)` after temporarily overriding
       `AGENT_CONFIG` (`_shell_fn`, `confirm_shell`, `confirm_write`) for
       the daemon shell allowlist.
    2. `core/orchestrator.py`'s `run_queue` (~lines 550-602) builds a
       different string (`"Overall goal: {original}\n\n{context_prefix}
       {file_context}{guidance}Current step: {task.description}"`, plus
       the `NEW-52` write_file-hint injection) and calls
       `run_agent(prompt, history=[], yolo=yolo, _in_subtask=True)`
       directly (no daemon involved) — this is `is_complex()`'s in-process
       planning path, not the plannd/daemon path.
  **Decision:** test via path 1's exact string templates and entry point
  (`TaskExecutor._execute_task`, or equivalently `run_agent` called with
  the same `no_plan=True, _in_subtask=True, yolo=True` flags and the same
  daemon `AGENT_CONFIG` overrides) — this is the path the just-fixed 1.5B
  `PLANNER_PROMPT` round's output actually feeds into for real plan
  execution, and it's the path both `NEW-30` and `NEW-49` concern. Do
  **not** start `core/daemon.py` or `plannd`'s HTTP server as processes —
  hand-craft the enriched strings ourselves, verbatim in daemon.py's
  format, standing in for what the 1.5B planner would now emit (per
  Ish's request), and call `TaskExecutor()._execute_task(prompt)` (or the
  equivalent direct `run_agent()` call) with only the 7B model loaded on
  its usual port. This isolates the 7B `system_prompt.py` measurement
  from both 1.5B planner noise and the `orchestrator.py` path's separate
  `NEW-52` contamination.

  **In scope:**
  - `NEW-30` (anchor): construct an Edit-step test where the target file
    has genuinely never been read this session (no prior step created or
    read it) — per daemon.py's own template this is a step i>0 case
    (`"Previous context: ...\n\nYour task: Edit <file> to <change>\n\n
    Complete only this step."`) or a single-step Edit plan. Discriminating
    test per this round's scoping: after the model's first-turn
    `read_file` succeeds, does it correctly emit `patch_file` on the
    *next* turn (per `system_prompt.py:216-219`), or does it say "Done."
    and stop (per `:143-146`/`:156`), leaving the edit never applied?
    Also run a **control** case — Edit on a file already shown in context
    from an earlier step (`run_queue`-style `file_context`, or daemon's
    same-session file already read) — where one `patch_file` call should
    suffice and NEW-30's contradiction should not fire. Both cases needed
    to isolate the bug from ordinary Edit-step behavior.
  - `NEW-49`: within the same model-load cycle, run one Edit-first
    2-step plan through daemon.py's real step-0 enrichment text
    (verbatim, "Write the COMPLETE file... Do not skip any requirement"
    applied to an Edit step) to see whether the 7B actually rewrites the
    whole file instead of editing it — converts NEW-49 from Suspected to
    Confirmed/Refuted using the real 7B, at negligible extra cost since
    the model is already loaded for the NEW-30 tests.
  - Full step-shape matrix, mirroring the shapes already live-validated
    on the 1.5B planner side: multi-step Create→Edit→Run, edit-only
    single-step, repeat-Run (e.g. run tests twice), and one
    Ask-peer-CLI-shaped step (see deferred note below on how to interpret
    that result).
  - Tool-completeness delta pass (see separate sub-task below) —
    desk-only, do first, no model load required.
  - Correct `NEW-30`'s status wording in `NEW_ISSUES.md` once a fix
    direction is chosen and live-tested (rule 7: code-complete vs.
    live-verified are different).

  **Deferred / explicitly out of scope for this round:**
  - `NEW-52` (`orchestrator.py`'s own write_file-hint hardcoding) — not
    fixed here; only used as a reason to prefer the `task_executor`
    path over `run_queue` for the hand-crafted tests, so it doesn't
    contaminate NEW-30/NEW-49 results. Left open for its own future round.
  - Actually starting `core/daemon.py` or `plannd`'s server process — the
    whole point of this round is 7B-only; daemon.py's *code* (its
    enrichment string templates) is used as a template to hand-craft
    prompts, but the daemon process itself is never started.
  - `NEW-54` (peer-CLI delegation has no tool-call surface, decided by
    regex on raw text before the system prompt applies): the
    Ask-peer-CLI test scenario should be run and reported, but its
    result tests `agent.py`'s `_detect_peer_delegation` regex matching
    against the enriched step string, **not** `system_prompt.py`'s own
    tool-calling instructions — report it as such, don't conflate it with
    a system_prompt.py finding.
  - `NEW-31`/`NEW-32` (critique-prompt template wiring, layered-prompt
    layer-name collisions) — out of scope, unrelated prompt-quality
    surface; not touched by hand-crafted single-step plan execution
    anyway (draft phase only, no critique/refine phase exercised by a
    single `run_agent` call per step).

  **Tool-completeness sub-task (separate from prompt-quality testing, per
  Ish's explicit ask) — desk-only, run first, no model load:**
  - Confirm whether the existing Track 1 CCOS plugin/capability audit
    (2026-07-30, `NEW-34`-`NEW-37` etc.) covered the tool set exposed to
    `core/agent.py`'s own tool-calling loop (the `TOOL_MAP` at
    `agent.py:49-70`: `read_file`/`write_file`/`patch_file`/
    `append_file`/`list_dir`/`shell`/`search_files`/`note_save`/
    `note_forget`) as opposed to the broader CCOS plugin surface — it did
    not; that audit's scope was `ccos/plugins/*/manifest.json` vs.
    implementation, a different layer. This round's delta, already found
    during scoping and logged (not yet fixed): `NEW-53` (`append_file`/
    `note_forget` unreachable — no word→tool trigger for either) and
    `NEW-54` (peer-CLI delegation not a real tool at all). Confirm no
    further gaps once the live test matrix above surfaces any (e.g. a
    tool the 7B tries to call that isn't in `TOOL_MAP` at all).

  **Pipeline:** prompt-engineer scopes/edits `system_prompt.py` text (this
  is prompt work, same as last round) → code-reviewer approves →
  live-verifier confirms with the 7B-only, single-model-load-cycle
  discipline (rule 2/3: `free -h` before, track the spawned PID, confirm
  unloaded after, one load cycle at a time, batch all test messages into
  one session). If a fix direction requires touching `daemon.py` or
  `agent.py` code (not just prompt text) — e.g. if the NEW-30 fix chosen
  is "orchestrator/daemon pre-injects file content" rather than a prompt
  wording change — hand that specific piece to implementer first, mirroring
  last round's `_TOOL_VERBS` implementer fix, then back through
  code-reviewer/live-verifier.

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
       (item 4) folds in here. **Status (updated 2026-08-10): sub-task A
       (resource snapshot + `/status` wiring) code-reviewer-approved and
       committed (`c48f77b`) — no process-lifecycle risk, code-complete
       is its correct final status. Sub-task B (TUI/GUI interactive-
       session signal, both halves in scope) code-reviewer-approved
       2026-08-10 after a round-1 rejection: a single shared
       `TUI_PID_FILE` let one TUI session's write, crash, or clean exit
       silently erase a different still-live session's presence (three
       distinct reproduced paths — overwrite, stale-reap, and a
       truncate-before-flock race); fixed by moving to one atomically-
       (`os.replace()`-)written file per session under `TUI_SESSIONS_DIR`
       instead of one shared file, ownership now structural rather than
       content-compared, with a real `os.fork()`-based two-distinct-PID
       test covering it (the first draft of that test would have passed
       even with the bug — hand-placed file, not a real second PID —
       caught before hand-off, not by review). GUI half approved
       unchanged in round 1: `gui/server.py`'s live `clients` websocket
       count, not GUI-process-liveness, is the signal, cross-checked
       against the GUI server's own PID file so a crash-while-clients-
       connected doesn't strand a false-positive "someone's watching."
       Not live-verified — this sub-task touches PID-file/lock logic per
       CLAUDE.md rule 4 (mandatory review, two rounds to converge) but no
       daemon dispatch/shutdown behavior actually changed yet (sub-tasks
       C/D). Not yet committed. **Sub-task C (gate queue dispatch on A+B,
       move planning to the pull side) is code-complete and
       code-reviewer-approved as of 2026-08-10** — claim-order (gate
       check before `try_claim_task()` in both branches), the `no_plan`
       inversion, `plan_only=True` path preservation, the `needs_planning`
       column migration, and `can_dispatch_task()`'s gate logic were all
       independently re-verified by code-reviewer, including a
       negative-control test proving the claim-order regression test
       actually catches a real regression if the ordering is reverted.
       Full suite verified at 496 passed, 1 skipped. Review also surfaced
       two findings logged to `NEW_ISSUES.md`: `NEW-113` (the
       `self.server.planner = self.planner` wiring in `Daemon.__init__`
       is now dead code — `_handle_command` no longer reads
       `self.planner`/`server.planner` post-restructuring) and `NEW-114`
       (a crash window between `add_tasks()` creating the new expanded
       multi-step rows and `complete_task()` marking the superseded raw
       row `done`, with no stale-`running` reaper anywhere in the
       codebase to recover an orphaned raw row if the daemon dies in that
       gap — a genuine new gap this sub-task's restructuring introduces,
       not a pre-existing one). Neither finding is fixed; both are
       explicitly out of scope for this sub-task per code-reviewer's own
       docs-only scoping of this round. **Sub-task C is now genuinely
       live-verified, 2026-08-10** (replaces the earlier held-pending-
       Ish's-go-ahead status — Ish's go-ahead was given and the
       live-verification criterion documented below was met in full; see
       the sub-task C section below for the verbatim evidence). **Sub-
       task D (`should_trip_shutdown` tripwire + retired socket
       `shutdown` handler) is code-complete, code-reviewer-approved, and
       also now live-verified 2026-08-10**, with one scope caveat on the
       slot-release evidence (it's confirmed only for the embed-server
       model, not the primary model, for a structural reason — see the
       sub-task D section below) and one evidence item
       (`free -h` before/after) not captured in this pass. One new
       finding surfaced live during this round's verification, not
       previously known: `NEW-118` (Confirmed) — the watchdog tick that
       fires the autonomous shutdown tripwire doesn't short-circuit the
       rest of that same tick, so the model-load watchdog still runs
       immediately afterward (harmless in this run only because the
       resource gate independently denied that load). **Sub-task E
       remains 100% unstarted** (confirmed by inspecting the live
       `daemon_control/manifest.json` — still pre-decision shape) — the
       only piece of this round not yet begun.

       **Scoping pass complete, 2026-08-09 (project-architect, desk-only,
       no code changed).** Two premises in the original decision text
       don't match the live code and are corrected here:
       - `daemon_shutdown` is **not** in
         `ccos/plugins/system/daemon_control/` — it's `core/daemon.py:1148`
         (calling the socket `"shutdown"` cmd, handled by
         `DaemonServer._handle_shutdown` at `core/daemon.py:347-352`). The
         plugin (`daemon_control.py`) explicitly does **not** wrap it
         today — the plugin's own docstring already documents this
         correctly, pending exactly this decision.
       - Nothing in the shipped scripts calls the socket `shutdown`
         handler. `codeydOS stop` → `stop_daemon()` uses `kill -TERM
         $PID` (tracked PID) against the daemon's existing
         `_handle_sigterm`, not `send_command("shutdown")`. So retiring
         the socket path as a directly-triggerable action (sub-task D)
         breaks no current operational flow.

       `_handle_command` (`core/daemon.py:180-260`) already enqueues and
       returns immediately (`state.add_task`/`planner.add_tasks`) — it is
       *not* today's "direct run now" problem. The real "queue-only"
       violation is one line up: it runs the 1.5B planner
       (`send_plan_request_async`, up to a 180s `asyncio.wait_for`)
       **synchronously inside the socket handler**, at enqueue time,
       completely outside any resource gate. "Callers enqueue; the
       daemon pulls on its own schedule" means moving planning to the
       pull side (sub-task C), not building a new queue engine — the
       existing SQLite task queue (`core/state.py`'s `add_task`/
       `get_next_pending`/`cancel_task`, consumed by
       `Daemon._process_planner_tasks`) already is a plain FIFO
       add/delete-only queue, matching the decision's stated semantics
       as-is.

       No existing signal distinguishes "TUI/GUI process is up" from
       "a user is actually interacting" — the GUI's own `clients: Set[
       web.WebSocketResponse]` (`gui/server.py:122`) already tracks real
       connected browser sessions and is the correct signal to key
       mutual exclusion off; the GUI server *process* being alive
       (`codey-stop`'s `gui-server.pid`) is not, and using it would
       silently make the daemon do zero background work for the entire
       life of a `codey-start` session regardless of whether anyone is
       looking at the page. See `NEW-106`/`NEW-107`: `core/observability.py`'s
       `temperature`/`cpu_usage`/`memory_usage` properties are
       per-process/wrong-signal and must not be used as this round's
       thermal/CPU/RAM source — real signals already exist in
       `core/thermal.py`, `core/resource_gate.py`, and `core/sysmon.py`
       (whose `/proc/stat`-delta CPU sampler is never started by the
       daemon today).

       **Sub-task build order** (mirrors 7.4's 5-sub-task pattern,
       safest/no-daemon-behavior-change first; B–E all touch
       process-lifecycle-adjacent code and require code-reviewer
       approval per CLAUDE.md rule 4):
       1. **Sub-task A — resource snapshot + `/status` wiring (no daemon
          behavior change).** Add a rolling system-wide CPU% sampler
          (reuse `core/sysmon.py`'s `/proc/stat`-delta approach; a single
          rolling sampler updated on the existing 30s watchdog tick,
          not a duplicate cold-read helper, since sub-task D's 20-minute
          sustained-CPU tripwire needs the same history) plus real
          RAM headroom (`core/resource_gate.py`'s
          `read_meminfo`/`compute_headroom_bytes`) and real temperature
          (`thermal.get_current_temp_c()`), composed with existing
          queue-depth (`state.get_tasks_by_status`) into one snapshot.
          Confirm which battery source actually reads on-device
          (`core/sysmon.py:_read_battery()`'s two paths:
          `/sys/class/power_supply/battery/` first, `termux-battery-status`
          subprocess fallback — the fallback is a `termux-api` runtime
          dependency; if it's the one actually exercised, `install.sh`
          needs it per CLAUDE.md rule 11). Wire `core/observability.py`'s
          existing (but currently unwired) `status()` to a `/status` CLI
          handler in `main.py` (`PENDING_ISH_DECISIONS.md` item 4) —
          display-only, no daemon behavior change. No model load, no
          kill/PID/lock logic — the one sub-task of this round that
          plausibly doesn't require a mandatory code-reviewer pass under
          rule 4's own wording, though a lighter review is still
          expected per the normal pipeline.
       2. **Sub-task B — interactive-session signal (TUI confirmed in
          scope; GUI scope depends on one open question).** A
          PID-bearing, self-healing lock file for the TUI
          (`main.py`'s interactive session), written on start and
          removed on clean exit, stale-checked with `os.kill(pid, 0)` —
          same shape as `core/daemon.py:86-118`'s `check_pid_file()`,
          reused as the direct reference rather than inventing a new
          pattern. A bare flag file with no liveness check would leave
          the daemon permanently blocked after any TUI crash — same
          failure class this project has hit before with PID files.
          For the GUI: `gui/server.py`'s `clients` set already tracks
          real connected sessions; before implementing, confirm with
          Ish (or flag as a separate decision) whether the GUI half
          ships in this sub-task (server exposes a small "any clients
          connected" signal the daemon can read cross-process — e.g. a
          count written alongside the existing `gui-server.pid`) or is
          deferred — do not substitute GUI-process-alive as a stand-in
          for this signal.
       3. **Sub-task C — gate queue dispatch on A+B, move planning to the
          pull side.** **Scoped 2026-08-10 (project-architect, desk-only
          — that scoping pass itself changed no code). Code-complete and
          code-reviewer-approved
          2026-08-10 — see the round-level status note above for the
          verified specifics (496 passed/1 skipped, NEW-113/NEW-114
          logged, not fixed). Genuinely live-verified 2026-08-10 — see
          this sub-task's own live-verification criterion and evidence
          below.** Mandatory code-reviewer AND live-verifier — this is
          the first sub-task where daemon dispatch behavior actually
          changes (the daemon may now sit idle on a non-empty queue).

          **Finding that reshapes this sub-task's scope, logged as
          `NEW-112` (Confirmed):** `_handle_command`'s two enqueue
          branches (`self.planner.add_tasks(enriched)` for a multi-step
          plan, `self.state.add_task(prompt)` single-task fallback) have
          **zero live callers today**. Repo-wide search for every caller
          of the daemon's `"command"` socket cmd found exactly one:
          `core/planner_service.py:84-88`
          (`send_command("command", {"prompt": prompt, "no_plan": False,
          "plan_only": True}, timeout=185)`), called from
          `main.py`'s `_run_with_plan()` — and `plan_only=True` takes an
          early `return` (`core/daemon.py:209-242`) before either enqueue
          branch runs. `gui/server.py`'s WebSocket `"command"` message
          is unrelated (spawns a `main.py` subprocess directly, never
          touches the daemon socket). `codeyOS`'s own `send_command()`
          helper is only ever invoked with `"task"`/`"cancel"`.
          `daemon_control.py` deliberately doesn't wrap `command` at all.
          No test exercises the enqueue branches either. Practically,
          `command` today is a synchronous **planning-oracle RPC** used
          by the interactive CLI to get plan text back for local,
          step-by-step `run_agent()` execution — never a "hand this to
          the daemon's own queue" path. This makes the original
          response-contract worry (would callers relying on `"Plan
          created: N steps"`/`task_ids` in the immediate socket response
          break?) **moot**: `_request_daemon_plan()` reads only
          `response.get("plan")`; nothing anywhere reads `message`,
          `task_ids`, or `task_id`. No poll/notify replacement path is
          needed.

          **Resulting design, response-contract question resolved:**
          - **Keep the `plan_only=True` RPC path exactly as it behaves
            today** — synchronous, up to the existing 180s
            `asyncio.wait_for` timeout, returning `{"status": "ok",
            "plan": steps}` (or falling through to a plan-less response
            when the planner is unavailable/times out/returns ≤1 step,
            same as today). **This path is explicitly exempt from the
            new interactive-session gate** (sub-task B's
            `is_interactive_session_active()`): the caller of this RPC
            *is* the interactive session asking on its own behalf, not
            the daemon doing background work while a user is looking
            away. Gating it would make the daemon refuse to plan for the
            exact session that's asking — a self-deadlock, not a safety
            win. Do not apply the new predicate here.
          - **Strip the synchronous `send_plan_request_async` call out of
            the enqueue branches.** When `plan_only` is falsy (today
            dead in production, but per `daemon_control.py`'s own
            docstring this is real, intended-future functionality —
            "the real 'submit a new prompt for the daemon to execute'
            entry point"), `_handle_command` should just enqueue the raw
            prompt (`self.state.add_task(prompt, ...)`, one row, no
            planning, no enrichment) and return an immediate
            `{"status": "ok", "message": "Task queued", "task_id":
            <id>}` — the multi-step enrichment/`task_ids` shape goes
            away for this path because there is no plan yet at enqueue
            time. Add a way to mark a queued row as "raw, needs
            planning" vs. "already a concrete step" — the cleanest,
            smallest-diff option is a new nullable `task_queue` column
            (e.g. `needs_planning INTEGER DEFAULT 0`, set to 1 only by
            this raw-enqueue path; every existing/other caller's rows
            default to 0, i.e. "already concrete," preserving current
            behavior for both `_process_planner_tasks` branches
            untouched by this flag). Do not repurpose `dependencies` or
            any existing column for this signal.
          - **Move planning to the pull side.**
            `Daemon._process_planner_tasks()` (`core/daemon.py:998-1054`)
            gets a new step, before dispatch: for a claimed direct-command
            task with `needs_planning=1`, call `send_plan_request_async`
            there (same 180s timeout, same fallback-to-single-task
            semantics as today's socket-handler code, just relocated) —
            on ≥2 steps, replace the one raw row with the existing
            enriched multi-step `add_tasks()` shape (dependent tasks,
            same enrichment text as today) and clear `needs_planning`
            without executing anything this tick; on ≤1 step/timeout/
            unavailable, clear `needs_planning` and execute the raw
            prompt directly as today's single-task path already does.
            This is what makes "queue-only" (`PENDING_ISH_DECISIONS.md`
            item 2) real for whenever a future live caller uses the
            enqueue path, rather than fixing a path nothing currently
            calls.

          **The gating predicate.** New function `can_dispatch_task()`
          in `core/resource_gate.py`, named to parallel `can_admit()`
          (which it complements, not replaces — see relationship below),
          living next to it per WORK_QUEUE's "single resource-gate
          authority" framing, not duplicated into `observability.py`.
          Signature/shape: takes a `ResourceSnapshot` (sub-task A's
          `get_resource_snapshot()`) and an `interactive_active: bool`
          (sub-task B's `is_interactive_session_active()`) — both passed
          in, not read internally, so this function stays synchronous
          and trivially testable with synthetic snapshots, matching
          `can_admit()`'s own inject-everything test convention. Returns
          a decision with at least `allowed: bool` and `reason: str`
          (a small dataclass mirroring `GateDecision`'s naming, e.g.
          `DispatchDecision`, is fine, but doesn't need `GateDecision`'s
          cost/headroom/ceiling fields — those are model-admission-
          specific and don't apply to this coarse pre-check).

          **`can_dispatch_task()` vs. `can_admit()`:** `_execute_task()`
          (`core/task_executor.py:96`) already runs through `run_agent()`
          → the model-loading path, which already calls `can_admit()`
          with a real `ModelSpec` before any model loads. `can_dispatch_task()`
          must NOT re-simulate that admission decision — it's a cheap,
          coarse pre-check whose only job is to avoid claiming
          (`try_claim_task()`) a task the executor would immediately fail
          on for a resource reason, and to enforce the interactive-lock
          rule that `can_admit()` knows nothing about. Checks:
            1. `interactive_active` is `True` → refuse (this is the rule
               `can_admit()` has no equivalent of: never do daemon-
               initiated background work while a human is watching the
               TUI/GUI).
            2. `temperature_c is not None and temperature_c >=
               THERMAL_CONFIG["temp_critical"]` → refuse. Same threshold
               `can_admit()` already uses (`THERMAL_CONFIG["temp_critical"]`,
               currently 90°C) — one authority, not a second number to
               keep in sync.
            3. `battery_percent is not None and not battery_charging and
               battery_percent <= THERMAL_CONFIG["batt_critical"]` (5%)
               → refuse. Mirrors `core/recursive.py:get_adaptive_depth()`'s
               existing "not charging AND at/below batt_critical → treat
               as most-restrictive" convention exactly (same config keys,
               same not-charging gate) — reuse, don't reinvent.
            4. RAM: `ram_headroom_bytes` below a new named constant in
               `core/resource_gate.py` (e.g. `DISPATCH_MIN_HEADROOM_BYTES`)
               → refuse. This is the one leg with no existing project
               constant to reuse — pick a conservative, clearly-commented
               default grounded in this project's own swap-pressure
               evidence (`NEW-14`/`NEW-18`/`NEW-21`: swap onset observed
               as low as ~1.2GiB free before a load, severe pressure
               within seconds under a full 3-model stack) rather than an
               arbitrary number; something on the order of 1GiB is
               defensible from that evidence, but the exact value is
               implementer's to justify in the PR description and
               code-reviewer's to sanity-check — not a product decision
               requiring Ish.
            5. `cpu_percent is None` → **ignore this signal; do not
               refuse solely because of it.** Reason: `NEW-108` confirms
               `/proc/stat` is `Permission denied` on this device, so
               `cpu_percent` reads `None` unconditionally, always,
               regardless of actual load. Treating `None` as "fail
               closed" would permanently wedge dispatch on this exact
               device — the sub-task would be uncompletable and
               unlive-verifiable by construction, not merely degraded.
               This mirrors `can_admit()`'s own existing precedent for
               an unreadable temperature (`core/resource_gate.py:877-879`,
               "An unreadable temperature (None) is treated as 'no
               thermal objection'"): an unmeasurable signal is not
               evidence of a problem. When `cpu_percent` is a real float
               ≥ some high-load threshold, a future round MAY choose to
               gate on it (not scoped here — this sub-task's own CPU leg
               is effectively a no-op on this device today); if
               implemented, do not invent a new threshold — ask whether
               reusing `THERMAL_CONFIG["temp_critical"]`-style single
               ownership makes sense, or defer to sub-task D's own
               >90%-CPU tripwire work, which faces the identical
               NEW-108 constraint. **The returned reason string when
               `cpu_percent is None` and the decision is otherwise
               `allowed=True` must say the CPU leg was unmeasured**
               (e.g. `"within resource limits (CPU unmeasurable on this
               device, NEW-108 — not evaluated)"`), so a live-verifier
               reading dispatch-decision logs doesn't mistake "gate
               open" for "CPU confirmed low."
          - Battery-read caching, mandatory, not optional:
            `get_resource_snapshot()`'s own docstring
            (`core/resource_gate.py:460-470`) already flags that its
            default `read_battery_fn` shells out to
            `termux-battery-status` with a 2s subprocess timeout on every
            call, and warns a "hot, frequently-ticking loop" caller (this
            one — every `_process_planner_tasks()` tick) must supply a
            `read_battery_fn` that reads a slower-cadence cached value
            instead of the default. Do not wire the default battery
            reader directly into this dispatch loop; reuse whatever
            cached/rate-limited battery read this codebase already has
            for its 30s watchdog tick (same one sub-task A's rolling CPU
            sampler ticks on), or add a comparable cache if none exists
            yet — this is a hard requirement for this sub-task, not an
            optional optimization, or every tick pays an avoidable 2s
            subprocess cost.
          - **Claim-order requirement:** `can_dispatch_task()` must be
            consulted **before** `state.try_claim_task()` in *both*
            branches of `_process_planner_tasks()` (the planner-task
            branch, currently ~line 1017, and the direct-command-task
            branch, currently ~line 1057). Claiming first and gating
            after would strand a refused task in `running` status with
            no executor ever picking it back up. `planner.get_next_task()`
            (`core/planner_v2.py:160`) is confirmed side-effect-free (a
            pure peek over the in-memory dict, no state mutation) so
            calling it before the gate check is safe.

          **Sequenced build steps for implementer:**
            1. `core/resource_gate.py`: add `DISPATCH_MIN_HEADROOM_BYTES`
               constant (commented with its NEW-14/18/21 justification)
               and `can_dispatch_task(snapshot, interactive_active) ->
               DispatchDecision` per the checks above, in that priority
               order (interactive lock → thermal → battery → RAM →
               CPU-if-measurable), each independently unit-testable with
               synthetic `ResourceSnapshot`s (mirror `tests/
               test_resource_gate.py`'s existing convention).
            2. `core/state.py`: add the `needs_planning` column (default
               0) to `task_queue`'s schema + the same
               `ALTER TABLE ... ADD COLUMN` migration pattern already
               used for `dependencies`/`retry_count`
               (`core/state.py:87-95`); add whatever minimal accessor
               `_process_planner_tasks()` needs to read/clear the flag
               (a `state.get_task(id)["needs_planning"]` read plus a new
               `state.clear_needs_planning(id)` or equivalent — match
               existing method-per-mutation style in this file, don't
               overload `complete_task`/`fail_task` for this).
            3. `core/daemon.py` `_handle_command`: keep the
               `plan_only=True` branch's existing behavior unchanged;
               for the non-`plan_only` path, delete the
               `send_plan_request_async` call and the
               enrichment/`add_tasks` logic, replace with a single
               `state.add_task(prompt, needs_planning=1)`-style raw
               enqueue, return the new minimal response shape described
               above.
            4. `core/daemon.py` `_process_planner_tasks()`: before each of
               the two `try_claim_task()` calls, build a
               `ResourceSnapshot` (cached/rate-limited per the battery
               note above — do not call `get_resource_snapshot()` fresh
               every tick if that reintroduces the 2s battery subprocess
               cost; reuse/extend whatever cached snapshot sub-task A's
               `/status` wiring already produces if it's on a compatible
               cadence, or build a new lower-frequency cache specific to
               this loop if not) and `interactive_active` value, call
               `can_dispatch_task()`, and `return` (skip this tick,
               exactly like today's "nothing to do" early returns) when
               `allowed=False`. Log the decision's `reason` at `info`
               level on refusal so a live-verifier can see why the
               daemon is idling without needing to read source.
               Add the `needs_planning` pre-dispatch planning step for
               the direct-command branch as described above, before it
               falls through to `executor._execute_task()`.
            5. Tests: unit tests for `can_dispatch_task()`'s five checks
               (synthetic snapshots, no real hardware/model reads);
               a `_process_planner_tasks()`-level test that a refused
               dispatch decision leaves a task `pending` (never
               `running`) — this is the regression test for the
               claim-order requirement above; a test that a
               `needs_planning=1` task gets planned and expanded (or
               falls back to single-task) on the pull side, mocking
               `send_plan_request_async`.

          **Nothing in this sub-task requires Ish's direct input** — the
          response-contract question the parent task raised is resolved
          by NEW-112's evidence (no live caller depends on the removed
          synchronous response fields), and the CPU-None handling follows
          existing in-module precedent (`can_admit()`'s temperature
          fail-open) rather than inventing new policy. The one number
          without a reusable existing constant (`DISPATCH_MIN_HEADROOM_BYTES`)
          is implementer's/code-reviewer's call, not a product decision.

          **Live-verification criterion for this sub-task** (not just
          "tests pass"): with a real TUI session file present
          (`is_tui_session_active()` true) and a non-empty queue, observe
          via verbatim daemon log output that `_process_planner_tasks()`
          logs a refusal reason and the queued task's status stays
          `pending` across multiple ticks; then remove the session file
          and observe the same task get claimed and dispatched within
          one tick, with verbatim log/`--status`/DB-row evidence — not a
          paraphrase.

          **Live-verified 2026-08-10 — criterion met in full.** With a
          real PID-bearing TUI session lock file written to
          `~/.codeyOS/tui-sessions/` and a task inserted directly via
          `state.add_task()`, the daemon logged a real refusal
          repeatedly across ~40+ seconds and many ticks — verbatim
          `Daemon: dispatch deferred (direct task 1) — interactive
          TUI/GUI session active — deferring background dispatch` — and
          the DB row stayed `status=pending` throughout. After removing
          the TUI session file, the very next tick claimed and dispatched
          the task (`Daemon: executing direct task 1: echo
          LIVE_VERIFY_SUBTASK_C_MARKER...`, `started_at` populated in the
          DB). The task itself then failed at the model-load step
          because the resource gate independently denied the 7B load for
          its own reasons (headroom/thermal) — expected, and not a
          sub-task C bug; the dispatch-gating behavior under test worked
          exactly as designed. Daemon stopped cleanly afterward via its
          tracked PID, no traceback, `llama-server` confirmed clean
          (`ps aux | grep llama-server` showing only the grep), PID file
          removed. One test artifact was left behind in the real
          `~/.codeyOS/state.db` as a byproduct of this run: task id=1
          (`echo LIVE_VERIFY_SUBTASK_C_MARKER...`), `status=done` — see
          `NEW-120` (new finding, this round) for why a task that failed
          at the model-load step persists as `done` rather than `failed`
          (a pre-existing `_process_planner_tasks()` behavior, not
          introduced by this sub-task); this row is a test artifact, not
          production data, and was not cleaned up by this
          verification-only pass.
       4. **Sub-task D — `daemon_shutdown` autonomous tripwire; retire
          the socket-triggerable path.** Scoped 2026-08-10, following
          sub-tasks A-C's design conventions (`core/resource_gate.py`
          module-level rolling-history pattern, config-driven thresholds
          with an env override, explicit-reason dataclasses). Re-verified
          against current committed code (post B/C landing) before
          writing this: `_trigger_shutdown()` is now at
          `core/daemon.py:726-731` (moved from the :709-714 cited in the
          prior scoping pass — two sub-tasks have landed lines above it
          since), and its routing through `_main_loop()`'s `finally:`
          block (now `core/daemon.py:980-1013`, `get_loader().unload()`
          call at :994-998) to actually stop the detached `llama-server`
          process is unchanged and still correct.

          **RESOLVED 2026-08-10 — Ish chose option 3; implemented,
          code-reviewer-approved, and now live-verified. Retained below
          for the decision record and the full reasoning trail.**

          **BLOCKING OPEN QUESTION — needs Ish's direct decision, not
          implementer's, before this sub-task can be built:**
          `PENDING_ISH_DECISIONS.md` item 2 specifies the trip condition
          as "~20 minutes of sustained severe thermal + >90% CPU usage"
          — an AND of two legs. `NEW-108` (Confirmed, sub-task A)
          established `/proc/stat` is `Permission denied` on this actual
          device, so `sample_cpu_percent()`/`get_current_cpu_percent()`
          return `None` unconditionally, always — this round re-confirmed
          the same is true of `/proc/loadavg` and `os.getloadavg()`
          (`Permission denied` / `AttributeError`, checked live on-device
          2026-08-10), so there is no readable substitute CPU/load signal
          available on this hardware, not even a coarser proxy. If the
          CPU leg is kept as a strict `>90%` requirement, it can **never**
          be true on this device, meaning the whole tripwire can never
          fire here — code-complete forever, unlive-verifiable by
          construction, exactly what rule 7 exists to catch.

          This is deliberately NOT resolved the way sub-task C resolved
          its own CPU-None question (treat `None` as "unmeasured, don't
          refuse solely on it"). That precedent is directional and this
          is the opposite direction: `can_dispatch_task()`'s CPU-None
          fail-open makes an "allow work" decision more permissive on a
          missing signal — the safe direction for a false negative there
          is bounded (a dispatch that maybe shouldn't have happened).
          Here, a CPU-None fail-open on the *kill* condition would make
          an "end an autonomous safety trip" decision LESS likely to fire
          on a missing signal — a false negative here means the device
          keeps running hot for longer, unsupervised, which is the exact
          failure mode this tripwire exists to catch. Reusing C's
          precedent mechanically in the opposite-consequence direction
          would be deciding the policy question by analogy instead of by
          its own merits, so it isn't done here.

          Three options, presented to Ish rather than picked
          unilaterally:
          1. **Thermal-only fail path**: drop the CPU leg from the trip
             condition when unmeasurable (which is always, on this
             device), tripping on ~20 min sustained severe thermal alone.
             This changes the actual runtime behavior of the autonomous
             tripwire from the AND policy `PENDING_ISH_DECISIONS.md`
             describes to an effectively thermal-only policy on this
             specific hardware — a safety-relevant behavior change, not
             an implementation detail.
          2. **Keep the strict AND**, accept it is genuinely
             unlive-verifiable on today's device (document that
             explicitly as its own status, distinct from "not yet
             live-verified" — it would become verifiable on different
             hardware, with root, or with `psutil` available), and treat
             this sub-task as permanently code-complete-only until one of
             those changes.
          3. **AND with CPU-as-veto-only-when-measurable**: trip on
             sustained severe thermal alone whenever CPU is unmeasured
             (today, always, on this device), but require the real
             `>90%` CPU reading too on any future device/environment
             where the signal IS readable — same code path, condition
             degrades gracefully instead of picking one behavior forever.
          Recommendation, offered but not acted on unilaterally: option 3
          — it preserves the AND as the intended real-hardware behavior
          (matching the decision text) while still being buildable and
          live-verifiable on this device today, and it doesn't silently
          commit this codebase to "thermal-only" as if that were always
          the design intent. The asymmetry that makes this genuinely
          Ish's call and not implementer's: unlike sub-task C's dispatch
          gate (fail-open toward permitting work), this is a fail-open-
          toward-NOT-killing-the-daemon decision on a device's own
          overheat-protection mechanism — a false negative here changes
          how long the device is allowed to run hot unsupervised, which
          is exactly the class of call CLAUDE.md's "ambiguous product
          direction" escalation clause exists for.

          **Decided by Ish, 2026-08-10: option 3 (CPU-as-veto-only-when-
          measurable).** `should_trip_shutdown()` trips on sustained
          severe thermal alone whenever `cpu_percent is None` (today,
          always, on this device); on hardware/environment where a real
          CPU reading becomes available, the `>90%` requirement applies
          as a genuine second leg of the AND. Implementer builds this
          version of the predicate, not the strict-AND or thermal-only-
          permanent alternatives.

          **Everything below this point is implementer-ready regardless
          of which of the three options Ish picks** — only the body of
          one predicate function (`should_trip_shutdown()`, see below)
          waits on that answer; the surrounding structure, config,
          history-tracking, shutdown routing, and retirement of the
          external trigger do not change based on the answer.

          - **Thermal history — net new, does not exist today.**
            Sub-task A's `_cpu_history`/`sample_cpu_percent()`/
            `get_cpu_history()` (`core/resource_gate.py:270-353`) has no
            thermal equivalent: `core/thermal.py`'s
            `get_current_temp_c()` is a one-shot point read, and its
            private `_last_temp_snapshot` is inference-duration
            bookkeeping local to `ThermalManager`, not a queryable
            history. Build `sample_temperature_c()` / `get_temp_history()`
            / `reset_temp_sampler()` in `core/resource_gate.py`,
            mirroring `sample_cpu_percent()`/`get_cpu_history()`/
            `reset_cpu_sampler()` exactly: module-level `_temp_history:
            List[Tuple[float, float]]`, a `TEMP_HISTORY_MAX_AGE_SEC`
            pruning window (reuse or mirror `CPU_HISTORY_MAX_AGE_SEC`'s
            30-minute value — same 20-minute-window-plus-margin
            reasoning applies unchanged), and the same "None on read
            failure, never a fabricated 0.0" sentinel contract (a
            None thermal read must not look like "confirmed cool" any
            more than a None CPU read should look like "confirmed
            idle" — see `sample_cpu_percent()`'s own docstring for why).
            Unlike the CPU sampler, `read_current_temp_c()` is already a
            live, working signal on this device (confirmed: thermal
            reads succeed elsewhere in this codebase today) — this
            history-tracker will actually accumulate real samples here,
            unlike `_cpu_history`, which stays permanently empty on this
            device (state this explicitly in code comments so a future
            reader doesn't conclude the CPU leg "just hasn't tripped
            yet" — it structurally cannot populate on this hardware; see
            `sample_cpu_percent()`'s existing None-before-append
            behavior on read failure).
          - **Tick location**: the existing 30s watchdog block in
            `_main_loop()` (`core/daemon.py:941-975`), immediately after
            the existing `sample_cpu_percent()` call at :952-961, still
            **outside** the `if not _is_remote()` guard — the comment
            already at :945-951 justifying that placement
            ("CPU/thermal state is backend-independent, and 7.4 sub-task
            D's future 20-minute sustained-CPU tripwire needs an
            unbroken history regardless of local/remote backend") was
            written for exactly this sub-task and still applies
            unchanged to the new `sample_temperature_c()` call.
          - **Sustained-window check**: a new `should_trip_shutdown()`
            predicate in `core/resource_gate.py` (next to
            `can_dispatch_task()`, same `@dataclass(frozen=True)
            TripDecision(should_trip: bool, reason: str)` style),
            checking `get_temp_history()` (and, depending on Ish's
            answer above, `get_cpu_history()`) for both (a) a run of
            samples at/above threshold that (b) actually *spans* the
            required duration — not just N samples above threshold,
            which a freshly-started daemon with a couple of hot ticks
            right after boot could otherwise satisfy trivially. At the
            30s tick rate, ~20 minutes is ~40 samples; require the
            oldest-to-newest span of the qualifying run to be ≥ the
            configured duration AND a minimum fraction of ticks within
            that span to qualify (guards against one cool blip inside an
            otherwise-sustained run resetting the whole window to zero,
            which a naive "must be unbroken" check would do). A daemon
            restart clears both `_cpu_history` and the new
            `_temp_history` (process-global, matching sub-task A's
            existing behavior) — meaning no trip is possible for the
            first ~20 minutes after any daemon restart. This is intended
            (there's no persisted history across restarts to trip on,
            and a freshly-restarted daemon has no basis for concluding
            "sustained"), not a gap; state this in the docstring so it
            isn't mistaken for one later.
          - **Config**: `THERMAL_CONFIG` already has the right threshold
            for the thermal leg — `temp_critical` (90°C, the highest
            existing tier; there is no separate "severe" tier above it
            in `core/thermal.py`'s `_check_thermal_status()`, confirmed
            by reading it directly this round) is the correct value to
            reuse, not a new number. What's genuinely new: a duration key
            (e.g. `THERMAL_CONFIG["shutdown_trip_after_sec"]`, default
            1200 = 20 min) and, if Ish's answer keeps a CPU threshold in
            any form, a CPU percentage key (e.g.
            `THERMAL_CONFIG["shutdown_cpu_pct"]`, default 90). Both need
            an env-var override (precedent: `CODEY_N_CTX`, commit
            `0ae2690`; `CODEY_TEST_PRIMARY_ARCH`,
            `core/resource_gate.py:657-663`) so live-verification can run
            with a drastically lowered duration (e.g. 20 seconds instead
            of 20 minutes) without editing a committed default —
            otherwise this sub-task is unlive-verifiable in any
            practical session length, the same unlive-verifiable trap
            rule 7 exists to catch, just via a different mechanism than
            the CPU-signal question above. State explicitly in the
            module docstring that these thresholds must never be
            *permanently* lowered by committing a config edit — only
            overridden transiently via the env var for a live-test
            session.
          - **Shutdown routing**: on trip, `should_trip_shutdown()`
            itself does nothing but decide — the watchdog-tick call site
            in `_main_loop()` calls the daemon's existing
            `_trigger_shutdown()` (`core/daemon.py:726-731`) directly,
            never a raw `sys.exit()`/`os._exit()`/self-signal, so
            `_main_loop()`'s `finally:` block (`core/daemon.py:980-1013`)
            still runs and still calls `get_loader().unload()` to stop
            the detached (`os.setsid`'d) `llama-server` process —
            bypassing it would orphan a real model process holding real
            RAM while its gate slot gets reaped as dead, worse than
            today's already-known leaked-slot cases. **New risk this
            sub-task surfaces, not previously exercised**:
            `_trigger_shutdown()` calls `self.server.server.close()`
            directly; since (confirmed this round, via grep across the
            whole repo) nothing calls the socket `shutdown` handler in
            production today, this exact code path inside
            `_trigger_shutdown()` has plausibly never actually executed
            on a live daemon before. `_main_loop()`'s `finally:` block
            separately calls `await self.server.stop()`
            (`core/daemon.py:1009`) — sub-task D makes
            `_trigger_shutdown()` the *only* live way that combination
            gets exercised (autonomous trip -> `_trigger_shutdown()`'s
            explicit `.close()` -> loop exit -> `finally:`'s
            `.stop()`), so implementer must confirm no double-close
            traceback and a clean exit; this is now part of the
            live-verification criterion below, not assumed safe by
            inspection alone.
          - **No new "already tripped" persistence needed**: a concern
            that occurred during scoping — could a still-hot device
            immediately reload the model and re-trip in a loop right
            after an autonomous shutdown? — is already covered by
            existing machinery: `can_admit()`'s thermal check
            (`core/resource_gate.py:915-931`) denies any new model load
            while `current_temp >= temp_critical`, so a still-hot device
            cannot immediately reload the primary model regardless of
            this sub-task. No new "tripped" flag/cooldown file is
            needed; do not build one.
          - **Retire the socket-triggerable path.** Confirmed again this
            round (fresh grep across the whole repo, not trusting the
            prior pass's note): no shipped script calls the socket
            `shutdown` handler — `codey-stop`/`codeydOS` both use direct
            `kill -TERM`/`kill -9` on tracked PIDs, never the daemon's
            own socket protocol, and
            `ccos/plugins/system/daemon_control/daemon_control.py`
            explicitly declines to wrap it (its own docstring already
            states why, citing the same
            `PENDING_ISH_DECISIONS.md` item 2 this sub-task implements).
            "Retire" means: remove `self.register_handler("shutdown",
            self._handle_shutdown)` (`core/daemon.py:183`) and delete
            `_handle_shutdown()` (`core/daemon.py:359-364`) outright —
            not a no-op-with-log-line. Ish's own decision wording
            ("`daemon_shutdown` is **repurposed** from a directly-
            callable kill into an autonomous safety tripwire") describes
            a replacement, not a still-present-but-inert path; leaving a
            dead-but-registered handler around is exactly the kind of
            "restorable by accident" surface this project has been bitten
            by before. Also delete the module-level `daemon_shutdown()`
            helper (`core/daemon.py:1303-1305`) — confirmed this round
            (repo-wide grep) it has zero callers anywhere already, so
            there's nothing this deletion could break. After removal, a
            client that still sends `{"cmd": "shutdown"}` over the socket
            gets the dispatcher's existing generic
            `{"status": "error", "message": "Unknown command: shutdown"}`
            response (`core/daemon.py:594`) — an already-existing, clear
            failure path, not a new one this sub-task needs to design.
          - **Live-verification criterion** (mirroring sub-task C's
            concrete evidence bar, not "tests pass"): with the duration
            env-override set to a short test value (seconds, not
            minutes) and, if applicable per Ish's answer, thermal state
            genuinely elevated or the CPU condition satisfied per
            whichever option was chosen, on a **daemon-only harness**
            (per this project's own NEW-14 swap-pressure finding —
            do not run this alongside other concurrent model-load
            testing), capture verbatim: `free -h` immediately before and
            after the trip (rule 2); the accumulating per-tick warning
            log lines as the sustained window builds; the trip-fired log
            line itself with its `reason`; the daemon process exiting
            with **no traceback** (covers the `_trigger_shutdown()`
            double-close risk noted above); `ps aux | grep llama-server`
            showing only the grep itself afterward (not just "daemon
            process exited" — this is the whole point per the original
            spec); the daemon's PID file removed; and
            `resource_gate_state.json` showing no leaked slot for the
            unloaded model (directly implied by the `finally:` block's
            own existing comment about leaked slots wrongly counting
            against every future admission decision — this sub-task is
            the first to actually exercise that shutdown path for real).
          - This is a process-lifecycle change (kill logic, the daemon's
            only real shutdown-trigger surface) — mandatory code-reviewer
            approval per CLAUDE.md rule 4 regardless of size, covering
            both the autonomous trip logic and the retired external
            trigger in one pass (still true, unchanged from the prior
            scoping note) — plus live-verifier per the criterion above,
            not code-complete alone.

          **Live-verified 2026-08-10 — most of the criterion met, one
          item not supplied, one scope caveat on the slot-release
          claim.** With `CODEY_SHUTDOWN_TRIP_AFTER_SEC=70` and
          `CODEY_TEMP_CRITICAL_C=36` (real ambient measured at 37.0°C on
          this device), a fresh daemon accumulated the sustained-window
          history tick by tick — verbatim warning lines confirmed the
          window growing 0s → 30s → 60s of the required 70s ("insufficient
          history to conclude sustained... expected for the first
          ~duration after any daemon restart") — then fired: `Autonomous
          shutdown tripwire fired: sustained thermal trip (100% of
          samples over a 91s trailing window at/above 36 (most recent
          sample 37.0)); CPU unmeasurable on this device (NEW-108) —
          thermal alone sufficient per Ish's 2026-08-10 option-3
          decision`. The daemon exited cleanly with no traceback in the
          full log (confirms the double-close risk flagged above did not
          materialize — `_trigger_shutdown()`'s `self.server.server
          .close()` followed by `finally:`'s `await self.server.stop()`
          both ran without error), `ps aux | grep llama-server` showed
          only the grep afterward, the PID file was removed, and
          `resource_gate_state.json` showed `[]`.
          - **Evidence items supplied**: accumulating per-tick warning
            log lines, the trip-fired log line with its `reason`, clean
            no-traceback exit, clean `llama-server`/PID-file state,
            `resource_gate_state.json` showing no leaked entry.
          - **Evidence item NOT supplied this pass**: `free -h`
            immediately before and after the trip (rule 2), which the
            criterion above explicitly requires — not captured in this
            run's report. Stated here as unsupplied rather than assumed
            or inferred.
          - **Scope caveat on the `[]`/no-leaked-slot claim**: the
            primary 7B model never actually held a gate slot during this
            specific run — it was independently denied admission, both
            by the same `THERMAL_CONFIG["temp_critical"]` threshold this
            test had to lower to make the tripwire reachable at all
            (`can_admit()` and `should_trip_shutdown()` deliberately
            share this one threshold, per this sub-task's own design)
            and by real headroom pressure left over from an earlier
            harness mistake in this session. So `[]` genuinely proves
            slot-release only for the embed-server model (which WAS
            resident and released silently-on-success, as designed by
            this codebase's existing convention) — it does **not**
            re-verify slot-release for the primary model, and cannot be
            made to under the current design, since lowering
            `temp_critical` enough to make the tripwire reachable
            necessarily also denies the primary model's own admission
            through the same threshold. Decoupling the two thresholds
            (or finding another way to get a resident primary model into
            a tripwire-reachable test) would be required to close this
            gap in a future round; not scoped here.
          - **New finding surfaced live this round, not previously
            known**: `NEW-118` (Confirmed) — `_trigger_shutdown()`
            (`core/daemon.py:717-740`) only sets `self.running = False`;
            it does not `return`/`raise`/otherwise interrupt its caller,
            so the same watchdog tick that calls it continues running
            afterward, including `_watchdog_check_model()`
            (`core/daemon.py:1031`), which attempted a real 7B model
            load in the same ~1-second span as the trip firing (verbatim
            log evidence in NEW-118's write-up). Harmless in this run
            only because the resource gate independently denied that
            load attempt; on a device/config where it were admitted, the
            daemon would load a model and then immediately unload it via
            the same shutdown's `finally:` block — the exact leaked-slot
            failure class that block's own comment already warns about,
            now demonstrated reachable via a path (the shutdown
            tripwire) that did not exist before this sub-task. Not fixed
            this round (docs/logging-only); see NEW-118 for the
            described shape of a fix.
       5. **Sub-task E — `daemon_control` plugin/manifest update.** Low
          risk, docs-adjacent: `manifest.json` and `daemon_control.py`'s
          docstring both still describe the pre-decision reasoning
          ("deliberately does NOT expose... pending Ish's explicit
          decision") — update to the post-decision reality once B–D
          land (enqueue/cancel wrapped as today, `/status` from sub-task
          A exposed, `daemon_shutdown` documented as autonomous-only and
          deliberately never wrapped as a callable capability, not
          "pending a decision" that's now made).

       Findings logged this scoping pass, not part of this round's
       fix scope: `NEW-106` (`observability.State.temperature` returns
       the LLM sampling temperature, not device heat), `NEW-107`
       (`observability.State.cpu_usage`/`memory_usage` are per-process,
       not system-wide).
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

## Track 3.5 — Multi-agent platform direction (new 2026-08-05, Ish; scoped only, none started)

New track from `CODEY_OS_MASTER_VISION.md` Section 9's 2026-08-05
amendment (multi-agent platform direction, confirmed by Ish — see
`PROJECT_LOG.md`'s 2026-08-05 entry) and its companion doc,
`docs/agent-plugin-blueprint.md`. Everything below is design/vision work
only — no code exists yet for any of these. Not strictly sequential with
Track 3, but the resource-gate item (first below) should follow Track
3's Phase 5a (coding-domain resource gate) rather than duplicate it —
generalize, don't rebuild.

- [ ] **Design and build the scheduler/resource-bus** that gates model
      execution across multiple agents/processes by live RAM/thermal
      state, queuing work when resources aren't available. Builds on
      (does not replace) Phase 5a's coding-domain resource gate — see
      `CODEY_OS_MASTER_VISION.md` Section 9.2 and
      `docs/agent-plugin-blueprint.md` Section 5. Must handle push-driven
      agents (e.g. IMAP-IDLE-triggered) as well as pull-driven ones —
      open design question, not answered yet.
- [ ] **Design the plugin/agent manifest schema extension** — `agent_type`,
      `model_tiers`, `resource_footprint`, `event_triggers`,
      `permissions`, `data_store` (proposed in
      `docs/agent-plugin-blueprint.md` Section 3, not read by any code
      today). Needs an actual implementation pass in
      `ccos/core/capability_registry.py`/`ccos/core/plugin_manager.py`
      once designed.
- [ ] **Scope actual Aigentik-CLI integration** (`~/Aigentik-CLI`, a
      separate repo/process/model — not part of Codey-OS). Requirements
      are worked through at a design level in
      `docs/agent-plugin-blueprint.md` Section 4; no implementation plan
      exists yet, and this item should produce one before any code is
      written against Aigentik-CLI.

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
  nothing deleted). **Update 2026-07-31: final disposition decided — Ish
  asked for permanent removal.** All 3 dirs `git rm -r`'d (see `NEW-34`'s
  closing entry in `NEW_ISSUES.md`). This is unrelated to Phase 4
  activation itself, which stays gated per rule 1 exactly as before —
  only the pre-existing recombiner *output* was removed, not any
  activation decision on the engine.

---

## Currently here

**Tracks 0 and 1 are now genuinely fully done (2026-07-30)** — the
earlier "fully done" claim was corrected mid-session per rule 6 when it
turned out 2 of Track 1's 4 items were still open; both are now closed:
the `recovery.py`/`strategy_tracker.py` comparison turned out to already
be resolved in Phase 2 (just undocumented until now), and `NEW-19` got a
direct decision from Ish, now a scoped Track 2 task (since fully
live-verified, see above). **In progress now (2026-07-31):** a
live-verifier session ran a real 1.5B-only planner test (RAM-disciplined,
7B never loaded), live-confirmed `NEW-28` with a sharpened mechanism, and
surfaced `NEW-46`/`NEW-47`/`NEW-48`. prompt-engineer then ran a
4-iteration rewrite of `PLANNER_PROMPT` in `core/plannd.py`, each iteration
reviewed by code-reviewer and re-tested by live-verifier — **this round is
now done: `NEW-28`/repeat-Run regression/`NEW-47` are code complete and
live-verified, `NEW-46`'s original trigger is fixed (its 1/3 residual
failure is now separately tracked as new open finding `NEW-50`). The
entire rewrite is COMMITTED (`d674a0c`) — the "UNCOMMITTED, pending Ish"
note here was stale and corrected 2026-07-31.** Two new findings from this round's
final regression testing remain open and unscoped: `NEW-50` (broader
example-content leakage, not just violation-labeled examples) and `NEW-51`
(Rule 9 peer-CLI delegation fails on a fresh untested phrasing, causal
link to this session not established). See the updated Track 2 entry
above.

**7B coder system-prompt round — scoped 2026-07-31, TWO live passes run
2026-07-31, BOTH INVALIDATED by a workspace-boundary contamination bug,
round NOT done.** Anchors on the corrected `NEW-30` framing (see
`NEW_ISSUES.md`) plus `NEW-49`; a desk-only tool-completeness delta pass
found two gaps this same scoping session, `NEW-53` and `NEW-54`; a third
finding, `NEW-52`, is `orchestrator.py`'s own version of the `NEW-49`
hardcoding bug, deliberately routed around (not fixed) by testing via
the `task_executor` path instead.

**First live pass** (7B-only, port 8080, one clean load/unload cycle,
PID-tracked) ran `NEW-30`'s test via hand-crafted `daemon.py`-style
step-enrichment strings fed to `TaskExecutor._execute_task`. **Second
live pass** (this session, trial detail relayed from that
live-verifier's own report, not independently re-derived here) targeted
`NEW-49`'s never-reached case 3 plus a `NEW-30` follow-up, using the
same hand-crafted-scratch-file approach.

**Correction, 2026-07-31 (rule 6, project-architect, no code/prompt
touched):** a third live-verifier session discovered that every scratch
test file used in BOTH passes lived under
`/data/data/com.termux/files/usr/tmp/claude-10247/.../scratchpad/...` —
entirely outside `core/filesystem.py:79-127`'s `_validate_path()`
boundary (`WORKSPACE_ROOT`/`CODE_DIR`, both
`/data/data/com.termux/files/home/Codey-OS` on this device).
Independently re-verified via a direct Python check against the live
`Filesystem` instance — see `NEW_ISSUES.md`'s new `NEW-60` entry for the
literal output. **Every `read_file` call in case 1 of both passes
returned `[ERROR] Access denied`, not real file content — everything
downstream in case 1 (wrong-path `write_file` guesses, dropped/
fabricated content, blocked-`shell` attempts, premature "Done."
responses) measured the model's denied-read recovery behavior, not the
read-then-edit contradiction `NEW-30` targets.** No valid data exists
this session on case 1's read-then-edit question or `NEW-49`'s planned
test (same case-1-shaped fixture). Case 2 (the control, file content
pre-injected into the prompt rather than read via `read_file`) is not
explained by this mechanism — no read was attempted there to deny — but
its own outcomes still don't confirm or refute `NEW-56`'s original
framing either, per `NEW_ISSUES.md`'s corrected entry. Full corrected
status
of each affected finding is in `NEW_ISSUES.md`'s new correction section
(inserted directly after `NEW-59`, before the Track 1 tool-audit
section): `NEW-30` stays NOT fixed and now genuinely untested (one
narrow, bounded positive signal survives — correct turn-1 `read_file`
targeting in 2 of 3 first-pass case-1 trials, before denial); `NEW-56`
downgraded (behavior real, cause reattributed to `NEW-60`, not
confirmed as a normal-conditions patch-vs-write bug); `NEW-55` kept
Confirmed with a provenance note added (the crash itself doesn't depend
on the denial); `NEW-49` unchanged, still Suspected; `NEW-57` unchanged,
its held-pending condition restated as still fully open. One new
Confirmed finding, `NEW-60`: a workspace-access-denied `read_file` call
sends the 7B agent into an unbounded, unrecoverable failure spiral
(wrong-path writes, blocked shell, wandering unrelated reads, premature
"Done."). Confirmed by code read (`filesystem.py:79-127` →
`agent.py:489/492-521/1748`) plus a direct literal reproduction; live
failure-shape corroboration is narrower than the full trial count —
documented specifically for the 2 case-1 trials of the first pass where
a denied read is on record, with pass 2's trials relayed only (see
`NEW_ISSUES.md`'s `NEW-60` entry for the exact accounting). Real and
production-reachable independent of `NEW-30`/`NEW-56` regardless, and
the actual cause of both contaminated passes.

**Third pass run 2026-07-31, Ish-greenlit — `NEW-30` is FIXED on its
actual mechanism, live-verified.** Both required fixes applied (scratch
fixtures moved inside `WORKSPACE_ROOT`, hard read-success precondition
gate before spending inference budget on a trial) and confirmed working.
RAM discipline clean (`free -h` before/after both cycles, PIDs tracked,
`ps aux | grep llama-server` clean after — one cycle hit the codebase's
own thermal-triggered auto-restart mid-run, not a manual kill, per rule
3). **Decisive A/B result:** same running server, 3 draws with the fix
vs. 3 with pre-fix `system_prompt.py`, fixture reset between draws —
**3/3 read-before-patch with the fix, 0/3 without** (pre-fix draws
skipped straight to a guessed `patch_file`, succeeding only by luck on a
generic fixture — the `NEW-7`/`NEW-44` ungrounded-`old_str` pattern).
One "fixed" draw still failed to apply, but from an unrelated newly-found
bug (`NEW-61`, JSON-repair regex mangles single-quoted values), not a
recurrence of the original "Done. after read" behavior. `NEW-49`
refuted at n=1 (real evidence, not yet a closed Suspected finding). Case
2 (control) showed the model reading anyway even with content
pre-injected — reported, not resolved either way; injection mechanism
caveat noted in `NEW_ISSUES.md`. See `NEW_ISSUES.md`'s new "`NEW-30`
third pass" and `NEW-61` entries for full detail.

**Status: COMMITTED 2026-07-31 (`d410b38`), on Ish's direct instruction,
bundled with `NEW-34`'s plugin deletion in one commit.** This closes out
the live-verification blocker on the 7B coder system-prompt round for
its anchor question. Remaining open items from this round, unscoped:
`NEW-49` (needs more than n=1 to close), `NEW-52` (deferred,
`orchestrator.py` write_file-hint hardcoding), `NEW-53`/`NEW-54`
(tool-completeness gaps), `NEW-61` (new, JSON-repair single-quote bug),
Case 2's control deviation (unresolved). `NEW-55` (the crash) was already
fixed and committed separately (commit `6859745`).

**Follow-up round, 2026-07-31 — `NEW-57`/`NEW-62` fixed, committed
(`4625e43`).** Ish asked for a desk investigation into whether a
mechanism exists that loads file content directly into the model's
context and retains it for a few turns before releasing it (motivated by
the `NEW-30` third pass's case 2 control behaving unexpectedly). Found:
yes, `core/memory_v2.py`'s `WorkingMemory` does exactly that
(`LRU_EVICT_AFTER = 3` "turns" — but a "turn" there means one
`run_agent()` call, i.e. one plan step, not one model response within a
step's read/patch/done loop). Tracing who populates it surfaced two real
bugs:
- `NEW-57` **re-corrected back to Confirmed** — an earlier correction
  claiming `core.context` and `core.memory_v2` are separate stores was
  itself wrong; `core/context.py:11` imports the identical
  `core.memory_v2.memory` singleton. So `write_file`/`patch_file` DID
  already register into the same store `_get_file_block()` reads from —
  `read_file` was the only branch that didn't. Fixed: `read_file` now
  mirrors the write branch's `_mem.load_file()`/`_mem.touch_file()` calls.
- `NEW-62` (new) — `detect_filenames()`'s regex silently stripped the
  leading dot off dot-prefixed path segments (e.g.
  `.live_verify_scratch/case1_anchor.py`, the very scratch dir the
  `NEW-30` third pass used), failing the existence check and silently
  skipping auto-load — meaning that pass's "genuinely unread file" framing
  held only by accident of this bug, not by design. Fixed, plus a
  bonus pre-existing bug the implementer caught along the way (`json`/`js`
  extension-alternation shadowing in the same regex).

Both fixes implementer-built, code-reviewer-approved (one non-blocking
warning turned into a new finding, `NEW-64` — `read_file`'s registration
has no size cap unlike the write branch, could evict more-useful resident
files on a large read), full suite green (271/271) before and after, no
model load needed (pure deterministic code, not model-behavior-dependent).
One more residual finding logged, not fixed: `NEW-63` (regex still can't
handle a mid-segment dot like Android's own `com.termux` path segment —
confirmed not a regression, pre-existing pattern fails identically).
Committed together with the `NEW_ISSUES.md` updates as `4625e43`.
