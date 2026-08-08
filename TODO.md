# TODO — Ordered Checklist of Outstanding Work

**Purpose:** one flat, checkable sequence, in dependency order, of every
real open item currently tracked across `CODEY_OS_MASTER_VISION.md`
(Sections 7.6, 8, 9.7), `WORK_QUEUE.md`, and `PROJECT_PLAN.md`. This file
is the checklist; `WORK_QUEUE.md` is the same sequence with full
evidence, history, and reasoning behind each line — read this to see
what's left and in what order, read `WORK_QUEUE.md` when you need the
"why" behind a specific line. Nothing is checked off here unless
`PROJECT_LOG.md`/`PROJECT_PLAN.md` already records it as actually
complete — where the source docs distinguish code-complete from
live-verified, that distinction is carried into the note.

Built 2026-08-08, consolidating `CODEY_OS_MASTER_VISION.md` Sections
7.6/8/9.7, `WORK_QUEUE.md` (full read-through), `PROJECT_PLAN.md`'s open
items, and `docs/agent-plugin-blueprint.md` Section 6. Numbered against
`CODEY_OS_MASTER_VISION.md`'s own section numbers where an item
corresponds directly to one (so the two docs stay cross-referenceable);
plain sequential numbers otherwise, with the corresponding `WORK_QUEUE.md`
track noted inline.

---

## Phase 1: Resource gate (coding domain) — foundation, build first

Everything else below depends on this existing. Nothing here is started.

