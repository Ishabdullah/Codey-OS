"""Invoke Git from an explicitly trusted OS/Python installation location.

Selection is performed at invocation time, never from PATH, cwd, repository,
or environment overrides. Trust is in the installation location, not a digest,
immutability, or protection against concurrent executable replacement. Git's
secondary configuration, hooks, helpers, and inherited environment remain
unbounded for general run_git. The local-commit profile below limits ambient
environment only; repository/global configuration and helpers remain unbounded.
"""

import os
import re
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


_SHELL_GIT_FORCED_OVERRIDES = {
    "core.hookspath": "/dev/null",
    "core.fsmonitor": "false",
    "commit.gpgsign": "false",
    "tag.gpgsign": "false",
    "push.gpgSign": "false",
    "submodule.recurse": "false",
    "gc.auto": "0",
    "maintenance.auto": "false",
}


def shell_git_environment():
    """Snapshot one environment for a generic shell-tool git invocation.

    Unlike push_environment(), whose base is _local_commit_environment()'s
    narrow allowlist, this starts from the full ambient os.environ --
    tools/shell_tools.py's _run_shell_command_structured() runs arbitrary
    non-git commands with no env= override at all, and must not change that for
    anything except the structural keys below.

    Any ambient GIT_CONFIG_COUNT/GIT_CONFIG_KEY_<n>/GIT_CONFIG_VALUE_<n>/
    GIT_CONFIG_PARAMETERS is removed before adding ours. This base is
    untrusted ambient process environment, not a controlled allowlist like
    push_environment()'s -- leaving a pre-existing block in place would
    either let it survive underneath ours at a lower, harmless index, or
    (worse) depend on index arithmetic staying correct if this function is
    changed later. Removing it outright keeps the index trivial to audit.

    Covers (planted in repo-local, global, or system Git config): hook
    execution via core.hookspath; fsmonitor hook execution via
    core.fsmonitor; GPG-signing subprocess invocation for commit/tag/push
    via gpg.program (commit.gpgsign/tag.gpgsign/push.gpgSign); submodule
    recursion into an unmediated child Git process via submodule.recurse;
    background gc/maintenance subprocess spawning via gc.auto/
    maintenance.auto.

    Named residual, NOT covered, by design (Option B is a generic env
    layer, not an operation-specific router -- see NEW_ISSUES.md NEW-893):
      - `git -c core.hooksPath=<path>` or `--config-env=...` on the
        command line take precedence over GIT_CONFIG_COUNT/KEY/VALUE and
        defeat this entirely. Verified experimentally against the real
        git binary (2026-10-13, disposable repo): with this function's
        exact override set forced via env and a repository-local
        core.hooksPath pointing at a hook that writes a marker file --
        (a) no override: hook fires; (b) env override only: hook does
        NOT fire; (c) env override plus `git -c core.hooksPath=<real
        hooks dir>`: hook fires again, identically to (a). Mitigated
        only by classify_shell_command() already requiring human
        confirmation on every direct git invocation -- the residual risk
        is a human approving a command whose -c/--config-env clause they
        didn't notice, not silent unconfirmed execution.
      - credential.helper (arbitrary `!command`), core.sshCommand,
        core.editor, diff.external/textconv filter-driver programs, and
        `!`-prefixed aliases remain live if planted in repo-local or
        global config -- none of these are forced here.
      - Ambient GIT_EXEC_PATH/GIT_SSH_COMMAND/GIT_ASKPASS pass through
        unchanged by design (this is a generic shell tool; stripping a
        user's own legitimate SSH/exec configuration would be an
        unrequested behavior change for ordinary git usage).
      - A git invocation reached indirectly through `env git ...`,
        `xargs ... git ...`, or `find ... -exec git ...` is still
        classified HIGH_IMPACT by classify_shell_command() (env/find/
        xargs are each forced HIGH_IMPACT directly) and so still
        requires human confirmation, but the inner git process it
        eventually spawns is not the direct argv[0] `_run_shell_command_
        structured()` inspects, so it still runs under full ambient env
        once approved -- see NEW_ISSUES.md NEW-875.
      - A `timeout 5 git push`-style wrapper was this paragraph's
        previously-documented gap (`timeout` not forced HIGH_IMPACT,
        running fully ambient and unconfirmed under confirm_shell=False)
        -- NEW-875's WP2.1 group 1 closeout (2026-10-14) fixed this:
        `timeout` is now in `_EXEC_WRAPPER_BASENAMES`, so
        `classify_shell_command("timeout 5 git push")` returns
        `"HIGH_IMPACT"` (verified directly against current code), and
        `_run_shell_command_structured()`'s `_argv_token_hits_git()` scan
        applies env isolation to the wrapped git invocation once
        approved. The general class this paragraph warns about (an
        exec-wrapper basename not yet added to the set) remains open for
        any basename not yet enumerated -- see NEW-904.
      - An explicit `-S`/`--gpg-sign` on the command line (e.g. `git
        commit -S -m msg`) bypasses commit.gpgsign entirely regardless
        of this function's commit.gpgsign=false override -- Git's own
        documentation says `-S` "countermand[s] both the commit.gpgSign
        configuration variable, and earlier --gpg-sign", i.e. it does
        not consult the config variable at all when passed explicitly.
        Verified experimentally (2026-10-13, disposable repo): with
        this function's exact override set forced via env and
        gpg.program pointed at a script that writes a marker file,
        `git commit -S -m x` still invokes the fake gpg and the marker
        fires -- identically to the fully-ambient case. tag.gpgsign and
        push.gpgSign are not independently re-verified here for the
        same explicit-flag bypass (`git tag -s`, `git push --signed`),
        but the same Git precedent (an explicit per-invocation flag
        overriding a config default) makes the same gap plausible for
        both; treat this residual as applying to all three until each
        is checked.

    Deliberately excludes diff.ignoresubmodules/status.submodulesummary/
    rerere.enabled (present in git_mutation_context.py::_FORCED_OVERRIDES
    for mutation operations): those three change what `git status`/`git
    diff`/a merge *reports*, they do not spawn a subprocess, and this
    function must not silently change the output of a plain `git status`
    or `git diff` the agent runs through the shell tool to read real
    repository state. Also excludes GIT_NO_LAZY_FETCH (push_environment()
    only, prevents lazy-fetch during transmission; would break a
    partial-clone `checkout`/`log -p` here, where lazy fetch may be
    required for correct results).
    """
    environment = os.environ.copy()
    environment.pop("GIT_CONFIG_PARAMETERS", None)
    for name in list(environment):
        if name == "GIT_CONFIG_COUNT" or re.fullmatch(r"GIT_CONFIG_(KEY|VALUE)_\d+", name):
            del environment[name]
    environment["GIT_CONFIG_COUNT"] = str(len(_SHELL_GIT_FORCED_OVERRIDES))
    for index, (key, value) in enumerate(_SHELL_GIT_FORCED_OVERRIDES.items()):
        environment[f"GIT_CONFIG_KEY_{index}"] = key
        environment[f"GIT_CONFIG_VALUE_{index}"] = value
    return environment
