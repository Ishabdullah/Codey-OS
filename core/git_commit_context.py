"""Isolated scoped commits in ordinary Git worktrees.

Only selected configuration data is imported. Hooks, signing, executable
filters and other configured helpers are excluded. Explicit -filter is also
unsupported: Git cannot distinguish it from a driver named unset in this
protocol. Absent/reset attributes remain usable. This is not a filesystem
sandbox, atomic transaction, or protection against hostile concurrent changes.
"""

import os
import shutil
import stat
import tempfile
from contextlib import contextmanager
from pathlib import Path

from core import git_execution


class ScopedCommitError(RuntimeError):
    """Expected policy failures or checked Git failures.

    Policy diagnostics are static; checked Git diagnostics preserve stderr.
    """


_DATA_KEYS = {
    "user.name", "user.email", "user.useconfigonly", "author.name", "author.email",
    "committer.name", "committer.email", "core.filemode", "core.ignorecase",
    "core.symlinks", "core.precomposeunicode", "core.autocrlf", "core.eol",
    "core.safecrlf", "core.checkroundtripencoding", "core.attributesfile",
    "core.excludesfile", "core.protecthfs", "core.protectntfs", "core.quotepath",
    "core.bigfilethreshold", "core.logallrefupdates", "i18n.commitencoding", "commit.cleanup",
}
_ACTIVE = ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "REBASE_HEAD", "rebase-merge", "rebase-apply", "sequencer")
_KWARGS = {"cwd", "capture_output", "text", "check", "timeout"}


def discover_worktree(cwd):
    """Find ordinary/unsupported repo candidates without invoking Git.

    Absence returns None; permission/read errors remain actual exceptions.
    A .git file, symlink or bare candidate is returned for audited rejection.
    """
    current = Path(os.path.abspath(os.fspath(cwd)))
    while True:
        try:
            (current / ".git").lstat()
        except FileNotFoundError:
            if (current / "HEAD").is_file() and (current / "objects").is_dir() and (current / "refs").is_dir():
                return current, current
        else:
            return current, current / ".git"
        if current.parent == current:
            return None
        current = current.parent


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
        raise ScopedCommitError("Required Git metadata is missing") from None
    if not stat.S_ISREG(mode):
        raise ScopedCommitError("Unsupported Git metadata file")
    return True


