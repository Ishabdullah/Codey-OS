"""Finite subordinate service mechanics; public operation auditing is separate.

Only core-selected private Bash mechanics may execute under the lifecycle lock.
No arbitrary command/function/path override or audit-suppression token is accepted.
"""

import argparse
import contextlib
import json
import os
import select
import sys
import time
from dataclasses import dataclass
from pathlib import Path

if __package__:
    from . import process_identity as identity
else:
    import process_identity as identity

_REPO_ROOT = Path(__file__).resolve().parents[1]
_PRIVATE_LIBRARY = _REPO_ROOT / "lib/service_lifecycle.sh"
_LOCK_FD = 200
# Caller values only enter argv positions, never this Bash source fragment.
_BASH_FRAGMENT = 'source "$1"; shift; _codey_service_operation "$@"'
_SERVICES = {
    "daemon": ("codeyOS", "codeyOS"),
    "restoricon": ("restoricon-api", "restoricon-api"),
    "aigentik": ("aigentik", "aigentik"),
    "litestream": ("litestream", "litestream"),
    "cloudflared": ("cloudflared", "cloudflared"),
    "backup-docs": ("backup-docs", "backup-docs"),
    "llama-server-8080": ("llama-server-8080", "llama-server-8080"),
}
_OPERATIONS = ("start", "stop", "restart", "reload", "preflight")
# All operations acquire their complete set in this same order, before effects.
_START_ORDER = ("daemon", "restoricon", "aigentik", "cloudflared", "litestream", "backup-docs")
_LOCK_ORDER = (*_START_ORDER, "llama-server-8080")
_LOCK_NUMBERS = (200, 210, 211, 212, 213, 214, 215)  # 201 is the private readiness pipe



class ServicePathRefused(identity.UnsafeRecord):
    """A configured lifecycle path was refused; the message is operator-safe."""


@dataclass(frozen=True)
class ServicePaths:
    key: str
    pid_file: Path
    log_file: Path
    socket_file: Path | None = None


def service_paths(service):
    """Resolve one lifecycle path snapshot; unsafe values are refused."""
    if service not in _SERVICES:
        raise identity.UnsafeRecord("Unknown configured service")
    key, stem = _SERVICES[service]
    if service == "daemon":
        # Existing parser/default merge is authoritative. Its fallback warnings
        # belong to stderr, never a finite path data channel.
        with contextlib.redirect_stdout(sys.stderr):
            if __package__:
                from .daemon_config import DaemonPathError, resolve_daemon_paths
            else:
                sys.path.insert(0, str(_REPO_ROOT))
                from core.daemon_config import DaemonPathError, resolve_daemon_paths
            try:
                selected = resolve_daemon_paths()
            except DaemonPathError as error:
                raise ServicePathRefused(str(error)) from None
        return ServicePaths(key, selected.pid_file, selected.log_file, selected.socket_file)
    root = Path(os.environ.get("CODEY_STATE_DIR") or Path.home() / ".codeyOS")
    if not root.is_absolute():
        value = repr(str(root))[:120]
        raise ServicePathRefused(
            f"Set CODEY_STATE_DIR to an absolute directory for service lifecycle paths; got {value}"
        )
    return ServicePaths(key, root / f"{stem}.pid", root / f"{stem}.log")


def _close_extra_fds(keep):
    # Linux /proc is already required for the identity contract. Closing rather
    # than LOCK_UN preserves other processes sharing an inherited description.
    for entry in os.listdir("/proc/self/fd"):
        fd = int(entry)
        if fd > 2 and fd not in keep:
            try:
                os.close(fd)
            except OSError:
                pass  # listdir's own transient descriptor is already closed


def _config_helpers():
    if not __package__:
        sys.path.insert(0, str(_REPO_ROOT))
    from utils import config
    return config


