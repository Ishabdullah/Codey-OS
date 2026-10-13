"""Isolated local Git ref mutations: branch create, checkout, merge.

Unlike core/git_commit_context.py, core/git_query_context.py, and
core/git_worktree_context.py (which all redirect GIT_DIR to a private admin
directory wired with symlinks or copies back to the real refs/objects/index),
this module leaves GIT_DIR pointing at the real `.git` directory and makes no
copy of refs, objects, index, or HEAD. A branch create, checkout, or merge
*is* the mutation of that real state -- there is nothing to compute privately
and publish afterward, unlike a commit's detached-HEAD value or a read-only
query's answer. This is therefore a genuinely different isolation mechanism
from every prior slice, not an application of the same one.

Isolation is provided by environment-injected configuration overrides
(`GIT_CONFIG_COUNT`/`GIT_CONFIG_KEY_<n>`/`GIT_CONFIG_VALUE_<n>`), which Git
documents as higher-precedence than `--file`, repository, global, or system
configuration. Verified experimentally against the real git binary in this
environment (2026-10-13, disposable repo): a repository-local
`core.hookspath` pointing at a hook that writes a marker file continues to be
neutralized by the env override even though the repository's own
`.git/config` sets a conflicting value, and restoring the repository-local
value and removing the override reproduces the firing hook again (control
case).

This inverts core/git_commit_context.py's "import positive configuration
data only" contract: repository, home, and global configuration all apply in
full here, except for the specific structural keys this module forcibly
overrides. Importing only positive data is meaningless when GIT_DIR is not
redirected -- Git reads the real repository/home/global configuration
regardless of any side config file's contents.

Deviation from the literal slice spec, logged here per rule 6 (correct the
record rather than leave a stronger claim standing): the spec asked for
`git_commit_context._DATA_KEYS` to be imported into a private config file for
non-fast-forward merge identity (item 5). That import turned out to be
unnecessary and was not built. `git_commit_context.py` needs it only because
*that* module explicitly devnulls `GIT_CONFIG_GLOBAL` (its own
`_isolated_commit_context`, to keep its fabricated admin GIT_DIR's config
surface positive-only) and therefore has to reconstruct identity by hand.
This module never touches `GIT_CONFIG_GLOBAL`/`GIT_CONFIG_SYSTEM` at all, and
`core/git_execution._local_commit_environment()` (reused here, as in every
other isolation module) already forwards `HOME`/`XDG_CONFIG_HOME` into the
child environment. Verified experimentally (2026-10-13, disposable repo): a
plain, non-fast-forward `git commit` with no `GIT_CONFIG_GLOBAL` override and
only `HOME`/`PATH`/`GIT_CONFIG_NOSYSTEM=1` in its environment picks up
`user.name`/`user.email` from `$HOME/.gitconfig` exactly as an unmediated
`git merge` would. `git_commit_context._ACTIVE` is still reused directly, per
the spec, for the active-sequencer-state check below.

Hook neutralization (named contract inversion): `core.hookspath` is forced
(via the env override above) to an empty directory. This disables
`pre-merge-commit`, `prepare-commit-msg`, `commit-msg`, and `post-merge`
hooks for `git_merge`, and `post-checkout` for `git_checkout`/
`git_branch_create` -- a real, commonly-relied-on veto/notification
mechanism, not an incidental side effect. Verified experimentally
(2026-10-13): a real `post-checkout` hook that writes a marker file fires on
an unmediated checkout and does not fire once the override is applied.

Filter-driver rejection (checkout risk): `git checkout` smudges working-tree
content through any `filter=<name>` attribute on a path whose content is
about to change. Verified experimentally which path set is actually smudged
(disposable repo, 2026-10-13, three `filter=foo`-attributed files): a path
whose content differs between the pre-checkout HEAD and the checkout target
was smudged; a path with the same attribute but unchanged content was left
untouched. This module therefore probes exactly
`git diff --name-only <current HEAD> <resolved target>` (the set that will
actually change) with `check-attr -z --stdin --all`, reusing
git_commit_context.py's "reject both explicit -filter and literal unset"
reasoning -- the two have identical protocol output here and cannot be told
apart -- and rejects if any probed path reports a `filter` attribute at all.
Also verified experimentally (disposable repo, 2026-10-13) that a real
checkout smudges content according to the *target* commit's
`.gitattributes`, even when that attribute is entirely absent from the
current HEAD's tree -- so this probe reads attributes with
`check-attr --source=<resolved target>`, not from the current worktree/index
(contrast the merge probe below, which deliberately does not). If the
checkout target does not resolve to a commit (unknown branch/ref), the probe
is skipped and the real `git checkout` command is left to produce its own
native error text; probing an unresolvable target would preempt that message
with a different one.

DWIM bypass (found by code-reviewer during this slice's review, fixed and
verified 2026-10-13): `resolve_target()`'s strict `rev-parse --verify
<name>^{commit}` probe and the real `git checkout <name> --` command used to
resolve names differently. A name with no local branch/ref but a same-named
remote-tracking branch (e.g. `origin/feature` with no local `feature`) is
unresolvable by the strict probe (`resolve_target()` returns `None`, so the
filter probe above never runs) but still succeeds via Git's branch-name DWIM,
which auto-creates a local tracking branch from the remote-tracking ref --
smudging content through a configured filter driver with no rejection check
having run. Verified experimentally (disposable repo: clone with
`origin/feature`, no local `feature`, `filter=foo`-attributed path with a
configured smudge driver): plain `git checkout feature --` switched via DWIM
and fired the driver; `git checkout --no-guess feature --` failed with
`fatal: invalid reference: feature`, the same resolution strict `rev-parse
--verify` reports. The real checkout call is therefore run with `--no-guess`
(verified not to disturb the `-` previous-branch case or a detached-HEAD
commit/SHA checkout), making the real command's resolution match
`resolve_target()`'s strict resolution exactly and closing the divergence.

The equivalent `git_merge` call was checked for the same divergence and found
not to have it: verified experimentally (disposable repo, same remote-
tracking/no-local-branch setup) that `git rev-parse --verify --quiet
<name>^{commit}` and `git merge -- <name>` resolve a bare remote-tracking
branch name identically -- both fail on an ambiguous/unknown name with no
DWIM auto-vivification step, because merge's operand is a commit-ish to
merge, not a branch to switch to or create. No `--no-guess`-equivalent change
was needed or made for `git_merge`.

Merge-driver rejection (merge risk; no existing precedent in this project): a
`merge=<name>` attribute can select a custom `merge.<name>.driver` run during
3-way conflict resolution. Verified experimentally which paths actually
invoke a configured driver (disposable repo, 2026-10-13, three
`merge=foo`-attributed paths: one changed on both sides of history since the
merge base, one changed only on the incoming side, one changed only
locally): the configured driver command ran exactly once, for the
changed-on-both-sides path; the other two were applied directly without
invoking it. `git diff --name-only <current HEAD> <resolved incoming>`
(computed before merging) is a safe conservative superset of that set,
confirmed in the same experiment -- it names all three paths, including the
two that in fact never invoke the driver. Mirroring the filter probe's
"can't safely distinguish configured-non-default from absent" posture, this
module rejects if ANY probed path reports a non-empty `merge` attribute, not
only a specific driver name -- the built-in `text`/`binary`/`union` values
are also rejected conservatively rather than allowlisted. Unlike the
checkout probe above, this one deliberately does NOT pass `--source`:
verified experimentally (disposable repo, 2026-10-13) that a real non-ff
merge only invokes a configured driver when the `merge` attribute is
visible from the CURRENT HEAD's worktree/index -- an attribute defined only
in the incoming branch's `.gitattributes` is not consulted and the merge
falls back to an ordinary content conflict instead, so probing the incoming
tree's attributes would both miss nothing real and risk rejecting merges
that native Git would have completed cleanly. If the merge target does not
resolve to a commit, the probe is skipped and the real
`git merge` command is left to produce its own native error text.

Active-state handling (deliberately the OPPOSITE of
core/git_worktree_context.py's worktree-READ case): branch-create, checkout,
and merge are all REJECTED while any sequencer operation (merge,
cherry-pick, revert, rebase) is already in progress, reusing
`git_commit_context._ACTIVE`'s full tuple -- including `MERGE_HEAD`, unlike
`git_commit_context.py`'s own broad-commit continuation case, which tolerates
`MERGE_HEAD` on purpose because that code exists to *finish* a pending
merge. `git_worktree_context.py` tolerates active state because it only
*reads* already-unmerged paths (that is the entire point of
`detect_conflicts`); this module *writes* new ref/HEAD state, and starting a
second ref mutation while one sequencer operation is already mid-flight is
exactly the unsafe case `_ACTIVE` exists to name. Checked explicitly here,
rather than left to Git's own (inconsistent across these three commands)
native refusal.

Not a filesystem sandbox, atomic transaction, or protection against hostile
concurrent changes. No index, object, ref, or HEAD copy is made; the real
worktree's refs/HEAD/index are mutated directly, by design -- that is the
entire purpose of these three operations.

Cleanup-failure-after-success (found by code-reviewer, fixed 2026-10-13):
the admin-dir `shutil.rmtree(admin)` cleanup in this context manager's
`finally` block used to re-raise unconditionally whenever `original_error`
was `None` -- including when the entire mutation body (branch create,
checkout, merge, or checkpoint rollback) completed with no exception at
all. That turned a genuinely successful operation into a reported failure:
`gate_exec()` (core/action_gateway.py) would record the audit outcome as
`failed` instead of `allowed`, and githelper.py's three callers would raise
an uncaught, unrelated `OSError` instead of returning their formatted
success string. This case is now handled separately from the
both-body-and-cleanup-failed case (which is unchanged): the cleanup OSError
is logged via `utils.logger.warning` and flagged on `context` as
`_mutation_cleanup_failed = True`, which callers check and append as a note
to their own already-computed success/failure string -- this covers both
the success and native-git-failure (`[ERROR]`/`[CONFLICT]`) return paths
for githelper.py's three callers, since both reach the `getattr(context, ...)`
check without raising a Python exception. It does NOT cover
core/checkpoint.py's rollback() on its own native-failure path (a nonzero
checkout or a non-commit hash raises inside the `with` block, so
`original_error is not None` and the note lands on that exception's
`__notes__` instead of on `context` -- rollback()'s own RuntimeError/ValueError
text does not include it). Not a regression -- the note is still attached
to the exception, just not rendered into rollback()'s message -- logged as
NEW-### in NEW_ISSUES.md rather than fixed here, since fixing it would mean
widening rollback()'s exception handling past `GitMutationError` in a way
that risks the exact-string regression guard
(`test_operation_exceptions_are_failed_without_success`) rather than a
one-line change. The leaked admin temp directory itself (left behind under
`real`, inside the repo's `.git`, on every cleanup failure) is a disk-hygiene
issue, not a correctness one, and is also not addressed here.

Fourth caller (slice32): core/checkpoint.py's rollback() routes its two
bare `run_git` calls (a `cat-file -t` validation of the stored checkpoint
hash, then the actual `git checkout --detach <hash> --` restore) through
this module's isolated_mutation_context, reusing exactly the same
hook-neutralization, filter-driver-rejection (via `reject_attribute`), and
active-sequencer-rejection posture already applied to git_checkout. The
`--detach` checkout argv is a new accepted shape in `_valid_mutation_argv`,
separate from `--no-guess`, because rollback's operand is always a raw
full-length hex OID (never a branch/tag name), which cannot trigger
branch-name DWIM.

`cat_file_type(oid)` vs `resolve_target(name)` -- do not use the latter for
rollback's commit-type check. `resolve_target()` resolves via
`<target>^{commit}`, which deliberately peels an annotated tag through to
the commit it points at (correct for an ordinary checkout/merge operand,
which may legitimately be a tag name). rollback's stored `git_hash` field
is meant to hold only a previously-recorded `git rev-parse HEAD` value, so
it must already BE a commit object, not merely resolve to one through a
tag -- a tag object stored there means a tampered/corrupted checkpoint row,
and `resolve_target()` would wrongly accept it. `cat_file_type()` performs
no peeling and reports the literal type of the named object, which is the
check rollback actually needs. Do not swap these two to "simplify" a future
caller; the distinction is the whole point.
"""

