"""World / live-store guard primitives for the Restoricon database (WP2.2 S1).

This module is a seatbelt, not a boundary.  It stops mistakes and agent
misuse through supported code paths from opening the live Restoricon store
(``<home>/.codeyOS/restoricon.db``).  It does NOT stop a hostile process that
can edit source or exec arbitrary code; NEW-1069 (an OS-level boundary) is the
real boundary and remains a separate candidate.

Why it exists: ``DatabaseManager`` historically fell back to the live path,
so any test/tool/CLI that forgot a path opened real business data.

Constraints: stdlib only.  It must NOT import ``utils.config`` or ``core.*``
(those create import-time state).  "Live" is derived from the passwd home, not
``$HOME``, so a monkeypatched/disposable HOME cannot rebase what counts as
live.  Every resolution error fails closed (treated as live).

Wired into the launcher (S2/S3a); database.py/server/CLI enforcement is S3b.
"""

from __future__ import annotations

import json
import os
import pwd
import sys
from urllib.parse import unquote
from typing import Set

_SQLITE_SUFFIXES = ("-wal", "-shm", "-journal")


class WorldConfigError(RuntimeError):
    """No usable database/world configuration could be determined."""


class LiveStoreRefused(PermissionError):
    """A non-production caller tried to open the live Restoricon store."""


def _passwd_home() -> str:
    """Home dir from the passwd database (not $HOME); fail closed on error."""
    try:
        home = pwd.getpwuid(os.getuid()).pw_dir
    except Exception as exc:  # KeyError/OSError: cannot know where live is
        raise WorldConfigError(f"cannot determine passwd home: {exc}") from exc
    if not home or not os.path.isabs(home):
        raise WorldConfigError(f"passwd home is not an absolute path: {home!r}")
    return home


_MAX_CONFIG_BYTES = 1024 * 1024


def _declared_db_paths(home: str) -> Set[str]:
    """Candidate paths for ``restoricon.db_path`` in <home>/.codeyOS/config.json.

    Fails closed: only a missing config.json yields an empty set.  Any other
    read/parse/shape problem (unreadable, oversize, bad JSON, non-dict
    structure, non-string db_path, unresolvable ~user) raises WorldConfigError
    so is_live_path() reports True rather than silently dropping a declared
    live path.  A null/empty db_path means "unset" (same as utils.config).

    Production (utils/config.py get_restoricon_api_config) resolves it with
    Path(os.path.expanduser(raw)).resolve(): relative = CWD, ~ = $HOME.  The
    guard returns every plausible interpretation (CWD-relative and
    .codeyOS-relative; $HOME and passwd-home for ~) so it errs toward live.
    """
    cfg_path = os.path.join(home, ".codeyOS", "config.json")
    try:
        with open(cfg_path, "rb") as fh:
            blob = fh.read(_MAX_CONFIG_BYTES + 1)
    except FileNotFoundError:
        return set()
    except Exception as exc:
        raise WorldConfigError(f"cannot read {cfg_path}: {exc}") from exc
    if len(blob) > _MAX_CONFIG_BYTES:
        raise WorldConfigError(f"{cfg_path} exceeds {_MAX_CONFIG_BYTES} bytes")
    try:
        data = json.loads(blob.decode("utf-8"))
    except Exception as exc:
        raise WorldConfigError(f"cannot parse {cfg_path}: {exc}") from exc
    if not isinstance(data, dict):
        raise WorldConfigError(f"{cfg_path}: top level is not an object")
    if "restoricon" not in data or data["restoricon"] is None:
        return set()
    section = data["restoricon"]
    if not isinstance(section, dict):
        raise WorldConfigError(f"{cfg_path}: 'restoricon' is not an object")
    raw = section.get("db_path")
    if raw is None or raw == "":
        return set()
    if not isinstance(raw, str):
        raise WorldConfigError(f"{cfg_path}: restoricon.db_path is not a string")

    out: Set[str] = set()
    if raw == "~" or raw.startswith("~/"):
        out.add(os.path.normpath(os.path.expanduser(raw)))  # $HOME
        out.add(os.path.normpath(os.path.join(home, raw[2:])))  # passwd home
    elif raw.startswith("~"):
        expanded = os.path.expanduser(raw)
        if expanded == raw:
            raise WorldConfigError(f"cannot resolve {raw!r} (~user) in {cfg_path}")
        out.add(os.path.normpath(expanded))
    elif os.path.isabs(raw):
        out.add(os.path.normpath(raw))
    else:
        out.add(os.path.abspath(raw))  # production: relative to CWD
        out.add(os.path.normpath(os.path.join(home, ".codeyOS", raw)))
    return out


def live_db_paths() -> Set[str]:
    """Return the set of paths that count as the live Restoricon DB."""
    home = _passwd_home()
    paths = {os.path.join(home, ".codeyOS", "restoricon.db")}
    paths |= _declared_db_paths(home)
    return paths


