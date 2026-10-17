"""Finite public service gateway with installed private worker mechanics.

Private Python access is the established installed-code contract, not an
anti-tampering boundary against arbitrary same-UID Python execution.
"""

import contextlib
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
# This source is constant. Repository location and finite selectors are argv data.
_WORKER_BOOTSTRAP = "import sys; sys.path.insert(0, sys.argv[1]); from core.service_actions import _worker_main; raise SystemExit(_worker_main(sys.argv[2:]))"


class _OperationFailed(RuntimeError):
    pass


def _validate(values):
    from core import service_lifecycle as mechanics

    if not isinstance(values, (tuple, list)) or not all(isinstance(value, str) for value in values):
        raise ValueError("Invalid service operation")
    if len(values) == 3 and values[0] == "lock-exec":
        try:
            mechanics.validate_lock_request(values[1], values[2])
        except mechanics.identity.UnsafeRecord as error:
            raise ValueError("Invalid service operation") from error
        return "READ" if values[2] == "preflight" else "ACT"
    if len(values) == 2 and values[0] in ("status", "logs") and values[1] in (*mechanics._SERVICES, "all"):
        return "READ"
    if len(values) == 1 and values[0] in ("config-show", "daemon-status"):
        return "READ"
    if values == ["config-create"] or values == ("config-create",):
        return "ACT"
    raise ValueError("Invalid service operation")


@contextlib.contextmanager
def _signal_requests(state):
    """Request interruption without dropping the only retained worker handle."""
    saved = []
    def requested(number, _frame):
        if state["interrupted"] is None:
            state["interrupted"] = 128 + number
    try:
        if threading.current_thread() is threading.main_thread():
            for number in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
                previous = signal.getsignal(number)
                if previous != signal.SIG_IGN:
                    signal.signal(number, requested)
                    saved.append((number, previous))
        yield
    finally:
        for number, previous in reversed(saved):
            signal.signal(number, previous)


def _wait_owned(worker, state):
    while True:
        try:
            return worker.wait()
        except (KeyboardInterrupt, SystemExit):
            state["interrupted"] = state["interrupted"] or 130
        except Exception:  # noqa: BLE001 - retain ownership/sanitize private failures
            # A wait failure is not exit confirmation. Keep the exact Popen,
            # recover by wait/poll, and never auto-kill, detach or respawn it.
            state["wait_error"] = True
            try:
                result = worker.poll()
            except Exception:  # noqa: BLE001 - retain ownership/sanitize private failures
                result = None
            if type(result) is int:
                return result
            time.sleep(.05)


def run_public(values):
    """One envelope: no lifecycle lock is held by this gateway parent."""
    authority = _validate(values)
    from core.action_gateway import get_action_gateway

    label = ".".join((values[1], values[2])) if values[0] == "lock-exec" else ".".join(values)
    state = {"interrupted": None, "wait_error": False, "status": 2}
    def execute():
        worker = None
        result = None
        failure = False
        try:
            with _signal_requests(state):
                worker = subprocess.Popen([sys.executable, "-c", _WORKER_BOOTSTRAP, str(_REPO_ROOT), *values], close_fds=True)
                result = _wait_owned(worker, state)
        except (KeyboardInterrupt, SystemExit):
            state["interrupted"] = state["interrupted"] or 130
            failure = True
        except Exception:  # noqa: BLE001 - retain ownership/sanitize private failures
            failure = True
        finally:
            if worker is not None and result is None:
                result = _wait_owned(worker, state)
        status = (128 - result if result < 0 else result) if type(result) is int else 2
        if status == 0 and (failure or state["wait_error"] or state["interrupted"]):
            status = state["interrupted"] or 2
        state["status"] = status
        if status != 0 or failure or state["wait_error"] or state["interrupted"]:
            if worker is None:
                reason = "Service worker could not start; operation not completed."
            else:
                reason = f"Service worker completed with exit {result}; public status {status}."
                if state["interrupted"]:
                    reason += " Interruption observed; worker disposition confirmed."
                if authority == "ACT":
                    reason += " Partial effects possible."
            raise _OperationFailed(reason)
        return "Service worker completed."
    decision = get_action_gateway().gate_exec(
        authority=authority, action="service." + label,
        command="service " + label, confirm_available=False, execute=execute,
    )
    if decision.allowed:
        return state["status"]
    if decision.outcome == "refused":
        print("Service operation refused.", file=sys.stderr)
        return 2
    print("Service operation failed; see operation output and audit.", file=sys.stderr)
    return state["status"]


def _worker_main(values):
    """Finite installed mechanism; deliberately has no public CLI entrypoint."""
    try:
        _validate(values)
        from core import service_lifecycle as mechanics

        if values[0] == "lock-exec":
            mechanics.lock_exec(values[1], values[2])
        elif values[0] == "status":
            return mechanics.status(values[1])
        elif values[0] == "logs":
            mechanics.show_logs(values[1])
        elif values[0] == "config-create":
            from core.daemon_config import create_default_config
            print(f"Default config created at: {create_default_config()}")
        elif values[0] == "config-show":
            _show_config()
        else:
            result = mechanics.status("daemon")
            _show_daemon_models()
            return result
        return 0
    except Exception:  # noqa: BLE001 - retain ownership/sanitize private failures
        print("Service mechanics unavailable or unsafe.", file=sys.stderr)
        return 2


def _show_config():
    import json

    from utils.config import (
        get_aigentik_config,
        get_cloudflare_tunnel_token,
        get_config_file_path,
        get_restoricon_api_config,
        load_user_config,
    )

    def redact(value):
        if isinstance(value, dict):
            return {key: "***redacted***" if any(part in key.lower() for part in ("token", "secret", "api_key")) else redact(item) for key, item in value.items()}
        if isinstance(value, list):
            return [redact(item) for item in value]
        return value
    path = get_config_file_path()
    print(f"Config file: {path} (exists: {path.is_file()})")
    print("\nActive configurations:")
    print(f"  • Cloudflare Token: {'configured' if get_cloudflare_tunnel_token() else 'not set'}")
    print(f"  • Restoricon API:   {get_restoricon_api_config()}")
    print(f"  • Aigentik:         {get_aigentik_config()}")
    print("\nLoaded raw config:")
    print(json.dumps(redact(load_user_config()), indent=2))


def _show_daemon_models():
    # Fixed READ display, matching the retired codeydOS heredoc/port meanings.
    import urllib.request

    from utils import config

    def healthy(port):
        import json
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2) as response:
                return response.status == 200 and json.loads(response.read().decode()).get("status") == "ok"
        except Exception:  # noqa: BLE001 - retain ownership/sanitize private failures
            return False
    backend = getattr(config, "CODEY_BACKEND", "local")
    planner = getattr(config, "CODEY_PLANNER_BACKEND", "local")
    if config.is_remote_backend():
        name = config.UNLIMITEDCLAUDE_MODEL if backend == "unlimitedclaude" else config.OPENROUTER_MODEL
        print(f"Model:          {backend} ({name})")
    else:
        mmap = "enabled" if config.QWEN_MMAP else "disabled"
        print(f"Model:          loaded   (mmap: {mmap})" if healthy(8080) else "Model:          not loaded")
    if config.is_remote_planner_backend():
        name = config.UNLIMITEDCLAUDE_PLANNER_MODEL if planner == "unlimitedclaude" else config.OPENROUTER_PLANNER_MODEL
        suffix = f" [{planner}]" if planner != backend else ""
        print(f"Planner:        {planner} ({name}){suffix}")
    else:
        print("Planner:        local (shares the model above, thinking mode)")