class _Context:
    def __init__(self, cwd, paths, root, real, admin, environment):
        self.cwd, self.paths = cwd, list(paths)
        self.root, self.real, self.admin = root, real, admin
        self.environment = environment

    def _run(self, argv, **kwargs):
        return git_execution.run_git(argv, env=dict(self.environment), **kwargs)

    def _query(self, argv, *, input=None, cwd=None, binary=False):
        kwargs = {"cwd": cwd or self.cwd, "capture_output": True, "text": not binary, "timeout": 15}
        if input is not None:
            kwargs["input"] = input
        result = self._run(argv, **kwargs)
        if result.returncode != 0:
            raise ScopedCommitError("Isolated Git metadata query failed")
        return result.stdout

    def run(self, argv, **kwargs):
        if not kwargs.keys() <= _KWARGS:
            raise ValueError("Unsupported scoped commit runner keyword arguments")
        if not isinstance(argv, (list, tuple)) or not argv or argv[0] != "git":
            raise ValueError("Scoped commit argv must begin with git")
        position = 2 if len(argv) > 1 and argv[1] == "--literal-pathspecs" else 1
        if len(argv) <= position or argv[position] not in {"add", "status", "diff", "commit", "rev-parse"}:
            raise ValueError("Unsupported scoped commit operation")
        if "cwd" in kwargs and os.path.abspath(os.fspath(kwargs["cwd"])) != os.path.abspath(os.fspath(self.cwd)):
            raise ValueError("Scoped commit cwd cannot be replaced")
        result = self._run(argv, **kwargs)
        if argv[position] == "status" and result.returncode != 0:
            raise ScopedCommitError("Isolated Git status failed")
        return result

    def _config(self, key, value):
        result = self._run(["git", "config", "--file", str(self.admin / "config"), "--replace-all", key, value], cwd=self.cwd, capture_output=True, text=True, timeout=15)
        if result.returncode != 0:
            raise ScopedCommitError("Isolated Git configuration is invalid")

    def configure(self, child_home, child_xdg):
        files = []
        if child_xdg:
            files.append(Path(child_xdg) / "git/config")
        elif child_home:
            files.append(Path(child_home) / ".config/git/config")
        if child_home:
            files.append(Path(child_home) / ".gitconfig")
        files.append(self.real / "config")
        selected, repository = {}, {}
        for file in files:
            if not _regular(file, optional=True):
                continue
            records = self._query(["git", "config", "--file", str(file), "--includes", "--null", "--list"])
            for record in records.split("\0"):
                if not record:
                    continue
                key, separator, value = record.partition("\n")
                key = key.lower()
                if key.startswith("includeif."):
                    raise ScopedCommitError("Conditional Git configuration includes are unsupported")
                value = value if separator else "true"
                if key in _DATA_KEYS:
                    selected[key] = value
                if file == self.real / "config":
                    repository[key] = value
        if repository.get("core.bare", "false").lower() not in ("false", "no", "off", "0") or "core.worktree" in repository:
            raise ScopedCommitError("Bare or custom Git worktrees are unsupported")
        version = repository.get("core.repositoryformatversion", "0")
        if version not in ("0", "1"):
            raise ScopedCommitError("Unsupported Git repository format")
        extensions = {key: value for key, value in repository.items() if key.startswith("extensions.")}
        if not extensions.keys() <= {"extensions.objectformat", "extensions.refstorage"}:
            raise ScopedCommitError("Unsupported Git repository extensions")
        if version == "0" and extensions:
            raise ScopedCommitError("Git extensions require repository format version one")
        object_format = extensions.get("extensions.objectformat", "sha1")
        if object_format not in ("sha1", "sha256") or extensions.get("extensions.refstorage", "files") != "files":
            raise ScopedCommitError("Unsupported Git object or reference format")
        if repository.get("core.sparsecheckout", "false").lower() not in ("false", "no", "off", "0"):
            raise ScopedCommitError("Sparse Git indexes are unsupported")
        structure = {
            "core.repositoryformatversion": version, "core.bare": "false",
            "core.hookspath": str(self.admin / "hooks"), "core.fsmonitor": "false",
            "gc.auto": "0", "maintenance.auto": "false",
            "commit.gpgsign": "false", "tag.gpgsign": "false", "submodule.recurse": "false",
            "diff.ignoresubmodules": "all", "status.submodulesummary": "false",
        }
        if object_format == "sha256":
            structure.update({"core.repositoryformatversion": "1", "extensions.objectformat": "sha256"})
        for key, value in {**selected, **structure}.items():
            if key in ("core.attributesfile", "core.excludesfile"):
                if value.startswith("~/"):
                    if not child_home:
                        raise ScopedCommitError("Git data path requires a home directory")
                    value = str(Path(child_home) / value[2:])
                elif not os.path.isabs(value):
                    value = os.path.join(os.fspath(self.cwd), value)
            self._config(key, value)

    def preflight_paths(self):
        if self._query(["git", "rev-parse", "--shared-index-path"]).strip():
            raise ScopedCommitError("Split Git indexes are unsupported")
        self._config("core.splitindex", "false")
        # Check all index modes for sparse entries; check selected gitlinks only.
        index = self._query(["git", "ls-files", "--sparse", "--stage", "-z"], binary=True)
        if any(record.startswith(b"040000 ") for record in index.split(b"\0")):
            raise ScopedCommitError("Sparse Git indexes are unsupported")
        selected = self._query(["git", "--literal-pathspecs", "ls-files", "--stage", "-z", "--", *self.paths], binary=True)
        if any(record.startswith(b"160000 ") for record in selected.split(b"\0")):
            raise ScopedCommitError("Selected Git submodules are unsupported")
        candidates = self._query(["git", "--literal-pathspecs", "ls-files", "--cached", "--others", "--exclude-standard", "--full-name", "-z", "--", *self.paths], binary=True)
        names = [name for name in candidates.split(b"\0") if name]
        for name in names:
            candidate = self.root / os.fsdecode(name.rstrip(b"/"))
            while candidate != self.root and self.root in candidate.parents:
                if _exists(candidate / ".git"):
                    raise ScopedCommitError("Selected embedded Git repositories are unsupported")
                candidate = candidate.parent
        if names:
            attributes = self._query(["git", "check-attr", "-z", "--stdin", "--all"], input=b"\0".join(names) + b"\0", cwd=self.root, binary=True)
            fields = attributes.split(b"\0")
            if (attributes and not attributes.endswith(b"\0")) or len(fields) % 3 != 1:
                raise ScopedCommitError("Isolated Git attribute query is malformed")
            selected_names = set(names)
            for index in range(0, len(fields) - 1, 3):
                if fields[index] not in selected_names or not fields[index + 1]:
                    raise ScopedCommitError("Isolated Git attribute query is malformed")
                # --all omits absent/reset attributes, unlike named queries.
                # Reject all filter records: explicit -filter and literal unset
                # have identical protocol output, so both are unsupported.
                if fields[index + 1] == b"filter":
                    raise ScopedCommitError("Selected Git filter drivers are unsupported")



