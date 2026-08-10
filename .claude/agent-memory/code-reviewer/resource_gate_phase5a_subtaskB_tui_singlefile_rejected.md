---
name: resource-gate-phase5a-subtaskB-tui-singlefile-rejected
description: Phase 4.1/7.4 sub-task B (TUI+GUI interactive-session signal) round 1 — CHANGES REQUESTED, single-slot TUI_PID_FILE can't represent multiple concurrent sessions
metadata:
  type: project
---

Round 1 of Track 3 Phase 5a / 7.4 sub-task B (`core/resource_gate.py`'s
`is_tui_session_active()`/`is_gui_client_connected()`/
`is_interactive_session_active()`, `main.py`'s `_write_tui_pid_file()`/
`_remove_tui_pid_file()`, `gui/server.py`'s `_write_gui_clients_count()`)
was rejected for a real, empirically-reproduced bug in the TUI half.

**The bug:** `TUI_PID_FILE` is a single shared path
(`utils.config.TUI_PID_FILE`), and the feature is explicitly meant to
support multiple concurrent interactive sessions (two terminals). A
single-slot file cannot represent a set of live sessions:

- Session A writes PID_A. Session B starts, opens the file with mode
  `"w"` (truncates), writes PID_B. **A's marker is destroyed at the
  moment of the open/truncate, before B even finishes writing.**
- If B later exits cleanly, `_remove_tui_pid_file()`'s ownership check
  (only unlink if the file currently names *my* PID) correctly stops B
  from deleting a *different* PID that's since overwritten the file —
  but by the time B exits, the file only ever held B's PID anyway. The
  ownership check protects a slot that was already the sole occupant; it
  does not restore A's lost signal.
- Reproduced directly (see conversation transcript): after A writes,
  `is_tui_session_active()` → True; after B overwrites, still True
  (B alive); after B exits and unlinks its own (correctly-owned) entry,
  `is_tui_session_active()` → False even though A is still running and
  at the prompt.
- A second, independent path collapses to the same root cause and is
  arguably worse: if B is killed with SIGKILL (no cleanup), the file
  holds a dead PID_B; `is_tui_session_active()`'s own stale-reaping
  (mirroring `daemon.py:check_pid_file()`'s self-healing) sees a dead
  PID and unlinks the file as "stale" — again erasing A's still-live
  signal, no ordered exit required, triggered by a plain crash.
- A third, narrower race: `_write_tui_pid_file()` does
  `open(path, "w")` (truncates) *before* taking `flock(LOCK_EX)`. In
  that window the file exists but is empty. A concurrent
  `is_tui_session_active()` call in that instant hits `int("")` →
  `ValueError` → treats it as corrupt → unlinks it. Confirmed by direct
  repro that once unlinked mid-write, the writer's later `flush()`
  writes into a since-deleted inode and does NOT recreate the path —
  the just-started session ends up with no PID file at all, invisible
  to the signal for its whole life. This exact `open("w")`-before-`flock`
  ordering also exists in `daemon.py:write_pid_file()`, but is not
  practically reachable there (no concurrent reader in that same
  startup window beyond the already-handled H-4 race); the new TUI file
  has a live, polling, always-running reader (the daemon), making this
  a newly-reachable risk, not just a copy of an already-accepted
  pattern.

**Fix direction handed back:** per-session files, not one shared file —
e.g. `CODEY_STATE_DIR / "tui-sessions" / f"{os.getpid()}.pid"`.
`_write_tui_pid_file()` writes only its own path; `_remove_tui_pid_file()`
unlinks only its own path (ownership becomes structural — no
read-back-and-compare needed, and the truncate-before-lock race becomes
harmless since no other session's file is ever touched);
`is_tui_session_active()` scans the directory and returns True if *any*
entry names a live PID, reaping only entries it proves dead.

**What was fine and should NOT be reworked:** the GUI half
(`is_gui_client_connected()`, `_write_gui_clients_count()`) — single GUI
server process is a valid single-slot design, count updated on both
connect/disconnect, `on_startup` zeroes stale counts, PID cross-check
correctly handles the "server crashed while clients connected" false-
positive case, and the "no GUI PID file at all" fallback (`return True`,
trusting the count) is the right direction for the documented
`python3 gui/server.py`-with-no-launcher case. `is_interactive_session_active()`'s
plain OR composition is fine. NEW-111 (`gui/server.py` reading
`sys.argv[1]` at import time) is accurately described, reproduced with
real pasted output, and correctly left unfixed/out-of-scope.

**Process lesson:** the 100 new isolated tests (`tests/test_resource_gate.py`
additions, `tests/test_main_tui_lock.py`, `tests/test_gui_clients_signal.py`)
all passed — precisely because none of them constructed the two-concurrent-
TUI-session scenario. A green test suite here was not evidence of
correctness; the multi-session claim needed an actual two-process/PID
repro, which the implementer's own docstrings asserted but never tested.
When a task's premise is explicitly "N concurrent instances of X are a
normal supported case," write (or demand) a test that actually
instantiates N ≥ 2 and interleaves their write/remove calls — a test that
only checks "my removal doesn't delete someone else's *currently
correctly-recorded* PID" doesn't cover "my overwrite destroys someone
else's recording in the first place."

See also [[daemon_self_pid_check_verified]] for the sibling single-daemon
PID-file pattern this diverges from (single-instance vs. multi-instance
semantics require genuinely different file layouts, not the same file
with an added ownership check).
