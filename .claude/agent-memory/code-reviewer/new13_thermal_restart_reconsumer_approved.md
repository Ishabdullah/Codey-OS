---
name: new13-thermal-restart-reconsumer-approved
description: NEW-13 fix re-wires ThermalManager.restart_recommended into ModelLoader.ensure_model() via unload()+load_primary() — APPROVED, closes NEW-12's orphaned-flag warning
metadata:
  type: project
---

Round (NEW-13): closes the Warning logged in
[[new12_inference_launcher_delegation_approved]] — `core/thermal.py`'s
`restart_recommended` flag had no consumer after NEW-12 removed the old
`core/inference.py::_start_server()` block. Fix adds a branch inside
`ModelLoader.ensure_model()` (core/loader_v2.py) that checks the flag when
the server is already loaded/running, and if set: `self.unload()` →
`tm.restart_recommended = False` → `return self.load_primary()`.

Verified independently:
- `git diff --stat` showed only `core/loader_v2.py`, +15/-0, entirely
  inside `ensure_model()`. `LlamaServer.start()`'s NEW-9 `pthread_sigmask`
  block and `stop()`'s killpg/SIGTERM/SIGKILL teardown are byte-for-byte
  untouched by this diff (confirmed by reading full file, not just the
  diff hunk).
- `unload()`/`load_primary()` are the only mechanisms touched — no direct
  `self._server.stop()`/Popen call added. `unload()` correctly clears
  `self._server`/`self._loaded`; `load_primary()` correctly sets
  `self._loaded`/`self._loaded_at`/`self._load_failures` bookkeeping.
- Thread count actually takes effect on restart: `core/thermal.py::
  _reduce_threads()` mutates `MODEL_CONFIG["n_threads"]` in place (dict,
  not a copy), and `LlamaServer.start()`'s cmd-list construction reads
  `MODEL_CONFIG["n_threads"]` fresh each call (line inside `start()`, not
  cached at `__init__`/module import) — confirmed by reading the actual
  cmd-building code, not assumed.
- Flag-clear-before-restart-attempt ordering: if `load_primary()` then
  fails, `ensure_model()` correctly propagates `False` (no swallow). No
  stuck-broken-state risk beyond ordinary load-failure behavior: since
  `load_primary()` on failure leaves `self._loaded = False`, the *next*
  `ensure_model()` call takes the `return self.load_primary()` fallback
  path regardless of the (now-cleared) thermal flag — normal retry-on-
  next-call semantics, not a new dead-end. Compared this against the
  pre-NEW-12 `core/inference.py::_start_server()` history via `git log -p`
  — old code had messier flag-clear-then-unconditional-restart logic with
  the same basic shape (clear flag, then always attempt restart
  regardless of the old process's teardown outcome); new code is at least
  as safe.
- `except Exception: pass` has an explicit comment justifying fail-open
  (thermal check must never block normal inference) — satisfies this
  project's exception-swallowing scrutiny rule.
- Concurrency: no lock around the flag-check-then-act sequence, but
  repo-wide grep confirms `ensure_model()` has exactly one call site
  (`core/inference.py::_start_server()`), and the GUI (`gui/server.py::
  run_codey`) shells out to `main.py` as a *subprocess* rather than
  calling `infer()`/`ensure_model()` in-process — so concurrent
  `ensure_model()` calls within one process aren't currently reachable.
  This is a *latent* risk (a future caller could reintroduce concurrency)
  but not currently exploitable — logged as Warning, not blocking, same
  treatment as the NEW-9 sigmask fork-inheritance Warning.
- Full test suite: `321 passed, 1 failed` — the 1 failure
  (`ccos/tests/test_ccos.py::test_sandbox`) reproduces identically on a
  stashed (pre-diff) tree, confirmed pre-existing and unrelated.
- No test exercises this new branch directly (no `restart_recommended`/
  `ensure_model` hits under `tests/`) — live-verification gap, not a
  blocker given real sustained-thermal triggering is impractical to
  reproduce live. The proposed workaround (directly set
  `get_thermal_manager().restart_recommended = True` then call
  `ensure_model()` again, check for a new PID via `get_pid()` before/
  after) is adequate: it exercises the exact code path this diff added
  (`is_running()` True branch → flag check → unload → load_primary) even
  though it doesn't reproduce genuine device heat.

**How to apply:** this closes the NEW-12 orphaned-flag Warning. If a
future diff touches `ensure_model()` again, re-verify the "exactly one
call site, no concurrent callers" premise before dismissing the
no-lock concurrency gap as non-exploitable — it's true only because
`gui/server.py` shells out via subprocess rather than calling in-process.
