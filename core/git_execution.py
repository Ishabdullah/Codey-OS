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


_PUSH_FORCED_OVERRIDES = {
    "core.hookspath": "/dev/null",
    "push.gpgSign": "false",
    "submodule.recurse": "false",
    "gc.auto": "0",
    "maintenance.auto": "false",
}


def push_environment():
    """Snapshot one child environment for a single `git push` invocation.

    Base allowlist is identical to _local_commit_environment() (HOME and
    XDG_CONFIG_HOME are forwarded so the gh credential helper and global
    identity/config still resolve; everything else ambient is stripped).
    On top of that, the structural keys above are forced via the same
    highest-precedence GIT_CONFIG_COUNT/GIT_CONFIG_KEY_<n>/
    GIT_CONFIG_VALUE_<n> mechanism core/git_mutation_context.py uses,
    verified experimentally against the real git binary (2026-10-13,
    disposable repos): core.hookspath=/dev/null neutralizes `pre-push` and
    `reference-transaction` hooks with no filesystem resource to create or
    clean up (deliberately not the temp-hooks-dir pattern used elsewhere in
    this project -- a real character device needs no mkdtemp/rmtree and
    therefore cannot leak a cleanup-failure-after-success bug); push.gpgSign
    neutralizes signed-push GPG invocation even when repository-local
    config sets gpg.program/user.signingkey/push.gpgSign=true; submodule.
    recurse neutralizes push.recurseSubmodules=on-demand, which would
    otherwise run an unmediated git process against each submodule's own,
    unmediated hooks/config. gc.auto/maintenance.auto are carried over from
    core/git_mutation_context.py's established ref-mutation precedent, not
    independently re-verified here. This function has no side effects and
    is safe to call once per push attempt.

    Deliberately NOT reused from core/git_mutation_context.py: that
    module's preflight() (split/sparse index), linked-worktree rejection,
    and active-sequencer-state rejection are either meaningless for push
    (it never reads the index or working tree) or a real, unrequested
    behavior change (refusing to push already-committed refs because an
    unrelated local rebase is in progress) -- see NEW_ISSUES.md.
    """
    environment = dict(_local_commit_environment())
    # Stops pack-objects on a partial clone's remote from spawning a lazy
    # fetch during this push (GIT_ATTR_NOSYSTEM is redundant here -- the
    # base environment already sets GIT_CONFIG_NOSYSTEM -- and is omitted).
    environment["GIT_NO_LAZY_FETCH"] = "1"
    environment["GIT_CONFIG_COUNT"] = str(len(_PUSH_FORCED_OVERRIDES))
    for index, (key, value) in enumerate(_PUSH_FORCED_OVERRIDES.items()):
        environment[f"GIT_CONFIG_KEY_{index}"] = key
        environment[f"GIT_CONFIG_VALUE_{index}"] = value
    return environment
