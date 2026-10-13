"""Copied-index Git worktree READ operations using copied private administration.

Unlike core/git_query_context.py's fixed metadata reads (which never touch the
index and so can safely point GIT_INDEX_FILE at a nonexistent file), these five
operations read actual working-tree/index comparisons (status, diff, conflict
detection). A fabricated empty index silently produces false-empty results for
these commands (verified experimentally: a real merge conflict's `UU` status
line and unmerged-path diff output disappear entirely against a fresh empty
index). The admin dir therefore copies the real index, not a fabricated one.

Two deliberate inversions from core/git_commit_context.py's isolated-commit
contract:
  1. Sparse/split indexes now fail explicitly (reusing the same probes) —
     the commit contract tolerates neither, but this module did not inherit
     that enforcement before this slice; it now does.
  2. Active merge/cherry-pick/revert/rebase state is explicitly SUPPORTED,
     not rejected — detect_conflicts exists specifically to report unmerged
     paths, which only exist mid-merge. core/git_commit_context.py's _ACTIVE
     rejection list is intentionally not imported or reused here.

Verified experimentally (disposable repo, real forced merge conflict): the
`UU`/unmerged presentation in `git status --short` and in
`git diff --name-only --diff-filter=U` is produced entirely from index stage
data, not from MERGE_HEAD/MERGE_MSG/CHERRY_PICK_HEAD/REVERT_HEAD/REBASE_HEAD.
Those files are therefore NOT copied into the admin dir — copied-index-only
reproduces identical output to the real repository for the merge/conflict
cases this module performs, including `git diff`/`git diff --cached` content
during an active conflict. (The one divergence found there was non-`--short`
`git status`'s merge-specific *hint text*, which none of these five
operations use.)

This parity claim does NOT extend to output-shaping config: `_DATA_KEYS`
imports Git-identity/conversion keys (core.autocrlf, core.eol, etc.) but not
status/diff presentation keys such as status.showUntrackedFiles,
diff.algorithm, diff.context, or diff.mnemonicPrefix. A real repository
configured with e.g. status.showUntrackedFiles=no will report untracked
files here where the real `git status --short` would hide them (verified
experimentally). The fixed, bounded config surface is a deliberate design
choice, not a gap to close by expanding the allowlist — it keeps this
module's config exposure auditable — but output can diverge from the real
repository's configured presentation for these keys. See NEW_ISSUES.md.

This is not an atomic snapshot, filesystem sandbox, or binary integrity proof.
Local object alternates are unrestricted read data. No original index, locks,
refs, logs, or configuration are written.

Two further explicit decisions, each checked against real Git rather than
assumed (rule 12):
  - info/grafts IS copied into the admin dir (read-only; mirrors
    core/git_query_context.py:239-242) so has_parent()/HEAD~1..HEAD history
    queries see the same graft-rewritten ancestry as the real repository.
  - Relative core.attributesfile/core.excludesfile values are resolved
    against self.root (the worktree root), not self.cwd. Verified
    experimentally: a relative core.excludesfile continues to exclude a
    top-level path identically whether Git is invoked from the worktree
    root or from a subdirectory, i.e. real Git resolves these paths against
    the top of the working tree, never the invoking cwd. core/git_commit_context.py
    (fixed under NEW-885) now resolves the same two keys against self.root as
    well, so the two modules agree here.
"""

import os
import re
import shutil
import stat
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

from core import git_execution
from core.git_commit_context import discover_worktree


class GitWorktreeError(RuntimeError):
    """Static policy/protocol/checked-Git worktree diagnostic."""


# Positive-import allowlist: native worktree conversion/attribute scalars only.
# Distinct from core/git_commit_context.py's 24-key _DATA_KEYS (identity/commit
# specific); this module never commits, so identity keys are not imported.
_DATA_KEYS = {
    "core.autocrlf", "core.eol", "core.safecrlf", "core.checkroundtripencoding",
    "core.attributesfile", "core.excludesfile", "core.precomposeunicode",
    "core.symlinks", "core.filemode", "core.ignorecase", "core.quotepath",
    "core.bigfilethreshold",
}

_DIFF_QUIET = ("--no-ext-diff", "--no-textconv")


def _temporary_candidates():
    return (Path(sys.base_prefix) / "tmp", Path("/tmp"))


def _regular(path, *, optional=False):
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        if optional:
            return False
        raise GitWorktreeError("Required Git worktree metadata is missing") from None
    if not stat.S_ISREG(mode):
        raise GitWorktreeError("Unsupported Git worktree metadata file")
    return True


