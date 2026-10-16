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
    case "$lock_fd" in 200|210|211|212|213|214|215) ;; *) return 2 ;; esac
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
        local begin extra
        for extra in "${_codey_lock_fds[@]}"; do
            [ "$extra" = "$lock_fd" ] || exec {extra}>&-
        done
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
    if parsed="$(
        exec 0<&"$ready_read"
        exec {ready_read}<&-
        for extra in 200 210 211 212 213 214 215; do exec {extra}>&-; done
        exec python3 "$_CODEY_LIFECYCLE_ROOT/core/service_lifecycle.py" parse-ready --expected-helper "$helper_job"
    )" && [ "$_codey_interrupted" -eq 0 ]; then
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


_codey_service_one() {
    local service="$1" action="$2" state rc offset argc
    local fd="${_fds[$service]}" key="${_keys[$service]}" pid="${_pids[$service]}"
    if [ "$action" = stop ] || [ "$action" = reload ] || [ "$action" = preflight ]; then
        if _codey_locked_identity "$fd" "$action" "$key" "$pid"; then
            if [ "$action" = stop ]; then
                printf '  %s → stopped (verified owned-process exit)\n' "$service"
                if [ "${_orphan_counts[$service]}" != 0 ]; then
                    printf '  %s → UNTRACKED matches preserved (diagnostic only): %s\n' "$service" "${_orphans[$service]}" >&2
                    return 2
                fi
            fi
            return 0
        else
            rc=$?
            printf '  %s → %s not completed or identity unavailable\n' "$service" "$action" >&2
            return "$rc"
        fi
    fi
    if state="$(_codey_locked_identity "$fd" preflight "$key" "$pid")"; then
        printf '  %s → already running (verified identity)\n' "$service"
        [ "${_orphan_counts[$service]}" = 0 ] || printf '  %s → UNTRACKED matches (diagnostic only): %s\n' "$service" "${_orphans[$service]}" >&2
        return 0
    else
        rc=$?
        if [ "$rc" != 1 ]; then
            printf '  %s → startup blocked: unsafe/unverifiable identity\n' "$service" >&2
            return 2
        fi
    fi
    if [ "${_orphan_counts[$service]}" != 0 ]; then
        printf '  %s → startup blocked by UNTRACKED matches (diagnostic only): %s\n' "$service" "${_orphans[$service]}" >&2
        return 2
    fi
    if [ "${_missing[$service]}" = 1 ]; then
        printf '  %s → optional service unavailable/not configured; skipped\n' "$service"
        return 0
    fi
    if [ "$service" = daemon ]; then
        _codey_service_one llama-server-8080 stop || return $?
    elif [ "$service" = litestream ]; then
        python3 "$_CODEY_LIFECYCLE_ROOT/core/setup_litestream.py" || return $?
        if timeout 60 python3 "$_CODEY_LIFECYCLE_ROOT/core/backup_secrets.py" >> "${_logs[$service]}" 2>&1; then
            printf '  Secrets → DR backup uploaded\n'
        else
            printf '  Secrets → DR backup skipped/failed (see service log)\n' >&2
        fi
        if [ ! -f "$HOME/.codeyOS/litestream.yml" ]; then
            printf '  litestream → optional configuration unavailable; skipped\n'
            return 0
        fi
    fi
    # A custom log parent is created only after verified startup permission;
    # the owned helper itself opens the existing destination in append mode.
    local log_parent="${_logs[$service]%/*}"
    [ "$log_parent" != "${_logs[$service]}" ] || log_parent=.
    mkdir -p -- "$log_parent" || return $?
    offset="${_offsets[$service]}" argc="${_counts[$service]}"
    if _codey_spawn_owned "$fd" "$key" "$pid" "${_logs[$service]}" "${_cwds[$service]}" "${_all_argv[@]:offset:argc}"; then
        printf '  %s → started (verified process identity; application readiness pending)\n' "$service"
        return 0
    else
        rc=$?
        printf '  %s → launch failed; partial state may require inspection\n' "$service" >&2
        return "$rc"
    fi
}

_codey_service_operation() {
    local requested="$1" operation="$2" size="$3"
    shift 3
    local -A _fds=() _keys=() _pids=() _logs=() _sockets=() _cwds=() _missing=() _orphan_counts=() _orphans=() _offsets=() _counts=()
    local -a _codey_lock_fds=() _all_argv=() starts=(daemon restoricon aigentik cloudflared litestream backup-docs) stops=(backup-docs litestream cloudflared aigentik restoricon daemon)
    local index name argc fd
    for ((index=0; index<size; index++)); do
        fd="$1" name="$2"
        _codey_lock_fds+=("$fd")
        _fds[$name]="$fd" _keys[$name]="$3" _pids[$name]="$4" _logs[$name]="$5" _sockets[$name]="$6" _cwds[$name]="$7" _missing[$name]="$8" _orphan_counts[$name]="$9" _orphans[$name]="${10}"
        argc="${11}"
        shift 11
        _offsets[$name]="${#_all_argv[@]}" _counts[$name]="$argc"
        _all_argv+=("${@:1:argc}")
        shift "$argc"
    done
    [ "$#" = 0 ] || return 2
    source "$_CODEY_LIFECYCLE_ROOT/lib/bootstrap_environment.sh"
    prepare_bootstrap_environment
    local failed=0 rc target
    if [ "$requested" = llama-server-8080 ]; then
        _codey_service_one llama-server-8080 stop
        return $?
    fi
    if [ "$operation" = stop ] || [ "$operation" = restart ]; then
        for target in "${stops[@]}"; do
            [ "$requested" = all ] || [ "$requested" = "$target" ] || continue
            if _codey_service_one "$target" stop; then
                if [ "$target" = daemon ]; then
                    _codey_service_one llama-server-8080 stop || failed=2
                fi
            else
                rc=$?; failed="$rc"
            fi
        done
        [ "$failed" = 0 ] || return "$failed"
        if [ "$operation" = stop ]; then
            printf '  Requested services stopped with verified exits.\n'
            return 0
        fi
    fi
    if [ "$operation" = start ] || [ "$operation" = restart ]; then
        for target in "${starts[@]}"; do
            [ "$requested" = all ] || [ "$requested" = "$target" ] || continue
            _codey_service_one "$target" start || return $?
        done
        return 0
    fi
    _codey_service_one "$requested" "$operation"
}
