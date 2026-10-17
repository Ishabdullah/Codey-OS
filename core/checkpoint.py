#!/usr/bin/env python3
"""
Checkpoint system for Codey-OS self-modification.

Before modifying core files, creates a checkpoint:
- Git commit with checkpoint message
- Full file backup in ~/.codeyOS/checkpoints/
- SQLite record for tracking

Supports rollback to any checkpoint.
"""

import json
import re
import shutil
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional

from core.git_commit_context import discover_worktree, isolated_scoped_commit_context
from core.git_mutation_context import GitMutationError, isolated_mutation_context
from core.state import get_state_store
from utils.config import CHECKPOINT_DIR, CODE_DIR
from utils.logger import info, success, warning

# Checkpoint directory
CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)

# Checkpoint-BACKUP scope: only the top-level directory component of each
# pattern is used (create_checkpoint backs up every *.py under it,
# recursively). Deliberately separate from CORE_CLASSIFICATION_ROOTS below
# so widening what is classified as core never silently changes what is
# backed up (NEW-951 / WP2.1 slice 14a).
CORE_PATTERNS = [
    "core/*.py",
    "tools/*.py",
    "utils/*.py",
    "prompts/*.py",
]

# Classification scope for is_core_file(): any *.py at any depth under
# these CODE_DIR roots is a Codey-OS core file (NEW-951). WP2.1 slice
# 14a-ext (Ish fork 1, 2026-10-17) adds ccos/plugins (the plugin tree is
# auto-discovered and executed) and bench (promotion-gate integrity). This
# is classification only: CORE_PATTERNS (backup scope) is unchanged.
CORE_CLASSIFICATION_ROOTS = (
    "core",
    "tools",
    "utils",
    "prompts",
    "ccos/plugins",
    "bench",
)


@dataclass
class Checkpoint:
    """Represents a checkpoint."""

    id: str
    created_at: int
    reason: str
    files_modified: List[str]
    git_commit_hash: Optional[str]


def is_core_file(file_path: str) -> bool:
    """Check if a file is a Codey-OS file that needs checkpointing."""
    path = Path(file_path).resolve()

    # Only *.py files at any depth under the specific core directories
    # (core/, tools/, utils/, prompts/) count — NOT the entire repo
    # (CODE_DIR is the repo root). Recursive since NEW-951; the old
    # Path.match("<root>/*.py") only matched direct children.
    for root in CORE_CLASSIFICATION_ROOTS:
        base_dir = CODE_DIR / root
        try:
            path.relative_to(base_dir)
        except ValueError:
            continue
        if path.name.endswith(".py"):
            return True

    return False


def create_checkpoint(reason: str, files_modified: List[str] = None) -> str:
    """
    Create a checkpoint before self-modification.

    Args:
        reason: Reason for checkpoint (e.g., "Adding new feature")
        files_modified: List of files that will be modified

    Returns:
        Checkpoint ID (timestamp with a random suffix -- see NEW-863:
        a bare `str(int(time.time()))` let two checkpoints created in
        the same wall-clock second silently overwrite each other's
        backup files via `exist_ok=True`'s directory reuse)
    """
    checkpoint_id = f"{int(time.time())}-{uuid.uuid4().hex[:8]}"
    backup_dir = CHECKPOINT_DIR / checkpoint_id
    # exist_ok=False: a genuine collision (the id above is already
    # vanishingly unlikely to repeat) must raise loudly here rather than
    # silently reuse another checkpoint's directory and let backups
    # overwrite each other (NEW-863).
    backup_dir.mkdir(parents=True, exist_ok=False)

    info(f"Checkpoint: creating '{checkpoint_id}' - {reason}")

    # Backup core files
    backed_up = []

    # Backup all Python files in core directories
    for pattern in CORE_PATTERNS:
        base_path = CODE_DIR / pattern.split("/")[0]
        if base_path.exists():
            for py_file in base_path.rglob("*.py"):
                try:
                    rel_path = py_file.relative_to(CODE_DIR)
                    dest = backup_dir / rel_path
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(py_file, dest)
                    backed_up.append(str(rel_path))
                except Exception as e:
                    warning(f"Checkpoint: could not backup {py_file}: {e}")

    # Also backup specific important files
    important_files = [
        CODE_DIR / "main.py",
        CODE_DIR / "codey",
        CODE_DIR / "codeyOS",
    ]
    for f in important_files:
        if f.exists():
            try:
                dest = backup_dir / f.name
                shutil.copy2(f, dest)
                backed_up.append(f.name)
            except Exception as e:
                warning(f"Checkpoint: could not backup {f}: {e}")

    # Create git commit
    git_hash = _create_git_commit(reason, files_modified)

    # Record in database
    state = get_state_store()
    state.execute(
        """
        INSERT INTO checkpoints (id, created_at, reason, files_modified, git_commit_hash)
        VALUES (?, ?, ?, ?, ?)
    """,
        (checkpoint_id, int(time.time()), reason, json.dumps(files_modified or []), git_hash),
    )

    success(f"Checkpoint '{checkpoint_id}' created ({len(backed_up)} files backed up)")

    return checkpoint_id


