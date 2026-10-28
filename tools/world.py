"""World manager: disposable, empty Restoricon dev stores (WP2.2 S4).

A world lives under a worlds root that sits OUTSIDE ``~/.codeyOS`` (default
``<passwd home>/.codeyOS-worlds``) so dev/test work never touches live
business data (CLAUDE.md rule 0(b)).  This is a seatbelt, not a boundary
(NEW-1069): it deletes directories, so every destructive step is fd-relative
and re-checked, and it never launches, signals or kills anything.

Limits: this is a seatbelt against mistakes, not a security boundary.  The
manifest records the world dir's st_dev/st_ino at create so a COPIED or stale
world.json in another directory is refused.  That binding is NOT a defence
against a same-uid process: anything that can stat a directory can write a
matching manifest, so a root sibling with a hand-forged manifest is deletable
under the same-uid trust model (such a writer could simply rm it; that is
NEW-1069's scope).  Keep only worlds in the worlds root; sibling directories
are not protected from each other.

Worlds are EMPTY only: the DB is a schema-only ``DatabaseManager`` store on
the world's own path.  Imports are limited to stdlib, ``restoricon_core.world``
and ``DatabaseManager``: never ``utils.config`` or ``core.*`` (import-time
state, NEW-855).

CLI: ``python3 -m tools.world {create NAME | list [--json] | env NAME |
destroy NAME [--yes]}``.  Exit 0 ok, 2 refusal/validation, 1 unexpected.
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import os
import re
import shlex
import socket
import stat
import sys
from datetime import datetime, timezone
from typing import Dict, List, Optional

from restoricon_core import world as guard
from restoricon_core.database import DatabaseManager

NAME_RE = re.compile(r"[a-z0-9][a-z0-9_-]{0,39}", re.ASCII)
RESERVED = frozenset(
    {"production", "live", "default", "restoricon", "codeyos", "worlds"}
)
PORT_LO, PORT_HI = 18770, 18999  # Aigentik default is 8000 (outside the range)
MARKER = ".codey-worlds-root"
LOCKFILE = ".lock"
MANIFEST = "world.json"
MAX_DEPTH = 32
_MAX_JSON = 64 * 1024


class WorldRefusal(Exception):
    """A validation/safety refusal (exit code 2)."""


# ---------------------------------------------------------------- names/root

def validate_name(name) -> str:
    """Return ``name`` if it is a legal world name, else raise WorldRefusal.

    Exact-string fullmatch (no strip/normalisation) so a trailing newline,
    separators, NUL, dots or non-ASCII can never reach a path join.
    """
    if not isinstance(name, str) or NAME_RE.fullmatch(name) is None:
        raise WorldRefusal(f"invalid world name {name!r}: must match [a-z0-9][a-z0-9_-]{{0,39}}")
    if name in RESERVED:
        raise WorldRefusal(f"world name {name!r} is reserved")
    return name


def _within(path: str, base: str) -> bool:
    """True if path == base or lies below it (separator-terminated compare)."""
    if path == base:
        return True
    prefix = base if base.endswith(os.sep) else base + os.sep
    return path.startswith(prefix)


def worlds_root() -> str:
    """Unvalidated absolute worlds root: env override else passwd-home sibling.

    The passwd home (not $HOME) is used so a disposable HOME cannot rebase it.
    """
    env = os.environ.get("CODEY_WORLDS_ROOT")
    if env:
        if "\x00" in env or not os.path.isabs(env):
            raise guard.WorldConfigError("CODEY_WORLDS_ROOT must be an absolute path")
        return os.path.normpath(env)
    return os.path.join(guard._passwd_home(), ".codeyOS-worlds")


def _live_dirs() -> List[str]:
    """Realpaths of every directory that holds (or would hold) the live DB."""
    dirs = {os.path.realpath(os.path.dirname(p)) for p in guard.live_db_paths()}
    dirs.add(os.path.realpath(os.path.join(guard._passwd_home(), ".codeyOS")))
    return sorted(dirs)


def assert_root_safe(root: str) -> str:
    """Validate the worlds root and return its realpath, or raise.

    Why: ``destroy`` deletes trees, so a hostile CODEY_WORLDS_ROOT (``~``,
    ``~/.codeyOS``, ``/``, a symlink, a shared-writable dir) must be refused
    before any filesystem effect.  Refused: the root equals/lies inside the
    live dir, is an ancestor of it, is ``/`` or the home, is a symlink or
    non-directory, or is group/other-writable.  Resolution errors fail closed.
    """
    raw = os.path.normpath(root)
    real = os.path.realpath(raw)
    home = os.path.realpath(guard._passwd_home())
    if real == os.sep or real == home:
        raise WorldRefusal(f"worlds root {real!r} is / or the home directory")
    for ld in _live_dirs():
        if _within(real, ld):
            raise WorldRefusal(f"worlds root {real!r} is inside the live state dir {ld!r}")
        if _within(ld, real):
            raise WorldRefusal(f"worlds root {real!r} contains the live state dir {ld!r}")
    try:
        st = os.lstat(raw)
    except FileNotFoundError:
        return real
    if stat.S_ISLNK(st.st_mode):
        raise WorldRefusal(f"worlds root {raw!r} is a symlink")
    if not stat.S_ISDIR(st.st_mode):
        raise WorldRefusal(f"worlds root {raw!r} is not a directory")
    if st.st_mode & 0o022:
        raise WorldRefusal(f"worlds root {raw!r} is group/other-writable")
    return real


def _regular_nofollow(path: str) -> bool:
    """True if path is a regular file and not a symlink (lstat)."""
    try:
        return stat.S_ISREG(os.lstat(path).st_mode)
    except OSError:
        return False


def _open_reg(path: str, dir_fd: Optional[int] = None) -> int:
    """Open a regular file for reading; never blocks on a FIFO, never follows a link.

    O_NONBLOCK makes open(2) on a FIFO return immediately and the fstat then
    rejects anything that is not a regular file, so a planted FIFO cannot hang
    a manifest/pid reader.
    """
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW, dir_fd=dir_fd)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError("not a regular file")
    except BaseException:
        os.close(fd)
        raise
    return fd


def _read_json_nofollow(path: str, dir_fd: Optional[int] = None):
    """Read a small JSON file without following a symlink or blocking on a FIFO."""
    fd = _open_reg(path, dir_fd)
    try:
        blob = os.read(fd, _MAX_JSON + 1)
    finally:
        os.close(fd)
    if len(blob) > _MAX_JSON:
        raise ValueError("file too large")
    try:
        return json.loads(blob.decode("utf-8"))
    except RecursionError:
        # A hostile deeply nested file under the size cap: treat as an
        # unreadable manifest (callers handle ValueError) instead of crashing.
        raise ValueError("JSON nested too deeply") from None


def _write_new(path: str, data: bytes) -> None:
    """Create ``path`` exclusively (no symlink follow, 0600) and fsync it."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)


