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

      **Scoping pass, 2026-08-11 (project-architect, desk-only, no code
      changed, no live model load run — one pure-arithmetic cost-estimate
      call against real `/proc/meminfo`, no spawn).** Assessment of what's
      actually left, since a prior round's framing (from Phase 4.1
      sub-task D's live-verification, a *different* task's test) implied
      the primary model's load-through-gate-then-unload cycle was wholly
      unverified — that framing is corrected here, not accepted at face
      value (`NEW-130`).
      - **Code-complete, all five sub-tasks**: unchanged from above — true
        since 2026-08-09, code-reviewer-approved.
      - **Live-verified, primary role's gate *mechanism***: round 18
        (`aa18b7a`, 2026-08-09) really admitted, spawned, and later really
        released (via a real `release_model_slot` request, not a mock) a
        real, resident `"primary"`-role slot — confirmed by `NEW-104`'s
        PID-level evidence. `WORK_QUEUE.md`'s 7.3 sub-task E note wrongly
        claimed the opposite; corrected there, 2026-08-11, per rule 6.
      - **NOT live-verified**: the real production model
        (`~/models/qwen2.5-coder-7b/qwen2.5-coder-7b-instruct-q4_k_m.gguf`)
        at the real production default `n_ctx` (32768) has never actually
        been spawned through the gate — round 18 used a substitute
        (Qwen3-4B) at a test-only `n_ctx=2048`, because at the time no
        smaller-real-footprint substitute was thought to admit at
        production `n_ctx` at all. **This is not a dead end, but it's
        tighter than it first looks**: a desk-only cost-estimate call
        this round (`NEW-131`,
        `core/resource_gate.estimate_model_load_cost()`/`can_admit()`
        against the real file and a real live `/proc/meminfo` read, no
        spawn) found the real 7B at `n_ctx=32768` is `hard_reject=False`
        — estimated cost 6830557184 bytes (~6514MiB) is only 136MiB
        (~2.1%) under this device's device_ceiling_bytes 6973872537
        (~6650MiB), not "comfortably" under it. It was denied just now
        by the separate *budget check* (transient headroom: 5845012480
        bytes/~5574MiB available at calculation time, needs ~8143MiB/
        ~7.95GiB with the 1.25x margin). **Historical-peak check (desk
        grep of `PROJECT_LOG.md`, no new live run)**: the highest
        `MemAvailable` this project's own live-test history has ever
        recorded is ~7.6GiB (round 13, daemon-only post-teardown state,
        `plannd` not running) — ~350MiB short of the ~7.95GiB this
        specific config needs. No historical capture has ever reached
        the bar. This doesn't prove the pass below is unreachable (that
        7.6GiB reading wasn't a maximally-clean boot state, and the
        estimate above used the optimistic `reserved_bytes=0` — a
        resident embed server's slot would subtract further), but a
        denial on the pass below would be consistent with this device's
        entire history, not a surprise or a sign of a broken gate.
      - **This is a live-verification-only gap, not unbuilt scope** — no
        new code is needed to attempt it, `CODEY_N_CTX` just needs to
        stay unset (the 32768 default) for this one test, unlike every
        prior live-test round. But given the historical-peak check above,
        **a denial result should be treated as informative, not as
        "the gap is now closed"** — only a genuine admission (or a
        denial whose margin, in real bytes, is captured and compared
        against this note's numbers) actually closes it; a denial with
        no numbers recorded would not.
      - **Scoped next action for live-verifier**: on a **daemon-only
        harness** (`NEW-121` notes `codeydOS start` currently always
        launches `plannd` alongside the daemon — start the daemon process
        directly, or kill `plannd` by tracked PID immediately after, per
        round 18's own precedent for reaching `can_admit()` at all), with
        `CODEY_N_CTX` unset:
        1. `free -h` before anything (rule 2), record verbatim.
        2. Confirm no `llama-server`/`plannd` process resident:
           `ps aux | grep llama-server` showing only the grep.
        3. Start the daemon only; let its startup preload attempt to load
           the real primary model at `n_ctx=32768` through `can_admit()`.
        4. Record the actual `GateDecision` verbatim (admitted or not,
           and the exact byte figures in the `reason` string) — a denial
           on headroom is a valid, informative result, NOT a failed test,
           but it must include the real numbers (not just "denied") to
           be comparable against this note's historical-peak figures; if
           admitted, confirm exactly one resident `"primary"` slot, cost
           matching the estimate above, and that
           `confirm_resident_and_mark_slot()` behaves as it did in round
           18 (`NEW-105` — may fall through to its fallback again; that's
           already known, not a new failure to chase).
        5. If admitted: request `release_model_slot` for `"primary"` (via
           a second CLI process attempting its own load, matching round
           18's Stage 2 pattern, or a direct daemon socket command) and
           confirm the release actually happens — `list_slots()` empty,
           `ps aux | grep llama-server` showing only the grep, `free -h`
           after showing RAM actually returned.
        6. `free -h` after full teardown (rule 2), record verbatim.
        7. Log the real numbers to `PROJECT_LOG.md`/this entry regardless
           of outcome — a denial with real numbers closes this gap just
           as usefully as an admission would, since the open question is
           "does the real config get a fair shot at the gate," not
           "does it always succeed."
      - **Not in scope for this live-verification pass, and not blocking
        it**: `NEW-129`'s `temp_critical` sharing between `can_admit()`
        and `should_trip_shutdown()` — that only matters for testing the
        *autonomous shutdown tripwire's* slot-release guarantee for the
        primary model (Phase 4.1's item, not 7.4's), and this pass
        doesn't need to touch `temp_critical` at all. `NEW-104`
        (pid/port slot binding) and `NEW-105` (confirm-poll never firing)
        are known, non-blocking, accounting-only gaps — expect to see
        both again in this pass; don't treat either as a new failure.
      - **Sharper flag to Ish, not resolved here** (per `NEW-131`): the
        shipped default `n_ctx=32768` requires ~7.95GiB of
        `MemAvailable` to pass the gate's own budget check on this
        10GiB device — a bar this project's entire live-test history has
        never once reached (highest ever recorded: ~7.6GiB, round 13).
        Is 32768 the right production default for this device, or should
        the production default itself come down (with `CODEY_N_CTX`
        remaining the override mechanism it already is)? This directly
        conditions 7.3 sub-task E's tier thresholds and whether "closed"
        for 7.4 should mean "the mechanism works and the config is
        admissible in principle" (already true) or "the shipped default
        actually loads on this device in normal conditions" (still
        genuinely open) — a product decision, not an implementation
        detail, not guessed at here.
      - **Diagnostic follow-up to `NEW-131`, 2026-08-11 (read-only, no
        model load, per Ish's explicit request before deciding on
        `n_ctx`): investigated *why* `MemAvailable` never reaches
        7.95GiB on this device, rather than assuming it's a hard
        ceiling.** Verbatim `free -h` baseline (fresh capture, no model
        loaded):
        ```
                       total        used        free      shared  buff/cache   available
        Mem:            10Gi       5.2Gi       1.2Gi        55Mi       4.4Gi       5.3Gi
        Swap:           11Gi       2.3Gi       9.7Gi
        ```
        Repeated ~1 min later (same idle state): `available` 5.4Gi,
        `Swap` used 2.4Gi/free 9.6Gi — stable, not actively draining or
        recovering. **Correction to the "Termux/Android often has zero
        swap" assumption this follow-up was scoped to test**: this
        device *does* have swap, and it's already in active use. `/proc/
        meminfo` shows `SwapTotal: 12582908 kB` (~12GiB) backed by
        `/sys/block/zram0` (`disksize` 12884901888 bytes = 12GiB;
        `mm_stat`: ~2.48GiB of logical data compressed into ~608MiB of
        physical RAM, roughly 4:1) — Samsung's zram, already holding
        2.3-2.4GiB of swapped-out pages at idle. `getprop` confirms
        Samsung's own low-memory-killer config (`ro.slmk.swap_free_low_
        percentage`), consistent with a real, actively-managed swap
        subsystem, not an absent one.
        **But this doesn't move the needle on the gate's check, because
        `MemAvailable` structurally excludes swap** — it's the kernel's
        estimate of memory obtainable *without* swapping (free pages +
        reclaimable cache, watermark-adjusted), and `SwapFree` never
        enters that formula. Verified against this capture's own
        `/proc/meminfo`: `MemFree 1244408` + `Cached 4176184` +
        `SReclaimable 471532` ≈ 5.89GiB, roughly matching the reported
        `MemAvailable: 5573052` kB (~5.57GiB) once the kernel's
        watermark reserve is subtracted — `SwapFree`'s 10.1GiB literally
        does not appear in the sum. **So "add swap" is a non-lever
        twice over: swap already exists at ~12GiB capacity, and even if
        more were added it would not raise `MemAvailable` by itself.**
        Doing the ceiling arithmetic from this same capture: `MemTotal`
        11350704 kB (~10.82GiB) minus what's structurally non-reclaimable
        right now (`AnonPages` 3051092 + `SUnreclaim` 608436 +
        `PageTables` 247884 + `KernelStack` 122488 + `Unevictable`
        207808 ≈ 4.24GiB) puts a theoretical ceiling around ~6.6GiB *at
        this snapshot's anon load* — below both the historical 7.6GiB
        peak and the gate's 7.95GiB bar. Reaching 7.95GiB would require
        Android's total anon footprint to drop under ~2.8GiB from
        today's ~3.05GiB; this is one snapshot's ceiling, not a swept
        maximum, since anon load varies with whatever Android is
        holding resident at the time.
        **No reclaimable Codey-OS-side hogs found.** `ps aux --sort=-
        %mem | head -30` verbatim (top of list only; full session-only
        process view, see below):
        ```
        USER       PID %CPU %MEM    VSZ   RSS TTY      STAT START   TIME COMMAND
        u0_a247  23783  6.5  3.5 6776016 404764 pts/0  Sl+   1970   6:50 ld.so .../claude-code-linux-arm64/claude --resume
        u0_a247  23776  0.0  0.2 13604388 33136 ?      Ssl   1970   0:05 node .../proxy.cjs ...
        u0_a247  23234  0.0  0.0 13440740 9476 pts/0   Sl+   1970   0:00 node .../claude --resume
        ```
        (remaining rows are this shell/`ps`/`head` invocation itself).
        A targeted search (`ps aux | grep -iE "llama-server|main\.py|
        daemon|codey"`) returned zero matches — no stray/orphaned
        `llama-server`, `main.py`, or daemon processes left resident
        from past sessions. The only meaningful resident memory visible
        to Termux is this very live-verifier session's own `claude`
        CLI process (~405MiB RSS) plus its proxy (~33MiB) — not
        something reclaimable without ending the session doing the
        investigating.
        **Android/OS-level memory is structurally invisible from
        Termux, not just unexamined**: `id` returns
        `uid=10247(u0_a247) ... context=u:r:untrusted_app_27:s0:...` —
        a sandboxed app UID, and `ps aux` only ever showed processes
        under that same UID (confirmed above), consistent with
        Android's per-app process isolation. `swapon`/`dumpsys` are
        both absent from Termux's PATH and `/proc/swaps` returned
        `Permission denied` — there is no available tool, rooted or
        not, to inspect what other Android apps/system services are
        holding resident. The ~5.2GiB `used` in the `free -h` baseline
        above is therefore mostly *not* attributable to anything
        Codey-OS or Termux itself controls or can see.
        **Verdict**: this is closer to a real, mostly-fixed OS-level
        ceiling than a reclaimable-headroom problem — no stray
        processes to kill, no missing swap to add (it already exists
        and isn't the limiting factor for this specific metric), and no
        visibility into whatever Android itself is holding. The one
        genuinely open, not-yet-decided question this surfaces (outside
        this task's scope to resolve, flagging rather than fixing per
        CLAUDE.md rule 8 — may warrant its own `NEW_ISSUES.md` entry):
        `NEW-21`'s own history shows real loads on this device
        *succeed* by swapping (baseline 4.3Gi used/2.2Gi free, single
        load drove swap 1.2Gi→5.6Gi in ~10s) — meaning the gate's
        `MemAvailable`-only budget check is gating on a metric that
        structurally cannot see the swap capacity the workload actually
        relies on. That reframes the option set beyond "lower `n_ctx`
        vs. find more free RAM": it may also be "is `MemAvailable` the
        right signal at all for this gate, or should the budget check
        incorporate `SwapFree`/zram capacity instead/in addition." Not
        decided here — still Ish's call, now with real numbers instead
        of a guess.

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

- [ ] 7.4a (WQ Track 3 item 1b, new item spun off 7.4's own closing
      question, 2026-08-11) — **Swap-aware resource-gate budget check.**
      Ish's direct decision (2026-08-11): redesign `can_admit()`'s budget
      check to account for zram/swap capacity, not `MemAvailable` alone —
      see `TODO.md` 7.4's own diagnostic follow-up entry above (the
      `MemAvailable`-structurally-excludes-swap finding) and `NEW-21` for
      the originating evidence. Scoped as its own item, not folded into
      7.4: all five of 7.4's sub-tasks are code-complete and
      code-reviewer-approved already, and reopening that scope would blur
      the code-complete/live-verified distinction rule 7 requires; this
      item resolves 7.4's own dangling closing question ("is
      `MemAvailable` the right signal at all for this gate"), so treat it
      as that question's answer, cross-referenced both ways, not a
      duplicate. **7.4's own pending live-verification pass (the real 7B
      at `n_ctx=32768` through the gate) is now sequenced behind sub-task
      C below** — running it before C would just re-confirm the same
      `MemAvailable`-only denial already captured in 7.4's notes.

      **Scoping correction to the mandate itself, before any sub-task
      detail — read this first**: `NEW-21` is real evidence that a load
      can *complete its spawn* while swapping (RSS squeezed 5.6GB→1.26GB
      as swap climbed 1.2Gi→5.6Gi in ~10s), but it does NOT show that
      loads *work* under swap — no inference request ever reached that
      server that run (independently confirmed in `NEW-21`'s own text),
      so post-swap performance/stability is unmeasured, n=1, from an
      otherwise-inconclusive round. This justifies building the
      *mechanism* (a swap-aware secondary check) — it does not yet
      justify any specific threshold. Any threshold proposed below is a
      first, un-calibrated default in the same spirit as
      `REQUIRED_HEADROOM_FACTOR`/`DEVICE_CEILING_USABLE_FRACTION`, not a
      value derived from a controlled measurement — sub-task E's live
      pass is what's actually supposed to produce that measurement (real
      inference latency under a swap-assisted admission, not just "did it
      spawn").

      **zram-specific risk, not previously considered and worth flagging
      up front**: zram is a compressed block device living *inside*
      `MemTotal`, not extra capacity outside it — swapping to it buys
      compression ratio, not new memory, and costs CPU to compress/
      decompress. The ~4:1 ratio observed in 7.4's diagnostic capture
      (`mm_stat`: ~2.48GiB logical → ~608MiB physical) was measured on
      ordinary Android app anon pages at idle, not on model weights.
      Quantized (Q4_K_M) model weights are already high-entropy,
      compressed data — the same 4:1 ratio may not hold for them at all
      (closer to 1:1 is plausible, meaning swapping model pages to zram
      buys much less headroom than the ratio above would suggest, while
      still costing CPU). **This is unverified — sub-task E's live pass
      should capture the actual in-model-load compression ratio via
      `/sys/block/zram0/mm_stat` sampled during the load, not assume the
      idle-anon-page ratio carries over.** Until measured, do not treat
      `SwapTotal`/`SwapFree` capacity as 1:1 usable headroom.

      **Device-grounded constant available, not previously in this
      project's docs**: `getprop ro.slmk.swap_free_low_percentage` on
      this device reads `10` — Samsung's own low-memory-killer (`slmk`)
      config kills processes once `SwapFree` drops below 10% of
      `SwapTotal` (≈1.2GiB at this device's ~12GiB `SwapTotal`). This is
      a real, device-sourced floor (not a guessed constant) that any
      swap-budget check must stay above — the swap-budget check's
      permitted-swap-usage ceiling should be derived from this, not
      picked independently. (`ro.slmk.2nd.swap_free_low_percentage` also
      reads `10` — same value on this device's secondary profile, for
      what that's worth; not further investigated.)

      **Hard invariant, must not be relaxed by this work**:
      `compute_device_ceiling_bytes()` (the absolute hard-reject check,
      derived from `MemTotal` only) must NEVER have swap/zram capacity
      added into its basis. Swap softens the *budget* check only — a
      single model that alone exceeds the device's usable physical-RAM
      ceiling stays permanently non-admissible regardless of swap, per
      the 2026-08-08 amendment's one remaining non-negotiable rule (see
      this module's own docstring, lines 27-29). State this explicitly in
      each sub-task's code review so no implementer "improves" the
      ceiling check by folding swap in.

      **Sub-tasks A/B/C1: done, code-reviewer-approved (three rounds —
      see below), uncommitted as of this writing.** C2/D/E unblocked as
      of Ish's 2026-08-11 decisions below, sequenced C2 → D → E since D
      needs both new `GateDecision` fields settled and E needs D done.
      A/B landed clean on the first pass. C1's implementation surfaced a
      real, pre-existing bug that this project's mandatory-review
      pipeline (CLAUDE.md rule 4) was specifically built to catch:
      C1's new `_sum_committed_bytes()` sums PENDING+RESIDENT slots
      (correct per spec), which activated a previously-dormant gap —
      `core/loader_v2.py`'s `load_primary()` and
      `core/planner_loader.py`'s `load()` both called `reserve_slot()`
      without ever rebinding the slot's `pid` to the real spawned
      subprocess PID, so `reserve_slot()`'s own dead-PID reap filter
      kept checking the long-lived loader's own PID forever — a crashed
      model left a permanent ~6.83GiB ghost slot that could never be
      reaped, and the very next reload attempt was denied by C1's own
      budget ceiling (ghost + candidate > 8.90GiB), with nothing in the
      crash-retry path able to recover. Fixed by adding an optional
      `pid` kwarg to `mark_resident()`, rebinding the slot's real PID
      inside the same lock as its PENDING→RESIDENT transition, forwarded
      from both loaders' spawned-branch call sites — this closes
      `NEW-81` (marked resolved). A second review pass caught that the
      fix broke an existing test (`FakeServerSpawned`'s hardcoded
      `pid=12345` fixture wasn't actually alive, so the now-honored
      real-PID reap logic correctly reaped it mid-test) — fixed by using
      `os.getpid()` instead, with the same pattern checked and ruled out
      elsewhere in the test suite. Third pass: **APPROVED**, full suite
      691 passed, 1 skipped, 0 failures, verified live by the reviewer
      independently. `NEW-134` logged (not fixed): a slot leaked during
      the PENDING window, before `mark_resident(pid=...)` ever runs, is
      still attributed to the loader's own PID and isn't
      liveness-reapable in that narrower window — post-C1 this now
      permanently consumes fixed-ceiling budget rather than just
      skewing a self-healing `MemAvailable`-relative figure; cross-
      references `NEW-82`/`NEW-114`. **Live-verification deliberately
      deferred to sub-task E** (Ish's call, 2026-08-11): A/B/C1 don't
      themselves change dispatch behavior yet (C2 is the actual
      swap-awareness wiring point), so live-verifying config/logic-only
      code ahead of the real integration point was judged premature —
      E already owns the full live model-load verification once C2/D
      land.
      - **A — swap signal sourcing only, no admission behavior change.**
        `read_meminfo()` (`core/resource_gate.py:72`) already parses and
        returns `SwapTotal`/`SwapFree` in bytes (line 103) — this part of
        the signal is already present with zero plumbing needed. What's
        actually missing: (1) a `read_zram_stats()` helper reading
        `/sys/block/zram0/mm_stat` (injectable path, matching
        `read_meminfo()`'s own convention), returning `None` on a
        non-Android host or absent device rather than raising — mirrors
        `read_current_temp_c()`'s fail-soft posture, since this needs to
        stay import-safe/test-safe off-device; (2) add `swap_total_bytes`/
        `swap_free_bytes`/`zram_compression_ratio` (or `None`) fields to
        `ResourceSnapshot` so `can_dispatch_task()` and any future caller
        can see swap state without a second signal-sourcing path. No
        change to `can_admit()`, `estimate_model_load_cost()`, or any
        `GateDecision`/`DispatchDecision` logic in this sub-task — pure
        additive signal sourcing, same risk class as 7.4 sub-task A
        (importing/reading these functions starts nothing, spawns
        nothing). **No CLAUDE.md rule 4 review required for this
        sub-task specifically** (no process-lifecycle/admission-behavior
        change), but still gets code-reviewer's normal lighter pass.
        **Ready for implementer now, no Ish decision needed** — sets no
        policy, only sources a signal.
      - **B — swap-aware budget as a pure, standalone function.** A new
        function (e.g. `compute_swap_assisted_headroom_bytes()` or
        similar — implementer's naming call, matching this module's
        existing naming pattern) taking `meminfo` and an explicit
        `max_swap_usage_bytes` parameter (NOT a module-level constant
        blessed as the default in this sub-task — tests pin an explicit
        value, the real default is Ish's call, see below), and returning
        the additional headroom a swap-assisted check would allow beyond
        `compute_headroom_bytes()`'s existing `MemAvailable`-only figure.
        Not called by `can_admit()` yet — pure function, independently
        unit-testable with synthetic meminfo dicts. **Pre-registered test
        case, per this scoping's own math**: feed `NEW-21`'s exact
        baseline (`MemAvailable` consistent with 4.3Gi used/2.2Gi free,
        `SwapTotal`~12GiB, `SwapFree` consistent with 1.2Gi already used)
        into this function and assert what a plausible
        `max_swap_usage_bytes` default would authorize — write the
        expected value into the test BEFORE tuning the function to match,
        not after, so the default isn't silently reverse-engineered to
        make a specific case pass. **Ready for implementer now, no Ish
        decision needed** — takes its policy constant as a parameter,
        doesn't bless a default.
      - **C1 — the new named cumulative concurrent-model budget ceiling
        (Ish's direct decision, 2026-08-11 — see "Ish's decisions" block
        below for the full derivation). Ready for implementer now, no
        further Ish input needed.** Split out from the swap-aware work
        (now C2, below) because the two push in opposite directions (C1
        tightens admission, C2 relaxes it under swap), C1 has zero
        dependency on sub-tasks A/B, and it is the piece Ish explicitly
        asked for by name — it should not be stuck waiting on C2/E's
        swap-calibration timeline.
        1. Add a new named module-level constant,
           `MAX_CONCURRENT_MODEL_BUDGET_BYTES = int(8.90 * (1024 ** 3))`
           (= 9,556,302,233 bytes — **corrected 2026-08-11, see below;
           this superseded an earlier 8.80GiB value that failed its own
           purpose, see `NEW-133`**), with a docstring/comment recording
           the exact derivation (see below) verbatim enough that a future
           reader can see where 8.90 came from without re-deriving it,
           and stating explicitly: this is device-derived from *this*
           device's real on-disk model files at n_ctx=32768 on ~10.8GiB
           `MemTotal` — it must be **recomputed** (via
           `estimate_model_load_cost()` against the real files on that
           device), not linearly scaled, if this code ever runs on
           different hardware. Also state explicitly that 8.90GiB /
           10.8GiB ≈ 0.82 being well above `DEVICE_CEILING_USABLE_FRACTION`
           (0.60) is intentional and must not be "reconciled" toward it —
           these are two different concepts (one model's absolute
           physical-RAM ceiling vs. a fixed cap on the sum of ALL
           concurrently-declared model costs), same distinction the task
           brief drew. **Also state the embed-floor caveat in the same
           comment**: the raw sum this ceiling is built from includes the
           embed model's cost as a floor estimate only (file + fixed
           overhead, no computable KV-cache term — see sub-item 7 below)
           — if sub-task E's live pass, or any future
           `estimate_model_load_cost()` change, measures the embed
           model's real resident cost above that floor by more than this
           constant's ~45.7MiB margin over the raw sum, the three-model-
           concurrent case this ceiling was built to admit could become
           inadmissible again, the same failure mode `NEW-133` found —
           re-check this constant against the real embed cost at that
           point rather than assuming the margin still holds.
        2. Add a new function alongside `total_reserved_bytes()` (matching
           its shape and its `state_dir`/`reap_dead` parameters) that sums
           `cost_bytes` across **every** live, non-dead slot regardless of
           `SLOT_STATUS_PENDING`/`SLOT_STATUS_RESIDENT` — deliberately the
           opposite filter from `total_reserved_bytes()`, because this is
           a *declared-cost policy sum* against a fixed named ceiling, not
           a live-`MemAvailable`-double-counting guard (`total_reserved_bytes()`'s
           PENDING-only filter exists specifically to avoid double-counting
           against a fresh meminfo read — this new check never touches
           meminfo at all, so that concern doesn't apply here). Document
           that this assumes every slot in the store carries a real
           `cost_bytes` — confirmed true for `reserve_slot()`'s own writes
           (`core/resource_gate.py:1820`, `"cost_bytes":
           decision.estimated_cost_bytes`, always populated) and
           positionally required (no default) by `register_slot()`'s own
           signature — but if some future caller ever calls
           `register_slot()` with `cost_bytes=0` this sum silently
           undercounts and the ceiling fails open; call this out in the
           function's docstring rather than adding new defensive code
           this task didn't ask for.
        3. **Critical wiring detail — read before implementing, this is
           the difference between a correct check and a self-race**:
           `can_admit()` itself must take the sum as a caller-precomputed
           parameter (e.g. `concurrent_committed_bytes: int = 0`), same
           convention as the existing `reserved_bytes` parameter, keeping
           `can_admit()` free of any direct state-store I/O and fully
           synthetic-test-able. **But `reserve_slot()` — the actual
           cross-process entry point (`core/resource_gate.py:1722`) —
           must compute this new sum itself, inside its own existing
           `with _LockedState(state_dir) as slots:` block (line ~1789),
           in the same place it already computes `reserved` (PENDING-only,
           line ~1797), and pass both down into its own `can_admit()`
           call.** `reserve_slot()`'s whole documented purpose is closing
           the TOCTOU window between "is there room" and "write my
           reservation" by holding the lock for the entire read-check-write
           sequence (see its own docstring) — computing the new
           PENDING+RESIDENT sum *outside* that lock (e.g. in a separate
           caller-side helper call before `reserve_slot()`) reopens
           exactly that race for this new check: two concurrent callers
           could each read a stale sub-8.90GiB total and both admit,
           together exceeding it. Any other caller of `can_admit()`
           directly (not through `reserve_slot()`) that wants this check
           enforced is responsible for computing its own consistent
           snapshot the same way — document this explicitly rather than
           leaving it implicit.
        4. **Say explicitly which call sites pass the real sum this
           sub-task, and which stay at the `0` default until D.** With
           `concurrent_committed_bytes` defaulting to `0`, every
           unmodified call site is unaffected (a real budget of `0` never
           trips the new check) — that is deliberate for callers this
           sub-task doesn't touch, but must be a stated decision, not an
           accident: `reserve_slot()` MUST pass the real sum (see item 3)
           — without that, C1 is "code complete" but the ceiling never
           actually fires anywhere live, the same failure class
           `DEVICE_CEILING_USABLE_FRACTION`'s own comment warns against
           for a ceiling that never fires. `would_model_fit()`
           (`core/resource_gate.py:1057`) is explicitly deferred to D
           (below) — do not wire it in C1.
        5. **Denial classification matters and is not the same as
           `hard_reject`.** Unlike the single-model ceiling (permanent,
           can never be satisfied by any device state change), a
           cumulative-budget denial is recoverable — release/unload
           another resident model and the same load then passes. Add a
           new `GateDecision` field (default `False`, e.g.
           `budget_ceiling_exceeded: bool`) distinct from `hard_reject` so
           callers can tell them apart. Confirmed by direct code read
           (`core/loader_v2.py:563-564,640`): the retryable-vs-permanent
           split is driven entirely by `GateDecision.hard_reject`
           (`LOAD_OUTCOME_GATE_DENIED_HARD if decision.hard_reject else
           LOAD_OUTCOME_GATE_DENIED`) — as long as this new check leaves
           `hard_reject=False`, it maps to the retryable
           `LOAD_OUTCOME_GATE_DENIED` path automatically, with no
           `loader_v2.py` change needed. Still grep `hard_reject` and
           `LOAD_OUTCOME_GATE_DENIED_HARD` across `main.py`,
           `core/daemon.py`, `core/loader_v2.py` before committing, to
           confirm no other branch treats "denied, not hard_reject" cases
           differently in a way this new denial type would trip.
        6. Before changing `GateDecision`'s shape at all, grep every
           construction site and every attribute read across `main.py`,
           `core/daemon.py`, `core/loader_v2.py`, `core/planner_loader.py`
           (same diligence C2 below also needs) — new fields with
           defaults are safe for existing positional construction,
           anything else isn't.
        7. **Arithmetic correction, resolved 2026-08-11 — `NEW-133`
           closed.** 7B (6.361GiB) + 1.5B (2.166GiB) + embed (~0.328GiB
           floor estimate) = **~8.855GiB raw sum** (exact bytes:
           6,830,557,184 + 2,325,280,320 + 352,563,303 = 9,508,400,807).
           Ish's original figure, 8.80GiB, was described as "the raw sum
           minus ~0.06GiB, for a slight safety margin" but was arithmetic-
           ally *below* the 8.855GiB raw sum by ~0.055GiB — meaning the
           exact three-model-concurrent scenario the ceiling was derived
           from would, as specified, itself have been refused by a few
           tens of MiB once all three were declared resident/pending
           simultaneously, defeating the stated intent ("make sure the
           device's own policy is shown to Codey so it never even tries
           to load a model above that number," Ish's own framing for
           this constant, quoted in full in the "Ish's decisions" block
           and `WORK_QUEUE.md`'s item 1b entry below — reads as "the full
           3-model case should be admissible," not "should be refused by
           design"). Flagged to Ish (`NEW_ISSUES.md` `NEW-133`);
           **Ish's answer (2026-08-11, direct): round up slightly instead,
           so the full 3-model case stays admissible, with any remaining
           margin-wanting applied elsewhere (the swap-budget check) rather
           than as a deduction on this ceiling.** Corrected value:
           **`MAX_CONCURRENT_MODEL_BUDGET_BYTES = 8.90GiB` (9,556,302,233
           bytes)** — the raw sum rounded up to the next 0.05GiB, giving a
           positive margin of 47,901,426 bytes (~45.7MiB) *above* the raw
           sum rather than below it. **Scoping call, not a further Ish
           round-trip**: no deduction margin belongs on this ceiling at
           all — it is a declared-cost policy sum, not a live-RAM check,
           so it is not what protects against OOM (the `MemAvailable ×
           REQUIRED_HEADROOM_FACTOR` path already does that); whatever
           conservatism a "safety margin" was meant to buy lives instead
           in C2's independently-derived, separately-calibrated
           `MAX_SWAP_ASSIST_BYTES` (768MiB, un-calibrated first default,
           see the "Ish's decisions" block and the swap-budget derivation
           below) — not duplicated here. **Caveat that must ship in the
           constant's own comment (see sub-item 1 above)**: the embed
           term in the raw sum is a floor estimate (no computable KV-cache
           term — see decision 2 below), and the ~45.7MiB margin this
           correction adds could be smaller than that floor's real
           undercount; if sub-task E's live pass or any future
           `estimate_model_load_cost()` change measures the embed model's
           real cost above the floor by more than ~45.7MiB, this constant
           needs re-derivation, not a bare "it's already fixed" assumption.
        8. Needs at least one test exercising this check with the
           cumulative sum non-zero (i.e. simulating another model already
           declared resident/pending) — with only the primary 7B
           considered in isolation today, the existing `MemAvailable`
           check already refuses the planner/embed loads first on this
           device, so this new ceiling is otherwise dormant in every
           existing test fixture and would go unexercised by accident.
           Also test `reserve_slot()`'s own PENDING+RESIDENT sum
           specifically (item 3 above) with two simulated concurrent
           slots already registered, not just `can_admit()` in isolation
           with a hand-fed parameter — the locking-correctness claim in
           item 3 is only actually exercised by a test that goes through
           `reserve_slot()` itself.
        9. **Requires CLAUDE.md rule 4's mandatory code-reviewer pass** —
           same reasoning as every other sub-task in this item that
           touches `can_admit()`'s admission math.
      - **C2: done, code-reviewer-approved on the first pass,
        uncommitted as of this writing.** `MAX_SWAP_ASSIST_BYTES = 768MiB`
        (matches this section's own pre-registered `NEW-21`-fixture
        derivation: `min(768MiB, 8.4GiB) = 768MiB`), on by default via
        `CODEY_SWAP_ASSIST_ADMISSION` (unset → on; only `"1"`/`"0"`
        accepted, anything else raises loudly); new
        `GateDecision.admitted_via_swap` field. The swap-assist branch
        lives entirely inside the existing `if required > headroom:`
        block, reached only after both `hard_reject` and C1's
        `budget_ceiling_exceeded` checks have already returned —
        structurally, not just by convention, unable to override
        either. `would_model_fit()` explicitly passes
        `enable_swap_assist=False`, matching this sub-task's own
        pre-declared routing default. Full suite: 705 passed, 1
        skipped. Two findings logged, not fixed: `NEW-135` (no
        `reserved_bytes`-style deduction on the swap-assist check —
        concurrent swap-assisted admissions could each independently
        claim the same 768MiB cap) and `NEW-136` (`admitted_via_swap`
        isn't persisted into the slot record, so a later reader can't
        tell which resident slots were swap-admitted) — both in scope
        for sub-task D's consistency pass, not this one. — wire the
        swap-aware secondary check into `can_admit()`
        (depends on A + B, and on C1 landing first — the new
        `GateDecision` field this needs is added once, alongside C1's,
        not as a second separate schema change). Only evaluated when the
        existing `required > headroom` (`MemAvailable ×
        REQUIRED_HEADROOM_FACTOR`) check would otherwise deny — the
        existing primary path stays byte-for-byte unchanged on any load
        that already passes on `MemAvailable` alone. Add a new
        `GateDecision` field (with a default, e.g.
        `admitted_via_swap: bool = False`) distinguishing "admitted on
        RAM" from "admitted on swap budget" in logs/live-verification
        output — do not silently fold this into the existing `admitted`
        bool with no way to tell which path fired. **Now unblocked** — see
        "Ish's decisions" block below for the on-by-default answer and the
        safe-swap-budget derivation (a project-architect scoping call, not
        a further Ish round-trip, per this task's own instructions).
        **New invariant, must not be relaxed**: swap-assisted admission
        (C2) may only ever override the `required > headroom` denial — it
        must never be allowed to override C1's cumulative-budget denial.
        C1's ceiling is meant to stay meaningful even with swap-assisted
        admission on by default; if C2's check ran first or could
        substitute for C1, an over-budget concurrent load could talk its
        way past 8.90GiB via swap, defeating the reason the named
        constant exists. **Requires CLAUDE.md rule 4's mandatory
        code-reviewer pass** — this changes whether a model process gets
        spawned, which is process-lifecycle-adjacent by direct
        consequence, matching this project's own established precedent
        (7.4 sub-tasks 2-5 all required it for the same reason).
      - **D: done, code-reviewer-approved on the first pass,
        uncommitted as of this writing.** D1: new
        `would_model_fit_decision()` returns the full `GateDecision`;
        `would_model_fit()` stays a thin `.admitted` bool wrapper over
        it (kept deliberately, since repointing `would_model_fit()`
        itself to return an always-truthy `GateDecision` object would
        silently break any existing `if would_model_fit(...):` caller
        — verified no live caller exists yet anyway, `core/model_tiers.py`
        hasn't wired the call). D2: `can_dispatch_task()` gained
        swap-aware dispatch per Ish's 2026-08-11 decision (extend
        swap-assist to autonomous background dispatch, not just single
        explicit loads) — reuses C2's exact
        `compute_swap_assisted_headroom_bytes()`/
        `MAX_SWAP_ASSIST_BYTES`/`CODEY_SWAP_ASSIST_ADMISSION` mechanism
        rather than a second parallel one; new
        `DispatchDecision.dispatched_via_swap` field; the swap-assist
        branch is nested strictly inside the RAM-headroom check, itself
        reached only after interactive/thermal/battery checks have
        already returned — a snapshot passing on RAM alone is
        unaffected. One deliberate divergence from `can_admit()`:
        `can_dispatch_task()` catches a malformed
        `CODEY_SWAP_ASSIST_ADMISSION`'s `ValueError` and falls back to
        disabled (logged) rather than propagating, since propagating
        would unwind through `core/daemon.py`'s main loop's `finally:`
        block (which unloads the 7B server) and kill the daemon's run
        coroutine — verified this fallback direction is the safe one
        (identical to pre-D2 behavior), so the divergence can only make
        autonomous dispatch more conservative on bad config, never more
        permissive. D3: docs-only — a note added to
        `confirm_resident_and_mark_slot()`'s docstring and `NEW-105`'s
        entry, stating (reasoned, not newly live-measured) that
        swap-assisted admission is expected to make its existing
        `MemAvailable`-delta confirmation even less likely to ever
        fire; not marked resolved. `NEW-135`/`NEW-136` deliberately
        left unfixed this round (a genuine internal inconsistency in
        this document — C2's write-up forward-referenced them as "in
        scope for D," but D's own enumerated sub-items never named
        either — judged a defensible scoping call by code-reviewer,
        not silent avoidance; `NEW-135`'s widened blast radius under D2
        documented in `can_dispatch_task()`'s docstring). Full suite:
        724 passed, 1 skipped (19 new tests, zero regressions). —
        consistency pass on what C1 and C2 each break elsewhere,
        once C1+C2 exist (blocked on both, not parallel with either —
        needs the real new `GateDecision` shape to fix against):
        1. `would_model_fit()` (line ~1057) currently returns only
           `.admitted` — this now has two independent reasons to be
           imprecise, not one. Under swap-assisted admission (C2) it
           would silently report "yes it fits" to any future caller
           (7.3's routing layer, `core/model_tiers.py`, currently under
           concurrent development — **do not touch that file this
           round**, D only needs to reason about what `would_model_fit()`
           itself returns) without distinguishing a swap-assisted "fits"
           from a comfortable-headroom "fits". Separately, under C1's
           cumulative ceiling, a "no" caused by "this device's fixed
           multi-model budget is already spent" is a materially different
           signal from a "no" caused by "not enough RAM right now" — a
           router might reasonably retry the first later (once another
           model unloads) but should treat the second as this candidate
           model being unsuitable full stop. Needs a decision: does
           swap-assisted count as "fits" for routing purposes at all, and
           does a budget-ceiling "no" need its own distinguishable return
           value, or does this need its own parameter/return shape
           entirely? (Default absent an explicit call: treat swap-assisted
           as NOT counting for `would_model_fit()`'s routing use unless a
           caller explicitly opts in — routing a smaller-model fallback
           decision onto a thrash-risk load is a different risk profile
           than the gate's own explicit, single-load admission decision.)
        2. `can_dispatch_task()`'s `DISPATCH_MIN_HEADROOM_BYTES` (1GiB,
           checked against `ram_headroom_bytes` only — no swap field
           exists on `ResourceSnapshot` before sub-task A) will still
           refuse task dispatch in exactly the memory state the new
           admission check says yes to. Left unreconciled, a live pass
           will look like a self-contradicting bug (dispatch refuses,
           then a direct `can_admit()` call for the same conditions
           admits) rather than two independently-scoped checks with
           different purposes. Needs either an explicit note in both
           functions' docstrings that these are deliberately different
           checks with different risk tolerances (dispatch = "should the
           daemon autonomously start new background work", admission =
           "can this specific model load be allowed") or a swap-aware
           update to the dispatch floor too — Ish's call, not assumed
           here.
        3. `confirm_resident_and_mark_slot()` (`core/loader_v2.py`)
           confirms a load via a `MemAvailable`-delta poll, and per
           `NEW-105` has never once actually succeeded in this project's
           live-test history (falls through to its own "mark resident
           anyway" fallback every time so far). Under swap-assisted
           admission, the model's pages go largely to swap by design, so
           `MemAvailable` will move even less than it already does today
           — `NEW-105` goes from "known accounting gap, sometimes
           doesn't fire" to "structurally guaranteed never to fire on
           this path." Not a blocking bug (the fallback path already
           exists and is already the observed behavior), but flag this
           explicitly in the live pass write-up so it isn't mistaken for
           a new regression.
      - **E — live verification**, blocked on C1+C2+D. Bar is stricter than
        7.4's own existing live-verification bar (which only measured
        whether the process spawned — `NEW-21` already proved that can
        happen while thrashing):
        1. `free -h` before anything (rule 2), record verbatim, plus
           `cat /sys/block/zram0/mm_stat` before the load.
        2. Confirm no `llama-server`/`plannd` resident (daemon-only
           harness, per 7.4's own established precedent for reaching
           `can_admit()` at all on this device).
        3. Start the load in the swap-assisted-admission configuration,
           sampling `/proc/meminfo` AND `/sys/block/zram0/mm_stat` at a
           few-second cadence *during* the load, not just before/after —
           `NEW-21`'s finding is a **rate** phenomenon (1.2→5.6Gi in
           ~10s); a before/after pair structurally cannot see it, and
           this is also how the real model-page compression ratio
           question above gets answered.
        4. Track the server's own RSS over time too — `NEW-21` saw a
           5.6GB→1.26GB squeeze; "admitted" is not the same claim as
           "working."
        5. **Send at least one real inference request and record
           wall-clock latency**, compared against a non-swapped baseline
           run — this is the actual measurement `NEW-21` never made, and
           the only one that answers whether swap-assisted admission
           produces a genuinely usable load or just a spawned-but-
           unusable one.
        6. Pre-declared abort criterion, decided BEFORE starting, not
           improvised mid-run: e.g. `SwapFree` below the
           `ro.slmk.swap_free_low_percentage` floor (~1.2GiB on this
           device) or observed RSS collapse below some fraction of the
           model's declared size → kill the tracked PID immediately
           (rule 3 — track the specific PID this session's own code
           spawned; `NEW-103` already confirmed `codeydOS` teardown
           itself uses a bare `pkill -f`, so this harness cannot lean on
           that path for cleanup).
        7. `free -h` and `mm_stat` after full teardown (rule 2), record
           verbatim.
        8. **Flag for `LIVE_TEST_QUEUE.md` instead of an agent-run live
           pass**: this pass deliberately admits a load that today's gate
           refuses, into a device state closer to its actual failure
           mode than any prior live-test round has intentionally
           targeted. The live-verifier agent session's own `claude` CLI
           process is itself ~400MiB RSS and is a candidate for the same
           `slmk` low-memory-killer this pass is testing the edge of —
           Ish should decide whether to run this one himself rather than
           delegate it, same reasoning as this project's existing
           `LIVE_TEST_QUEUE.md` deferrals.

      **E — RUN 2026-08-11, Ish's explicit direct authorization to
      delegate to an agent rather than run himself (overriding item 8
      above's default suggestion).** Real outcome, honest and complete —
      **PARTIAL PASS**: swap-assisted admission mechanism validated
      end-to-end (real gate → real spawn → real inference → real clean
      teardown), but NOT at the real production `n_ctx=32768` default —
      see `NEW-137` (logged, not silently noted). Full verbatim evidence:

      **1. Pre-load baseline** (`free -h` + `mm_stat`, before anything):
      ```
                     total        used        free      shared  buff/cache   available
      Mem:            10Gi       4.2Gi       1.0Gi        14Mi       5.6Gi       6.4Gi
      Swap:           15Gi       1.6Gi        14Gi
      mm_stat: 1702944768 432669351 451792896 0 1035563008 56138 70796 15783 51887
      ```
      `getprop ro.slmk.swap_free_low_percentage` = `10` (confirmed live,
      matches TODO's documented constant). Live `SwapTotal` on this device
      this session = 17,179,865,088 bytes (16.0GiB, not the ~12GiB figure
      TODO.md's earlier text used as an example) → live slmk floor =
      1,717,986,509 bytes (~1.6GiB), used as this run's actual abort floor
      in place of the stale ~1.2GiB example figure.

      **2. Confirmed no `llama-server`/`plannd` resident** before start —
      `ps aux | grep llama-server` / `grep plannd` showed nothing but the
      grep itself.

      **3. `n_ctx=32768` dry-run of the real gate, before any spawn**
      (no code modified — a synthetic-free, live `/proc/meminfo` call
      against the real `ModelSpec`/`estimate_model_load_cost()`):
      ```
      GateDecision(admitted=False, hard_reject=False, reason="model
      'primary' cost estimate (6514MiB) x headroom_factor (1.25) =
      8143MiB, which exceeds current headroom (6761MiB)",
      estimated_cost_bytes=6830557184, headroom_bytes=7089922048,
      device_ceiling_bytes=6973870080, budget_ceiling_exceeded=False,
      admitted_via_swap=False)
      swap_headroom = 768.0 MiB; combined_headroom ≈ 7517.8 MiB;
      required ≈ 8143 MiB → still refused even WITH swap-assist.
      ```
      **This device's live headroom this session never once put the real
      32768 case inside the swap-admittable band** — deficit
      (~1356-1382MiB across several samples) consistently exceeded
      `MAX_SWAP_ASSIST_BYTES` (768MiB) by ~600-650MiB. Per this pass's own
      instructions ("use your judgement... a specific `CODEY_N_CTX`" is an
      explicitly permitted lever), `CODEY_N_CTX=16384` was used instead,
      confirmed via the same live dry-run methodology to land inside the
      swap-admitted band immediately before spawn:
      ```
      GateDecision(admitted=True, hard_reject=False, reason="model
      'primary' cost estimate (5618MiB) x headroom_factor (1.25) =
      7023MiB exceeds RAM-only headroom (6378MiB), but is covered by RAM
      + swap-assisted headroom (7146MiB, of which 768MiB is
      swap-assisted) — admitted via swap assist", estimated_cost_bytes=
      5891033088, headroom_bytes=6687719424, device_ceiling_bytes=
      6973870080, budget_ceiling_exceeded=False, admitted_via_swap=True)
      ```
      **This is a real, honest limitation of this run, logged as
      `NEW-137`: the production `n_ctx=32768` default was not reachable
      inside the swap-assisted admission band at any live memory state
      observed this session** — the mechanism is validated at 16384, not
      32768.

      **4. Live spawn via the real `core/loader_v2.py` `ModelLoader.
      load_primary()`** (not a mock — a dedicated harness script
      instrumented the real module in-process, per this project's
      existing daemon-only-harness precedent for reaching `can_admit()`
      without full daemon mode), tracked PID captured immediately:
      ```
      Loading model: qwen2.5-coder-7b-instruct-q4_k_m.gguf
      GATE_DECISION: admitted=True, admitted_via_swap=True (as above)
      Starting llama-server...
      llama-server PID: 513
      llama-server started on port 8080
      Loaded model (qwen2.5-coder-7b-instruct-q4_k_m.gguf)
      LOAD_PRIMARY_RESULT: ok=True elapsed=11.21s
      ```
      **Load completed successfully in 11.21s wall-clock** — admitted via
      swap, spawned, and passed its own `/health` check without stalling.

      **5. `/proc/meminfo` + `/sys/block/zram0/mm_stat` sampled at 3s
      cadence during the load** (full log in this session's scratchpad;
      key trajectory, confirming `NEW-21`'s rate phenomenon reproduces
      here too):
      ```
      t+0s   MemAvailable=6418MiB SwapFree=14776MiB
      t+9s   MemAvailable=6390MiB SwapFree=14799MiB
      t+12s  MemAvailable=7116MiB SwapFree=14923MiB   (brief pre-spawn spike)
      t+15s  MemAvailable=5481MiB SwapFree=14456MiB
      t+18s  MemAvailable=4426MiB SwapFree=13620MiB
      t+21s  MemAvailable=3013MiB SwapFree=13628MiB
      t+24s  MemAvailable=2880MiB SwapFree=13830MiB   rss=7129.8MiB (pid acquired)
      t+30s  MemAvailable=2814MiB SwapFree=13909MiB   rss=7129.8MiB
      t+36s  MemAvailable=2858MiB SwapFree=13922MiB   rss=7070.6MiB
      t+42s  MemAvailable=2827MiB SwapFree=13937MiB   rss=7070.6MiB (steady state)
      ```
      `MemAvailable` fell ~6.4GiB→~2.7-2.9GiB over ~25-40s (a real,
      substantial rate phenomenon, consistent with `NEW-21`'s ~10s-scale
      finding), then plateaued — it did NOT continue collapsing toward
      zero. `SwapFree` fell from ~14.8GiB to a ~13.6-13.9GiB range
      (a real but modest ~900MiB-1.2GiB drop from the ~14.8GiB baseline),
      **never approaching the ~1.6GiB live slmk abort floor** (stayed
      >12GiB above it throughout).

      **Correction, caught on this pass's own advisor review, before
      first-draft overclaim shipped — the model-weight zram-compression
      question this item posed (`can_admit()`'s own docstring, "quantized
      model weight pages may compress far less favorably...unverified
      until sub-task E's live pass") is STILL UNANSWERED, not resolved by
      this run.** The spawn command line captured in this run's own
      driver output reads `7B model: mmap=enabled, mlock=disabled` —
      `--mmap` means the model's weight pages are file-backed (clean,
      reclaimable directly back to the GGUF file on disk), not anonymous
      memory, and file-backed pages under Linux are never written to
      swap/zram regardless of memory pressure. The zram `mm_stat` delta
      observed during this run (`orig_data_size` baseline 1,702,944,768 →
      steady-state 2,483,011,584, a ~780MB rise; ratio moved from a
      baseline ~3.94:1 to ~3.59:1, i.e. the same largely-pre-existing
      anon pool slightly diluted, not a fresh weight-page population)
      **cannot be model weight pages under this launch configuration** —
      it is some other process's/subsystem's anonymous memory being
      swapped under the pressure this load created, not evidence about
      quantized-weight compression ratio one way or the other. Separately
      corroborating this reading: `buff/cache` fell from 5.6GiB (baseline)
      to ~3.0GiB (during/after load per the `free -h` samples below) —
      a page-cache-reclaim signature (mmap'd file pages being dropped
      from cache under pressure, then re-faulted from disk as needed),
      not a swap-growth signature, and consistent with `SwapFree`'s
      comparatively modest ~900MiB-1.2GiB movement against a ~7GiB RSS
      process. **Measuring the actual model-weight-page compression
      ratio this item's docstring asks about would require a launch
      configuration where weight pages are anonymous (`--mlock` alone
      does not achieve this — it pins file-backed pages resident, it
      does not make them anonymous/swap-eligible; a genuinely non-mmap
      load path, if `llama-server` exposes one, would be needed) — not
      attempted this run, flagged for whichever future pass revisits
      this question specifically, or for accepting the question as moot
      given `--mmap` is this project's actual shipped configuration (see
      `NEW-139`).** For completeness, the incremental zram ratio on just
      the pages that entered zram during this run (delta
      orig_data_size=780,066,816 / delta compr_data_size=258,305,272 ≈
      **3.02:1**) is recorded here but is NOT load-bearing for the
      weight-compression question — per the above, those pages are not
      weight pages under `--mmap` regardless of their own ratio.

      **6. Server RSS — tracked only from ~22-24s after spawn onward, a
      real gap in this run's own coverage, corrected here.** The harness's
      `get_pid()` (and therefore the monitor's ability to read
      `/proc/<pid>/status`) is only reachable AFTER `ModelLoader.
      load_primary()` returns — the monitor log shows `rss=NAMiB` for
      every sample from t+0 through t+21s, with `pid acquired: 513` only
      logged after that. **This means the RSS-collapse abort criterion
      was structurally inoperative for the entire ~22s load window** —
      exactly the window `NEW-21`'s original 1.2→5.6GiB-in-~10s
      phenomenon occurred in. Only the `SwapFree`-floor trip was live
      during that riskiest part of the run; this is a real limitation of
      this run's safety envelope, not a clean "no collapse observed
      throughout," and is stated honestly here rather than glossed over.
      Once tracking began (first sample `VmRSS=7300956 kB`, correctly
      converted: 7,300,956 KiB × 1024 = 7,476,178,944 bytes ≈ **6.96GiB**
      — the original write-up's "7129.8MiB...~7.1-7.3GiB" language
      mis-stated this as a GiB figure without the KiB→byte conversion;
      corrected throughout this entry), RSS held in a **~6.58-6.96GiB
      range** for the rest of the load+inference window (steady-state
      low ~6733.7MiB/6.58GiB, high ~7129.8MiB/6.96GiB) — a single
      observed value at first-contact, not an observed rise, since no
      earlier sample exists to compare it against. This RSS range is
      still clearly above the gate's own declared cost estimate for this
      spec (5.6GiB total at n_ctx=16384) — see `NEW-138` for the
      corrected, honestly-scoped write-up of that gap (the file/anon
      split this session's data cannot actually support quantifying — do
      not read the peak-minus-model_bytes subtraction from an earlier
      draft of this entry as a real number; it was withdrawn, see
      `NEW-138`). No RSS value observed (from the point tracking began)
      dropped anywhere near the pre-declared 20%-of-model_bytes collapse
      floor (~892MiB).

      **7. Real inference request issued and timed** (`/health` returned
      `{"status":"ok"}` first): a single chat-completion request (43
      prompt tokens, `max_tokens=80`) returned HTTP 200 in **8.25s
      wall-clock**, generating 52 completion tokens
      (`predicted_per_second=8.27` per the server's own `timings` block;
      `prompt_per_second=22.49`). **Compared against the one other
      throughput figure in this project's live-test history**
      (`PROJECT_LOG.md` round 18, 2026-08-09: 594 tokens in 60.9s ≈ 9.75
      tok/s) — relabeled here, not called a "non-swapped baseline": that
      round used `n_ctx=2048` (this run used `16384`, an 8x difference),
      and that round's own log entry does not record a `free -h`/swap
      state alongside the figure, so whether swap was involved that time
      is genuinely unknown, not confirmed absent. **8.27 tok/s vs. 9.75
      tok/s from a differently-configured prior run is weak evidence at
      best** — reported as the only two data points this project has,
      not as a controlled swapped-vs-non-swapped comparison. What this
      run does support directly: **a real inference request against a
      swap-admitted load completed in single-digit seconds and returned
      a coherent, complete response — not a stall, not a timeout, not a
      degraded/garbled output** (the actual question `NEW-21` left
      unanswered).

      **8. Pre-declared abort criterion: never fired.** `SwapFree` stayed
      >12GiB above the live ~1.6GiB slmk floor throughout: no trip. RSS
      never collapsed below the pre-declared 20%-of-`model_bytes`
      (~892MiB) floor after crossing the 2GiB high-watermark: no trip.
      Teardown was via the normal (non-abort) path: `loader.unload()` →
      `LlamaServer.stop()`, called on the tracked `subprocess.Popen`
      object captured at spawn time (process-group SIGTERM, not
      `pkill -f` — CLAUDE.md rule 3 honored throughout).

      **9. Post-teardown baseline** (`free -h` + `mm_stat`, after full
      teardown):
      ```
                     total        used        free      shared  buff/cache   available
      Mem:            10Gi       3.0Gi       4.9Gi        10Mi       2.9Gi       7.5Gi
      Swap:           15Gi       2.2Gi        13Gi
      mm_stat: 2402484224 659497933 716546048 0 1035563008 72102 86703 23324 89264
      ```
      `ps aux | grep llama-server` after teardown showed nothing but the
      grep itself — full one-model-load-cycle-at-a-time discipline
      honored (CLAUDE.md rule 2).

      **Additional correction, also caught on advisor review before this
      write-up shipped**: at the moment of spawn, `estimated_cost_bytes`
      (5,891,033,088 = 5618MiB) was itself LESS than `headroom_bytes`
      (6,687,719,424 = 6378MiB) — the model's raw declared cost fit
      inside real RAM headroom on its own. Only `required` (cost ×
      `REQUIRED_HEADROOM_FACTOR`=1.25 = 7023MiB) exceeded headroom. **This
      means the swap-assist branch was triggered by the 25% safety
      margin, not by the model physically failing to fit in available
      RAM** — a materially different claim than "this device was out of
      real RAM for this model and swap rescued it." What real, physical
      memory pressure DID occur during the run (`MemAvailable` falling to
      ~2.7-2.9GiB, `buff/cache` falling ~2.6GiB, total system `used`
      rising to ~7.6-7.9GiB) came from the load actually running at its
      real ~7.1GiB RSS footprint once spawned, not from the admission
      decision itself being marginal.

      **Honest bottom line, per CLAUDE.md rule 5/6 — not overclaimed:**
      this run validates the swap-assisted-admission DECISION BRANCH
      end-to-end at `n_ctx=16384` — real gate call, real spawn (11.21s),
      real stable residency (no RSS collapse, `SwapFree` >12GiB above its
      kill floor throughout), and a real inference request that completed
      in 8.25s with a coherent response, not a stall or garbled output.
      **It does NOT demonstrate a load that is physically dependent on
      zram/swap to function** — the swap-assist branch fired because of
      `REQUIRED_HEADROOM_FACTOR`'s margin, not a genuine RAM shortfall for
      this spec, and this run's own launch configuration (`--mmap`)
      structurally could not exercise the quantized-model-weight
      zram-compression question this item's docstring originally posed
      (weight pages are file-backed, not swap-eligible, under `--mmap`;
      see step 5's correction above). **This does NOT confirm any of the
      above at the real production `n_ctx=32768` default either** — this
      device's live headroom never once put that specific case inside the
      swap-admittable band this session (`NEW-137`); a future live pass at
      a moment when `MemAvailable` sits within ~768MiB of `required` at
      32768 would be needed to close that gap. Also newly logged:
      `NEW-138` (revised — an unexplained ~1.56GiB anon-RSS gap after
      accounting for the mmap'd weight file, with `--embedding
      --pooling mean` flagged as an unverified candidate cause). **Sub-
      task E is NOT marked fully "done"/"passed" as a blanket claim** —
      the admission mechanism itself was exercised successfully end-to-end
      at a reduced n_ctx, but neither the production n_ctx=32768 case nor
      the original model-weight-compression question this item was meant
      to answer were actually resolved by this run; both remain open for
      a future pass.

      **Ish's decisions (2026-08-11, given directly in-session — resolves
      all three open questions below, verbatim, not paraphrased)**:
      1. **Default on or off: ON by default.** Swap-assisted admission
         (C2) is active by default, no opt-in env var required to enable
         it (an env var may still exist to *disable* it, implementer's
         call, but the shipped default is on). This reverses this entry's
         own earlier "opt-in is the more conservative starting posture"
         suggestion — Ish's explicit call overrides that suggestion.
      2. **The device-wide concurrent-model budget ceiling: 8.90GiB
         (corrected 2026-08-11, see below — Ish's original session figure
         was 8.80GiB), computed live in this session from real on-disk
         model files via
         this project's own `estimate_model_load_cost()`** (not a
         guess/estimate) — this is a *different, additional* concept from
         the per-model hard-reject ceiling
         (`compute_device_ceiling_bytes()`, ~6.49GiB via
         `DEVICE_CEILING_USABLE_FRACTION=0.60`, unchanged and untouched by
         this decision): a fixed cap on the **sum** of all
         concurrently-declared model costs, checked before any admission
         attempt is even made (see C1 above). Real numbers, all at
         `n_ctx=32768` for the two LLMs:
         - 7B (primary/coder) at n_ctx=32768: model_bytes=4.361GiB,
           kv_cache=1.750GiB, overhead=0.250GiB → **total 6.361GiB**.
         - 1.5B (planner) at n_ctx=32768: model_bytes=1.041GiB,
           kv_cache=0.875GiB, overhead=0.250GiB → **total 2.166GiB**.
         - embed model: file=0.078GiB, **no KV-cache term computable**
           (the embed model_id has no entry in `KNOWN_MODEL_ARCHS`, so
           `estimate_model_load_cost()` cannot compute its KV term —
           flagged to and accepted by Ish as an honest gap, not papered
           over) → floor estimate ~0.328GiB (file + `DEFAULT_COMPUTE_OVERHEAD_BYTES`
           only, likely an undercount since it's missing a KV term).
           **Also flagged to and accepted by Ish as a known caveat**: the
           embed server is hardcoded to always launch at `-c 2048` in
           `core/embed_server.py`, NOT `n_ctx=32768` — the "embed at
           32768" premise the raw sum below implies does not reflect what
           the code actually does today; used anyway since the embed
           model's real contribution to the total is small regardless.
         - Raw sum of all three: 6.361 + 2.166 + 0.328 ≈ **8.855GiB**
           (exact bytes: 6,830,557,184 + 2,325,280,320 + 352,563,303 =
           9,508,400,807).
         - **Ish's original session figure: 8.80GiB** — explicitly this
           raw sum minus ~0.06GiB, "for a slight safety margin."
         - **Arithmetic problem found and corrected, 2026-08-11 —
           `NEW-133` resolved.** 8.80GiB was actually *below* the 8.855GiB
           raw sum it was derived from by ~0.055GiB — meaning the exact
           three-model-concurrent case Ish computed the number from would
           itself have been refused by a few tens of MiB under a literal
           reading, defeating the stated intent ("make sure the device's
           own policy is shown to Codey so it never even tries to load a
           model above that number"). Flagged to Ish via `NEW_ISSUES.md`
           `NEW-133`; **Ish's direct answer: round up slightly instead, so
           the full 3-model case stays admissible, with any remaining
           margin applied elsewhere (the swap-budget check) rather than as
           a deduction on this ceiling.** **Corrected final ceiling:
           `MAX_CONCURRENT_MODEL_BUDGET_BYTES = 8.90GiB` (9,556,302,233
           bytes)** — the raw sum rounded up to the next 0.05GiB,
           yielding a positive margin of 47,901,426 bytes (~45.7MiB)
           *above* the raw sum. See C1 sub-item 7 above for the full
           derivation, the caveat about the embed-floor undercount that
           must ship in the constant's own comment, and the scoping call
           on where any remaining "safety margin" intent actually belongs
           (C2's independently-derived `MAX_SWAP_ASSIST_BYTES`, not this
           ceiling).
      3. **Sequencing vs. the `n_ctx=32768` production-default question:
         resolved by decision 2's own approach.** The 8.90GiB figure is
         computed at the full, real production `n_ctx=32768` for both
         LLMs, so this ceiling decision effectively settles what "max"
         means at the current shipped default — a lower `n_ctx` default
         remains a possible *future* lever (already how this item's C2
         sub-task frames it: "n_ctx should be able to be lowered depending
         on what's needed by a task and what the device has free"), not a
         prerequisite this item was blocked on.

      **Scoping call made here, not a further Ish round-trip (per this
      task's own instructions — Ish gave the ceiling number and the
      "never even tries" intent; the wiring mechanics below are
      implementer-scoping detail resolved by project-architect)**:
      decision 1 (swap-assisted admission ON by default) still leaves
      C2's `max_swap_usage_bytes` default unset — sub-task B deliberately
      took it as a parameter specifically because "the real default is
      Ish's call," and the 8.90GiB figure above answers a *different*
      question (cumulative declared cost) than "how much live `SwapFree`
      may one pending load's cost estimate eat into." Derive C2's default
      from the device-grounded `slmk` floor already documented above, not
      picked independently, but **do not use a bare `SwapFree - K *
      slmk_floor` formula on its own** — checked against this item's own
      pre-registered `NEW-21` fixture (`SwapTotal`≈12GiB, `SwapFree`≈
      10.8GiB, `slmk_floor_bytes`≈1.2GiB), `K=2.0` alone authorizes
      `10.8 - 2.4 = 8.4GiB` of swap-assist — enough to admit nearly any
      load at near-zero `MemAvailable`, directly contradicting this
      entry's own earlier framing ("capped well under the ~1.2GiB floor,
      not up against it") and leaving C1's 8.90GiB ceiling as the only
      real constraint C2 respects. Use a **capped** form instead:
      **`permitted_swap_usage_bytes = min(MAX_SWAP_ASSIST_BYTES,
      max(0, SwapFree - K * slmk_floor_bytes))`**, where
      `slmk_floor_bytes` is the `ro.slmk.swap_free_low_percentage`-derived
      floor (~1.2GiB on this device, computed live from `SwapTotal ×
      0.10`, not hardcoded), `K` is a gate term that zeroes the assist as
      `SwapFree` approaches that floor (project-architect proposes
      `K = 2.0` — stay two full `slmk` floors above the point Samsung's
      own low-memory-killer starts acting), and `MAX_SWAP_ASSIST_BYTES`
      is the actual conservative sizing term — project-architect proposes
      `768MiB` (a new, named, documented, un-calibrated first default,
      well under the ~1.2GiB `slmk` floor per the asymmetry already
      documented above: under-estimating just reproduces today's status
      quo, over-estimating risks `slmk` killing something unrelated), in
      the same spirit as `REQUIRED_HEADROOM_FACTOR`/
      `DEVICE_CEILING_USABLE_FRACTION` — sub-task E's live pass is what
      actually calibrates both constants, exactly as already planned for
      those two knobs. Verify whatever values are actually chosen against
      the `NEW-21` fixture (`min(768MiB, 8.4GiB) = 768MiB`) BEFORE writing
      them into code, per sub-task B's own "expected value in the test
      first" rule applied to this default. State this derivation and both
      constants' values explicitly in C2's own code comment, the same way
      `REQUIRED_HEADROOM_FACTOR`'s comment documents its own reasoning.

      **Explicitly out of scope for this item**: changing
      `compute_device_ceiling_bytes()`'s basis (see hard invariant
      above); any change to `n_ctx` defaults themselves (question 3
      above is a flag, not a decision made here); building any UI/CLI
      surface for the new knob beyond an env var; retuning
      `REQUIRED_HEADROOM_FACTOR`/`DEVICE_CEILING_USABLE_FRACTION`
      (unrelated existing knobs, not part of this mandate). No new
      dependency is expected (all reads are `/proc`/`/sys`, no new pip
      package or `pkg install` requirement) — if a sub-task turns out to
      need one, `install.sh` must be updated in that same task per rule
      11, not deferred.

      **F — Recalibration of `MAX_SWAP_ASSIST_BYTES`, scoped by
      project-architect 2026-08-11. Implemented and code-reviewer-approved
      (one round, after a stale-status line in this entry was caught and
      fixed — see below); uncommitted as of this writing, pending the
      required live-verification pass (single-model 32768, concurrent
      primary+planner 32768, and now also the `NEW-21`-shaped low-swap-
      headroom single-model case per `NEW-140`) before this is trusted.**
      New context
      since B/C2 were written above (which derived 768MiB from an
      un-calibrated first-pass posture): (1) Ish increased this device's
      real swap capacity — `SwapTotal` is now ~16.0GiB zram (confirmed
      `/sys/block/zram0/disksize` = 17,179,869,184 bytes), not the
      ~12GiB the 768MiB derivation assumed. (2) Sub-task E's 2026-08-11
      live pass (above) proved the swap-assisted mechanism genuinely
      works end-to-end at `n_ctx=16384` (real admission, 11.21s spawn,
      stable ~6.58-6.96GiB RSS, an 8.25s real inference request, `SwapFree`
      staying >12GiB above the ~1.6GiB live slmk floor throughout). (3)
      That same pass found the real production default, `n_ctx=32768`,
      NOT reachable — `NEW-137` — because the deficit (~1356-1382MiB that
      session) exceeded the 768MiB cap by ~600-650MiB.

      **Ish's explicit direct decision, given 2026-08-11**: raise
      `MAX_SWAP_ASSIST_BYTES` close to the formula's own live-computed
      ceiling on this device, not just far enough to patch the one known
      32768 gap (a more conservative ~2GiB alternative was offered and
      explicitly declined) — he wants to use most of the real capacity
      the swap increase provides.

      **Live arithmetic this pass (fresher than the brief handed to this
      task, which used a slightly earlier sample — re-verify at
      implementation/live-verification time, this drifts sample to
      sample):**
      ```
      /proc/meminfo:  SwapTotal=16,777,212 kB (17,179,865,088 B, ~16.00GiB)
                      SwapFree =14,562,300 kB (14,911,795,200 B, ~13.89GiB)
                      MemAvailable = 6,410,892 kB (6,564,753,408 B, ~6261MiB)
      slmk_floor_bytes = SwapTotal * 0.10 = 1,717,986,508.8 B (~1.60GiB)
      gated_swap_free  = SwapFree - 2.0 * slmk_floor_bytes
                       = 14,911,795,200 - 3,435,973,017.6
                       = 11,475,822,182.4 B  ≈ 10.69GiB  (the formula's own
                         uncapped ceiling — compute_swap_assisted_headroom_
                         bytes()'s `min(max_swap_usage_bytes, gated_swap_free)`
                         term, right operand)
      n_ctx=32768 deficit TODAY: required (6514MiB * 1.25 = 8143MiB) -
        headroom (6261MiB) = ~1882MiB — worse than sub-task E's
        1356-1382MiB sample, itself a real illustration of how much this
        drifts sample to sample (~500-900MiB swing observed across two
        reads in this task alone).
      ```

      **Recommendation: `MAX_SWAP_ASSIST_BYTES = 10 * 1024**3` =
      10,737,418,240 bytes (10.00GiB)** — for `can_admit()` only (see the
      dispatch-side split below, a new consideration this recalibration
      surfaces). Reasoning:
      - Deliberately NOT set to literally equal the live-computed ceiling
        (~10.69GiB) — kept as a genuine outer sanity ceiling (per this
        task's own framing of that option), ~0.69GiB below it, larger
        than the ~500-900MiB sample-to-sample drift observed just this
        session. A cap that exactly tracks the formula's own SwapFree
        term at all times would make the fixed constant meaningless (the
        `min()` would never select it) — 10GiB stays a real, binding
        outer bound that only stops binding if `gated_swap_free` itself
        drops below 10GiB (e.g. a future lower-swap device, or this
        device's swap becoming genuinely more pressured than observed
        today).
      - **This does make `can_admit()`'s plain-`MemAvailable`-only check
        effectively non-binding for any single admissible model whenever
        `gated_swap_free >= 10GiB` (true at every sample taken this
        session)**: `hard_reject` bounds any single model's cost at
        `compute_device_ceiling_bytes()` (~6.49GiB, `DEVICE_CEILING_
        USABLE_FRACTION=0.60` unchanged), so the largest possible
        `required` after `REQUIRED_HEADROOM_FACTOR` (1.25) is
        ~8.11GiB — below the 10GiB cap regardless of live `MemAvailable`,
        including at `MemAvailable=0`. **This is the exact outcome C2's
        own derivation comment above warned against** ("enough to admit
        nearly any load at near-zero MemAvailable, contradicting this
        feature's own framing") — stated here explicitly, not silently
        left standing: that warning was written when `SwapTotal` was
        ~12GiB and the cap was being derived independently from Ish's
        raw-capacity intent. Ish's 2026-08-11 direction supersedes it for
        `can_admit()` specifically — with 16GiB of real swap now
        available, "trust swap as real, usable capacity, bounded by the
        slmk-floor-anchored formula's own 2x-floor buffer rather than by
        an artificially small byte cap" is now the deliberate policy, not
        an oversight. The residual value the 10GiB ceiling still buys:
        protection against a transient anomalous `SwapFree` read, and a
        real (if generous) bound on future lower-swap hardware this
        module is meant to also run on (per `compute_device_ceiling_
        bytes()`'s own "intended to run on higher-RAM hardware too"
        framing, mirrored here for swap).
      - Predicate for a future live-verifier to dry-run before spawning
        anything (do not assume — check this live against real
        `/proc/meminfo` immediately before any 32768 attempt): admission
        via swap requires `headroom_bytes + min(10GiB, gated_swap_free)
        >= required_bytes`. At today's `required=8143MiB` for the primary
        7B at `n_ctx=32768`, and `gated_swap_free` (~10.69GiB) exceeding
        the 10GiB cap, swap contributes the full 10GiB (10240MiB)
        regardless of `headroom_bytes` — so 32768 SHOULD now admit at
        essentially any live `MemAvailable` this device is likely to show,
        but this is arithmetic, not yet a live observation — see the
        live-verification requirement below.

      **New split this recalibration surfaces, not previously
      considered**: `MAX_SWAP_ASSIST_BYTES` is currently a single
      constant shared by BOTH `can_admit()` (one-shot, explicit,
      human/loader-initiated model loads) and `can_dispatch_task()`
      (runs unguarded on EVERY tick of the daemon's autonomous,
      unattended dispatch loop, gating `DISPATCH_MIN_HEADROOM_BYTES` —
      1GiB, chosen specifically as an early-warning floor "well before
      `can_admit()`'s own...check would run," per that constant's own
      comment). Raising the shared constant to 10GiB would make
      `can_dispatch_task()`'s RAM-headroom check ALSO effectively
      non-binding whenever swap is healthy — combined headroom would
      reach the 1GiB dispatch floor from `ram_headroom_bytes=0` alone
      (10GiB swap contribution vastly exceeds the 1GiB floor), collapsing
      the deliberate early-warning gap between "dispatch refuses" and
      "admission refuses" that constant's own comment describes as the
      point of a *flat, lower, task-agnostic* floor. Ish's 2026-08-11
      direction was given in the context of the 32768 model-load gap
      (`NEW-137`) — nothing in it addresses the autonomous per-tick
      dispatch loop's own, separate risk profile, and collapsing that
      gap is a real behavior change to unattended background dispatch,
      not just to one-shot model admission. **Scoping call made here
      (implementation-mechanics detail, not a further Ish round-trip,
      per this task's own instructions): decouple the two.** Keep
      `can_admit()`'s default at the new `MAX_SWAP_ASSIST_BYTES` (10GiB)
      above; add a new, separate constant
      `DISPATCH_MAX_SWAP_ASSIST_BYTES = 768 * 1024 * 1024` (unchanged
      from today's value, same derivation/comment already in place for
      it) as `can_dispatch_task()`'s own default for its
      `max_swap_usage_bytes` parameter, so the dispatch loop's
      swap-assisted band stays exactly where sub-task D2 originally set
      it. If Ish later wants the dispatch floor raised too, that is a
      separate, explicit decision — not a side effect of this
      recalibration.

      **Test-fixture consequence for whoever implements this — verified
      directly against `tests/test_resource_gate.py`, not assumed from a
      comment.** `test_compute_swap_assisted_headroom_new21_fixture_
      pre_registered_case` (and every other `compute_swap_assisted_
      headroom_bytes()` boundary test in that section) passes
      `max_swap_usage_bytes` EXPLICITLY as an argument on every call — it
      does not read the module-level `MAX_SWAP_ASSIST_BYTES` default at
      all, so raising the constant does NOT change that test's expected
      value; no update needed there. What DOES need updating:
      - `test_max_swap_assist_bytes_value` (asserts
        `rg.MAX_SWAP_ASSIST_BYTES == 805_306_368` directly) — must become
        `10_737_418_240`, since this recalibration changes exactly that
        constant.
      - A new equivalent assertion should be added for
        `DISPATCH_MAX_SWAP_ASSIST_BYTES == 805_306_368` (the new,
        decoupled dispatch-side constant), mirroring the existing test's
        pattern.
      - `test_can_dispatch_task_swap_assist_capped_still_refuses_when_
        gap_too_large` (RAM headroom 2GiB below the dispatch floor, huge
        `SwapFree`, asserts refusal) and
        `test_can_dispatch_task_swap_assist_gated_near_slmk_floor_still_
        refuses` both rely on `can_dispatch_task()`'s DEFAULT
        `max_swap_usage_bytes` staying at 768MiB to pass — these are the
        concrete regression tests that would have SILENTLY FLIPPED to
        asserting the wrong thing (a 2GiB gap being covered) had the
        shared constant been raised without the admission/dispatch split
        above. Confirm both still pass unchanged once
        `DISPATCH_MAX_SWAP_ASSIST_BYTES` (768MiB) is wired in as
        `can_dispatch_task()`'s new default — this is direct evidence the
        split is necessary, not just defensive.
      - `test_swap_assist_admits_when_ram_alone_would_deny` and
        `test_can_dispatch_task_swap_assist_admits_when_ram_alone_would_
        refuse` only assert `admitted`/`allowed`/`*_via_swap` booleans and
        a `"swap" in reason.lower()` substring — no exact byte figure — so
        both remain valid at either cap value with no change needed.

      **Concurrent-admission consequence, not previously flagged in this
      item — read before live-verifying.** A 10GiB `MAX_SWAP_ASSIST_BYTES`
      does not just unlock the single-model 32768 case — worked through
      against `reserve_slot()`'s real mechanics (`core/resource_gate.py`,
      confirmed by direct read): for a SECOND concurrent load (e.g. the
      1.5B planner reserved while the 7B primary is already
      PENDING/RESIDENT), `reserved_bytes` (or the live `MemAvailable`
      drop from an already-resident primary) can push RAM-only headroom
      to ~0, but the 10GiB swap-assist cap will still cover essentially
      any second or third model's `required` on its own (the planner's
      required at 32768 is ~2.71GiB, the embed model's is smaller still —
      both far under 10GiB). **This means the swap-assisted admission
      cap, not `MAX_CONCURRENT_MODEL_BUDGET_BYTES` (8.90GiB) or RAM
      headroom, becomes the practical constraint that used to stop a
      3-model concurrent stack from being admitted at low `MemAvailable`
      — and 8.90GiB was deliberately computed to admit exactly that full
      3-model stack (see decision 2 above).** Net effect: this
      recalibration, combined with the already-existing 8.90GiB budget
      ceiling, now permits admitting up to ~8.9GiB of declared model cost
      on a ~10.83GiB `MemTotal` device at arbitrarily low live
      `MemAvailable` — the exact device state `NEW-14`/`NEW-21` already
      observed causing real swap distress (`NEW-14`: 3 concurrent models
      hit 7.5-8.5GiB swap in ~40s). This is a real, load-bearing
      consequence of Ish's "use most of the real capacity" direction, not
      an oversight — but it is a SIDE EFFECT beyond the single-model
      32768 case this item's evidence base (sub-task E) actually covers,
      and it is UNVERIFIED. `NEW-135` (updated this session) already
      documents a related, narrower gap — two racing PENDING admissions
      each independently claiming the same swap cap — whose blast radius
      also now scales from ≤768MiB to ≤10GiB. **The live-verification
      requirement below is expanded accordingly: it must cover a
      concurrent (primary + planner, sequential `reserve_slot()` calls)
      case at `n_ctx=32768`, not only the single primary-model case
      sub-task E already ran at `n_ctx=16384`.**

      **Required follow-up, explicit, not to be skipped:**
      1. **Implementer**: change `MAX_SWAP_ASSIST_BYTES` to
         10,737,418,240 (10GiB) at its `can_admit()` call site only; add
         `DISPATCH_MAX_SWAP_ASSIST_BYTES = 805,306,368` (768MiB,
         unchanged) and rewire `can_dispatch_task()`'s default parameter
         onto it; update `test_max_swap_assist_bytes_value`'s expected
         value (805,306,368 → 10,737,418,240) and add the equivalent
         assertion for the new `DISPATCH_MAX_SWAP_ASSIST_BYTES` constant,
         per the test-fixture section above (confirm the two
         `can_dispatch_task()` cap-enforcement tests named there still
         pass unchanged — they should, since dispatch's own default isn't
         moving); update every docstring/comment in
         `core/resource_gate.py` that currently cites "768MiB" as
         `MAX_SWAP_ASSIST_BYTES`'s value to instead describe the split
         (admission 10GiB / dispatch 768MiB unchanged) — do not leave
         stale comments contradicting the new constants.
      2. **Mandatory `code-reviewer` pass** (CLAUDE.md rule 4 — this
         touches admission-behavior in `core/resource_gate.py`, same
         category as every other change to this module). Reviewer should
         specifically check the concurrent-admission consequence above is
         addressed by whatever the live-verification pass (item 3) is
         actually scoped to cover, not silently left as an unverified
         side effect.
      3. **Mandatory fresh live-verification pass, TWO cases, not one:**
         (a) single primary-model load, re-running sub-task E's exact
         procedure (RAM-discipline rules 2/3, pre/post `free -h` +
         `mm_stat`, tracked-PID teardown, a real inference request timed)
         at the REAL production `n_ctx=32768` default with the new 10GiB
         cap — NOT assumed from the arithmetic above. Real evidence so
         far (sub-task E) only covers ~900MiB-1.2GiB of actual swap
         movement at `n_ctx=16384`; a 10GiB cap could in principle
         authorize a much larger swap reliance for the bigger
         `n_ctx=32768` load (larger KV cache: 1.750GiB vs. 0.875GiB),
         which has never been observed live. (b) **concurrent case, newly
         required by this recalibration's own consequence above**:
         primary + planner loaded sequentially via real `reserve_slot()`
         calls at `n_ctx=32768`, observing whether the second load is
         actually admitted via swap-assist at low real `MemAvailable` (as
         the arithmetic above predicts) and, if so, what real swap/RSS
         behavior that produces — this is the case that risks recreating
         `NEW-14`'s "3 concurrent models hit 7.5-8.5GiB swap in ~40s"
         condition, and sub-task E's single-model run does not cover it.
         Per advisor review of this scoping: also close, or explicitly
         document as still-open, the RSS-collapse abort-criterion gap
         `NEW-138` recorded (the harness's `get_pid()` — and therefore the
         abort-on-RSS-collapse check — was structurally inoperative for
         the entire ~22s load window in the 16384 run, since it can only
         resolve after `load_primary()` returns) before running this at
         32768, where the KV-cache jump means expected RSS is higher
         (~7.5-7.9GiB against `MemTotal`~10.83GiB with ~4.5GiB already in
         use per this session's own `free -h`) — either fix the
         PID-acquisition gap first, or state explicitly in that pass's
         write-up that only the `SwapFree`-floor abort trip was armed
         during the load window, same honesty standard sub-task E's own
         write-up already held itself to.

      **G — RUN 2026-08-11, sub-task F's required live-verification pass
      (Ish's explicit authorization to delegate to an agent, same override
      as sub-task E). Real outcome, honest — case (a) FULL PASS, case (b)
      b1 (read-only) FULL PASS, case (b) b2 (real concurrent spawn) ABORTED
      via pre-declared criterion (real, valuable evidence obtained — see
      below, `NEW-141`), scenario 3 (`NEW-140` shape) DEFERRED, not safely
      reachable this round — full verbatim evidence:**

      **Step 0 — `NEW-138` PID-acquisition gap: CLOSED for this harness
      only, not for production.** `core/loader_v2.py:ModelLoader.
      load_primary()` assigns `self._server = LlamaServer(model_path)`
      (line 700) BEFORE calling `self._server.start()`, and `LlamaServer.
      _spawn_locked()` sets `self.process = subprocess.Popen(...)`
      immediately at spawn time (line 385), well before the ~11-22s
      health-wait loop that `start()`/`load_primary()` block on internally.
      This harness therefore calls `loader.load_primary()` in a background
      thread and polls `loader.get_pid()` (a public getter, no source file
      touched) from the calling thread every ~0.3s starting at t=0 — this
      closes the gap from ~22s (sub-task E) down to **t+0.3s to t+3.0s**
      across this session's three runs (case a: t+3.0s; case b1: t+0.3s).
      RSS-collapse abort-criterion monitoring was therefore armed for
      essentially the entire load window this run, not just after
      `load_primary()` returned. This is a harness-side fix only —
      `core/loader_v2.py` itself is unmodified, and production callers
      (`core/daemon.py`, `main.py`) still only see `load_primary()`'s
      return value, not an early PID.

      **Case (a) — single primary-model load at real production
      `n_ctx=32768`, new 10GiB `MAX_SWAP_ASSIST_BYTES` cap.**

      Pre-load baseline (`free -h`):
      ```
                     total        used        free      shared  buff/cache   available
      Mem:            10Gi       4.8Gi       1.3Gi        36Mi       4.7Gi       5.8Gi
      Swap:           15Gi       1.2Gi        14Gi
      ```
      No `llama-server`/`plannd` resident (`ps aux | grep` showed only the
      grep). `getprop ro.slmk.swap_free_low_percentage` = `10`.

      Dry-run gate call, before any spawn, real live `/proc/meminfo`:
      ```
      MemTotal=11623116800 MemFree=1342382080 MemAvailable=6169915392
      SwapTotal=17179865088 SwapFree=15853678592
      CostEstimate(model_bytes=4683073536, kv_cache_bytes=1879048192, overhead_bytes=268435456)
      GateDecision(admitted=True, hard_reject=False, reason="model 'primary'
      cost estimate (6514MiB) x headroom_factor (1.25) = 8143MiB exceeds
      RAM-only headroom (5884MiB), but is covered by RAM + swap-assisted
      headroom (16124MiB, of which 10240MiB is swap-assisted) — admitted
      via swap assist", estimated_cost_bytes=6830557184, headroom_bytes=
      6169915392, device_ceiling_bytes=6973870080, budget_ceiling_
      exceeded=False, admitted_via_swap=True)
      ```
      **Confirms the scoping's own arithmetic prediction: 32768 is now
      admitted via swap-assist (full 10240MiB/10GiB swap contribution),
      unlike sub-task E's 32768 dry-run which was refused
      (`admitted=False`) at the old 768MiB cap.** Also newly noted:
      `estimated_cost_bytes` (6,830,557,184) sits only **~137MiB under
      `device_ceiling_bytes`** (6,973,870,080) — a marginally larger model
      file, or any future change to `DEVICE_CEILING_USABLE_FRACTION`,
      would flip 32768 to a permanent `hard_reject` regardless of swap
      capacity. Worth tracking, not itself a defect.

      Real spawn via `ModelLoader.load_primary()`, tracked PID acquired at
      t+3.0s (see Step 0 above):
      ```
      llama-server PID: 29179
      LOAD_PRIMARY_RESULT: ok=True elapsed=16.25s
      ```
      **16.25s wall-clock — the `_spawn_locked()` 60s health-wait cap did
      NOT bind at 32768** (an open question from sub-task E's scoping,
      now answered: no, not at this device's observed load times).

      `/proc/meminfo` + `mm_stat` sampled at 3s cadence during the load
      (full log: `.live_verify_scratch/case_a_samples.jsonl`, not
      committed per this pass's constraints — verbatim key trajectory
      below):
      ```
      t+0s   MemAvailable=5884MiB SwapFree=15119MiB
      t+3s   MemAvailable=6906MiB SwapFree=15213MiB  rss=3571.3MiB (pid acquired t+3.0s)
      t+6s   MemAvailable=5069MiB SwapFree=15141MiB  rss=5722.9MiB
      t+9s   MemAvailable=4734MiB SwapFree=14237MiB  rss=6731.1MiB
      t+12s  MemAvailable=4017MiB SwapFree=13749MiB  rss=7057.2MiB
      t+15s  MemAvailable=2096MiB SwapFree=13866MiB  rss=7714.4MiB
      t+18s  MemAvailable=2071MiB SwapFree=13899MiB  rss=7547.1MiB
      t+21s  MemAvailable=8015MiB SwapFree=13990MiB  rss=null (server stopped, teardown)
      ```
      `MemAvailable` fell ~5.9GiB→~2.1GiB over ~15-18s (same rate
      phenomenon `NEW-21`/sub-task E already found, now confirmed at
      32768 too), then the process settled before the inference request.
      `SwapFree` fell from ~15.1GiB to a ~13.7-14.0GiB range (~1.1-1.4GiB
      real movement, comparable in magnitude to sub-task E's 16384 run's
      ~900MiB-1.2GiB), **never approaching the 2×slmk floor
      (3.200GiB, live slmk_floor=1.600GiB)** — stayed >10GiB above it
      throughout. Peak RSS observed: **7714.4MiB (~7.53GiB)** at t+15s —
      **~1200MiB (~1.17GiB) over the gate's own declared cost estimate**
      (6514MiB) — a larger overshoot than sub-task E's 16384 run
      (~843-900MiB there), consistent with `NEW-138`'s open finding
      reproducing at a second, higher `n_ctx` (second data point, not yet
      root-caused — logged to `NEW_ISSUES.md` below, not fixed here).

      Real inference request: single chat-completion (issued after
      `/health` returned ok), **3.03s wall-clock**, coherent output:
      `'```python\ndef add_numbers(a, b): return a + b```'` — not a stall,
      not garbled.

      **Pre-declared abort criteria (never fired):** SwapFree floor
      (< 2×slmk_floor = 3.200GiB): min observed 13.7GiB, never close.
      Rate trip (SwapFree drop > 1.5GiB in one 3s sample): max single-
      interval drop observed ~950MiB (t+9→12s), below threshold.
      MemAvailable floor (< 300MiB): min observed 2071MiB, never close.
      RSS-collapse floor (20% of model_bytes = 893.2MiB, armed only after
      a 2GiB high-watermark): RSS never dropped below ~3.5GiB after
      crossing 2GiB, no trip.

      Teardown: `loader.unload()` (normal path, tracked `subprocess.Popen`
      object, no `pkill -f`). Post-teardown baseline:
      ```
                     total        used        free      shared  buff/cache   available
      Mem:            10Gi       3.6Gi       5.0Gi        14Mi       2.2Gi       7.0Gi
      Swap:           15Gi       2.1Gi        13Gi
      ```
      `ps aux | grep llama-server` after teardown: nothing but the grep.
      Gate state store (`~/.codeyOS/resource_gate_state.json`): `[]`
      (no leaked slot). **Case (a): FULL PASS**, clean cycle confirmed
      before case (b) began, per CLAUDE.md rule 2.

      **Case (b) — concurrent primary + planner at `n_ctx=32768`.**
      A structural finding first, not previously stated explicitly in this
      item's own scoping: **`core/planner_loader.py`'s `ensure_planner()`
      (the production entry point `core/plannd.py:get_plan()` actually
      calls) evicts the primary model FIRST, via
      `_evict_primary_and_confirm_free()`, before ever reserving a slot for
      the planner** — Ish's sequential-swap decision ("primary and planner
      must never be resident at the same time," `core/planner_loader.py`'s
      own module docstring) is enforced at that orchestration layer, not
      at `reserve_slot()`/`can_admit()` itself. **This means the
      concurrent-admission consequence this sub-task's own scoping
      flagged is UNREACHABLE through the shipped production call path** —
      a live-verifier following `ensure_planner()` alone would never
      observe it, because the primary is gone before the planner's
      `reserve_slot()` call happens. To actually exercise the gate's
      concurrent-admission arithmetic, this run called
      `PlannerLoader.load()` directly (the lower-level method
      `ensure_planner()` itself calls internally, AFTER its own eviction
      dance) — a real, existing production code path, just invoked
      without the swap-guard orchestration wrapper around it, per this
      task's own "real `reserve_slot()`/`load()` call sequence" language.
      **Logged to `NEW_ISSUES.md` as a new finding, not fixed here** (see
      below) — a future reader must not conclude concurrent residency is
      a supported/tested state; it is explicitly NOT reachable through any
      shipped orchestration entry point.

      **b1 (read-only, zero additional spawn risk): `can_admit()` dry-run
      for the planner spec while the primary is genuinely resident, at
      real live low `MemAvailable`.** Fresh cycle: primary loaded again
      (PID acquired at **t+0.3s**, `LOAD_PRIMARY_RESULT: ok=True
      elapsed=14.79s`). Once resident:
      ```
      primary_resident sample: MemAvailable=2001MiB SwapFree=14226MiB primary_rss=6840.8MiB
      GATE_STATE_STORE: [{"slot_id": "ba4a157a...", "model_id": "primary",
        "cost_bytes": 6830557184, "pid": 32428, "status": "resident", ...}]
      ```
      (Confirmed by direct read of `core/resource_gate.py:_sum_committed_
      bytes()` that summing every slot's `cost_bytes` regardless of
      PENDING/RESIDENT status, as done here, is exactly what
      `reserve_slot()` itself computes internally as
      `concurrent_committed_bytes` — this dry-run's call shape is a true
      equivalent of the real `reserve_slot()` arithmetic, not an
      approximation.)
      ```
      B1_PLANNER_COST: CostEstimate(model_bytes=1117320768,
        kv_cache_bytes=939524096, overhead_bytes=268435456)
      B1_DECISION: GateDecision(admitted=True, hard_reject=False,
        reason="model 'planner' cost estimate (2218MiB) x headroom_factor
        (1.25) = 2772MiB exceeds RAM-only headroom (2001MiB), but is
        covered by RAM + swap-assisted headroom (12241MiB, of which
        10240MiB is swap-assisted) — admitted via swap assist",
        estimated_cost_bytes=2325280320, headroom_bytes=2098470912,
        device_ceiling_bytes=6973870080, budget_ceiling_exceeded=False,
        admitted_via_swap=True)
      ```
      **This is real, live confirmation of the scoping's own prediction**
      ("the 10GiB swap-assist cap will still cover essentially any second
      or third model's `required` on its own"): at real `MemAvailable`=
      2001MiB with the primary genuinely resident (not a synthetic
      fixture), the planner IS admitted via swap-assist, with the full
      10240MiB swap contribution binding (not the smaller `gated_swap_free`
      operand — `SwapFree`=14.2GiB here keeps `gated_swap_free` well above
      the 10GiB cap). Teardown (`planner.unload()`+`loader.unload()`,
      both no-ops beyond the resident primary since the planner was never
      actually spawned in b1) confirmed clean: post-teardown `free -h`
      showed `available` 6.7Gi, `ps aux | grep llama-server` empty, gate
      state store back to `[]`.

      **b2 (real concurrent spawn — the actual risk this sub-task exists
      to probe): ABORTED via pre-declared abort criterion, clean tracked-PID
      teardown. Real, valuable evidence obtained — not a full pass, an
      honest early abort per this task's own explicit instruction that this
      is a fully acceptable outcome.**

      Before this run, per advisor review, the harness was strengthened
      beyond case (a)'s abort criteria (SwapFree floor <2×slmk_floor,
      MemAvailable <300MiB — both proved too static to fire during
      sub-task E's own run): a **rate-trip criterion** (SwapFree drop
      >1.5GiB within one 3s sample interval) was added, plus
      `RssAnon`/`RssFile`/`RssShmem` sampling (not just `VmRSS`, per
      `NEW-138`'s own "fix direction" ask) and a post-load 75s steady-state
      monitoring window (`NEW-14`'s phenomenon was observed AFTER load
      completed, not during — case (a)'s harness only sampled through the
      load itself).

      Fresh cycle, clean baseline confirmed (`free -h`: available 5.9Gi,
      swap 2.0Gi/15Gi used; no `llama-server` resident; gate state store
      `[]`). Primary loaded first (PID acquired **t+0.3s**,
      `LOAD_PRIMARY_RESULT: ok=True elapsed=12.72s`). Sample immediately
      after, primary resident, before planner load starts:
      ```
      t+12.7s MemAvailable=1819MiB SwapFree=13712MiB
        primary_rss: VmRSS=6984.6MiB RssAnon=6263.3MiB RssFile=720.9MiB RssShmem=0.4MiB
      ```
      `PlannerLoader.load()` called DIRECTLY (not `ensure_planner()`, which
      would have evicted the primary first — see the structural finding
      above), while the primary stayed genuinely resident — planner PID
      acquired **t+3.0s** into the planner's own load call:
      ```
      t+15.7s MemAvailable=1251MiB SwapFree=13525MiB
        primary_rss: VmRSS=5941.4MiB RssAnon=5940.1MiB RssFile=1.0MiB RssShmem=0.4MiB
        planner_rss: VmRSS=1417.8MiB RssAnon=923.9MiB RssFile=493.4MiB RssShmem=0.4MiB
      t+18.7s MemAvailable=1366MiB SwapFree=11319MiB
        primary_rss: VmRSS=3072.9MiB RssAnon=3071.5MiB RssFile=0.9MiB RssShmem=0.4MiB
        planner_rss: VmRSS=2217.2MiB RssAnon=1933.0MiB RssFile=283.8MiB RssShmem=0.4MiB
      [monitor] ABORT CRITERION FIRED (during planner load): SwapFree rate-drop 2209MiB/3s
      ```
      **The rate-trip criterion fired — the only one of the three
      pre-declared criteria that did, and it would NOT have fired under
      case (a)'s single-model run.** In the same ~6s window (t+12.7→18.7),
      the primary's own `RssAnon` collapsed from 6263.3MiB to 3071.5MiB
      (a **~3192MiB anonymous-page swap-out**, not RSS being freed —
      `RssFile` dropped too, from 720.9MiB to 0.9MiB, a separate
      mmap-reclaim signal), while zram `mm_stat`'s `orig_data_size` jumped
      from 2,985,271,296 to 5,209,858,048 bytes (**+2.13GB** in the same 3s
      sample interval) — the swap-out volume and the `SwapFree` drop are
      mutually consistent, not an artifact of one reading alone. **This is
      a real, live reproduction of `NEW-14`'s rate phenomenon
      ("3 concurrent models hit 7.5-8.5GiB swap in ~40s"), now triggered
      by only 2 concurrent models (not 3) at `n_ctx=32768`, within ~6
      seconds of the second load starting — faster and with fewer
      concurrent models than `NEW-14`'s original observation.** New
      finding, logged as `NEW-141` below.

      Per the pre-declared abort protocol: the in-flight `planner.load()`
      background thread was joined (bounded, 15s) BEFORE any kill, so the
      call could finish its own internal bookkeeping (gate `mark_resident`)
      rather than being torn down mid-write — it completed
      (`✓ Loaded planner model`, with the gate's own `confirm_resident_
      and_mark_slot()` logging its own already-known-flaky `MemAvailable`-
      drop-confirmation timeout, "marking resident anyway" — `NEW-105`,
      unrelated, expected). Then both tracked PIDs (planner 13466, primary
      13024) were torn down via `os.killpg(SIGTERM)` then, after a 3s
      grace period, `os.killpg(SIGKILL)` — no `pkill -f`, CLAUDE.md rule 3
      honored throughout.

      Post-teardown confirmation:
      ```
                     total        used        free      shared  buff/cache   available
      Mem:            10Gi       4.1Gi       3.8Gi        26Mi       2.9Gi       6.3Gi
      Swap:           15Gi       1.7Gi        14Gi
      ```
      `ps aux | grep llama-server` after teardown: nothing but the grep.
      Gate state store: `[]` (no leaked slot from either the primary or
      the planner). **Clean state confirmed.**

      **Honest bottom line for b2, per CLAUDE.md rule 5/6**: this run did
      NOT reach the planned 75s post-load steady-state monitoring window —
      the rate-trip criterion fired during the planner's own load, before
      "both resident, settled" was ever reached, so that window's specific
      question (does swap pressure keep climbing or plateau once both
      models are steady, as case (a)'s single-model run plateaued around
      t+15-18s) remains genuinely unanswered. What WAS directly observed,
      live, not inferred: **a real, fast (~6s), substantial (~3.2GiB
      anon-page) swap-out event triggered by the second concurrent
      `n_ctx=32768` model load, closely matching `NEW-14`'s documented
      distress shape** — the pre-declared abort criterion correctly
      identified this as the moment to stop, and stopping there (rather
      than pushing further to observe a steady state that this same data
      suggests may not have been reached safely) is treated here as the
      correct, conservative call per this task's own explicit instruction
      that an early abort is a fully acceptable outcome, not a failure to
      "complete" the scenario. No repeat attempt was made — the same
      device-state shape would be trivially reproducible and there is
      no reason to believe a second attempt would end differently or
      more safely.

      **Scenario 3 — `NEW-140`'s specific low-swap-headroom device shape
      (`SwapTotal`≈8GiB, `SwapFree`≈6.8GiB): DEFERRED, not safely reachable
      this round, consistent with the pre-analysis before any spawn this
      session.** An opportunistic read-only dry-run was captured
      immediately after b2's teardown (the highest residual-pressure
      moment of this session, free to capture, no additional spawn risk):
      ```
      SCENARIO3_RESIDUAL_MEMINFO: MemTotal=11623116800 MemFree=4365389824
        MemAvailable=6924828672 SwapTotal=17179865088 SwapFree=15157424128
      SCENARIO3_RESIDUAL_DECISION: GateDecision(admitted=True,
        hard_reject=False, reason="...admitted via swap assist",
        estimated_cost_bytes=6830557184, headroom_bytes=6924828672,
        device_ceiling_bytes=6973870080, admitted_via_swap=True)
      ```
      By the time teardown completed (a few seconds after the abort fired)
      the device had already substantially recovered — `SwapFree` back to
      ~14.1GiB, `MemAvailable` back to ~6.6GiB — nowhere near `NEW-140`'s
      `SwapFree`≈6.8GiB fixture shape. This confirms the pre-registered
      reasoning from this pass's own scoping: on a real ~16GiB-zram-swap
      device with `SwapFree` routinely sitting at ~13-15GiB at rest,
      reaching `SwapFree`≈6.8GiB means the device actually consuming
      ~7-9GiB of real swap first — which is itself the exact distress
      condition this pass is required NOT to manufacture via an untested
      mechanism. b2's own abort (a ~3.2GiB anon swap-out in ~6s) came
      closer to that shape than case (a) alone did, but the harness
      correctly stopped before reaching it, and no further attempt was
      made to push closer. **This scenario remains open for a future pass**
      — the only safe way to observe it appears to be either a genuinely
      lower-swap test device, or accepting that reaching it live on this
      device means deliberately reproducing `NEW-14`/`NEW-21`-class
      distress, which this task's own instructions explicitly forbid
      manufacturing.

- [ ] 7.4b (WQ Track 3 item 1c, new item spun off 7.4a's own sub-task F
      finding — `NEW-141` — plus a fresh, direct 2026-08-11 Ish decision
      on model lifecycle policy, not a continuation of the swap-cap
      arithmetic itself). **Scoping pass complete, 2026-08-11
      (project-architect), no code changed.**

      **Ish confirmed both candidate numbers, 2026-08-11: planner ceiling
      = 8192, coder background-dispatch ceiling = 16384.** Both ready for
      implementer now.

      **Ish's decision, verbatim intent, three parts:**
      1. Embed model: always resident from Codey startup to Codey
         shutdown, never spun up on-demand. Context stays at its natural
         max (already true — no change needed, see below).
      2. Planner (1.5B): capped at a small, fixed context ceiling — never
         the full 32768 it shares with the coder today.
      3. Coder (7B): context adjusts dynamically by task, EXCEPT when
         the user is actively using it interactively outside daemon mode
         — then it runs at full max context.

      **Embed model's "natural max" fact (already verified, do not
      re-derive):** `nomic-embed-text-v1.5.Q4_K_M.gguf`'s real on-disk
      GGUF metadata (`nomic-bert.context_length`) is 2048, exactly
      matching `core/embed_server.py`'s current hardcoded `-c 2048`
      launch flag. Decision 1 needs zero context-size change — it is
      entirely a lifecycle change (always-on vs. on-demand).

      **Sub-task A — embed-server lifecycle (always resident).**
      `core/embed_server.py`'s `start()`/`stop()` already exist and are
      idempotent/PID-tracked (no rework of the kill logic needed). The
      actual gap: today it starts EAGERLY only from `core/daemon.py`'s
      `_main_loop` (line ~922) at daemon startup, and LAZILY from
      `core/inference.py:_start_server()` (called on every `infer()`, in
      whichever process is doing interactive/CLI inference) — the lazy
      path is the "spun up on-demand" behavior Ish's decision means to
      end. Under the real product entry point (`codey-start`, which
      always starts the daemon first — see `codey-start:47-53`), embed
      already starts eagerly with the daemon; the lazy path only matters
      for interactive-only invocations that bypass daemon startup, or as
      a second, redundant "ensure" call inside every `infer()` even when
      the daemon already started it.

      **Blocking prerequisite found this pass, `NEW-144` (Confirmed, see
      `NEW_ISSUES.md`):** `EmbedServer.start()`'s only "already running"
      fast path checks `self.process` (this Python object's OWN spawned
      subprocess handle) — it has no health-check-only path for "a
      DIFFERENT process already has a healthy embed server running."
      Falling through, `start()` sees the port bound and unconditionally
      treats it as stale, killing and respawning it. Concretely: the
      TUI process's own first `infer()` call under `codey-start` kills
      and restarts the daemon's already-healthy embed server, every
      session. **Sub-task A must fix this before "always resident,
      never spun down except at Codey shutdown" can be true at all** —
      the natural fix is a single source of truth (only the process that
      is meant to own the embed lifecycle actually starts/stops it;
      every other caller — `core/inference.py:_start_server()`
      specifically — health-checks only and never calls `start()`'s
      kill-and-replace path against an occupant it can positively
      confirm is healthy).

      Stop side: `core/daemon.py`'s `_main_loop`'s `finally:` block
      already calls `stop_embed_server()` via the tracked Python
      singleton (line ~1067-1071) on graceful daemon shutdown — this is
      the correct, already-existing "stop only when Codey shuts down"
      mechanism and should be the one this sub-task relies on. Do NOT
      route through `codey-stop`'s bare `pkill -9 -f "llama-server"`
      sweep (`codey-stop:36`) as part of this sub-task's design — that
      line is a pre-existing, already-logged CLAUDE.md rule 3 violation
      (`NEW-85`, Confirmed, not this sub-task's to fix) and must not be
      treated as embed's real stop mechanism; the graceful daemon
      shutdown path already does this correctly today.

      **Mandatory `code-reviewer` pass** (CLAUDE.md rule 4 — directly
      touches process start/kill logic in `core/embed_server.py` and
      the daemon startup sequence).

      **Status, 2026-08-13 (`NEW-151`): implementation landed
      (`EmbedServer.is_healthy()` in `core/embed_server.py`,
      health-check-before-`start()` in `core/inference.py:_start_server()`)
      but NOT via this sub-task's own review path — it rode into commit
      `5687dcf`, a config-only NEW-102/bug_002 fix commit, without the
      mandatory `code-reviewer` pass above ever happening. Do not treat
      sub-task A as done. Still needs: a real `code-reviewer` pass on
      this diff.**

      **Sub-task B — planner context ceiling.**
      Derived, not invented, from the real prompt this project actually
      sends: `core/plannd.py`'s `PLANNER_PROMPT` (the system prompt sent
      on every planner call, local AND remote backends) measures at
      9,786 characters / **~2,446 tokens** (measured this pass, char/4
      approximation — verbatim: `chars: 9786, approx tokens (chars/4):
      2446`). `get_plan()`'s local-backend call
      (`core/plannd.py:394-403`) is single-turn — system prompt + the
      raw user message only, no conversation history, no project
      context (that only reaches the SEPARATE 7B-fallback path,
      `core.orchestrator.plan_tasks()`, not the 1.5B). Output is capped
      at `PLANNER_MAX_TOKENS = 1024` (`utils/config.py:431`). Fixed
      floor: 2,446 + 1,024 = **3,470 tokens**, before the user message
      or chat-template overhead.

      **Candidate ceiling: 8192.** At 8192, ~4,700 tokens remain for the
      user message plus template overhead — generous headroom over any
      realistic single coding request. A tighter 4096 would leave only
      ~626 tokens for the user message and is too tight (a long
      multi-clause request could overflow it). **What Ish is actually
      confirming is not the number in isolation but its consequence**:
      today, at 32768, an arbitrarily long user message fits; at 8192,
      anything past ~4,700 tokens of user message would overflow and
      either truncate or fail depending on how the local server handles
      an over-length request (not itself tested this pass). **Needs
      Ish's explicit confirmation before implementer starts** — same
      posture as `MAX_CONCURRENT_MODEL_BUDGET_BYTES`/
      `MAX_SWAP_ASSIST_BYTES`'s derive-then-confirm precedent.

      Mechanically: today the planner shares `MODEL_CONFIG["n_ctx"]`
      (the same global 32768 constant as the coder) via
      `core/planner_loader.py:88` (`n_ctx=MODEL_CONFIG.get("n_ctx",
      4096)`) — this sub-task adds a planner-specific constant instead
      of reading the shared global.

      **Mandatory `code-reviewer` pass — NOT for a process-lifecycle
      reason (this sub-task changes a launch flag value, not kill/PID
      logic), but because changing the planner's `n_ctx` changes
      `estimate_model_load_cost()`'s KV-cache term for the planner,
      which changes `can_admit()`'s real admission arithmetic** — the
      same "admission-behavior change in `core/resource_gate.py`-adjacent
      code" category 7.4a sub-task F's own scoping cited for its own
      mandatory review. Do not substitute rule 4's PID/lifecycle
      language for this — cite the admission-behavior category instead.

      **Sub-task C — coder interactive-vs-daemon context branching.**
      **Important scoping correction, found this pass, do not build
      against the original framing:** `core/model_tiers.py`'s
      `classify_tier()` CANNOT drive this. For `("coding", "coder",
      *)`, `_CODER_TIERS` has exactly one local tier (`"large"`, per
      `NEW-84` — no local `"small"` tier exists), so
      `classify_tier()`'s own documented fallback
      (`model_tiers.py:208-209`) returns `"large"` unconditionally
      whenever there's no `"small"` key. Separately, `NEW-126` already
      found the underlying `_score_message()` signal set matches almost
      every realistic coding prompt as `"large"` anyway. Reusing the
      classifier as originally imagined would therefore give every
      coder task full context and change nothing.

      **What IS implementable now**: a two-value branch, not a
      per-task dynamic scale — `n_ctx = 32768` when
      `core.resource_gate.is_interactive_session_active()` is True (the
      exact signal 7.4 sub-task C already built and wired into daemon
      dispatch — reuse it, do not build a second detection mechanism),
      else a smaller fixed ceiling for daemon-dispatched background
      coder tasks. **Candidate background ceiling: 16384** — the exact
      value 7.4a sub-task E's own live-verification pass already proved
      admits cleanly with real, live, moderate (~900MiB-1.2GiB) swap
      movement, as a known-safe intermediate point between full 32768
      and a value nobody has tested live. **Needs Ish's explicit
      confirmation, same as sub-task B's number.** True per-task
      dynamic `n_ctx` (matching the fuller "adjusts dynamically based on
      the task" framing) is `CODEY_OS_MASTER_VISION.md` Section 11's
      11.9 item, already named in this file's Phase 2 (11.9-11.11,
      "adaptive `n_ctx` ... computed per load attempt instead of a fixed
      global constant") and explicitly parked pending a concrete
      domain agent needing it — this sub-task realizes the narrow
      interactive-vs-background slice of 11.9 now, while 11.9's fuller
      per-task scale stays parked, not silently expanded.

      Mechanically: wire the branch at `core/loader_v2.py`'s
      `load_primary()` (currently reads `MODEL_CONFIG.get("n_ctx",
      4096)` unconditionally, line 660) and its call sites in
      `main.py` (interactive) and `core/daemon.py` (background
      dispatch) — the two already-distinct call contexts sub-task C of
      7.4 (interactive-session signal) exists specifically to
      distinguish.

      **Mandatory `code-reviewer` pass AND `live-verifier` pass**
      (CLAUDE.md rule 4 — this is the first sub-task in this item that
      actually changes real model-load behavior/spawn args, same
      category as 7.4's sub-task C "first sub-task where daemon
      dispatch behavior actually changes").

      **NEW-145 fix — scoped 2026-08-11 (project-architect), not yet
      implemented. Real regression, found once sub-task C's branch went
      live under the actual `codey-start` entry point** (see
      `NEW_ISSUES.md`'s NEW-145 for the full mechanism): the daemon's own
      eager coder preload (`_preload_primary_model()`, called from
      `_main_loop()` at startup, line ~918) always runs before any TUI
      session could possibly have registered as interactive, so it
      always evaluates `is_interactive_session_active()` False and spawns
      the coder at the new 16384 background ceiling — then the TUI's own
      later `infer()` call reuses that already-running 16384 server via
      `LlamaServer.start()`'s port-in-use reuse branch instead of getting
      its own 32768 server. Net effect: ordinary interactive use under
      `codey-start` silently SHRANK from 32768 (unconditional, pre-this-
      round) to 16384 — the opposite of decision 3.

      **Ish's fix decision, given directly in-session, 2026-08-11:**
      remove the daemon's eager preload of the coder (primary/7B) model
      entirely. Only the embed model (sub-task A) stays always-resident/
      eagerly preloaded. The coder loads lazily on first real request —
      interactive or background — so `is_interactive_session_active()`
      is evaluated at actual spawn time, not guessed wrong at daemon
      startup. Accepted tradeoff, explicit: the first real coder request
      after daemon start pays full model-load latency (~11-16s, this
      session's own live-test evidence) instead of finding an
      already-warm model — not something to design around.

      **Concrete change, two call sites (both needed — verified by
      direct read this pass, not just the one Ish named):**
      1. **`core/daemon.py`'s `_main_loop()`**: delete the
         `self._preload_primary_model()` call (line ~918) and its
         `if not _is_remote():` guard around it; delete the now-dead
         `_preload_primary_model()` method itself (lines ~824-895) —
         nothing else calls it, so a retained-but-uncalled method is not
         "removed entirely." The `else:` branch's remote-backend log
         line (line ~920, "Backend: {backend} — skipping local 7B and
         1.5B server startup") needs a new home outside the now-deleted
         `if`; a single unconditional startup log line is the natural
         replacement, e.g. logging either "coder (7B) will load lazily
         on first request — no startup preload" (local backend) or the
         existing remote-skip message (remote backend) — this keeps
         daemon startup behavior observable in the log, matching how
         every other deliberate behavior change in this project has been
         made visible (not a silent behavior change).
      2. **`core/daemon.py`'s `_watchdog_check_model()`** (line ~752,
         30s tick) — found during this scoping pass, NOT something
         `_preload_primary_model()`'s removal alone fixes: this watchdog
         also calls `loader.ensure_model()` UNCONDITIONALLY every tick,
         with no distinction between "was loaded and died — restart it"
         (the watchdog's actual original purpose) and "never loaded,
         nobody has asked yet — leave it alone." Left as-is, this
         watchdog reproduces NEW-145's exact failure shape on an EVEN
         MORE common path than the one originally filed: `codey-start`
         skips daemon startup entirely when a daemon is already running
         (`codey-start:48`'s `is_daemon_running` check) — the normal
         steady state for this project's actual daily use is a
         long-lived daemon with the TUI attaching and detaching
         repeatedly. Any time the daemon sits ≥30s with no TUI
         registered, the watchdog's next tick will call `ensure_model()`
         with `is_interactive_session_active()` False, spawn the coder
         at 16384, and a TUI attaching afterward reuses that same
         under-provisioned server — same reuse-branch mechanism NEW-145
         itself already names.
         **Fix**: add a new signal the watchdog can use to distinguish
         the two cases, since `ensure_model()`'s own semantics are pure
         "ensure loaded" and correctly must stay that way for its real-
         request callers (main.py's interactive path, daemon background
         dispatch) — the gate belongs at the watchdog's daemon-side call
         site, not inside `ensure_model()` itself. Concretely: add
         `ModelLoader._ever_loaded: bool = False` in `__init__`
         (`core/loader_v2.py` line ~622), set it True alongside the
         existing `self._loaded_at = time.time()` assignment on a
         successful load (line ~779 — deliberately never reset by
         `unload()`, same as `_loaded_at` already isn't, so it correctly
         answers "has this loaded at least once in this process's
         lifetime," not "is it loaded right now"), and expose it via a
         new `was_ever_loaded() -> bool` accessor (matching the existing
         `is_loaded()`/`get_loaded_model()` accessor pattern — do not
         have the watchdog reach into `loader._ever_loaded` directly).
         `_watchdog_check_model()` then gates: if the server isn't
         currently running AND `not loader.was_ever_loaded()`, return
         early without calling `ensure_model()` at all (nothing to
         restart — no real request has happened yet, so there is nothing
         "died"). If it was ever loaded before and isn't running now,
         proceed to `ensure_model()` as today.

         **Deliberate consequence, must be stated for code-reviewer, not
         left for them to find (same "self-race" category rule 4 exists
         for):** `_ever_loaded` is per-process state on the DAEMON's own
         `get_loader()` singleton. Under `codey-start`, the coder is
         normally spawned by the TUI process, not the daemon — the
         daemon's own `load_primary()` reaches line ~779 via
         `LlamaServer.start()`'s port-in-use ADOPTION branch in that
         case (reusing the TUI-spawned server, not spawning its own),
         not a fresh spawn. Line ~779 is already the convergence point
         for both the genuine-spawn and the adoption branch (both set
         `self._loaded = True` there before returning `True`), so
         placing `self._ever_loaded = True` at that same line
         automatically covers adoption too — no separate branch-specific
         code needed, but this must be called out explicitly for the
         reviewer, because it changes what "ever loaded" actually means:
         "this loader spawned OR adopted a running server at least
         once," not "this loader spawned it." That distinction matters
         for watchdog crash-restart coverage specifically: (a) unchanged
         for coder loads the daemon's own loader performed
         (background-dispatched loads) — restarts on crash exactly as
         today; (b) unchanged for a TUI-spawned coder the daemon's loader
         has adopted at least once (the normal `codey-start` case) —
         also restarts on crash, same as today, because adoption already
         sets `_ever_loaded` via the same line; (c) NEW: a coder that has
         never been spawned NOR adopted by the daemon's own loader is
         left alone by the watchdog rather than eagerly loaded — this is
         the actual fix. Document this "spawned OR adopted" meaning on
         the `was_ever_loaded()` accessor's own docstring, not just in
         this write-up — a future reader checking crash-restart coverage
         needs it there.
      **Both call sites must land in the same round** — fixing only (1)
      narrows NEW-145's exposure window (down to ~30s after a fresh
      `codey-start`) but does not close it on the more common
      already-running-daemon path; NEW-145 stays open until both are
      done (CLAUDE.md rule 6 — do not let a partial fix be recorded as a
      full one).

      **Tests affected:** `tests/test_daemon_model_watchdog.py:250-362`
      (the six `test_preload_*` tests) are deleted along with
      `_preload_primary_model()` — no coverage is lost, the watchdog's
      own tests above line 248 already exercise the same
      `LOAD_OUTCOME_*` message branches against the same `FakeLoader`.
      That file's module docstring (lines 1-41) currently names
      `_preload_primary_model()` as one of its two subjects and needs
      updating to describe only the watchdog. A new test is needed for
      the watchdog's new never-loaded-and-unrequested-yet case (asserts
      `ensure_model()` is NOT called when `was_ever_loaded()` is False
      and nothing is running).

      **Residual gap, explicitly NOT this fix's job (logged separately,
      `NEW-149`, Confirmed):** even with both call sites fixed, whichever
      caller spawns the coder server first still wins the context size
      for that server's entire life (`LlamaServer.start()`'s port-in-use
      reuse branch, `core/loader_v2.py:211-230`) — a background
      daemon-dispatched task that loads first at 16384 still leaves a
      later-attaching interactive TUI stuck at 16384, with no respawn.
      This fix closes NEW-145's specific "daemon always loads before any
      TUI can register" race; it does not make decision 3 unconditionally
      true in every ordering. Do not read "NEW-145 resolved" as "decision
      3 fully realized."

      **Checked this pass, no other eager coder-load path found:**
      `gui/` and `ccos/` grepped for `load_primary`/`ensure_model`/
      `get_loader`/`infer(` — no startup or connect-time eager coder-load
      call site in either; `ccos/plugins/system/daemon_control/
      daemon_control.py`'s one hit is a doc comment referencing
      `main.py`'s CLI-side `_load_primary_with_gate_recovery()`, not a
      new eager-load site.

      **Mandatory `code-reviewer` pass** (CLAUDE.md rule 4 — real
      daemon-startup AND daemon-watchdog process-lifecycle behavior
      change, matching this project's own established precedent for
      anything touching daemon startup/model-load lifecycle).

      **Mandatory `live-verifier` pass — unit tests cannot show this fix
      worked, NEW-145 was only ever found under the real entry point.**
      Concrete pass/fail evidence to capture (verbatim, per CLAUDE.md
      rule 5, not paraphrased): run `free -h` first (rule 2). Start a
      fresh daemon via `codey-start`, confirm the new startup log line
      ("coder will load lazily on first request...") appears and NO
      llama-server (port 8080) process exists yet (`ps aux | grep
      llama-server` showing nothing but the grep). Then send the TUI's
      first real prompt and confirm the resulting llama-server's actual
      command line shows `-c 32768` (verbatim `ps`/`cat /proc/<pid>/
      cmdline` output). Separately, confirm the watchdog gate: leave the
      daemon running with the TUI detached for ≥30s (past one tick) with
      no prompt sent, and confirm no coder server spawns during that
      window. Use the daemon-only/lighter harness posture this project's
      own NEW-14 finding established, not a full 3-model concurrent
      session.

      **Status, 2026-08-13 (`NEW-151`): implementation landed
      (`core/daemon.py`'s `_preload_primary_model()` removed,
      `_watchdog_check_model()`'s `was_ever_loaded()` gate added,
      matching `core/loader_v2.py`/test changes) but NOT via this
      sub-task's own review path — it rode into commit `5687dcf`, a
      config-only NEW-102/bug_002 fix commit, without either the
      mandatory `code-reviewer` pass or the mandatory `live-verifier`
      pass above ever happening. Do not treat sub-task C as done, and do
      not read the code's mere presence in `main` as evidence it works
      under the real entry point — both mandatory passes above are still
      outstanding.**

      **Status update, 2026-08-13 (`NEW-152`): the retroactive
      `code-reviewer` pass prompted by `NEW-151` found a Critical gap in
      the `was_ever_loaded()` gate itself** (see `NEW_ISSUES.md`'s
      `NEW-152` for the full mechanism — sticky-True after the daemon's
      first adoption of a TUI-spawned coder, which is the normal
      `codey-start` steady state, meant the gate stopped protecting
      against eager background-ceiling respawns after that point).
      **Fixed same round**: `was_ever_loaded()` replaced with
      `was_ever_spawned()` (genuine-spawn-only, adoption no longer
      counts) in `core/loader_v2.py`/`core/daemon.py`, with matching test
      updates in `tests/test_daemon_model_watchdog.py`/
      `tests/test_loader_resource_gate.py`. **Code complete, tests pass
      (`python -m pytest -q` → 742 passed, 1 skipped, 0 failed). The
      mandatory rule-4 `code-reviewer` subagent pass has NOT run — the
      `code-reviewer` subagent was not invocable in the session that
      built this fix (no Task/subagent-launch tool available); the diff
      was instead reviewed by project-architect directly against
      `.claude/agents/code-reviewer.md`'s own checklist as a stopgap,
      which is not a substitute for the real pass. Live-verification is
      also still outstanding, per the coordinator's explicit instruction
      to stop before invoking `live-verifier` this round.** Do not treat
      sub-task C or `NEW-145` as closed, and do not treat this fix as
      "code-reviewer approved," until both the real `code-reviewer` pass
      and the live-verifier pass (extended to also cover the
      adoption/exit/respawn sequence `NEW-152` describes, per its own
      write-up) are run.

      **Pick up alongside this sub-task (2026-08-11, project-architect
      consolidation pass — `NEW_ISSUES.md` cross-referenced to match):
      `NEW-102`.** Same code this sub-task is already touching —
      `main.py`'s `--ctx` handling and `core/loader_v2.py:
      load_primary()`'s `MODEL_CONFIG.get("n_ctx", ...)` read. `NEW-102`
      is that (a) `main.py`'s `--ctx` flag never actually reaches
      `core/memory_v2.py`'s `CTX_TOTAL` (import order binds it before
      `--ctx` is applied), and (b) `--ctx` has no positive-value guard,
      unlike the `CODEY_N_CTX` env var. Fix alongside this sub-task's own
      n_ctx-branching change rather than as a separate future round.

      **`NEW-102` resolved, 2026-08-13 (project-architect + code-reviewer
      pass, prompted by cloud ultrareview's `bug_002` finding on this
      sub-task's own initial landing).** This sub-task's own first pass
      (the `PLANNER_N_CTX`/`CODER_BACKGROUND_N_CTX` constants above) had
      reintroduced the exact `NEW-102` import-order trap it was supposed
      to close — both were module-level constants derived from `_n_ctx`
      at `utils/config.py` import time, so a runtime `--ctx` override via
      `main.py`'s `apply_overrides()` never reached either of them (only
      the interactive coder path's live `MODEL_CONFIG.get("n_ctx", ...)`
      read did). Confirmed as a real regression, not just a gap: baseline
      commit `163b5e5`'s `core/planner_loader.py:88` read
      `MODEL_CONFIG.get("n_ctx", 4096)` live at call time, so `--ctx` DID
      reach the planner before this sub-task's first pass, and stopped
      after it.

      Fix: `utils/config.py`'s `PLANNER_N_CTX`/`CODER_BACKGROUND_N_CTX`
      constants replaced with `get_planner_n_ctx()`/
      `get_coder_background_n_ctx()` functions that re-read
      `MODEL_CONFIG["n_ctx"]` on every call (same `min(..., 8192/16384)`
      clamp, now evaluated live); `core/memory_v2.py`'s `CTX_TOTAL`
      (the original `NEW-102` finding, unused by any caller today)
      converted the same way to `get_ctx_total()`; `main.py`'s `--ctx`
      argparse handling changed from `if args.ctx:` to
      `if args.ctx is not None:` with an explicit `ValueError` on
      `args.ctx <= 0` (so `--ctx 0`, previously silently ignored via
      Python truthiness, and `--ctx -1` both fail loudly instead of an
      unvalidated bad value reaching the resource gate's KV-cache cost
      estimate). All three call sites (`core/planner_loader.py`'s two
      `PLANNER_N_CTX` reads, `core/loader_v2.py:load_primary()`'s
      `CODER_BACKGROUND_N_CTX` read) updated to the new function names;
      stale comments referencing the old constant names in
      `core/resource_gate.py` and `utils/config.py`'s own header updated
      in the same pass. 4 new tests added to
      `tests/test_74b_planner_and_coder_n_ctx.py` (12 total in that file,
      all passing): runtime `MODEL_CONFIG["n_ctx"]` mutation followed by
      both functions, and `main.apply_overrides()` exercised directly
      with a fake `--ctx` — the regression-specific check that would
      have caught this. Full suite (`python -m pytest tests/ -q`): 670
      passed, 1 skipped, 3 unrelated pre-existing failures (see
      `NEW-150`, logged separately — a different test file's own
      isolation gap, confirmed not caused by this change).

      **Verification tier: code complete, unit-verified.** No live model
      load needed or done — under default settings
      (`min(32768, 8192)`/`min(32768, 16384)`) the numbers this returns
      are identical before and after the fix, so there is no default-path
      behavior change to live-verify. The fix's actual effect (a runtime
      `--ctx` override reaching the planner/background-coder ceilings) is
      unit-verified via `apply_overrides()` called directly, not observed
      through a real `codey-start --ctx <n>` session. Also note: this fix
      makes the *read* live; it does not carry the mutation across
      process boundaries — `apply_overrides()` only runs inside the
      interactive `main.py` process, so a daemon-dispatched background
      coder load (a separate process) still sees whatever `MODEL_CONFIG`
      that process's own import produced, not a `--ctx` flag passed to a
      different process's CLI invocation.

      **Sub-task D — `MAX_CONCURRENT_MODEL_BUDGET_BYTES` (C1) revisit,
      docs-only, no value change expected.** C1's 8.90GiB derivation
      (`core/resource_gate.py:1201-1275`) already summed all THREE
      models — 7B + 1.5B + embed — as a concurrent case, with the embed
      model's ~0.328GiB already included in the raw sum. Always-on
      embed does NOT invalidate this: the derivation already assumed
      embed's cost is always present in the sum, it just wasn't always
      REALIZED in practice before this decision. **What DOES go stale**:
      sub-tasks B and C above shrink two of the three operands — the
      planner's KV term at 8192 (~0.219GiB, roughly a quarter of the
      2,325,280,320-byte figure's 0.875GiB KV term at 32768) and,
      outside interactive sessions, the coder's own KV term at a 16384
      background ceiling instead of 32768. This sub-task recomputes the
      real 3-model sum via `estimate_model_load_cost()` against the
      real on-disk files at the NEW ceilings (once B/C's numbers are
      Ish-confirmed) and updates the derivation comment to match — the
      ceiling itself will very likely stay 8.90GiB (the new sum is
      LOWER, giving MORE margin, not less, so nothing about safety
      regresses), but the comment's stated arithmetic must not be left
      contradicting the code it documents. No code-reviewer needed if
      the constant's value doesn't change (comment-only); mandatory
      review if the recompute does change the value.

      **Does this three-part policy close `NEW-141`'s gap? Worked
      through concretely, not asserted:** `NEW-141` reproduced
      concurrent 7B+1.5B residency, BOTH at full `n_ctx=32768`, causing
      a ~3.2GiB anon-page swap-out in ~6s. Three independent, already-
      existing mechanisms (none of them new to this item) already
      prevent this shape in every SHIPPED production path, and this
      item's decisions shrink the blast radius further if any of them
      is ever bypassed:
      1. **Sequential swap-guard** (`core/planner_loader.py`'s
         `ensure_planner()`) evicts the primary FIRST, before ever
         reserving a planner slot — `NEW-141` was only reproducible by
         calling the lower-level `PlannerLoader.load()` directly,
         bypassing this guard entirely (already logged as `NEW-142`,
         Confirmed: the concurrent-admission consequence is
         "structurally UNREACHABLE via any shipped orchestration path").
      2. **Cross-process eviction safety, checked this pass**: even the
         one place that's exempt from 7.4 sub-task C's interactive-
         session dispatch gate — the synchronous `plan_only:True` RPC,
         which an interactive session can issue on its own behalf while
         its OWN process has the coder loaded at full context —
         cannot evict a model a different process spawned.
         `_evict_primary_and_confirm_free()`
         (`core/planner_loader.py:232-283`) only calls `loader.unload()`
         when `loader.is_loaded()` is true for the CALLING process's own
         `ModelLoader` object; it then re-checks via
         `probe_port_health(PRIMARY_SERVER_PORT)` (a real cross-process
         TCP/health check) and fails closed — "not loading planner"
         — if the primary is still answering, which it will be if a
         different process (the interactive session) owns it. Verified
         by direct read, not run live this pass. No residual gap found
         here.
      3. **7.4 sub-task C's dispatch gate** already defers ALL background
         (daemon) task dispatch — which is the only path that would need
         the planner for anything besides the exempt `plan_only` RPC
         above — while `is_interactive_session_active()` is true
         (live-verified 2026-08-10, `Daemon: dispatch deferred ...
         interactive TUI/GUI session active`). So even setting aside
         mechanisms 1/2, the daemon structurally will not attempt a
         background planner-needing dispatch while the coder is being
         used interactively.

      **Verdict: `NEW-141`'s exact failure shape (concurrent full-
      context 7B+1.5B) remains structurally unreachable through every
      shipped path, both before and after this item** — decisions 2/3
      don't newly CLOSE an open gap (mechanisms 1-3 above already
      closed it), but they substantially shrink the consequence if
      any future change ever bypasses the sequential-swap guard: a
      planner capped at 8192 contributes a much smaller KV footprint
      than one at 32768, and a daemon-dispatched coder task at a 16384
      background ceiling likewise. No further live-verification is
      required to "close" this item's own relationship to `NEW-141` —
      the open item remains `NEW-141`/`NEW-140`'s own scenario 3 (low-
      swap-headroom device shape), already logged as deferred, unrelated
      to this item's three decisions.

      **Build order for implementer**: A (embed lifecycle, blocked on
      fixing `NEW-144` first) and D (docs-only) can start immediately.
      B and C are BOTH blocked on Ish confirming their respective
      candidate numbers (8192 planner ceiling; 16384 background coder
      ceiling) before implementer starts — do not implement against
      either candidate as if already approved.

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

- [x] 4.1 (WQ Track 3 item 2, "PENDING_ISH_DECISIONS.md item 2") — Daemon
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
      update) — committed (`b37d17f`, 2026-08-10), code-reviewer-
      approved.** Pure docs/description text, no
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
      Track 3 item 2 sub-task 5 for the full accounting. **4.1 as a
      whole is now closed: sub-tasks A-E all committed and
      code-reviewer-approved (A `c48f77b`, B `a4eb77b`, C `d8bcaa7`, D
      `696aafe`, E `b37d17f`), with C and D also live-verified
      (`96b6ea1`); A and E carried no process-lifecycle/dispatch
      behavior change so code-complete is their correct final status,
      not a stand-in for live-verified. B is not independently
      live-verified either — it touches PID-file/lock logic (CLAUDE.md
      rule 4) but round 19's sub-task C live-verification did exercise
      B's per-session `~/.codeyOS/tui-sessions/` lock mechanism live as
      a side effect of testing C, not as B's own dedicated pass.**
- [ ] 7.3 (WQ Track 3 item 3, "Phase 5b") — **Scoped 2026-08-10
      (project-architect, desk-only, no code changed).** Task classifier
      + tier config, coding domain only. Full sub-task breakdown (A-D
      decide-half, buildable now; E act-half, blocked on 7.4) in
      `WORK_QUEUE.md`'s Track 3 item 3 entry — read that before starting
      implementation. Short version: A extracts a shared signal-scoring
      helper from `core/orchestrator.py:is_complex()` (scoring logic
      only, keyword lists stay put) so the new classifier reuses it
      instead of a third drifting keyword list. **Sub-task A: done,
      code-reviewer-approved, uncommitted** — `_score_message()` +
      `ScoreResult` dataclass added to `core/orchestrator.py`,
      `_action_kws`/`_question_starters`/`_qa_phrases` moved to module
      level (not duplicated, not moved to a new module),
      `is_complex()` rewritten to call the new helper with identical
      control flow/thresholds — confirmed behaviorally equivalent
      (`tests/test_orchestration.py`: 41 passed; full suite: 522
      passed, 1 skipped). `core/agent.py`'s separate duplicate
      `_action_kws` list was left untouched, out of this sub-task's
      one-file scope. **Sub-task B: done, code-reviewer-approved,
      uncommitted** — new `core/model_tiers.py` (`MODEL_TIERS: Dict[
      (domain, role, tier), ModelTierEntry]`, `ModelTierEntry` =
      `{model_ref, backend, port}`, `get_tier()`/`tiers_for_role()`
      helpers, values sourced from `utils/config.py` not re-hardcoded),
      coding domain only, coder role's single local tier (`SECONDARY_
      MODEL_PATH` / `NEW-84` deliberately excluded), planner's `large`
      tier and coder's `large` tier both point at the same physical 7B
      per `NEW-125`, remote tier entries populated only when
      `CODEY_BACKEND`/`CODEY_BACKEND_P` is actually set remote at
      import time (`get_tier()` raises `KeyError` on a missing key,
      matching this project's fail-loud config convention) — not
      wired into any loader/dispatch path yet (confirmed via grep).
      24 new unit tests, no live model loads; full suite 611 passed, 1
      skipped. **Sub-task C: done, code-reviewer-approved, uncommitted** —
      `classify_tier(domain, role, message) -> str` added to
      `core/model_tiers.py` (reuses `core.orchestrator._score_message()`
      rather than a third keyword list; coder role always returns
      `"large"`, its only local tier; planner role picks `"small"`/`"large"`
      via `has_action`/`length`/`signal_count`), wired into
      `planner_service.get_plan()` to *log* its decision (and the raw
      signal breakdown) alongside the existing fallback ladder, which is
      unchanged — confirmed log-only both by code trace and by tests that
      run `get_plan()` with the real (unmocked) `classify_tier()` and
      assert its return value is untouched. 15 new unit tests
      (`tests/test_model_tiers.py`'s `TestClassifyTier`,
      `tests/test_planner_service_classify_tier.py`), full suite 630
      passed, 1 skipped. Findings from this sub-task: `NEW-126` (current
      thresholds resolve to `"large"` for nearly all prompts, and
      `classify_tier()` has no `"remote"`-tier code path at all today even
      though `_request_daemon_plan()` does route to a remote backend when
      configured — both flagged for sub-task E to address, not fixed here).
      **Sub-task D: done, code-reviewer-approved, uncommitted** — direct
      unit coverage for `_score_message()`/`ScoreResult`
      (`tests/test_orchestration.py`'s new `TestScoreMessage`, 15 tests)
      and for `is_complex()`'s exact branch thresholds
      (`TestIsComplexThresholdBoundaries`, 7 tests, pinning
      `core/orchestrator.py:276-281`'s length 49/50/150/151/300/301
      edges); `MODEL_TIERS`/`get_tier()`/`classify_tier()` edge cases
      (empty message, unknown domain/role, `length`/`signal_count`
      boundary values) and a full-chain integration sweep across every
      `(domain, role)` pair in `MODEL_TIERS` were already covered by
      sub-tasks B/C's own `tests/test_model_tiers.py` (39 tests) —
      verified directly, no gap remained to fill there. Two new
      findings logged, not fixed: `NEW-127` (`core/agent.py`'s inline
      `_action_kws` list has drifted 6 words out of sync with
      `core/orchestrator.py`'s module-level copy — verify/test/
      validate/confirm/complete/finish — with a reproduced case where
      the two disagree on `has_action`) and `NEW-128` (`is_complex()`'s
      `length > 300` branch is byte-identical to the `elif length > 150`
      branch below it — dead-code duplication, not a functional bug).
      Full suite: 659 passed, 1 skipped. **E (actually switching
      which model loads based on the classifier's tier) is out of scope
      for this round** — Vision §7.6 item 1 requires the resource gate to
      exist before tier logic can safely *act*, and 7.4's positive
      admission path (a real load-through-gate-then-unload cycle) is
      still unverified per 7.4's own status above. **Ish confirmed
      2026-08-10: proceed with A-D now, ahead of 7.4 closing** — C only
      logs `classify_tier()`'s decision, never dispatches on it, so no
      real load/act risk exists yet; E stays blocked on 7.4 as scoped.
      Planner model-family choice stays deferred to
      this phase's on-device validation, unchanged from the original
      scope note. Two findings logged during scoping, not fixed:
      `NEW-124` (stale "0.5B" doc comment in `planner_service.py`,
      actual model is 1.5B), `NEW-125` (the 7B coder model and the
      planner's large-tier fallback are the same physical model today —
      the tier config table needs to represent that honestly, not paper
      over it).
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
