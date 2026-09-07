#!/data/data/com.termux/files/usr/bin/bash
#
# lib/service_manager.sh - Codey-OS Unified Service Manager
#
# Orchestrates daemon, Restoricon API server, Codey-Aigentik, Cloudflare tunnel,
# lifecycles with PID tracking and clean signal handling.
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

LITESTREAM_PID_FILE="$DAEMON_DIR/litestream.pid"
LITESTREAM_LOG_FILE="$DAEMON_DIR/litestream.log"

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

# Detect the launch entrypoint script for an Aigentik-style directory.
# Echoes the bare script basename (e.g. "main.py", "index.js") — the single
# source of truth for both the launch command and orphan cmdline matching.
# Empty output means no recognizable entrypoint exists in $1.
svc_detect_entrypoint_script() {
    local a_dir="$1"
    local candidate
    for candidate in main.py app.py server.py run.sh index.js start.sh; do
        if [ -f "$a_dir/$candidate" ]; then
            echo "$candidate"
            return 0
        fi
    done
}

# Build the shell command that runs a detected entrypoint script.
svc_entrypoint_command() {
    local script="$1"
    case "$script" in
        *.py) echo "python3 $script" ;;
        *.sh) echo "bash $script" ;;
        *.js) echo "node $script" ;;
        "")   echo "" ;;
        *)    echo "$script" ;;
    esac
}