def _require_marker(root: str) -> None:
    """list/destroy/env need the root marker. It records that tools.world
    initialised this root; it is a mistake guard, not proof: a same-uid writer
    can plant it, as with the manifest (see the module docstring)."""
    marker = os.path.join(root, MARKER)
    if not _regular_nofollow(marker):
        raise WorldRefusal(f"{root!r} has no {MARKER} marker; not a worlds root")
    try:
        data = _read_json_nofollow(marker)
    except (OSError, ValueError):
        raise WorldRefusal(f"{marker!r} is unreadable") from None
    if not isinstance(data, dict) or data.get("created_by") != "tools.world":
        raise WorldRefusal(f"{marker!r} is not a tools.world marker")


def _ensure_root(raw_root: str) -> str:
    """Create (0700) or accept the root for ``create``; return its realpath."""
    real = assert_root_safe(raw_root)
    raw = os.path.normpath(raw_root)
    try:
        os.lstat(raw)
        existed = True
    except FileNotFoundError:
        existed = False
    if not existed:
        os.mkdir(raw, 0o700)
        os.chmod(raw, 0o700)
        real = assert_root_safe(raw_root)
    if not _regular_nofollow(os.path.join(real, MARKER)):
        if os.listdir(real):
            raise WorldRefusal(
                f"{real!r} is not empty and has no {MARKER} marker; refusing to adopt it"
            )
        _write_new(
            os.path.join(real, MARKER),
            json.dumps({"schema": 1, "created_by": "tools.world"}).encode(),
        )
    _require_marker(real)
    return real


def _open_root(need_marker: bool = True) -> str:
    root = assert_root_safe(worlds_root())
    if need_marker:
        _require_marker(root)
    return root