def _directory(path):
    if not stat.S_ISDIR(path.lstat().st_mode):
        raise GitWorktreeError("Unsupported Git worktree metadata directory")


def _present(path):
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    return True


def _copy_refs(source, target):
    target.mkdir()
    for entry in source.iterdir():
        mode = entry.lstat().st_mode
        if stat.S_ISDIR(mode):
            _copy_refs(entry, target / entry.name)
        elif stat.S_ISREG(mode):
            shutil.copyfile(entry, target / entry.name)
        else:
            raise GitWorktreeError("Unsupported Git worktree reference data")


class _Worktree:
    def __init__(self, cwd, root, real, admin):
        self.cwd, self.root, self.real, self.admin = cwd, root, real, admin
        parents = dict.fromkeys(str(path.parent) for path in git_execution._git_candidates() if path.is_absolute())
        if not parents:
            raise GitWorktreeError("No trusted Git worktree installation directories")
        self.environment = {
            "PATH": os.pathsep.join(parents), "LC_ALL": "C", "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_SYSTEM": os.devnull, "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_DIR": str(admin), "GIT_WORK_TREE": str(root),
            "GIT_OBJECT_DIRECTORY": str(real / "objects"), "GIT_INDEX_FILE": str(admin / "index"),
            "GIT_OPTIONAL_LOCKS": "0", "GIT_NO_LAZY_FETCH": "1", "GIT_TERMINAL_PROMPT": "0",
            "GIT_ATTR_NOSYSTEM": "1",
        }
        self.hash_length = 40
        self.unborn = False
        self.branch = None

    def _run(self, argv, **kwargs):
        if not _valid_worktree_argv(argv):
            raise GitWorktreeError("Unsupported fixed Git worktree command")
        kwargs.setdefault("cwd", self.cwd)
        kwargs.setdefault("timeout", 15)
        return git_execution.run_git(argv, env=dict(self.environment), capture_output=True, **kwargs)

    def _checked(self, argv, *, binary=False, input=None):
        kwargs = {"text": not binary}
        if input is not None:
            kwargs["input"] = input
        result = self._run(argv, **kwargs)
        if result.returncode != 0:
            raise GitWorktreeError("Git worktree command failed")
        if not isinstance(result.stdout, (str, bytes)):
            raise GitWorktreeError("Git worktree command protocol is invalid")
        return result.stdout

    def configure(self):
        values = {}
        if _regular(self.real / "config", optional=True):
            output = self._checked(["git", "config", "--file", str(self.real / "config"), "--no-includes", "--null", "--list"])
            if output and not output.endswith("\0"):
                raise GitWorktreeError("Git worktree configuration protocol is invalid")
            for record in output[:-1].split("\0") if output else []:
                if not record:
                    raise GitWorktreeError("Git worktree configuration protocol is invalid")
                key, separator, value = record.partition("\n")
                if not key or "." not in key:
                    raise GitWorktreeError("Git worktree configuration protocol is invalid")
                value = value if separator else "true"
                key = key.lower()
                if key.startswith(("include.", "includeif.")):
                    raise GitWorktreeError("Repository configuration includes are unsupported for worktree queries")
                values[key] = value
        version = values.get("core.repositoryformatversion", "0")
        extensions = {key: value for key, value in values.items() if key.startswith("extensions.")}
        if version not in ("0", "1") or (version == "0" and extensions) or not extensions.keys() <= {"extensions.objectformat", "extensions.refstorage"}:
            raise GitWorktreeError("Unsupported Git worktree repository format")
        if values.get("core.bare", "false").lower() not in ("false", "no", "off", "0") or "core.worktree" in values:
            raise GitWorktreeError("Unsupported Git worktree configuration")
        if values.get("core.sparsecheckout", "false").lower() not in ("false", "no", "off", "0"):
            raise GitWorktreeError("Sparse Git worktree indexes are unsupported")
        object_format = extensions.get("extensions.objectformat", "sha1")
        if object_format not in ("sha1", "sha256") or extensions.get("extensions.refstorage", "files") != "files":
            raise GitWorktreeError("Unsupported Git worktree storage format")
        self.hash_length = 64 if object_format == "sha256" else 40
        structure = {
            "core.repositoryformatversion": version, "core.bare": "false",
            "core.splitindex": "false", "core.fsmonitor": "false",
            "gc.auto": "0", "maintenance.auto": "false", "core.sparsecheckout": "false",
        }
        if object_format == "sha256":
            structure.update({"core.repositoryformatversion": "1", "extensions.objectformat": "sha256"})
        for key, value in values.items():
            if key not in _DATA_KEYS:
                continue
            if key in ("core.attributesfile", "core.excludesfile") and (value.startswith("~/") or value == "~"):
                # No child HOME is carried into this READ context; reject
                # rather than silently resolving against an ambient one.
                raise GitWorktreeError("Home-relative Git worktree data paths are unsupported")
            if key in ("core.attributesfile", "core.excludesfile") and not os.path.isabs(value):
                value = os.path.join(os.fspath(self.root), value)
            structure[key] = value
        # admin/config already holds the base [core] block written by the
        # context manager; each key is replaced through git itself so
        # values with special characters are quoted the way Git expects.
        for key, value in structure.items():
            result = git_execution.run_git(
                ["git", "config", "--file", str(self.admin / "config"), "--replace-all", key, value],
                env=dict(self.environment), cwd=self.root, capture_output=True, text=True, timeout=15,
            )
            if result.returncode != 0:
                raise GitWorktreeError("Git worktree configuration is invalid")

    def preflight(self):
        if self._checked(["git", "rev-parse", "--shared-index-path"]).strip():
            raise GitWorktreeError("Split Git worktree indexes are unsupported")
        index = self._checked(["git", "ls-files", "--sparse", "--stage", "-z"], binary=True)
        if any(record.startswith(b"040000 ") for record in index.split(b"\0")):
            raise GitWorktreeError("Sparse Git worktree indexes are unsupported")

    def validate_head(self):
        with (self.admin / "HEAD").open("rb") as stream:
            raw = stream.read(4097)
        if len(raw) > 4096:
            raise GitWorktreeError("Git worktree HEAD exceeds supported size")
        try:
            value = raw.decode("ascii").removesuffix("\n")
        except UnicodeDecodeError:
            raise GitWorktreeError("Git worktree HEAD is invalid") from None
        if value.startswith("ref: "):
            target = value[5:]
            if not target.startswith("refs/heads/") or self._run(["git", "check-ref-format", target]).returncode != 0:
                raise GitWorktreeError("Git worktree symbolic HEAD is unsupported")
            _regular(self.admin / target, optional=True)
            self.branch = target[len("refs/heads/"):]
            existence = self._run(["git", "show-ref", "--exists", target]).returncode
            if existence == 2:
                self.unborn = True
                return
            if existence != 0:
                raise GitWorktreeError("Git worktree reference lookup failed")
        elif not re.fullmatch(r"[0-9a-fA-F]{" + str(self.hash_length) + r"}", value):
            raise GitWorktreeError("Git worktree detached HEAD is invalid")

    def has_parent(self):
        return self._run(["git", "rev-parse", "--verify", "HEAD~1"]).returncode == 0

    def _names(self, argv, *, input=None):
        output = self._checked(argv, binary=True, input=input)
        return [name for name in output.split(b"\0") if name]

    def reject_filtered(self, names):
        """Guard against arbitrary external filter execution before any
        content-producing (non-name-only) worktree command runs. Must be
        called strictly before the corresponding content command, using a
        name list obtained from a filter-inert (name-only) query — running
        it afterward would let a malicious filter execute first."""
        if not names:
            return
        attributes = self._checked(["git", "check-attr", "-z", "--stdin", "--all"], binary=True, input=b"\0".join(names) + b"\0")
        fields = attributes.split(b"\0")
        if (attributes and not attributes.endswith(b"\0")) or len(fields) % 3 != 1:
            raise GitWorktreeError("Git worktree attribute query is malformed")
        selected = set(names)
        for index in range(0, len(fields) - 1, 3):
            if fields[index] not in selected or not fields[index + 1]:
                raise GitWorktreeError("Git worktree attribute query is malformed")
            # --all omits absent/reset attributes; explicit -filter and a
            # literal unset filter are indistinguishable here, so both
            # outcomes are rejected together.
            if fields[index + 1] == b"filter":
                raise GitWorktreeError("Selected Git filter drivers are unsupported")

    def status(self, paths):
        argv = ["git", "status", "--short"]
        if paths is not None:
            argv = ["git", "--literal-pathspecs", "status", "--short", "--", *paths]
        name_argv = ["git", "diff", "--name-only", "-z", *_DIFF_QUIET]
        other_argv = ["git", "ls-files", "--others", "--exclude-standard", "-z"]
        if paths is not None:
            name_argv = ["git", "--literal-pathspecs", "diff", "--name-only", "-z", *_DIFF_QUIET, "--", *paths]
            other_argv = ["git", "--literal-pathspecs", "ls-files", "--others", "--exclude-standard", "-z", "--", *paths]
        names = set(self._names(name_argv)) | set(self._names(other_argv))
        self.reject_filtered(sorted(names))
        output = self._checked(argv)
        return output.strip() or "Nothing to commit."

    def diff_stat(self):
        if self.unborn:
            return ""
        names = self._names(["git", "diff", "--name-only", "HEAD", "-z", *_DIFF_QUIET])
        self.reject_filtered(names)
        return self._checked(["git", "diff", "--stat", "HEAD", *_DIFF_QUIET]).strip()

    def detect_conflicts(self):
        names = self._names(["git", "diff", "--name-only", "--diff-filter=U", "-z", *_DIFF_QUIET])
        if names:
            return [os.fsdecode(name) for name in names]
        # Fallback preserved verbatim, including its known UU/AA-only prefix
        # gap (pre-registered NEW_ISSUES candidate; not fixed in this slice).
        other_names = set(self._names(["git", "diff", "--name-only", "-z", *_DIFF_QUIET]))
        other_names |= set(self._names(["git", "ls-files", "--others", "--exclude-standard", "-z"]))
        self.reject_filtered(sorted(other_names))
        output = self._checked(["git", "status", "--short"])
        files = []
        for line in output.splitlines():
            if line.startswith("UU ") or line.startswith("AA "):
                files.append(line[3:].strip())
        return files

    def diff_for_commit(self, max_chars):
        def truncate(text):
            if len(text) > max_chars:
                return text[:max_chars] + "\n... (truncated)"
            return text

        for content_argv, name_argv in (
            (["git", "diff", "--cached", *_DIFF_QUIET], ["git", "diff", "--cached", "--name-only", "-z", *_DIFF_QUIET]),
            (["git", "diff", *_DIFF_QUIET], ["git", "diff", "--name-only", "-z", *_DIFF_QUIET]),
        ):
            names = self._names(name_argv)
            if not names:
                continue
            self.reject_filtered(names)
            diff = self._checked(content_argv).strip()
            if diff:
                return truncate(diff)

        if self.unborn or not self.has_parent():
            return "(no diff available)"
        names = self._names(["git", "diff", "--name-only", "HEAD~1", "HEAD", "-z", *_DIFF_QUIET])
        if not names:
            return "(no diff available)"
        self.reject_filtered(names)
        diff = self._checked(["git", "diff", "HEAD~1", "HEAD", *_DIFF_QUIET]).strip()
        return truncate(diff) if diff else "(no diff available)"


