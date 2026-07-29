#!/data/data/com.termux/files/usr/bin/bash
# CODEY-OS GUI launcher
# Usage:  bash gui/start.sh [port] [--dashboard-only]
#
# Starts the browser GUI in the background, then drops you into the
# interactive codeyOS session in this terminal — both live at once.
#
# Dashboard-only mode: pass --dashboard-only (or set
# CODEY_GUI_DASHBOARD_ONLY=1) to skip the main.py model-load chain
# entirely and just serve the GUI/dashboard. Useful for viewing the
# dashboard without paying the cost of a full model load. Ctrl+C still
# cleanly stops the GUI server via the same trap used in the default mode.
#
# Requires:  pip install aiohttp   (already in requirements.txt)

set -e
cd "$(dirname "$0")/.."

DASHBOARD_ONLY="${CODEY_GUI_DASHBOARD_ONLY:-0}"
PORT=""
for arg in "$@"; do
  if [ "$arg" = "--dashboard-only" ]; then
    DASHBOARD_ONLY=1
  else
    PORT="$arg"
  fi
done
PORT="${PORT:-8888}"
export CODEY_GUI_PORT="$PORT"
export PYTHONUNBUFFERED=1

echo ""
echo "  ╔══════════════════════════════════════╗"
echo "  ║    CODEY-OS  ·  GUI + CLI LAUNCHER   ║"
echo "  ╠══════════════════════════════════════╣"
echo "  ║  Browser → http://localhost:${PORT}      ║"
echo "  ║  Terminal → interactive codeyOS below ║"
echo "  ╚══════════════════════════════════════╝"
echo ""

# ── Start GUI server in background ──────────────────────────────────────────
python gui/server.py &
GUI_PID=$!
echo "  GUI server started (PID $GUI_PID)  →  http://localhost:${PORT}"
echo "  Open that URL in your browser, then use the terminal below as usual."
echo ""
echo "  (Ctrl+C stops everything)"
echo ""

# Kill the GUI server when this script exits (Ctrl+C or natural exit)
trap 'echo ""; echo "  Stopping GUI server..."; kill "$GUI_PID" 2>/dev/null; exit 0' INT TERM EXIT

# ── Drop into interactive codeyOS in the foreground ──────────────────────────
if [ "$DASHBOARD_ONLY" = "1" ]; then
  echo "  Dashboard-only mode: not starting main.py. Waiting on GUI server..."
  wait "$GUI_PID"
else
  python main.py
fi