import os
import shutil
import stat
import tempfile
from contextlib import contextmanager
from pathlib import Path

from core import git_execution
from core.git_commit_context import _ACTIVE, discover_worktree
from utils.logger import warning


class GitMutationError(RuntimeError):
    """Static policy/protocol/checked-Git mutation diagnostic."""


def _exists(path):
    try:
        path.lstat()
    except (FileNotFoundError, NotADirectoryError):
        return False
    return True


def _regular(path, *, optional=False):
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        if optional:
            return False
        raise GitMutationError("Required Git metadata is missing") from None
    if not stat.S_ISREG(mode):
        raise GitMutationError("Unsupported Git metadata file")
    return True


# Structural keys this module forces regardless of repository/global/system
# configuration, via the highest-precedence GIT_CONFIG_COUNT/KEY/VALUE env
# mechanism (verified experimentally; see module docstring). core.hookspath's
# value is filled in with the admin hooks directory at build time.
_FORCED_OVERRIDES = {
    "core.hookspath": None,
    "core.fsmonitor": "false",
    "gc.auto": "0",
    "maintenance.auto": "false",
    "commit.gpgsign": "false",
    "tag.gpgsign": "false",
    "submodule.recurse": "false",
    "diff.ignoresubmodules": "all",
    "status.submodulesummary": "false",
    "rerere.enabled": "false",
}

