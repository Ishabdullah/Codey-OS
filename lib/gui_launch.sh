#
# lib/gui_launch.sh - shared GUI-server launch/PID-file/trap-kill logic
#
# Extracted (NEW-22 residual) from the two independent copies of this
# pattern that used to live inline in `codey-start` and `codeyOS`. This
# file is a library meant to be *sourced*, not executed directly — it has
# no entry point of its own and does nothing until
# `gui_launch_ensure_running` is called by a caller that has already
# sourced it.
#
# Contract with the caller (both current callers already satisfy this
# before sourcing this file, but re-verify if you add a new caller):
#   - CODEY_OS_DIR must already be set to the repo root (both current
#     callers compute this identically via
#     `$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)` before this point).
#   - DAEMON_DIR must already be set to the daemon state dir
#     (`$HOME/.codeyOS` in both current callers) and must exist
#     (both callers `mkdir -p "$DAEMON_DIR"` before this point).
#   - CODEY_GUI_PORT may optionally be set in the environment to override
#     the default port (8888).
#
# Effects of calling gui_launch_ensure_running:
#   - Sets (as plain, non-local shell globals — required so the EXIT trap
#     installed below can still see them after this function returns)
#     GUI_PORT, GUI_PID_FILE, GUI_STARTED_HERE.
#   - If a GUI server is already running (per the PID file + kill -0
#     liveness check), prints an "already running" message and does
#     nothing else — this is the safety short-circuit that prevents a
#     second invocation from starting a duplicate GUI server or clobbering
#     a PID file that belongs to a GUI server this invocation did not
#     start.
#   - Otherwise starts `gui/server.py` in the background, records its PID
#     in `$DAEMON_DIR/gui-server.pid`, and installs a trap that kills
#     *only* that PID (and removes the PID file) on the caller's exit —
#     never on a GUI server this invocation didn't start.
#
# Trap signal set (EXIT only), and why:
#   Neither `codey-start` nor `codeyOS` traps INT/TERM anywhere else in
#   the file (grepped both — no other `trap` calls), so the EXIT-only
#   (`codey-start`) vs. EXIT-INT-TERM (`codeyOS`) split between the two
#   files was drift, not an intentional per-script difference. Converged
#   on EXIT-only, not EXIT-INT-TERM, after on-device testing overturned an
#   earlier draft of this file's reasoning:
#
#   1. No promptness benefit found. `kill -INT` sent to a real wrapper
#      PID while it was blocked on a synchronous foreground child (both a
#      plain `sleep 30` stand-in and the real `python3 ... main.py`) did
#      NOT run the trap until that foreground child exited on its own —
#      identical to plain EXIT's behavior in the same scenario. An
#      earlier version of this comment claimed otherwise from a
#      misread of an initial test; corrected here per the project's
#      "correct the record" rule.
#   2. Trapping INT is actively wrong for this codebase's real Ctrl+C
#      path. `main.py` (grepped: 10+ call sites, e.g. lines 527, 949,
#      1314, 1335, 1423) catches `KeyboardInterrupt` in many places and
#      *continues* its interactive loop — Ctrl+C there commonly cancels
#      one in-flight generation, not the whole session. A real terminal
#      Ctrl+C delivers SIGINT to the whole foreground process group
#      (wrapper + `python3` child together). If the wrapper trapped INT,
#      that keystroke would tear the GUI down immediately (kill the GUI
#      process, remove the PID file) while `main.py` absorbs the same
#      signal and keeps running — the user loses the GUI mid-session
#      without the wrapper actually exiting, and (since a trap without an
#      explicit `exit` doesn't terminate the shell — verified directly:
#      a foreground `sleep` continued running to completion after its
#      wrapper's INT trap fired) nothing re-arms it afterward. EXIT-only
#      does not have this failure mode: it only fires when the wrapper
#      itself is actually exiting.
#   3. The two real termination paths both already work correctly under
#      EXIT-only: (a) if the foreground child actually dies (e.g. from a
#      terminal-wide SIGINT/SIGTERM the child doesn't catch, or normal
#      completion), `wait` returns and the wrapper's own exit — whether
#      via its own pending unhandled signal or just falling off the end
#      of the script — runs the EXIT trap; (b) `codey-stop` (out of this
#      file's scope) kills the GUI server's own recorded PID directly and
#      never signals the wrapper's PID at all, so it doesn't interact
#      with this trap either way.

gui_launch_ensure_running() {
    GUI_PORT="${CODEY_GUI_PORT:-8888}"
    GUI_PID_FILE="$DAEMON_DIR/gui-server.pid"
    GUI_STARTED_HERE="false"

    if [ -f "$GUI_PID_FILE" ] && kill -0 "$(cat "$GUI_PID_FILE" 2>/dev/null)" 2>/dev/null; then
        echo "  GUI    → http://localhost:${GUI_PORT}  (already running)"
    elif [ -f "$CODEY_OS_DIR/gui/server.py" ]; then
        export PYTHONUNBUFFERED=1
        export CODEY_GUI_PORT="$GUI_PORT"
        python3 "$CODEY_OS_DIR/gui/server.py" &
        echo $! > "$GUI_PID_FILE"
        GUI_STARTED_HERE="true"
        echo "  GUI    → http://localhost:${GUI_PORT}"
    fi

    # Stop the GUI server when the wrapper itself exits (Ctrl+C that
    # actually terminates the session, or natural exit) — but only tear
    # it down if this invocation is the one that started it. EXIT-only:
    # see the module-level comment above for why INT/TERM are
    # deliberately not trapped separately here.
    if [ "$GUI_STARTED_HERE" = "true" ]; then
        trap 'echo; echo "  Stopping GUI server..."; kill "$(cat "$GUI_PID_FILE" 2>/dev/null)" 2>/dev/null; rm -f "$GUI_PID_FILE"' EXIT
    fi
}