_FIXED_ARGV = (
    ["git", "status", "--short"],
    ["git", "rev-parse", "--shared-index-path"],
    ["git", "rev-parse", "--verify", "HEAD~1"],
    ["git", "ls-files", "--sparse", "--stage", "-z"],
    ["git", "ls-files", "--others", "--exclude-standard", "-z"],
    ["git", "check-attr", "-z", "--stdin", "--all"],
    ["git", "diff", "--stat", "HEAD", *_DIFF_QUIET],
    ["git", "diff", "--cached", *_DIFF_QUIET],
    ["git", "diff", *_DIFF_QUIET],
    ["git", "diff", "HEAD~1", "HEAD", *_DIFF_QUIET],
    ["git", "diff", "--name-only", "-z", *_DIFF_QUIET],
    ["git", "diff", "--name-only", "HEAD", "-z", *_DIFF_QUIET],
    ["git", "diff", "--name-only", "HEAD~1", "HEAD", "-z", *_DIFF_QUIET],
    ["git", "diff", "--cached", "--name-only", "-z", *_DIFF_QUIET],
    ["git", "diff", "--name-only", "--diff-filter=U", "-z", *_DIFF_QUIET],
)

# Path-taking prefixes: argv must be one of these fixed heads, followed by
# "--", followed by zero or more literal path operands (any strings).
_PATH_PREFIXES = (
    ["git", "--literal-pathspecs", "status", "--short", "--"],
    ["git", "--literal-pathspecs", "diff", "--name-only", "-z", *_DIFF_QUIET, "--"],
    ["git", "--literal-pathspecs", "ls-files", "--others", "--exclude-standard", "-z", "--"],
)


