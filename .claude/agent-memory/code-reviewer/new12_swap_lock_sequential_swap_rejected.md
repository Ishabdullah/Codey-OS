---
name: new12-swap-lock-sequential-swap-rejected
description: NEW-12 remaining items (flock cross-process lock + primary/planner sequential swap) — REJECTED first pass, APPROVED fix-up round 2026-07-31
metadata:
  type: project
---

## Round 1 (rejected 2026-07-31) — required fixes, all since verified fixed in round 2

1. **Any unload+load cycle that changes `_loaded`/`_server` state must go through
   `SWAP_GUARD`, not just the code path literally named "swap".** Found:
   `ModelLoader.ensure_model()`'s thermal-restart branch did `self.unload()` +
   `self.load_primary()` *before* the SWAP_GUARD acquire later in the same
   function — during that window a concurrent `ensure_planner()` could see
   "primary not loaded, port free" and spawn the planner. Both resident,
   purely in-process.

2. **"Symmetric" eviction claims must be verified by diffing exception
   handling, not just control flow.** `ModelLoader._evict_planner_and_confirm_free()`
   wrapped its body in try/except (fail-closed); the mirror,
   `PlannerLoader._evict_primary_and_confirm_free()`, had no try/except at
   all, despite its caller's docstring claiming "never raises".
   `probe_port_health()` only caught `(URLError, OSError, ValueError)` — a
   malformed HTTP status line (`http.client.BadStatusLine`) wasn't caught.

3. **A test that mocks health/lock state but not `subprocess.Popen` + uses
   the real model path is a live-spawn hazard.** One lock-contention test
   patched `_is_port_in_use`/`_check_health`/`time.sleep` but not `Popen`,
   using real `lv.MODEL_PATH` — same mocking-gap class as the implementer's
   disclosed PID-1388 incident that round.

4. **`main.py`'s unguarded `load_primary()` calls bypass the swap entirely**
   (logged as NEW-69, not a quick patch — see round 1 write-up's reasoning
   on why routing through `ensure_model()` naively would fail-closed the
   REPL whenever the daemon has a planner loaded, due to fresh-process
   singleton semantics).

5. **Timing budget correction:** implementer's self-reported "~180s" omitted
   `LlamaServer.stop()`'s SIGKILL path, `probe_port_health`'s 2s, and
   `_is_port_in_use`'s double socket+HTTP checks. Real worst case ~190s+,
   *over* `core/daemon.py`'s `asyncio.wait_for(..., timeout=180.0)` — logged
   into NEW-68 as a severity correction (rule 6).

## Round 2 fix-up — APPROVED (2026-07-31)

All 3 required bugs (items 1-3 above) verified fixed, independently
re-derived, not just trusted from implementer's report:

1. **SWAP_GUARD now covers `ensure_model()`'s entire body.** Verified by
   actually reverting the guard-widening in place (moved the thermal-restart
   branch back outside the lock, narrowed the lock to only the cold-load
   branch) and re-running the new regression test
   (`test_ensure_model_thermal_restart_holds_swap_guard_against_concurrent_planner_swap`):
   it failed exactly as predicted (`assert planner_result.get("result") is False`
   → `AssertionError: assert True is False`, actual
   `{'result': True, 'is_loaded': True}` — the planner loaded concurrently
   during the thermal-restart window). Restored the file from a pre-edit
   backup, confirmed `diff` was empty against the original, re-ran full
   suite (`280 passed`). This is the right way to verify a "we added a
   regression test for the bug" claim — don't just read the test, prove it
   actually red/green cycles against the real fix.