@contextlib.contextmanager
def _create_lock(root: str):
    """Exclusive flock on <root>/.lock: serialises port allocation across creates."""
    fd = os.open(os.path.join(root, LOCKFILE), os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)  # closing releases the flock


# ------------------------------------------------------------------ layout

def _paths(root: str, name: str) -> Dict[str, str]:
    wd = os.path.join(root, name)
    state = os.path.join(wd, "state")
    return {
        "dir": wd,
        "state": state,
        "db": os.path.join(state, "restoricon.db"),
        "docs": os.path.join(state, "restoricon_documents"),
        "audit": os.path.join(state, "action_gateway_audit.jsonl"),
        "manifest": os.path.join(wd, MANIFEST),
    }


def _open_world(root: str, name: str):
    """Open a world dir once and validate it; return (fd, manifest) or raise.

    Why: destroy/env must act only on a directory that tools.world created.
    The dir is opened once with O_NOFOLLOW|O_DIRECTORY and everything else
    (manifest, in-use check, deletion) is done relative to that fd, so the
    path cannot be swapped between check and use.  The manifest must match
    schema, name, creator, root AND the dir's st_dev/st_ino recorded at
    create, so a copied or stale world.json in another directory is refused
    (this does not stop a same-uid writer who stats the dir and forges a
    matching manifest; see the module docstring).
    The caller owns (and must close) the returned fd.
    """
    validate_name(name)
    wd = os.path.join(root, name)
    try:
        st = os.lstat(wd)
    except FileNotFoundError:
        raise WorldRefusal(f"world {name!r} does not exist") from None
    if not stat.S_ISDIR(st.st_mode):  # lstat: a symlink is not a directory
        raise WorldRefusal(f"{wd!r} is not a real directory (symlink or file)")
    real = os.path.realpath(wd)
    if real != wd or os.path.dirname(real) != root:
        raise WorldRefusal(f"{wd!r} does not resolve to a direct child of the root")
    try:
        fd = os.open(wd, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError as exc:
        raise WorldRefusal(f"cannot open {wd!r}: {exc}") from None
    try:
        fst = os.fstat(fd)
        try:
            man = _read_json_nofollow(MANIFEST, fd)
        except (OSError, ValueError):
            raise WorldRefusal(f"{wd}/{MANIFEST} missing, unreadable or malformed") from None
        if not isinstance(man, dict):
            raise WorldRefusal(f"{wd}/{MANIFEST} is not an object")
        if (
            man.get("schema") != 1
            or man.get("name") != name
            or man.get("created_by") != "tools.world"
            or man.get("root") != root
        ):
            raise WorldRefusal(f"{wd}/{MANIFEST} does not describe world {name!r} in this root")
        if man.get("dev") != fst.st_dev or man.get("ino") != fst.st_ino:
            raise WorldRefusal(f"{wd}/{MANIFEST} is not bound to this directory (dev/ino mismatch)")
        port = man.get("port")
        if isinstance(port, bool) or not isinstance(port, int) or not PORT_LO <= port <= PORT_HI:
            raise WorldRefusal(f"{wd}/{MANIFEST} has an invalid port")
    except BaseException:
        os.close(fd)
        raise
    return fd, man


def _load_manifest(root: str, name: str) -> dict:
    """Validated manifest for list/env (opens and closes the world dir)."""
    fd, man = _open_world(root, name)
    os.close(fd)
    return man


# ------------------------------------------------------------------- ports

def _recorded_ports(root: str) -> set:
    """Ports in every readable manifest; unparsable manifests are skipped (documented limit)."""
    used = set()
    try:
        names = os.listdir(root)
    except OSError:
        return used
    for n in names:
        mp = os.path.join(root, n, MANIFEST)
        try:
            if os.path.islink(os.path.join(root, n)):
                continue
            port = _read_json_nofollow(mp).get("port")
        except (OSError, ValueError, AttributeError):
            continue  # unreadable manifest: its port is unknown, nothing to record
        if isinstance(port, int) and not isinstance(port, bool):
            used.add(port)
    return used


def allocate_port(root: str) -> int:
    """First port in 18770-18999 neither recorded in a manifest nor bound.

    Why: dev APIs need distinct loopback ports.  Called under the create
    lock.  The bind probe has SO_REUSEADDR off so a listener is a miss; it
    never connects, never parses ss/netstat, never touches 8770.  The port
    is advisory: a later bind can still race, and the server then fails
    loudly (not a safety property).
    """
    used = _recorded_ports(root)
    for port in range(PORT_LO, PORT_HI + 1):
        if port in used:
            continue
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind(("127.0.0.1", port))
        except OSError:
            continue
        finally:
            s.close()
        return port
    raise WorldRefusal("no free port in 18770-18999")


# ------------------------------------------------------------------ delete

def _walk(dir_fd: int, dev: int, depth: int, delete: bool, rel: str = "") -> int:
    """Walk (and optionally delete) the contents of an open directory fd.

    Returns the entry count.  Everything is relative to dir fds with
    O_NOFOLLOW/no-follow stats, so a symlink swapped in after the check
    cannot redirect the walk.
    """
    if depth > MAX_DEPTH:
        raise WorldRefusal(f"directory nesting exceeds {MAX_DEPTH}")
    count = 0
    for entry in os.listdir(dir_fd):
        st = os.stat(entry, dir_fd=dir_fd, follow_symlinks=False)
        count += 1
        mode = st.st_mode
        if stat.S_ISLNK(mode) or stat.S_ISREG(mode):
            if delete:
                os.unlink(entry, dir_fd=dir_fd)  # a link is removed as a link
        elif stat.S_ISDIR(mode):
            if st.st_dev != dev:
                raise WorldRefusal(f"{entry!r} is on a different filesystem; refusing")
            try:
                sub = os.open(entry, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=dir_fd)
            except OSError as exc:
                raise WorldRefusal(f"cannot open {entry!r}: {exc}") from None
            try:
                fst = os.fstat(sub)
                if (fst.st_dev, fst.st_ino) != (st.st_dev, st.st_ino):
                    raise WorldRefusal(f"{entry!r} changed during the walk; refusing")
                count += _walk(sub, dev, depth + 1, delete, rel + entry + "/")
            finally:
                os.close(sub)
            if delete:
                os.rmdir(entry, dir_fd=dir_fd)
        else:
            raise WorldRefusal(
                f"unexpected special file {rel + entry!r} in the world; "
                f"remove {rel + entry!r} manually, then retry"
            )
    return count


class PartialDelete(Exception):
    """Deletion failed after it started: the world may be partially deleted (exit 1)."""


def _strict_rmtree(root: str, name: str, expected, fd: Optional[int] = None) -> int:
    """Delete exactly the world dir ``root/name``; return the entry count.

    Why not shutil.rmtree: this verifies containment itself.  The dir is
    opened O_NOFOLLOW (or the caller's already-validated ``fd`` is used) and
    must have the ``expected`` (st_dev, st_ino) and still be what ``name``
    points at in the root.  A full no-delete pre-scan runs first (special
    files, nesting, cross-mount and open errors refuse BEFORE anything is
    removed); the delete pass works through dir fds, unlinking symlinks as
    links.  The final rmdir is relative to the root fd after re-checking the
    name still binds to the same inode.  A failure once deletion has started
    raises PartialDelete.
    """
    root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    own = fd is None
    try:
        if own:
            try:
                fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd)
            except OSError as exc:
                raise WorldRefusal(f"cannot open world dir {name!r}: {exc}") from None
        try:
            def bound() -> bool:
                try:
                    cur = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
                except OSError:
                    return False
                return (cur.st_dev, cur.st_ino) == tuple(expected)

            fst = os.fstat(fd)
            if (fst.st_dev, fst.st_ino) != tuple(expected) or not bound():
                raise WorldRefusal(f"{name!r} is not the directory that was validated; refusing")
            try:
                _walk(fd, fst.st_dev, 1, delete=False)
            except OSError as exc:
                raise WorldRefusal(f"pre-scan failed: {exc}") from None
            try:
                count = _walk(fd, fst.st_dev, 1, delete=True)
                if not bound():
                    raise WorldRefusal(f"{name!r} no longer binds to the deleted directory")
                os.rmdir(name, dir_fd=root_fd)
            except Exception as exc:
                raise PartialDelete(
                    f"PARTIALLY DELETED: {name!r} ({type(exc).__name__}: {exc})"
                ) from exc
        finally:
            if own:
                os.close(fd)
    finally:
        os.close(root_fd)
    return count


