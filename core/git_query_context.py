"""Fixed metadata Git READ operations using copied private administration.

This is not an atomic snapshot, filesystem sandbox, or binary integrity proof.
Local object alternates are unrestricted read data. No original index, locks,
refs, logs or configuration are written. Worktree queries are outside this scope.
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


class GitQueryError(RuntimeError):
    """Static policy/protocol/checked-Git query diagnostic."""


def _temporary_candidates():
    return (Path(sys.base_prefix) / "tmp", Path("/tmp"))


def _regular(path, *, optional=False):
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        if optional:
            return False
        raise GitQueryError("Required Git query metadata is missing") from None
    if not stat.S_ISREG(mode):
        raise GitQueryError("Unsupported Git query metadata file")
    return True


def _directory(path):
    if not stat.S_ISDIR(path.lstat().st_mode):
        raise GitQueryError("Unsupported Git query metadata directory")


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
            raise GitQueryError("Unsupported Git query reference data")


class _Metadata:
    def __init__(self, root, real, admin):
        self.root, self.real, self.admin = root, real, admin
        parents = dict.fromkeys(str(path.parent) for path in git_execution._git_candidates() if path.is_absolute())
        if not parents:
            raise GitQueryError("No trusted Git query installation directories")
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
        self.head = None

    def _run(self, argv):
        valid = argv in (["git", "rev-parse", "--verify", "HEAD"], ["git", "branch", "-a", "--format=%(HEAD) %(refname:short)"], ["git", "config", "--file", str(self.real / "config"), "--no-includes", "--null", "--list"])
        if isinstance(argv, list):
            valid = valid or (len(argv) == 3 and argv[:2] == ["git", "check-ref-format"] and isinstance(argv[2], str) and argv[2].startswith("refs/heads/"))
            valid = valid or (len(argv) == 4 and argv[:3] == ["git", "show-ref", "--exists"] and isinstance(argv[3], str) and argv[3].startswith("refs/heads/"))
            valid = valid or (len(argv) == 4 and argv[:3] == ["git", "cat-file", "-t"] and isinstance(argv[3], str) and bool(re.fullmatch(r"[0-9a-fA-F]{" + str(self.hash_length) + r"}", argv[3])))
            valid = valid or (len(argv) == 4 and argv[:2] == ["git", "log"] and isinstance(argv[2], str) and bool(re.fullmatch(r"-[0-9]+", argv[2])) and argv[3] in ("--oneline", "--format=%s"))
        if not valid:
            raise GitQueryError("Unsupported fixed Git metadata command")
        return git_execution.run_git(argv, cwd=self.root, env=dict(self.environment), capture_output=True, text=True, timeout=15)

    def _checked(self, argv):
        result = self._run(argv)
        if result.returncode != 0:
            raise GitQueryError("Git metadata command failed")
        if not isinstance(result.stdout, str):
            raise GitQueryError("Git metadata command protocol is invalid")
        return result.stdout

    def configure(self):
        values = {}
        if _regular(self.real / "config", optional=True):
            output = self._checked(["git", "config", "--file", str(self.real / "config"), "--no-includes", "--null", "--list"])
            if output and not output.endswith("\0"):
                raise GitQueryError("Git metadata configuration protocol is invalid")
            for record in output[:-1].split("\0") if output else []:
                if not record:
                    raise GitQueryError("Git metadata configuration protocol is invalid")
                key, separator, value = record.partition("\n")
                if not key or "." not in key:
                    raise GitQueryError("Git metadata configuration protocol is invalid")
                value = value if separator else "true"
                key = key.lower()
                if key.startswith(("include.", "includeif.")):
                    raise GitQueryError("Repository configuration includes are unsupported for metadata queries")
                values[key] = value
        version = values.get("core.repositoryformatversion", "0")
        extensions = {key: value for key, value in values.items() if key.startswith("extensions.")}
        if version not in ("0", "1") or (version == "0" and extensions) or not extensions.keys() <= {"extensions.objectformat", "extensions.refstorage"}:
            raise GitQueryError("Unsupported Git metadata repository format")
        if values.get("core.bare", "false").lower() not in ("false", "no", "off", "0") or "core.worktree" in values:
            raise GitQueryError("Unsupported Git metadata worktree configuration")
        object_format = extensions.get("extensions.objectformat", "sha1")
        if object_format not in ("sha1", "sha256") or extensions.get("extensions.refstorage", "files") != "files":
            raise GitQueryError("Unsupported Git metadata storage format")
        self.hash_length = 64 if object_format == "sha256" else 40
        # Only validated structural scalars enter this generated config.
        config = f"[core]\nrepositoryFormatVersion = {version}\nbare = false\n[gc]\nauto = 0\n[maintenance]\nauto = false\n"
        if object_format == "sha256":
            config += "[extensions]\nobjectFormat = sha256\n"
        (self.admin / "config").write_text(config)

    def validate_head(self):
        with (self.admin / "HEAD").open("rb") as stream:
            raw = stream.read(4097)
        if len(raw) > 4096:
            raise GitQueryError("Git query HEAD exceeds supported size")
        try:
            value = raw.decode("ascii").removesuffix("\n")
        except UnicodeDecodeError:
            raise GitQueryError("Git query HEAD is invalid") from None
        if value.startswith("ref: "):
            target = value[5:]
            if not target.startswith("refs/heads/") or self._run(["git", "check-ref-format", target]).returncode != 0:
                raise GitQueryError("Git query symbolic HEAD is unsupported")
            # A directory at the symbolic leaf is corrupt, not unborn.
            _regular(self.admin / target, optional=True)
            self.branch = target[len("refs/heads/"):]
            existence = self._run(["git", "show-ref", "--exists", target]).returncode
            if existence == 2:
                self.unborn = True
                return
            if existence != 0:
                raise GitQueryError("Git query reference lookup failed")
        elif not re.fullmatch(r"[0-9a-fA-F]{" + str(self.hash_length) + r"}", value):
            raise GitQueryError("Git query detached HEAD is invalid")
        resolved = self._checked(["git", "rev-parse", "--verify", "HEAD"]).strip()
        if not re.fullmatch(r"[0-9a-fA-F]{" + str(self.hash_length) + r"}", resolved) or self._checked(["git", "cat-file", "-t", resolved]).strip() != "commit":
            raise GitQueryError("Git query HEAD is not a local commit")
        self.head = resolved.lower()

    def query(self, operation, n):
        if operation == "is_repo":
            return True
        if operation == "head":
            return self.head
        if operation == "branch":
            return self.branch or "HEAD"
        if operation in ("log", "messages"):
            if self.unborn or n == 0:
                return "No commits yet." if operation == "log" else []
            format_option = "--oneline" if operation == "log" else "--format=%s"
            output = self._checked(["git", "log", f"-{n}", format_option])
            return output.strip() or "No commits yet." if operation == "log" else [line.strip() for line in output.splitlines() if line.strip()]
        if operation == "branches":
            output = self._checked(["git", "branch", "-a", "--format=%(HEAD) %(refname:short)"])
            lines = []
            for line in output.splitlines():
                line = line.strip()
                if line:
                    lines.append(f"[bold green]* {line[2:]}[/bold green]  (current)" if line.startswith("* ") else f"  {line}")
            return "\n".join(lines) or "No branches found."
        raise GitQueryError("Unsupported Git metadata operation")


@contextmanager
def _metadata_context(cwd):
    cwd = Path(os.path.abspath(os.fspath(cwd)))
    _directory(cwd)
    found = discover_worktree(cwd)
    if found is None:
        yield None
        return
    root, real = found
    if root == real:
        raise GitQueryError("Bare Git metadata queries are unsupported")
    _directory(real)
    _directory(real / "objects")
    _directory(real / "refs")
    if _present(real / "commondir") or _present(real / "gitdir"):
        raise GitQueryError("Linked Git metadata queries are unsupported")
    parent = None
    for candidate in _temporary_candidates():
        if not candidate.is_absolute() or candidate == root or root in candidate.parents:
            continue
        # Fixed candidates may have symlinked ancestors, but a symlink entry
        # itself is not an admitted temporary root. Compare real locations.
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
        raise GitQueryError("No usable external Git query temporary directory")
    admin = Path(tempfile.mkdtemp(prefix="codey-query-", dir=parent))
    original_error = None
    try:
        _regular(real / "HEAD")
        # Bound source HEAD copy as well as later parsing.
        with (real / "HEAD").open("rb") as stream:
            value = stream.read(4097)
        if len(value) > 4096:
            raise GitQueryError("Git query HEAD exceeds supported size")
        (admin / "HEAD").write_bytes(value)
        _copy_refs(real / "refs", admin / "refs")
        for name in ("packed-refs", "shallow"):
            if _regular(real / name, optional=True):
                shutil.copyfile(real / name, admin / name)
        if (real / "info").exists() or (real / "info").is_symlink():
            _directory(real / "info")
        grafts = real / "info/grafts"
        if _regular(grafts, optional=True):
            (admin / "info").mkdir()
            shutil.copyfile(grafts, admin / "info/grafts")
        (admin / "config").write_text("[core]\nrepositoryFormatVersion = 0\nbare = false\n")
        context = _Metadata(root, real, admin)
        context.configure()
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
            original_error.add_note("Git metadata query cleanup also failed")
            original_error._git_query_cleanup_failed = True


def metadata_query(cwd, *, action, operation, n=None):
    """One READ audit; unexpected errors retain identity with static audit text."""
    from core.action_gateway import READ, get_action_gateway

    original_error = None
    def execute():
        nonlocal original_error
        try:
            if operation in ("log", "messages") and (not isinstance(n, int) or isinstance(n, bool) or n < 0):
                raise GitQueryError("Git history count must be a nonnegative integer")
            with _metadata_context(cwd or os.getcwd()) as context:
                if context is None:
                    if operation in ("is_repo", "head"):
                        return False if operation == "is_repo" else None
                    raise GitQueryError("Git metadata query requires a repository")
                return context.query(operation, n)
        except Exception as exc:
            original_error = exc
            reason = str(exc) if isinstance(exc, GitQueryError) else "Git metadata query failed"
            if getattr(exc, "_git_query_cleanup_failed", False):
                reason += "; Git metadata query cleanup also failed"
            raise GitQueryError(reason) from exc
    decision = get_action_gateway().gate_exec(authority=READ, action=action, command="checkpoint Git HEAD query" if operation == "head" else "git metadata query", confirm_available=False, execute=execute)
    if original_error is not None:
        raise original_error
    if not decision.allowed:
        raise GitQueryError("Git metadata query was refused")
    return decision.detail["result"]