_MUTATION_KWARGS = {"cwd", "capture_output", "text", "check", "timeout"}


def _valid_mutation_argv(argv):
    if not isinstance(argv, list) or argv[:1] != ["git"]:
        return False
    if argv[1:2] == ["checkout"]:
        if len(argv) == 4 and argv[2] == "-b" and isinstance(argv[3], str):
            return True
        # --no-guess disables Git's branch-name DWIM (auto-creating a local
        # tracking branch from a same-named remote-tracking ref when the
        # name does not resolve as a ref by itself) so the real command's
        # resolution matches resolve_target()'s strict `rev-parse --verify`
        # probe exactly. Without this, a name that resolve_target() reports
        # as unresolvable (so the filter-driver probe below is skipped) can
        # still succeed via DWIM, smudging content through a filter driver
        # with no rejection check having run at all. Verified experimentally
        # (2026-10-13, disposable repo: remote-tracking branch, no local
        # branch of that name, filter driver configured) that plain
        # `git checkout <name> --` takes the DWIM path and fires the filter,
        # while `git checkout --no-guess <name> --` fails with "invalid
        # reference" exactly as the strict probe predicted.
        if len(argv) == 5 and argv[2] == "--no-guess" and isinstance(argv[3], str) and argv[4] == "--":
            return True
        # --detach is core/checkpoint.py::rollback's exact-hash restore
        # command and needs no --no-guess. rollback() has already confirmed,
        # via cat_file_type(), that the full-length hex string it passes
        # here names an existing commit object before this call ever runs,
        # so DWIM's auto-vivification (new local tracking branch from a
        # same-named remote-tracking ref) is not the relevant risk -- the
        # string resolves as the object itself. Verified experimentally
        # (2026-10-13, disposable repo) that `git checkout --detach <hex> --`
        # still detaches onto that exact commit even when a local branch
        # happens to be named identically to the hex string (Git emits an
        # "ambiguous refname" advice warning and resolves to the object, not
        # the branch) -- this argv does not need --no-guess to behave
        # correctly. Note this validator itself accepts any string in
        # argv[3], not only hex; the hex-only property is enforced by
        # rollback()'s regex check before isolated_mutation_context is ever
        # entered, not by this validator.
        return len(argv) == 5 and argv[2] == "--detach" and isinstance(argv[3], str) and argv[4] == "--"
    if argv[1:2] == ["merge"]:
        return len(argv) == 4 and argv[2] == "--" and isinstance(argv[3], str)
    return False