# ---------------------------------------------------------------- commands

def _seed_empty(db: str) -> None:
    """Create the schema-only DB via the guarded DatabaseManager constructor."""
    m = DatabaseManager(db, init_schema=True)
    m.close()


def cmd_create(name: str) -> dict:
    """Create an empty world; on any failure after mkdir remove only that dir."""
    validate_name(name)
    root = _ensure_root(worlds_root())
    with _create_lock(root):
        p = _paths(root, name)
        try:
            os.lstat(p["dir"])
            raise WorldRefusal(f"world {name!r} already exists")
        except FileNotFoundError:
            pass
        if os.path.dirname(os.path.realpath(p["dir"])) != root:
            raise WorldRefusal("world dir does not resolve to a direct child of the root")
        for key in ("state", "db", "docs", "audit"):
            rp = os.path.realpath(p[key])
            if not _within(rp, p["dir"]) or rp == p["dir"]:
                raise WorldRefusal(f"{key} path escapes the world dir")
        # Overlap with the live dir is already impossible here: assert_root_safe
        # (in _ensure_root) refuses a root inside or containing the live dir.
        if guard.is_live_path_strict(p["db"]):
            raise WorldRefusal("world DB path classifies as the live store")
        port = allocate_port(root)
        os.mkdir(p["dir"], 0o700)
        os.chmod(p["dir"], 0o700)
        wst = os.lstat(p["dir"])
        try:
            for key in ("state", "docs"):
                os.mkdir(p[key], 0o700)
                os.chmod(p[key], 0o700)
            _seed_empty(p["db"])
            os.chmod(p["db"], 0o600)
            man = {
                "schema": 1,
                "name": name,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "port": port,
                "source": "empty",
                "created_by": "tools.world",
                "root": root,
                "dev": wst.st_dev,
                "ino": wst.st_ino,
            }
            tmp = os.path.join(p["dir"], ".world.json.tmp")
            _write_new(tmp, json.dumps(man, indent=2).encode())
            os.replace(tmp, p["manifest"])
        except BaseException:
            _strict_rmtree(root, name, (wst.st_dev, wst.st_ino))  # rollback: only the half-made world dir
            raise
    return {"dir": p["dir"], "port": port, "name": name}


