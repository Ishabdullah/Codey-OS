"""Invoke Git from an explicitly trusted OS/Python installation location.

Selection is performed at invocation time, never from PATH, cwd, repository,
or environment overrides. Trust is in the installation location, not a digest,
immutability, or protection against concurrent executable replacement. Git's
secondary configuration, hooks, helpers, and inherited environment remain
unbounded for general run_git. The local-commit profile below limits ambient
environment only; repository/global configuration and helpers remain unbounded.
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


_LOCAL_COMMIT_AMBIENT = {
    "HOME", "XDG_CONFIG_HOME", "USER", "LOGNAME", "EMAIL", "TZ",
    "GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_AUTHOR_DATE",
    "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL", "GIT_COMMITTER_DATE",
}
_LOCAL_COMMIT_KWARGS = {"cwd", "capture_output", "text", "check", "timeout"}


def _local_commit_environment():
    """Allowlist ambient scalars; retain HOME/XDG and identity verbatim.

    System config and ambient execution/repository/config selectors are removed.
    Repository/global config, hooks, signing, and other helpers remain unbounded.
    No identity is invented and the parent environment is intact.
    """
    environment = {name: os.environ[name] for name in _LOCAL_COMMIT_AMBIENT if name in os.environ}
    parents = dict.fromkeys(
        str(candidate.parent) for candidate in _git_candidates()
        if candidate.is_absolute()
    )
    # Keep installation directories even when Git is absent: an empty PATH
    # would introduce current-directory lookup if an executable appeared later.
    if not parents:
        raise ValueError("No absolute Git installation directories available")
    environment.update(PATH=os.pathsep.join(parents), LC_ALL="C", GIT_CONFIG_NOSYSTEM="1")
    return environment


def local_commit_runner():
    """Snapshot one child environment for a local-commit operation sequence.

    Each invocation receives a fresh copy; caller kwargs cannot replace the
    environment, executable, or shell mode. The general run_git contract remains
    unchanged. This is ambient isolation, not a complete Git effects boundary.
    """
    environment = dict(_local_commit_environment())

    def run(argv, **kwargs):
        if not kwargs.keys() <= _LOCAL_COMMIT_KWARGS:
            raise ValueError("Unsupported local commit runner keyword arguments")
        return run_git(argv, env=dict(environment), **kwargs)

    return run