@contextmanager
def isolated_scoped_commit_context(cwd, paths):
    """Yield a scoped runner with positive config and native data attributes.

    Uses actual index/objects/refs/reflogs. An owned HEAD lock coordinates ordinary
    Git users; detached HEAD publication occurs even after an operation failure.
    Staging, commit and publication can leave partial effects. No hostile path
    replacement, transaction, or filesystem containment guarantee is made.
    """
    discovered = discover_worktree(cwd)
    if discovered is None:
        raise ScopedCommitError("Not a git repository")
    root, real = discovered
    if real == root or real.is_symlink() or not real.is_dir():
        raise ScopedCommitError("Unsupported Git worktree layout")
    for name in _ACTIVE:
        if _exists(real / name):
            raise ScopedCommitError("Active Git operations are unsupported")
    if _exists(real / "commondir") or _exists(real / "gitdir"):
        raise ScopedCommitError("Linked Git worktrees are unsupported")
    for name in ("objects", "refs"):
        path = real / name
        if path.is_symlink() or not path.is_dir():
            raise ScopedCommitError("Unsupported Git metadata directory")
    for name in ("logs", "info"):
        path = real / name
        if _exists(path) and (path.is_symlink() or not path.is_dir()):
            raise ScopedCommitError("Unsupported Git metadata directory")
    _regular(real / "HEAD")
    for name in ("config", "index", "packed-refs", "shallow"):
        _regular(real / name, optional=True)
    original_head = None
    environment = dict(git_execution._local_commit_environment())
    home, xdg = environment.get("HOME"), environment.get("XDG_CONFIG_HOME")
    lock = real / "HEAD.lock"
    fd = None
    owned_stat = None
    published = False
    admin = None
    operation_error = None
    try:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            raise ScopedCommitError("Git HEAD is already locked") from None
        owned_stat = os.fstat(fd)
        original_head = (real / "HEAD").read_bytes()
        admin = Path(tempfile.mkdtemp(prefix="codey-scoped-", dir=real))
        (admin / "HEAD").write_bytes(original_head)
        (admin / "config").write_text("[core]\nrepositoryFormatVersion = 0\nbare = false\n")
        (admin / "hooks").mkdir()
        (admin / "info").mkdir()
        for name in ("attributes", "exclude"):
            source = real / "info" / name
            if _regular(source, optional=True):
                shutil.copyfile(source, admin / "info" / name)
        for name in ("packed-refs", "shallow"):
            if _regular(real / name, optional=True):
                shutil.copyfile(real / name, admin / name)
        (real / "logs").mkdir(exist_ok=True)
        for name in ("refs", "objects", "logs"):
            (admin / name).symlink_to(real / name, target_is_directory=True)
        environment.update({
            "GIT_DIR": str(admin), "GIT_WORK_TREE": str(root), "GIT_INDEX_FILE": str(real / "index"),
            "GIT_OBJECT_DIRECTORY": str(real / "objects"), "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_SYSTEM": os.devnull, "GIT_ATTR_NOSYSTEM": "1", "GIT_NO_LAZY_FETCH": "1",
        })
        context = _Context(cwd, paths, root, real, admin, environment)
        context.configure(home, xdg)
        context.preflight_paths()
        try:
            yield context.run
        except BaseException as exc:
            operation_error = exc
            raise
    except BaseException as exc:
        operation_error = exc
        raise
    finally:
        cleanup_error = None
        if fd is not None:
            try:
                if original_head is not None and (real / "HEAD").read_bytes() != original_head:
                    raise ScopedCommitError("Actual Git HEAD changed during scoped commit")
                if admin is not None:
                    private_head = (admin / "HEAD").read_bytes()
                    if not original_head.startswith(b"ref: ") and private_head != original_head:
                        if os.write(fd, private_head) != len(private_head):
                            raise ScopedCommitError("Detached Git HEAD publication was incomplete")
                        if lock.lstat().st_ino != owned_stat.st_ino:
                            raise ScopedCommitError("Owned Git HEAD lock was replaced")
                        os.replace(lock, real / "HEAD")
                        published = True
                        os.close(fd)
                        fd = None
            except Exception as exc:  # noqa: BLE001 - finish cleanup, preserve operation error
                cleanup_error = exc
            try:
                if not published and _exists(lock):
                    if lock.lstat().st_ino != owned_stat.st_ino:
                        raise ScopedCommitError("Owned Git HEAD lock was replaced")
                    lock.unlink()
            except Exception as exc:  # noqa: BLE001 - finish cleanup, preserve operation error
                if cleanup_error is None:
                    cleanup_error = exc
            finally:
                if fd is not None:
                    try:
                        os.close(fd)
                    except OSError as exc:
                        if cleanup_error is None:
                            cleanup_error = exc
            if admin is not None:
                try:
                    shutil.rmtree(admin)
                except Exception as exc:  # noqa: BLE001 - report after other cleanup completes
                    if cleanup_error is None:
                        cleanup_error = exc
        if cleanup_error is not None:
            if operation_error is not None:
                operation_error.add_note("Scoped Git context cleanup or HEAD publication also failed")
                operation_error._scoped_cleanup_failed = True
            else:
                raise cleanup_error
