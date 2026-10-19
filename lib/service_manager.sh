#!/data/data/com.termux/files/usr/bin/bash
# Public service orchestration; identity mechanics live in fixed core profiles.
# Sourcing only prepares functions/environment names and never creates state.
CODEY_OS_DIR="${CODEY_OS_DIR:-$(cd -- "${BASH_SOURCE[0]%/*}/.." && pwd -P)}"
source "$CODEY_OS_DIR/lib/bootstrap_environment.sh"

svc_operation() {
    python3 "$CODEY_OS_DIR/core/service_lifecycle.py" lock-exec "$1" "$2"
}
svc_status() {
    python3 "$CODEY_OS_DIR/core/service_lifecycle.py" status "$1"
}
start_daemon() { svc_operation daemon start; }
stop_daemon() { svc_operation daemon stop; }
status_daemon() { svc_status daemon; }
start_restoricon() { svc_operation restoricon start; }
stop_restoricon() { svc_operation restoricon stop; }
status_restoricon() { svc_status restoricon; }
start_aigentik() { svc_operation aigentik start; }
stop_aigentik() { svc_operation aigentik stop; }
status_aigentik() { svc_status aigentik; }
start_litestream() { svc_operation litestream start; }
stop_litestream() { svc_operation litestream stop; }
status_litestream() { svc_status litestream; }
start_cloudflare() { svc_operation cloudflared start; }
stop_cloudflare() { svc_operation cloudflared stop; }
status_cloudflare() { svc_status cloudflared; }
start_backup_docs() { svc_operation backup-docs start; }
stop_backup_docs() { svc_operation backup-docs stop; }
status_backup_docs() { svc_status backup-docs; }
start_all_services() { svc_operation all start; }
stop_all_services() { svc_operation all stop; }
restart_all_services() { svc_operation all restart; }
status_all_services() {
    printf 'Codey-OS Services Status:\n'
    svc_status all
}
show_service_logs() {
    local service="${1:-all}"
    case "$service" in
        codeyOS) service=daemon ;; api) service=restoricon ;;
        cloudflare|tunnel) service=cloudflared ;; backup_docs) service=backup-docs ;;
    esac
    python3 "$CODEY_OS_DIR/core/service_lifecycle.py" logs "$service"
}

show_service_config() {
    python3 "$CODEY_OS_DIR/core/service_lifecycle.py" config-show
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
  logs [service]  Show service logs (daemon, restoricon, aigentik, cloudflare, litestream, backup-docs)
  config          Show active configuration settings
  help, --help    Show this help message

Options & Passthrough:
  Any other command or flag (e.g. codey "Fix bug in main.py") automatically
  ensures all services are running and passes arguments directly to codeyOS.
EOF
}
