"""Fixed codeyOS client: argv is data, and foreground exits stay foreground exits.

RPC branches deliberately do not import main, daemon, inference, or a model.
Socket permissions/identity coordinate a connection; action authority is the
server's responsibility, not a property supplied by this serializer.
"""

import datetime
import importlib
import json
import re
import socket
import sys
from pathlib import Path

# Also support execution by absolute script path from any invoking directory.
if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class ClientError(Exception):
    """A refused or unsuccessful client operation."""


def _configuration():
    from core.daemon_config import get_config, resolve_daemon_paths

    config = get_config()
    return config, resolve_daemon_paths(config)


def _require_daemon(paths):
    from core.process_identity import RUNNING, UNSAFE, inspect_record

    observed = inspect_record(paths.pid_file, "codeyOS")
    if observed.state == UNSAFE:
        raise ClientError("Daemon identity is unsafe/unverifiable; connection refused")
    if observed.state != RUNNING or not paths.socket_file.is_socket():
        raise ClientError("Codey-OS daemon is not running. Start it with: codeydOS start")


def _request(paths, command, data, timeout):
    _require_daemon(paths)
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.settimeout(timeout)
        sock.connect(str(paths.socket_file))
        sock.sendall(json.dumps({"cmd": command, "data": data}).encode("utf-8"))
        chunks = []
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
        if not chunks:
            raise ClientError("No response from daemon")
        try:
            result = json.loads(b"".join(chunks).decode("utf-8"))
        except (ValueError, UnicodeError) as exc:
            raise ClientError("Invalid response from daemon") from exc
        if not isinstance(result, dict) or result.get("status") != "ok":
            message = result.get("message", "Invalid response from daemon") if isinstance(result, dict) else "Invalid response from daemon"
            raise ClientError(str(message))
        return result
    except TimeoutError as exc:
        raise ClientError("Connection timed out. Daemon may be busy.") from exc
    except OSError as exc:
        raise ClientError(f"Socket error: {exc}") from exc
    finally:
        try:
            sock.close()
        except OSError:
            # Closing a failed connection cannot change the operation's result.
            pass


def _task_id(value):
    if not re.fullmatch(r"[0-9]+", value) or not value.strip("0"):
        raise ClientError("Task ID must be a positive decimal integer")
    try:
        return int(value)
    except ValueError as exc:
        raise ClientError("Task ID must be a positive decimal integer") from exc


def _icon(task):
    return {"done": "✓", "running": "⟳", "pending": "○", "failed": "✗"}.get(task["status"], "?")


def _show_status(health, config):
    print("Codey-OS Daemon Status")
    print("=" * 40)
    print(f"PID:            {health.get('pid', 'N/A')}")
    print("Status:         Running")
    print(f"Uptime:         {health.get('uptime_seconds', 0)} seconds")
    print(f"Memory:         {health.get('memory_mb', 0)} MB")
    print("\nTask Queue:")
    tasks = health.get("tasks", {})
    print(f"  Pending:      {tasks.get('pending', 0)}")
    stuck = tasks.get("stuck", [])
    print(f"  Stuck:        {', '.join(map(str, stuck)) if stuck else 'None'}")
    print(f"\nRecent Actions: {health.get('recent_actions', 0)} logged")
    print(f"\nState Database: {config.get('state', 'db_path')}")


def _show_tasks(result, single):
    if not single:
        print("Tasks:")
        for task in result.get("tasks", []):
            description = task["description"][:50].replace("\n", " ")
            print(f"  [{task['id']}] {_icon(task)} {description}")
        return
    task = result["task"]
    print(f"Task {task['id']}: {task['description']}")
    print(f"Status: {_icon(task)} {task['status']}")
    if task.get("result"):
        print(f"Result: {task['result'][:200]}")
    for key, label in (("created_at", "Created"), ("completed_at", "Completed")):
        if task.get(key):
            print(f"{label}: {datetime.datetime.fromtimestamp(task[key])}")


def _direct(arguments):
    # Keep direct-mode streams and signal dispositions untouched. In particular,
    # SystemExit and KeyboardInterrupt must escape rather than becoming success.
    original = sys.argv
    sys.argv = [original[0], *arguments]
    try:
        return importlib.import_module("main").main()
    finally:
        sys.argv = original


def main(argv=None):
    arguments = list(sys.argv[1:] if argv is None else argv)
    first = arguments[0] if arguments else None
    if first == "--daemon":
        return _direct(arguments)
    background = any(value in ("--bg", "--background") for value in arguments)
    if first not in ("status", "task", "cancel") and not background:
        return _direct(arguments)
    try:
        # Validate IDs before configuration inspection, identity checks, or socket
        # creation: malformed input has no authority to initiate a connection.
        task_data = None
        if first == "task":
            if len(arguments) < 2:
                raise ClientError("Usage: codeyOS task <id>|list")
            task_data = {"limit": 20} if arguments[1] == "list" else {"id": _task_id(arguments[1])}
        elif first == "cancel":
            if len(arguments) < 2:
                raise ClientError("Usage: codeyOS cancel <task_id>")
            task_data = {"id": _task_id(arguments[1])}
        config, paths = _configuration()
        if first == "status":
            _show_status(_request(paths, "health", {}, 5.0), config)
        elif first == "task":
            _show_tasks(_request(paths, "task", task_data, 10.0), "id" in task_data)
        elif first == "cancel":
            result = _request(paths, "cancel", task_data, 10.0)
            print(result.get("message", "Cancelled"))
        else:
            prompt = " ".join(value for value in arguments if value not in ("--bg", "--background", "--yolo"))
            result = _request(paths, "command", {"prompt": prompt, "yolo": "--yolo" in arguments}, 30.0)
            print(json.dumps(result, indent=2))
        return 0
    except (ClientError, OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
