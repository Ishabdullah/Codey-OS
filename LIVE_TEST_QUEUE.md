# Live Test Queue — for Ish to run without Claude active

**Why this file exists:** per CLAUDE.md rule 2, this device has crashed
from concurrent model loads before. Ish has confirmed the actual trigger
is running Claude (this agent) *at the same time* as the 7B/1.5B/embed
models — the three models alone, without Claude also running, are within
the device's real limit. So: while Claude is doing TODO.md work, any item
that would require loading a model live is **not** executed by Claude —
it's code-complete + unit/mock-tested only, and the specific live-test
step needed is recorded here instead, for Ish to run himself later
(without Claude active) once there's something worth testing.

Add an entry here any time a TODO.md item's real verification needs a
live model load. Update `TODO.md`'s own note for that item to point here
plus "code-complete, live test deferred — see LIVE_TEST_QUEUE.md."
Ish logs any issue found running these back into `NEW_ISSUES.md` per the
normal convention (Confirmed/Suspected, next `NEW-##` ID).

---

## Queue

### [NEW-83] `core/embed_server.py`'s port-occupant kill logic — confirm real PID identification works on-device

- **What was built and reviewed:** `_kill_port_occupant()`'s bare `pkill
  -9 llama-server` (a CLAUDE.md rule 3 violation) replaced with
  positively-identified PID killing: `_find_port_occupant_pid()` (parses
  `/proc/net/tcp`+`tcp6`) as primary, `_find_pid_via_registered_slot()`
  (checks `resource_gate`'s residency store) as secondary fallback, fails
  loudly if neither identifies a PID. Code-reviewer-approved (round 6,
  2026-08-09). 14/14 new tests pass, but one self-skips because
  `/proc/net/tcp` returned `PermissionError` in the dev sandbox — this is
  suspected to match a real Android/Termux restriction on that path for
  unprivileged apps.
- **What the live test should do:** on the actual device, deliberately
  occupy the embed server's port (8082) with a foreign process, then start
  `embed_server` and confirm: (1) it correctly identifies and kills the
  right PID (not a bare-name kill of anything else running), (2) it
  actually starts successfully afterward, (3) if `/proc/net/tcp` really is
  unreadable here, confirm the registered-slot fallback path is what's
  actually firing (add temporary logging if needed to see which path
  succeeded) — this determines whether the "secondary fallback" is
  actually the primary real-world mechanism, which matters for how
  seriously to take `NEW-86`'s residual PID-recycling race.
- **RAM discipline reminder:** this test only needs the embed server
  itself running, not the full 7B/1.5B stack — keep it isolated, run
  `free -h` before/after per rule 2 regardless.
- **What to log back and where if it fails:** if `/proc/net/tcp` is
  confirmed unreadable on-device and the registered-slot fallback also
  fails to identify the occupant in some real scenario, log a new
  Confirmed `NEW-##` finding — this would mean the fix's "fail loudly
  instead of killing blind" behavior could produce real, repeating
  startup failures on this device, not just a theoretical edge case.

### [TODO.md 7.4 sub-task 2] Slot-aware loaders — confirm the real `/proc/meminfo` residency-confirmation poll works against an actual model load

- **What was built and reviewed:** `core/loader_v2.py`'s
  `ModelLoader.load_primary()` and `core/planner_loader.py`'s
  `PlannerLoader.load()` now reserve a slot via `resource_gate.reserve_slot()`
  before spawning `llama-server`, and confirm residency via a bounded
  `/proc/meminfo`-drop poll (`confirm_resident_and_mark_slot()`) before
  marking the slot resident — not just a health-endpoint answer. A
  structural try/finally (added in a follow-up fix, both
  code-reviewer-approved) guarantees the spawned process is stopped and
  the reservation released on any exception in the reserve→spawn→confirm
  window. Every test so far drives `confirm_resident_and_mark_slot()`'s
  poll via a patched `read_meminfo` — the real `/proc/meminfo`-drop
  detection logic has never executed against an actual model load.