def _create_git_commit(reason: str, files_modified: List[str] = None) -> Optional[str]:
    """Commit literal triggering paths through ACT; directories select subtrees.

    Nonempty mutations use a private administrative/configuration context
    inside ACT. No-path calls use one isolated READ query; scoped clean attempts return the existing HEAD.
    Directories, including '.', intentionally select their subtrees; this is
    no single-file or workspace containment guarantee. Staging/commit/hash lookup
    is not atomic: failure can leave staging or an already-created commit.
    """
    try:
        if not files_modified:
            from core.git_query_context import metadata_query

            try:
                return metadata_query(CODE_DIR, action="checkpoint.git_head", operation="head")
            except Exception:  # noqa: BLE001 - query failures abort dependent work with static diagnostics
                warning("Checkpoint: Git metadata query failed")
                return None
        if discover_worktree(CODE_DIR) is None:
            return None

        # Runtime import avoids the gateway -> Filesystem -> checkpoint cycle.
        from core.action_gateway import ACT, get_action_gateway

        def execute():
            try:
                paths = list(files_modified)
                with isolated_scoped_commit_context(CODE_DIR, paths) as runner:
                    result = runner(
                        ["git", "--literal-pathspecs", "add", "--"] + paths, cwd=CODE_DIR, capture_output=True, text=True
                    )
                    if result.returncode != 0:
                        raise RuntimeError(f"git add failed: {result.stderr.strip()}")

                    result = runner(
                        ["git", "--literal-pathspecs", "diff", "--cached", "--quiet", "--"] + paths,
                        cwd=CODE_DIR, capture_output=True, text=True,
                    )
                    if result.returncode not in (0, 1):
                        raise RuntimeError(f"git diff failed: {result.stderr.strip()}")
                    if result.returncode == 1:
                        result = runner(
                            ["git", "--literal-pathspecs", "commit", "-m", f"Codey checkpoint: {reason}", "--"] + paths,
                            cwd=CODE_DIR, capture_output=True, text=True,
                        )
                        if result.returncode != 0:
                            raise RuntimeError(f"git commit failed: {result.stderr.strip()}")

                    result = runner(
                        ["git", "rev-parse", "HEAD"], cwd=CODE_DIR, capture_output=True, text=True
                    )
                    if result.returncode != 0:
                        raise RuntimeError(f"git rev-parse HEAD failed: {result.stderr.strip()}")
                    return result.stdout.strip()
            except Exception as exc:
                # Include additional cleanup failure in audit without hiding the operation.
                if getattr(exc, "_scoped_cleanup_failed", False):
                    raise RuntimeError(f"{exc}; scoped Git context cleanup or publication also failed") from exc
                raise

        decision = get_action_gateway().gate_exec(
            authority=ACT,
            action="checkpoint.create_git_commit",
            command="checkpoint local git commit attempt",
            confirm_available=False,
            execute=execute,
        )
        if decision.allowed:
            return decision.detail["result"]
        warning(f"Checkpoint: git commit {decision.outcome}: {decision.reason}")
        return None

    except Exception as e:
        warning(f"Checkpoint: git commit failed: {e}")
        return None