def _valid_worktree_argv(argv):
    if not isinstance(argv, list) or not argv or argv[0] != "git":
        return False
    if argv in _FIXED_ARGV:
        return True
    if len(argv) >= 4 and argv[1] == "config" and argv[2] == "--file" and isinstance(argv[3], str):
        return argv[4:] == ["--no-includes", "--null", "--list"] or (
            len(argv) == 7 and argv[4] == "--replace-all" and isinstance(argv[5], str) and isinstance(argv[6], str)
        )
    if len(argv) == 3 and argv[:2] == ["git", "check-ref-format"] and isinstance(argv[2], str) and argv[2].startswith("refs/heads/"):
        return True
    if len(argv) == 4 and argv[:3] == ["git", "show-ref", "--exists"] and isinstance(argv[3], str) and argv[3].startswith("refs/heads/"):
        return True
    for prefix in _PATH_PREFIXES:
        # NEW-879: path operands are forwarded verbatim, including bytes.
        if argv[:len(prefix)] == prefix and all(isinstance(token, (str, bytes)) for token in argv[len(prefix):]):
            return True
    return False


@contextmanager
def _worktree_context(cwd):
    cwd = Path(os.path.abspath(os.fspath(cwd)))
    _directory(cwd)
    found = discover_worktree(cwd)
    if found is None:
        yield None
        return
    root, real = found
    if root == real:
        raise GitWorktreeError("Bare Git worktree queries are unsupported")
    _directory(real)
    _directory(real / "objects")
    _directory(real / "refs")
    if _present(real / "commondir") or _present(real / "gitdir"):
        raise GitWorktreeError("Linked Git worktree queries are unsupported")
    for name in ("config", "index", "packed-refs", "shallow"):
        _regular(real / name, optional=True)
    parent = None
    for candidate in _temporary_candidates():
        if not candidate.is_absolute() or candidate == root or root in candidate.parents:
            continue
        if candidate.is_symlink():
            continue
        resolved = candidate.resolve()
        resolved_root = root.resolve()
        if resolved == resolved_root or resolved_root in resolved.parents:
            continue
        if candidate.is_dir() and os.access(candidate, os.W_OK | os.X_OK):
            parent = candidate
            break
    if parent is None:
        raise GitWorktreeError("No usable external Git worktree temporary directory")
    admin = Path(tempfile.mkdtemp(prefix="codey-worktree-", dir=parent))
    original_error = None
    try:
        _regular(real / "HEAD")
        with (real / "HEAD").open("rb") as stream:
            value = stream.read(4097)
        if len(value) > 4096:
            raise GitWorktreeError("Git worktree HEAD exceeds supported size")
        (admin / "HEAD").write_bytes(value)
        _copy_refs(real / "refs", admin / "refs")
        for name in ("packed-refs", "shallow"):
            if _regular(real / name, optional=True):
                shutil.copyfile(real / name, admin / name)
        if (real / "info").exists() or (real / "info").is_symlink():
            _directory(real / "info")
        (admin / "info").mkdir()
        for name in ("attributes", "exclude", "grafts"):
            source = real / "info" / name
            if _regular(source, optional=True):
                shutil.copyfile(source, admin / "info" / name)
        if _regular(real / "index", optional=True):
            shutil.copyfile(real / "index", admin / "index")
        (admin / "config").write_text("[core]\nrepositoryFormatVersion = 0\nbare = false\n")
        context = _Worktree(cwd, root, real, admin)
        context.configure()
        context.preflight()
        context.validate_head()
        yield context
    except BaseException as exc:
        original_error = exc
        raise
    finally:
        try:
            shutil.rmtree(admin)
        except Exception:  # Preserve body identity; report additional cleanup failure.
            if original_error is None:
                raise
            original_error.add_note("Git worktree query cleanup also failed")
            original_error._git_worktree_cleanup_failed = True