def cmd_list() -> List[dict]:
    """Read-only listing; never opens any restoricon.db."""
    root = _open_root()
    out = []
    for n in sorted(os.listdir(root)):
        if NAME_RE.fullmatch(n) is None:
            continue
        wd = os.path.join(root, n)
        try:
            if not stat.S_ISDIR(os.lstat(wd).st_mode):
                continue
        except OSError:
            continue
        try:
            man = _load_manifest(root, n)
            out.append({"name": n, "port": man["port"], "created_at": man.get("created_at"),
                        "source": man.get("source"), "state": "ok"})
        except (WorldRefusal, OSError):
            out.append({"name": n, "port": None, "created_at": None,
                        "source": None, "state": "broken"})
    return out


def cmd_env(name: str) -> List[str]:
    """Return ``export`` lines for the world.

    Why stdout only: the caller evals them into its own shell; this function
    never execs, spawns or mutates the environment, prints no token and never
    a production grant.  RESTORICON_WORLD_NAME is informational: nothing may
    read it as authorization.
    """
    root = _open_root()
    man = _load_manifest(root, name)
    p = _paths(root, name)
    if guard.is_live_path_strict(p["db"]):
        raise WorldRefusal("world DB path classifies as the live store")
    env = [
        ("CODEY_STATE_DIR", p["state"]),
        ("RESTORICON_DB_PATH", p["db"]),
        ("RESTORICON_DOC_STORE_PATH", p["docs"]),
        ("CODEY_ACTION_GATEWAY_AUDIT", p["audit"]),
        ("RESTORICON_API_HOST", "127.0.0.1"),
        ("RESTORICON_API_PORT", str(man["port"])),
        ("RESTORICON_WORLD_NAME", name),
    ]
    return [f"# tools.world env {name}"] + [f"export {k}={shlex.quote(v)}" for k, v in env]


