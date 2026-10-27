"""Scratch replay tripwires, installed before any product/hunter import.

This is a recording bootstrap, not a Python/native or filesystem sandbox.
Every intercepted primitive raises. No real-process or loopback escape is kept.
"""
import hashlib
import json
import os
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parent / "replay_guard_runs"
LIVE_REPO = Path("/data/data/com.termux/files/home/Codey-OS")
ENV_PATHS = ("HOME", "CODEY_STATE_DIR", "CODEY_ACTION_GATEWAY_AUDIT",
             "CODEY_CONFIG_PATH", "RESTORICON_DB_PATH", "TMPDIR", "GIT_CONFIG_GLOBAL")


class GuardViolation(RuntimeError):
    """Preflight or recorder-integrity failure: do not import/run a target."""


class ReplayBlocked(RuntimeError):
    """A primitive was recorded and refused before real execution."""


def _under(path, parent):
    return path == parent or parent in path.parents


def validate_root(raw, protected_repo=LIVE_REPO):
    """Require an existing nonce directory inside our dedicated scratch base.

    Reject symlinked roots and both directions of overlap with the live repo.
    The dedicated base is not itself a writable fixture root.
    """
    p = Path(raw)
    if not p.is_absolute():
        raise GuardViolation("root must be absolute")
    resolved = p.resolve(strict=True)
    base = BASE.resolve()
    forbidden = Path(protected_repo).resolve()
    if not resolved.is_dir() or p != resolved:
        raise GuardViolation("root must be a real directory, not a symlink")
    if resolved == base or not _under(resolved, base):
        raise GuardViolation("root must be below the dedicated scratch base")
    if _under(resolved, forbidden) or _under(forbidden, resolved):
        raise GuardViolation("root overlaps protected repository")
    return resolved


def _summary(value, depth=0):
    """Type/hash-only event arguments: do not repr unknown objects or secrets."""
    t = type(value)
    if value is None or (t is bool or t is int):
        return value
    if t is float:
        return {"type": "float"}  # avoid NaN/Infinity and noncanonical JSON
    if (t is str or t is bytes):
        raw = value.encode("utf-8", "surrogatepass") if t is str else value
        return {"type": t.__name__, "length": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest()}
    if depth >= 4:
        return {"truncated": True}
    if (t is tuple or t is list):
        return {"type": t.__name__, "length": len(value),
                "items": [_summary(x, depth + 1) for x in value[:32]]}
    if t is dict:
        items = list(value.items())[:32]
        return {"type": "dict", "length": len(value),
                "items": [[_summary(k, depth + 1), _summary(v, depth + 1)]
                          for k, v in items]}
    return {"type": "opaque"}