def _resolve_checkpoint_dir(checkpoint_id: str) -> Path:
    """Validate checkpoint_id's shape and resolve its backup directory,
    without requiring the directory to exist.

    Shared by `_rollback_files()` (which additionally requires the
    directory to exist -- there is nothing to restore from otherwise)
    and `prune_checkpoints()` (which treats a missing directory as
    already-pruned and simply skips the `rmtree`), so both
    deletion-adjacent paths get identical containment guarantees
    instead of two independently-maintained copies of this guard.
    """
    if (
        not isinstance(checkpoint_id, str)
        or not checkpoint_id
        or checkpoint_id in (".", "..")
        or any(character in checkpoint_id for character in ("/", "\\", "\0"))
        or Path(checkpoint_id).is_absolute()
    ):
        raise ValueError("Invalid checkpoint ID")
    if CHECKPOINT_DIR.is_symlink():
        raise ValueError("Checkpoint directory missing or unsafe")
    backup_dir = CHECKPOINT_DIR / checkpoint_id
    if backup_dir.is_symlink():
        raise ValueError("Checkpoint directory missing or unsafe")
    if backup_dir.exists():
        backup_dir.resolve().relative_to(CHECKPOINT_DIR.resolve())
    return backup_dir


def _rollback_files(checkpoint_id: str):
    """Validate the complete producer-scoped backup set before any writes."""
    backup_dir = _resolve_checkpoint_dir(checkpoint_id)
    if not backup_dir.is_dir():
        raise ValueError("Checkpoint directory missing or unsafe")
    if CODE_DIR.is_symlink() or not CODE_DIR.is_dir():
        raise ValueError("Restore root missing or unsafe")
    code_root = CODE_DIR.resolve()
    files = []
    pending = [backup_dir]
    entries = []
    while pending:
        for entry in sorted(pending.pop().iterdir()):
            if entry.is_symlink():
                raise ValueError("Checkpoint contains a symlink")
            entries.append(entry)
            if entry.is_dir():
                pending.append(entry)
    for backup_file in sorted(entries):
        relative = backup_file.relative_to(backup_dir)
        if ".git" in relative.parts:
            raise ValueError("Checkpoint cannot restore Git metadata")
        if backup_file.is_symlink():
            raise ValueError("Checkpoint contains a symlink")
        if backup_file.is_dir():
            if relative.parts[0] not in ("core", "tools", "utils", "prompts"):
                raise ValueError("Checkpoint directory outside supported restore scope")
            continue
        if not backup_file.is_file():
            raise ValueError("Checkpoint contains a nonregular file")
        backup_file.resolve().relative_to(backup_dir.resolve())
        relative = backup_file.relative_to(backup_dir)
        producer_file = (
            len(relative.parts) > 1
            and relative.parts[0] in ("core", "tools", "utils", "prompts")
            and relative.suffix == ".py"
        ) or relative.as_posix() in ("main.py", "codey", "codeyOS")
        if not producer_file:
            raise ValueError("Checkpoint file outside supported restore scope")
        destination = CODE_DIR / relative
        destination.resolve().relative_to(code_root)
        current = CODE_DIR
        for component in relative.parts:
            current = current / component
            if current.is_symlink():
                raise ValueError("Restore destination contains a symlink")
            if current.exists():
                if current == destination:
                    if not current.is_file():
                        raise ValueError("Restore destination is not a regular file")
                elif not current.is_dir():
                    raise ValueError("Restore destination ancestor is not a directory")
        files.append((backup_file, destination))
    return files


def _copy_backup_files(files):
    for backup_file, destination in files:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup_file, destination)


