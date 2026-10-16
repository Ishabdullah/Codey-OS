#!/data/data/com.termux/files/usr/bin/bash
# Parent/child environment only: no service action, output, or credential read.
prepare_bootstrap_environment() {
    local root="${CODEY_OS_DIR:-$(cd -- "${BASH_SOURCE[0]%/*}/.." && pwd -P)}"
    export CODEY_DIR="$root"
    case "${PYTHONPATH:-}" in
        "$root"|"$root":*) ;;
        *) export PYTHONPATH="$root${PYTHONPATH:+:$PYTHONPATH}" ;;
    esac
    if [ -f "$HOME/.codeyOS/gcp_credentials.json" ]; then
        export GOOGLE_APPLICATION_CREDENTIALS="$HOME/.codeyOS/gcp_credentials.json"
    elif [ -n "${GOOGLE_APPLICATION_CREDENTIALS:-}" ]; then
        export GOOGLE_APPLICATION_CREDENTIALS
    fi
}