class Guard:
    """Own one validated root, bounded in-memory events and installed symbols."""
    def __init__(self, root):
        self.root = root
        self.events = []
        self.patches = []
        self.capabilities = {}
        self.sealed = False

    def path(self, relative):
        """Validate each fixture/report write at call time, including symlinks."""
        rel = Path(relative)
        if rel.is_absolute() or not rel.parts or ".." in rel.parts:
            raise GuardViolation("fixture path must be a relative descendant")
        result = (self.root / rel).resolve()
        if result == self.root or not _under(result, self.root):
            raise GuardViolation("fixture path escapes root")
        return result

    def write_text(self, relative, text):
        path = self.path(relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Recheck after creating parents; caller must own this scratch tree.
        path = self.path(relative)
        path.write_text(text, encoding="utf-8")
        return path

    def block(self, label):
        def denied(*args, **kwargs):
            if len(self.events) >= 10000:
                raise GuardViolation("event budget exhausted")
            self.events.append({"api": label, "args": _summary(args),
                                "kwargs": _summary(kwargs)})
            raise ReplayBlocked(label)
        return denied

    def patch(self, owner, name, label):
        if not hasattr(owner, name):
            self.capabilities[label] = "unavailable on this runtime"
            return
        fn = self.block(label)
        try:
            setattr(owner, name, fn)
        except (AttributeError, TypeError) as exc:
            raise GuardViolation("cannot install primitive " + label) from exc
        self.patches.append((owner, name, fn, label))
        self.capabilities[label] = "installed"

    def assert_integrity(self):
        if not self.sealed:
            raise GuardViolation("installation is not complete")
        for owner, name, fn, label in self.patches:
            if getattr(owner, name) is not fn:
                raise GuardViolation("recorder replaced: " + label)

    def save(self, relative):
        self.assert_integrity()
        return self.write_text(relative, json.dumps({
            "root": str(self.root), "capabilities": self.capabilities,
            "events": self.events,
        }, indent=2) + "\n")


def install(root, protected_repo=LIVE_REPO, require_requests=True):
    """Install before target imports, fail closed on invalid env/missing patches.

    Standard-library/bootstrap imports happen here before targets. Requests is
    imported only after low-level network/process blockers are installed.
    This does not prove all dynamic receivers or native calls are intercepted.
    """
    root = validate_root(root, protected_repo)
    if os.environ.get("CODEY_REPLAY_ROOT") != str(root):
        raise GuardViolation("CODEY_REPLAY_ROOT must match validated root")
    for key in ENV_PATHS:
        raw = os.environ.get(key)
        if not raw or not Path(raw).is_absolute():
            raise GuardViolation("missing absolute disposable path: " + key)
        p = Path(raw).resolve()
        if not _under(p, root) or p == root:
            raise GuardViolation("environment path escapes root: " + key)
    if any(k.lower().endswith("_proxy") for k in os.environ):
        raise GuardViolation("inherited proxy environment forbidden")
    # Do not silently accept prior product imports or an installed guard from
    # another snapshot. Prefix restriction is intentionally conservative.
    if any(n == "main" or n.split(".")[0] in
           {"core", "tools", "ccos", "utils", "bench", "restoricon_core"}
           for n in sys.modules):
        raise GuardViolation("product module imported before guard")
    import subprocess
    import socket
    import urllib.request
    import http.client
    import asyncio
    import asyncio.subprocess
    import asyncio.base_events
    import asyncio.unix_events
    import multiprocessing
    import multiprocessing.process
    import pty
    import ctypes

    g = Guard(root)
    for name in ("run", "Popen", "call", "check_call", "check_output", "getoutput", "getstatusoutput"):
        g.patch(subprocess, name, "subprocess." + name)
    names = {n for n in dir(os) if n.startswith(("exec", "spawn", "posix_spawn"))}
    names.update({"system", "popen", "fork", "forkpty", "kill", "killpg", "startfile"})
    for name in sorted(names):
        g.patch(os, name, "os." + name)
    for name in ("connect", "connect_ex", "bind", "listen", "accept", "send", "sendall", "sendto", "sendmsg"):
        g.patch(socket.socket, name, "socket.socket." + name)
    for name in ("create_connection", "create_server", "getaddrinfo", "gethostbyname", "gethostbyname_ex",
                 "gethostbyaddr", "getnameinfo", "getfqdn"):
        g.patch(socket, name, "socket." + name)
    for cls in (http.client.HTTPConnection, http.client.HTTPSConnection):
        for name in ("connect", "request", "send", "getresponse"):
            g.patch(cls, name, "http.client." + cls.__name__ + "." + name)
    for name in ("urlopen", "urlretrieve"):
        g.patch(urllib.request, name, "urllib.request." + name)
    for class_name in ("OpenerDirector", "URLopener", "FancyURLopener"):
        cls = getattr(urllib.request, class_name, None)
        if cls is None:
            g.capabilities["urllib.request." + class_name + ".open"] = "unavailable on this runtime"
        else:
            g.patch(cls, "open", "urllib.request." + class_name + ".open")
    for module in (asyncio, asyncio.subprocess):
        for name in ("create_subprocess_exec", "create_subprocess_shell"):
            g.patch(module, name, module.__name__ + "." + name)
    for name in ("open_connection", "start_server", "open_unix_connection", "start_unix_server"):
        g.patch(asyncio, name, "asyncio." + name)
    for name in ("subprocess_exec", "subprocess_shell", "create_connection", "create_server",
                 "create_datagram_endpoint", "create_unix_connection", "create_unix_server", "getaddrinfo"):
        g.patch(asyncio.base_events.BaseEventLoop, name, "asyncio.BaseEventLoop." + name)
    # Unix overrides must be patched too; inherited BaseEventLoop methods
    # alone do not cover socket/unix-specific implementations.
    for name in ("_make_subprocess_transport", "create_unix_connection", "create_unix_server"):
        g.patch(asyncio.unix_events._UnixSelectorEventLoop, name, "asyncio.UnixSelectorEventLoop." + name)
    g.patch(multiprocessing.process.BaseProcess, "start", "multiprocessing.BaseProcess.start")
    g.patch(multiprocessing, "Pool", "multiprocessing.Pool")
    for name in ("fork", "spawn"):
        g.patch(pty, name, "pty." + name)
    for name in ("CDLL", "PyDLL", "WinDLL", "OleDLL"):
        g.patch(ctypes, name, "ctypes." + name)
    g.patch(ctypes.LibraryLoader, "LoadLibrary", "ctypes.LibraryLoader.LoadLibrary")
    # Lazy LibraryLoader attribute access captures a constructor internally.
    g.patch(ctypes.LibraryLoader, "__getattr__", "ctypes.LibraryLoader.__getattr__")
    try:
        import requests
    except ImportError as exc:
        g.capabilities["requests"] = "unavailable; low-level socket/DNS blockers installed"
        if require_requests:
            raise GuardViolation("required Requests recorder unavailable") from exc
    else:
        for name in ("request", "send"):
            g.patch(requests.sessions.Session, name, "requests.Session." + name)
        for module in (requests, requests.api):
            for name in ("request", "get", "post", "put", "patch", "delete", "head", "options"):
                g.patch(module, name, module.__name__ + "." + name)
    g.sealed = True
    g.assert_integrity()
    return g
