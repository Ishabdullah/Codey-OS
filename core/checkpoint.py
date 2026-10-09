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
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional

from core.git_execution import run_git
from core.state import get_state_store
from utils.config import CHECKPOINT_DIR, CODE_DIR
from utils.logger import info, success, warning

# Checkpoint directory
CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)

# Core files that should be checkpointed before modification
CORE_PATTERNS = [
    "core/*.py",
    "tools/*.py",
    "utils/*.py",
    "prompts/*.py",
]


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

    # Only files under the specific core directories (core/, tools/, utils/,
    # prompts/) count — NOT the entire repo (CODE_DIR is the repo root).
    for pattern in CORE_PATTERNS:
        base_dir = CODE_DIR / pattern.split("/")[0]
        try:
            path.relative_to(base_dir)
        except ValueError:
            continue
        if path.match(pattern):
            return True

    return False


def create_checkpoint(reason: str, files_modified: List[str] = None) -> str:
    """
    Create a checkpoint before self-modification.

    Args:
        reason: Reason for checkpoint (e.g., "Adding new feature")
        files_modified: List of files that will be modified

    Returns:
        Checkpoint ID (timestamp)
    """
    checkpoint_id = str(int(time.time()))
    backup_dir = CHECKPOINT_DIR / checkpoint_id
    backup_dir.mkdir(parents=True, exist_ok=True)

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
    """Commit only triggering paths through ACT mediation.

    No-path calls only read HEAD without a mutation audit; scoped clean
    attempts return the existing HEAD. Staging/commit/hash lookup are not
    atomic: failure can leave staged changes or an already-created commit.
    """
    try:
        # Check if we're in a git repo
        result = run_git(
            ["git", "rev-parse", "--git-dir"], cwd=CODE_DIR, capture_output=True, text=True
        )
        if result.returncode != 0:
            return None

        if not files_modified:
            # Nothing specific to stage — no-op, just report current HEAD.
            result = run_git(
                ["git", "rev-parse", "HEAD"], cwd=CODE_DIR, capture_output=True, text=True
            )
            return result.stdout.strip() if result.returncode == 0 else None

        # Runtime import avoids the gateway -> Filesystem -> checkpoint cycle.
        from core.action_gateway import ACT, get_action_gateway

        def execute():
            paths = list(files_modified)
            result = run_git(
                ["git", "add", "--"] + paths, cwd=CODE_DIR, capture_output=True, text=True
            )
            if result.returncode != 0:
                raise RuntimeError(f"git add failed: {result.stderr.strip()}")

            result = run_git(
                ["git", "diff", "--cached", "--quiet", "--"] + paths,
                cwd=CODE_DIR, capture_output=True, text=True,
            )
            if result.returncode not in (0, 1):
                raise RuntimeError(f"git diff failed: {result.stderr.strip()}")
            if result.returncode == 1:
                result = run_git(
                    ["git", "commit", "-m", f"Codey checkpoint: {reason}", "--"] + paths,
                    cwd=CODE_DIR, capture_output=True, text=True,
                )
                if result.returncode != 0:
                    raise RuntimeError(f"git commit failed: {result.stderr.strip()}")

            result = run_git(
                ["git", "rev-parse", "HEAD"], cwd=CODE_DIR, capture_output=True, text=True
            )
            if result.returncode != 0:
                raise RuntimeError(f"git rev-parse HEAD failed: {result.stderr.strip()}")
            return result.stdout.strip()

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


def _rollback_files(checkpoint_id: str):
    """Validate the complete producer-scoped backup set before any writes."""
    if (
        not isinstance(checkpoint_id, str)
        or not checkpoint_id
        or checkpoint_id in (".", "..")
        or any(character in checkpoint_id for character in ("/", "\\", "\0"))
        or Path(checkpoint_id).is_absolute()
    ):
        raise ValueError("Invalid checkpoint ID")
    backup_dir = CHECKPOINT_DIR / checkpoint_id
    if CHECKPOINT_DIR.is_symlink() or backup_dir.is_symlink() or not backup_dir.is_dir():
        raise ValueError("Checkpoint directory missing or unsafe")
    backup_dir.resolve().relative_to(CHECKPOINT_DIR.resolve())
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
        if git_hash is not None:
            if not isinstance(git_hash, str) or re.fullmatch(r"(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})", git_hash) is None:
                raise ValueError("Checkpoint commit ID is malformed")
            result = run_git(
                ["git", "cat-file", "-t", git_hash], cwd=CODE_DIR, capture_output=True, text=True
            )
            if result.returncode != 0 or result.stdout.strip() != "commit":
                raise ValueError("Checkpoint commit ID is not an existing commit object")

        for backup_file, destination in files:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup_file, destination)

        if git_hash is not None:
            result = run_git(
                ["git", "checkout", "--detach", git_hash, "--"],
                cwd=CODE_DIR, capture_output=True, text=True,
            )
            if result.returncode != 0:
                raise RuntimeError(f"Rollback git checkout failed: {result.stderr.strip()}")

        state.log_action("rollback", f"Restored from checkpoint {checkpoint_id}")
        return f"restored {len(files)} files"

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


def prune_checkpoints(keep_count: int = 5):
    """
    Remove old checkpoints, keeping only the most recent ones.

    Args:
        keep_count: Number of recent checkpoints to keep
    """
    state = get_state_store()
    checkpoints = state.get_checkpoints(100)  # Get all

    if len(checkpoints) <= keep_count:
        return

    to_remove = checkpoints[keep_count:]

    for cp in to_remove:
        checkpoint_id = cp["id"]
        backup_dir = CHECKPOINT_DIR / checkpoint_id

        # Remove backup directory
        if backup_dir.exists():
            shutil.rmtree(backup_dir)

        # Remove from database
        state.delete_checkpoint(checkpoint_id)

        info(f"Checkpoint: pruned '{checkpoint_id}'")

    success(f"Checkpoint: pruned {len(to_remove)} old checkpoints")


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
