---
name: new278-plugin-pid-dir-resolution-approved
description: NEW-278 ProcessSupervisor pid_file resolution fix (plugin_manager.py) — approved, 2 real bugs confirmed fixed, 2 out-of-scope findings (NEW-424/425) verified accurate
metadata:
  type: project
---

Reviewed 2026-09-09: `ccos/core/plugin_manager.py` + `ccos/tests/test_external_plugin_supervision.py` diff for NEW-278 (Rule-4 process-lifecycle gate).

**Verdict: APPROVED.**

Two independent bugs, both confirmed real by tracing pre-fix code, both closed by the fix:
1. `start_external_plugin()` used to resolve a relative manifest `pid_file` against `plugin.path` (repo source tree) — confirmed both real manifests (`ccos/plugins/voice/aigentik/manifest.json`, `.../device/private_agent/manifest.json`) use bare relative filenames, so this was live, not theoretical.
2. `PluginManager.unload()` passed the raw manifest `pid_file` string straight to `stop_external_plugin(pid_file=...)`. That method's signature is `pid_path = Path(pid_file) if pid_file else self._pid_files.pop(...)` — i.e. explicitly passing a non-None `pid_file` **always bypasses** the `self._pid_files` fallback that already had the correctly-resolved path. This means the bug was real even within a single long-lived `PluginManager` instance (same process, load() then unload()), not just cross-process — worth noting because a shallower read might dismiss bug 2 as only mattering after a restart.

Fix: new module-level `_resolve_pid_path()` + `PLUGIN_PID_DIR = CODEY_STATE_DIR / "plugins"`, used consistently by both `start_external_plugin()` and `unload()`. `mkdir(parents=True, exist_ok=True)` is already called before `write_text()`, so first-run directory-doesn't-exist is handled, no crash.

**Design choice verified sound**: `PLUGIN_PID_DIR` is namespaced under `plugins/`, not `CODEY_STATE_DIR` directly, specifically because `lib/service_manager.sh` already owns `$DAEMON_DIR/aigentik.pid` (`AIGENTIK_PID_FILE`) for the *separate* `~/Codey-Aigentik` process. Confirmed both `aigentik` manifest's `start_command` (`python3 -m aigentik.server`, cwd inside the CCOS plugin dir) and service_manager.sh's `start_aigentik()` spawn genuinely different processes under a shared conceptual name — sharing one PID path would have been a real Rule-3-adjacent collision (either supervisor could SIGTERM/SIGKILL a PID the other spawned). This is exactly the class of bug this project's rule 4 exists to catch, and the implementer got it right.

**Tests**: both new regression tests are genuine discriminators, not tautologies (the ledger records that an early draft of test 2 asserted `_resolve_pid_path(x) == _resolve_pid_path(x)` and was caught and rewritten before this round — matches what's in the current diff, which does a real `load()`→`unload()` round trip). Manually re-traced: `stop_external_plugin`'s `Path(pid_file)` branch would resolve a bare `"voice.pid"` against process CWD pre-fix, so test 2's `assert not expected_pid_path.exists()` after `unload()` would fail against reverted code — confirmed this is a real discriminator, not just trusting the ledger's claim.

**NEW-424/425 (both logged not fixed, correctly out of scope)**:
- NEW-424: `start_external_plugin(self, plugin, state_dir=None)` — `state_dir` param confirmed genuinely dead; body uses the module-level `PLUGIN_PID_DIR` constant, never reads the parameter. Real, harmless (nothing passes a non-default value today), correctly deferred.
- NEW-425: `utils/config.py` hardcodes `CODEY_STATE_DIR = Path.home() / ".codeyOS"` with no env-var override, while `lib/service_manager.sh` does `DAEMON_DIR="${CODEY_STATE_DIR:-$HOME/.codeyOS}"` (honors an env override of the same name). Confirmed real latent divergence under non-default deployment; correctly out of scope for this fix (this fix imports the existing constant, doesn't change its semantics).

**Orphaned state**: `ccos/plugins/voice/aigentik/aigentik.pid` and `.../device/private_agent/private_agent.pid` (old buggy-location files) confirmed still present on disk (`ls -la` timestamped today), gitignored so `git status` stays clean, correctly flagged as a loose end rather than silently left. Not code, not blocking.

**Test suite**: `ccos/tests/ -q` → 114 passed (exact match to ledger claim). `tests/ -q` → 1545 passed, 1 skipped (ledger claimed 1546 passed — 1 off, attributable to concurrent untracked test files in the same working tree from other parallel agents at review time, not this diff; ccos/tests exact match is the more relevant signal since this diff only touches ccos/).

Nothing to add to the general bug-pattern list — this one is a clean example of the project's own stated Rule 3/4 collision risk (shared conceptual process name, two independent supervisors) being correctly reasoned through, not a new pattern.
