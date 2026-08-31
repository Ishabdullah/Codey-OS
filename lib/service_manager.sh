#!/data/data/com.termux/files/usr/bin/bash
#
# lib/service_manager.sh - Codey-OS Unified Service Manager
#
# Orchestrates daemon, Restoricon API server, Codey-Aigentik, Cloudflare tunnel,
# and GUI server lifecycles with PID tracking and clean signal handling.
# Follows Rule 3: Never kill processes by bare name pattern.
#

CODEY_OS_DIR="${CODEY_OS_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
DAEMON_DIR="${CODEY_STATE_DIR:-$HOME/.codeyOS}"

DAEMON_PID_FILE="$DAEMON_DIR/codeyOS.pid"
DAEMON_LOG_FILE="$DAEMON_DIR/codeyOS.log"

RESTORICON_PID_FILE="$DAEMON_DIR/restoricon-api.pid"
RESTORICON_LOG_FILE="$DAEMON_DIR/restoricon-api.log"

AIGENTIK_PID_FILE="$DAEMON_DIR/aigentik.pid"
AIGENTIK_LOG_FILE="$DAEMON_DIR/aigentik.log"

CLOUDFLARED_PID_FILE="$DAEMON_DIR/cloudflared.pid"
CLOUDFLARED_LOG_FILE="$DAEMON_DIR/cloudflared.log"

GUI_PID_FILE="$DAEMON_DIR/gui-server.pid"
GUI_LOG_FILE="$DAEMON_DIR/gui-server.log"

mkdir -p "$DAEMON_DIR"

# ── Core PID lifecycle helpers ───────────────────────────────────────────────

svc_is_running() {
    local pid_file="$1"
    if [ ! -f "$pid_file" ]; then
        return 1
    fi

    local pid
    pid=$(cat "$pid_file" 2>/dev/null || echo "")
    if [ -z "$pid" ]; then
        rm -f "$pid_file"
        return 1
    fi

    if kill -0 "$pid" 2>/dev/null; then
        return 0
    else
        rm -f "$pid_file"
        return 1
    fi
}

svc_stop_by_pid() {
    local pid_file="$1"
    local svc_name="$2"

    if ! svc_is_running "$pid_file"; then
        echo "  $svc_name → not running"
        return 0
    fi

    local pid
    pid=$(cat "$pid_file" 2>/dev/null || echo "")
    if [ -z "$pid" ]; then
        rm -f "$pid_file"
        echo "  $svc_name → not running"
        return 0
    fi

    echo "  $svc_name → stopping (PID $pid)..."
    kill -TERM "$pid" 2>/dev/null || true

    for i in {1..10}; do
        if ! kill -0 "$pid" 2>/dev/null; then
            rm -f "$pid_file"
            echo "  $svc_name → stopped"
            return 0
        fi
        sleep 0.5
    done

    echo "  $svc_name → force stopping (PID $pid)..."
    kill -9 "$pid" 2>/dev/null || true
    rm -f "$pid_file"
    echo "  $svc_name → stopped (forced)"
    return 0
}

# ── Service: Daemon ──────────────────────────────────────────────────────────

start_daemon() {
    if svc_is_running "$DAEMON_PID_FILE"; then
        echo "  Daemon      → already running (PID $(cat "$DAEMON_PID_FILE"))"
    elif [ -f "$CODEY_OS_DIR/codeydOS" ]; then
        echo "  Daemon      → starting..."
        bash "$CODEY_OS_DIR/codeydOS" start
    fi
}

stop_daemon() {
    if [ -f "$CODEY_OS_DIR/codeydOS" ]; then
        bash "$CODEY_OS_DIR/codeydOS" stop
    else
        svc_stop_by_pid "$DAEMON_PID_FILE" "Daemon"
    fi
}

status_daemon() {
    if svc_is_running "$DAEMON_PID_FILE"; then
        echo "  Daemon:          running (PID $(cat "$DAEMON_PID_FILE"))"
    else
        echo "  Daemon:          stopped"
    fi
}

# ── Service: Restoricon Core API Server ─────────────────────────────────────

