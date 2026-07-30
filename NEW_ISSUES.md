# New Issues Found During V3 Overhaul

## Milestone (2026-07-30): all four original punch-list items resolved

The user's original four-item punch list — [NEW-3], [NEW-1], [NEW-5],
and [NEW-2] — is now fully resolved (see each entry below for its own
resolution evidence and commit). [NEW-6] (sibling `load_primary()`
KeyboardInterrupt gap at three call sites in `main.py`) is now also
Resolved (2026-07-30, Round 8, commit `435c120`). [NEW-7] (the
`[Recursive]` planner's tendency to synthesize whole duplicate
functions with `old_str=""` instead of targeted patches) and [NEW-8]
(a pre-existing, unrelated `ccos/tests/test_ccos.py::test_sandbox`
failure) remain open. [NEW-9] (a residual, intermittent atfork/fork-
window race that can bypass the guard pattern shared by NEW-5's and
NEW-6's fixes, at all four call sites) was newly discovered during
Round 8's live-verification of NEW-6 and logged Confirmed — needs its
own dedicated scoping pass, not yet queued for a fix.

## Found during Round 3 (NEW-4) live-verification pass, 2026-07-29 — NOT fixed, logged only

### [NEW-5] `llama-server` child can outlive `gui/start.sh`'s (or any) parent process indefinitely on a TERM/Ctrl+C during mid-load, with no automatic recovery
- **Status: Resolved** (2026-07-30, Round 6). Fixed by commit `eed29dc`:
  `main.py`'s `repl()` (~line 1267-1274) now wraps `loader.load_primary()`
  in `try/except (KeyboardInterrupt, SystemExit)`, calling the existing
  `shutdown()` and returning cleanly, reusing the scoped-PID teardown
  path with no new kill logic. code-reviewer approved; live-verifier
  independently reproduced a genuine mid-load `SIGINT` via `pty.fork()`
  (tracked child PID) and confirmed no orphan `llama-server` remained
  (`ps -eo pid,ppid,pgid,comm | grep -E "python|llama"` empty, `free -h`
  RAM recovered), plus a regression check on the normal-completion path.
  See `PROJECT_LOG.md` 2026-07-30 entry for full verbatim evidence.
  `NEW_ISSUES.md` [NEW-6] (same unguarded pattern at three sibling call
  sites) remains open as a separate, unscoped follow-up.
- **Caveat added (2026-07-30, Round 8 live-verification of NEW-6) — per
  CLAUDE.md rule 6, correcting the record rather than letting the
  unqualified "fully live-verified" claim above stand as if this gap
  didn't exist.** Round 8's live-verifier, testing the sibling `try/except
  (KeyboardInterrupt, SystemExit)` guard at three other call sites that
  share this exact pattern, found that the same guard shape used here in
  `repl()` has a narrow, intermittent residual gap: if `SIGINT` lands
  during `subprocess.Popen()`'s internal `os.fork()` call inside
  `core/loader_v2.py` (~lines 116-130), CPython's own atfork exception
  handling can silently swallow the `KeyboardInterrupt` before it ever
  reaches the guard's `try/except` — meaning the guard simply never fires
  in that narrow window, in all four call sites that share this pattern
  (this one included), not just the three new ones. This is **not** a
  regression in this fix and does **not** downgrade this entry's overall
  Resolved status — the guard demonstrably works correctly for the vast
  majority of the interrupt window (this entry's own Round 6
  live-verification above, plus 2 of 2 clean reruns of the sibling
  `args.init` site in Round 8). It is a newly-discovered, narrower,
  pre-existing residual gap in the shared `core/loader_v2.py` Popen/fork
  code, logged in full as its own entry, [NEW-9] below.
- **Confidence: Confirmed** (upgraded 2026-07-29, Round 6 — live-reproduced
  and root-caused by reading the code; previously Suspected on a single
  observation).
- **Original (Suspected) finding, Round 3:** implementer's live
  verification of the default (no-flag) path for the Round 3
  `--dashboard-only` task (`gui/start.sh`, commit `ea954eb`) observed the
  spawned `llama-server` child (a tracked PID) "still alive briefly"
  after the parent script exited on a mid-load `TERM`, before being
  killed directly by that tracked PID. Not reproduced a second time at
  the time; no root cause investigated.
- **Round 6 live reproduction (this entry's upgrade):** live-verifier sent
  `kill -TERM` to the tracked `gui/start.sh` script PID while the 7B
  model was mid-load, then polled every 0.5s for 10+ seconds. The bash
  script, `gui/server.py`, `main.py`, and `llama-server` were **all still
  alive, unchanged**, for the entire polling window — not "briefly"
  outliving the parent, but surviving it with no sign of any teardown in
  progress. Letting it run to full completion (~40s later total), the
  script's own `trap ... TERM` handler **never fired**, because bash was
  blocked in `wait()` on its foreground child (`python main.py`), which
  does not exit on its own when sent `TERM` this way. The tracked PIDs
  (`main.py` and `llama-server`) had to be killed individually and
  manually — there is no automatic recovery path.
- **Root cause (identified by reading the code, not just observing
  behavior):**
  - `main.py`'s `repl()` (around line 1269) calls
    `loader.load_primary()` with no `try/except KeyboardInterrupt`
    wrapper around the call.
  - `ModelLoader.load_primary()`'s own exception handler
    (`core/loader_v2.py` around line 351) is `except Exception`, which
    does **not** catch `KeyboardInterrupt` (it subclasses
    `BaseException`, not `Exception`), so a `KeyboardInterrupt` raised
    during the load window propagates straight out of `load_primary()`
    uncaught.
  - There is also no top-level exception handler around `main()` itself
    (bottom of `main.py`, `if __name__ == "__main__": main()` is bare),
    so an uncaught `KeyboardInterrupt` during this window exits the
    process without ever calling `shutdown()` (`main.py` line ~125,
    which contains the correct scoped-PID teardown logic via
    `loader.get_pid()` / `loader.unload()`).
  - Separately, `llama-server` is spawned with `preexec_fn=os.setsid`
    (`core/loader_v2.py` line 127), putting it in its own process
    group specifically to insulate it from terminal signal groups —
    meaning it is never touched by a terminal-delivered signal that
    hits `main.py`, and depends entirely on `main.py`'s own code
    explicitly killing it. When that code path is skipped (as above),
    `llama-server` becomes a genuine, indefinitely-running orphan.
  - Important supporting detail for any fix: `ModelLoader.load_primary()`
    (`core/loader_v2.py` line 341) assigns `self._server = LlamaServer(...)`
    **before** calling `self._server.start()` (line 342), and `start()`
    itself sets `self.process` (the `Popen` handle, with its real PID)
    immediately after spawning (line 123-130), well before the up-to-60s
    health-check polling loop that follows (lines 132-153). This means
    `loader.get_pid()` / `loader.unload()` are both usable to tear down a
    partially-started server for nearly the entire load window, not just
    after a successful load — a catch-and-teardown fix has a real target
    to kill for almost the full duration of the exposure window.
- **Confirmed NOT broken:** a normal Ctrl+C at the `You>` prompt (i.e.
  post-load, in the REPL's own input loop) works cleanly and tears
  everything down in ~1.5s — the REPL's existing
  `except (KeyboardInterrupt, EOFError)` blocks (e.g. `main.py` line 948)
  catch it fine there. The gap is specific to the model-load window,
  before any of those handlers are active.
- **Scope note:** lives entirely in `main.py`'s own model-load call site
  and `core/loader_v2.py`'s exception handling, not in `gui/start.sh`'s
  trap logic. Confirmed unreachable in `--dashboard-only` mode, since
  `main.py` never runs there.
- **Fix direction (scoped as a Round 6 follow-on task, not yet applied):**
  wrap the `loader.load_primary()` call in `repl()` (`main.py` ~line
  1269) in a `try/except (KeyboardInterrupt, SystemExit)` that, on catch,
  calls the existing `shutdown()` (`main.py` line 125) to tear down any
  partially-started server via the scoped-PID path it already uses, then
  exits cleanly — reusing `shutdown()`, not reinventing a parallel kill
  path. This is CLAUDE.md rule 4 territory (process/daemon lifecycle,
  kill logic) and requires code-reviewer's explicit approval before
  commit regardless of how small the diff looks.

## Found during Round 6 NEW-5 root-cause investigation, 2026-07-29 — NOT fixed, logged only

### [NEW-6] Same unguarded `loader.load_primary()` pattern exists at three other call sites in `main.py`
- **Status: Resolved (2026-07-30, Round 8, commit `435c120`).** `main.py`'s
  `args.init`/`args.tdd`/`args.fix` sites each now wrap
  `loader.load_primary()` in `try/except (KeyboardInterrupt, SystemExit)`,
  calling the existing `shutdown()` and returning cleanly — the same
  pattern as NEW-5's `repl()` fix (`eed29dc`). code-reviewer approved.
  live-verifier ran all three sites plus a `--tdd`/`--fix` pass: 3 of 4
  site-tests (`--init` reruns x2, `--tdd`, `--fix`) came back clean —
  guard fired, no orphan `llama-server`, `ps` empty afterward, `free -h`
  recovered RAM each time. One of four `--init` attempts reproduced a
  genuine orphan (real `llama-server`, PPID 1, `ps` confirmed), root-caused
  to a residual atfork/fork-window race in the **shared**
  `core/loader_v2.py` Popen call — pre-existing in the underlying
  `try/except (KeyboardInterrupt, SystemExit)` pattern itself, not a
  regression introduced by this round's diff, and not specific to the
  three new sites (it affects `repl()`'s existing guard too). See
  `PROJECT_LOG.md` 2026-07-30 Round 8 entry for full verbatim evidence.
  **This fix works exactly as scoped** — the guard correctly catches
  `KeyboardInterrupt`/`SystemExit` and tears down via `shutdown()` for the
  vast majority of the model-load window at all three sites, matching
  NEW-5's `repl()` behavior. The residual fork-window race is a separate,
  already-logged concern, not a defect in this round's diff — tracked as
  its own entry, [NEW-9] below, since it needs its own dedicated
  scoping/fix pass (likely relocating or supplementing the guard to also
  cover the fork window itself).
- **Confidence: Suspected** (same code shape confirmed by reading the
  code; not independently live-reproduced at each site the way NEW-5 was
  for the `repl()` path — but the mechanism is identical, so the risk is
  the same in kind).
- **Where found:** while investigating NEW-5's root cause, grepped all
  call sites of `loader.load_primary()` in `main.py`. In addition to
  `repl()` (~line 1269, the one covered by NEW-5's scoped fix), the same
  unguarded pattern (`loader = get_loader(); loader.load_primary()` with
  no surrounding `try/except KeyboardInterrupt`) appears at:
  - `args.init` path, `main.py` ~line 1458
  - `args.tdd` path, `main.py` ~line 1465-1466
  - `args.fix` path, `main.py` ~line 1485-1486
- **Why this matters:** a `KeyboardInterrupt` (e.g. Ctrl+C) during model
  load in any of these one-shot CLI paths would hit the same gap as
  NEW-5 — no handler catches it before it propagates out of
  `load_primary()`, `shutdown()` is never called, and `llama-server`
  (spawned in its own process group via `preexec_fn=os.setsid`) is left
  as an orphan.
- **Not fixed here:** the NEW-5 fix task is deliberately scoped to just
  the `repl()` call site (the one actually live-reproduced). These three
  sibling sites are logged for a possible dedicated follow-up task, not
  bundled into the NEW-5 fix, to keep that fix tightly scoped per
  CLAUDE.md's project-architect instructions.

## Found during Round 9 (NEW-9) scoping pass, 2026-07-30 — NOT fixed, logged only

### [NEW-10] `main.py` has no `SIGTERM` handler at all — a direct `SIGTERM` during model load (or any point) terminates the process instantly, bypassing every existing `try/except (KeyboardInterrupt, SystemExit)` guard entirely
- **Confidence: Suspected.** Confirmed via code-reading and a Python
  semantics check (`signal.getsignal(signal.SIGTERM)` returns `SIG_DFL`
  in a fresh interpreter; `grep -n "signal\." main.py` shows no
  `signal.signal(signal.SIGTERM, ...)` call anywhere in `main.py`) —
  not yet live-reproduced as an actual orphan from a direct `SIGTERM`
  sent to the `main.py` process itself (distinct from NEW-5's Round 6
  finding, which was about `gui/start.sh`'s bash wrapper not forwarding
  `TERM` to its foreground child, a different mechanism).
- **Where found:** while root-causing NEW-9's atfork/fork-window race
  (Round 9 scoping pass), checked whether the same race applies to
  `SIGTERM` as well as `SIGINT`. It does not apply in the same way —
  it's worse. `SIGINT` has a default Python-level handler
  (`signal.default_int_handler`) that raises `KeyboardInterrupt`, which
  is what lets `try/except (KeyboardInterrupt, SystemExit)` guards catch
  it at all (when the atfork race doesn't swallow it first). `SIGTERM`'s
  disposition in `main.py` is unmodified `SIG_DFL`, whose default action
  is immediate process termination at the kernel level — it never
  reaches Python bytecode, never raises any exception, and cannot be
  caught by any `try/except`, including the NEW-5/NEW-6 guards, at any
  point in the model-load window (not just the narrow fork window NEW-9
  describes).
- **Impact if confirmed:** a direct `kill -TERM <main.py PID>` (as
  opposed to sending TERM to `gui/start.sh`'s bash wrapper, which was
  NEW-5's original scenario) during model load would orphan
  `llama-server` unconditionally, 100% of the time, with none of the
  NEW-5/NEW-6/NEW-9 guard work having any effect on this path.
- **Not fixed here:** out of scope for NEW-9's scoping pass, which is
  specifically about the `SIGINT`/`KeyboardInterrupt`/atfork race.
  Needs its own dedicated scoping pass: likely direction is installing
  an explicit `signal.signal(signal.SIGTERM, ...)` handler early in
  `main.py` that translates `SIGTERM` into a controlled shutdown path
  (e.g. raising `SystemExit` or directly invoking the existing
  `shutdown()`), which is CLAUDE.md rule 4 territory and needs
  code-reviewer's explicit approval before commit.

## Found during Round 10 NEW-9 follow-up discussion, 2026-07-30 — NOT fixed, logged only

### [NEW-11] Daemon's 30s watchdog checks a stale in-memory flag, not real process liveness
- **Confidence: Confirmed** (read directly from code, not inferred).
- **Where:** `core/daemon.py:549-563`, the periodic (every 30s / 60 ticks
  × 0.5s) watchdog inside `_main_loop`. It checks
  `loader.get_loaded_model()` and, if falsy, logs `"7B model server
  died — restarting..."` and calls `loader.load_primary()`.
- **The gap:** `get_loaded_model()` (`core/loader_v2.py:382-384`) just
  returns `"primary" if self._loaded else None` — an in-memory boolean
  set once at load time. It does **not** call `self.process.poll()` or
  otherwise check real process liveness. Once `self._loaded` becomes
  `True`, it stays `True` forever (no periodic poll resets it), so this
  watchdog only catches "the daemon never successfully loaded the model
  in the first place" — it would **not** detect a genuine mid-session
  crash of an already-successfully-loaded `llama-server` while the
  daemon keeps running.
- **Mitigating factor:** the daemon is not the only safety net.
  `core/inference_v2.py:90-94` calls `loader.ensure_model()` on every
  single inference request, and `ensure_model()`
  (`core/loader_v2.py:376-380`) **does** check real liveness
  (`is_running()` → `process.poll()`/HTTP health check) and will
  respawn via `load_primary()` if genuinely dead. So a crash would
  still self-heal on the next inference call, just not proactively via
  the watchdog.
- **Impact:** Low-to-medium. Not a process-orphaning bug itself
  (opposite problem — it under-reacts, not over-spawns), but it means
  the daemon's own dashboard/status data could show "model loaded" when
  it's actually dead, for however long until the next real inference
  request.
- **Not fixed here** — logging only, per CLAUDE.md rule 8. Fix direction
  for a future pass: change the watchdog's check to call
  `loader._server.is_running()` (real liveness) instead of
  `get_loaded_model()` (stale flag), or reset `self._loaded = False`
  when `is_running()` becomes false.
- **Relation to NEW-9:** separate, unrelated mechanism — **not** the
  same bug. Confirmed by direct evidence: NEW-9's live-reproductions
  all happened 2026-07-30 while `~/.codeyOS/codeyOS.log` shows the
  daemon was only ever started once, on 2026-07-29 13:35, and never run
  since (no PID file, no process currently alive). The daemon could not
  have been involved in any NEW-9 reproduction.

### [NEW-12] Duplicated/scattered model-launch configuration — a second, uncoordinated `llama-server` launcher exists with no port-conflict check
- **Confidence: Confirmed** (read directly from code — exact file:line
  citations below, not inferred).
- **Where found:** investigating the user's report that changing which
  model Codey-OS uses required updating the path in multiple locations.
- **Core finding:** there are two independent places that build and
  launch a `llama-server` subprocess command for the primary 7B model
  on port 8080, not one:
  1. `core/loader_v2.py:127` (`LlamaServer.start()`, in `LlamaServer`
     class) — the canonical path used by daemon and CLI via
     `get_loader()`. Command built at `core/loader_v2.py:58-110`. Uses
     `os.setsid` (line 131) for clean process-group teardown via
     `killpg` (line 179). Does check port-in-use before spawning
     (`loader_v2.py:49-53`, `_is_port_in_use()` at 212-231) and reuses
     an existing server if one answers instead of double-spawning.
  2. `core/inference.py:40-103` (`_start_server()`) — a second, legacy
     launcher with a different flag set (no `--host`, no `--embedding`,
     no mmap/mlock handling; see `core/inference.py:60-79`). Has **no**
     port-in-use check at all before `subprocess.Popen` (line 84) —
     only skips spawning if its own module-global `_server_proc` is
     already alive, which is irrelevant to whether some other process
     already has port 8080 bound. No `os.setsid`/process-group
     detachment — plain `Popen` with `stdout=DEVNULL, stderr=DEVNULL`
     (no logs, no group-kill handle). Its `stop_server()`
     (`core/inference.py:106-110`) is never called from anywhere in the
     codebase (confirmed via grep, zero callers) — meaning if this path
     spawns a server, nothing in the daemon's shutdown path
     (`core/daemon.py:583-588`, which only knows about
     `loader_v2.get_loader().unload()`) or anywhere else ever tears it
     down.
- **Is the legacy path reachable, or dead code? Reachable, not dead.**
  `core/inference_v2.py:192-213` (`_infer_http`) imports and calls
  `core.inference.infer` as a fallback (`core/inference_v2.py:196`),
  triggered whenever the primary chat backend fails to initialize or
  throws an exception (`core/inference_v2.py:59-61` init exception
  path, `core/inference_v2.py:99-106` mid-request exception path). So
  under a real, plausible failure condition, live code will call into
  `core/inference.py`'s independent, no-port-check, never-torn-down
  launcher.
- Port 8080 has no single named config constant (unlike ports
  8081/8082, which have `PLANND_SERVER_PORT`/`EMBED_SERVER_PORT` in
  `utils/config.py`) — it's hardcoded independently in
  `core/loader_v2.py:25` (`SERVER_PORT = 8080`),
  `core/inference.py:14,77`, and `core/inference_hybrid.py:34`
  (`port: int = 8080` default param).
- **Separately (same investigation, related but distinct):**
  `PLANNER_MODEL_PATH`/`PLANND_SERVER_PORT` are defined in
  `utils/config.py:233-239` but never read by any process-launching
  code anywhere in the repo (confirmed via grep) — the 1.5B planner
  server is evidently expected to be started manually by the user via a
  hand-typed shell command, completely disconnected from
  `utils/config.py`. `docs/configuration.md:155` also documents the
  wrong default model file for this (`~/models/qwen2.5-0.5b/...`) vs.
  what `utils/config.py:236` actually defaults to
  (`~/models/qwen2.5-coder-1.5b/...`), and `install.sh:36,41` builds/
  downloads yet another value independently. This is very likely the
  direct cause of the user's "had to update the model path in multiple
  locations" experience for the planner model specifically (the
  primary 7B model's path is properly centralized via `MODEL_PATH` in
  `utils/config.py`, imported consistently by `core/loader_v2.py`,
  `core/inference.py`, `core/lora_import.py`).
- **Cross-process coordination:** within one Python process,
  `get_loader()` is a true singleton (module-level,
  `core/loader_v2.py:417-422`) so one process can't double-spawn via
  `loader_v2` alone. But across processes (e.g. the daemon and a
  separately/directly-run `python3 main.py` CLI invocation, each with
  their own independent `ModelLoader` singleton), the only protection
  is the `_is_port_in_use()` HTTP probe — a TOCTOU race, not a lock. If
  both processes start near-simultaneously during the up-to-60s
  health-check window (`loader_v2.py:139` polls up to 60s), both could
  see port 8080 as free and both attempt to spawn. There is no
  flock/pidfile-based mutex dedicated to the model-server port itself
  (the daemon's own `fcntl.flock` at `core/daemon.py:55-93` only
  prevents daemon-vs-daemon double-start, not daemon-vs-CLI).
- **Impact/assessment:** this is a plausible, concrete contributing
  factor to the broader family of process-lifecycle bugs already
  tracked (NEW-5/NEW-6/NEW-9), not purely a maintainability nuisance —
  specifically via (a) the untracked, no-port-check
  `core/inference.py:_start_server()` fallback path, reachable in
  production, capable of spawning an unmanaged second `llama-server`
  with no cleanup hook, and (b) the TOCTOU race window in
  `_is_port_in_use()` when a daemon and a CLI process start close
  together. Not confirmed as the direct cause of any specific
  already-reproduced NEW-5/6/9 orphan (those were traced to a
  different, lower-level atfork/signal-timing mechanism, confirmed
  unrelated to this in the NEW-11 write-up above) — this is a separate,
  additional risk in the same problem family, not a re-explanation of
  the already-diagnosed bugs.
- **Not fixed here** — logging only, per CLAUDE.md rule 8. Fix
  directions for a future dedicated pass (do not scope as a task yet,
  just list as candidates):
  1. Quarantine or delete `core/inference.py`'s independent
     `_start_server()`/`Popen` launcher — route its fallback through
     `core.loader_v2.get_loader()` instead of building its own command.
  2. Add a single named `SERVER_PORT`/`PRIMARY_SERVER_PORT` constant in
     `utils/config.py` that all three files (`loader_v2.py`,
     `inference.py`, `inference_hybrid.py`) import, instead of each
     hardcoding `8080` independently.
  3. Either wire `PLANNER_MODEL_PATH`/`PLANND_SERVER_PORT` into an
     actual launcher (so the 1.5B planner starts the same way the 7B
     model does) or remove/clearly-mark them as unused-today in
     `utils/config.py` and `docs/configuration.md`, and fix
     `docs/configuration.md:155`'s wrong default to match
     `utils/config.py:236`.
  4. Consider replacing/augmenting the HTTP port-probe
     (`_is_port_in_use()`) with a real cross-process lock (e.g. an
     flock'd `.pid`/`.lock` file per port) before spawning, to close the
     daemon-vs-CLI TOCTOU race.

## Found during Round 8 (NEW-6) live-verification pass, 2026-07-30 — NOT fixed, logged only

### [NEW-9] Residual, intermittent atfork/fork-window race can silently bypass the `try/except (KeyboardInterrupt, SystemExit)` model-load guard at all four sites (`repl()`, `args.init`, `args.tdd`, `args.fix`)
- **Status: STILL OPEN — Round 9 fix attempt (commit `1a1c0b7`) did NOT
  close this**, corrected 2026-07-30 per CLAUDE.md rule 6 after Round 9's
  own live-verification. `1a1c0b7` wrapped only the `subprocess.Popen(...)`
  call itself in `signal.pthread_sigmask(SIG_BLOCK/SIG_UNBLOCK)`, but
  live-verifier's repeated-attempt testing (16 valid independent attempts)
  reproduced the identical orphan in 3/16 (~19%), statistically
  indistinguishable from the original ~1-in-4 rate. Root cause of the
  fix's failure: the vulnerable window starts far earlier than the
  `Popen()` call — the `"Starting llama-server..."` log line fires at
  `core/loader_v2.py` line ~55, roughly 70 lines before the
  `pthread_sigmask(SIG_BLOCK)` call at line ~125 (command-list
  construction, mmap/mlock config lookup, log-file open all happen in
  between, unguarded). A `SIGINT` landing in that gap is delivered
  normally by the OS before the mask is ever applied, arms the
  interpreter's pending-interrupt flag, and can still surface inside the
  forked child's atfork callback exactly as before — the mask was simply
  placed too late to cover the real window. Verbatim reproduction
  (attempt a9 of 16): `Exception ignored in atfork callback` printed,
  `"Interrupted during model load, cleaning up..."` never printed, and
  `ps -p 14123 -o pid,ppid,pgid,etimes,cmd` confirmed a real orphan
  (`14123  1  14123  13  .../llama-server ...`). Do not consider `1a1c0b7`
  a completed fix — it is a partial, insufficient mitigation left in
  place (harmless, narrows nothing meaningfully, but not the fix). This
  needs a fresh scoping pass that moves the block point up to cover the
  full window from the log line (or earlier) through the `Popen()` call,
  not just the call itself.
- **Status: STILL OPEN — Round 10 fix attempt (commit `2aaabb1`)
  substantially reduced but did NOT fully close this**, corrected
  2026-07-30 per CLAUDE.md rule 6 after Round 10's own live-verification.
  `2aaabb1` widened the masked region identified as missing in Round 9's
  correction above — moving `signal.pthread_sigmask(SIG_BLOCK)` up to
  cover the full window from at/before `"Starting llama-server..."`
  through the `Popen()` call, not just the call itself.
  live-verifier's repeated-attempt testing (22 valid, independent
  attempts, `pty.fork()`-based harness, tracked child PID, real
  `os.kill(pid, SIGINT)`, delay varied 0.0s-0.3s; 4 additional attempts
  were invalid/contaminated by leftover orphans from earlier failures and
  excluded from the count) found **20/22 clean at delays ≥0.03s, but 2/22
  FAILED — both at delay=0.0s** (`SIGINT` sent the instant `"Starting
  llama-server..."` was observed), reproducing the identical
  `atfork`-swallowed-`KeyboardInterrupt` orphan symptom. This is a real,
  substantial improvement (2/22 ≈ 9%, clustered only at the absolute
  earliest timing, vs. Round 9's 3/16 ≈ 19% spread across the whole
  range, vs. the original ~1-in-4 to ~1-in-5 rate) — but it is **not**
  zero, and this is now the **second consecutive fix attempt on NEW-9 to
  be live-verified as incomplete**. Verbatim reproduction (attempt a01 of
  22):
  ```
  ℹ  Starting llama-server...
  ℹ  7B model: mmap=enabled, mlock=disabled
  Exception ignored in atfork callback <function _afterFork at 0x764aa8b530>:
  Traceback (most recent call last):
    File ".../python3.14/logging/__init__.py", line 245, in _afterFork
      def _afterFork():
  KeyboardInterrupt:
  ℹ  llama-server PID: 9141, logging to /data/data/com.termux/files/home/.codeyOS/llama-server.log
  ✓  llama-server started on port 8080
  ✓  Loaded model (qwen2.5-coder-7b-instruct-q4_k_m.gguf)
  ...
  You>
  ```
  The `KeyboardInterrupt` was silently swallowed by CPython's atfork
  machinery, never reached `main.py`'s `except (KeyboardInterrupt,
  SystemExit)` guard. The REPL continued as if uninterrupted, loaded the
  model fully, sat at the `You>` prompt. Post-check: `ps` showed PID
  9141, `llama-server`, PPID 1 (orphaned/reparented to init), 224s
  elapsed, 1.87GB RSS. Killed via `kill -TERM 9141` (exact tracked PID),
  confirmed reaped, RAM recovered. A second, independent attempt (a24)
  reproduced an identical failure signature (same `atfork` traceback),
  PID 15693, PPID 1, 128s elapsed, 914MB RSS — also killed by tracked PID
  and confirmed reaped. **Root cause observation (not yet a confirmed fix
  path):** both failures show `KeyboardInterrupt` raised *inside*
  `logging._afterFork`, an `os.register_at_fork()` callback invoked as
  part of `subprocess.Popen()`'s internal `fork()` — even though
  `signal.pthread_sigmask(SIG_BLOCK, {SIGINT})` is active for the entire
  widened region at the time of the interrupt. The mask should be
  preventing `SIGINT` from reaching Python's normal signal-check point at
  all, yet this specific atfork-callback code path still independently
  observes/raises the interrupt. This suggests the remaining failure mode
  is deeper than "the guarded window was too narrow" (which explained
  Round 9's failure and which Round 10 correctly fixed for the vast
  majority of the window) — possible explanations not yet confirmed
  include a Termux/Android-specific signal-delivery quirk, or some
  property of CPython's atfork-callback execution that isn't fully
  governed by `pthread_sigmask` in this environment. **`2aaabb1` is not
  being reverted** — it is a genuine, verified improvement, not a
  regression — but it must not be described anywhere as having resolved
  NEW-9. A third fix attempt should not simply repeat the "widen the
  masked window further" approach without new information: the Round
  9→Round 10 pattern (progressively widening the masked region) has
  shown diminishing but nonzero returns and does not appear to be
  converging to zero through mask-widening alone. Per CLAUDE.md's
  escalation rules, this is being brought to Ish directly for a decision
  on how to proceed — no new fix attempt has been scoped here.
- **Confidence: Confirmed** (directly reproduced live during Round 8's
  live-verification of the NEW-6 fix — a real orphaned `llama-server`
  process was caught, root-caused by reading CPython's `subprocess.Popen`/
  `os.fork()` internals, not inferred). Reconfirmed as still-open via
  Round 9's 16-attempt live-verification above.
- **Where found:** Round 8 live-verifier's `--init` testing (attempt 1 of
  4 total attempts across all four guarded call sites). Hit rate observed:
  1-in-4 across this round's testing.
- **Root cause:** `core/loader_v2.py`'s `LlamaServer.start()`
  (~lines 116-130) calls `subprocess.Popen(...)`, which internally performs
  `os.fork()`. If a `SIGINT` arrives in the narrow window during that
  internal fork, CPython's own atfork exception-handling machinery
  (specifically observed here interacting with `logging`'s
  `_afterFork` callback) can silently discard the resulting
  `KeyboardInterrupt` before it ever propagates up to the caller's
  `try/except (KeyboardInterrupt, SystemExit)` guard. The guard code
  itself is not wrong — it simply never gets invoked, because the
  exception is swallowed one layer below it, inside the standard library.
  This means the guard pattern introduced by NEW-5's fix (`eed29dc`) and
  extended by NEW-6's fix (`435c120`) has a real, narrow gap that no
  amount of correct `try/except` placement at the call site can close on
  its own.
- **Affected call sites — all four that share this guard pattern:**
  - `repl()`, `main.py` (NEW-5's original fix, `eed29dc`)
  - `args.init`, `main.py` (NEW-6's fix, `435c120`)
  - `args.tdd`, `main.py` (NEW-6's fix, `435c120`)
  - `args.fix`, `main.py` (NEW-6's fix, `435c120`)
- **Reproduction evidence (verbatim, `--init` attempt 1, Round 8):**
  ```
  CHILD_PID=27122
  ℹ  Starting llama-server...
  >>> SENDING SIGINT to 27122 at t=0.18s
  Exception ignored in atfork callback <function _afterFork at 0x73f8ff7530>:
  Traceback (most recent call last):
    File ".../logging/__init__.py", line 245, in _afterFork
  KeyboardInterrupt:
  ℹ  llama-server PID: 27124, logging to /data/data/com.termux/files/home/.codeyOS/llama-server.log
  >>> CHILD STILL RUNNING after wait loop
  ```
  Post-check: `ps -p 27124 -o pid,ppid,pgid,etimes,cmd` showed
  `27124  1  27124  62  .../llama-server -m ...` — a real orphan (PPID=1,
  reparented). The expected "Interrupted during model load, cleaning
  up..." message never printed — the guard's `try/except` never fired.
  live-verifier killed it directly by tracked PID (`kill -TERM 27124`),
  confirmed reaped, RAM recovered. All 3 subsequent attempts across the
  other sites (`--init` rerun, `--tdd`, `--fix`) came back clean — guard
  fired correctly each time.
- **Impact:** in this narrow, timing-dependent window (hit 1-in-4 across
  Round 8's own testing), `llama-server` can still be orphaned
  indefinitely on `SIGINT` during model load, at any of the four call
  sites — the same underlying failure mode NEW-5/NEW-6 were meant to
  close, just a much narrower slice of it than either fix targeted.
- **Not fixed here — deliberately out of scope for Round 8**, whose scope
  was limited to NEW-6's three sibling call sites (same fix, same pattern
  as NEW-5 already had). This is a different, deeper problem in the
  shared `core/loader_v2.py` Popen/fork mechanism itself, not something
  the existing guard pattern can be fixed to catch without a different
  approach.
- **Fix direction (not scoped, needs its own dedicated pass):** the
  guard cannot be relocated to "wrap the fork itself" in the naive sense,
  since the swallowing happens inside CPython/stdlib internals during
  `os.fork()`, not in caller-reachable code. Plausible directions for a
  future scoping pass to evaluate (none decided here):
  - Investigate whether disabling/deferring the `logging` module's atfork
    handler (the specific callback seen swallowing the exception in the
    reproduction above) around the `Popen()` call changes the behavior.
  - Consider an interrupt-safe mechanism that doesn't rely on
    `KeyboardInterrupt` propagation through the fork window at all — e.g.
    a signal handler installed before the `Popen()` call that sets a flag
    checked immediately after, rather than depending on the exception
    reaching a `try/except` above the call.
  - Confirm whether this is Termux/Android-`libc`-specific or general
    CPython behavior on any Linux target, since that affects how
    aggressively to prioritize a fix.
  - Any fix needs code-reviewer's explicit approval before commit per
    CLAUDE.md rule 4 (process-lifecycle/kill-logic changes) — this
    touches the exact category that has produced this project's worst
    bugs before.
- **Queue position:** discovered mid-Round-8, not part of the original
  four-item punch list (NEW-3/1/5/2) or the two incidental follow-ups
  already queued (NEW-4, NEW-7). Recommend asking Ish whether this should
  be prioritized ahead of NEW-4/NEW-7 in the queue (it's a RAM-crash-class
  process-lifecycle gap, arguably higher severity) or simply appended
  after them — not decided unilaterally here.

## Found during Round 2 (C-2) live-verification pass, 2026-07-29 — NOT fixed, logged only

### [NEW-4] `gui/start.sh` unconditionally chains into `main.py`, forcing a full 7B model load just to view the dashboard
- **Status: RESOLVED (2026-07-29, Round 3, commit `ea954eb`).** This
  entry was never marked Resolved despite the fix landing back in
  Round 3 — corrected 2026-07-30. `gui/start.sh` gained an opt-in
  `--dashboard-only` flag (or `CODEY_GUI_DASHBOARD_ONLY=1` env var)
  that skips `main.py`'s eager 7B model load entirely and just serves
  the GUI/dashboard, waiting on the GUI server's own PID instead.
  Default (no-flag) behavior is unchanged — still chains into
  `main.py` — matching the original suggested direction below (an
  opt-in decoupling, not a default-behavior change). code-reviewer
  approved (one non-blocking suggestion: last-positional-arg-wins in
  the new arg-parsing loop, latent/no current caller affected). Fully
  live-verified: default path showed a real model-load cycle
  (`free -h` 8.3Gi used during load → 3.1Gi after teardown);
  `--dashboard-only` path confirmed via `pgrep` that no `main.py` or
  `llama-server` process ever started, and `curl` to the dashboard
  endpoint returned 200. See `PROJECT_LOG.md`'s 2026-07-29 Round 3
  entry for full verbatim evidence. (This round's live-verification
  also surfaced the original NEW-5 finding as a side observation,
  since separately resolved.)
- **Confidence: Confirmed** (directly observed live during the C-2
  live-verification pass, not inferred).
- **Where found:** live-verifier's real launch of `gui/start.sh` (the
  actual daemon-managed GUI startup path, not a scratch instance) while
  confirming C-2's GUI-security fixes end-to-end.
- **Finding:** `gui/start.sh` unconditionally chains into `main.py` after
  starting `gui/server.py`, and `main.py` eagerly loads the 7B model with
  zero user interaction required. There is no path to bring up the GUI
  server/dashboard alone without also paying the full 7B model-load cost
  — observed directly: launching via `gui/start.sh` triggered a real
  `llama-server` 7B load (PID 25675) before the dashboard was usable.
- **Impact:** a user who only wants to check the dashboard (RAM/CPU/temp,
  task status, etc.) via the GUI has no way to do so without incurring a
  full model load, which on this device is a meaningful RAM/time cost and
  runs against this project's RAM-discipline concerns (rule 2 in
  `CLAUDE.md`).
- **Suggested direction (not applied — out of scope for the C-2
  live-verification task that found it):** decouple `gui/server.py`'s
  dashboard-only capabilities (which read from `core/dashboard_data.py`,
  not the model) from `main.py`'s model-loading REPL, so `gui/start.sh`
  can optionally start just the dashboard server without also spawning
  `main.py`. Needs its own scoped task — not a security issue, a
  resource-cost/UX one.

## Found during Round 2 (C-2 GUI security) sub-task 3/3, 2026-07-29 — RESOLVED in Round 4, commit `efe9f5c`

### [NEW-3] GUI session token may leak into access logs if logging is ever configured for `gui/server.py`
- **Status: RESOLVED (2026-07-29, commit `efe9f5c`).** `gui/server.py`'s
  `web.run_app()` call now passes `access_log=None`, disabling aiohttp's
  default `AccessLogger` outright rather than relying on the current
  absence of a configured `logging` handler to keep the token dormant.
  code-reviewer approved: confirmed `access_log` is a genuine documented
  `aiohttp` kwarg (aiohttp 3.14.3 installed) and verified no other log
  call site in `gui/server.py` could leak the token. No live-verification
  performed for this fix specifically — scoped as a negative/absence
  assertion with no new live-session behavior to exercise, already
  covered by the prior Round 2 (C-2) full live-verification of normal GUI
  start (see `PROJECT_LOG.md`). Original finding detail preserved below.
- **Confidence: Suspected** (dormant today, plausible future trigger; not
  verified as currently reachable).
- **Where found:** code-reviewer's review of the C-2 sub-task 3 session-token
  commit (`1198ba1`).
- **Location:** `gui/server.py`, `web.run_app()` call (entry point, ~line 300).
- **Finding:** `web.run_app(make_app(), host=HOST, port=PORT, print=lambda
  *_: None)` is called without `access_log=None`, so aiohttp's default
  `AccessLogger` remains active and logs the full request line — including
  the `?token=<SESSION_TOKEN>` query string on `/ws` upgrade requests — at
  INFO level via Python's `logging` module.
- **Why not currently exploitable:** nothing in this repo calls
  `logging.basicConfig()` (or otherwise configures a handler) for the GUI
  process, and `gui/start.sh` backgrounds `python gui/server.py &` without
  redirecting stdout/stderr to a persistent file. Python's `logging`
  module's default `lastResort` handler only surfaces WARNING+ to stderr, so
  the INFO-level access log line is silently dropped today — the token does
  not currently land in any file or terminal output.
- **Why it's still worth tracking:** this is fragile, not fixed. If a future
  change adds `logging.basicConfig()` anywhere in the process (common when
  wiring up broader observability), or if `gui/start.sh` (or any future
  daemon supervisor) redirects the GUI subprocess's stdout/stderr to a log
  file, the session token starts landing in a readable log with no code
  change to `gui/server.py` itself required to trigger it.
- **Suggested fix (not applied — out of scope for this sub-task):** either
  pass `access_log=None` to `web.run_app()`, or move the token off the query
  string (header on upgrade, or first-message-after-connect) so it's not
  part of what any access logger would capture by default.

## Found during H-4 self-race / C-1 short-prompt follow-up task, 2026-07-29 — NOT fixed, logged only

### [NEW-2] `patch_file` with `old_str: ""` silently no-ops instead of inserting or erroring
- **Status: Resolved (2026-07-29/30, Round 7, commit `55e408c`).**
  `core/agent.py`'s fallthrough branch (~line 1831+) now logs and
  transcribes an explicit `[EDIT NOT APPLIED] <tool> on <path> failed
  after retries and escalation were exhausted — no file was modified.`
  marker when a `write_file`/`patch_file`/`append_file` call is still
  in an error state after both retry and peer-CLI escalation are
  exhausted, replacing the previous silent fallthrough to a generic
  "Next action or final answer" turn. code-reviewer independently
  traced `last_tool_result` freshness, ran the targeted test (`1 passed
  in 0.19s`) and the full suite (`321 passed, 1 pre-existing unrelated
  failure`), approved with no Critical/Warning findings. **Code
  complete, code-reviewer approved — not live-verified against the
  real model post-fix** (the pre-fix reproduction below was live; the
  post-fix confirmation is static/control-flow analysis + mocked
  tests, judged sufficient for this logging/control-flow change per
  Ground Rule 4/7). See `PROJECT_LOG.md` 2026-07-30 Round 7 entry for
  full detail. `NEW_ISSUES.md` [NEW-7] (the underlying planner
  behavior of synthesizing whole duplicate functions instead of
  targeted patches) remains open, unscoped, tracked separately.
- **Confidence: Confirmed** (directly observed, not inferred).
- **Where found:** Live verification of the C-1 short-QA-prompt fix. In a
  single warm `python3 main.py --no-resume` session, after two QA turns
  ("hello", "what can you do?"), a real coding request was sent: "add a
  docstring to the `shutdown` function in `main.py`". This correctly took
  the full/non-lightweight path (`main.py` loaded into context,
  `[Recursive] Draft (1/2)` → `[Recursive] Review (2/2)` → "Accepted —
  quality 8/10") and the model emitted a `patch_file` tool call:
  `{"name": "patch_file", "args": {"path": "main.py", "old_str": "", "new_str": "def shutdown():\n    \"\"\"...docstring...\"\"\"\n    print('Shutting down...')\n    # Add your shutdown logic here."}}`.
- **Evidence it no-op'd:** Immediately after acceptance, the harness
  logged `⚠ Malformed tool call — JSON parse failed, retrying`, which
  triggered a second, near-identical `patch_file` call with the same
  `old_str: ""`. No error or success message about the patch's actual
  effect was ever printed before the next `You>` prompt appeared.
  `git diff main.py` afterward showed **zero changes** — `shutdown()` at
  line 125 has no docstring, unmodified from HEAD. The model's tool call
  ran (or was retried) but never touched the file.
- **Likely root cause (not yet verified against `tools/patch_tools.py`):**
  the model appears to be using `old_str: ""` to mean "insert without
  matching," but `patch_file`'s matching logic likely treats an empty
  `old_str` as either "match nothing" (silent no-op) or a bad match
  that gets swallowed rather than surfaced as `[PATCH_FAILED]` to the
  user. Note `tests/test_patch.py`'s pre-existing failure (further down
  this file) is about the *format* of the failure message
  (`[PATCH_FAILED]` vs `[ERROR] String not found`) — this is a different,
  possibly related but unconfirmed, issue about a failure not being
  surfaced at all for the empty-`old_str` case.
- **Impact:** A user asking for a simple, common edit ("add a docstring
  to X") can get a "quality 8/10, accepted" response with an emitted tool
  call that looks successful in the transcript, while the file is
  actually untouched — a silent-failure UX gap, not a crash.
- **Not fixed here:** out of scope for the H-4/C-1 task that surfaced it
  (this task touched `core/daemon.py`, `prompts/system_prompt.py`, and
  `prompts/layered_prompt.py` only). Needs a dedicated look at
  `tools/patch_tools.py`'s handling of empty/non-matching `old_str`
  before deciding whether the fix is in the tool implementation or in
  prompting the model to never emit an empty `old_str`.
- **Correction (2026-07-29, Round 3 scoping pass) — the hypothesized
  root cause above does not hold up; downgrading per CLAUDE.md rule 6.**
  Read `tools/patch_tools.py:19-22` directly: an empty/non-string
  `old_str` is already explicitly rejected —
  `if not old_str or not isinstance(old_str, str): return "[ERROR]
  Invalid old_str: empty or not a string"` — and `git log --follow -p`
  shows this check has existed since commit `8ab96e1` (Jun 13 2026), well
  before this session. So `tool_patch_file` itself does **not**
  silently no-op on `old_str: ""` — it returns a clear, explicit error
  string. The originally-suspected fix location (`patch_tools.py`'s
  matching logic) is not where the bug is.
  - **Re-reading the original transcript evidence with this in mind:**
    the "malformed tool call — JSON parse failed" warning fired
    *before* any tool executed, meaning `tool_patch_file` was likely
    never actually called on the first attempt (the JSON never parsed,
    probably due to unescaped literal newlines inside the multi-line
    docstring in `new_str`, which breaks strict JSON parsing). The
    retry then produced a second near-identical malformed call.
  - **New, more likely mechanism (unconfirmed, needs live reproduction
    to nail down):** `core/agent.py:1434` sets `max_retries = 1`, so
    the malformed-tool-call retry path (`core/agent.py:1537-1553`) only
    gets one retry attempt. If the second attempt *also* fails to parse,
    `auto_retries >= max_retries` and the code falls through past the
    `if tool_dict:` block entirely (nothing between lines ~1553 and
    ~1843 re-enters it for a null `tool_dict` after retries are
    exhausted) to `history.append(...); return response, history`
    around `core/agent.py:1869-1873` — i.e. the raw, still-malformed
    model text becomes the "final answer" with no explicit surfacing of
    "the patch never applied." This would explain a silent-looking
    failure without any code in `patch_tools.py` being at fault.
  - **Status:** downgraded from Confirmed-root-cause to Suspected — the
    silent-no-op *symptom* is still Confirmed (git diff showed zero
    change), but the mechanism is now believed to be in
    `core/agent.py`'s malformed-JSON-retry exhaustion path, not
    `tools/patch_tools.py`. Needs a fresh live reproduction (single warm
    session, ask for a multi-line docstring/edit likely to trigger an
    unescaped-newline JSON break) with the raw model output captured
    verbatim before scoping an implementer task — not ready to hand off
    yet.

- **Correction (2026-07-30, live-verifier reproduction with real 7B
  model) — the Round 3 malformed-JSON hypothesis above does not hold up
  either; correcting per CLAUDE.md rule 6, root cause now Confirmed by
  direct live reproduction.**
  - **What Round 3 believed:** that `parse_tool_call()` failed to parse
    the model's `<tool>` JSON (a JSON-parse failure), and that this made
    the user see raw broken text that "looks like" a false claim of
    success.
  - **What was actually observed live (single warm session, prompt "add
    a docstring to the shutdown function in main.py", `[Recursive]`
    planner path):** the model's JSON was **well-formed both times** —
    `parse_tool_call()` succeeds and `tool_dict` is truthy on both
    attempts. There is no JSON-parse failure anywhere in this trace. The
    call was `{"name": "patch_file", "args": {"path": "main.py",
    "old_str": "", "new_str": "<a whole duplicate shutdown() function>"}}`.
  - **Confirmed actual mechanism, traced end-to-end:**
    1. `execute_tool(tool_dict)` calls `tool_patch_file(path, old_str="",
       new_str=...)`. `tools/patch_tools.py:21-22`'s empty-`old_str`
       guard (present since commit `8ab96e1`, as Round 3 found) fires
       and returns the string `"[ERROR] Invalid old_str: empty or not a
       string"`. This is a normal, working rejection — not a no-op and
       not swallowed.
    2. `core/agent.py:480-488` (`is_error()`) sees the `[ERROR]` prefix
       and returns `True`.
    3. First attempt: `core/agent.py:1700-1702` — `auto_retries(0) <
       max_retries(1)` (set at `core/agent.py:1434-1435`) — increments
       `auto_retries` to 1 and prints exactly the observed `⚠ Error
       detected — auto-retry 1/1`, then appends the raw `[ERROR]` text
       to the conversation and `continue`s. This matches what
       live-verifier saw.
    4. The model retries and emits the **identical** `old_str: ""` call
       again (this is the actual planner/prompting gap — see the new
       NEW-7-adjacent note below). `tool_patch_file` rejects it
       identically.
    5. Second attempt: `auto_retries(1) >= max_retries(1)`, so
       `core/agent.py:1760-1787`'s `elif` branch fires instead of the
       retry branch: it calls `core/peer_cli.py:303 escalate()`. On this
       device (no peer CLI configured / user did not opt in), `escalate()`
       returns `None` (`core/peer_cli.py:318-320` prints its own "No peer
       CLIs found" warning, or `mgr.confirm()` returns `False` and
       `core/peer_cli.py:333-335` prints "Peer CLI escalation skipped." —
       either way this is a *different* warning than the retry one, which
       is why no second "Error detected — auto-retry" line appeared).
    6. Falling through the `elif` (comment at `core/agent.py:1787`: "else:
       user skipped escalation, fall through to normal handling") reaches
       `core/agent.py:1788` unconditionally, then the `name ==
       "write_file"` check at `1792` is `False` for `patch_file`, so
       control lands in the `else` branch at `core/agent.py:1830-1841`:
       it appends `"Tool result: [ERROR] Invalid old_str...\nNext action
       or final answer:"` to `messages` and `continue`s the main loop —
       i.e. the model is invoked a **third** time.
    7. This third call is where the model, now holding the `[ERROR]`
       text as context, gives up on re-emitting a tool call and instead
       replies with plain text: *"Please provide the correct content for
       the `old_str` argument in the patch_file call."* This is an
       honest, if easy-to-miss, clarification request — **not** a false
       claim of success, contrary to Round 1's original framing.
    8. Because this third response contains no `<tool>` block,
       `tool_dict` is falsy, `is_hallucination()` doesn't trigger (the
       response isn't claiming a file/run happened), so execution falls
       through to `core/agent.py:1869-1873` and returns this text as an
       ordinary final answer — with no distinct ERROR-level surfacing
       anywhere in this whole path that an edit was attempted twice and
       both times rejected. This is the actual "silent" part of
       "silent no-op": not silent in the sense of "no error was ever
       produced" (two clear `[ERROR]` strings were produced, correctly,
       by `patch_tools.py`), but silent in the sense that **neither
       `[ERROR]` was ever escalated past ordinary conversational turns
       into something the user is guaranteed to notice** before the
       session moves on.
  - **Confirmed via:** `git diff main.py` after the session was
    completely empty; `main.py:125 def shutdown()` unmodified from HEAD.
  - **Status: Confirmed root cause** (upgraded from Suspected). The
    off-by-one retry-budget gating logic from Round 3's hypothesis
    (`max_retries = 1` meaning only one retry is allowed) was correct in
    spirit; what was wrong was believing the trigger was a JSON-parse
    failure and that the user gets a "looks like success" message. The
    actual trigger is a **failed tool-application** (empty `old_str`
    rejected by `patch_tools.py`'s existing, correct guard), and the
    actual user-visible result is an honest clarification question with
    no explicit "your edit did not apply" error surfaced.
  - **Scoped fix (handed to implementer):** when the tool-call/retry loop
    exhausts retries on a `write_file`/`patch_file`/`append_file` call
    that never produced a successful result (i.e. `is_error()` was still
    `True` on the last attempt and peer-CLI escalation did not resolve
    it), `core/agent.py`'s fallthrough at the `else` branch around
    `core/agent.py:1830-1841` should surface a clear, distinct, ERROR-
    level message/log stating that an edit was attempted and did **not**
    apply, rather than silently reusing the generic "Tool result: ...
    Next action or final answer:" framing that lets the loop end on an
    ordinary-looking clarification question. Scope is intentionally
    limited to this surfacing gap — it does **not** include fixing why
    the `[Recursive]` planner keeps synthesizing `old_str: ""` with a
    whole duplicate function instead of a targeted edit; that is tracked
    separately as NEW-7 below.

### [NEW-7] `[Recursive]` planner path may be prompted to synthesize whole functions rather than targeted patches (Suspected, not yet fixed)
- **Confidence: Suspected.** Observed once, in the same live session that
  reproduced NEW-2 above; not yet isolated from NEW-2's retry-surfacing
  gap or confirmed across multiple prompts.
- **Where found:** Same transcript as NEW-2. The `[Recursive] Draft` /
  `[Recursive] Review (2/2)` / "Accepted — quality 8/10" path
  (`core/agent.py:1462-1520`, backed by `core/recursive.py:326
  recursive_infer()`) both times produced `old_str: ""` with `new_str`
  containing a **complete duplicate `shutdown()` function** (docstring +
  body), rather than a minimal patch to the real function at
  `main.py:125`. `core/recursive.py`'s draft/critique/refine loop
  (read `core/recursive.py:390-403`) re-invokes the same generic
  `infer()` on the same message history with critique feedback — there
  is no `patch_file`-specific prompt telling the model that `old_str`
  must match existing file content verbatim; the model appears to be
  treating "add a docstring" as "write a new function" instead of "find
  and edit the existing one."
- **Not investigated:** whether this is specific to the `[Recursive]`
  path or would also happen on the plain (non-recursive) path; whether
  it's specific to docstring-insertion requests; whether it happens
  consistently or was one draw from the model. Needs a dedicated
  scoping pass with multiple live reproductions before an implementer
  task is written — deliberately not bundled into NEW-2's fix.

## Found during Round 1 (C-1/H-1/H-4) fix task, 2026-07-29 — NOT fixed, logged only

### [NEW-1] `pytest tests/` spawns a real 7B `llama-server` and orphans it — matches audit finding L-6

- **Status: RESOLVED (commit `c65be95`), fully live-verified 2026-07-29.**
  live-verifier ran the full suite: `pytest tests/ -q` → **253 passed in
  0.43s** (previously ~42s, due to the hidden real 7B model load). No
  orphan `llama-server` process remained afterward, confirmed via
  `ps -eo pid,ppid,comm | grep llama` (not `pgrep -af`, which has a
  false-positive self-match issue in this shell environment — the
  wrapper's own command-line text matches the `llama` pattern). `free -h`
  was stable before/after (563Mi free → 816Mi free; swap unchanged at
  1.6Gi). Per Ground Rule 7, this closes the "code complete" →
  "fully live verified" gap left open after code-reviewer's approval,
  which had only re-run `tests/test_memory.py` in isolation, not the full
  suite.
- **Confidence: Confirmed (upgraded from Suspected, Round 5 diagnostic
  investigation, 2026-07-29).** The mechanism below was live-reproduced
  3+ times, including a decisive proof: catching the orphaned
  `llama-server`'s PPID pointing directly at the live pytest process
  itself, before OS reparenting to PID 1 had occurred.
- **Root cause:**
  `tests/test_memory.py::TestMemoryCompressSummary::test_compress_summary_handles_inference_failure`
  (lines ~351-361) calls `self.memory.compress_summary(long_history)`
  with **no mocking of inference at all**, despite its name and docstring
  ("compress_summary should return fresh turns when inference fails")
  implying it tests a failure/degraded path. Call chain: test →
  `core/memory_v2.py:600-627` `compress_summary()` unconditionally does
  `from core.inference_v2 import infer; ... compressed = infer(prompt,
  stream=False)` (line 619, wrapped in a bare `try/except Exception`,
  line 603/625, which is why the test still passes either way and never
  signaled the problem) → `core/inference_v2.py:65-94` `infer()` does
  `loader = get_loader(); if not loader.ensure_model(): ...` (lines
  92-94) — this `ensure_model()` call is the real model-load trigger,
  spawning an actual local 7B `llama-server` subprocess.
- **Evidence:**
  - A timestamped, verbose pytest log showed a 28-second gap (consistent
    with a real 7B model load) immediately before this specific test,
    versus ~5ms between every other adjacent test pair in the suite.
  - Live-reproduced 3+ times in Round 5.
  - Decisive proof: in one reproduction, the orphan `llama-server`'s PPID
    was caught pointing directly at the live pytest process ID before OS
    reparenting to PID 1 occurred (matches the two earlier PPID-1
    orphan observations logged below, which were seen only after
    reparenting had already happened).
  - Nothing in the test's setUp/tearDown (`tests/test_memory.py:335-340`,
    `reset_memory()` only) tracks or kills the spawned server, which is
    why it's left running/orphaned after the test session ends.
- **Original correlation evidence (Round 1, retained for record):** Ran
  `python3 -m pytest tests/ -q` (253/253 pass, no failures) inside one
  single shell command that also ran `free -h; pgrep -af llama-server`
  immediately after — that combined command's output showed a full 7B
  `llama-server` on port 8080 running with `PPID 1` (reparented/orphaned),
  no PID file anywhere (`~/.codeyOS/codeyOS.pid` doesn't exist), no daemon
  running. Reproduced in an earlier separate run too (different PID).
  Both times the process outlived the pytest run and had to be killed
  manually (`kill -TERM -<pid>`, scoped to that PID's process group) to
  recover RAM — that part (kill discipline, RAM recovery) is solid and
  verified both times via `free -h` before/after.
- **Impact:** a device crash occurred during the Round 1 session in which
  this was first observed, with RAM going from ~6.6 GB available to under
  200 MB free with 6+ GB in swap without any deliberate model-load
  action. Now that the mechanism is confirmed, this test is a real,
  reproducible RAM-crash contributor, not just a plausible one — every
  plain `pytest tests/` run loads a full 7B model and orphans the server.
- **Round 1 static investigation (superseded by Round 5, not
  retracted):** a targeted grep-level search
  (`grep -rn "llama-server\|LlamaServer\|subprocess\|Popen\|get_loader\|ensure_model" tests/*.py`)
  missed the mechanism because it only checked for direct spawn/loader
  calls inside `tests/*.py` files, not the indirect path through
  `core/memory_v2.py`'s `compress_summary()` (`infer(` is called from
  non-test code). That static approach could not have found this; the
  gap is closed by the Round 5 dynamic (timestamped-log + PPID-capture)
  investigation above.
- **Fix direction:** mock `core.inference_v2.infer` (or the loader it
  calls) in `test_compress_summary_handles_inference_failure` so the test
  actually exercises the inference-unavailable branch it claims to test,
  without triggering a real model load. See fix task scoped in
  `PROJECT_PLAN.md` / handed to implementer.

## Found during Round 7 (NEW-2) full-suite runs, 2026-07-29/30 — NOT fixed, logged only

### [NEW-8] `ccos/tests/test_ccos.py::test_sandbox` fails on this device, pre-existing and unrelated to Round 7's changes
- **Confidence: Confirmed** (independently reproduced twice — once by
  implementer, once by code-reviewer running the full suite separately
  — both during Round 7's NEW-2 work, in `ccos/tests/test_ccos.py`, a
  file untouched by Round 7's diff).
- **Where found:** `pytest tests/ ccos/... -q`-style full-suite runs
  during Round 7 (NEW-2). Result both times: `321 passed, 1 failed`,
  the failure being `ccos/tests/test_ccos.py::test_sandbox`.
- **Likely cause (from code-reviewer's read, not yet root-caused in
  depth):** an `echo` command sandbox-path-allowlist issue in
  `ccos/core/sandbox.py`'s handling of the test's shell-command case,
  not related to any file this round's diff touched.
- **Impact:** cosmetic to Round 7 (doesn't affect its correctness
  claim, since it's outside the diff), but represents a real,
  reproducible environment/test gap worth its own investigation.
- **Not fixed here:** out of scope for Round 7 (NEW-2), which only
  touched `core/agent.py` and added
  `tests/test_new2_edit_not_applied.py`. Needs a dedicated look at
  `ccos/core/sandbox.py`'s `echo`-command allowlist logic and
  `ccos/tests/test_ccos.py::test_sandbox`'s expectations before scoping
  a fix.

## Pre-existing Test Failures (Not Introduced by V3 Changes)

### test_hallucination.py (8 failures)
- **Issue**: Hallucination detection tests failing
- **Root Cause**: The `detect_hallucination()` function in `core/agent.py` doesn't detect past-tense claims like "I created", "I wrote", "I modified"
- **Impact**: Medium - hallucination detection is incomplete
- **Files**: `tests/test_hallucination.py`, `core/agent.py`
- **Recommendation**: Review and update hallucination detection patterns

### test_patch.py (1 failure)
- **Issue**: Patch error message format changed
- **Root Cause**: The patch tool now returns `[PATCH_FAILED]` instead of `[ERROR] String not found`
- **Impact**: Low - test expectation mismatch
- **Files**: `tests/test_patch.py`, `tools/patch_tools.py`
- **Recommendation**: Update test to match new error format

## Additional Security Hardening Needed

### 1. Command Injection via Filename (agent.py:863-865)
- **Status**: Partially addressed
- **Issue**: Shell commands built from LLM-generated filenames
- **Recommendation**: Add filename sanitization before shell command construction

### 2. Daemon Shell Allowlist Too Broad (task_executor.py:47-52)
- **Status**: Documented but not changed
- **Issue**: `python` and `pip` are allowed prefixes, enabling arbitrary code execution
- **Recommendation**: Consider restricting to specific script paths

### 3. Unix Socket Authentication (daemon.py)
- **Status**: Added peer UID check
- **Issue**: Current implementation relies on Unix domain socket permissions
- **Recommendation**: Consider adding token-based authentication for additional security

## Code Quality Improvements Needed

### 1. Unused Imports (129 F401 violations)
- **Files**: Multiple files throughout codebase
- **Recommendation**: Run `autoflake --remove-all-unused-imports` to clean up

### 2. Line Length Violations (1343 E501 violations)
- **Files**: Multiple files throughout codebase
- **Recommendation**: Consider using `black` formatter with line length 100

### 3. Comparison Style (74 E712 violations)
- **Files**: Multiple files
- **Recommendation**: Replace `== False` with `is False` or `not cond`

## Privacy Enhancements Needed

### 1. Network Request Logging
- **Status**: Not implemented
- **Issue**: No logging of network requests for audit trail
- **Recommendation**: Add optional network request logging

### 2. Data Retention Policy
- **Status**: Not implemented
- **Issue**: No automatic cleanup of old session data
- **Recommendation**: Add configurable data retention settings

## Testing Gaps

### 1. Integration Tests
- **Status**: Missing
- **Issue**: No integration tests for daemon mode
- **Recommendation**: Add integration tests for daemon startup/shutdown

### 2. Security Tests
- **Status**: Partial
- **Issue**: Shell injection tests exist, but no tests for path traversal
- **Recommendation**: Add path traversal tests for filesystem operations

## Documentation Updates Needed

### 1. Security Guide
- **Status**: Referenced in README but may need updates
- **Issue**: Security guide should document V3 security improvements
- **Recommendation**: Update `docs/security.md` with V3 changes

### 2. Privacy Policy
- **Status**: Missing
- **Issue**: No explicit privacy policy document
- **Recommendation**: Add `PRIVACY.md` documenting data handling practices