- **What the live test should do:** load the real 7B model via
  `load_primary()` (and separately, the 1.5B planner via
  `PlannerLoader.load()`) on-device and confirm: (1) the slot gets marked
  resident only after real memory usage actually reflects the load, not
  prematurely off a health-check response; (2) the poll's bound is long
  enough to reliably detect a real load's memory-usage rise without
  false-negatively timing out; (3) `resource_gate.list_slots()` shows
  exactly one resident slot per loaded model, no leaks, after a normal
  successful load-then-unload cycle.
- **RAM discipline reminder:** this is a real model-load test — run
  `free -h` before and after per rule 2, one model-load cycle at a time,
  confirm fully unloaded (`ps aux | grep llama-server` showing nothing
  but the grep) before running the second (planner) case.
- **What to log back and where if it fails:** if the poll times out on a
  real load, or marks a slot resident before memory usage actually rose,
  log a new Confirmed `NEW-##` finding — either would mean the gate's
  admission math (built in sub-task 1, validated only against synthetic
  fixtures) is unsafe against real load behavior, which is exactly what
  sub-task 1's un-calibrated `REQUIRED_HEADROOM_FACTOR`/
  `DEVICE_CEILING_USABLE_FRACTION` constants were flagged as needing this
  kind of validation for.

### [TODO.md 7.4 sub-task 3] Daemon watchdog outcome handling — confirm gate-denial vs. genuine-crash distinction behaves correctly on-device

- **What was built and reviewed:** `core/daemon.py`'s 30s model watchdog
  (`Daemon._watchdog_check_model()`) now distinguishes a gate-denied
  reservation (transient or hard), `SWAP_GUARD`-deferred, never-loaded,
  and a genuine process crash, instead of treating all of them as "died —
  restarting." Startup preload and shutdown unload are similarly
  outcome-aware. Also folds in `NEW-84`'s fix (loaders now read
  `cfg.MODEL_PATH`/`cfg.PLANNER_MODEL_PATH` fresh per call instead of a
  stale import-time binding), reviewed together since both changes ended
  up in the same files.
- **What the live test should do:** on-device, deliberately create a
  real resource-pressure scenario (e.g. constrain available RAM some
  other way, or trigger it naturally under real load) so the gate
  actually denies a daemon reservation at least once, and confirm: (1)
  the watchdog logs it as a gate-denial, not "died — restarting"; (2) the
  daemon doesn't spin retrying pointlessly on a hard denial; (3) once
  headroom returns, the model actually loads successfully on a later
  watchdog tick without needing a daemon restart. Also confirm a normal
  successful startup/watchdog/shutdown cycle behaves identically to
  before this change (no regression in the common case).
- **RAM discipline reminder:** this may involve deliberately inducing
  memory pressure — do this carefully, one model-load cycle at a time,
  `free -h` before/after, and be ready to intervene if the device
  actually approaches its real crash threshold rather than just the
  gate's conservative admission threshold.
- **What to log back and where if it fails:** if the watchdog
  misclassifies a real outcome, or a hard-denied reservation somehow
  still causes a restart loop, log a new Confirmed `NEW-##` finding.

### [TODO.md 7.4 sub-task 4] Daemon `release_model_slot` command — confirm real busy/release behavior against a live daemon

- **What was built and reviewed:** `core/daemon.py`'s new
  `release_model_slot` Unix-socket command lets an external process ask
  the daemon to unload a model (`"primary"` or `"planner"`) and free its
  resource-gate slot. Declines cleanly if a task is actively inferring or
  a swap is in flight, no-ops cleanly if already unloaded, otherwise
  unloads and confirms via a bounded port-health poll. Not yet called by
  anything real — `main.py`'s CLI integration is sub-task 5.
