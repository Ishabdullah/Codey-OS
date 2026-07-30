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
- **Status: Resolved (Round 13, commit `ab13a8d`).** code-reviewer
  approved. **Fully live-verified**, after two earlier live-verification
  attempts crashed Termux entirely at 7B model-load time (via the full
  `codeydOS start`, which also spawns a separate 1.5B "plannd" planner
  process) and a third attempt self-aborted proactively (per the
  live-verifier's own safety instructions) after observing swap climb
  from a ~1Gi baseline to 7.5-8.5Gi within ~40 seconds of steady-state
  startup with all three models running — see [NEW-14] below. The
  successful verification used a lighter, isolated harness instead:
  launching the daemon directly via `python3 main.py --daemon` (bypassing
  the `codeydOS` wrapper script that spawns the separate plannd process),
  running only the 7B primary + embed server. Baseline `free -h`:
  `used 3.3Gi / available 7.3Gi / swap 1.2Gi`. After daemon+7B+embed
  started (confirmed via `ps` — no plannd process present):
  `used 8.7Gi / available 1.8Gi / swap 1.8Gi`, stable, no aggressive
  climb. `curl http://127.0.0.1:8080/health` → `{"status":"ok"}`. Killed
  the tracked `llama-server` PID (921) directly via `kill -9 921` (not a
  name-pattern kill). Watchdog fired on schedule, literal daemon log:
  ```
  2026-07-30 01:11:41,418 - WARNING - 7B model server died — restarting...
  2026-07-30 01:11:41,444 - INFO - llama-server PID: 3034, logging to .../llama-server.log
  2026-07-30 01:11:51,056 - INFO - llama-server started on port 8080
  ```
  New PID (3034) confirmed distinct from the killed PID (921), fired at
  exactly the expected 30s-tick timing (4 ticks after the daemon started
  listening). A real inference call against the restarted server (not
  just a health check) returned `{"choices":[{"message":{"content":"PONG"}}]}`.
  Clean teardown via `SIGTERM` on the tracked daemon PID (845) — the
  daemon's own shutdown path stopped the model server and embed server
  itself (`Stopping model server... / Embed server stopped / Daemon
  socket stopped / Daemon stopped`). Final `ps` empty, PID file and
  socket file both removed. Final `free -h`:
  `used 2.9Gi / available 7.6Gi / swap 1.7Gi`. Peak swap this run: ~1.9Gi
  (vs. 7.5-8.5Gi in the full 3-model-stack attempt), confirming the
  separate plannd process was the dominant RAM/swap pressure source, not
  the daemon/watchdog code itself.
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

**Status: Resolved (Round 11, commit `59f4f69`).** Fixed exactly item 1
of the fix directions above: `core/inference.py`'s independent,
uncoordinated `_start_server()`/`Popen` launcher was removed and its
fallback path now delegates to `core.loader_v2.get_loader().ensure_model()`
— the canonical, port-checked, singleton-guarded launcher. code-reviewer
approved (and separately flagged a scope-adjacent regression, now logged
as [NEW-13] below). Live-verified: `free -h` before (`4.5Gi` used,
`2.9Gi` free) / after (`4.5Gi` used, `3.2Gi` free) showed no RAM leak;
starting the primary model then calling the fallback `core.inference.infer()`
in the same process produced no second `"Loading model:"`/`"Starting
llama-server..."`/`"llama-server PID:"` log line (i.e. no second `Popen()`
was invoked — `ensure_model()` short-circuited on its already-running
check) and the fallback call returned a real completion (`'Hello'`), not
an `[ERROR]` string; teardown used the single tracked PID. **Caveat:**
this is verified via log-line-absence + successful-completion +
clean-teardown evidence, not a literal multi-checkpoint `ps` snapshot —
the verifier's in-script `ps` capture had a filter bug (`ps`'s COMMAND
column truncates `llama-server` to `llama-serv`, so the substring match
never actually confirmed "exactly one process" via a literal `ps` table
at each checkpoint) and was not re-run, per the one-cycle-only RAM
discipline rule. Items 2-4 of the fix directions above (a single named
port constant, wiring the planner launcher, a real cross-process lock)
remain open, deferred to a future round.