start_restoricon() {
    if svc_is_running "$RESTORICON_PID_FILE"; then
        echo "  Restoricon  → already running (PID $(cat "$RESTORICON_PID_FILE"))"
        return 0
    fi

    local rest_cfg
    rest_cfg=$(python3 -c "
import sys; sys.path.insert(0, '$CODEY_OS_DIR')
from utils.config import get_restoricon_api_config
c = get_restoricon_api_config()
print(f\"{c['host']}|{c['port']}|{c['db_path']}\")
" 2>/dev/null || echo "127.0.0.1|8770|$DAEMON_DIR/restoricon.db")

    local r_host r_port r_db
    IFS='|' read -r r_host r_port r_db <<< "$rest_cfg"
    r_host="${r_host:-127.0.0.1}"
    r_port="${r_port:-8770}"
    r_db="${r_db:-$DAEMON_DIR/restoricon.db}"

    export PYTHONPATH="$CODEY_OS_DIR:${PYTHONPATH:-}"
    nohup python3 -m restoricon_core.api.server --host "$r_host" --port "$r_port" --db "$r_db" >> "$RESTORICON_LOG_FILE" 2>&1 &
    local r_pid=$!
    echo "$r_pid" > "$RESTORICON_PID_FILE"
    sleep 0.5

    if kill -0 "$r_pid" 2>/dev/null; then
        echo "  Restoricon  → http://${r_host}:${r_port} (PID $r_pid)"
    else
        echo "  Restoricon  → ERROR: failed to start. Check $RESTORICON_LOG_FILE"
        rm -f "$RESTORICON_PID_FILE"
        return 1
    fi
}

stop_restoricon() {
    svc_stop_by_pid "$RESTORICON_PID_FILE" "Restoricon API"
}

status_restoricon() {
    if svc_is_running "$RESTORICON_PID_FILE"; then
        echo "  Restoricon:      running (PID $(cat "$RESTORICON_PID_FILE"))"
    else
        echo "  Restoricon:      stopped"
    fi
}

# ── Service: Codey-Aigentik ─────────────────────────────────────────────────

start_aigentik() {
    if svc_is_running "$AIGENTIK_PID_FILE"; then
        echo "  Aigentik    → already running (PID $(cat "$AIGENTIK_PID_FILE"))"
        return 0
    fi

    local aig_cfg
    aig_cfg=$(python3 -c "
import sys; sys.path.insert(0, '$CODEY_OS_DIR')
from utils.config import get_aigentik_config
c = get_aigentik_config()
print(f\"{c['dir']}|{c['port']}\")
" 2>/dev/null || echo "$HOME/Codey-Aigentik|8000")

    local a_dir a_port
    IFS='|' read -r a_dir a_port <<< "$aig_cfg"
    a_dir="${a_dir:-$HOME/Codey-Aigentik}"

    if [ ! -d "$a_dir" ]; then
        return 0
    fi

    local entrypoint=""
    if [ -f "$a_dir/main.py" ]; then
        entrypoint="python3 main.py"
    elif [ -f "$a_dir/app.py" ]; then
        entrypoint="python3 app.py"
    elif [ -f "$a_dir/server.py" ]; then
        entrypoint="python3 server.py"
    elif [ -f "$a_dir/run.sh" ]; then
        entrypoint="bash run.sh"
    fi

    if [ -z "$entrypoint" ]; then
        return 0
    fi

    echo "  Aigentik    → starting from $a_dir..."
    (cd "$a_dir" && nohup $entrypoint >> "$AIGENTIK_LOG_FILE" 2>&1 & echo $! > "$AIGENTIK_PID_FILE")
    sleep 0.5
    local a_pid
    a_pid=$(cat "$AIGENTIK_PID_FILE" 2>/dev/null || echo "")
    if [ -n "$a_pid" ] && kill -0 "$a_pid" 2>/dev/null; then
        echo "  Aigentik    → started (PID $a_pid)"
    else
        echo "  Aigentik    → ERROR: failed to start. Check $AIGENTIK_LOG_FILE"
        rm -f "$AIGENTIK_PID_FILE"
        return 1
    fi
}

stop_aigentik() {
    svc_stop_by_pid "$AIGENTIK_PID_FILE" "Codey-Aigentik"
}

status_aigentik() {
    if svc_is_running "$AIGENTIK_PID_FILE"; then
        echo "  Aigentik:        running (PID $(cat "$AIGENTIK_PID_FILE"))"
    else
        echo "  Aigentik:        stopped"
    fi
}

# ── Service: Cloudflare Tunnel ──────────────────────────────────────────────

start_cloudflare() {
    if svc_is_running "$CLOUDFLARED_PID_FILE"; then
        echo "  Cloudflare  → already running (PID $(cat "$CLOUDFLARED_PID_FILE"))"
        return 0
    fi

    if ! command -v cloudflared &>/dev/null; then
        return 0
    fi

    local token
    token=$(python3 -c "
import sys; sys.path.insert(0, '$CODEY_OS_DIR')
from utils.config import get_cloudflare_tunnel_token
t = get_cloudflare_tunnel_token()
print(t if t else '')
" 2>/dev/null || echo "")

    if [ -z "$token" ]; then
        return 0
    fi

    echo "  Cloudflare  → starting tunnel..."
    nohup cloudflared tunnel run --token "$token" >> "$CLOUDFLARED_LOG_FILE" 2>&1 &
    local c_pid=$!
    echo "$c_pid" > "$CLOUDFLARED_PID_FILE"
    sleep 0.5
    if kill -0 "$c_pid" 2>/dev/null; then
        echo "  Cloudflare  → tunnel active (PID $c_pid)"
    else
        echo "  Cloudflare  → ERROR: tunnel failed to start. Check $CLOUDFLARED_LOG_FILE"
        rm -f "$CLOUDFLARED_PID_FILE"
        return 1
    fi
}

stop_cloudflare() {
    svc_stop_by_pid "$CLOUDFLARED_PID_FILE" "Cloudflare Tunnel"
}

status_cloudflare() {
    if svc_is_running "$CLOUDFLARED_PID_FILE"; then
        echo "  Cloudflare:      running (PID $(cat "$CLOUDFLARED_PID_FILE"))"
    else
        echo "  Cloudflare:      stopped"
    fi
}

# ── Service: GUI Server ─────────────────────────────────────────────────────

start_gui() {
    local with_trap="${1:-false}"

    local gui_cfg
    gui_cfg=$(python3 -c "
import sys; sys.path.insert(0, '$CODEY_OS_DIR')
from utils.config import get_gui_config
c = get_gui_config()
print(f\"{c['host']}|{c['port']}\")
" 2>/dev/null || echo "127.0.0.1|8888")

    local g_host g_port
    IFS='|' read -r g_host g_port <<< "$gui_cfg"
    g_host="${g_host:-127.0.0.1}"
    g_port="${g_port:-8888}"

    export CODEY_GUI_PORT="$g_port"
    export CODEY_GUI_HOST="$g_host"
    export PYTHONUNBUFFERED=1

    local started_here="false"
    if svc_is_running "$GUI_PID_FILE"; then
        echo "  GUI         → http://${g_host}:${g_port} (already running)"
    elif [ -f "$CODEY_OS_DIR/gui/server.py" ]; then
        nohup python3 "$CODEY_OS_DIR/gui/server.py" >> "$GUI_LOG_FILE" 2>&1 &
        local g_pid=$!
        echo "$g_pid" > "$GUI_PID_FILE"
        started_here="true"
        sleep 0.5
        if kill -0 "$g_pid" 2>/dev/null; then
            echo "  GUI         → http://${g_host}:${g_port} (PID $g_pid)"
        else
            echo "  GUI         → ERROR: failed to start. Check $GUI_LOG_FILE"
            rm -f "$GUI_PID_FILE"
            return 1
        fi
    fi

    if [ "$with_trap" = "true" ] && [ "$started_here" = "true" ]; then
        trap 'echo; echo "  Stopping GUI server..."; kill "$(cat "$GUI_PID_FILE" 2>/dev/null)" 2>/dev/null; rm -f "$GUI_PID_FILE"' EXIT
    fi
}

stop_gui() {
    svc_stop_by_pid "$GUI_PID_FILE" "GUI server"
}

status_gui() {
    if svc_is_running "$GUI_PID_FILE"; then
        echo "  GUI server:      running (PID $(cat "$GUI_PID_FILE"))"
    else
        echo "  GUI server:      stopped"
    fi
}

# ── Composite Management Operations ──────────────────────────────────────────

start_all_services() {
    local with_gui_trap="${1:-false}"
    mkdir -p "$DAEMON_DIR"
    start_daemon
    start_restoricon
    start_aigentik
    start_cloudflare
    start_gui "$with_gui_trap"
}

stop_all_services() {
    echo "Stopping Codey-OS services..."
    stop_cloudflare
    stop_aigentik
    stop_restoricon
    stop_gui
    stop_daemon
    echo
    echo "  All Codey-OS services stopped."
}

status_all_services() {
    echo "Codey-OS Services Status:"
    echo "──────────────────────────────────────────────"
    status_daemon
    status_restoricon
    status_aigentik
    status_cloudflare
    status_gui
    echo "──────────────────────────────────────────────"
    if [ -f "$CODEY_OS_DIR/codeydOS" ]; then
        bash "$CODEY_OS_DIR/codeydOS" status || true
    fi
}

show_service_logs() {
    local svc="$1"
    case "$svc" in
        daemon|codeyOS)
            tail -n 50 "$DAEMON_LOG_FILE" 2>/dev/null || echo "No log found for daemon ($DAEMON_LOG_FILE)."
            ;;
        restoricon|api)
            tail -n 50 "$RESTORICON_LOG_FILE" 2>/dev/null || echo "No log found for restoricon ($RESTORICON_LOG_FILE)."
            ;;
        aigentik)
            tail -n 50 "$AIGENTIK_LOG_FILE" 2>/dev/null || echo "No log found for aigentik ($AIGENTIK_LOG_FILE)."
            ;;
        cloudflare|cloudflared|tunnel)
            tail -n 50 "$CLOUDFLARED_LOG_FILE" 2>/dev/null || echo "No log found for cloudflare ($CLOUDFLARED_LOG_FILE)."
            ;;
        gui)
            tail -n 50 "$GUI_LOG_FILE" 2>/dev/null || echo "No log found for gui ($GUI_LOG_FILE)."
            ;;
        *)
            echo "Available logs: daemon, restoricon, aigentik, cloudflare, gui"
            echo
            for logfile in "$DAEMON_LOG_FILE" "$RESTORICON_LOG_FILE" "$AIGENTIK_LOG_FILE" "$CLOUDFLARED_LOG_FILE" "$GUI_LOG_FILE"; do
                if [ -f "$logfile" ]; then
                    echo "=== $(basename "$logfile") (last 10 lines) ==="
                    tail -n 10 "$logfile"
                    echo
                fi
            done
            ;;
    esac
}

show_service_config() {
    python3 -c "
import sys, json
sys.path.insert(0, '$CODEY_OS_DIR')
from utils.config import (
    get_config_file_path, load_user_config,
    get_cloudflare_tunnel_token, get_restoricon_api_config,
    get_aigentik_config, get_gui_config
)
cfg_path = get_config_file_path()
print(f'Config file: {cfg_path} (exists: {cfg_path.is_file()})')
print('\nActive configurations:')
print(f'  • Cloudflare Token: {\"configured\" if get_cloudflare_tunnel_token() else \"not set\"}')
print(f'  • Restoricon API:   {get_restoricon_api_config()}')
print(f'  • Aigentik:         {get_aigentik_config()}')
print(f'  • GUI Server:       {get_gui_config()}')
print('\nLoaded raw config:')
print(json.dumps(load_user_config(), indent=2))
"
}

show_help() {
    cat << 'EOF'
Codey-OS Unified Command & Service Orchestrator

Usage:
  codey [command] [arguments...]

Commands:
  (no args)       Start all services and enter interactive TUI (codeyOS)
  start           Start all services in background
  stop            Stop all Codey-OS services cleanly
  status          Show status of all services and daemon model health
  restart         Restart all services cleanly
  logs [service]  Show service logs (daemon, restoricon, aigentik, cloudflare, gui)
  config          Show active configuration settings
  help, --help    Show this help message

Options & Passthrough:
  Any other command or flag (e.g. codey "Fix bug in main.py") automatically
  ensures all services are running and passes arguments directly to codeyOS.
EOF
}
