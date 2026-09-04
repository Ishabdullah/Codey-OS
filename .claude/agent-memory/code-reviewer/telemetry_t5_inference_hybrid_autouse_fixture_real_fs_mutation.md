---
name: telemetry-t5-inference-hybrid-autouse-fixture-real-fs-mutation
description: T5 inference_hybrid.py telemetry round — passivity/streaming-loop verified clean, but an autouse test fixture that flips TELEMETRY_ENABLED=True without patching is_interactive_session_active() made every test in the file mutate real ~/.codeyOS/tui-sessions/ state
metadata:
  type: project
---

Reviewed T5 (`core/inference_hybrid.py`, Category-A inference events + Category-B
gate-decision telemetry) — a CLAUDE.md rule-4 file (inference hot path). Round
result: CHANGES REQUESTED for one test-file fix; production code approved.

**Passivity verified clean** — `git diff --stat -- core/resource_gate.py` was
empty: zero bytes touched in the file with the cross-process `flock`, the
strongest possible proof for this class of file. Category-B telemetry emitted
strictly outside both the lock and the fail-closed admission `except` block.
Streaming per-token loop change was a branch reshuffle (`if not X and Y` →
`if not X: ... if Y:`), not new per-iteration work — verified by reading, not
trusting the "one added conditional" description.

**Bug found via advisor, not my own first pass — worth internalizing the
pattern:** a new `@pytest.fixture(autouse=True)` set `recorders.store.TELEMETRY_ENABLED
= True` for every test in the file (overriding conftest's session-wide False
default) to exercise the new telemetry paths, but did NOT patch
`core.resource_gate.is_interactive_session_active()`. That function isn't a
pure read — `is_tui_session_active()` underneath it lists a real,
non-test-isolated device path (`utils.config.TUI_SESSIONS_DIR`,
`CODEY_STATE_DIR / "tui-sessions"`) and **unlinks** any stale/dead-PID entry
it finds (`entry.unlink(missing_ok=True)`), logging warnings. Flipping the
kill switch on for a whole test file made every test in it — including 5
pre-existing tests that predate this round — reach into and mutate the
developer's actual `~/.codeyOS/tui-sessions/` directory on every run.

**Generalizable check for future telemetry rounds:** whenever a fixture
force-enables `TELEMETRY_ENABLED` to exercise new instrumentation, trace
every function newly reachable under that flag (not just the emit function
itself) for real I/O side effects — a signal-reading helper written for a
different design purpose (interactive-session detection) can have
cleanup/mutation behavior baked in that's fine in production but breaks test
hermeticity when force-enabled file-wide. Required fix pattern:
`monkeypatch.setattr("core.resource_gate.is_interactive_session_active", lambda *a, **k: False)`
in the fixture, or redirect the underlying dir to `tmp_path`.

**Emitter-default disposition (separate judgment call in this round):** the
implementer defaulted `telemetry_emitter="codey-os.daemon"` in
`core/inference_hybrid.py` because the file has no reliable per-call-site
process-identity signal, provably false for TUI-driven `core/agent.py` calls.
Ruled sound-as-is/defer rather than blocking, because `telemetry/store.py`'s
`get_run_id()` is a genuine process-global singleton and `main.py` already
declares `emitter="codey-os.tui"` at its own `record_run_start()` for that
same `run_id` — so mislabeled records are still recoverable via a
`run_id`/`pid` join, not silently lost. Correction made to the coordinator's
framing: the real fix needs no schema v2 bump (the enum blocker was only for
a rejected module-identity string idea) — thread real per-call-site process
identity through `core/agent.py`/`core/task_executor.py` at T7 instead. I did
independently find a cheaper candidate fix (`TUI_SESSIONS_DIR/{os.getpid()}.pid`
existence check, honest "am I the TUI" signal, no schema change needed) but
recommended against requiring it — it's only partial (doesn't fix
orchestrator/planner/plannd/recursive callers) and adds new filesystem-derived
branching to a rule-4 file for marginal gain mid-series.

See also [[telemetry_t3_prefix_cache_hit_round2_flaky_test_rejected]] (the T3
precedent this round was told to mirror) and
[[telemetry_t4_cli_rollup_rotate_approved]].
