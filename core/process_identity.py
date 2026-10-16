"""Durable service-process identity, using only the Python standard library.

Records protect against stale PIDs, not a user able to forge their own state
root. Identity is rechecked immediately before signals; without pidfd support
there remains a kernel check-to-signal PID-reuse race. No argv is recorded.
"""

import argparse
import fcntl
import json
import math
import os
import re
import signal
import stat
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

RUNNING = "running"
DEAD = "absent-dead"
UNSAFE = "unsafe-unverifiable"
_KEYS = {"version", "service", "pid", "boot_id", "start_ticks", "uid"}
_MAX_PID = 2**31 - 1


class UnsafeRecord(RuntimeError):
    """Identity or lock ownership cannot be established safely."""


def valid_pid(pid):
    return type(pid) is int and 1 < pid <= _MAX_PID


def parse_pid(data):
    # echo-compatible final newline, without accepting spaces/signs/options.
    if not re.fullmatch(rb"[1-9][0-9]{0,9}\n?", data):
        raise UnsafeRecord("Invalid PID record")
    pid = int(data)
    if not valid_pid(pid):
        raise UnsafeRecord("Invalid PID record")
    return pid


def _integer(value, maximum):
    return type(value) is int and 0 <= value <= maximum


def parse_identity(data, service):
    def unique_fields(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate identity field")
            result[key] = value
        return result

    try:
        identity = json.loads(data, object_pairs_hook=unique_fields)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise UnsafeRecord("Invalid identity record") from exc
    if (
        not isinstance(identity, dict) or set(identity) != _KEYS
        or type(identity["version"]) is not int or identity["version"] != 1
        or identity["service"] != service or not valid_pid(identity["pid"])
        or not _integer(identity["uid"], 2**32 - 1)
        or not _integer(identity["start_ticks"], 2**64 - 1)
        or not isinstance(identity["boot_id"], str)
        or not re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", identity["boot_id"])
    ):
        raise UnsafeRecord("Invalid identity record")
    return identity


def _signature(st):
    return (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)


@dataclass(frozen=True)
class Snapshot:
    signature: tuple
    data: bytes


def _read(path, limit):
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        if os.path.lexists(path):
            raise UnsafeRecord("Unreadable record") from None
        return None
    except OSError as exc:
        raise UnsafeRecord("Unreadable record") from exc
    with os.fdopen(descriptor, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
            raise UnsafeRecord("Invalid record type or size")
        data = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
        try:
            current = path.lstat()
        except OSError as exc:
            raise UnsafeRecord("Record changed while reading") from exc
        if len(data) > limit or _signature(before) != _signature(after) or _signature(after) != _signature(current):
            raise UnsafeRecord("Record changed while reading")
        return Snapshot(_signature(after), data)


def process_info(pid, proc_root=Path("/proc")):
    """Read stat field22 after the final ')', plus real UID and boot ID."""
    if not valid_pid(pid):
        raise UnsafeRecord("Invalid process PID")
    root = Path(proc_root)
    try:
        boot = (root / "sys/kernel/random/boot_id").read_text().strip()
        try:
            text = (root / str(pid) / "stat").read_text()
        except FileNotFoundError:
            if root.is_dir() and not (root / str(pid)).exists():
                return None
            raise
        close = text.rfind(")")
        prefix = text[:text.find("(")].strip()
        fields = text[close + 1:].split()
        if close < 0 or prefix != str(pid) or len(fields) < 20:
            raise UnsafeRecord("Invalid process stat")
        status = (root / str(pid) / "status").read_text()
        uid_match = re.search(r"^Uid:\s+(\d+)\s+\d+\s+\d+\s+\d+\s*$", status, re.MULTILINE)
        if not uid_match:
            raise UnsafeRecord("Missing process UID")
        info = {"pid": pid, "boot_id": boot, "start_ticks": int(fields[19]), "uid": int(uid_match.group(1))}
        # Reuse record validation for strict numeric/boot syntax checks.
        parse_identity(json.dumps({"version": 1, "service": "probe", **info}).encode(), "probe")
        info["parent_pid"] = int(fields[1])
        if not _integer(info["parent_pid"], _MAX_PID) or fields[0] not in ("R", "S", "D", "Z", "T", "t", "X", "x", "K", "W", "P", "I"):
            raise UnsafeRecord("Invalid process stat state or parent")
        info["state"] = fields[0]
        return info
    except (OSError, ValueError, IndexError) as exc:
        raise UnsafeRecord("Process identity unavailable") from exc


@dataclass(frozen=True)
class Inspection:
    state: str
    identity: dict | None = None
    pid_snapshot: Snapshot | None = None
    identity_snapshot: Snapshot | None = None
    legacy: bool = False


def _inspect_pair(pid_record, identity_record, service, proc_root, *, require_identity=False):
    if pid_record is None:
        return Inspection(DEAD) if identity_record is None else Inspection(UNSAFE)
    pid = parse_pid(pid_record.data)
    identity = parse_identity(identity_record.data, service) if identity_record else None
    if identity is not None and identity["pid"] != pid:
        return Inspection(UNSAFE)
    if identity is None and require_identity:
        return Inspection(UNSAFE)
    current = process_info(pid, proc_root)
    if identity is None:
        state = DEAD if current is None or current["state"] in ("Z", "X", "x") else UNSAFE
        return Inspection(state, None, pid_record, None, legacy=True)
    if current is None:
        return Inspection(DEAD, identity, pid_record, identity_record)
    if any(current[key] != identity[key] for key in ("pid", "boot_id", "start_ticks", "uid")):
        return Inspection(UNSAFE)
    state = DEAD if current["state"] in ("Z", "X", "x") else RUNNING
    return Inspection(state, identity, pid_record, identity_record)


class LifecycleRecord:
    """One stable flock context. No skip-lock mode is available.

    An inherited FD must reference this exact nonsymlink lock inode and
    successfully acquire LOCK_EX|LOCK_NB. Closing its duplicate never issues
    LOCK_UN, which would release the launcher's shared open-description lock.
    """

    def __init__(self, pid_file, service, *, proc_root=Path("/proc"), lock_fd=None, blocking=True):
        if not isinstance(service, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", service):
            raise UnsafeRecord("Invalid service name")
        self.path = Path(pid_file)
        self.identity_path = Path(str(self.path) + ".identity")
        self.lock_path = Path(str(self.path) + ".lifecycle.lock")
        self.service = service
        self.proc_root = Path(proc_root)
        self.inherited_fd = lock_fd
        self.blocking = blocking
        self.fd = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            if self.inherited_fd is None:
                self.fd = os.open(self.lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, 0o600)
            elif type(self.inherited_fd) is int and 0 <= self.inherited_fd <= 2**31 - 1:
                self.fd = os.dup(self.inherited_fd)
            else:
                raise UnsafeRecord("Invalid inherited lock descriptor")
            self._check_lock()
            flags = fcntl.LOCK_EX | (fcntl.LOCK_NB if self.inherited_fd is not None or not self.blocking else 0)
            fcntl.flock(self.fd, flags)
            self._check_lock()
            return self
        except (OSError, UnsafeRecord) as exc:
            if self.fd is not None:
                os.close(self.fd)
                self.fd = None
            raise UnsafeRecord("Lifecycle lock unavailable") from exc

    def _check_lock(self):
        if self.fd is None:
            raise UnsafeRecord("Lifecycle lock not held")
        descriptor = os.fstat(self.fd)
        entry = self.lock_path.lstat()
        if not stat.S_ISREG(entry.st_mode) or not stat.S_ISREG(descriptor.st_mode) or (entry.st_dev, entry.st_ino) != (descriptor.st_dev, descriptor.st_ino):
            raise UnsafeRecord("Lifecycle lock changed")

    def __exit__(self, *args):
        if self.fd is not None:
            if self.inherited_fd is None:
                fcntl.flock(self.fd, fcntl.LOCK_UN)
            os.close(self.fd)
            self.fd = None

    def inspect(self):
        try:
            self._check_lock()
            pid_record = _read(self.path, 32)
            identity_record = _read(self.identity_path, 2048)
            return _inspect_pair(pid_record, identity_record, self.service, self.proc_root)
        except (UnsafeRecord, OSError):
            return Inspection(UNSAFE)

    def is_current_self_record(self):
        """Recognize current-process publication or its integer-only prewrite."""
        observed = self.inspect()
        if observed.state == RUNNING:
            return observed.identity["pid"] == os.getpid()
        if observed.state != UNSAFE:
            return False
        try:
            self._check_lock()
            if _read(self.identity_path, 2048) is not None:
                return False
            pid_record = _read(self.path, 32)
            if pid_record is None or parse_pid(pid_record.data) != os.getpid():
                return False
            current = process_info(os.getpid(), self.proc_root)
            return current is not None and current["state"] not in ("Z", "X", "x")
        except (OSError, UnsafeRecord):
            return False

    def _unchanged(self, expected):
        self._check_lock()
        return (_read(self.path, 32), _read(self.identity_path, 2048)) == (expected.pid_snapshot, expected.identity_snapshot)

    def cleanup(self, expected=None, *, current_self=False):
        observed = self.inspect()
        expected = observed if expected is None else expected
        own_shutdown = current_self and observed.state == RUNNING and observed.identity is not None and observed.identity["pid"] == os.getpid()
        if observed.state != DEAD and not own_shutdown:
            return False
        try:
            if not self._unchanged(expected):
                return False
            # Recheck the pair before removing either entry. Stable locks
            # serialize cooperative publishers; same-UID forgery is out of scope.
            if expected.identity_snapshot is not None:
                if _read(self.identity_path, 2048) != expected.identity_snapshot:
                    return False
                self.identity_path.unlink()
            if expected.pid_snapshot is not None:
                if _read(self.path, 32) != expected.pid_snapshot:
                    return False
                self.path.unlink()
            return True
        except (OSError, UnsafeRecord):
            return False

    def publish(self, pid, *, launcher_parent=None):
        """Publish only self or a proven direct child, never a discovered PID.

        CLI helpers use launcher_parent to check the shell's freshly spawned
        sibling child. Python callers normally omit it (self/direct child).
        """
        self._check_lock()
        if launcher_parent is not None and launcher_parent != os.getppid():
            raise UnsafeRecord("Invalid launcher parent")
        current = process_info(pid, self.proc_root)
        parent = os.getpid() if launcher_parent is None else launcher_parent
        if current is None or current["state"] in ("Z", "X", "x") or not (pid == os.getpid() and launcher_parent is None or current["parent_pid"] == parent):
            raise UnsafeRecord("Process is not a live owned child or self")
        observed = self.inspect()
        identity = {"version": 1, "service": self.service, **{key: current[key] for key in ("pid", "boot_id", "start_ticks", "uid")}}
        if observed.state == UNSAFE:
            # A launcher's integer prewrite is valid only for this proven
            # child/self and with no sidecar; all other unsafe evidence stays.
            pid_record = _read(self.path, 32)
            if _read(self.identity_path, 2048) is not None or pid_record is None or parse_pid(pid_record.data) != pid:
                raise UnsafeRecord("Existing process record is unsafe")
            observed = Inspection(UNSAFE, None, pid_record, None, True)
        elif observed.state == RUNNING and observed.identity != identity:
            raise UnsafeRecord("Existing process is running")
        if not self._unchanged(observed):
            raise UnsafeRecord("Process records changed")
        self._atomic_write(self.path, str(pid).encode(), observed.pid_snapshot)
        self._atomic_write(self.identity_path, json.dumps(identity, sort_keys=True).encode(), observed.identity_snapshot)
        published = self.inspect()
        if published.state != RUNNING or published.identity != identity:
            raise UnsafeRecord("Published identity could not be verified")
        return published

    def _atomic_write(self, target, data, expected):
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".identity-", delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            if _read(target, 2048) != expected:
                raise UnsafeRecord("Process record changed before publication")
            os.replace(temporary, target)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def signal(self, requested_signal, expected=None):
        """Revalidate a durable identity immediately before every signal."""
        if not isinstance(requested_signal, int) or isinstance(requested_signal, bool) or requested_signal not in (signal.SIGTERM, signal.SIGKILL, signal.SIGHUP, signal.SIGUSR1):
            return UNSAFE
        observed = self.inspect()
        if expected is not None and (
            observed.identity != expected.identity or observed.pid_snapshot != expected.pid_snapshot
            or observed.identity_snapshot != expected.identity_snapshot
        ):
            return UNSAFE
        if observed.state != RUNNING:
            return observed.state
        # A second complete inspection detects replacement after initial lookup.
        current = self.inspect()
        if current != observed:
            return UNSAFE
        try:
            os.kill(current.identity["pid"], requested_signal)
        except ProcessLookupError:
            return DEAD if self.inspect().state == DEAD else UNSAFE
        except OSError:
            return UNSAFE
        return RUNNING

    def stop(self, timeout=5.0):
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout < 0:
            return UNSAFE
        original = self.inspect()
        if original.state == UNSAFE:
            return UNSAFE
        if original.state == DEAD:
            return DEAD if self.cleanup(original) else UNSAFE
        for requested_signal in (signal.SIGTERM, signal.SIGKILL):
            result = self.signal(requested_signal, expected=original)
            if result == UNSAFE:
                return UNSAFE
            deadline = time.monotonic() + timeout
            while True:
                current = self.inspect()
                if current.state == UNSAFE or current.identity != original.identity or current.pid_snapshot != original.pid_snapshot or current.identity_snapshot != original.identity_snapshot:
                    return UNSAFE
                if current.state == DEAD:
                    return DEAD if self.cleanup(original) else UNSAFE
                if time.monotonic() >= deadline:
                    break
                time.sleep(min(0.05, max(0, deadline - time.monotonic())))
        return UNSAFE


def inspect_record(pid_file, service):
    """Read bounded stable snapshots without mkdir, locks, cleanup or signals.

    A missing identity partner or concurrent replacement is unsafe. The result
    supplies no startup/signal authority and can become stale after return.
    Lifecycle mutations still hold their own lock and revalidate independently.
    """
    try:
        record = LifecycleRecord(pid_file, service)  # validates names; never enters a lock
        pair = (_read(record.path, 32), _read(record.identity_path, 2048))
        observed = _inspect_pair(*pair, service, record.proc_root, require_identity=True)
        if pair != (_read(record.path, 32), _read(record.identity_path, 2048)):
            return Inspection(UNSAFE)
        return observed
    except (OSError, UnsafeRecord):
        return Inspection(UNSAFE)



@dataclass(frozen=True)
class SpawnReady:
    outcome: str
    child_pid: int | None = None
    guardian_pid: int | None = None


def parse_spawn_ready(data):
    """Strict bounded private-pipe grammar; returned PIDs confer no authority."""
    if not isinstance(data, bytes) or len(data) > 96:
        raise UnsafeRecord("Invalid spawn readiness")
    if data == b"failed-cleanup-confirmed\n":
        return SpawnReady("failed-cleanup-confirmed")
    matched = re.fullmatch(rb"published ([1-9][0-9]{0,9})\n", data)
    if matched:
        return SpawnReady("published", child_pid=parse_pid(matched[1]))
    matched = re.fullmatch(rb"retained ([1-9][0-9]{0,9}) ([1-9][0-9]{0,9})\n", data)
    if matched:
        guardian, child = parse_pid(matched[1]), parse_pid(matched[2])
        if guardian != child:
            return SpawnReady("retained", child_pid=child, guardian_pid=guardian)
    raise UnsafeRecord("Invalid spawn readiness")


def _bounded_seconds(value, maximum):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= maximum:
        raise UnsafeRecord("Invalid spawn timing")
    return float(value)


def _ready_pipe(fd, lock_fd):
    if type(fd) is not int or not 3 <= fd <= _MAX_PID or fd == lock_fd:
        raise UnsafeRecord("Invalid readiness descriptor")
    if not stat.S_ISFIFO(os.fstat(fd).st_mode) or fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_ACCMODE != os.O_WRONLY:
        raise UnsafeRecord("Readiness descriptor must be a writable pipe")
    # One <= PIPE_BUF atomic write must not hang behind a broken reader.
    os.set_blocking(fd, False)
    return fd


class OwnedLaunch:
    """A single actual child and its publication/failed-launch ownership.

    run() only relinquishes a successfully published child or a reaped child.
    Failed cleanup never returns: this same helper retains its Popen and lock
    as a guardian until it can reap. SIGKILL/host crash can defeat that purely
    in-memory fallback; no durable marker is promised when writes fail.
    """

    def __init__(self, record, argv, *, log_file, ready_fd, cwd=None, startup_delay=0.5, timeout=5.0):
        self.record = record
        if not isinstance(argv, (list, tuple)):
            raise UnsafeRecord("Service arguments must be an argv list")
        self.argv = list(argv)
        if not self.argv or any(not isinstance(arg, str) or "\0" in arg for arg in self.argv):
            raise UnsafeRecord("Invalid service arguments")
        if not isinstance(log_file, (str, os.PathLike)) or cwd is not None and not isinstance(cwd, (str, os.PathLike)):
            raise UnsafeRecord("Invalid service paths")
        self.log_file = log_file
        self.ready_fd = _ready_pipe(ready_fd, record.inherited_fd)
        self.cwd = cwd
        self.startup_delay = _bounded_seconds(startup_delay, 5.0)
        self.timeout = _bounded_seconds(timeout, 30.0)
        self.child = None
        self.publication = None
        self.interrupted = False
        self.ready_attempted = False
        self.handed_off = False

    def _report(self, outcome):
        if self.ready_attempted:
            return False
        self.ready_attempted = True
        try:
            data = outcome.encode("ascii") + b"\n"
            parse_spawn_ready(data)
            return os.write(self.ready_fd, data) == len(data)
        except BaseException:
            return False
        finally:
            try:
                os.close(self.ready_fd)
            except BaseException:
                pass
            self.ready_fd = None

    def _reap_owned(self):
        if self.child is None:
            return True
        try:
            if self.child.poll() is None:
                try:
                    self.child.terminate()
                except ProcessLookupError:
                    pass  # still confirm/reap through this actual Popen
                try:
                    self.child.wait(timeout=self.timeout)
                except subprocess.TimeoutExpired:
                    if self.child.poll() is None:
                        try:
                            self.child.kill()
                        except ProcessLookupError:
                            pass
                    self.child.wait(timeout=self.timeout)
            else:
                self.child.wait(timeout=self.timeout)
            return self.child.poll() is not None
        except BaseException:
            return False  # interruptions never discard the owned child

    def _cleanup_record(self):
        if self.publication is not None:
            try:
                self.record.cleanup(self.publication)
            except BaseException:
                pass  # child exit is confirmed; preserve uncertain/replaced evidence

    @contextmanager
    def _signal_requests(self):
        previous = {}
        def request_cleanup(*_):
            self.interrupted = True
        try:
            for sig in (signal.SIGHUP, signal.SIGTERM, signal.SIGINT, signal.SIGQUIT):
                previous[sig] = signal.signal(sig, signal.SIG_IGN if sig == signal.SIGHUP else request_cleanup)
            yield
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)

    def run(self):
        """Emit one private result and return 0 only after successful publication."""
        with self._signal_requests():
            try:
                self.record._check_lock()
                observed = self.record.inspect()
                if observed.state != DEAD or not self.record.cleanup(observed):
                    raise UnsafeRecord("Service launch blocked by existing evidence")
                # Keep only our handle immediately after Popen returns. Every
                # later operation, including file close, converges on cleanup.
                with open(self.log_file, "ab", buffering=0) as log:
                    self.child = subprocess.Popen(
                        self.argv, cwd=self.cwd, stdin=subprocess.DEVNULL,
                        stdout=log, stderr=subprocess.STDOUT, close_fds=True,
                    )
                if self.interrupted:
                    raise UnsafeRecord("Service launch interrupted")
                self.publication = self.record.publish(self.child.pid)
                deadline = time.monotonic() + self.startup_delay
                while True:
                    if self.interrupted or self.child.poll() is not None:
                        raise UnsafeRecord("Service launch did not remain live")
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    time.sleep(min(0.05, remaining))
                if self.record.inspect() != self.publication:
                    raise UnsafeRecord("Service publication changed")
                if self._report(f"published {self.child.pid}"):
                    # Durable identity + live observation + delivered private
                    # published result commit the handoff. Later restoration
                    # errors must not turn that child into a failed guardian
                    # outside the cleanup-request signal context.
                    self.handed_off = True
                    return 0
                # Failed readiness delivery is a failed launch too.
            except BaseException:
                pass
            return self.finish_failure()

    def finish_failure(self):
        """Never release an unconfirmed child, including after interrupted setup."""
        if self._reap_owned():
            self._cleanup_record()
            self._report("failed-cleanup-confirmed")
            return 2
        self._report(f"retained {os.getpid()} {self.child.pid}")
        # The private pipe is closed before this loop. Parent can return
        # bounded failure while we retain both child and same lock FD.
        while True:
            try:
                time.sleep(0.5)
            except BaseException:
                pass
            if self._reap_owned():
                self._cleanup_record()
                return 2


class _SpawnParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse normally echoes unrecognized values, which may be secrets.
        raise UnsafeRecord("Invalid owned-spawn arguments")


def _spawn_main(argv):
    ready_fd = None
    try:
        parser = _SpawnParser(add_help=False)
        parser.add_argument("--pid-file", required=True)
        parser.add_argument("--service", required=True)
        parser.add_argument("--lock-fd", required=True, type=int)
        parser.add_argument("--ready-fd", required=True, type=int)
        parser.add_argument("--log-file", required=True)
        parser.add_argument("--cwd")
        parser.add_argument("--startup-delay", type=float, default=0.5)
        parser.add_argument("--timeout", type=float, default=5.0)
        parser.add_argument("command", nargs=argparse.REMAINDER)
        args = parser.parse_args(argv)
        ready_fd = _ready_pipe(args.ready_fd, args.lock_fd)
        if not args.command or args.command[0] != "--":
            raise UnsafeRecord("Service argv delimiter required")
        with LifecycleRecord(args.pid_file, args.service, lock_fd=args.lock_fd) as record:
            launch = OwnedLaunch(record, args.command[1:], log_file=args.log_file, ready_fd=ready_fd, cwd=args.cwd, startup_delay=args.startup_delay, timeout=args.timeout)
            ready_fd = None  # launch owns closing this pipe, including guardian path
            try:
                return launch.run()
            except BaseException:
                if launch.handed_off:
                    return 0
                # All other signal-context exits occur before spawn or after
                # confirmed reap; failed-live guardians stay inside run().
                return launch.finish_failure()
    except BaseException:
        if ready_fd is not None:
            try:
                os.write(ready_fd, b"failed-cleanup-confirmed\n")
            except OSError:
                pass
            finally:
                os.close(ready_fd)
        # Fixed, payload-free diagnostics; the service argv is never printed.
        print("Owned service launch failed", file=sys.stderr)
        return 2

def _pid_argument(text):
    try:
        return parse_pid(text.encode("ascii"))
    except (UnsafeRecord, UnicodeError) as exc:
        raise argparse.ArgumentTypeError("Invalid PID") from exc


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "spawn":
        return _spawn_main(argv[1:])
    parser = argparse.ArgumentParser(description="Validate recorded service process identity")
    parser.add_argument("operation", choices=("record", "inspect", "cleanup", "signal", "stop"))
    parser.add_argument("pid_file")
    parser.add_argument("service")
    parser.add_argument("--pid", type=_pid_argument)
    parser.add_argument("--signal", choices=("TERM", "KILL", "HUP", "USR1"), default="USR1")
    parser.add_argument("--timeout", type=float, default=5)
    parser.add_argument("--lock-fd", type=int)
    args = parser.parse_args(argv)
    result = UNSAFE
    try:
        if args.operation == "inspect" and args.lock_fd is None:
            result = inspect_record(args.pid_file, args.service).state
        else:
            with LifecycleRecord(args.pid_file, args.service, lock_fd=args.lock_fd) as record:
                if args.operation == "record":
                    record.publish(args.pid, launcher_parent=os.getppid())
                    result = RUNNING
                elif args.operation == "inspect":
                    result = record.inspect().state
                elif args.operation == "cleanup":
                    result = DEAD if record.cleanup() else UNSAFE
                elif args.operation == "signal":
                    result = record.signal(getattr(signal, "SIG" + args.signal))
                else:
                    result = record.stop(args.timeout)
    except (OSError, UnsafeRecord):
        result = UNSAFE
    print(result)
    # Inspect/signal distinguish already-dead (1) from running/sent (0).
    # Completed stop/cleanup are conventional successful actions (0).
    if args.operation in ("stop", "cleanup") and result == DEAD:
        return 0
    return {RUNNING: 0, DEAD: 1, UNSAFE: 2}[result]


if __name__ == "__main__":
    raise SystemExit(main())
