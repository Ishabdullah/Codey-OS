---
name: main-py-new5-keyboardinterrupt-fix-approved
description: NEW-5 fix (repl() load_primary() try/except KeyboardInterrupt/SystemExit -> shutdown()) — APPROVED via static analysis
metadata:
  type: project
---

Round 6, NEW-5 fix in `main.py` `repl()` (~line 1269): wraps
`loader.load_primary()` in `try/except (KeyboardInterrupt, SystemExit):
shutdown(); return`. Reviewed and **approved**.

Why it's safe (traced, not assumed):
- `ModelLoader.get_pid()`/`unload()` (`core/loader_v2.py`) null-check
  `self._server` and `self._server.process` correctly at every point
  `load_primary()` could be interrupted — before `self._server` is
  assigned, after assigned but before `Popen`, after `Popen` but before
  health-check completes, and after a full successful load. No crash, no
  spurious kill, no leaked orphan in any of these states.
- `get_loader()` is a module-level singleton (`core/loader_v2.py` line
  411) — `shutdown()` calling `get_loader()` again from inside the new
  except block gets the *same* instance `repl()` already has, not a new
  one. No self-race (the PID-file self-race bug class doesn't apply
  here — this is an in-memory singleton with correct null-checks, not a
  file written and re-read by the same process).
- `shutdown()` (main.py line 125, unchanged) is the only kill path
  exercised — no parallel/duplicate teardown logic was added. It already
  gates on `_daemon_is_running()` (leaves llama-server alive if a daemon
  owns it) and already scopes kills to the tracked PID via
  `loader.get_pid()`/`unload()`, never pkill-by-name.
- `monitor.start()` runs before `load_primary()` in `repl()`; `shutdown()`
  calls `get_monitor().stop()` first, so the new early-return doesn't
  leak the monitor thread.
- `repl()` is the last statement in `main()` — the new early `return`
  just lets `main()` end normally; nothing after `repl()` needed running.
- Grepped for `sys.exit`/`raise SystemExit` reachable from
  `load_primary()`'s call stack — none exist, so catching `SystemExit`
  here doesn't swallow an unrelated intentional exit code.

See [[termux_signal_delivery_unreliable_in_sandbox]] for why I could not
cleanly reproduce this live through the Bash tool, and relied on static
analysis + the implementer's separately-run live-verification claim.

Companion open item: [NEW-6] in `NEW_ISSUES.md` — same unguarded
`load_primary()` pattern at three other call sites (`args.init`,
`args.tdd`, `args.fix`), deliberately not bundled into this fix,
logged for a follow-up task.
