"""Invoke Git from an explicitly trusted OS/Python installation location.

Selection is performed at invocation time, never from PATH, cwd, repository,
or environment overrides. Trust is in the installation location, not a digest,
immutability, or protection against concurrent executable replacement. Git's
secondary configuration, hooks, helpers, and inherited environment remain
unbounded here; caller classifications and execution contracts are unchanged.
"""

import os
import subprocess
import sys
from pathlib import Path


def _git_candidates():
    """Ordered installation locations, with lexical duplicates removed."""
    return tuple(dict.fromkeys((Path(sys.base_prefix) / "bin/git", Path("/usr/bin/git"), Path("/bin/git"))))


def _trusted_git_executable():
    for candidate in _git_candidates():
        if not candidate.is_absolute():
            raise PermissionError("Git installation candidate must be absolute")
        try:
            candidate.lstat()
        except FileNotFoundError:
            continue
        # An existing unusable preferred entry (including a broken symlink)
        # must fail explicitly rather than silently choosing another binary.
        if not candidate.is_file() or not os.access(candidate, os.X_OK):
            raise PermissionError("Git installation candidate is not an executable regular file")
        return str(candidate)
    raise FileNotFoundError("Git is missing from trusted installation locations")


def run_git(argv, **kwargs):
    """Replace the legacy 'git' prefix, preserving operands/kwargs and errors.

    The input vector is not modified. No Git policy, config sanitization, or
    new audit is introduced; callers own mediation before mutation execution.
    """
    if not isinstance(argv, (list, tuple)) or not argv or argv[0] != "git":
        raise ValueError("Git argv must begin with the literal 'git' executable")
    executable = _trusted_git_executable()
    # Preserve the caller's check argument (including its absence) verbatim.
    return subprocess.run([executable, *argv[1:]], **kwargs)  # noqa: PLW1510