# Find live processes whose working directory canonically matches $1.
#
# Rule 3 compliance: a cwd match ALONE is not sufficient to identify (and
# subsequently kill) a process — any node REPL, editor language server, or
# `npm test` run launched from that directory would match. When $3 (the
# expected entrypoint token, e.g. "index.js") is supplied, a PID is only
# returned if its /proc/PID/cmdline ALSO contains that token. Every real
# call site in this file passes $3; the $3-empty path exists only for the
# 2-arg unit test of the cwd-matching mechanism itself and must not be
# used on any code path that then terminates the matched PIDs.
svc_find_orphans_by_cwd() {
    local target_dir="$1"
    local proc_filter="${2:-node}"
    local entrypoint_token="${3:-}"

    if [ -z "$target_dir" ] || [ ! -d "$target_dir" ]; then
        return 0
    fi

    local canonical_target
    canonical_target=$(cd "$target_dir" 2>/dev/null && pwd -P)
    [ -z "$canonical_target" ] && return 0

    local cand_pids=()
    if command -v pgrep &>/dev/null; then
        mapfile -t cand_pids < <(pgrep "$proc_filter" 2>/dev/null || true)
    elif [ -d /proc ]; then
        # Fallback if pgrep is not installed: inspect cmdline for proc_filter
        for p in /proc/[0-9]*; do
            [ -d "$p" ] || continue
            local cmd
            cmd=$(cat "$p/cmdline" 2>/dev/null | tr '\0' ' ' || true)
            if [[ "$cmd" =~ $proc_filter ]]; then
                cand_pids+=("${p##*/}")
            fi
        done
    fi

    local matched_pids=()
    for pid in "${cand_pids[@]}"; do
        [ -n "$pid" ] || continue
        [[ "$pid" =~ ^[0-9]+$ ]] || continue
        [ -d "/proc/$pid" ] || continue

        local proc_cwd
        proc_cwd=$(readlink "/proc/$pid/cwd" 2>/dev/null || true)
        [ "$proc_cwd" = "$canonical_target" ] || continue

        if [ -n "$entrypoint_token" ]; then
            local proc_cmd
            proc_cmd=$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null || true)
            case " $proc_cmd " in
                *" $entrypoint_token "*|*"/$entrypoint_token "*) ;;
                *) continue ;;
            esac
        fi
        matched_pids+=("$pid")
    done

    echo "${matched_pids[*]}"
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

    # Single source of truth for the entrypoint: used both to launch the
    # process below and to two-factor-match orphans (cwd + this token).
    local entry_script entrypoint
    entry_script=$(svc_detect_entrypoint_script "$a_dir")
    entrypoint=$(svc_entrypoint_command "$entry_script")

    local tracked_pid=""
    if svc_is_running "$AIGENTIK_PID_FILE"; then
        tracked_pid=$(cat "$AIGENTIK_PID_FILE" 2>/dev/null || echo "")
    fi

    if [ -z "$entrypoint" ]; then
        # No recognizable entrypoint: can't launch, and can't safely scan for
        # orphans without a token (Rule 3 invariant). Report tracked state only.
        if [ -n "$tracked_pid" ]; then
            echo "  Aigentik    → already running (PID $tracked_pid)"
        fi
        return 0
    fi

    # Find live processes running THIS entrypoint from the Aigentik directory.
    # Guard: if Aigentik ever spawns long-lived node children via
    # child_process.fork / cluster / worker_threads that re-exec the same
    # entrypoint script, they would share cwd + token and be misidentified
    # as orphans and killed while the tracked parent survives. Revisit the
    # identification (e.g. add a parent-PID / process-group check) then.
    local all_found_pids
    all_found_pids=$(svc_find_orphans_by_cwd "$a_dir" "node" "$entry_script")
    local orphan_pids=()
    for p in $all_found_pids; do
        if [ -n "$tracked_pid" ] && [ "$p" = "$tracked_pid" ]; then
            continue
        fi
        orphan_pids+=("$p")
    done

    # If already running and no orphans exist, nothing to do
    if [ -n "$tracked_pid" ] && [ ${#orphan_pids[@]} -eq 0 ]; then
        echo "  Aigentik    → already running (PID $tracked_pid)"
        return 0
    fi

    # If orphans exist, terminate them before starting fresh
    if [ ${#orphan_pids[@]} -gt 0 ]; then
        echo "  ⚠ Aigentik → found ${#orphan_pids[@]} orphaned process(es) not tracked by PID file: ${orphan_pids[*]} — terminating before starting fresh"
        for opid in "${orphan_pids[@]}"; do
            echo "  Terminating orphan Aigentik process (PID $opid)..."
            kill -TERM "$opid" 2>/dev/null || true
            for i in {1..10}; do
                if ! kill -0 "$opid" 2>/dev/null; then
                    break
                fi
                sleep 0.5
            done
            if kill -0 "$opid" 2>/dev/null; then
                kill -9 "$opid" 2>/dev/null || true
            fi
        done
    fi

    # If tracked instance was already running, return after clearing orphans
    if [ -n "$tracked_pid" ]; then
        echo "  Aigentik    → running (PID $tracked_pid)"
        return 0
    fi

    echo "  Aigentik    → starting from $a_dir..."
    (cd "$a_dir" && exec nohup $entrypoint >> "$AIGENTIK_LOG_FILE" 2>&1) &
    local a_pid=$!
    echo "$a_pid" > "$AIGENTIK_PID_FILE"
    sleep 0.5
    # KNOWN RACE (NEW-268, not fixed this round — needs a lockfile, out of
    # scope): two concurrent `codey start` runs are not serialized. Process B
    # can scan between A's spawn and this PID-file write, kill A's fresh
    # node as an "orphan", making A's kill -0 below fail so A does the
    # rm -f — deleting B's PID entry and leaving B's node untracked.
    if kill -0 "$a_pid" 2>/dev/null; then
        echo "  Aigentik    → started (PID $a_pid)"
    else
        echo "  Aigentik    → ERROR: failed to start. Check $AIGENTIK_LOG_FILE"
        rm -f "$AIGENTIK_PID_FILE"
        return 1
    fi
}

stop_aigentik() {
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

    # Same entrypoint token used by start_aigentik — required for Rule 3
    # two-factor orphan identification (cwd match alone is not enough).
    local entry_script
    entry_script=$(svc_detect_entrypoint_script "$a_dir")

    svc_stop_by_pid "$AIGENTIK_PID_FILE" "Codey-Aigentik"

    # Invariant: never run a terminate path with an empty entrypoint token —
    # that would collapse svc_find_orphans_by_cwd to cwd-only matching and
    # SIGKILL unrelated node processes sharing $a_dir (Rule 3).
    if [ -z "$entry_script" ]; then
        echo "  Aigentik    → no recognizable entrypoint in $a_dir; skipping orphan scan"
        return 0
    fi

    # Check for any remaining orphans running from Aigentik directory
    local remaining_pids
    remaining_pids=$(svc_find_orphans_by_cwd "$a_dir" "node" "$entry_script")
    if [ -n "$remaining_pids" ]; then
        local r_array=($remaining_pids)
        echo "  ⚠ Aigentik → found ${#r_array[@]} remaining process(es) after stop: $remaining_pids — terminating"
        for opid in "${r_array[@]}"; do
            echo "  Terminating remaining Aigentik process (PID $opid)..."
            kill -TERM "$opid" 2>/dev/null || true
            for i in {1..10}; do
                if ! kill -0 "$opid" 2>/dev/null; then
                    break
                fi
                sleep 0.5
            done
            if kill -0 "$opid" 2>/dev/null; then
                kill -9 "$opid" 2>/dev/null || true
            fi
        done
    fi

    # Verify and report final state
    local final_pids
    final_pids=$(svc_find_orphans_by_cwd "$a_dir" "node" "$entry_script")
    if [ -z "$final_pids" ]; then
        echo "  Aigentik    → fully stopped, 0 processes remaining"
    else
        echo "  ⚠ Aigentik  → WARNING: processes still alive: $final_pids"
    fi
}

status_aigentik() {
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

    # Same entrypoint token used by start_aigentik — required for Rule 3
    # two-factor orphan identification (cwd match alone is not enough).
    local entry_script
    entry_script=$(svc_detect_entrypoint_script "$a_dir")

    local tracked_pid=""
    if svc_is_running "$AIGENTIK_PID_FILE"; then
        tracked_pid=$(cat "$AIGENTIK_PID_FILE" 2>/dev/null || echo "")
    fi

    # Without a known entrypoint token, fall back to a PID-file-only report
    # rather than a cwd-only scan (same invariant as stop_aigentik).
    if [ -z "$entry_script" ]; then
        if [ -n "$tracked_pid" ]; then
            echo "  Aigentik:        running (PID $tracked_pid)"
        else
            echo "  Aigentik:        stopped"
        fi
        return 0
    fi

    local all_found_pids
    all_found_pids=$(svc_find_orphans_by_cwd "$a_dir" "node" "$entry_script")
    local orphan_pids=()
    for p in $all_found_pids; do
        if [ -n "$tracked_pid" ] && [ "$p" = "$tracked_pid" ]; then
            continue
        fi
        orphan_pids+=("$p")
    done

    if [ -n "$tracked_pid" ]; then
        if [ ${#orphan_pids[@]} -gt 0 ]; then
            echo "  Aigentik:        running (PID $tracked_pid) [⚠ ${#orphan_pids[@]} orphan(s): ${orphan_pids[*]}]"
        else
            echo "  Aigentik:        running (PID $tracked_pid)"
        fi
    else
        if [ ${#orphan_pids[@]} -gt 0 ]; then
            echo "  Aigentik:        stopped (PID file) [⚠ ${#orphan_pids[@]} UNTRACKED orphan(s) running: ${orphan_pids[*]}]"
        else
            echo "  Aigentik:        stopped"
        fi
    fi
}

# ── Service: Litestream ───────────────────────────────────────────────────────

start_litestream() {
    local l_dir="$DAEMON_DIR"
    local l_token="replicate"
    local l_bin="$HOME/go/bin/litestream"
    local l_cfg="$HOME/.codeyOS/litestream.yml"
    
    if [ ! -f "$l_bin" ]; then
        return 0
    fi
    
    # Generate litestream.yml
    python3 "$CODEY_OS_DIR/core/setup_litestream.py" || return 1
    
    if [ ! -f "$l_cfg" ]; then
        return 0
    fi
    
    # Propagate GCS credentials if set in environment (used by Litestream in background)
    if [ -n "$GOOGLE_APPLICATION_CREDENTIALS" ]; then
        export GOOGLE_APPLICATION_CREDENTIALS
    fi


    local tracked_pid=""
    if svc_is_running "$LITESTREAM_PID_FILE"; then
        tracked_pid=$(cat "$LITESTREAM_PID_FILE" 2>/dev/null || echo "")
    fi

    local all_found_pids
    all_found_pids=$(svc_find_orphans_by_cwd "$l_dir" "litestream" "$l_token")
    local orphan_pids=()
    for p in $all_found_pids; do
        if [ -n "$tracked_pid" ] && [ "$p" = "$tracked_pid" ]; then
            continue
        fi
        orphan_pids+=("$p")
    done

    if [ -n "$tracked_pid" ] && [ ${#orphan_pids[@]} -eq 0 ]; then
        echo "  Litestream  → already running (PID $tracked_pid)"
        return 0
    fi

    if [ ${#orphan_pids[@]} -gt 0 ]; then
        echo "  ⚠ Litestream → found ${#orphan_pids[@]} orphaned process(es) not tracked by PID file: ${orphan_pids[*]} — terminating before starting fresh"
        for opid in "${orphan_pids[@]}"; do
            echo "  Terminating orphan Litestream process (PID $opid)..."
            kill -TERM "$opid" 2>/dev/null || true
            for i in {1..10}; do
                if ! kill -0 "$opid" 2>/dev/null; then
                    break
                fi
                sleep 0.5
            done
            if kill -0 "$opid" 2>/dev/null; then
                kill -9 "$opid" 2>/dev/null || true
            fi
        done
    fi

    if [ -n "$tracked_pid" ]; then
        echo "  Litestream  → running (PID $tracked_pid)"
        return 0
    fi

    echo "  Litestream  → starting replication..."
    (cd "$l_dir" && exec nohup "$l_bin" replicate -config "$l_cfg" >> "$LITESTREAM_LOG_FILE" 2>&1) &
    local l_pid=$!
    echo "$l_pid" > "$LITESTREAM_PID_FILE"
    sleep 0.5
    
    if kill -0 "$l_pid" 2>/dev/null; then
        echo "  Litestream  → started (PID $l_pid)"
    else
        echo "  Litestream  → ERROR: failed to start. Check $LITESTREAM_LOG_FILE"
        rm -f "$LITESTREAM_PID_FILE"
        return 1
    fi
}

stop_litestream() {
    local l_dir="$DAEMON_DIR"
    local l_token="replicate"
    
    svc_stop_by_pid "$LITESTREAM_PID_FILE" "Litestream"

    local remaining_pids
    remaining_pids=$(svc_find_orphans_by_cwd "$l_dir" "litestream" "$l_token")
    if [ -n "$remaining_pids" ]; then
        local r_array=($remaining_pids)
        echo "  ⚠ Litestream → found ${#r_array[@]} remaining process(es) after stop: $remaining_pids — terminating"
        for opid in "${r_array[@]}"; do
            echo "  Terminating remaining Litestream process (PID $opid)..."
            kill -TERM "$opid" 2>/dev/null || true
            for i in {1..10}; do
                if ! kill -0 "$opid" 2>/dev/null; then
                    break
                fi
                sleep 0.5
            done
            if kill -0 "$opid" 2>/dev/null; then
                kill -9 "$opid" 2>/dev/null || true
            fi
        done
    fi

    local final_pids
    final_pids=$(svc_find_orphans_by_cwd "$l_dir" "litestream" "$l_token")
    if [ -z "$final_pids" ]; then
        echo "  Litestream  → fully stopped, 0 processes remaining"
    else
        echo "  ⚠ Litestream → WARNING: processes still alive: $final_pids"
    fi
}

status_litestream() {
    local l_dir="$DAEMON_DIR"
    local l_token="replicate"
    local tracked_pid=""
    if svc_is_running "$LITESTREAM_PID_FILE"; then
        tracked_pid=$(cat "$LITESTREAM_PID_FILE" 2>/dev/null || echo "")
    fi

    local all_found_pids
    all_found_pids=$(svc_find_orphans_by_cwd "$l_dir" "litestream" "$l_token")
    local orphan_pids=()
    for p in $all_found_pids; do
        if [ -n "$tracked_pid" ] && [ "$p" = "$tracked_pid" ]; then
            continue
        fi
        orphan_pids+=("$p")
    done

    if [ -n "$tracked_pid" ]; then
        if [ ${#orphan_pids[@]} -gt 0 ]; then
            echo "  Litestream:      running (PID $tracked_pid) [⚠ ${#orphan_pids[@]} orphan(s): ${orphan_pids[*]}]"
        else
            echo "  Litestream:      running (PID $tracked_pid)"
        fi
    else
        if [ ${#orphan_pids[@]} -gt 0 ]; then
            echo "  Litestream:      stopped (PID file) [⚠ ${#orphan_pids[@]} UNTRACKED orphan(s) running: ${orphan_pids[*]}]"
        else
            echo "  Litestream:      stopped"
        fi
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

# ── Composite Management Operations ──────────────────────────────────────────

start_all_services() {
    mkdir -p "$DAEMON_DIR"
    start_daemon
    start_restoricon
    start_aigentik
    start_cloudflare
    start_litestream
}

stop_all_services() {
    echo "Stopping Codey-OS services..."
    stop_litestream
    stop_cloudflare
    stop_aigentik
    stop_restoricon
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
    status_litestream
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
        litestream)
            tail -n 50 "$LITESTREAM_LOG_FILE" 2>/dev/null || echo "No log found for litestream ($LITESTREAM_LOG_FILE)."
            ;;
        *)
            echo "Available logs: daemon, restoricon, aigentik, cloudflare, litestream"
            echo
            for logfile in "$DAEMON_LOG_FILE" "$RESTORICON_LOG_FILE" "$AIGENTIK_LOG_FILE" "$CLOUDFLARED_LOG_FILE" "$LITESTREAM_LOG_FILE"; do
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
    get_aigentik_config
)
cfg_path = get_config_file_path()
print(f'Config file: {cfg_path} (exists: {cfg_path.is_file()})')
print('\nActive configurations:')
print(f'  • Cloudflare Token: {\"configured\" if get_cloudflare_tunnel_token() else \"not set\"}')
print(f'  • Restoricon API:   {get_restoricon_api_config()}')
print(f'  • Aigentik:         {get_aigentik_config()}')
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
  logs [service]  Show service logs (daemon, restoricon, aigentik, cloudflare, litestream)
  config          Show active configuration settings
  help, --help    Show this help message

Options & Passthrough:
  Any other command or flag (e.g. codey "Fix bug in main.py") automatically
  ensures all services are running and passes arguments directly to codeyOS.
EOF
}