def _in_use(world_fd: int, port: int) -> Optional[str]:
    """Kill-free in-use check: returns a reason string or None.

    Why: a running world must be stopped through its normal PID-tracked stop
    (rule 3), never by this tool.  Only ``os.kill(pid, 0)`` (existence probe,
    no signal delivered) on a sane pid (1..2**22; 0/negatives would address a
    process group) and a loopback TCP connect are used.  Pid files are read
    relative to the validated world fd without blocking on a FIFO.
    """
    try:
        sfd = os.open("state", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=world_fd)
    except OSError:
        sfd = None  # no readable state dir: no pid files to consult
    if sfd is not None:
        try:
            entries = os.listdir(sfd)
            for e in entries:
                if not e.endswith(".pid"):
                    continue
                try:
                    pid = int(_read_text_nofollow(e, sfd).strip())
                except (OSError, ValueError):
                    continue  # unreadable/garbage/non-regular pid file names no process
                if not 1 <= pid <= 2 ** 22:
                    continue
                try:
                    os.kill(pid, 0)
                except (ProcessLookupError, OverflowError):
                    continue
                except PermissionError:
                    return f"pid {pid} from {e} is alive"
                return f"pid {pid} from {e} is alive"
        finally:
            os.close(sfd)
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.2)
    try:
        if s.connect_ex(("127.0.0.1", port)) == 0:
            return f"something is listening on 127.0.0.1:{port}"
    except OSError:
        pass  # connect failure means nothing is listening
    finally:
        s.close()
    return None


def _read_text_nofollow(path: str, dir_fd: Optional[int] = None) -> str:
    fd = _open_reg(path, dir_fd)
    try:
        return os.read(fd, 64).decode("ascii")
    finally:
        os.close(fd)


def cmd_destroy(name: str, yes: bool) -> dict:
    """Validate everything on one opened fd, then delete exactly that world dir.

    Why: the world dir is opened once; the manifest, in-use check and
    deletion all use that fd, and the root-relative name is re-checked to
    still bind to the same inode right before deleting and before the final
    rmdir, so a swap after validation cannot redirect the delete.
    """
    validate_name(name)
    root = _open_root()
    fd, man = _open_world(root, name)
    try:
        st = os.fstat(fd)
        ident = (st.st_dev, st.st_ino)
        p = _paths(root, name)
        if guard.is_live_path(p["dir"]) or guard.is_live_path(p["db"]):
            raise WorldRefusal("target classifies as the live store")
        reason = _in_use(fd, man["port"])
        if reason:
            raise WorldRefusal(
                f"world {name!r} appears in use ({reason}); stop its services with the "
                "normal PID-tracked stop first"
            )
        if not yes:
            try:
                n = _walk(fd, st.st_dev, 1, delete=False)
            except OSError as exc:
                raise WorldRefusal(f"pre-scan failed: {exc}") from None
            return {"deleted": False, "dir": p["dir"], "entries": n, "port": man["port"]}
        n = _strict_rmtree(root, name, ident, fd=fd)
    finally:
        os.close(fd)
    return {"deleted": True, "dir": p["dir"], "entries": n, "port": man["port"]}


# --------------------------------------------------------------------- CLI

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m tools.world", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("create").add_argument("name")
    ls = sub.add_parser("list")
    ls.add_argument("--json", action="store_true")
    sub.add_parser("env").add_argument("name")
    d = sub.add_parser("destroy")
    d.add_argument("name")
    d.add_argument("--yes", action="store_true")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "create":
            r = cmd_create(args.name)
            print(f"created world {r['name']}: {r['dir']} (port {r['port']})")
            print(f'activate with: eval "$(python3 -m tools.world env {r["name"]})"')
        elif args.cmd == "list":
            rows = cmd_list()
            if args.json:
                print(json.dumps(rows))
            else:
                for r in rows:
                    print(f"{r['name']}\t{r['port']}\t{r['created_at']}\t{r['source']}\tstate: {r['state']}")
        elif args.cmd == "env":
            print("\n".join(cmd_env(args.name)))
        else:
            r = cmd_destroy(args.name, args.yes)
            if r["deleted"]:
                print(f"destroyed world {args.name}: {r['dir']} ({r['entries']} entries)")
            else:
                print(
                    f"would delete {r['dir']} ({r['entries']} entries, port {r['port']}); "
                    "re-run with --yes to proceed",
                    file=sys.stderr,
                )
                return 2
        return 0
    except PartialDelete as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except (WorldRefusal, guard.WorldConfigError, guard.LiveStoreRefused) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # unexpected: report once, exit 1 (no retry, no cleanup beyond create's rollback)
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
