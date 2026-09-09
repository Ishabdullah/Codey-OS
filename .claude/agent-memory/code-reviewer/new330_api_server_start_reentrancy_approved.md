---
name: new330-api-server-start-reentrancy-approved
description: NEW-330 RestoriconAPIServer.start() double-guard (_is_running + _run_start_emitted) — approved; verified real stop()->start() socket-crash gap is honestly scoped, not hidden
metadata:
  type: project
---

`restoricon_core/api/server.py`'s `RestoriconAPIServer.start()` had no re-entrancy
guard — two in-process `start()` calls duplicated a `run_start` telemetry record
under the same process-wide `run_id`. Fix adds two separate flags: (1) `_is_running`
early-return no-op for back-to-back double-start, (2) `_run_start_emitted` (never
reset by `stop()`) gating the telemetry call specifically, since `run_id` is a
process-wide singleton and `stop()` resets `_is_running` — without (2), a
`start()->stop()->start()` sequence would pass guard (1) and duplicate the record
anyway.

Verified independently, not just re-read:
- Negative control: manually stripped the `_run_start_emitted` guard (unconditional
  `_record_telemetry_run_start()` call), ran
  `test_api_server_stop_then_start_does_not_duplicate_run_start` directly ->
  reproduced `assert 2 == 1` exactly as the implementer's ledger entry claimed.
- The implementer's own self-flagged, unfixed finding — that `stop()` closes the
  httpd socket/db, so a subsequent `start(background=True)` crashes inside the
  spawned thread (`ValueError: Invalid file descriptor: -1` in `serve_forever()`'s
  selector registration) — is REAL. Reproduced standalone with
  `threading.excepthook` capturing the exact exception. Confirmed the crash is
  async (happens inside the background thread, not synchronously at the
  `start()`/`stop()` call sites in the test), so the test's
  `@pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")`
  is honestly scoped to suppress exactly this known, documented crash — not
  papering over a different, undocumented failure. The second `stop()` call in that
  test (closing an already-closed socket/db a second time) does not itself raise;
  `socket.close()` and `sqlite3.Connection.close()` are both idempotent, and
  `BaseServer.shutdown()`'s wait on `__is_shut_down` doesn't deadlock because
  `serve_forever()`'s `finally` block sets that event even when the selector
  registration raises inside the `try`.
- Full suite: 1545 passed, 1 skipped, 0 failures (226.62s) — matches expectation,
  no regression.
- Cross-checked the "matches LlamaServer/EmbedServer's double-start convention"
  claim: true at the level of intent (both return early on an already-running
  instance instead of re-running startup side effects) but the actual mechanisms
  differ a lot — `LlamaServer.start()` and `EmbedServer.start()` do a live
  process/port/health check plus adoption-of-existing-occupant logic, not a plain
  boolean flag. This is a fair analogy, not a false one; noted as a minor imprecision,
  not a blocker.

**Why:** the `run_id`-is-a-process-wide-singleton reasoning for needing TWO
separate flags (not one) is the non-obvious part here — an `_is_running`-only
guard looks sufficient until you specifically trace a stop/start cycle.

**How to apply:** for any future re-entrancy-guard fix in this codebase, check
whether the thing being guarded (like a telemetry emission tied to a process-wide
id) has a lifetime that outlives the instance-level running/stopped state being
used to gate it — a single boolean tied to "currently running" is the wrong scope
if the guarded action should happen at most once ever, not once per start/stop
cycle. Also: **`git checkout -- <path>` during live verification wiped the ENTIRE
target diff back to HEAD**, not just my temporary negative-control edit — had to
reconstruct via `git apply` from a saved patch of the original diff. Confirmed this
is the same trap logged in `git_checkout_path_wipes_uncommitted_diff.md`; when
doing a negative-control edit + revert on a file with real uncommitted changes,
either use `git stash` (push/pop) or restore by hand-editing back, never
`git checkout -- <path>` to "undo" a scratch edit.
