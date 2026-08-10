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

- [ ] 7.4 (WQ Track 3 item 1, "Phase 5a") — **All five sub-tasks
      code-complete and code-reviewer-approved as of 2026-08-09. Round 18
      (2026-08-09) achieved the first full live confirmation of the core
      admission→load→CLI-recovery path end to end — a real milestone —
      but three new real gaps were found live in supporting mechanisms
      (kill-by-pattern, slot pid/port binding, confirmation-poll
      accuracy). Top-level box stays unchecked: genuinely live-verified
      for the core path now, not "fully done." See the round 18 summary
      below the round 13 one for what changed.**
      What's now live-confirmed: the gate's hard-ceiling denial actually
      firing with no spawn (`NEW-95`); the CLI path
      (`main.py --init`/`load_primary()`) genuinely reaching
      `can_admit()` and reporting a real denial with byte-exact figures;
      sub-task 5's `GATE_DENIED_HARD` skip-daemon-contact branch, live,
      for the first time. What's still unverified: an actual successful
      load-through-the-gate-then-unload cycle (the substitute model's
      real KV-cache shape, 36 layers/8 KV heads, made it cost MORE than
      the 7B at production `n_ctx=32768` despite being a smaller file —
      hard-rejected, correctly, but this means no substitute has
      successfully exercised the positive admission path yet);
      `release_model_slot` (sub-task 4) actually firing on a real
      request; the transient-`GATE_DENIED`-then-retry path. Needs either
      a genuinely smaller-KV-footprint substitute, or a documented
      `n_ctx` override for test runs (neither exists today — flagged in
      `NEW-95`). **Two real gaps found in 7.4's interaction with the
      pre-existing `plannd` process** (not part of 7.4 itself, but
      block it in the default runtime configuration): `NEW-96` — the
      daemon's startup preload never reaches `can_admit()` at all while
      `plannd` is running (blocked earlier by an unrelated sequential-swap
      eviction check), and the resulting message still says "will load on
      first request" — a false promise in the actual default runtime
      shape, since nothing will ever free `plannd`'s port under this
      configuration; `NEW-97` — `plannd` bypasses
      `reserve_slot()`/`register_slot()` entirely (bash `nohup`, not
      routed through the gate-aware `PlannerLoader`), so the gate's
      residency model — built in sub-task 1 to be cross-process-aware —
      can't see it. Both worth fixing before another live-test round;
      neither was in this round's scope to patch (live-verification
      observes, doesn't fix).

      **Round 18 update (2026-08-09), after `U.27`/`U.28`/`U.31` were
      fixed**: real dry-run against the live gate found `n_ctx=2048` was
      needed (not 8192 — `32768` hard-rejected, `8192` denied on real
      headroom, `4096` admitted with only a 76MiB margin, judged too
      thin). **Stage 1 succeeded for the first time**: startup preload
      still hit `eviction_failed` (confirms `U.28` only fixed `plannd`'s
      *accounting* visibility, not the eviction check's actual pass/fail
      logic — verified directly this round, not assumed); killing
      `plannd` by tracked PID let the next watchdog tick reach
      `can_admit()` for real — admitted, spawned, exactly one resident
      slot, cost matching the estimate. Live correction to
      `core/daemon.py`'s own comment: `eviction_failed` does self-resolve
      once `plannd` actually exits, contrary to what that comment claims.
      **Stage 2 succeeded for the first time**: CLI hit a real transient
      headroom denial, asked the daemon to release its slot, got it,
      retried, spawned its own server, completed real inference —
      sub-tasks 4/5's actual reason for existing, confirmed working end
      to end. Three new Confirmed findings, not fixed (verification-only
      round): `NEW-103` (`codeydOS` teardown actually cleans up via a
      bare `pkill -f`, not any PID-tracked path — confirmed as the real
      live mechanism, not theoretical); `NEW-104` (gate slots key to the
      *caller's* PID, not the spawned child's — live-reproduced
      accounting blindness after the CLI's release-then-retry cycle;
      accounting/observability impact, not admission-safety, since
      `can_admit()` reads real `/proc/meminfo` directly); `NEW-105`
      (`confirm_resident_and_mark_slot()`'s `MemAvailable`-delta
      confirmation never actually confirmed either successful load this
      round, falling through to its own "mark resident anyway" fallback
      both times — not a safety regression, but its actual job never
      once succeeded). See `U.32`/`U.33`/`U.34` below for these as
      tracked follow-ups.

      Build the resource gate + slot-aware loader, per
      `CODEY_OS_MASTER_VISION.md` Section 7.4's 2026-08-08 amendment:
      **no fixed concurrency ceiling** — the gate admits as many
      concurrently-resident models (daemon + CLI) as live RAM/swap
      headroom, thermal state, and telemetry actually support, and also
      owns CPU thread/core allocation per model as residency changes.
      The one hard admission check that remains: a single model must
      never load if it alone exceeds what the device can handle.
      Future (not this round): task-appropriate fallback to a smaller
      model when it can correctly do the job — a routing concern (7.3),
      not part of the gate's own admission logic; the gate should expose
      "would a smaller model fit right now" as an answerable question
      without implementing the routing itself.
      **NEW-69 resolved into scope, not deferred**: the gate's residency
      data model is cross-process-aware (daemon + `main.py`'s CLI loads)
      from sub-task 1, not daemon-only-first — but *enforcement* against
      the CLI waits until sub-task 4 (daemon-side slot-release command)
      exists, so the CLI can't get blocked with no way to free a slot.
      Verified real call sites (confirmed by direct code read,
      2026-08-08): `core/daemon.py` 509-517 (startup preload), 556-564
      (watchdog), 587-589 (shutdown unload); `main.py` 1269-1271,
      1550-1552, 1561-1564, 1586-1589 (four direct CLI loads, none go
      through `ensure_model()`). NEW-24 corrected: **two** broken
      `loader.load_secondary()` call sites in `core/lora_import.py`
      (lines 336 and 424, not just 336). NEW-21's real numbers (baseline
      4.3Gi used/2.2Gi free, single load drove swap 1.2Gi→5.6Gi in ~10s)
      are used as a regression-test case — a bare headroom-minus-margin
      formula would have wrongly approved that load, so the gate needs a
      per-load cost estimate (model size + `n_ctx`-driven KV cache), not
      headroom alone. Signal sourcing needed real correction too: none of
      Section 7.4's four named sources work as-is —
      `ccos/core/device_manager.py` (not `core/`) is a cached static
      scan, not live; `core/sysmon.py`'s monitoring thread is never
      started by the daemon; `core/observability.py`'s memory figure is
      per-process RSS, not system headroom; `core/thermal.py` has no
      public current-temperature accessor. Five-sub-task build order
      (each of 2-5 touches process-lifecycle code — mandatory
      `code-reviewer` pass per CLAUDE.md rule 4):
      1. **[x] Code-complete, 2026-08-08.** Gate module + real signal
         sourcing (no model load; unit-testable with synthetic
         `/proc/meminfo` fixtures, NEW-21's numbers as a regression case).
         Built as `core/resource_gate.py` (new module, not wired into any
         running path — `core/daemon.py`/`core/loader_v2.py`/
         `core/planner_loader.py`/`main.py` untouched, per this sub-task's
         explicit scope) plus a minimal additive public accessor,
         `ThermalManager.get_current_temp_c()` /
         `core.thermal.get_current_temp_c()`, wrapping the existing private
         `_read_cpu_temp()`. Tests: `tests/test_resource_gate.py` (41
         tests, all passing; full suite `pytest tests/ -q` — 321 passed).
         No process-lifecycle risk, so no live-verification needed for this
         sub-task per its own scope note — code-complete is the correct
         status here, not a stand-in for live-verified.
      2. **[x] Code-complete, 2026-08-09 (not live-verified — mocked/unit
         tests only, per this sub-task's own scope).** Slot concept wired
         into `core/loader_v2.py:ModelLoader.load_primary()`/`unload()` and
         `core/planner_loader.py:PlannerLoader.load()`/`unload()`: each
         reserves a slot via `resource_gate.reserve_slot()` before spawning,
         surfaces a denied reservation as a real load failure (no spawn), and
         calls a new shared `core/loader_v2.py:confirm_resident_and_mark_slot()`
         (bounded `/proc/meminfo`-drop poll, not just a health-endpoint
         answer — matches `mark_resident()`'s documented precondition) before
         marking the slot resident; `unload()` releases it. A reuse case
         (`LlamaServer.start()` returning `True` via one of its no-spawn
         reuse branches, `self.process` still `None`) releases the loader's
         own reservation instead of double-accounting a process it doesn't
         own. `core/embed_server.py` registers/releases a slot via
         `register_slot()`/`release_slot()` directly (never
         `reserve_slot()`/`can_admit()`) — accounted-but-exempt, never
         blocks or gets evicted. NEW-24 fixed at both call sites in
         `core/lora_import.py` (`swap_to_finetuned_model`,
         `rollback_to_backup`): routed the "secondary" branch to
         `core.planner_loader.get_planner_loader()` instead of the
         nonexistent `loader.load_secondary()` (also fixed
         `rollback_to_backup`'s unconditional `loader.unload()`, which was
         unloading the *primary* even for the secondary branch). **Residual
         gap found while fixing NEW-24, not itself in this sub-task's
         scope**: hot-swapping to an arbitrary fine-tuned file still doesn't
         work for either variant — both loaders read a module-level path
         constant bound at import time, not `cfg.MODEL_PATH`/
         `cfg.SECONDARY_MODEL_PATH`, so `swap_to_finetuned_model()` reloads
         the *original* weights while reporting success. Tests:
         `tests/test_loader_resource_gate.py` (new, 15 tests — reservation/
         denial/spawn-failure/reuse/release paths for both loaders, the
         confirm-resident poll logic, embed-server accounting, and two tests
         against the real (unmocked) `resource_gate` module with synthetic
         meminfo); `tests/test_new12_launcher_lock_and_swap.py` updated with
         an autouse fixture patching the gate so its swap-lock tests stay
         deterministic. Full suite `pytest tests/ -q` — 346 passed.
         `core/daemon.py`/`main.py` untouched, per this sub-task's explicit
         scope (sub-tasks 3/5).

         **Round 2 fix, 2026-08-09 (code-complete, not live-verified —
         real-`resource_gate` + real-spawned-subprocess unit tests only):**
         code-reviewer round-1 review (`.claude/agent-memory/code-reviewer/
         resource_gate_subtask2_confirm_mark_slot_leak.md`) live-reproduced
         a leak: only the two explicit failure branches (`start()` returning
         `False`; the reuse-without-spawn branch) released the reservation —
         if `confirm_resident_and_mark_slot()` itself raised (its
         `rg.mark_resident()` does a blocking `flock()` + atomic
         `os.replace()`, both of which can raise under fd exhaustion/disk
         pressure), the spawned process and the PENDING reservation both
         leaked with no cleanup path. Fixed in both
         `core/loader_v2.py:ModelLoader.load_primary()` and
         `core/planner_loader.py:PlannerLoader.load()` by wrapping the whole
         spawn→confirm sequence in a structural try/finally: a `loaded_ok`
         flag is only set `True` on the genuine success path; the `finally`
         clause stops the spawned process (only if this call actually
         spawned it — `self._server.process is not None` — never a reused
         server, CLAUDE.md rule 3) and releases the reservation on every
         other exit, explicit `return False` or a propagating exception
         alike. Tests: two new regression tests added to
         `tests/test_loader_resource_gate.py` (17 total now) that force
         `rg.mark_resident()` to raise against the REAL `resource_gate`
         module (tmp_path-backed state store) with a REAL (but harmless,
         no-model, RAM-discipline-safe) spawned `sleep 300` subprocess in
         place of llama-server — asserting via `rg.list_slots()` that no
         slot leaks and via `proc.poll()` that no process is left orphaned.
         Verified red-before-green: both new tests fail against the
         pre-fix code (real reproduction of the leak, including two
         genuinely orphaned `sleep 300` processes observed via `ps aux`
         until manually killed) and pass against the fix. Full suite
         `pytest tests/ -q` — 362 passed, 1 skipped. `NEW-81` (slot `pid`
         defaults to the caller's own PID, not the spawned subprocess's)
         deliberately left deferred — no existing `resource_gate.py` API to
         update a slot's `pid` post-reservation, and adding one is out of
         this fix's scope (task explicitly said not to touch
         `resource_gate.py` unless an actual bug was found there; none was).
      3. **[x] Code-complete, 2026-08-09 (not live-verified — mocked/unit
         tests only, per this sub-task's own scope).** Found (per this
         sub-task's own instructions, before changing anything): all three
         of `daemon.py`'s call sites already call `ensure_model()`/
         `unload()`, and `ensure_model()` already routes through the
         gate-aware `load_primary()` on both its branches (cold load at its
         tail call, and the thermal-restart branch via `unload()` +
         `load_primary()`) — sub-task 2 already closed the bypass gap. **No
         call-site restructuring needed.** The actual gap, exactly as this
         sub-task's own scope note anticipated: `ensure_model()`'s `False`
         return was a single undifferentiated signal, and `daemon.py`
         treated every failure as a process crash — the watchdog discarded
         `ensure_model()`'s return value entirely and unconditionally
         logged "died — restarting" on any falsy `get_model_instance()`,
         including "never loaded at all" and "the gate denied a
         reservation" (a real, expected 7.4 outcome, not a crash). Fixed by
         adding an additive outcome-tracking surface to
         `core/loader_v2.py:ModelLoader` — `LOAD_OUTCOME_*` constants
         (`ok`/`already_loaded`/`deferred`/`gate_denied`/
         `gate_denied_hard`/`eviction_failed`/`spawn_failed`/`error`) plus
         `get_last_ensure_outcome()`/`get_last_ensure_reason()` getters, set
         at EVERY return point in both `ensure_model()` and `load_primary()`
         (not just the gate-denial path) so a stale value from a prior,
         unrelated call is never misread as the current call's outcome —
         e.g. a `SWAP_GUARD`-deferred call must never inherit a previous
         call's `gate_denied` outcome. `ensure_model()`'s/`load_primary()`'s
         own return type is unchanged (still plain `bool`) — the four
         existing external callers (`core/inference.py`,
         `core/inference_v2.py`, `main.py`, `core/lora_import.py`) are
         untouched. `decision.hard_reject` (already returned by
         `resource_gate.can_admit()`, not a new field) is surfaced through
         this so `gate_denied_hard` (this model alone exceeds the device
         ceiling — retrying can never help) is distinguished from
         `gate_denied` (transient headroom/thermal — worth retrying).
         `daemon.py`'s three sites updated to consume this: (1) startup
         preload's failure message no longer says "will load on first
         request" under a gate denial, which would be a false promise — it
         distinguishes hard/transient denial from a genuine load failure;
         (2) the 30s watchdog's inline block extracted into a new
         `Daemon._watchdog_check_model()` method (independently testable)
         that reports gate denial (hard and transient), `SWAP_GUARD`-deferred
         (logged at `info`, not `warning` — benign, self-resolves next tick),
         "never loaded" vs. genuine "died, restart failed" as distinct
         outcomes instead of one "died — restarting" message for all of
         them, and its own `except Exception` is now logged (with the
         exception text) rather than a bare `pass` — CLAUDE.md's rule
         against silently swallowing exceptions around safety-relevant code
         without a justifying comment applies directly to a model-loader
         call site; (3) shutdown's `unload()` `except Exception: pass`
         changed to a logged warning, since a failure there can leave BOTH
         an orphaned detached llama-server process and a leaked gate slot
         (the latter wrongly counts against every future admission decision
         on this device) — left the neighboring embed-server shutdown's own
         bare `except: pass` alone, out of scope, no comparable
         gate-accounting side effect. Tests: 8 new tests appended to
         `tests/test_loader_resource_gate.py` covering
         `get_last_ensure_outcome()`/`get_last_ensure_reason()` at every
         `load_primary()`/`ensure_model()` return point, including the
         staleness-regression case (a gate-denied call followed by an
         unrelated `SWAP_GUARD`-deferred call must report `deferred`, not a
         leftover `gate_denied`); new `tests/test_daemon_model_watchdog.py`
         (7 tests, `Daemon.__new__(Daemon)` to skip `__init__`'s heavy
         state-store/planner/signal-handler setup since
         `_watchdog_check_model()` doesn't use `self`) covering all six
         watchdog branches (success, gate-denied hard/transient, deferred,
         never-loaded, genuine-crash) plus the exception-is-logged-not-
         swallowed case. Full suite `pytest tests/ -q` — 385 passed, 1
         skipped. **Findings outside this sub-task's scope, logged not
         fixed** (see `NEW_ISSUES.md`): the embed-server watchdog's own
         bare `except Exception: pass` (immediately adjacent to the fixed
         model watchdog, not one of this sub-task's three named sites); a
         detached-server-vs-`reap_dead` accounting hole (if the daemon dies
         without running its shutdown `finally`, `list_slots(reap_dead=True)`
         can reap a slot for an llama-server that's still resident and
         running detached, under-counting real RAM — needs a
         `resource_gate.py` API change, explicitly out of this sub-task's
         scope); `load_primary()` incrementing `self._load_failures` on a
         gate denial, which could poison a "model is broken" failure
         counter if anything ever escalates on it (nothing currently does —
         `get_load_failures()`/`reset_failures()` have no other consumers).
      4. **[x] Code-complete, 2026-08-09 (not live-verified — mocked/unit
         tests only). Code-reviewer pass still pending** (implementer
         agent hit a session usage limit mid-task before requesting
         review; I finished the small remainder myself directly — see
         below — rather than leave it half-done). Daemon-side slot-release
         socket command (the real NEW-69 prerequisite): new
         `release_model_slot` command registered on `core/daemon.py`'s
         existing `DaemonServer` handler pattern (`{"model_id": "primary"
         | "planner"}` → `{"status", "released", "outcome", "message"}`).
         Declines (not errors) if a task is actively inferring
         (`core/thermal.py`'s new `is_inference_active()` accessor, same
         additive pattern as sub-task 1's `get_current_temp_c()` —
         process-local, can't stay stuck if the daemon dies mid-task,
         unlike the SQLite task `running` status) or if `SWAP_GUARD` is
         already held elsewhere (non-blocking acquire, held across the
         whole unload once acquired — same reasoning as `ensure_model()`
         holding it for its entire body). Already-unloaded is a clean
         no-op success, not an error. A per-`model_id` cooldown
         (`RELEASE_SLOT_COOLDOWN_S = 5.0`) prevents this command being used
         to force rapid unload/reload thrashing against the daemon's own
         model — armed only on a confirmed release, never on a busy/
         cooldown decline, so a legitimate retry right after a decline
         isn't punished. `unload()` runs via `run_in_executor` (can block
         on `process.wait(timeout=8)`) and the release is confirmed via a
         bounded poll of `probe_port_health()` before being reported as
         actually freed. Thermal-check exceptions fail closed to "busy"
         rather than risking a release mid-inference. Explicitly does NOT
         wire `main.py` to call this yet (sub-task 5). Tests:
         `tests/test_daemon_release_model_slot.py` (13 tests — invalid
         input, busy-task decline, thermal-check-fails-closed,
         swap-guard-busy decline, already-unloaded no-op, successful
         release, planner routing, exception-releases-guard, unconfirmed
         release reported distinctly, cooldown enforcement, busy-decline-
         doesn't-arm-cooldown, handler registration). Full suite `pytest
         tests/ -q` — 466 passed, 1 skipped. **What I fixed myself after
         the session-limit cutoff** (implementer had already written and
         committed-to-working-tree the actual `core/daemon.py`/
         `core/thermal.py` logic before being cut off mid-test-writing):
         2 of the new tests referenced `daemon_mod.SWAP_GUARD`, which
         doesn't exist (`SWAP_GUARD` is imported locally inside the
         handler from `core.loader_v2`, not re-exported at
         `core.daemon` module level) — fixed both to reference
         `core.loader_v2.SWAP_GUARD` directly, fixed a placeholder no-op
         assertion in the autouse fixture (`assert X if False else True`,
         clearly an unfinished stub) into a real pre/post-test guard-state
         check, and removed one unused `threading` import. No change to
         the actual `core/daemon.py`/`core/thermal.py` implementation
         logic itself — only the test file. **Still needs a real
         `code-reviewer` pass before commit** — this is daemon/
         process-control code that lets an external process trigger
         daemon-side unloading, exactly CLAUDE.md rule 4's mandatory
         category, and the implementer's own design reasoning (busy/
         cooldown/guard handling) hasn't had independent review yet, only
         my own read-through while fixing the tests.
      5. **[x] Code-complete, 2026-08-09 (not live-verified — mocked/unit
         tests only, per this sub-task's own scope).** `main.py`'s four
         direct `loader.load_primary()` CLI call sites (`repl()`,
         `args.init`/`args.tdd`/`args.fix`) already went through the gate's
         admission check (via `load_primary()`'s own `reserve_slot()` call,
         sub-tasks 1-2) — what this sub-task actually closed, per its own
         scope note, is the missing recovery path for what happens on a
         DENIED reservation: no way for the CLI to free up room, just a
         load that fails with nothing to try next. Added
         `main.py:_load_primary_with_gate_recovery(loader)`: calls
         `loader.load_primary()`; if it fails with
         `LOAD_OUTCOME_GATE_DENIED` (transient, from
         `get_last_ensure_outcome()`/`get_last_ensure_reason()`, sub-task
         3's getters) and a daemon is running (`_daemon_is_running()`),
         asks it to free a slot via `core/daemon.py`'s
         `release_model_slot` socket command
         (`send_command("release_model_slot", {"model_id": "primary"},
         timeout=_RELEASE_SLOT_TIMEOUT_S)`, `_RELEASE_SLOT_TIMEOUT_S = 20.0`
         — bounded above the daemon's own worst-case release latency
         (~11s: `RELEASE_CONFIRM_TIMEOUT_S` poll + `process.wait(timeout=8)`)
         rather than `send_command()`'s generic 60s default, since this
         call sits in the CLI's own model-load path) and retries the load
         exactly once if the outcome is `released` or `already_unloaded`.
         Every other case reports the ORIGINAL gate denial, not a
         secondary failure, with no retry: `LOAD_OUTCOME_GATE_DENIED_HARD`
         (retrying can never help) skips daemon contact entirely; no
         daemon running skips it too; `send_command()` raising (socket
         error/timeout/unreachable, or the daemon's own `status: "error"`,
         which `send_command()` turns into a `RuntimeError`) is caught and
         treated identically to "no daemon"; a decline
         (`busy_task_running`/`busy_swap_in_flight`/`cooldown`/
         `unload_attempted_unconfirmed`, or any unrecognized outcome
         string) is reported as the original denial with no retry
         attempted. A second retry-side denial (the daemon released, but
         the retried load is ALSO gate-denied) is not retried again —
         single retry only, matching the sub-task's explicit "don't loop"
         requirement. A second new helper, `_is_unrecovered_gate_denial(loader)`,
         lets each of the four call sites distinguish "bail with a clear
         failure" (an unrecovered `GATE_DENIED`/`GATE_DENIED_HARD` — the
         reservation was genuinely and permanently denied) from "let it
         lazy-retry" (`SPAWN_FAILED`/`ERROR` etc. — `core/inference_v2.py`'s
         own `ensure_model()` call already retries these at actual
         inference time, so the CLI proceeding into the REPL/`run_init()`/
         etc. with no model loaded was already this project's existing,
         deliberate degradation path for those outcomes, left unchanged).
         `shutdown()` was read in full and found already correct for this
         sub-task's purposes — it already checks `if _daemon_is_running():
         return` before touching `loader.unload()`, leaving a
         daemon-owned model alone; no change needed. `_sigterm_handler`'s
         docstring (which named the exact `load_primary()` call pattern
         being replaced) updated so it still describes reality post-edit.
         Tests: new `tests/test_main_gate_recovery.py` (16 tests —
         first-try success, non-gate failures untouched/no daemon contact,
         no-daemon-running, daemon-releases-retry-succeeds,
         already-unloaded-retries-too, three decline outcomes all report
         the original denial with no retry, `send_command()` raising
         treated like no daemon, a second gate denial on the retry isn't
         retried again, the bounded timeout is actually passed, and
         `_is_unrecovered_gate_denial()`'s five outcome cases) using a
         scripted `FakeLoader` (`load_primary()` raises if called more
         times than scripted, directly enforcing "at most one retry").
         Full suite `pytest tests/ -q` — 411 passed, 1 skipped, 3
         deselected (see `NEW-93`: a pre-existing, unrelated test-isolation
         gap in `tests/test_new19_patch_failed_repeat_escalation.py` that
         fails any time `main.py` has an uncommitted working-tree diff
         when the suite runs, reproduced with/without this round's diff
         present to confirm it's not this round's logic). **Findings
         outside this sub-task's scope, logged not fixed** (see
         `NEW_ISSUES.md`): `NEW-92` (the `args.init`/`args.tdd`/`args.fix`
         branches call `load_primary()` unconditionally, with no
         `is_remote_backend()` guard, unlike `repl()` right above them —
         a remote-backend user still spawns a local 7B on those three
         paths); `NEW-93` (the test-isolation gap above). **This closes
         all five sub-tasks of TODO.md 7.4** — the item as a whole is
         code-complete but NOT live-verified (none of the five sub-tasks
         have had a real on-device model-load test yet; real device
         testing is queued separately in `LIVE_TEST_QUEUE.md`, not claimed
         done here). Still needs its mandatory `code-reviewer` pass before
         commit (CLAUDE.md rule 4 — process-lifecycle-adjacent CLI code).

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
- [ ] 11.x (`CODEY_OS_MASTER_VISION.md` Section 11, 2026-08-09 amendment,
      elaborated same-day with 11.9-11.11, then 11.13) — **Not yet
      actionable as a whole; parked until a domain agent that needs it is
      actually scoped** (one narrow slice of 11.9 is an exception — see
      `U.31` below, split out because it's immediately useful, not
      because the broader vision is ready to build). Names the Model
      Orchestrator layer above the resource gate (7.4): models as
      ephemeral load→work→unload workers, structured stage-to-stage
      handoff (extends 7.5's context-passing work with a compact-record
      shape instead of full context), a fuller resource profile than 7.4
      currently computes (GPU/NPU utilization, battery/charging state,
      model load time, estimated inference cost — none of this exists in
      `core/resource_gate.py` today), and per-model requirement
      declarations (extends 9.3's proposed manifest fields with priority
      class + load-time estimate). **11.9-11.11 (added after round 13's
      live-verification found the concrete problem)**: adaptive `n_ctx`
      and CPU allocation computed per load attempt instead of a fixed
      global constant (`utils/config.py`'s `MODEL_CONFIG["n_ctx"]` today
      has no override and no per-model/per-condition adjustment — this is
      literally why round 13's substitute model got hard-rejected);
      per-domain approved model lists spanning largest→medium→smallest,
      extending 9.3; confidence-gated escalation to a larger model when a
      smaller one's result confidence is too low, making 11.7's
      illustrative `request_second_pass()` line concrete. **11.13 (added
      same round)**: OpenRouter as a configurable, orchestrator-selectable
      tier in 11.10's per-domain approved lists, not just today's static
      startup-time `CODEY_BACKEND`/`CODEY_BACKEND_P` env-var choice —
      per-domain enable/disable, per-domain model selection (or one
      shared model for all domains), and three usage modes (cloud-only,
      local-only, automatic — with automatic explicitly distinguishing
      "no viable local model" from "device can't currently run one" as
      two different triggers). Names a real tension worth surfacing to
      the user, not silently deciding: this project's local-first framing
      (Section 1: "no cloud dependency required") vs. a domain opting
      into cloud-only, which sends that domain's data off-device by
      choice. Explicitly illustrated with a future Android-control/vision-agent example — 
      describes target architecture shape, not a commitment to build
      Gmail/Android-automation capability now. Do not start building any
      of this (except `U.31`) until a concrete domain agent needing it is
      scoped through the normal pipeline. `core/resource_gate.py`'s
      existing admission logic (7.4) is unchanged by this — this section
      names the layer *above* it, not a revision to what's already built
      and approved.

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
      `core/observability.py`'s wrap folds in here. **Scoping pass
      complete, 2026-08-09** — see WQ Track 3 item 2 for the full
      5-sub-task build order (A: resource snapshot + `/status` wiring,
      no daemon behavior change; B: TUI/GUI interactive-session signal,
      GUI half pending an open question to Ish; C: gate queue dispatch +
      move planning off the socket handler, mandatory code-reviewer +
      live-verifier; D: autonomous shutdown tripwire + retire the unused
      socket-triggerable shutdown path; E: `daemon_control` plugin/
      manifest update) and two doc corrections (`daemon_shutdown` lives
      in `core/daemon.py`, not the plugin; no shipped script calls the
      socket `shutdown` handler today). **Sub-task A (resource snapshot +
      `/status` wiring) code-reviewer-approved and committed (`c48f77b`,
      2026-08-09)** — no process-lifecycle risk, so code-complete is its
      correct final status, not a stand-in for live-verified. **Sub-task
      B (TUI/GUI interactive-session signal) code-reviewer-approved
      2026-08-10, both TUI and GUI halves in scope per Ish's call**: a
      round-1 bug (single shared `TUI_PID_FILE` let one TUI session's
      write/crash/exit silently erase a different live session's
      presence — three distinct paths, all reproduced) was fixed by
      switching to one atomically-written file per session
      (`TUI_SESSIONS_DIR`) instead of one shared file; a real
      `os.fork()`-based two-PID test now covers it. Not live-verified —
      code-complete/mock-and-real-subprocess-unit-tested only; this sub-
      task touches PID-file/lock logic per CLAUDE.md rule 4 so it had a
      mandatory (two-round) review, but no daemon dispatch/shutdown
      behavior actually changed yet (that's sub-tasks C/D). **Sub-task C
      (gate queue dispatch on A+B, move planning to the pull side)
      scoped 2026-08-10** — see WQ Track 3 item 2 for the full build
      order; code-complete, see status further below. Scoping surfaced
      `NEW-112` (Confirmed):
      `_handle_command`'s enqueue branches have zero live callers today
      (the only live caller of the `command` socket cmd always sends
      `plan_only: True`, a synchronous planning-oracle RPC that returns
      before either enqueue branch runs) — resolves the response-contract
      question the parent decision raised (no live caller depends on the
      fields a deferred-planning response would drop) and reshapes the
      sub-task: the `plan_only` RPC path stays as-is and is explicitly
      exempt from the new interactive-session gate (its caller IS the
      interactive session asking on its own behalf); the enqueue branches
      get a new `needs_planning` task-queue flag and planning moves to
      `_process_planner_tasks()`. New predicate `can_dispatch_task()`
      (`core/resource_gate.py`, next to `can_admit()`) composes sub-task
      A's snapshot + sub-task B's interactive-lock signal; `cpu_percent
      is None` (confirmed always true on this device per `NEW-108`) is
      treated as "signal unmeasured, don't refuse solely on it," mirroring
      `can_admit()`'s existing temperature-None fail-open precedent — the
      alternative (fail-closed) would permanently wedge dispatch on this
      hardware. Nothing in this sub-task needs Ish's direct input. Still
      mandatory code-reviewer AND live-verifier — first sub-task where
      daemon dispatch behavior actually changes. **Sub-task C
      code-reviewer-approved 2026-08-10**: claim-order fix (gate check
      before `try_claim_task()` in both branches), the `no_plan`
      inversion fix, `plan_only=True` path preservation, the
      `needs_planning` column migration, and the gate logic itself were
      all independently re-verified, including a negative-control test
      proving the claim-order regression test actually catches a real
      regression. Full suite verified at 496 passed, 1 skipped. Two
      findings surfaced by review were logged (not fixed, out of scope
      for this sub-task): `NEW-113` (`Daemon.__init__`'s
      `self.server.planner = self.planner` wiring is now dead code —
      `_handle_command` no longer reads `self.planner`/`server.planner`)
      and `NEW-114` (a crash window between `add_tasks()` creating
      expanded multi-step rows and `complete_task()` marking the
      superseded raw row `done`, with no stale-`running` reaper anywhere
      in the codebase to recover an orphaned row — a genuine new gap this
      sub-task's restructuring introduces). **Sub-task C: genuinely
      live-verified, 2026-08-10** (replaces the earlier held-pending-
      Ish's-go-ahead status). With a real TUI session made active (a PID-bearing
      lock file under `~/.codeyOS/tui-sessions/`) and a task inserted
      directly via `state.add_task()`, the daemon logged a real refusal
      repeatedly across ~40+ seconds/many ticks — verbatim `Daemon:
      dispatch deferred (direct task 1) — interactive TUI/GUI session
      active — deferring background dispatch` — with the DB row staying
      `status=pending` throughout. Removing the TUI session file caused
      the very next tick to claim and dispatch the task (`Daemon:
      executing direct task 1: echo LIVE_VERIFY_SUBTASK_C_MARKER...`,
      `started_at` populated). The task itself then failed at the
      model-load step because the resource gate independently denied
      the 7B load for its own reasons (headroom/thermal) — expected, not
      a sub-task C bug. Daemon stopped cleanly afterward via its tracked
      PID, no traceback, `llama-server` confirmed clean, PID file
      removed — satisfies the sub-task's own live-verification criterion
      in full (WQ Track 3 item 2 sub-task C). One test artifact was left
      in the real `~/.codeyOS/state.db` as a side effect of this run:
      task id=1 (`echo LIVE_VERIFY_SUBTASK_C_MARKER...`), `status=done`
      (see new finding `NEW-120` on why a model-load failure like this
      one persists as `done` rather than `failed`) — not production
      data, not cleaned up by this verification-only round. **Sub-task D
      (`should_trip_shutdown` autonomous tripwire + retire the socket
      `shutdown` handler) — code-reviewer-approved, and now live-
      verified 2026-08-10, with one scope caveat** (see below).
      `PENDING_ISH_DECISIONS.md` item 2's CPU-signal question
      (strict AND vs. thermal-only vs. CPU-as-veto-only-when-measurable —
      see WQ Track 3 item 2 sub-task D for the full three-option writeup)
      was **decided by Ish, 2026-08-10: option 3 (CPU-as-veto-only-when-
      measurable)** — `should_trip_shutdown()` trips on sustained severe
      thermal alone whenever CPU is unmeasurable (always, on this device,
      per `NEW-108`), and additionally requires a genuine `>90%` CPU leg
      on any future hardware/environment where CPU IS readable. Implemented
      in `core/resource_gate.py`: rolling thermal-history sampler
      (`sample_temperature_c()`/`get_temp_history()`/
      `reset_temp_sampler()`, mirroring sub-task A's CPU sampler),
      `should_trip_shutdown()`/`_sustained_trailing_run()`, watchdog-tick
      wiring in `core/daemon.py`'s `_main_loop()`, `THERMAL_CONFIG`
      duration/threshold keys with `CODEY_SHUTDOWN_TRIP_AFTER_SEC`/
      `CODEY_SHUTDOWN_CPU_PCT` env overrides for live-verification,
      routing exclusively through the existing `_trigger_shutdown()`
      (never a raw exit), and full removal (not a no-op) of the socket
      `shutdown` handler and the now-unused `daemon_shutdown()` helper.
      A sparse-history false-trip bug (`_sustained_trailing_run()`
      checking only the *fraction* of present samples above threshold,
      never their density, so e.g. two samples 25 minutes apart could
      trip the daemon) was found and fixed in code-reviewer's first pass
      — a minimum sample-density check was added alongside the existing
      span + fraction checks, with a regression test for the exact
      reviewer-reproduced case. **Sub-task D: live-verified, 2026-08-10**
      (replaces the earlier held-pending-Ish's-go-ahead status). With
      `CODEY_SHUTDOWN_TRIP_AFTER_SEC=70` and
      `CODEY_TEMP_CRITICAL_C=36` (real ambient measured at 37.0°C), a
      fresh daemon accumulated the sustained-window history tick by
      tick — verbatim warning lines confirmed the window growing 0s →
      30s → 60s of the required 70s — then fired:
      `Autonomous shutdown tripwire fired: sustained thermal trip (100%
      of samples over a 91s trailing window at/above 36 (most recent
      sample 37.0)); CPU unmeasurable on this device (NEW-108) —
      thermal alone sufficient per Ish's 2026-08-10 option-3 decision`.
      The daemon exited cleanly (no traceback in the full log — confirms
      no double-close issue from `_trigger_shutdown()`'s direct
      `self.server.server.close()` call), `ps aux | grep llama-server`
      showed only the grep, the PID file was removed, and
      `resource_gate_state.json` showed `[]` (no leaked slot). **Scope
      caveat, stated plainly rather than glossed over:** the primary 7B
      model never actually held a gate slot during this run — it was
      independently denied admission by the same
      `THERMAL_CONFIG["temp_critical"]` threshold the test had to lower
      to make the tripwire reachable at all (`can_admit()` and
      `should_trip_shutdown()` deliberately share this one threshold),
      plus leftover headroom pressure from an earlier harness mistake in
      this session. So the `[]`/no-leaked-slot result is confirmed only
      for the embed-server model (which WAS resident and released
      silently-on-success, as designed) — **not re-verified for the
      primary model**, and structurally can't be with the two thresholds
      sharing one value; decoupling them would be required to close that
      gap in a future round. Also not captured in this pass: the
      `free -h` immediately-before/after evidence the sub-task's own
      live-verification criterion (WQ Track 3 item 2 sub-task D)
      enumerates — this run supplied every other enumerated evidence
      item (accumulating warning lines, trip-fired line with reason,
      no-traceback exit, clean `llama-server`/PID-file state,
      `resource_gate_state.json`) but not that one; note it as
      unsupplied rather than inferring it. One new finding surfaced live
      this round, not previously known: `NEW-118` (Confirmed) —
      `_trigger_shutdown()` doesn't short-circuit the rest of the
      watchdog tick that calls it, so the model-load watchdog
      (`core/daemon.py`'s `_watchdog_check_model()`) still ran
      immediately after the trip decision in the same tick; harmless in
      this run only because the resource gate independently denied that
      load attempt. **Sub-task E (`daemon_control` plugin/manifest
      update) — scoped and text written 2026-08-10, pending
      code-reviewer approval.** Pure docs/description text, no
      capability-registration change: every capability's `name`/
      `implementation` in `manifest.json` is byte-identical to before;
      only the module docstring and the top-level manifest
      `description` changed. Corrected: handler count is 7 post-D (not
      6 as an earlier pass of `NEW-116` itself miscounted — see
      `NEW-122`); `shutdown` is now "nothing left to wrap" rather than
      "deliberately unwrapped"; `command` stays unwrapped on updated
      reasoning (item 2's decision resolved HOW it behaves, not whether
      the resulting real-inference side effect is safe to expose,
      determined by re-reading `PENDING_ISH_DECISIONS.md` item 2
      directly); `release_model_slot` — previously omitted from the
      "2 unwrapped" count entirely — added with its own distinct
      reasoning (internal CLI-to-daemon coordination primitive, wrong
      audience for agent capabilities, not a risk-tier case). `/status`
      deliberately NOT newly wrapped here: verified
      `core/observability.py`'s `status()` is already exposed as
      `system.observability_full_status` in the separate, pre-existing
      `ccos/plugins/system/observability/` plugin, and that its `State`
      singleton is never populated by `core/daemon.py` (cross-`core/`/
      `tools/`/`gui/` grep) — a fresh capability call would read the
      calling process's own empty state, not the daemon's, so
      `daemon_status`/`daemon_health` remain the right capabilities for
      daemon state. `NEW-113`/`NEW-115` re-confirmed still open but
      outside this sub-task's two-file scope — see `NEW-123`. See WQ
      Track 3 item 2 sub-task 5 for the full accounting.
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
- [x] U.27 (`NEW-96`) — **Fixed and code-reviewer-approved, 2026-08-09.**
      `core/daemon.py`'s startup preload (`_preload_primary_model()`) and
      watchdog (`_watchdog_check_model()`) both now name
      `LOAD_OUTCOME_EVICTION_FAILED` explicitly, correctly taking
      precedence over the generic fallback (verified by a real test with
      a mocked non-running server — the exact condition that would
      otherwise fall into "died"). No message promises a retry will
      succeed. Full suite 501/501. Not yet re-live-verified (`NEW-97`/
      `U.28` still blocks reaching this path in the default runtime
      shape) — code-complete, live-verification pending the next 7.4
      test round.
- [x] U.28 (`NEW-97`) — **Fixed and code-reviewer-approved, 2026-08-09.**
      `codeydOS`'s `start_plannd()` now registers `plannd`'s process with
      `resource_gate.register_slot(model_id="planner", ..., status=RESIDENT)`
      after confirming it's alive — accounting-only, same
      accounted-but-exempt pattern `core/embed_server.py` already uses;
      `plannd` still starts unconditionally, never subject to
      `can_admit()` denial. `stop_plannd()` releases the slot at all
      three of its exit paths via a new `_release_plannd_slot()` helper,
      matching on both `model_id` and `pid` to guard against PID
      recycling (a real risk the implementer checked against
      `core/embed_server.py`'s own precedent for this store).
      Shell-injection safety of the bash-to-Python bridge verified
      directly by the reviewer (env-var passing, no interpolation into
      the Python source string); `set -e` correctly neutralized around
      both calls so a registration/release failure can never change
      `start_plannd()`/`stop_plannd()`'s exit codes. One misleading
      comment (implied RESIDENT registration feeds admission math; it
      doesn't — `total_reserved_bytes()` deliberately excludes RESIDENT
      slots, visibility only) corrected before commit. Surfaced `NEW-100`
      (a newly-observable contradiction: `release_model_slot` can report
      `already_unloaded` for the planner while the gate's own store still
      shows `plannd` RESIDENT) and `NEW-101` (bounded, low-severity
      duplicate-registration on an unclean `plannd` crash) — neither
      fixed, both logged. Not yet re-live-verified — `U.27`+`U.28`
      together are what the next 7.4 live-test round needs.
- [ ] U.29 (`NEW-98`, Suspected, low severity) — `resource_gate.py`'s
      `DEVICE_CEILING_USABLE_FRACTION`/`REQUIRED_HEADROOM_FACTOR`
      calibration comment overstates the real margin — live-measured at
      137MiB (not "comfortable") for the production 7B on this device.
      No action required unless the thinness itself is judged a problem;
      logged per sub-task 1's own stated intent to validate these
      constants against real behavior.
- [ ] U.30 (`NEW-99`, Suspected, same class as `NEW-83`) — `codeydOS`'s
      port-scoped `pkill -9 -f "llama-server.*8080"`/`*8081` pattern-kills
      rather than tracking a specific PID — less severe than the bare-name
      `NEW-83` bug already fixed (port-scoped narrows the blast radius),
      same class, not confirmed to have misfired. Natural companion fix
      to `NEW-85` (the wider `codeydOS`/`codey-stop` pkill sweep already
      queued).
- [x] U.31 (`NEW-95`'s own stated fix direction / vision Section 11.9's
      narrow actionable slice) — CODE COMPLETE (not yet live-verified).
      Added a documented `CODEY_N_CTX` env-var override for
      `utils/config.py`'s `MODEL_CONFIG["n_ctx"]` itself (default `32768`
      unchanged when unset), not a gate-only override on
      `core/resource_gate.py` as originally scoped above — a gate-only
      override would have desynced the gate's admission cost estimate
      from the real `llama-server -c` flag both `core/loader_v2.py` and
      `core/planner_loader.py` derive from this same
      `MODEL_CONFIG["n_ctx"]` value (the `NEW-84` class of bug). Follows
      the exact `os.environ.get(...)`-at-import-time pattern already used
      for `MODEL_PATH`/`PLANNER_MODEL_PATH`/`SECONDARY_MODEL_PATH` in the
      same file, since `n_ctx` (unlike a test-only model architecture
      override) is a legitimately production-tunable value. A non-integer
      or non-positive (0/negative) `CODEY_N_CTX` raises `ValueError` at
      import time (loud failure, not a silent fallback) — non-positive is
      checked explicitly since `int()` alone accepts 0/-1 and either
      would flow into `resource_gate`'s KV-cache cost estimate as a
      zero/negative term, causing the gate to under-estimate cost and
      over-admit. Verified every reader of `MODEL_CONFIG["n_ctx"]` in the
      repo (`core/loader_v2.py`, `core/planner_loader.py`,
      `core/lora_import.py`, `core/memory_v2.py`, `core/observability.py`,
      `core/summarizer.py`, `core/tokens.py`, `main.py`'s `--ctx` CLI
      override) reads the same dict key — no independent hardcoded
      `32768` elsewhere that this override would miss. Test coverage:
      `tests/test_u31_n_ctx_override.py` (unset → 32768, valid override
      used, non-numeric value raises, 0/-1 raise). Full suite: 437
      passed, 1 skipped. **Live-verified 2026-08-09 (round 18)**:
      `CODEY_N_CTX=2048` was used for a real successful admitted load,
      chosen via a real dry-run against the live gate at four candidate
      values — done, no longer outstanding.
- [ ] U.32 (`NEW-103`, Confirmed, live-reproduced round 18) — `codeydOS`'s
      `stop_daemon()`/`start_plannd()` clean up orphaned/existing
      `llama-server` processes via bare `pkill -9 -f "llama-server.*8080"`/
      `*8081` — confirmed this round as the *actual* live cleanup
      mechanism, not just a theoretical risk (it's what genuinely cleaned
      up round 18's model on teardown). Same class as `NEW-83`/`NEW-99`,
      now with live confirmation it's load-bearing in normal operation,
      not dead code. Fix direction: track each spawned server's PID at
      spawn time and kill only that specific PID, matching the discipline
      `core/daemon.py`'s `check_pid_file()`/`resource_gate.py`'s
      `_pid_alive()` already use elsewhere in this codebase. Natural
      companion to `U.30`/`NEW-99` (same files, same pattern) — worth
      doing together.
- [ ] U.33 (`NEW-104`, Confirmed, live-reproduced round 18) —
      `resource_gate.reserve_slot()`/`register_slot()` slots key to the
      *calling* process's PID by default, never the spawned
      `llama-server` child's — live-reproduced: after a CLI
      release-then-retry cycle, `list_slots()` showed zero `primary`
      entries while a real, healthy `llama-server` was still running
      (the CLI's own short-lived PID died on exit, taking its slot's
      identity with it). Mirrors on the daemon's own side too (slot `pid`
      is the daemon process, not its `llama-server` child; `port` is
      never set) — a code-read consequence, not separately reproduced.
      Impact is accounting/observability, not admission-safety (the live
      headroom check reads real `/proc/meminfo` directly, unaffected).
      Fix direction: at both `reserve_slot()`/`mark_resident()` call
      sites in `core/loader_v2.py`/`core/planner_loader.py`, once the
      actual spawned child's PID/port are known, update the slot's
      `pid`/`port` fields to the real process — `register_slot()`'s own
      docstring already anticipates exactly this usage, neither call site
      uses it yet.
- [ ] U.34 (`NEW-105`, Confirmed, live-reproduced round 18) —
      `core/loader_v2.py`'s `confirm_resident_and_mark_slot()` (a
      `MemAvailable`-delta poll) never actually confirmed either
      successful load in round 18, despite real RSS matching the cost
      estimate almost exactly both times — fell through to its own
      documented "mark resident anyway" fallback every time. Not a safety
      regression (the fallback correctly avoids a worse failure mode, a
      permanently-stuck PENDING slot) — but the confirmation mechanism's
      actual job (distinguishing "genuinely landed" from "still just
      declared") never once succeeded. Reasoned cause, not separately
      instrumented: `mmap`'d weight pages may not produce a clean
      `MemAvailable` drop the way fresh anonymous allocation would.
      Retuning candidate: a different signal (e.g. RSS-based rather than
      `MemAvailable`-delta-based) may be the right fix, but that needs
      real investigation, not a guess.

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
