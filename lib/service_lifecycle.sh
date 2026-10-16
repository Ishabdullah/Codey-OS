#!/data/data/com.termux/files/usr/bin/bash
# Private sourced mechanics only. No top-level service dispatch or directory write.
_CODEY_LIFECYCLE_ROOT="$(cd -- "${BASH_SOURCE[0]%/*}/.." && pwd -P)"

_codey_locked_identity() {
    local lock_fd="$1" operation="$2" service_key="$3" pid_file="$4"
    case "$service_key" in
        codeyOS|restoricon-api|aigentik|litestream|cloudflared|backup-docs|llama-server-8080) ;;
        *) return 2 ;;
    esac
    case "$operation" in
        preflight)
            python3 "$_CODEY_LIFECYCLE_ROOT/core/process_identity.py" inspect "$pid_file" "$service_key" --lock-fd "$lock_fd"
            ;;
        stop)
            python3 "$_CODEY_LIFECYCLE_ROOT/core/process_identity.py" stop "$pid_file" "$service_key" --lock-fd "$lock_fd"
            ;;
        reload)
            [ "$service_key" = codeyOS ] || return 2
            python3 "$_CODEY_LIFECYCLE_ROOT/core/process_identity.py" signal "$pid_file" "$service_key" --signal USR1 --lock-fd "$lock_fd"
            ;;
        *) return 2 ;;
    esac
}

_codey_wait_owned_job() {
    local job="$1" result
    while :; do
        _codey_wait_interrupted=0
        if wait "$job"; then result=0; else result=$?; fi
        [ "$_codey_wait_interrupted" -eq 0 ] && return "$result"
    done
}

_codey_spawn_owned() {
    local lock_fd="$1" service_key="$2" pid_file="$3" log_file="$4" service_cwd="$5"
    shift 5
    [ "$lock_fd" = 200 ] || return 2
    local -a child_argv=("$@")
    local helper_job original_read original_write ready_read parsed result
    local _codey_interrupted=0 _codey_wait_interrupted=0
    local _codey_saved_traps
    # Only Bash-generated serialization of already-installed handlers enters
    # the restoration evals below, never service/path/argv/readiness data.
    _codey_saved_traps="$(trap -p INT TERM HUP)"
    trap '_codey_interrupted=1; _codey_wait_interrupted=1' INT TERM HUP
    # The handshake prevents rapid helper exit from unsetting coprocess vars
    # before its real job identity and pipe descriptors are saved.
    coproc _CODEY_SERVICE_JOB {
        local begin
        IFS= read -r begin || exit 2
        [ "$begin" = begin ] || exit 2
        exec python3 "$_CODEY_LIFECYCLE_ROOT/core/process_identity.py" spawn \
            --pid-file "$pid_file" --service "$service_key" --lock-fd "$lock_fd" \
            --ready-fd 201 --log-file "$log_file" --cwd "$service_cwd" -- "${child_argv[@]}" \
            201>&1 1>&2
    }
    helper_job="$_CODEY_SERVICE_JOB_PID"
    original_read="${_CODEY_SERVICE_JOB[0]}"
    original_write="${_CODEY_SERVICE_JOB[1]}"
    if ! exec {ready_read}<&"$original_read"; then
        exec {original_read}<&-
        exec {original_write}>&-
        _codey_wait_owned_job "$helper_job" || :
        trap - INT TERM HUP
        eval "$_codey_saved_traps"
        return 2
    fi
    exec {original_read}<&-
    if ! printf 'begin\n' >&"$original_write"; then
        exec {original_write}>&-
        exec {ready_read}<&-
        _codey_wait_owned_job "$helper_job" || :
        trap - INT TERM HUP
        eval "$_codey_saved_traps"
        return 2
    fi
    exec {original_write}>&-
    # Core reads the complete <=96-byte private pipe through EOF, allowing
    # .5s startup plus both default 5s cleanup waits and scheduling margin.
    if parsed="$(python3 "$_CODEY_LIFECYCLE_ROOT/core/service_lifecycle.py" parse-ready --expected-helper "$helper_job" <&"$ready_read" {ready_read}<&- 200>&-)" && [ "$_codey_interrupted" -eq 0 ]; then
        exec {ready_read}<&-
        case "$parsed" in
            'retained '*)
                printf 'Service launch failed; retained guardian owns cleanup and lifecycle lock.\n' >&2
                trap - INT TERM HUP
                eval "$_codey_saved_traps"
                return 2
                ;;
            'published '*)
                if _codey_wait_owned_job "$helper_job"; then result=0; else result=2; fi
                [ "$_codey_interrupted" -eq 0 ] || result=2
                trap - INT TERM HUP
                eval "$_codey_saved_traps"
                return "$result"
                ;;
            failed-cleanup-confirmed)
                _codey_wait_owned_job "$helper_job" || :
                trap - INT TERM HUP
                eval "$_codey_saved_traps"
                return 2
                ;;
        esac
    fi
    # Broken/EOF/timeout protocol: close delivery then keep lock while waiting
    # for this actual Bash-owned helper job. No captured-PID signal/fallback.
    exec {ready_read}<&-
    _codey_wait_owned_job "$helper_job" || :
    trap - INT TERM HUP
    eval "$_codey_saved_traps"
    printf 'Service readiness failed; helper finished, service identity requires inspection.\n' >&2
    return 2
}
