---
name: new358-site3-aigentik-cli-approved
description: NEW-358 Site 3 (tools/ensure_model_cli.py) — dedicated aigentik run_start CLI, approved after live end-to-end verification
metadata:
  type: project
---

NEW-358's deferred Site 3 follow-up: new `tools/ensure_model_cli.py`
(Codey-OS) replaces Aigentik's inline `python3 -c "..."` one-liner
(`Codey-Aigentik/index.js:221`) with a dedicated script that calls
`telemetry.recorders.record_run_start(emitter="aigentik",
repo="Codey-Aigentik", ...)` before `get_loader().ensure_model('primary')`,
giving that delegated subprocess richer identity than the generic
loader-side fallback (`core/loader_v2.py::_ensure_run_start_fallback()`,
`3ea0a4d`) would provide. **Verdict: APPROVED.**

**Verification method worth reusing:** both of the diff's own tests
mock `telemetry.recorders.record_run_start` entirely, so they never
exercise the real function against the real schema. Per the
[[new259_daemon_config_and_loader_port_fix_approved]] precedent (a
missing kwarg made a whole mechanism a silent no-op through two
approvals), I called the *real*, unpatched `record_run_start()` with
the script's exact kwargs directly, inspected the written
`runs/*.json`/JSONL record, and confirmed: no exception; `git_commit_sha`
in the record matched Aigentik's actual `HEAD`, not Codey-OS's (proves
`repo_dir=get_aigentik_config()["dir"]` — a `str`, not `Path` — is real,
live-flowing data, not silently dropped — `get_git_provenance()` just
does `cwd = str(repo_dir)`, so the str/Path mismatch is harmless);
`models: []` schema-safe; `emitter: "aigentik"` valid per
`telemetry/schema/v1.json`'s enum. Then confirmed
`store.claim_run_start()` returned `False` immediately after — i.e. the
real call actually flips the same `_run_start_recorded` flag
`_ensure_run_start_fallback()` checks (both `mark_run_start_recorded()`
and `claim_run_start()` share one flag under `_run_start_lock` in
`telemetry/store.py`), directly confirming the docstring's "wins the
loader's fallback race" claim rather than trusting the docstring's
prose.

**Gotcha hit while doing this:** `CODEY_STATE_DIR`/`METRICS_DIR` in
`utils/config.py` are module-level `Path` constants computed once at
import time from `Path.home()` — setting `os.environ["CODEY_STATE_DIR"]`
*after* import (or in the same script, since imports happen first) has
**no effect**; there is no live env-var redirect for telemetry output.
A "sandboxed" live-call test that tries to redirect state dir this way
silently writes into the real `~/.codeyOS/metrics/` instead. Confirmed
by `find ~/.codeyOS/metrics -type f` newer than the test run, then
deleted the 2 stray `runs/*.json` + 3 stray `events/*.jsonl` files
afterward. **How to apply:** before trusting an env-var-based redirect
for any Codey-OS state directory, grep for how the constant is actually
computed — module-level `Path.home()/...` constants don't respect
env vars set later in the same process, and won't respect `os.environ`
set in a *different* process's env either. Always `find` for stray
recently-modified files under `~/.codeyOS/` after any "sandboxed" live
telemetry/state test and clean up before finishing the review.

**Implementer's stated rationale for item 4 was backwards but the code
was still right:** they said they verified path resolution "from
`tools/` cwd (matching how execSync actually calls it)" — wrong,
`execSync` inherits the *Node process's* cwd (Aigentik's directory), not
`tools/`. What actually makes the import work is Python's own
`sys.path[0] = script's directory` default plus the script's explicit
`sys.path.insert()` of the repo root, both cwd-independent. Flagged as a
non-blocking doc correction, not a functional bug — reproduced myself
from a genuinely different cwd (`/usr/tmp`) to confirm the real
behavior regardless of the stated reasoning.

Both Aigentik (`npm test`: 19 suites / 272 tests) and Codey-OS
(`pytest tests/`: 1435/1 skipped; full repo: 1542/1 skipped) suite
counts reproduced independently, exact match to implementer's claims.
Grepped Aigentik's test files for the old literal `python3 -c` string —
zero hits, confirming no test pinned the replaced string.

**How to apply:** when a diff's own tests mock the exact function whose
real behavior (schema validity, race-flag interaction, cross-repo git
provenance) is the actual thing being claimed, don't stop at "tests
pass" — call the real function once with the same kwargs against a
throwaway/cleaned-up state and inspect the actual written artifact. Mocks
prove call-order and non-blocking-on-failure; they cannot prove the real
call doesn't raise or that the race-winning side effect actually fires.
</content>