def _strip_suffix(p: str) -> str:
    """Strip all stacked -wal/-shm/-journal suffixes (over-blocks, never under)."""
    changed = True
    while changed:
        changed = False
        for suffix in _SQLITE_SUFFIXES:
            if p.endswith(suffix) and len(p) > len(suffix):
                p = p[: -len(suffix)]
                changed = True
    return p


def _file_uri_to_path(raw: str):
    """Map a sqlite ``file:`` URI to a filesystem path; None means in-memory.

    Strips scheme, authority (only empty/localhost allowed), query and
    fragment, and percent-decodes.  Raises ValueError if it cannot (caller
    fails closed).
    """
    rest = raw[len("file:"):]
    for sep in ("?", "#"):
        rest = rest.split(sep, 1)[0]
    if rest.startswith("//"):
        auth, slash, tail = rest[2:].partition("/")
        if auth not in ("", "localhost"):
            raise ValueError("unsupported file: URI authority")
        rest = slash + tail
    path = unquote(rest)
    if path == ":memory:":
        return None
    if not path:
        raise ValueError("empty file: URI path")
    return path


def _classify_live(p) -> bool:
    """Classify ``p`` as live (True) / not live (False); raises on any doubt.

    Body of the classifier shared by is_live_path (which turns every error
    into True) and is_live_path_strict (which turns every error into
    WorldConfigError).  Handles symlinks (realpath), sqlite sidecar suffixes,
    and hardlinks (samefile).  ``:memory:`` is never live.
    """
    raw = os.fspath(p)
    if isinstance(raw, bytes):
        raw = os.fsdecode(raw)
    if raw == ":memory:":
        return False
    if not raw:
        raise ValueError("empty database path")
    if "\x00" in raw:
        raise ValueError("embedded null character in path")
    if raw[:5].lower() == "file:":
        raw = _file_uri_to_path("file:" + raw[5:])  # ValueError propagates
        if raw is None:
            return False
        if "\x00" in raw:
            raise ValueError("embedded null character in path")

    live_real = set()
    live_existing = []
    for lp in live_db_paths():
        for variant in (lp,) + tuple(lp + s for s in _SQLITE_SUFFIXES):
            live_real.add(os.path.realpath(variant))
            if os.path.exists(variant):
                live_existing.append(variant)

    real = os.path.realpath(raw)
    candidates = {
        real,
        _strip_suffix(real),
        os.path.realpath(_strip_suffix(raw)),
    }
    if candidates & live_real:
        return True
    if os.path.exists(real):
        for lp in live_existing:
            if os.path.samefile(real, lp):
                return True
    return False


def is_live_path(p) -> bool:
    """True if ``p`` resolves to a live DB (or its -wal/-shm/-journal).

    ``:memory:`` is never live.  Any error returns True (fail closed): use
    this for refusals.  Never use it to GRANT authorization; use
    is_live_path_strict, which raises instead of answering True on doubt.
    """
    try:
        return _classify_live(p)
    except Exception:  # fail closed: if we cannot tell, treat as live
        return True


def is_live_path_strict(p) -> bool:
    """Positive classification: True only on a positive live match.

    False only on a positive non-match (or ``:memory:``).  Any inability to
    classify (NUL byte, empty path, OS error, unreadable/garbage
    ~/.codeyOS/config.json) raises WorldConfigError instead of guessing, so a
    caller that GRANTS something on True (the launcher's --world production)
    cannot be granted by an error.  An existing WorldConfigError is re-raised
    unchanged so its message (e.g. "cannot parse .../config.json") reaches
    the operator.
    """
    try:
        return _classify_live(p)
    except WorldConfigError:
        raise
    except Exception as exc:
        raise WorldConfigError(
            f"cannot classify database path as live or not: {exc}"
        ) from exc


def resolve_db_path(explicit=None) -> str:
    """Explicit arg, else ``RESTORICON_DB_PATH``; never a default.

    Only str/os.PathLike-of-str are accepted (bytes and non-path objects are
    rejected with WorldConfigError).  ``"."`` (what ``Path("")`` becomes) and
    any value with a NUL byte are rejected for both the explicit argument and
    the env value; an explicit ``""`` still means "unset" and falls through
    to the env.
    """
    def _check(value: str, what: str) -> str:
        if "\x00" in value:
            raise WorldConfigError(f"{what} contains a NUL byte")
        if value == ".":
            raise WorldConfigError(
                f"{what} '.' (or Path('')) is not a database file"
            )
        return value

    if explicit is not None:
        if isinstance(explicit, bytes):
            raise WorldConfigError("database path must be str, not bytes")
        try:
            explicit = os.fspath(explicit)
        except TypeError as exc:
            raise WorldConfigError("database path must be str or a path") from exc
        if not isinstance(explicit, str):
            raise WorldConfigError("database path must be str")
        _check(explicit, "database path")
        if explicit != "":
            return explicit
    env = os.environ.get("RESTORICON_DB_PATH")
    if env:
        return _check(env, "RESTORICON_DB_PATH")
    raise WorldConfigError(
        "no database configured; set RESTORICON_DB_PATH to a world copy"
    )


