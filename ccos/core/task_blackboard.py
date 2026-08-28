"""
TaskBlackboard — Ephemeral scoped task-context storage for CCOS.

Per Track A / Phase A2 Item 7.5:
Provides durable, scoped cross-step handoffs and context checkpoints
without repurposing ccos_memory or dumping raw conversational contexts.
Uses SQLite with WAL mode, foreign keys, and thread-safe locking.
"""

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from ccos.core.task_context import TaskContext

DEFAULT_BLACKBOARD_DB = str(Path(__file__).parent.parent / "data" / "task_blackboard.db")


class TaskBlackboard:
    """
    Thread-safe SQLite-backed task blackboard for in-flight state and checkpoints.
    """

    def __init__(self, db_path: Optional[str] = None):
        self._path = db_path or DEFAULT_BLACKBOARD_DB
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL;")
            cur.execute("PRAGMA foreign_keys=ON;")
            cur.executescript("""
                CREATE TABLE IF NOT EXISTS task_sessions (
                    task_id TEXT PRIMARY KEY,
                    goal TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    expires_at REAL,
                    metadata TEXT DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS blackboard_entries (
                    task_id TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    value_type TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    PRIMARY KEY (task_id, key),
                    FOREIGN KEY (task_id) REFERENCES task_sessions(task_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS context_checkpoints (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    step_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    FOREIGN KEY (task_id) REFERENCES task_sessions(task_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_blackboard_task_key
                    ON blackboard_entries (task_id, key);

                CREATE INDEX IF NOT EXISTS idx_checkpoints_task_created
                    ON context_checkpoints (task_id, created_at);

                CREATE INDEX IF NOT EXISTS idx_sessions_expires
                    ON task_sessions (expires_at);
            """)
            self._conn.commit()

    def create_task(
        self,
        task_id: str,
        goal: str = "",
        ttl_seconds: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Create a new task session."""
        now = time.time()
        expires_at = (now + ttl_seconds) if ttl_seconds is not None else None
        meta_json = json.dumps(metadata or {})

        with self._lock:
            try:
                self._conn.execute(
                    """
                    INSERT INTO task_sessions (task_id, goal, status, created_at, updated_at, expires_at, metadata)
                    VALUES (?, ?, 'active', ?, ?, ?, ?)
                    ON CONFLICT(task_id) DO UPDATE SET
                        goal = excluded.goal,
                        updated_at = excluded.updated_at,
                        expires_at = excluded.expires_at,
                        metadata = excluded.metadata
                    """,
                    (task_id, goal, now, now, expires_at, meta_json),
                )
                self._conn.commit()
                return True
            except Exception:
                return False

    def _ensure_task_session(self, task_id: str, goal: str = "", metadata: Optional[Dict] = None):
        """Ensure a task session exists for foreign keys."""
        with self._lock:
            now = time.time()
            expires = now + (24 * 3600)
            self._conn.execute(
                """
                INSERT OR IGNORE INTO task_sessions (task_id, goal, status, created_at, updated_at, expires_at, metadata)
                VALUES (?, ?, 'active', ?, ?, ?, ?)
                """,
                (task_id, goal or f"Task {task_id}", now, now, expires, json.dumps(metadata or {})),
            )
            self._conn.commit()

    def set(self, task_id: str, key: str, value: Any) -> bool:
        """Set a key-value entry on the task's blackboard."""
        now = time.time()
        val_type = type(value).__name__
        val_json = json.dumps(value, default=str)

        with self._lock:
            try:
                self._ensure_task_session(task_id)
                self._conn.execute(
                    """
                    INSERT INTO blackboard_entries (task_id, key, value, value_type, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(task_id, key) DO UPDATE SET
                        value = excluded.value,
                        value_type = excluded.value_type,
                        updated_at = excluded.updated_at
                    """,
                    (task_id, key, val_json, val_type, now, now),
                )
                self._conn.execute(
                    "UPDATE task_sessions SET updated_at = ? WHERE task_id = ?",
                    (now, task_id),
                )
                self._conn.commit()
                return True
            except Exception:
                return False

    def get(self, task_id: str, key: str, default: Any = None) -> Any:
        """Retrieve a key from the task's blackboard."""
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM blackboard_entries WHERE task_id = ? AND key = ?",
                (task_id, key),
            ).fetchone()
            if row is None:
                return default
            try:
                return json.loads(row["value"])
            except Exception:
                return row["value"]

    def get_all(self, task_id: str) -> Dict[str, Any]:
        """Retrieve all key-value pairs for a task."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT key, value FROM blackboard_entries WHERE task_id = ?",
                (task_id,),
            ).fetchall()
            result = {}
            for r in rows:
                try:
                    result[r["key"]] = json.loads(r["value"])
                except Exception:
                    result[r["key"]] = r["value"]
            return result

    def delete_key(self, task_id: str, key: str) -> bool:
        """Delete a specific key from the task blackboard."""
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM blackboard_entries WHERE task_id = ? AND key = ?",
                (task_id, key),
            )
            self._conn.commit()
            return cur.rowcount > 0

    def save_checkpoint(self, context: TaskContext) -> int:
        """
        Save an immutable TaskContext checkpoint for auditability / replay.
        Returns the checkpoint ID.
        """
        now = time.time()
        payload = context.to_json()

        with self._lock:
            self._ensure_task_session(context.task_id, context.goal)
            cur = self._conn.execute(
                """
                INSERT INTO context_checkpoints (task_id, step_id, payload, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (context.task_id, context.step_id, payload, now),
            )
            self._conn.execute(
                "UPDATE task_sessions SET updated_at = ? WHERE task_id = ?",
                (now, context.task_id),
            )
            self._conn.commit()
            return cur.lastrowid

    def get_latest_checkpoint(self, task_id: str) -> Optional[TaskContext]:
        """Retrieve the most recent checkpoint for a task."""
        with self._lock:
            row = self._conn.execute(
                """
                SELECT payload FROM context_checkpoints
                WHERE task_id = ?
                ORDER BY id DESC LIMIT 1
                """,
                (task_id,),
            ).fetchone()
            if row is None:
                return None
            return TaskContext.from_json(row["payload"])

    def get_checkpoints(self, task_id: str) -> List[TaskContext]:
        """Retrieve all checkpoints for a task in chronological order."""
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT payload FROM context_checkpoints
                WHERE task_id = ?
                ORDER BY id ASC
                """,
                (task_id,),
            ).fetchall()
            return [TaskContext.from_json(r["payload"]) for r in rows]

    def complete_task(self, task_id: str, status: str = "completed") -> bool:
        """Mark a task session as completed or failed."""
        now = time.time()
        with self._lock:
            cur = self._conn.execute(
                "UPDATE task_sessions SET status = ?, updated_at = ? WHERE task_id = ?",
                (status, now, task_id),
            )
            self._conn.commit()
            return cur.rowcount > 0

    def cleanup_task(self, task_id: str) -> bool:
        """Remove a task session and all associated blackboard entries / checkpoints."""
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM task_sessions WHERE task_id = ?",
                (task_id,),
            )
            self._conn.commit()
            return cur.rowcount > 0

    def purge_expired(self) -> int:
        """Purge all task sessions whose expires_at timestamp has passed."""
        now = time.time()
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM task_sessions WHERE expires_at IS NOT NULL AND expires_at < ?",
                (now,),
            )
            self._conn.commit()
            return cur.rowcount

    def close(self):
        """Close SQLite database connection."""
        with self._lock:
            try:
                self._conn.close()
            except Exception:
                pass


# Singleton instance
_blackboard: Optional[TaskBlackboard] = None


def get_task_blackboard(db_path: Optional[str] = None) -> TaskBlackboard:
    """Get or initialize singleton TaskBlackboard."""
    global _blackboard
    if _blackboard is None:
        _blackboard = TaskBlackboard(db_path)
    return _blackboard
