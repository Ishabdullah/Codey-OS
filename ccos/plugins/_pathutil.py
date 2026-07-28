"""
ccos/plugins/_pathutil.py — shared repo-root resolution for plugins
that need to import from outside ccos/ (core/, tools/, utils/, pipeline/).

Use this instead of a relative .parent chain — ccos/core/ and the
top-level core/ share a package name, and a miscalculated relative
path can silently shadow the wrong one.
"""
import sys
from pathlib import Path


def ensure_repo_root_on_path() -> Path:
    """
    Walk upward from this file until a directory containing both
    'core' and 'ccos' as subdirectories is found (the actual repo
    root), and ensure it sits at sys.path[0] — removing any existing
    occurrence first so a shadowing path inserted ahead of it (e.g.
    by another module's own sys.path.insert(0, ...)) can't win.
    Returns the resolved repo root Path.
    """
    current = Path(__file__).resolve().parent
    for candidate in [current, *current.parents]:
        if (candidate / "core").is_dir() and (candidate / "ccos").is_dir():
            repo_root = str(candidate)
            while repo_root in sys.path:
                sys.path.remove(repo_root)
            sys.path.insert(0, repo_root)
            return candidate

    raise RuntimeError(
        "Could not locate repo root (a directory containing both "
        "'core' and 'ccos') by walking up from " + str(current)
    )