def start_profile(service, selected):
    """Fixed installed profiles; no arbitrary shell command configuration."""
    cwd = Path.cwd()
    missing = False
    if service == "daemon":
        argv = ["python3", str(_REPO_ROOT / "core/daemon_bootstrap.py"), str(selected.pid_file), str(selected.socket_file), str(selected.log_file)]
    elif service == "restoricon":
        config = _config_helpers().get_restoricon_api_config()
        argv = ["python3", "-m", "restoricon_core.api.server", "--host", str(config["host"]), "--port", str(config["port"]), "--db", str(config["db_path"])]
    elif service == "aigentik":
        cwd = Path(_config_helpers().get_aigentik_config()["dir"])
        script = next((name for name in ("main.py", "app.py", "server.py", "run.sh", "index.js", "start.sh") if (cwd / name).is_file()), None)
        missing = script is None
        runtime = "python3" if script and script.endswith(".py") else "node" if script and script.endswith(".js") else "bash"
        argv = [runtime, script] if script else []
    elif service == "litestream":
        cwd = selected.pid_file.parent
        binary = Path.home() / "go/bin/litestream"
        missing = not binary.is_file()
        argv = [str(binary), "replicate", "-config", str(Path.home() / ".codeyOS/litestream.yml")]
    elif service == "cloudflared":
        import shutil
        # G15h (NEW-1021): the tunnel token is NEVER placed in argv. argv is
        # visible in /proc/<pid>/cmdline and `ps` of this bash mechanics
        # process, the owned-spawn helper and cloudflared itself. The spawn
        # helper (core/process_identity.py, _SERVICE_SECRET_ENV) resolves the
        # token and sets TUNNEL_TOKEN (documented by `cloudflared tunnel run
        # --help`) in the final child environment only. The value is used here
        # only to decide "configured?" and is not kept or returned.
        configured = bool(_config_helpers().get_cloudflare_tunnel_token()) if shutil.which("cloudflared") else False
        missing = not configured
        argv = ["cloudflared", "tunnel", "run"] if configured else []
    elif service == "backup-docs":
        cwd = _REPO_ROOT / "core"
        argv = ["python3", "backup_documents.py", "--daemon"]
    else:
        argv = []
    return str(cwd), missing, argv


def discover_untracked(service, cwd, argv, tracked=None):
    """Cwd/runtime/token matches are diagnostics, never termination authority."""
    if service not in ("aigentik", "litestream", "backup-docs") or not argv:
        return []
    runtime, token = Path(argv[0]).name, argv[1]
    target = str(Path(cwd).resolve())
    found = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit() or int(entry.name) == tracked:
            continue
        try:
            if os.readlink(entry / "cwd") != target:
                continue
            args = [value.decode(errors="replace") for value in (entry / "cmdline").read_bytes().split(b"\0") if value]
            if args and Path(args[0]).name.startswith(runtime) and any(value == token or Path(value).name == token for value in args[1:]):
                found.append(int(entry.name))
        except (OSError, ValueError):
            continue  # inaccessible/departed processes grant no authority
    return sorted(found)


def validate_lock_request(service, operation):
    if operation not in _OPERATIONS or service not in (*_SERVICES, "all") or operation == "reload" and service != "daemon" or service == "all" and operation in ("reload", "preflight") or service == "llama-server-8080" and operation != "stop":
        raise identity.UnsafeRecord("Unsupported service operation")