class _Context:
    def __init__(self, cwd, real, environment):
        self.cwd, self.real, self.environment = cwd, real, environment

    def _run(self, argv, **kwargs):
        return git_execution.run_git(argv, env=dict(self.environment), **kwargs)

    def _query(self, argv, *, input=None, binary=False, check_rc=True):
        kwargs = {"cwd": self.cwd, "capture_output": True, "text": not binary, "timeout": 15}
        if input is not None:
            kwargs["input"] = input
        result = self._run(argv, **kwargs)
        if check_rc and result.returncode != 0:
            raise GitMutationError("Isolated Git mutation query failed")
        return result

    def preflight(self):
        if self._query(["git", "rev-parse", "--shared-index-path"]).stdout.strip():
            raise GitMutationError("Split Git indexes are unsupported")
        index = self._query(["git", "ls-files", "--sparse", "--stage", "-z"], binary=True).stdout
        if any(record.startswith(b"040000 ") for record in index.split(b"\0")):
            raise GitMutationError("Sparse Git indexes are unsupported")

    def resolve_target(self, name):
        """Resolve a checkout/merge operand to a commit oid, or None.

        The bare '-' checkout target is resolved the same way `git checkout -`
        resolves it (verified experimentally: `git rev-parse --verify @{-1}`
        succeeds where `git rev-parse --verify -` does not). Any other
        unresolvable operand (unknown branch/ref) returns None so the caller
        can skip probing and let the real command produce its native error.
        """
        target = "@{-1}" if name == "-" else name
        result = self._query(
            ["git", "rev-parse", "--verify", "--quiet", target + "^{commit}"],
            check_rc=False,
        )
        value = result.stdout.strip()
        if result.returncode != 0 or not value:
            return None
        return value

    def cat_file_type(self, oid):
        """Return `git cat-file -t`'s stripped stdout for `oid`, or '' on failure.

        Unlike resolve_target()'s `^{commit}` peeling (correct for ordinary
        checkout/merge operands, which may legitimately be tag names), this
        performs no peeling -- it reports the literal type of the object named
        by `oid` exactly. core/checkpoint.py's rollback() needs this stricter
        check: its stored hash must already BE a commit object, not merely
        resolve to one through a tag, since that field is meant to hold only a
        previously-recorded `git rev-parse HEAD` value and a type mismatch is
        treated as a tampered/corrupted checkpoint row.
        """
        result = self._query(["git", "cat-file", "-t", oid], check_rc=False)
        return result.stdout.strip() if result.returncode == 0 else ""

    def changed_paths(self, target):
        """Paths that differ between the current HEAD and `target` (-z list)."""
        output = self._query(
            ["git", "diff", "--name-only", "-z", "--no-ext-diff", "--no-textconv", "HEAD", target],
            binary=True,
        ).stdout
        return [name for name in output.split(b"\0") if name]

    def reject_attribute(self, names, attribute, *, source=None):
        """Reject if any of `names` reports a non-empty `attribute` value.

        `--all` omits absent/reset attributes, so an explicit `-<attribute>`
        and a literal unset are indistinguishable in this protocol; both are
        rejected together (see module docstring).

        `source`, when given, reads `.gitattributes` from that tree-ish
        instead of the current worktree/index (`check-attr --source=<ref>`).
        Checkout needs this: verified experimentally (disposable repo,
        2026-10-13) that a real `git checkout` smudges content according to
        the *target* commit's `.gitattributes`, even when the attribute is
        entirely absent from the current HEAD's tree. Merge does not need
        this: verified experimentally (disposable repo, 2026-10-13) that a
        real non-ff `git merge` only invokes a custom `merge.<name>.driver`
        when the `merge` attribute is visible from the *current* HEAD's
        worktree/index -- an attribute defined only in the incoming branch's
        `.gitattributes` does not trigger the driver (git instead reports a
        plain content conflict), so the merge probe correctly omits `source`.
        """
        if not names:
            return
        argv = ["git", "check-attr"]
        if source is not None:
            argv.append(f"--source={source}")
        argv += ["-z", "--stdin", "--all"]
        output = self._query(
            argv,
            input=b"\0".join(names) + b"\0",
            binary=True,
        ).stdout
        fields = output.split(b"\0")
        if (output and not output.endswith(b"\0")) or len(fields) % 3 != 1:
            raise GitMutationError("Isolated Git attribute query is malformed")
        selected = set(names)
        wanted = attribute.encode()
        for index in range(0, len(fields) - 1, 3):
            if fields[index] not in selected or not fields[index + 1]:
                raise GitMutationError("Isolated Git attribute query is malformed")
            if fields[index + 1] == wanted:
                raise GitMutationError(f"Selected Git {attribute} drivers are unsupported")

    def run(self, argv, **kwargs):
        if not kwargs.keys() <= _MUTATION_KWARGS:
            raise ValueError("Unsupported mutation runner keyword arguments")
        if not _valid_mutation_argv(argv):
            raise ValueError("Unsupported Git mutation command")
        if "cwd" in kwargs and os.path.abspath(os.fspath(kwargs["cwd"])) != os.path.abspath(os.fspath(self.cwd)):
            raise ValueError("Mutation cwd cannot be replaced")
        kwargs.setdefault("cwd", self.cwd)
        return self._run(argv, **kwargs)