def rollback(checkpoint_id: str, *, confirm: Optional[Callable[[], bool]] = None) -> bool:
    """Restore an authorized checkpoint; default/no approval performs no work.

    The trusted confirmation callback must disclose that a saved commit
    restores the full versioned repository and detaches HEAD, not models.
    Preflight restricts backup destinations but cannot prove completeness
    or identity, prevent concurrent path replacement, or make restoration
    atomic. Copied backup bytes can make an older-commit checkout refuse
    because they differ from the current index; no force is applied. Failed
    attempts may retain partial file/Git effects.
    """
    # Runtime import avoids the gateway -> Filesystem -> checkpoint cycle.
    from core.action_gateway import HIGH_IMPACT, get_action_gateway

    def execute():
        files = _rollback_files(checkpoint_id)
        state = get_state_store()
        checkpoint_data = state.get_checkpoint(checkpoint_id)
        git_hash = checkpoint_data.get("git_commit_hash") if checkpoint_data else None
        cleanup_extra = ""
        if git_hash is not None:
            if not isinstance(git_hash, str) or re.fullmatch(r"(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})", git_hash) is None:
                raise ValueError("Checkpoint commit ID is malformed")
            try:
                with isolated_mutation_context(CODE_DIR) as context:
                    if context.cat_file_type(git_hash) != "commit":
                        raise ValueError("Checkpoint commit ID is not an existing commit object")
                    context.reject_attribute(context.changed_paths(git_hash), "filter", source=git_hash)
                    _copy_backup_files(files)
                    result = context.run(
                        ["git", "checkout", "--detach", git_hash, "--"],
                        cwd=CODE_DIR, capture_output=True, text=True,
                    )
                    if result.returncode != 0:
                        raise RuntimeError(f"Rollback git checkout failed: {result.stderr.strip()}")
                if getattr(context, "_mutation_cleanup_failed", False):
                    cleanup_extra = "; Git mutation context cleanup also failed"
            except GitMutationError as exc:
                extra = "; Git mutation context cleanup also failed" if getattr(exc, "_mutation_cleanup_failed", False) else ""
                raise RuntimeError(f"{exc}{extra}") from exc
        else:
            _copy_backup_files(files)

        state.log_action("rollback", f"Restored from checkpoint {checkpoint_id}")
        return f"restored {len(files)} files{cleanup_extra}"

    decision = get_action_gateway().gate_exec(
        authority=HIGH_IMPACT,
        action="checkpoint.rollback",
        command="checkpoint restore attempt",
        confirm_available=callable(confirm),
        confirm=confirm,
        execute=execute,
    )
    if not decision.allowed:
        warning(f"Rollback {decision.outcome}: {decision.reason}")
        return False
    success(f"Rollback: {decision.detail['result']} from checkpoint '{checkpoint_id}'")
    return True


def list_checkpoints(limit: int = 10) -> List[Dict]:
    """
    List recent checkpoints.

    Args:
        limit: Maximum number of checkpoints to return

    Returns:
        List of checkpoint info dicts
    """
    state = get_state_store()
    checkpoints = state.get_checkpoints(limit)

    result = []
    for cp in checkpoints:
        result.append(
            {
                "id": cp["id"],
                "created_at": cp["created_at"],
                "reason": cp["reason"],
                "git_commit": cp["git_commit_hash"][:8] if cp["git_commit_hash"] else None,
            }
        )

    return result


def get_latest_checkpoint() -> Optional[str]:
    """Get the most recent checkpoint ID."""
    state = get_state_store()
    checkpoints = state.get_checkpoints(1)
    return checkpoints[0]["id"] if checkpoints else None


