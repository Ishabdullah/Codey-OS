#!/usr/bin/env python3
"""
Direct filesystem access for Codey-OS.

Provides a class-based interface for file operations:
- read(path) - Read file content
- write(path, content) - Write file with confirmation
- patch(path, old, new) - Patch file with diff tracking
- exists(path) - Check if path exists
- list_dir(path) - List directory contents

Removes need for JSON tool-call parsing. Agent calls methods directly.
"""

import difflib
import os
from pathlib import Path
from typing import List, Optional, Union

from core.checkpoint import create_checkpoint
from core.checkpoint import is_core_file as _is_core_file
from core.filehistory import snapshot as _snapshot
from core.protected_paths import (TIER_DENY, build_context, credential_read_hit,
                                  first_hit, has_git_component)
from utils.config import CODE_DIR
import utils.config as _config
from utils.logger import info, success


class FilesystemAccessError(Exception):
    """Raised when filesystem access is denied or fails."""


class Filesystem:
    """
    Direct filesystem access for Codey-OS agent.

    Provides safe file operations with:
    - Path validation (no access outside workspace)
    - Workspace checks (prevent writing to protected areas)
    - Diff tracking for patches
    - Error handling with descriptive messages
    - Self-modification opt-in with checkpoint enforcement
    """

    def __init__(self, workspace: Path = None, allow_self_modification: bool = False):
        """
        Initialize filesystem access.

        Args:
            workspace: Root directory for file operations.
                      Defaults to utils.config.WORKSPACE_ROOT (not
                      necessarily os.getcwd()).
            allow_self_modification: If True, allow writes to CODE_DIR with
                                    checkpoint enforcement. Default False.
        """
        self.workspace = workspace or _config.WORKSPACE_ROOT
        self.allow_self_modification = allow_self_modification
        self._last_diff: Optional[str] = None
        self._checkpoint_created: bool = False

    def _require_checkpoint(self, path: Path) -> None:
        """
        Create checkpoint before modifying core files.

        Only creates one checkpoint per session for efficiency.

        Args:
            path: Path being modified

        Raises:
            FilesystemAccessError: If checkpoint creation fails
        """
        if self._checkpoint_created:
            return  # Already created checkpoint this session

        try:
            create_checkpoint(reason=f"Self-modification: {path.name}", files_modified=[str(path)])
            self._checkpoint_created = True
            info(f"Checkpoint created before modifying {path}")
        except Exception as e:
            raise FilesystemAccessError(f"Failed to create checkpoint: {e}")

    def _reject_git_metadata_mutation(self, path: Path) -> None:
        """Deny write/patch/append/restore of any path with a `.git` component
        (NEW-894, widened by G15e): the repository's own `.git`, a nested
        repository's or submodule's, a sibling repository's reached by
        absolute path, and case variants (`.GIT`). Components are measured
        below the workspace / CODE_DIR base (core.protected_paths.
        has_git_component), so a workspace that itself lives under a `.git`
        directory is not denied wholesale. Read access is intentionally
        unaffected -- see read()/exists()/is_file()/is_dir()/list_dir(), which
        still resolve these paths via _validate_path() alone -- inspecting
        `.git/config` has a legitimate introspection use and poses no
        injection risk by itself; only mutation does, since writing new
        credential.helper/core.sshCommand/remote.origin.url lines (or a hook)
        takes effect on Git's next invocation with no executable bit needed.

        Not matched: `.github/`, `.gitignore`, `foo.git.txt`, `a.git/b`.
        """
        if has_git_component(str(path), (self.workspace, CODE_DIR)):
            raise FilesystemAccessError(
                f"Access denied: {path} is inside a Git metadata directory "
                f"and cannot be modified."
            )

    def _check_protected(self, lexical: str, resolved: Path) -> None:
        """Raise for a DENY-tier protected path (core.protected_paths). HIGH
        tier is NOT acted on here: that is classification, done by the caller
        (tools.file_tools.classify_write_action). No flag unlocks DENY,
        including allow_self_modification."""
        self._reject_git_metadata_mutation(resolved)
        self._reject_git_metadata_mutation(Path(lexical))
        ctx = build_context(code_dir=CODE_DIR, workspace_root=self.workspace)
        hit = first_hit((lexical, str(resolved)), ctx)
        if hit is not None and hit.tier == TIER_DENY:
            raise FilesystemAccessError(
                f"Access denied: {resolved} is a protected path ({hit.rule}) "
                f"and cannot be modified by file tools."
            )

    def _lexical_form(self, raw: Union[str, Path]) -> str:
        """Pre-resolve() absolute spelling of `raw` (workspace-joined), so a
        symlink planted AT a protected path is judged by its own name as well
        as by its target."""
        p = Path(raw)
        if not p.is_absolute():
            p = self.workspace / p
        return os.path.normpath(str(p))

    def _validate_for_mutation(self, raw: Union[str, Path]) -> Path:
        """Workspace/CODE_DIR boundary (_validate_path) plus the protected-path
        guard, for the five mutation entry points. Runs before any checkpoint,
        mkdir or snapshot so a denied call has no side effect."""
        resolved = self._validate_path(raw)
        self._check_protected(self._lexical_form(raw), resolved)
        return resolved

    def _validate_for_read(self, raw: Union[str, Path]) -> Path:
        """Workspace/CODE_DIR boundary plus the credential-read guard (G15e
        Unit C, Q7b): file tools must not return ~/.ssh keys, .netrc,
        .git-credentials, the age key and state-dir secrets, shell history or
        /proc/<pid>/* even when the workspace contains them. Only the agent-
        facing read path (tool_read_file, patch_file's pre-read) calls this;
        operator code (daemon_config, setup_dr_key, backup_secrets, the
        dashboard) reads with plain IO and is unaffected. Fail closed: if the
        credential check itself errors the read is refused."""
        resolved = self._validate_path(raw)
        try:
            rule = credential_read_hit((self._lexical_form(raw), str(resolved)))
        except Exception as e:
            raise FilesystemAccessError(
                f"Access denied: could not evaluate credential guard for {resolved}: {e}"
            )
        if rule is not None:
            raise FilesystemAccessError(
                f"Access denied: {resolved} is a credential file ({rule}) and "
                f"cannot be read by file tools."
            )
        return resolved

    def _validate_path(self, path: Union[str, Path]) -> Path:
        """
        Validate and resolve path.

        Ensures path is within workspace. CODE_DIR access requires
        explicit self-modification opt-in.

        Args:
            path: Path to validate

        Returns:
            Resolved Path object

        Raises:
            FilesystemAccessError: If path is invalid or outside workspace
        """
        if isinstance(path, str):
            path = Path(path)

        # Resolve to absolute path
        if not path.is_absolute():
            path = self.workspace / path

        path = path.resolve()

        # Check if path is within workspace
        try:
            path.relative_to(self.workspace)
            return path
        except ValueError:
            pass

        # Path is outside workspace - check if it's CODE_DIR (self-modification)
        try:
            path.relative_to(CODE_DIR)
            # This is a CODE_DIR file - check if self-modification is enabled
            if not self.allow_self_modification:
                raise FilesystemAccessError(
                    f"Access denied: {path} is outside workspace. "
                    f"Enable self-modification with --allow-self-mod flag or ALLOW_SELF_MOD=1"
                )
            return path
        except ValueError:
            pass

        # Path is outside both workspace and CODE_DIR
        raise FilesystemAccessError(
            f"Access denied: {path} is outside workspace ({self.workspace})"
        )

    def read(self, path: Union[str, Path]) -> str:
        """
        Read file content.

        Args:
            path: Path to file (relative to workspace or absolute)

        Returns:
            File content as string

        Raises:
            FilesystemAccessError: If file cannot be read
        """
        MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB limit
        try:
            path = self._validate_for_read(path)

            if not path.exists():
                raise FilesystemAccessError(f"File not found: {path}")

            if not path.is_file():
                raise FilesystemAccessError(f"Not a file: {path}")

            file_size = path.stat().st_size
            if file_size > MAX_FILE_SIZE:
                raise FilesystemAccessError(
                    f"File too large ({file_size / 1024 / 1024:.1f}MB > {MAX_FILE_SIZE / 1024 / 1024}MB limit)"
                )

            content = path.read_text(encoding="utf-8")
            try:
                rel = path.relative_to(self.workspace)
            except ValueError:
                rel = path
            info(f"Read {rel} ({len(content)} chars)")
            return content

        except FilesystemAccessError:
            raise
        except Exception as e:
            raise FilesystemAccessError(f"Failed to read {path}: {e}")

    def write(self, path: Union[str, Path], content: str) -> str:
        """
        Write file content.

        Creates parent directories if they don't exist.
        Enforces checkpoint for core file modifications.

        Args:
            path: Path to file (relative to workspace or absolute)
            content: Content to write

        Returns:
            Success message with file path

        Raises:
            FilesystemAccessError: If file cannot be written
        """
        try:
            path = self._validate_for_mutation(path)

            # Check if modifying Codey's own code (requires checkpoint)
            is_core = _is_core_file(str(path))
            if is_core:
                info(f"Writing to core Codey file: {path}")
                # Enforce checkpoint before core file writes
                self._require_checkpoint(path)

            # Create parent directories
            path.parent.mkdir(parents=True, exist_ok=True)

            # Snapshot existing file so /undo works for write_file too
            if path.exists():
                _snapshot(str(path))

            # Write content
            path.write_text(content, encoding="utf-8")

            try:
                rel = path.relative_to(self.workspace)
            except ValueError:
                rel = path
            msg = f"Written {rel}"
            success(msg)
            return msg

        except FilesystemAccessError:
            raise
        except Exception as e:
            raise FilesystemAccessError(f"Failed to write {path}: {e}")

    def restore(self, path: Union[str, Path], content: str) -> str:
        """Overwrite an existing file with previously snapshotted content.

        Used only by /undo (WP2.1 slice 14b). Same validation, Git-metadata
        denial and core-file checkpointing as write(), but deliberately takes
        NO snapshot (undo maintains its own pre-undo/redo history entry; a
        snapshot here would double it) and creates no parent directories.
        The caller owns authority/confirmation.
        """
        try:
            path = self._validate_for_mutation(path)
            if _is_core_file(str(path)):
                self._require_checkpoint(path)
            path.write_text(content, encoding="utf-8")
            return f"Restored {path}"
        except FilesystemAccessError:
            raise
        except Exception as e:
            raise FilesystemAccessError(f"Failed to restore {path}: {e}")

    def make_parent_dirs(self, path: Union[str, Path]) -> Path:
        """Create a validated target's parents for recovery before a write.

        The recovery caller owns authority/confirmation. Validation, Git
        metadata denial and core-file checkpointing match write().
        """
        try:
            raw = path
            path = self._validate_for_mutation(raw)
            # The parent is checked too: creating a protected directory
            # (e.g. a shadow-named child of a PATH dir) is itself the plant.
            self._check_protected(
                os.path.dirname(self._lexical_form(raw)), path.parent
            )
            if _is_core_file(str(path)):
                self._require_checkpoint(path)
            path.parent.mkdir(parents=True, exist_ok=True)
            return path.parent
        except FilesystemAccessError:
            raise
        except Exception as exc:
            raise FilesystemAccessError(f"Failed to create parent directory: {exc}") from exc

    def patch(self, path: Union[str, Path], old_str: str, new_str: str) -> str:
        """
        Patch file content (replace old_str with new_str).

        Enforces checkpoint for core file modifications.

        Args:
            path: Path to file
            old_str: String to find and replace
            new_str: Replacement string

        Returns:
            Diff of changes made

        Raises:
            FilesystemAccessError: If patch cannot be applied
        """
        try:
            path = self._validate_for_mutation(path)

            if not path.exists():
                raise FilesystemAccessError(f"File not found: {path}")

            # Check if modifying core files (requires checkpoint)
            is_core = _is_core_file(str(path))
            if is_core:
                self._require_checkpoint(path)

            # Read current content
            content = path.read_text(encoding="utf-8")

            # Find and replace
            if old_str not in content:
                raise FilesystemAccessError(f"Could not find specified string in {path}")

            new_content = content.replace(old_str, new_str, 1)

            # Generate diff
            diff = self._generate_diff(
                path.name, content.splitlines(keepends=True), new_content.splitlines(keepends=True)
            )
            self._last_diff = diff

            # Write new content
            path.write_text(new_content, encoding="utf-8")

            try:
                rel = path.relative_to(self.workspace)
            except ValueError:
                rel = path
            msg = f"Patched {rel}"
            success(msg)
            return diff

        except FilesystemAccessError:
            raise
        except Exception as e:
            raise FilesystemAccessError(f"Failed to patch {path}: {e}")

    def append(self, path: Union[str, Path], content: str) -> str:
        """
        Append content to file.

        Enforces checkpoint for core file modifications.

        Args:
            path: Path to file
            content: Content to append

        Returns:
            Success message

        Raises:
            FilesystemAccessError: If append fails
        """
        try:
            path = self._validate_for_mutation(path)

            # Check if modifying core files (requires checkpoint)
            is_core = _is_core_file(str(path))
            if is_core:
                self._require_checkpoint(path)

            # Create if doesn't exist
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
                try:
                    rel = path.relative_to(self.workspace)
                except ValueError:
                    rel = path
                return f"Created {rel}"

            # Append to existing file
            with open(path, "a", encoding="utf-8") as f:
                f.write(content)

            try:
                rel = path.relative_to(self.workspace)
            except ValueError:
                rel = path
            msg = f"Appended to {rel}"
            success(msg)
            return msg

        except FilesystemAccessError:
            raise
        except Exception as e:
            raise FilesystemAccessError(f"Failed to append to {path}: {e}")

    def exists(self, path: Union[str, Path]) -> bool:
        """
        Check if path exists.

        Args:
            path: Path to check

        Returns:
            True if path exists, False otherwise
        """
        try:
            path = self._validate_path(path)
            return path.exists()
        except FilesystemAccessError:
            return False

    def is_file(self, path: Union[str, Path]) -> bool:
        """
        Check if path is a file.

        Args:
            path: Path to check

        Returns:
            True if path is a file, False otherwise
        """
        try:
            path = self._validate_path(path)
            return path.is_file()
        except FilesystemAccessError:
            return False

    def is_dir(self, path: Union[str, Path]) -> bool:
        """
        Check if path is a directory.

        Args:
            path: Path to check

        Returns:
            True if path is a directory, False otherwise
        """
        try:
            path = self._validate_path(path)
            return path.is_dir()
        except FilesystemAccessError:
            return False

    def list_dir(self, path: Union[str, Path] = ".") -> List[str]:
        """
        List directory contents.

        Args:
            path: Directory path (default: workspace root)

        Returns:
            List of file/directory names

        Raises:
            FilesystemAccessError: If directory cannot be listed
        """
        try:
            path = self._validate_path(path)

            if not path.is_dir():
                raise FilesystemAccessError(f"Not a directory: {path}")

            entries = [e.name for e in path.iterdir()]
            entries.sort()

            try:
                rel = path.relative_to(self.workspace)
            except ValueError:
                rel = path
            info(f"Listed {rel} ({len(entries)} entries)")
            return entries

        except FilesystemAccessError:
            raise
        except Exception as e:
            raise FilesystemAccessError(f"Failed to list {path}: {e}")

    def _generate_diff(self, filename: str, old_lines: List[str], new_lines: List[str]) -> str:
        """Generate unified diff between old and new content."""
        diff = difflib.unified_diff(
            old_lines, new_lines, fromfile=f"a/{filename}", tofile=f"b/{filename}", n=3
        )
        return "".join(diff)

    def get_last_diff(self) -> Optional[str]:
        """Get the diff from the last patch operation."""
        return self._last_diff


# Global filesystem instance
_filesystem: Optional[Filesystem] = None


def get_filesystem(workspace: Path = None, allow_self_modification: bool = False) -> Filesystem:
    """Get the global filesystem instance."""
    global _filesystem
    if _filesystem is None or _filesystem.allow_self_modification != allow_self_modification:
        _filesystem = Filesystem(workspace, allow_self_modification)
    return _filesystem


def reset_filesystem():
    """Reset the global filesystem instance.

    Used in tests, and also in production by main.py's /cwd handler so
    the next tool call picks up the new workspace.
    """
    global _filesystem
    if _filesystem:
        _filesystem = None