@contextmanager
def isolated_mutation_context(cwd):
    """Yield a runner that mutates the real worktree/refs directly.

    Ambient hooks, filter drivers, merge drivers, gpg signing, and other
    configured helpers are bounded as described in the module docstring.
    Active sequencer state (merge/cherry-pick/revert/rebase) is rejected.
    A non-fast-forward merge's commit identity comes from Git's own default
    home/global configuration lookup (`HOME`/`XDG_CONFIG_HOME` are forwarded
    by `git_execution._local_commit_environment()`, reused here) -- no
    explicit identity import is performed; see module docstring for why.
    """
    cwd = Path(os.path.abspath(os.fspath(cwd)))
    discovered = discover_worktree(cwd)
    if discovered is None:
        raise GitMutationError("Not a git repository")
    root, real = discovered
    if real == root or real.is_symlink() or not real.is_dir():
        raise GitMutationError("Unsupported Git worktree layout")
    if _exists(real / "commondir") or _exists(real / "gitdir"):
        raise GitMutationError("Linked Git worktrees are unsupported")
    for name in ("objects", "refs"):
        path = real / name
        if path.is_symlink() or not path.is_dir():
            raise GitMutationError("Unsupported Git metadata directory")
    _regular(real / "HEAD")
    for name in ("config", "index", "packed-refs", "shallow"):
        _regular(real / name, optional=True)
    for name in _ACTIVE:
        if _exists(real / name):
            raise GitMutationError("Active Git operations are unsupported")

    environment = dict(git_execution._local_commit_environment())
    admin = Path(tempfile.mkdtemp(prefix="codey-mutate-", dir=real))
    original_error = None
    try:
        (admin / "hooks").mkdir()
        environment["GIT_ATTR_NOSYSTEM"] = "1"
        environment["GIT_NO_LAZY_FETCH"] = "1"
        overrides = dict(_FORCED_OVERRIDES)
        overrides["core.hookspath"] = str(admin / "hooks")
        environment["GIT_CONFIG_COUNT"] = str(len(overrides))
        for index, (key, value) in enumerate(overrides.items()):
            environment[f"GIT_CONFIG_KEY_{index}"] = key
            environment[f"GIT_CONFIG_VALUE_{index}"] = value
        context = _Context(cwd, real, environment)
        context.preflight()
        try:
            yield context
        except BaseException as exc:
            original_error = exc
            raise
    except BaseException as exc:
        original_error = exc
        raise
    finally:
        try:
            shutil.rmtree(admin)
        except Exception as exc:  # noqa: BLE001 - report cleanup failure without masking a real mutation error
            if original_error is not None:
                original_error.add_note("Git mutation context cleanup also failed")
                original_error._mutation_cleanup_failed = True
            else:
                # The mutation body (and setup/preflight above it) ran to
                # completion with no exception -- this is a genuinely
                # successful branch create, checkout, merge, or checkpoint
                # rollback. Re-raising this admin-dir cleanup OSError here
                # would make it the ONLY exception the caller sees: found
                # by code-reviewer 2026-10-13, it made gate_exec()
                # (core/action_gateway.py) record a real HIGH_IMPACT/ACT
                # success as "failed" in the audit ledger, and for
                # githelper.py's three callers, replaced their formatted
                # success string with an uncaught, unrelated OSError. Report
                # it without raising. `context` is still the object bound in
                # the caller's `with ... as context:` (the thrown-in
                # exception path was never taken), so flag it there and let
                # each caller append the existing cleanup-failed note to its
                # own already-computed result string. The leaked admin temp
                # dir under `real` (inside the repo's .git) is a
                # disk-hygiene issue, not a correctness one.
                warning(
                    f"Git mutation context cleanup failed after a successful "
                    f"operation; admin directory not removed ({admin}): {exc}"
                )
                context._mutation_cleanup_failed = True