def lock_exec(service, operation):
    """Lock the entire operation; nested private mechanics reuse held FDs."""
    validate_lock_request(service, operation)
    targets = set(_START_ORDER if service == "all" else (service,))
    if "daemon" in targets and operation in ("start", "stop", "restart"):
        targets.add("llama-server-8080")
    selected = {name: service_paths(name) for name in _LOCK_ORDER if name in targets}
    records = []
    temporary = []
    try:
        for name, paths in selected.items():
            record = identity.LifecycleRecord(paths.pid_file, paths.key, blocking=False)
            record.__enter__()
            records.append(record)
        # Duplicate through a high temporary range before assigning fixed FDs;
        # an opener's numeric descriptor can otherwise collide with a later FD.
        import fcntl
        for record in records:
            temporary.append(fcntl.fcntl(record.fd, fcntl.F_DUPFD_CLOEXEC, 240))
        for record in records:
            os.close(record.fd)
            record.fd = None
        plan = []
        for index, ((name, paths), record, saved) in enumerate(zip(selected.items(), records, temporary)):
            number = _LOCK_NUMBERS[index]
            os.dup2(saved, number, inheritable=True)
            os.close(saved)
            temporary[index] = None
            record.fd = number
            record._check_lock()
            cwd, missing, argv = start_profile(name, paths) if operation in ("start", "restart") or name in ("aigentik", "litestream", "backup-docs") else (str(Path.cwd()), False, [])
            observed = record.inspect()
            orphans = discover_untracked(name, cwd, argv, observed.identity["pid"] if observed.state == identity.RUNNING else None)
            plan.extend((str(number), name, paths.key, str(paths.pid_file), str(paths.log_file), str(paths.socket_file or ""), cwd, "1" if missing else "0", str(len(orphans)), " ".join(map(str, orphans)), str(len(argv)), *argv))
        keep = {record.fd for record in records}
        _close_extra_fds(keep)
        os.execvpe("bash", ["bash", "-c", _BASH_FRAGMENT, "codey-service-mechanics", str(_PRIVATE_LIBRARY), service, operation, str(len(records)), *plan], dict(os.environ))
        raise identity.UnsafeRecord("Service mechanics did not exec")
    finally:
        # Never LOCK_UN a description that an owned guardian may retain.
        for descriptor in temporary:
            if descriptor is not None:
                os.close(descriptor)
        for record in records:
            if record.fd is not None:
                os.close(record.fd)
                record.fd = None


def status(service):
    """Pure snapshots; no creating lock adapter, cleanup, or signal path."""
    names = _START_ORDER if service == "all" else (service,)
    result = 0
    for name in names:
        try:
            selected = service_paths(name)
        except ServicePathRefused as refusal:
            if service != "all":
                raise
            print(f"  {name}: REFUSED ({refusal})")
            result = 2
            continue
        observed = identity.inspect_record(selected.pid_file, selected.key)
        suffix = f" (PID {observed.identity['pid']})" if observed.state == identity.RUNNING else ""
        print(f"  {name}: {observed.state}{suffix}")
        if name in ("aigentik", "litestream", "backup-docs"):
            cwd, _missing, argv = start_profile(name, selected)
            found = discover_untracked(name, cwd, argv, observed.identity["pid"] if observed.state == identity.RUNNING else None)
            if found:
                print(f"  {name}: UNTRACKED matches (diagnostic only): {' '.join(map(str, found))}")
        if observed.state == identity.UNSAFE:
            result = 2
        elif observed.state == identity.DEAD and service != "all":
            result = 1
    return result


def usable_daemon(pid_file, socket_file):
    """Coordination read only; this result never permits starting a daemon."""
    values = (pid_file, socket_file)
    if any(not value or "\0" in value or len(value.encode()) > 4096 or not Path(value).is_absolute() for value in values):
        raise identity.UnsafeRecord("Invalid client path snapshot")
    observed = identity.inspect_record(Path(pid_file), "codeyOS")
    if observed.state == identity.UNSAFE:
        print("Daemon identity is unsafe/unverifiable; connection refused", file=sys.stderr)
        return 2
    return 0 if observed.state == identity.RUNNING and Path(socket_file).is_socket() else 1


def show_logs(service):
    names = _START_ORDER if service == "all" else (service,)
    result = 0
    for name in names:
        try:
            selected = service_paths(name)
        except ServicePathRefused as refusal:
            if service != "all":
                raise
            print(f"=== {name} ===")
            print(f"{name}: REFUSED ({refusal})")
            result = 2
            continue
        try:
            with selected.log_file.open(errors="replace") as stream:
                from collections import deque
                lines = deque(stream, maxlen=50 if service != "all" else 10)
            print(f"=== {name} ===")
            print("".join(lines), end="")
        except FileNotFoundError:
            print(f"No log found for {name} ({selected.log_file}).")
    return result