### [NEW-13] Removing `core/inference.py`'s independent launcher (Round 11, NEW-12 fix, commit `59f4f69`) orphaned `ThermalManager`'s thread-reduction restart mechanism
- **Status: Resolved (Round 12, commit `0935cbd`).** Wired an equivalent
  restart-recommended check into `core/loader_v2.py`'s `ensure_model()`
  — when `ThermalManager.restart_recommended` is set, it now stops and
  restarts the running primary `llama-server` with the updated thread
  count and clears the flag. code-reviewer approved, with two
  non-blocking Warnings (no lock around the check-then-act sequence —
  not currently exploitable with only one call site; no unit test
  coverage of the new branch). **Fully live-verified:** started the
  primary model (PID 14619), forced `restart_recommended = True`,
  called `ensure_model()` again in the same process — confirmed a real
  restart (not a short-circuit): PID changed 14619 → 14800, old PID
  gone (`ps -p 14619` returncode 1), the flag correctly cleared
  afterward, a real inference call issued post-restart returned `'OK'`
  (not an error string), and clean teardown (`ps -p 14800` returncode 1
  after `unload()`). Verified via exact-PID `ps -p <pid>` checks rather
  than a `comm`-substring grep, since Termux's `ps` truncates `COMMAND`
  to `llama-serv` and would false-negative a `"llama-server"`
  substring match (environmental wrinkle, not a code defect).
  `free -h` before (`4.9Gi` used, `2.0Gi` free) / after (`3.3Gi` used,
  `5.6Gi` free) showed full RAM recovery, no leak. An unrelated test
  artifact (the inference call's side-effect embed server, PID 15580)
  was cleaned up by its own tracked PID, not a name-pattern kill.
- **Confidence: Confirmed** (found by code-reviewer during Round 11's
  NEW-12 review, verified via repo-wide grep, not inferred).
- **Where:** `core/thermal.py`'s `ThermalManager` class sets
  `self.restart_recommended = True` when `_reduce_threads()` fires
  (sustained inference triggers a thread-count reduction to manage
  device heat). The class's own comment states this flag exists so that
  "inference.py checks this and restarts llama-server with the updated
  thread count on next call." Before Round 11, `core/inference.py`'s
  `_start_server()` was the ONLY consumer of `restart_recommended`
  anywhere in the repo (confirmed via repo-wide grep for
  `restart_recommended`/`ThermalManager`/`get_thermal_manager`) — it
  checked the flag, terminated the old `_server_proc`, and restarted
  `llama-server` with the reduced thread count.
- **What changed:** Round 11's NEW-12 fix (commit `59f4f69`) removed
  `core/inference.py`'s independent `_start_server()` entirely (it was
  an uncoordinated, port-check-free llama-server launcher, correctly
  removed for that reason) and replaced it with a delegation to
  `core.loader_v2.get_loader().ensure_model()`. `core/loader_v2.py`'s
  launcher has no equivalent thermal-restart check anywhere in its own
  code path — it was never wired up there, since `core/inference.py`'s
  fallback path was thermal.py's only consumer.
- **Impact:** `ThermalManager` still detects sustained inference, still
  warns, and still reduces `MODEL_CONFIG["n_threads"]` in memory — but
  the actual server restart that was supposed to apply the new
  (reduced) thread count to the already-running `llama-server` process
  no longer fires from anywhere. This silently breaks the device-heat
  mitigation `core/thermal.py`'s own module docstring advertises
  (reducing threads after sustained inference to prevent thermal
  throttling on this mobile device).
- **Not fixed here** — logging only, per CLAUDE.md rule 8 (found outside
  NEW-12's stated scope during its review, correctly not silently fixed
  nor silently dropped). This is a real, if narrow, functional
  regression, not just a maintainability note — flag it as Confirmed,
  not Suspected.
- Fix direction for a future dedicated pass (not scoped here): wire an
  equivalent restart-recommended check into `core/loader_v2.py`'s
  `ModelLoader`/`LlamaServer` (the now-canonical launcher), likely
  inside `ensure_model()` or a periodic check point, so the mitigation
  applies regardless of which code path (primary or fallback) is
  currently in use. Needs its own scoping pass to decide exactly where
  the check belongs given `loader_v2.py`'s different structure (e.g.
  the NEW-9-hardened `pthread_sigmask` block around `Popen` — any
  restart logic must not interfere with that).

## Found during Round 13 (NEW-11) live-verification, 2026-07-30 — NOT fixed, logged only (observational)

### [NEW-14] Full `codeydOS start` (daemon + 7B + 1.5B plannd + embed server, all three models concurrently) pushes this device into severe swap pressure within seconds, even under normal conditions
- **Confidence: Confirmed** (directly observed, and consistent with two
  earlier Termux crashes at model-load time before this pattern was
  understood).
- **Where observed:** during Round 13 (NEW-11) live-verification. The
  first two live-verification attempts, both using the full `codeydOS
  start` wrapper (which launches the daemon plus the 7B primary model,
  the separate 1.5B "plannd" planner process, and the embed server, all
  concurrently), crashed Termux entirely, apparently right at 7B
  model-load time. A third attempt, same full stack, did not crash but
  self-aborted proactively per the live-verifier's own safety
  instructions after observing swap climb from a ~1Gi baseline to
  7.5-8.5Gi used within ~40 seconds of steady-state daemon startup —
  well before the actual kill/restart test began. Verbatim readings:
  `check 1: used 9.0Gi available 1.5Gi swap 4.6Gi` →
  `check 2: used 9.0Gi available 1.5Gi swap 7.1Gi` → settled around
  `swap 7.5Gi`. The device stayed responsive only because the test
  aborted itself in time, not because the risk wasn't real.
- **Contrast:** a fourth attempt, using a lighter, isolated harness
  (`python3 main.py --daemon` directly, bypassing the `codeydOS` wrapper
  and thus skipping the separate plannd process — only the 7B primary +
  embed server running), completed the same test safely with peak swap
  around ~1.9Gi, a small fraction of the full-stack figure. This strongly
  suggests the separate 1.5B plannd process (or the combination of all
  three models loading concurrently) is the dominant swap-pressure
  source, not the daemon/watchdog code exercised by the test itself.
- **Impact:** this is not a code bug — no exception, no crash-inducing
  logic error was found. It appears to be the genuine resource cost of
  running the full 3-model stack concurrently on this specific ~10.8GB
  device. It may explain other historical flakiness/crashes previously
  attributed to unclear causes, and is directly relevant to CLAUDE.md's
  RAM-discipline rule 2.
- **Not fixed here, and not necessarily fixable in a traditional
  code-level sense** — logged per CLAUDE.md rule 8 as a device-capacity
  finding worth preserving, not a bug to scope. Candidate follow-ups for
  a future pass (not scoped here): explicit user-facing documentation
  that the full `codeydOS start` (all three models) is heavy on
  ~10.8GB-class devices and should not be run alongside other memory-
  intensive live-verification tests; consider whether the daemon-only /
  plannd-optional lighter path used successfully here should become a
  documented, supported "lite" mode for constrained devices.

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