def worktree_query(cwd, *, action, operation, paths=None, max_chars=3000):
    """One READ audit; unexpected errors retain identity with static audit text."""
    from core.action_gateway import READ, get_action_gateway

    original_error = None

    def execute():
        nonlocal original_error
        try:
            with _worktree_context(cwd or os.getcwd()) as context:
                if context is None:
                    raise GitWorktreeError("Git worktree query requires a repository")
                if operation == "status":
                    return context.status(None)
                if operation == "status_paths":
                    return context.status(list(paths) if paths else None)
                if operation == "diff_stat":
                    return context.diff_stat()
                if operation == "detect_conflicts":
                    return context.detect_conflicts()
                if operation == "diff_for_commit":
                    return context.diff_for_commit(max_chars)
                raise GitWorktreeError("Unsupported Git worktree operation")
        except Exception as exc:
            original_error = exc
            reason = str(exc) if isinstance(exc, GitWorktreeError) else "Git worktree query failed"
            if getattr(exc, "_git_worktree_cleanup_failed", False):
                reason += "; Git worktree query cleanup also failed"
            raise GitWorktreeError(reason) from exc

    decision = get_action_gateway().gate_exec(
        authority=READ, action=action, command="git worktree query",
        confirm_available=False, execute=execute,
    )
    if original_error is not None:
        raise original_error
    if not decision.allowed:
        raise GitWorktreeError("Git worktree query was refused")
    return decision.detail["result"]