def path_data(field, encoding, data_fd):
    """Emit only selected daemon path data on a private writable pipe."""
    if field not in ("pid", "socket", "log", "all") or encoding not in ("json", "nul"):
        raise identity.UnsafeRecord("Unknown path data selection")
    selected = service_paths("daemon")
    fields = {"pid": str(selected.pid_file), "socket": str(selected.socket_file), "log": str(selected.log_file)}
    if any("\0" in value for value in fields.values()):
        raise identity.UnsafeRecord("Invalid configured path")
    values = fields if field == "all" else fields[field]
    if encoding == "json":
        data = json.dumps(values, separators=(",", ":")).encode() + b"\n"
    else:
        ordered = list(fields.values()) if field == "all" else [values]
        data = b"".join(value.encode() + b"\0" for value in ordered)
    if len(data) > 4096:
        raise identity.UnsafeRecord("Configured path data exceeds channel bound")
    fd = identity._ready_pipe(data_fd, None)
    try:
        if os.write(fd, data) != len(data):
            raise identity.UnsafeRecord("Path data delivery failed")
    finally:
        os.close(fd)


def _read_ready_pipe(fd):
    """Read one complete <=96-byte result through EOF, with a normal-budget margin."""
    deadline = time.monotonic() + 20.0
    data = b""
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0 or not select.select([fd], [], [], remaining)[0]:
            raise identity.UnsafeRecord("Service readiness timed out")
        chunk = os.read(fd, 97 - len(data))
        if not chunk:
            return data
        data += chunk
        if len(data) > 96:
            raise identity.UnsafeRecord("Service readiness exceeds channel bound")


def parse_ready(expected_helper):
    """Validate the complete private pipe, not a truncated first line."""
    if not identity.valid_pid(expected_helper):
        raise identity.UnsafeRecord("Invalid helper job identity")
    data = _read_ready_pipe(sys.stdin.fileno())
    result = identity.parse_spawn_ready(data)
    if result.guardian_pid is not None and result.guardian_pid != expected_helper or result.child_pid == expected_helper:
        raise identity.UnsafeRecord("Readiness does not match the actual helper job")
    sys.stdout.buffer.write(data)  # caller captures this in a private pipe


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise identity.UnsafeRecord("Invalid service mechanics arguments")


def main(argv=None):
    try:
        parser = _Parser(add_help=False)
        commands = parser.add_subparsers(dest="command", required=True)
        locked = commands.add_parser("lock-exec", add_help=False)
        locked.add_argument("service", choices=(*_SERVICES, "all"))
        locked.add_argument("operation", choices=_OPERATIONS)
        client = commands.add_parser("usable-daemon", add_help=False)
        client.add_argument("pid_file")
        client.add_argument("socket_file")
        logs = commands.add_parser("logs", add_help=False)
        logs.add_argument("service", choices=(*_SERVICES, "all"))
        inspected = commands.add_parser("status", add_help=False)
        inspected.add_argument("service", choices=(*_SERVICES, "all"))
        commands.add_parser("config-create", add_help=False)
        commands.add_parser("config-show", add_help=False)
        commands.add_parser("daemon-status", add_help=False)
        paths = commands.add_parser("paths", add_help=False)
        paths.add_argument("--field", choices=("pid", "socket", "log", "all"), default="all")
        paths.add_argument("--encoding", choices=("json", "nul"), default="json")
        paths.add_argument("--data-fd", type=int, required=True)
        ready = commands.add_parser("parse-ready", add_help=False)
        ready.add_argument("--expected-helper", type=int, required=True)
        args = parser.parse_args(argv)
        if args.command in ("lock-exec", "status", "logs", "config-create", "config-show", "daemon-status"):
            if not __package__:
                sys.path.insert(0, str(_REPO_ROOT))
            from core.service_actions import run_public
            values = [args.command]
            if args.command in ("lock-exec", "status", "logs"):
                values.append(args.service)
            if args.command == "lock-exec":
                values.append(args.operation)
            return run_public(values)
        elif args.command == "usable-daemon":
            return usable_daemon(args.pid_file, args.socket_file)
        elif args.command == "paths":
            path_data(args.field, args.encoding, args.data_fd)
        else:
            parse_ready(args.expected_helper)
        return 0
    except ServicePathRefused as refusal:
        print(str(refusal), file=sys.stderr)
        return 2
    except (OSError, identity.UnsafeRecord, ValueError, TypeError):
        print("Service mechanics unavailable or unsafe", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