### [NEW-7] `[Recursive]` planner path may be prompted to synthesize whole functions rather than targeted patches (Confirmed, reproducible, ~67% failure rate on the docstring-insertion prompt style — NOT recursion-specific — still not fixed)
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

- **Round 14 (2026-07-30) — desk scoping pass, no live session run.**
  Mechanism re-verified against current code (line numbers below refreshed
  from Round 1's citation, which had drifted). No fix or reproduction was
  attempted this round — this only refines the reproduction plan handed to
  the next live-verification round.
  - `core/agent.py:1467` — `_use_recursive = step == 1 and not is_qa and
    RECURSIVE_CONFIG.get("enabled", True)`. `RECURSIVE_CONFIG["enabled"]`
    (`core/recursive.py:111-118`) is controlled by the `CODEY_RECURSIVE`
    env var: `1` forces on, `0` forces off, unset defaults to on for the
    local backend (which is what this device uses). **This is a clean,
    already-existing knob to isolate recursive vs. plain path across two
    separate sessions** — no code change needed to test both paths.
  - Even when `_use_recursive` is `True`, `core/agent.py:1477-1485` calls
    `classify_breadth_need()` (`core/recursive.py:138-165`) first; a
    "minimal" classification (short Q&A-shaped messages) still takes the
    plain `infer()` call, not `recursive_infer()`. "Add a docstring to the
    shutdown function in main.py" (10 words, contains the action keyword
    "add") classifies as "standard" → `max_depth=1` → one real
    draft/critique/refine cycle through `recursive_infer()`
    (`core/agent.py:1487-1496`), matching the originally observed
    `[Recursive] Draft (1/2)` → `[Recursive] Review (2/2)` transcript.
  - **New structural finding, relevant to root-causing (not yet a fix):**
    the draft-phase system prompt (`build_recursive_prompt(phase="draft")`,
    aliased as `core/agent.py:614 build_system_prompt()`) is IDENTICAL
    between the plain and recursive paths — both are seeded with the same
    system prompt before the step loop (`core/agent.py:1402`). This means
    if the `old_str: ""` behavior originates in the draft call itself, it
    is not a recursion-specific prompting gap and should reproduce on the
    plain path too. The recursive path's only structural difference is the
    critique+refine loop that runs *after* the draft.
  - **Second structural finding:** the critique phase's system prompt
    (`_build_critique_prompt()`, `prompts/layered_prompt.py:352-382`)
    deliberately drops repo/file context — the critique model only sees
    the critique instructions (`CRITIQUE_CODE`,
    `prompts/critique_prompts.py:23-38`), the original user request, and
    the prior draft text, never the real file content. `CRITIQUE_CODE`'s
    7 checklist items (syntax, logic bugs, missing imports, task
    completeness, security, uncertain APIs, multi-action completeness)
    contain nothing that would catch "does `old_str` actually match real
    file content" — the critique model has no ground truth to check that
    against even if it wanted to. This means the observed "quality 8/10,
    Accepted" outcome is not surprising: the critique step is structurally
    incapable of catching this class of bug, independent of whether the
    draft-generation bug itself is recursion-specific. This is a candidate
    explanation for *why* recursion didn't self-correct the problem, but
    does not by itself explain why the draft was wrong in the first place
    — still needs live evidence.
  - Confirmed `tools/patch_tools.py:14-22` (`tool_patch_file`) and
    `prompts/system_prompt.py:90,163,174,192` (the `patch_file` tool
    documentation shown to the model) contain no instruction that
    `old_str` must be a verbatim substring of the real file, nor any
    warning against using an empty `old_str` to mean "insert new content."
    This is a real gap in the prompt but not yet confirmed as *the* cause
    of the observed behavior — could equally be a base-model tendency
    unrelated to prompt wording.
  - Also confirmed `main.py:396-406` (`/clear` REPL command) resets
    conversation history/context/undo/session **without** reloading the
    model — usable to run multiple independent draws in one model-load
    cycle for a same-prompt consistency check, per CLAUDE.md rule 2's
    batching guidance.
  - **Reproduction task designed and handed to the next live-verification
    round** (not run this round): two short, sequential, single-model-load
    `python3 main.py --no-resume` REPL sessions (never both processes
    live at once — confirm teardown between them per CLAUDE.md rule 2),
    testing the same 3 edit-style prompts in each:
    1. Session A — recursive path (default env, no override):
       `python3 main.py --no-resume`
    2. Session B — plain path forced: `CODEY_RECURSIVE=0 python3 main.py
       --no-resume`
    - In each session, send in order, with `/clear` between each prompt
      (resets context without a reload) to avoid cross-contaminating the
      model's context with its own prior attempt:
      a. "Add a docstring to the shutdown function in main.py." (exact
         repeat of the original Round 1 prompt — direct reproducibility
         check)
      b. `/clear`, then the same prompt again — consistency/sampling-
         variance check on an identical prompt within the same path.
      c. `/clear`, then "Add error handling to the load_primary function
         in core/loader_v2.py." — different verb ("add error handling"
         vs. "add a docstring"), different target function
         (`core/loader_v2.py:337 def load_primary(self)`), to check
         whether the bug is docstring-specific or broader.
      d. `/clear`, then "Rename the variable `p` to `file_path` in
         tool_patch_file in tools/patch_tools.py." (`tools/patch_tools.py:
         14,28 p = Path(path).expanduser()`) — a rename-style edit, the
         third distinct prompt style, on a third distinct target file.
    - After each prompt, capture verbatim: the full `<tool>` call emitted
      (or lack thereof), whether `old_str` is empty vs. a real substring
      of the target file, and `git diff <target file>` immediately after
      the turn to confirm whether the edit actually landed. Reset
      (`git checkout -- <file>`) between prompts if a patch does land, so
      each prompt starts from a clean baseline.
    - Confirm process teardown between Session A and Session B (`ps -eo
      pid,ppid,comm | grep -E "python|llama"` showing nothing but the
      grep itself, per the project's established non-`pgrep -af` pattern)
      and run `free -h` before Session A, between sessions, and after
      Session B per CLAUDE.md rule 2.
    - This 2-session x 4-prompt design (8 draws total) directly answers
      all three open questions: (a) reproducibility/consistency, via the
      repeated identical prompt in each session; (b) recursive-specific
      vs. plain-path, via the `CODEY_RECURSIVE` env toggle across the two
      sessions; (c) docstring-specific vs. broader, via the 3 distinct
      prompt styles/targets. No code changes required to run this — it is
      a live-reproduction task only, not a fix.

- **Round 14 (2026-07-30) — live-reproduction pass, 6 of 8 planned draws
  completed; stopped early at swap-thrashing, per CLAUDE.md rule 2's
  instability instruction (a safe, correct stop, not a failure).** Two
  sessions run: Session A (recursive, default env) and Session B
  (`CODEY_RECURSIVE=0`, plain path — confirmed via absence of
  `[Recursive]` labels in the transcript, not just assumed from the env
  var).

  | # | Session | Prompt | `old_str` observed | Bug reproduced? |
  |---|---|---|---|---|
  | a1 | A (recursive) | docstring (1st) | `"def shutdown():\n    pass"` — non-empty but hallucinated/wrong stub | No (empty-string bug) — but a distinct hallucinated-`old_str` failure |
  | a2 | A (recursive) | docstring (repeat) | `""` | **Yes** — exact reproduction of the original NEW-7 bug |
  | a3 | A (recursive) | loader_v2 error handling | N/A — draft only issued a `read_file` call, no patch attempted; quality 3/10, hit low-confidence gate | No (different failure mode — no patch attempt) |
  | a4 | A (recursive) | patch_tools rename | `"p = Path(path).expanduser()"` — real, correct substring | No — correctly targeted patch, no bug |
  | b1 | B (plain, confirmed via absent `[Recursive]` labels) | docstring (1st) | Attempt 1: `""`; retry attempt 2 (same turn): `"\ndef shutdown():\n    pass"` (hallucinated) | **Yes** on attempt 1 |
  | b2 | B (plain) | docstring (repeat) | `"def shutdown():\n    pass\n"` — non-empty, hallucinated stub | No (empty-string bug) — same hallucinated-stub variant as a1 |
  | b3 | B (plain) | loader_v2 error handling | NOT RUN — stopped for swap thrashing | N/A |
  | b4 | B (plain) | patch_tools rename | NOT RUN — stopped for swap thrashing | N/A |

  **Conclusions this data supports — correcting the record per CLAUDE.md
  rule 6 (this entry was previously "Suspected... observed once"):**
  - The literal `old_str: ""` bug is real and reproducible: 2/6 completed
    draws (a2, b1), one on EACH path (recursive and plain) —
    **this settles the open question: the bug is NOT recursion-specific.**
    The plain path's draft-phase system prompt is identical to the
    recursive path's (per this round's earlier structural finding), so
    this result is consistent with that prediction.
  - A closely related variant (non-empty but hallucinated/wrong
    `old_str`, assuming `shutdown()` is a one-line `pass` stub instead of
    its real ~15-line body) occurred in 2 more draws (a1, b2) — same
    underlying failure class (model doesn't ground `old_str` in real
    file content), different surface symptom.
  - Combined: **4 of 6 completed draws (67%) failed to produce a valid
    patch on the "add a docstring to `shutdown()`" prompt**, split evenly
    between the two `old_str`-grounding failure variants.
  - Neither the loader_v2/error-handling style (a3) nor the
    patch_tools/rename style (a4) reproduced any variant of the bug in
    the draws that did run — a4 in particular got a real, correct
    `old_str` substring match. This suggests the failure may correlate
    with the specific "add a docstring" prompt style/target more than
    with edit-requests broadly, though this is **not fully confirmed**
    since only one of the two other styles ran per session before the
    stop.
  - **Not yet answered, needs a follow-up round:** b3 and b4 (the
    loader_v2/patch_tools prompts on the PLAIN path) were never run, so
    there is no clean same-path comparison for those two prompt styles.
    A future round should complete these two draws (fresh model-load
    cycle, fresh baseline) before this can be called fully characterized.
  - This investigation also surfaced 4 additional, distinct structural
    findings beyond NEW-7 itself, logged separately per CLAUDE.md rule 8:
    [NEW-15] (a `write_file`-escalation path that can attempt to
    reconstruct an entire file in the wrong location after `patch_file`
    fails — the most severe finding of this round), [NEW-16] (the patch
    UI panel renders as if successful even when the underlying patch
    call failed), [NEW-17] (the post-edit commit offer can scope-bleed
    into unrelated pre-existing dirty files), and [NEW-18] (a single
    lightweight REPL session hit severe swap-thrashing after only 2
    model calls with retries, independent of NEW-14's full 3-model-stack
    finding).

  **RAM discipline note (all real, verbatim, all clean teardowns by
  tracked PID, never by pattern):**
  - Pre-Session-A: 4.9Gi free / 7.0Gi available, swap 1.6Gi
  - Mid-Session-A: 163Mi free / 2.0Gi available, swap 3.6Gi (high, not
    thrashing)
  - Post-Session-A teardown: 4.8Gi free / 6.8Gi available, swap 1.6Gi
  - Mid-Session-B after b1: 653Mi free / 2.0Gi available, swap 2.2Gi
  - **After b2: swap jumped to 8.9Gi used, `llama-server` RSS collapsed
    to ~2MB (nearly fully swapped out), CPU 113% — genuine
    swap-thrashing.** Live-verifier stopped immediately per CLAUDE.md
    rule 2's explicit instability instruction.
  - Post-forced-teardown: 4.8Gi free / 7.0Gi available, swap back to
    1.9Gi — full recovery confirmed, no orphaned processes.

  **Status after this round: Confirmed (upgraded from Suspected),
  reproducible (4/6 completed draws on the docstring-insertion prompt,
  67%), confirmed NOT recursion-specific. Not yet confirmed whether it
  generalizes to other edit-request styles (b3/b4 outstanding). Still
  open, still unfixed — no implementer task scoped this round
  (investigation/logging only, per this round's explicit scope).**

## Found during Round 14 (NEW-7) live-reproduction pass, 2026-07-30 — NOT fixed, logged only

### [NEW-15] After `patch_file` fails, the model can autonomously escalate to reconstructing an ENTIRE file from memory via `write_file` — and place the edit in the wrong location (Resolved 2026-07-30, Round 15, commit `7756581`)

- **Resolution:** `tools/file_tools.py`'s `tool_write_file()` now refuses
  to overwrite an existing `.py` file with syntactically invalid content
  (via `core/linter.py`'s `check_syntax()`, fail-open if the linter
  import fails), and `tools/patch_tools.py`'s `[PATCH_FAILED]` message
  was reworded to de-emphasize `write_file` and warn against
  partial-memory reconstruction (the tool itself remains available).
  Code-reviewer approved after directly exercising `tool_write_file()`
  with a live throwaway script confirming blocked/allowed/new-file/
  fail-open behavior against the running code, and explicitly assessed
  that an on-device model session was not warranted for this
  deterministic, tool-level guardrail. Full unit test coverage added
  (`tests/test_file_tools.py`, 4 new tests; full suite 258 passed). See
  `PROJECT_LOG.md`'s 2026-07-30 Round 15 entry for full detail.
- **Scope note:** this fix addresses only the `write_file`
  full-file-corruption risk. [NEW-16], [NEW-17], and [NEW-18] below —
  logged during the same Round 14 investigation that found this issue —
  remain open and unscoped, not addressed by this fix. NEW-7 itself
  (the underlying planner behavior that triggers the `patch_file`
  failures in the first place) also remains open — Round 14's b3/b4
  reproduction draws were never completed.

- **Confidence: Confirmed** — directly observed twice, in both plain-path
  draws (b1, b2) where `patch_file` failed.
- **Where found:** Round 14 NEW-7 live-reproduction session B (plain
  path, `CODEY_RECURSIVE=0`). In both b1 and b2, after `patch_file` was
  rejected by `tools/patch_tools.py:56-61`'s `old_str` uniqueness
  guardrail, the model autonomously escalated to a `write_file` call
  attempting to reconstruct the ENTIRE 62,975-character `main.py` from
  its own context — generation was still in progress (594-614 tokens in,
  function body barely started) when the turn ended. In b1, the
  reconstructed `shutdown()` was placed in the WRONG location (right
  after the `BANNER` string near the top of the file, not its real
  location at line 125).
- **Why this is more severe than NEW-7 itself:** had
  `AGENT_CONFIG["confirm_write"]` been `False` (e.g. a `--yolo`-style
  mode) or a user reflexively accepted the write confirmation, this
  escalation path could have TRUNCATED/DESTROYED the rest of `main.py`,
  not just introduced a duplicate function. The confirmation gate is
  what prevented actual damage in this investigation — it worked, but
  shouldn't be relied on as the only safeguard against a
  full-file-reconstruction escalation combined with a wrong-location
  edit.
- **Relevant code, not yet pinned down precisely:** `core/agent.py` (the
  `write_file` escalation path taken after a `patch_file` failure —
  live-verifier did not cite exact line numbers for this specific
  escalation branch; a future investigation needs to pin down the exact
  trigger logic). `core/peer_cli.py:223` ("Codey hit max retries"
  escalation prompt — may be related, not yet confirmed).
  `AGENT_CONFIG["confirm_write"]` (currently `True` by default in this
  environment).
- **Not fixed here** — flag as needing its own dedicated
  investigation/scoping round, likely higher priority than NEW-7 itself
  given the severity (potential for silent full-file data loss, not just
  a bad edit).

### [NEW-16] The "Patching `<file>`" diff-preview UI panel renders unconditionally, regardless of whether the underlying patch actually succeeded (Resolved 2026-07-30, Round 16, commit `99d922f`)

- **Status: Resolved.** `core/agent.py`'s `show_patch()`/
  `show_file_write()` call sites now thread `error=is_error(result,
  name)` through to `core/display.py`, which switches to a red border +
  "PATCH FAILED"/"WRITE FAILED" title on error (unchanged happy-path
  styling otherwise, mirroring `show_shell()`'s existing convention).
  The identical bug in `show_file_write()` was bundled into the same fix
  (same file, same pattern). `show_patch()`'s call site additionally
  gained a narrow inline check for `tools/patch_tools.py`'s
  `[PATCH_FAILED]` prefix, deliberately not via widening the shared
  `is_error()` (which by design excludes `[PATCH_FAILED]` from the
  retry/escalation logic — see [NEW-19] below for a deferred design
  question this surfaced). code-reviewer approved: confirmed
  `is_error()` and all four retry/escalation call sites untouched,
  happy-path output byte-for-byte unchanged, full suite 325 passed (1
  pre-existing unrelated failure). **Code complete, code-reviewer
  approved via direct `execute_tool()`-level verification — no live
  model session, explicitly assessed as unwarranted for this
  display-only class of change.** See `PROJECT_LOG.md` 2026-07-30 Round
  16 entry for full detail.
- **Confidence: Confirmed** — observed in all 4 of 4 failed draws this
  round (a1, a2, b1, b2).
- **Where found:** `core/agent.py`'s `show_patch()` call (live-verifier
  cited ~line 410-413; re-verify exact line numbers before scoping a
  fix). It renders the green "Patching `main.py`" diff-preview panel
  unconditionally, regardless of whether the underlying
  `TOOLS[name](args)` patch call actually succeeded. In every one of the
  4 failed draws this round, the UI showed a success-looking "Patching
  main.py" panel that had nothing to do with what actually happened on
  disk (confirmed via `git diff` showing no change in every single
  failed draw).
- **Why this matters:** a real UI-honesty gap, independent of NEW-7's
  root cause — a user watching the terminal would see a success-looking
  panel even when nothing was written to disk.
- **Not fixed here.**

### [NEW-17] The post-edit "offer to commit" prompt scopes to ALL current working-tree changes, not just the current turn's edit (Confirmed)

- **Status: RESOLVED (commit `f4f51fa`), code-reviewer approved via
  direct scratch-repo verification, 2026-07-30.** No live model session
  needed for this class of change (see `PROJECT_LOG.md` Round 17 for
  full details).
- **Confidence: Confirmed** — observed in every draw of this
  investigation.
- **Where found:** `core/agent.py`'s `check_git_and_offer_commit()`
  (live-verifier cited ~line 659-680; re-verify exact line numbers
  before scoping a fix). It fires whenever `patch_file`/`write_file` was
  ATTEMPTED this turn (success or failure), and offers to commit ALL
  current working-tree changes, not just this turn's. In every draw of
  this investigation it fired against a PRE-EXISTING, unrelated dirty
  `NEW_ISSUES.md` already in the working tree.
- **Why this matters:** a real scope-bleed risk — a user reflexively
  answering "y" to this prompt after a failed edit attempt could commit
  unrelated in-progress work they didn't intend to commit yet.
- **Fix:** added `git_status_paths()`/`git_commit_paths()` to
  `core/githelper.py` (scoped `git add -- <paths>` / `git commit -- <paths>`,
  never `-A`), threaded the already-existing per-turn `files_touched`
  list into `check_git_and_offer_commit()`. `git_commit()`/`git_status()`
  themselves untouched, still used by `main.py`'s intentionally-broad
  manual-commit flows.
- **Accepted low-priority footnote (not tracked as its own issue):**
  code-reviewer noted `files_touched` accumulates paths from any tool
  call with a `path` arg (including `read_file`), not strictly
  write/patch tools. Harmless today — `git_status_paths()`/
  `git_commit_paths()` no-op on files with no actual working-tree
  changes — but slightly imprecise. Judged too minor to warrant a
  dedicated NEW-2x entry; revisit only if `files_touched`'s population
  logic is touched again for an unrelated reason.

### [NEW-18] A single lightweight REPL session (no daemon/plannd/embed stack) hit severe swap-thrashing after only 2 model calls with retries — swap pressure isn't limited to the full 3-model stack (Confirmed, possibly related to [NEW-14])

- **Confidence: Confirmed** — directly observed once this round; not yet
  investigated for root cause or reproducibility.
- **Where found:** Round 14 NEW-7 live-reproduction, Session B. Swap
  usage climbed to 8.9Gi (from a healthy ~1.6-2.2Gi baseline) within a
  SINGLE REPL session after only 2 model calls with retries (b1, b2),
  using the LIGHT harness (plain `main.py --no-resume`, no
  daemon/plannd/embed server) — a harness previously assumed safe based
  on NEW-13's earlier-this-session live-verification.
- **Why this matters:** suggests swap-thrashing risk isn't limited to the
  full 3-model `codeydOS start` stack ([NEW-14]) — it can also occur
  within a single lightweight REPL session under retry-heavy/multi-turn
  load.
- **Open question:** whether this is inherent to sustained single-session
  multi-turn agent use on this device, or specific to the
  retry/escalation-heavy failure pattern this investigation was
  triggering (multiple failed patch attempts + `write_file` escalation
  attempts in the same session, as seen in [NEW-15]).
- **Not fixed here** — flag as needing a dedicated investigation given
  its implications for CLAUDE.md rule 2's RAM-discipline guidance (may
  need updating to caution about sustained retry-heavy sessions, not
  just concurrent multi-model stacks).

## Found during Round 16 (NEW-16) scoping pass, 2026-07-30 — NOT fixed, logged only

### [NEW-19] Whether `[PATCH_FAILED]`'s deliberate bypass of the retry/escalation logic is fully correct as designed, and whether it needs its own distinct transcript marker (Suspected)

- **Confidence: Suspected** — a design question surfaced during Round
  16's scoping, not yet confirmed as a bug. Needs its own dedicated
  scoping pass, not fixed here.
- **Where found:** while scoping Round 16's `show_patch()`/
  `show_file_write()` display fix, confirmed (by reading
  `tools/patch_tools.py` and `core/agent.py`'s retry/escalation call
  sites) that `[PATCH_FAILED]` (the old_str-not-found case) is
  deliberately excluded from `is_error()`, so it never enters the
  auto-retry gate, the peer-CLI escalation path, or NEW-2's
  `[EDIT NOT APPLIED]` transcript marker — by design, so the model sees
  full untruncated file content to reconstruct the edit itself, rather
  than a truncated retry message.
- **Open question 1:** is bypassing retry/escalation entirely the right
  behavior for every `[PATCH_FAILED]` case, or should some subset (e.g.
  repeated failures on the same file/turn) still escalate?
- **Open question 2:** if a `[PATCH_FAILED]` case is never resolved
  within a turn, there is currently no transcript marker recording that
  outcome at all. Reusing NEW-2's existing `[EDIT NOT APPLIED] <tool> on
  <path> failed after retries and escalation were exhausted — no file
  was modified.` marker verbatim would be **inaccurate** for this case
  specifically: `[PATCH_FAILED]` never enters retry or escalation in the
  first place, so the phrase "after retries and escalation were
  exhausted" is false here. If a marker is wanted for this case, it
  needs its own distinct wording, not a naive reuse of NEW-2's marker.
- **Not fixed here** — this is a design question, not a display bug (the
  narrow, display-only fix in Round 16 addresses only the UI-honesty gap
  at the panel-rendering layer, not this deeper retry/escalation/
  transcript-marker question). Needs its own dedicated scoping pass in
  NEW-2/NEW-15 territory before any fix is attempted.

## Found during Round 18 (NEW-18 live-reproduction attempt), 2026-07-30 — NOT fixed, logged only

### [NEW-18] update — original question remains UNANSWERED after Round 18 attempt (correction per Ground Rule 6)

- **Correction:** Round 18 attempted to reproduce and isolate NEW-18's
  open question (whether swap-thrashing is driven by context SIZE or by
  turn COUNT/retries) by comparing a small-file multi-turn session
  against a one-large-file-read session. **The comparison could not be
  run** — the test harness hit a distinct, unrelated bug in `main.py`'s
  stdin handling (see [NEW-20] below) before either session produced any
  model traffic. Zero requests reached `llama-server` in this attempt
  (confirmed via `llama-server.log` showing no incoming requests after
  the "listening on http://127.0.0.1:8080" line).
- **This is not new evidence either way.** NEW-18's original open
  question (size vs. count/retries as the driver) is still exactly as
  open as it was when originally logged. Do not read this round as
  confirming, refuting, or narrowing that question.
- **For any future reproduction attempt:** originally, this guidance
  required a TTY-backed harness (e.g. a `pty`, `script(1)`, or similar),
  not plain stdin piping into `main.py --no-resume` — see [NEW-20] for
  why plain piping didn't work at the time. **Update (Round 19):** this
  constraint is now relaxed. NEW-20 was fixed in commit `ac732e9` and
  fully live-verified — plain stdin piping into `main.py --no-resume` no
  longer hangs, spins, or garbles input, so a future NEW-18 reproduction
  attempt can safely use plain stdin piping again; a TTY-backed harness
  is no longer required for this reason (though may still be worth using
  if a TTY-specific behavior is itself under test). The harness should
  still control for baseline free RAM
  before model load, which varied meaningfully between the two runs
  attempted so far (this run's baseline was 4.3Gi used/2.2Gi free vs.
  the original NEW-7 run's baseline of 4.9Gi free) and is a likely
  confound on severity, independent of the size-vs-count question.
- **Not fixed here** — NEW-18 remains open, unresolved, unchanged in
  substance from its original entry above.

### [NEW-20] `main.py`'s paste-detection `select()` logic busy-loops at ~100% CPU and mis-concatenates input when stdin is a non-TTY file/pipe (Resolved)

- **Resolved in Round 19, commit `ac732e9`.** The paste-detection
  `select()` loop is now wrapped in `if sys.stdin.isatty():`, so it's
  skipped entirely for non-TTY stdin — falling through to the plain
  single-line `input()` result with existing `EOFError` handling taking
  over naturally at end of input. TTY sessions keep the exact same
  paste-glue behavior.
- **Code-reviewer approved:** independently reproduced pre-fix hang
  (piped input times out, exit 124), post-fix clean processing (exits in
  under a millisecond), and confirmed via a pty-based TTY simulation that
  paste-glue still fires correctly for genuine interactive sessions.
  Checked all launcher scripts (`gui/start.sh`, `codeydOS`, `codeyOS`)
  for stdin wrapping that could affect `isatty()` in real use — none
  found.
- **Fully live-verified (Round 19):** real invocation
  `printf 'hello\nwhat is 2+2\n/exit\n' | timeout 180 python3 main.py
  --no-resume` — `real 0m27.791s`, exit 0. The two piped lines were
  processed as two distinct, correctly-answered turns (not garbled
  together), with clean `/exit` teardown and no orphaned `llama-server`
  process afterward. This did involve a real model-load cycle (`repl()`
  calls `loader.load_primary()` unconditionally before the input loop),
  confirmed fully unloaded afterward per CLAUDE.md rule 2.
- **Consequence for [NEW-18]:** the harness guidance in NEW-18's entry
  below is updated — plain stdin piping into `main.py --no-resume` is now
  safe to use in a future reproduction attempt, since this fix is exactly
  what made it unsafe.

- **Confidence: Confirmed** — directly reproduced this round, and
  root-caused by reading the code and cross-referencing the session log
  and `llama-server.log`.
- **Where found:** `main.py:1337-1359`. The multi-line-paste-detection
  code calls `select.select([sys.stdin], [], [], 0.02)` to decide whether
  more input is immediately available (to distinguish a pasted
  multi-line block from a single line typed interactively). When stdin is
  a non-TTY file or pipe (e.g. a test harness piping a static input file
  into `main.py --no-resume`'s stdin), `select()` always reports stdin as
  "readable" — including once the file is at EOF. This caused two
  distinct failures in sequence this round:
  1. On the very first `input()` call, the paste-detection logic drained
     the *entire* remaining input file in one pass, concatenating all of
     it into a single garbled message instead of treating it as separate
     turns.
  2. After EOF, `readline()` returns `''` forever while `select()` keeps
     reporting the descriptor as "ready" — so the loop spins indefinitely
     with no forward progress and no way to exit. Observed at ~88% CPU on
     a 13MB-RSS process, with the model loaded successfully but zero
     requests ever reaching `llama-server` (confirmed via
     `llama-server.log` showing no incoming requests after the "listening
     on http://127.0.0.1:8080" line).
- **Why this matters:** this is a real, distinct bug independent of
  RAM/swap behavior — it currently blocks any automated/scripted testing
  of the REPL via stdin redirection, and could plausibly affect any real
  non-interactive invocation of `main.py` (e.g. piped input from another
  script or process), not just test harnesses.
- **Not fixed here** — flag as needing its own scoping/fix pass. This is
  a clean, cheap, well-isolated candidate for a near-future round: the
  root cause is already fully identified (the `select()`-based paste
  heuristic is TTY-only-safe and needs an `os.isatty(sys.stdin.fileno())`
  guard, or equivalent, before relying on `select()`'s readiness signal).

### [NEW-21] Model load alone (before any inference) can drive swap from ~1.2Gi to ~5.6Gi within ~10 seconds when baseline free RAM is tight (Confirmed, related to [NEW-14])

- **Confidence: Confirmed** — directly observed this round via
  `llama-server.log` timestamps and `free -h` readings taken by the
  live-verifier during the (otherwise inconclusive) Round 18 attempt.
- **Where found:** Round 18 live-reproduction attempt, using the light
  harness (plain `main.py --no-resume`, single model, no daemon/plannd/
  embed stack). Swap climbed from ~1.2Gi to ~5.6Gi within roughly 10
  seconds purely from the model load itself — confirmed via
  `llama-server.log` timestamps that this happened before any turn could
  possibly have been dispatched (and independently confirmed no requests
  ever reached the server this run at all). `llama-server`'s own RSS was
  subsequently squeezed from 5.6GB down to 1.26GB (partially swapped out),
  with swap climbing further to 6.8Gi over the following minute.
- **Baseline-dependency observation:** this run's baseline going into the
  load was 4.3Gi used / 2.2Gi free — notably worse than the original
  NEW-7 run's baseline of 4.9Gi free. Severity likely depends on how much
  free RAM exists before load starts, not just on the load itself; this
  is a relevant confound for any future comparison, not a fixed constant.
- **Why this matters:** consistent with [NEW-14]'s underlying concern
  (`n_ctx=32768`'s KV-cache reservation being large relative to this
  device's RAM budget), but now confirmed to affect even a **single
  lightweight model load**, not just the full 3-model
  `codeydOS start` stack. Same observational character as NEW-14 — may
  inform a future `n_ctx` tuning discussion, but no action is recommended
  yet.
- **Not fixed here** — observational only, logged for future reference.

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
- **Status: RESOLVED, verified 2026-07-30.** `python3 -m pytest tests/test_patch.py tests/test_hallucination.py -q` → `24 passed`, 0 failures. Whatever caused the original 8 failures no longer reproduces on current code — confirmed by directly running the test file, not inferred. Marked done during a NEW_ISSUES.md accuracy sweep; not tied to a specific round/commit since the fix (if any) predates when this was checked.
- **Original issue (for history)**: Hallucination detection tests failing
- **Original root cause**: The `detect_hallucination()` function in `core/agent.py` didn't detect past-tense claims like "I created", "I wrote", "I modified"
- **Files**: `tests/test_hallucination.py`, `core/agent.py`

### test_patch.py (1 failure)
- **Status: RESOLVED, verified 2026-07-30.** Same test run as above confirms 0 failures in `test_patch.py`. The test's expectations were already updated to match the current `[PATCH_FAILED]` message format (confirmed during Round 15's code review, which noted `tests/test_patch.py` only asserts `assertIn("old_str not found", res)` — a substring unaffected by later wording changes).
- **Original issue (for history)**: Patch error message format changed
- **Original root cause**: The patch tool now returns `[PATCH_FAILED]` instead of `[ERROR] String not found`
- **Files**: `tests/test_patch.py`, `tools/patch_tools.py`

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
- **Status: RESOLVED, verified 2026-07-30.** `PRIVACY.md` exists in the
  repo root with real content (87 lines — 100%-local-by-default, no
  telemetry, data handling practices). This entry was stale; the file
  it asked for already exists. Confirmed by directly reading the file,
  not inferred.
- **Original issue (for history)**: No explicit privacy policy document