- **What the live test should do:** with the daemon actually running and
  the 7B model loaded, send a real `release_model_slot` request (via
  `core/daemon.py`'s existing `send_command()` socket client) and
  confirm: (1) the model actually unloads and the port stops answering;
  (2) sending it again immediately gets a `cooldown` decline, not a
  second unload; (3) sending it while a real task is actively running
  gets a `busy_task_running` decline, not an unload mid-task — this is
  the one that most needs real confirmation, since it was only tested
  against a mocked thermal manager, never a genuinely in-flight
  inference call.
- **RAM discipline reminder:** one model-load cycle at a time, `free -h`
  before/after, confirm the model actually stops (`ps aux | grep
  llama-server`) after a confirmed release before considering the test
  done.
- **What to log back and where if it fails:** if a release happens while
  a real task is genuinely mid-inference, that's a Confirmed, high-
  severity finding — it would mean the busy-check that's supposed to
  protect in-flight work doesn't actually work under real conditions.

### [TODO.md 7.4 sub-task 5, and 7.4 as a whole] CLI gate-recovery path + full end-to-end resource gate — real on-device confirmation

**Status: attempted 2026-08-09 (round 13), partially resolved — see
`PROJECT_LOG.md` round 13 and `NEW-95` through `NEW-99` for full detail.
Re-reading this entry before the next attempt: some of the "what to test"
below is now done; some is newly blocked on two found-live gaps
(`NEW-96`/`NEW-97`, tracked as `TODO.md` `U.27`/`U.28`) that are worth
fixing first.**

- **What was built and reviewed:** `main.py`'s four CLI load sites
  (`repl()`, `args.init`, `args.tdd`, `args.fix`) now recover from a
  transient gate denial by asking the daemon to release a slot and
  retrying once; a hard denial doesn't retry. This is the last of five
  sub-tasks — the resource gate (sub-task 1), slot-aware loaders
  (sub-task 2), daemon migration (sub-task 3), the daemon-side release
  command (sub-task 4), and this CLI recovery wiring (sub-task 5) are all
  code-complete and code-reviewer-approved.
- **What round 13 actually confirmed live**: the CLI path
  (`main.py --init` → `load_primary()`) genuinely reaches
  `can_admit()` and reports a real hard denial with byte-exact figures,
  confirmed across two separate runs; sub-task 5's
  `LOAD_OUTCOME_GATE_DENIED_HARD` skip-daemon-contact branch, live, for
  the first time; the gate correctly refusing to spawn a model whose real
  KV-cache shape doesn't fit, with zero crash/hang/orphan.
- **What's still not confirmed, and why**: (1) An actual successful
  load-through-the-gate-then-unload cycle — every substitute tried so far
  either doesn't fit (round 13's Qwen3-4B) or wasn't tried; needs a
  substitute with a genuinely smaller real KV-cache footprint than the
  production 7B at `n_ctx=32768` (not just a smaller file — the file size
  and the KV-cache cost don't track each other across model families;
  round 13's substitute was a *smaller file* with a *larger* KV-cache
  shape), or a documented way to vary `n_ctx` for a test run (no env
  override exists for `n_ctx` today). (2) `release_model_slot` (sub-task
  4) actually firing on a real request — never reached, because round
  13's daemon-side attempt never got past the pre-existing, unrelated
  `eviction_failed` check (`NEW-96`) to reach the gate at all. (3) The
  transient-`GATE_DENIED`-then-retry path (as opposed to the hard-denial
  path, which IS now confirmed) — also not reached.
- **Recommended before the next attempt**: fix `U.27`/`U.28`
  (`NEW-96`/`NEW-97`) first — as long as `plannd` runs outside the gate's
  accounting and the daemon's own eviction check blocks it from ever
  reaching `can_admit()`, the daemon-side half of this test can't
  meaningfully proceed regardless of which model is substituted. Also
  pick (or add an env override for) a substitute whose real KV-cache
  shape (verify via GGUF header, don't assume from file size) is smaller
  than the 7B's at production `n_ctx`.
- **RAM discipline reminder:** this is the real deal — one model-load
  cycle at a time, `free -h` before/after every step, confirm fully
  unloaded between attempts. This test deliberately creates resource
  contention on purpose, so watch actual system behavior closely, not
  just the gate's reported outcome.
- **What to log back and where if it fails:** any real crash, orphaned
  process, leaked slot, or incorrect admission decision is a Confirmed
  finding.

## Format for future entries

```
### [Item ref, e.g. TODO.md 7.4] Short description of what needs live-testing
- What was built and unit/mock-tested (commit ref).
- Exactly what the live test should do (steps, expected outcome).
- RAM discipline reminder specific to this test if relevant (e.g. "confirm
  both 7B and 1.5B stay resident per the sequential-swap design" or
  "confirm only one model loads at a time").
- What to log back and where if it fails.
```