- [ ] 7.4 (WQ Track 3 item 1, "Phase 5a") — Build the resource gate +
      slot-aware loader: give `loader_v2` a slot concept
      (acquire/release/list current slots); build the single resource-gate
      authority (`device_manager`'s hardware inventory + live
      `sysmon`/`thermal`/`observability` signals, expressed as "current
      headroom minus a safety margin," never a hardcoded number); migrate
      `core/daemon.py`'s three existing direct `get_loader()` calls
      (~lines 509, 556, 587) onto it as a client, not a second authority.
      This is the direct fix for the project's known concurrent-model-load
      crash pattern. Fold in NEW-24 (`core/lora_import.py:336` calls a
      nonexistent `loader.load_secondary()`) as part of this work. Use
      NEW-14/NEW-18/NEW-21's prior swap/RAM observations as validation
      data for safety-margin sizing. **Note:** NEW-69 (interactive-CLI
      direct loads in `main.py` bypass the swap arbiter entirely) is
      adjacent to this item and constrains its design — a naive fix would
      break normal CLI use whenever the daemon has a planner loaded; this
      needs a real cross-process arbitration mechanism, not a quick patch.
      Flagged for Ish/project-architect input before or during this item.

## Phase 2: Parallel design work (does not touch running code — can run alongside Phase 1)

- [ ] 9.3 (WQ Track 3.5) — Design the plugin/agent manifest schema
      extension: `agent_type`, `model_tiers`, `resource_footprint`,
      `event_triggers`, `permissions`, `data_store` (proposed in
      `docs/agent-plugin-blueprint.md` Section 3, not read by any code
      today). Design only at this stage — do not implement against
      `ccos/core/capability_registry.py`/`plugin_manager.py` yet.
- [ ] 9.4 (WQ Track 3.5) — Scope actual Aigentik-CLI integration
      (`~/Aigentik-CLI`, a fully separate repo/process/model, not part of
      Codey-OS). Requirements are worked through at a design level in
      `docs/agent-plugin-blueprint.md` Section 4; produce an actual
      integration plan before any code is written against it.

## Phase 3: Multi-agent generalization — only after Phase 1 is real

Do not implement Phase 2's manifest fields against the gate, and do not
start real Aigentik-CLI integration work, until this phase's item exists —
both would mean coding against an interface that doesn't exist yet.

- [ ] 9.2 (WQ Track 3.5) — Generalize the resource gate into a
      scheduler/resource-bus that arbitrates across multiple agent
      processes (not just Codey-OS's own daemon), gating model execution
      by live RAM/thermal state and queuing work when resources aren't
      available. Must handle push-driven agents (e.g. IMAP-IDLE-triggered)
      as well as pull-driven ones — open design question, not answered
      yet. Builds on Phase 1's gate (7.4); does not replace it.

## Phase 4: Coding-domain architecture rollout (vision 7.6 steps 2-6) — proceeds alongside Phase 3 once Phase 1 is done

- [ ] 4.1 (WQ Track 3 item 2, "PENDING_ISH_DECISIONS.md item 2") — Daemon
      control redesign, sequenced directly alongside/after Phase 1's
      resource gate (7.4) since it needs that same authority:
      `daemon_shutdown` becomes an autonomous thermal/CPU tripwire,
      `command` becomes queue-only, daemon never runs while TUI/GUI is
      active, queue consumption gated on the same live headroom check.
      `core/observability.py`'s wrap folds in here. Currently 100%
      decisions-on-paper, zero implementation.
- [ ] 7.3 (WQ Track 3 item 3, "Phase 5b") — Task classifier + tier
      config, coding domain only: non-LLM heuristic classifier;
      `(domain, role, tier) → model` config; reconcile with (don't
      duplicate) `core/orchestrator.py:is_complex()` and the daemon's
      separate `planner_client`/`planner_v2`/`planner_service` paths.
      Planner model-family choice stays deferred to this phase's
      on-device validation.
- [ ] 4.3 (WQ Track 3 item 4, "Phase 5c") — Wrap `core/agent.py` as a
      real CCOS capability, migrating both existing call paths (`main.py`
      for CLI/GUI, `core/task_executor.py` for the daemon) onto one
      boundary rather than a third path; the capability wrapper owns its
      own permission surface (`confirm_shell`/`confirm_write`) explicitly,
      not inherited from the calling context. Also where
      `PROJECT_PLAN.md` Phase 2's deferred item 7 (wrapping recursive
      self-refinement) gets picked back up, same capability boundary.
- [ ] 7.5 (WQ Track 3 item 5, "Phase 5d") — In-flight context-passing fix
      + task-context blackboard, designed together:
      `plugin_manager.call_capability` gets a threaded context argument
      (fixing `skill_recombiner.py`'s generator so its three previously
      generated compound skills would regenerate correctly, not that
      those skills are being restored — see NEW-34, they were deleted);
      new scoped task-context table for durable cross-step handoffs — not
      a general shared-memory grant, not a repurposing of `ccos_memory`'s
      existing tables.
- [ ] 4.5 (WQ Track 3 item 6, "PENDING_ISH_DECISIONS.md item 3") — Peer
      CLI escalation redesign, sequenced after 4.1's queue and 7.5's
      blackboard exist (its design reuses both): daemon pulls an item
      needing escalation out of the main queue, parks it on a separate
      review list, notifies the user, keeps working the rest of the
      queue. Currently 100% design-only, zero implementation.
- [ ] 4.6 (WQ Track 3 item 7, "Phase 5e") — Wire `agent_orchestrator`'s
      5-agent deliberation (Planner → Critic → Optimizer → Capability →
      Safety) to real execution. Cheap (heuristic, not model-backed) but
      the Safety Agent's veto becomes live against real actions for the
      first time — treat as a behavior change to flag, not just a wiring
      task. Depends on 4.3 (coding agent must be a capability to be a
      routing target).
- [ ] 4.7 (WQ Track 3 item 8, "Phase 5f") — Multi-domain request
      splitting (e.g. "research X, then implement it"). Depends on 4.3,
      7.5, and 4.6 — first point where capability-as-plugin,
      context-passing, and the durable blackboard all compose.

## Unblocked / can run any time — not gated by Phases 1-4 above

These items have no dependency on the resource-gate/multi-agent work
above; interleave them whenever convenient (WQ Tracks 2 and 4).

- [ ] U.1 (WQ Track 2) — `NEW-7`: `[Recursive]`/agent planner sometimes
      synthesizes whole duplicate functions instead of targeted patches.
      Open on a **narrowed basis only**: Round 22's pre-registered 12-draw
      reproducibility pass found 0/12 wrong-target (NEW-44 downgraded, not
      closed) and recommends **against** scoping a target-function-
      identification prompt iteration right now — the remaining open
      surface is grounding-failure on `main.py`-sized fixtures (3/12,
      always the same hallucinated one-line-stub pattern), not
      wrong-targeting. Any future round should reinforce the existing
      `0026565` grounding fix against that specific pattern, not add new
      wrong-target instructions.
- [ ] U.2 (WQ Track 2) — `NEW-50`: worked examples in prompt text leak
      verbatim content into unrelated requests regardless of ✓/✗
      labeling — broader than the specific instance `NEW-46` already
      fixed (`NEW-46` itself is not fully closed; treat this as its
      residual). Not yet scoped to an implementer.
- [ ] U.3 (WQ Track 2) — `NEW-51`: Rule 9 peer-CLI delegation format
      fails entirely on a fresh, previously-untested phrasing ("Have
      gemini check X for race conditions") — no delegation step emitted,
      treated as a Create task instead. Open question not yet settled:
      pre-existing gap vs. regression from the same session's other
      changes.
- [ ] U.4 (WQ Track 2) — `NEW-48`: `core/plannd.py`'s `parse_steps()`
      truncation-warning heuristic (last-step-final-character check)
      false-positived on 8/8 test prompts, including independently
      judged clean/correct plans. Code, not prompt text. Recommend
      loosening or dropping the heuristic; not yet scoped.
- [ ] U.5 (WQ Track 2) — `NEW-49`: `core/daemon.py` (~lines 166-194)
      hardcodes step-1 = Create/full-rewrite semantics by position
      (`i == 0`) regardless of the step's actual verb, so an Edit-first
      multi-step plan gets told to overwrite the whole file instead of a
      targeted edit. **Refuted at n=1 in a later live pass — still
      Suspected, not closed; needs a larger sample than n=1 before either
      confirming or closing.**
- [ ] U.6 (WQ Track 2) — Security hardening backlog (never assigned
      individual NEW-IDs — assign one when picked up): command-injection-
      via-filename in `agent.py:863-865` (partially addressed, finish
      it); daemon shell allowlist too broad in `task_executor.py:47-52`
      (documented, not changed); Unix socket auth in `core/daemon.py`
      (peer-UID check exists, token-based auth recommended as a real
      enhancement, not yet built).
- [ ] U.7 (WQ Track 2 / PROJECT_PLAN.md Round 1) — H-1 fallback path is
      mechanism-verified only, never live-triggered. Finish the live
      verification (a mechanism-only claim doesn't stand alone, per
      CLAUDE.md rule 5).
- [ ] U.8 (WQ Track 2) — `NEW-9`'s residual atfork race. **Not a default
      "attempt fix #3" item** — already escalated twice (Rounds 9 and 10,
      each an improvement but neither a full close). This item is "get
      Ish's explicit call on accept-residual-risk vs. a third attempt
      with a genuinely new angle," per CLAUDE.md's stop-and-escalate
      rule — do not pick this up as a normal fix task without that call
      first.
- [ ] U.9 (WQ Track 3 item 1 note) — `NEW-69`: interactive-CLI direct
      loads (`main.py`) bypass the swap arbiter entirely. A naive fix
      would break normal CLI use whenever the daemon has a planner
      loaded — needs a real cross-process arbitration mechanism, not a
      quick patch. Flagged for Ish/project-architect; adjacent to (and
      constrains the design of) Phase 1's resource gate (7.4) above —
      get Ish's call on sequencing before or alongside 7.4, not a
      standalone pickup.
- [x] U.10 (WQ Track 2, 7B system-prompt round) — Attribution logging
      status. **Investigated 2026-08-08 (Ish asked for an investigation,
      not a fix): it did land**, just inside the same commit as sub-tasks
      2/3 rather than a separate one — `core/recursive.py:318-401`
      (`_log_phase`, `_finish`'s `[Recursive] Turn attribution: path=...
      cycles=... tool=...` log line), added in commit `6859745`'s
      description ("Also adds per-turn attribution logging..."), same
      commit as `NEW-58`/`NEW-59`. **Known, self-documented gap** (see
      `recursive.py:386-390`'s own comment): it only covers
      `recursive_infer()`'s two paths (recursive draft/critique/refine,
      and the config-disabled plain-`infer()` fallback through that same
      function) — it has no visibility into `core/agent.py`'s *separate*
      plain-`infer()` branch (the `step != 1` case that bypasses
      `recursive_infer()` entirely), which was out of that task's
      file-scope. That branch still produces no attribution log line at
      all. **Open question for Ish:** extend coverage to `agent.py`'s
      other branch as new work, or leave as a documented, accepted gap?
- [ ] U.11 (WQ Track 2, 7B system-prompt round) — `NEW-60` (Confirmed): a
      workspace-access-denied `read_file` call sends the 7B agent into an
      unbounded, unrecoverable failure spiral (wrong-path writes, blocked
      shell, wandering unrelated reads, premature "Done."). Confirmed by
      code read (`filesystem.py:79-127` → `agent.py:489/492-521/1748`)
      plus a direct literal reproduction. Explicitly noted as "real and
      production-reachable independent of NEW-30/NEW-56" — not yet scoped
      to an implementer.
- [ ] U.12 (WQ Track 2) — `NEW-52`: `orchestrator.py`'s own write_file-
      hint hardcoding (deliberately routed around, not fixed, during the
      7B system-prompt round). Open for its own future round.
- [ ] U.13 (WQ Track 2) — `NEW-53`/`NEW-54`: tool-completeness gaps in
      `core/agent.py`'s tool-calling loop — `append_file`/`note_forget`
      are unreachable (no word→tool trigger for either); peer-CLI
      delegation isn't a real tool at all (decided by regex on raw text
      before the system prompt applies).
- [ ] U.14 (WQ Track 2) — `NEW-61`: JSON-repair regex mangles
      single-quoted values (found during the 7B system-prompt round's
      third live pass).
- [ ] U.15 (WQ Track 2) — 7B system-prompt round's Case 2 (control)
      deviation: the model read a file anyway even with its content
      pre-injected into the prompt — reported, not resolved either way.
- [ ] U.16 (WQ Track 4) — `docs/architecture.md` rewrite — best done
      after 4.3 (Phase 5c) lands, so it can describe the coding agent as
      an actual CCOS capability instead of a pre-Phase-5 state that would
      already be stale by then.
- [ ] U.17 (WQ Track 4) — `docs/commands.md` gaps: 12 missing slash
      commands, ~13 missing CLI flags, one possibly-stale flag
      (`--rollback`).
- [x] U.18 (WQ Track 4) — `ccos/core/telemetry_engine.py` dedup-key
      collision bug. **Code-complete 2026-08-08, code-reviewer-approved
      after changes requested:** `record_execution()`
      (`telemetry_engine.py:157-174`) replaced the collision-prone
      `timestamp-ms + id(record) % 10000` `record_id` scheme with
      `timestamp-ms + uuid4().hex[:12]`. `record_id` is the DB's `UNIQUE`
      key and writes use `INSERT OR IGNORE` (`_flush_buffer`), so a
      collision doesn't error — it silently drops a real execution
      record. This closes one *plausible* collision source; it is
      **not** a confirmed root-cause fix for the original "intermittent
      test flakiness" report — no test in the suite exercises the actual
      collision scenario, and `code-reviewer` found two independent
      silent-drop mechanisms nearby that this fix does not touch
      (logged as `NEW-77` Confirmed, `NEW-78` Suspected). No model load
      involved (pure deterministic code); full suite 348/348 passing
      before and after, `ccos/tests/test_telemetry.py` 12/12 — evidence
      the change didn't break anything, not evidence it fixed the
      flakiness. Not process-lifecycle, so CLAUDE.md rule 4's mandatory
      gate didn't apply, but per Ish's direction this still went through
      a real `code-reviewer` pass (not self-review) after the fact,
      since the fix was originally made by an agent operating outside
      the normal pipeline.
- [ ] U.19 (WQ Track 4 / vision Section 8) — TTS is broken on both
      `core/voice.py` and `ccos/plugins/speech/tts_speech` (confirmed by
      Ish). Get one working, verify it, remove the other. STT (voice
      input) has no CCOS equivalent at all, so `core/voice.py` (or a
      rewrite) is needed regardless of the TTS outcome.
- [ ] U.20 (WQ Track 4) — Code quality backlog: unused imports (129
      F401), line length (1343 E501), comparison style (74 E712) — none
      addressed yet.
- [ ] U.21 (WQ Track 4) — Testing gaps: no daemon-mode integration tests,
      no path-traversal tests.
- [ ] U.22 (WQ Track 4) — Security guide docs: unclear whether they
      reflect recent changes; needs a read-through to confirm.
- [x] U.23 (vision Section 8) — `AUDIT_REPORT.md` disposition. **Done
      2026-08-08:** Ish's call was archive (not delete). Moved to
      `docs/archive/AUDIT_REPORT.md` (`git mv`, history preserved) with an
      archival header added. `CODEY_OS_MASTER_VISION.md` Section 8 and
      `NEW_ISSUES.md`'s NEW-27 entry both updated to reflect resolution.
- [ ] U.24 (vision Section 8) — `docs/TODO2.md` needs a scoped
      re-verification pass against current code (old, 2026-03-29-era
      deferred-items list; at least one item already contradicted by the
      current codebase). Logged as NEW-27, Suspected.
- [ ] U.25 (vision Section 8 / NEW-27) — README docs-table discoverability
      gap: `MODEL_COMPARISON.md`, `PRIVACY.md`, and `docs/importantdoc.md`
      have real, current content but no inbound link from `README.md`'s
      docs table.
- [ ] U.26 (found during this round's repo walk, not previously tracked —
      logged to `NEW_ISSUES.md` this round as `NEW-75`) — stray
      root-level file `=3.9.0` (a pip-invocation-typo artifact, ~1.7KB,
      contains pip install output) — Suspected safe to delete, not
      deleted here per CLAUDE.md rule 8.

## Parked — gated, do not start without Ish's explicit sign-off

- [ ] P.1 (vision Section 5 / PROJECT_PLAN.md Phase 4) — Self-improvement
      activation (`auto_improvement_loop`, `capability_optimizer`,
      `skill_recombiner`, `goal_engine`). **Gated by CLAUDE.md rule 1: do
      not start until Phases 1-4 above are stable, a meaningful period of
      observed real-task operation through the sandbox/safety-veto path
      has elapsed, AND Ish gives explicit, direct, in-session sign-off —
      not inferred from this checklist reaching the end.** When that
      time comes: review `auto_improvement_loop.py`/`capability_optimizer.py`
      behavior in a controlled test (not live); decide what "compound
      skill" creation should require before `skill_recombiner.py` is
      allowed to register something new automatically (approval gate?);
      decide whether `goal_engine.py`'s generated goals require explicit
      approval before entering the planner queue. Only after sign-off,
      wire into the live execution path.

---

## Notes

- Every `NEW-##` ID above is a currently-open item as of the last full
  read-through of `WORK_QUEUE.md`/`NEW_ISSUES.md` (2026-08-08). IDs that
  only appear as adjacent findings inside an already-closed queue item
  (e.g. NEW-36 through NEW-45, NEW-55 through NEW-64, NEW-70 through
  NEW-74, etc.) are not separately listed here unless they represent
  distinct, still-open work — check `NEW_ISSUES.md` directly for the full
  finding log; this file only tracks queue-level work items.
- This file does not track completed work — `PROJECT_LOG.md` is the
  historical record, `PROJECT_PLAN.md` tracks phase status in detail
  (including the code-complete-vs-live-verified distinction).