def prune_checkpoints(keep_count: int = 5, *, confirm: Optional[Callable[[], bool]] = None) -> int:
    """
    Remove old checkpoints, keeping only the most recent ones.

    Mediated as HIGH_IMPACT, not ACT: this permanently deletes backup
    data (the module docstring's own "delete important data" example),
    and it is the system's only rollback safety net for the checkpoints
    it removes -- unlike `_create_git_commit`'s ACT-gated git commit
    (recoverable from reflog/history), a pruned checkpoint's file
    backups are gone for good. Per the gateway's HIGH_IMPACT fail-closed
    rule, calling this with no confirmation path available (the default,
    `confirm=None`) refuses and does no work -- it is deliberately inert
    until a real caller is wired with an explicit confirmation path
    (out of scope for this change; see WP2.1 group 11).

    Args:
        keep_count: Number of recent checkpoints to keep. Must be a
            positive int -- 0 would erase every checkpoint (including
            the newest), and a negative value would slice the
            candidate list from the wrong end, pruning the newest
            checkpoints instead of the oldest.
        confirm: optional human confirmation callback, forwarded to the
            Action Gateway exactly like `rollback()`'s.

    Returns:
        Number of checkpoints actually removed (0 if refused or if
        there was nothing to prune).
    """
    if isinstance(keep_count, bool) or not isinstance(keep_count, int) or keep_count < 1:
        raise ValueError("keep_count must be a positive integer")

    from core.action_gateway import HIGH_IMPACT, get_action_gateway

    # Code-reviewer finding (WP2.1 group 11, round 1): a mid-loop rmtree
    # failure on a LATER candidate must not erase the fact that EARLIER
    # candidates were already genuinely pruned. `execute()` raising
    # never returns its local `removed` count to the caller -- the
    # exception propagates straight through gate_exec() to
    # OUTCOME_FAILED, and the old code then unconditionally returned 0,
    # contradicting the docstring's "number actually removed" contract
    # and this function's own "partial effects retained" design (same
    # as rollback()'s). `pruned` is captured in the enclosing scope and
    # incremented as each candidate's DB row + directory are actually
    # removed, so it reflects true progress regardless of how execute()
    # ultimately returns or raises.
    pruned = [0]

    def execute():
        state = get_state_store()
        checkpoints = state.get_checkpoints(None)  # genuinely all rows, not a 100-row cap

        if len(checkpoints) <= keep_count:
            return 0

        to_remove = checkpoints[keep_count:]

        # Validate the complete set before any writes (mirrors
        # _rollback_files's own discipline): if any candidate's ID is
        # unsafe, abort entirely rather than partially pruning the
        # trustworthy ones first.
        resolved = [(cp["id"], _resolve_checkpoint_dir(cp["id"])) for cp in to_remove]

        for checkpoint_id, backup_dir in resolved:
            # Delete the DB row before rmtree: a mid-rmtree failure then
            # leaves, at worst, a harmless orphan directory on disk --
            # never a DB row that still claims a backup exists after
            # it has been partially deleted (mirrors rollback()'s
            # ordering discipline, slice 32, for the same reason).
            state.delete_checkpoint(checkpoint_id)
            if backup_dir.exists():
                shutil.rmtree(backup_dir)
            pruned[0] += 1
            info(f"Checkpoint: pruned '{checkpoint_id}'")

        success(f"Checkpoint: pruned {pruned[0]} old checkpoints")
        return pruned[0]

    decision = get_action_gateway().gate_exec(
        authority=HIGH_IMPACT,
        action="checkpoint.prune",
        command="checkpoint prune attempt",
        confirm_available=callable(confirm),
        confirm=confirm,
        execute=execute,
    )
    if not decision.allowed:
        warning(f"Checkpoint prune {decision.outcome}: {decision.reason}")
        # pruned[0] reflects real progress even on OUTCOME_FAILED (a
        # later candidate's rmtree raised after earlier ones already
        # succeeded) or OUTCOME_REFUSED (always 0, execute() never ran).
        return pruned[0]
    return decision.detail["result"]


# State store extensions for checkpoints
def _extend_state_schema():
    """Add checkpoints table to state schema."""
    state = get_state_store()
    state.execute("""
        CREATE TABLE IF NOT EXISTS checkpoints (
            id TEXT PRIMARY KEY,
            created_at INTEGER NOT NULL,
            reason TEXT NOT NULL,
            files_modified TEXT,
            git_commit_hash TEXT
        )
    """)


# Initialize on import
_extend_state_schema()
