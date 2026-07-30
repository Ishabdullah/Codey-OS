---
name: daemon-self-pid-check-verified
description: core/daemon.py's check_pid_file() "if pid == os.getpid(): return False" guard reviewed and approved (commit pending as of 2026-07-29) — how to re-verify it if touched again
metadata:
  type: project
---

`check_pid_file()` in `core/daemon.py` has a guard: if the PID found in
`PID_FILE` equals `os.getpid()`, return False (not running) instead of
doing `os.kill(pid, 0)`. This exists because `codeydOS`'s `start_daemon()`
(shell script, repo root, already committed in 802e4c8) writes
`PID_FILE` with `$!` immediately after backgrounding the python process —
*before* `core/daemon.py`'s own `write_pid_file()` runs later in
`Daemon.run()`. So on every normal startup, `check_pid_file()` finds its
own PID already in the file.

**Why this is NOT the same bug class as the earlier self-race regression**
(a "well-intentioned, already-reviewed fix" mentioned in CLAUDE.md rule 4):
that earlier bug misread *external* state (a preemptively-written PID) as
evidence of a *different* process running. This guard instead reasons
from an OS invariant — `os.getpid()` can only ever equal the calling
process's own PID, never another live process's PID — so `pid ==
os.getpid()` can never be a false positive for "another instance is
running." Verified by reading `codeydOS`'s `start_daemon()` directly
(lines ~171-183) to confirm the premise in the code comment is real, not
just asserted.

**One residual nuance, not a bug:** `ccos/plugins/system/daemon_control/daemon_control.py`'s
`daemon_check_pid_file()` calls `check_pid_file()` and could run *inside*
the daemon's own process (as an agent capability during task execution).
In that case it will now return `{"running": False}` even though the
daemon is obviously running — because it's asking "is *another* instance
running" (matching `check_pid_file()`'s own docstring), not "is the
daemon running at all." Confirmed this matches the documented contract,
not a regression, but flag it again if anyone changes that docstring's
meaning or if `daemon_is_running()` (the socket-probe version, unaffected)
gets conflated with `check_pid_file()` in future refactors.

**How to apply:** If `core/daemon.py`'s PID-file logic changes again,
re-check `codeydOS`'s `start_daemon()`/`stop_daemon()` for whether the
premise ("shell pre-writes PID before Python's own write") still holds —
don't assume a code comment describing external state is accurate without
opening the referenced script.