2. **Symmetric fail-closed eviction.** `PlannerLoader._evict_primary_and_confirm_free()`
   and `ModelLoader._evict_planner_and_confirm_free()` now both wrap their
   entire body in try/except Exception, both fail-closed (return False).
   `http.client.HTTPException` added to both `probe_port_health()` and
   `LlamaServer._check_health()`'s except tuples — confirmed via direct
   Python introspection that `HTTPException`'s MRO is `(HTTPException,
   Exception, BaseException, object)`, i.e. it does NOT inherit from
   OSError/ValueError/URLError, so the addition was necessary and its
   subclasses (BadStatusLine, RemoteDisconnected, IncompleteRead, etc.)
   are all narrowly HTTP-protocol-shaped — not an overly broad catch.

3. **No test spawns a real model.** Confirmed `subprocess.Popen` is now
   patched (and asserted `not_called()`) in both the lock-contention reuse
   test AND the new Bug-1 thermal-restart test. Critically: in the new
   threaded test, all patches (`LlamaServer`, `Path.exists`, `Popen`,
   `load_primary` side_effect) are held active for the entire `with` block
   that both starts AND joins the background thread — this is the exact
   shape that caused the implementer's disclosed real-spawn incidents
   (PID 1388 round 1, PID 13052 round 2 fix-up dev): a thread's real code
   path (`real_load_primary()` captured before the patch, called inside
   the blocking wrapper) can run after a `with patch(...)` block has
   already exited if `t.join()` sits outside it. Here `t.join(timeout=10)`
   is INSIDE the `with`, so this is correct. Check this pattern first any
   time a test in this file (or its descendants) spawns a background
   thread around swap logic.

Also verified:
- `ps aux | grep llama-server` clean (used full binary paths — bare
  `ps`/`grep` broke in this Termux shell instance, see general project
  memory on this).
- `python3 -m pytest tests/ -q` → `280 passed in 0.93s` (or 1.02-1.21s
  across runs), verbatim, run myself, not trusted from implementer.
- `NEW-68`'s "Fix-up round impact" addendum accurately describes the
  guard-widening side effect (`ensure_model()` can now transiently return
  False from pure lock contention even when the primary was already
  healthy) as "worse-but-bounded, not a new unbounded risk". Traced the
  sole consumer (`core/inference.py:_start_server()`, no retry, raises
  RuntimeError, caught generically up the stack to a task-failure, not a
  crash) and agree with that characterization. Not a blocker.
- `NEW-70` (thermal-restart branch's `except Exception: pass` swallowing a
  genuine unload/reload failure and still returning True) — confirmed via
  the diff itself that this exact try/except shape existed in the
  pre-round code (shown as the `-` lines in the diff), i.e. genuinely
  pre-existing, not introduced by this round's restructuring. Correctly
  logged as out-of-scope, not fixed here.
- Scope was clean — only `core/loader_v2.py`, `core/plannd.py`,
  `core/planner_loader.py` (new), `utils/config.py`, the test file (new),
  and `NEW_ISSUES.md` touched. No `codey-start`/`codeyOS`/`lib/` bleed.

**Verdict: Approve.** Live-verifier still needed before calling this fully
done per CLAUDE.md rule 7 — the implementer's disclosed real-spawn
incidents during test development are evidence the swap CAN spawn a real
model correctly, but they were caught by test-authoring mistakes, not a
deliberate single supervised real-model swap cycle with `free -h`
before/after and `ps aux` confirmation of clean unload. Code-review +
unit tests are necessary but not sufficient for a process-lifecycle change
this central (daemon watchdog + get_plan() both drive it in production).

**Reusable technique for future "prove the regression test actually tests
the fix" claims:** back up the file, hand-revert just the fix hunk in
place (not full git stash — more surgical, lets you keep the new test),
run the specific new test, confirm real failure with a real assertion
diff (not just "test failed"), restore from backup, `diff` against backup
to confirm exact restoration, re-run full suite. Cheap and catches
"we wrote a test but it doesn't actually exercise the fix" claims that a
pure code-read can miss.

See also [[new12_inference_launcher_delegation_approved]],
[[new13_thermal_restart_reconsumer_approved]] (the thermal-restart
re-wiring that created the gap in round-1 finding 1).
