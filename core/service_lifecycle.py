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
_BASH_FRAGMENT = 'source "$1"; shift; _codey_locked_identity "$@"'
_SERVICES = {
    "daemon": ("codeyOS", "codeyOS"),
    "restoricon": ("restoricon-api", "restoricon-api"),
    "aigentik": ("aigentik", "aigentik"),
    "litestream": ("litestream", "litestream"),
    "cloudflared": ("cloudflared", "cloudflared"),
    "backup-docs": ("backup-docs", "backup-docs"),
    "llama-server-8080": ("llama-server-8080", "llama-server-8080"),
}
_OPERATIONS = ("stop", "reload", "preflight")


@dataclass(frozen=True)
class ServicePaths:
    key: str
    pid_file: Path
    log_file: Path
    socket_file: Path | None = None


def service_paths(service):
    """Resolve one snapshot; relative configured values retain current meaning."""
    if service not in _SERVICES:
        raise identity.UnsafeRecord("Unknown configured service")
    key, stem = _SERVICES[service]
    if service == "daemon":
        # Existing parser/default merge is authoritative. Its fallback warnings
        # belong to stderr, never a finite path data channel.
        with contextlib.redirect_stdout(sys.stderr):
            if __package__:
                from .daemon_config import resolve_daemon_paths
            else:
                sys.path.insert(0, str(_REPO_ROOT))
                from core.daemon_config import resolve_daemon_paths
            selected = resolve_daemon_paths()
        return ServicePaths(key, selected.pid_file, selected.log_file, selected.socket_file)
    root = Path(os.environ.get("CODEY_STATE_DIR") or Path.home() / ".codeyOS")
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


def lock_exec(service, operation):
    """Acquire/validate before fixed mechanics; this is never public READ status."""
    if operation not in _OPERATIONS or service not in _SERVICES or operation == "reload" and service != "daemon":
        raise identity.UnsafeRecord("Unsupported service operation")
    selected = service_paths(service)
    record = identity.LifecycleRecord(selected.pid_file, selected.key, blocking=False)
    try:
        record.__enter__()
        if record.fd != _LOCK_FD:
            os.dup2(record.fd, _LOCK_FD, inheritable=True)
            os.close(record.fd)
            record.fd = _LOCK_FD
        else:
            os.set_inheritable(_LOCK_FD, True)
        record._check_lock()
        _close_extra_fds({_LOCK_FD})
        os.execvpe("bash", ["bash", "-c", _BASH_FRAGMENT, "codey-service-mechanics", str(_PRIVATE_LIBRARY), str(_LOCK_FD), operation, selected.key, str(selected.pid_file)], dict(os.environ))
        raise identity.UnsafeRecord("Service mechanics did not exec")
    finally:
        if record.fd is not None:
            os.close(record.fd)
            record.fd = None


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
        locked.add_argument("service", choices=tuple(_SERVICES))
        locked.add_argument("operation", choices=_OPERATIONS)
        paths = commands.add_parser("paths", add_help=False)
        paths.add_argument("--field", choices=("pid", "socket", "log", "all"), default="all")
        paths.add_argument("--encoding", choices=("json", "nul"), default="json")
        paths.add_argument("--data-fd", type=int, required=True)
        ready = commands.add_parser("parse-ready", add_help=False)
        ready.add_argument("--expected-helper", type=int, required=True)
        args = parser.parse_args(argv)
        if args.command == "lock-exec":
            lock_exec(args.service, args.operation)
        elif args.command == "paths":
            path_data(args.field, args.encoding, args.data_fd)
        else:
            parse_ready(args.expected_helper)
        return 0
    except (OSError, identity.UnsafeRecord, ValueError, TypeError):
        print("Service mechanics unavailable or unsafe", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