def _announce_production(path) -> None:
    """The single stderr audit line for a production open of the live store."""
    print(
        f"[restoricon world] PRODUCTION open of live store: {path}",
        file=sys.stderr,
    )


def assert_world_allows(path, *, production: bool = False) -> None:
    """Raise LiveStoreRefused if ``path`` is live and not production-authorized.

    An empty/None path is refused even with production=True (never logged as
    a production open).  A production-authorized live open writes a visible
    line to stderr.
    """
    if path is None or path == "" or path == b"":
        raise LiveStoreRefused("refusing empty database path")
    if is_live_path(path):
        if not production:
            raise LiveStoreRefused(
                f"refusing to open live Restoricon store {path!r} "
                "without production authorization"
            )
        _announce_production(path)


def guard_db_open(db_path=None, *, production: bool = False, announce: bool = True) -> str:
    """Pre-open guard: return the exact string to hand to sqlite3.connect.

    Resolves explicit -> env -> error, rejects ``file:`` URIs, classifies the
    path with the strict classifier and refuses a live path unless
    ``production``.  An unclassifiable path raises WorldConfigError with its
    own message (never converted to LiveStoreRefused, and ``production=True``
    does not override it).  The returned realpath is the string that was
    classified, so check and open cannot diverge.  ``production=True`` on a
    positively non-live path is allowed silently.
    """
    raw = resolve_db_path(db_path)
    if raw == ":memory:":
        return ":memory:"
    if raw[:5].lower() == "file:":
        raise WorldConfigError(
            "file: URIs are not accepted as a database path; pass a filesystem path"
        )
    # realpath is computed exactly ONCE; that string is classified (sidecar
    # variants are derived from it inside the classifier), announced and
    # returned, so the checked string is the string that gets connected.
    try:
        real = os.path.realpath(raw)
    except Exception as exc:
        raise WorldConfigError(
            f"cannot classify database path as live or not: {exc}"
        ) from exc
    live = is_live_path_strict(real)  # WorldConfigError propagates unchanged
    if live and not production:
        raise LiveStoreRefused(
            f"refusing to open live Restoricon store {real!r} "
            "without production authorization (pass --world production)"
        )
    if live and announce:
        _announce_production(real)
    return real


def snapshot_fd_inodes() -> dict:
    """Map fd -> (st_dev, st_ino) for this process's open descriptors.

    Entries whose fstat fails (the listdir's own transient fd) are skipped.
    Fails closed with WorldConfigError if /proc/self/fd cannot be listed.
    """
    try:
        entries = os.listdir("/proc/self/fd")
    except OSError as exc:
        raise WorldConfigError(
            "cannot verify the opened database file: /proc/self/fd unreadable"
        ) from exc
    out = {}
    for entry in entries:
        try:
            fd = int(entry)
            st = os.fstat(fd)
        except (ValueError, OSError):
            continue
        out[fd] = (st.st_dev, st.st_ino)
    return out


def assert_opened_not_live(before: dict, after: dict, *, production: bool = False) -> None:
    """Post-open TOCTOU check: refuse if a newly opened fd is the live store.

    Compares fd snapshots taken around sqlite3.connect.  Any fd new in
    ``after`` (new number, or same number with a different dev/ino) whose
    (dev, ino) matches an existing live file (db/-wal/-shm/-journal, stat
    follows symlinks) raises LiveStoreRefused.  No-op when ``production``.
    Limits: this detects after open(2) but before any statement/PRAGMA, so no
    write or WAL switch has happened; it does not prevent the open itself
    (the pre-open guard does).  A legitimate production connection in another
    thread of the same process also looks like a new live fd (false refusal,
    the safe direction).  If the process already holds the live inode open,
    SQLite's unix VFS may reuse that fd and the diff misses a swap.  Hardlink
    detection (inode match) is by design but untested on Termux (no os.link).
    """
    if production:
        return
    live_inodes = set()
    for lp in live_db_paths():
        for variant in (lp,) + tuple(lp + s for s in _SQLITE_SUFFIXES):
            try:
                st = os.stat(variant)
            except FileNotFoundError:
                continue
            live_inodes.add((st.st_dev, st.st_ino))
    for fd, ident in after.items():
        if before.get(fd) != ident and ident in live_inodes:
            raise LiveStoreRefused(
                "post-open check: the opened file is the live Restoricon store"
            )
