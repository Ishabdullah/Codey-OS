---
name: new11-daemon-watchdog-liveness-check
description: NEW-11 daemon.py watchdog fix (stale get_loaded_model -> real is_running liveness check) — APPROVED
metadata:
  type: project
---

core/daemon.py's 30s local-model watchdog (inside `_main_loop`, around line
556-562) previously checked `loader.get_loaded_model()`, which only reflects
`self._loaded` — a flag set once at successful load and never reset by any
liveness check. It could only detect "never successfully loaded," not a
genuine mid-session `llama-server` crash. NEW-11 replaced it with:

```python
_server = _loader.get_model_instance()
if not (_server and _server.is_running()):
    warning("7B model server died — restarting...")
_loader.ensure_model()
```

Verified in `core/loader_v2.py`:
- `get_model_instance()` returns `self._server` directly (the live
  `LlamaServer` instance, or `None`) — not a copy, not a stale flag.
- `LlamaServer.is_running()` does a real check: `self.process.poll() is None`
  if a `subprocess.Popen` handle exists, else falls back to an HTTP
  `_check_health()` if `_started`. Genuine liveness check.
- `ModelLoader.ensure_model()`'s restart-vs-noop decision is driven by the
  *same* `self._server.is_running()` call the daemon just used to decide
  whether to print the warning — so warning text and actual action can't
  meaningfully disagree (single-threaded async loop, no `await` between the
  two calls, so no race window).

**Behavior change worth noting (not a bug):** before this diff, the
watchdog only ever called `load_primary()` (never `ensure_model()`), so
NEW-13's thermal-restart branch inside `ensure_model()` was never reachable
from this watchdog — it only fired from `inference.py`/`inference_v2.py` on
actual inference calls. After this diff, the watchdog calls `ensure_model()`
unconditionally every 30s regardless of inference activity, so a thermal
restart can now trigger during total daemon idle (no user activity) up to
every 30s. This is a legitimate behavior change (idle daemon can now restart
itself for thermal reasons) — likely intended/beneficial (see [[new13_thermal_restart_reconsumer_approved]])
but flag it explicitly if reviewing future rounds that touch thermal cadence
or idle power behavior, since it wasn't true before NEW-11.

No test coverage exists for this watchdog path (`grep -rl "watchdog\|ensure_model" tests/`
returned nothing) — only covered by production's `try/except Exception: pass`.
Live verification requires an actual daemon process + real model load +
killing the tracked llama-server PID and observing detection/restart within
one 30s tick — this was not performed as part of code review (static
analysis + unit suite only, 254 passed).
