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

Not yet wired into ``database.py``, the server or any CLI (slices S2/S3).
"""

from __future__ import annotations

import json
import os
import pwd
import sys
from urllib.parse import unquote
from typing import Optional, Set

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


def is_live_path(p) -> bool:
    """True if ``p`` resolves to a live DB (or its -wal/-shm/-journal).

    Handles symlinks (realpath), sqlite sidecar suffixes, and hardlinks
    (samefile).  ``:memory:`` is never live.  Any error returns True.
    """
    try:
        raw = os.fspath(p)
        if isinstance(raw, bytes):
            raw = os.fsdecode(raw)
        if raw == ":memory:":
            return False
        if not raw:
            return True  # empty path is a misconfiguration: fail closed
        if raw[:5].lower() == "file:":
            raw = _file_uri_to_path("file:" + raw[5:])  # ValueError -> live
            if raw is None:
                return False

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
    except Exception:  # fail closed: if we cannot tell, treat as live
        return True


def resolve_db_path(explicit=None) -> str:
    """Explicit arg, else ``RESTORICON_DB_PATH``; never a default.

    Only str/os.PathLike-of-str are accepted (bytes are rejected).
    """
    if explicit is not None:
        if isinstance(explicit, bytes):
            raise WorldConfigError("database path must be str, not bytes")
        explicit = os.fspath(explicit)
        if not isinstance(explicit, str):
            raise WorldConfigError("database path must be str")
        if explicit != "":
            return explicit
    env = os.environ.get("RESTORICON_DB_PATH")
    if env:
        return env
    raise WorldConfigError(
        "no database configured; set RESTORICON_DB_PATH to a world copy"
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
        print(
            f"[restoricon world] PRODUCTION open of live store: {path}",
            file=sys.stderr,
        )
