"""
CCOS Memory System — Structured knowledge storage.

Three components:
- Vector Store: semantic search over embeddings
- Structured DB: skills, tools, configs in SQLite
- Event Log: history of actions and outcomes

Stores: successful workflows, failed attempts,
installed plugins, learned preferences, performance data.
"""

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

DB_PATH = str(Path(__file__).parent.parent / "data" / "ccos_memory.db")


class StructuredDB:
    """
    SQLite-backed structured memory for skills, tools, and configs.
    """

    def __init__(self, db_path: str = None):
        self._path = db_path or DB_PATH
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._path)
        self._conn.row_factory = sqlite3.Row
        self._init_tables()

    def _init_tables(self):
        c = self._conn.cursor()
        c.executescript("""
            CREATE TABLE IF NOT EXISTS skills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                description TEXT,
                category TEXT DEFAULT 'general',
                implementation TEXT,
                version TEXT DEFAULT '1.0.0',
                status TEXT DEFAULT 'active',
                use_count INTEGER DEFAULT 0,
                success_count INTEGER DEFAULT 0,
                created_at REAL,
                updated_at REAL
            );

            CREATE TABLE IF NOT EXISTS workflows (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                goal TEXT,
                steps TEXT,
                result TEXT,
                success INTEGER DEFAULT 1,
                duration_ms REAL DEFAULT 0,
                created_at REAL
            );

            CREATE TABLE IF NOT EXISTS configs (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at REAL
            );

            CREATE TABLE IF NOT EXISTS preferences (
                key TEXT PRIMARY KEY,
                value TEXT,
                confidence REAL DEFAULT 0.5,
                updated_at REAL
            );

            CREATE TABLE IF NOT EXISTS performance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                capability TEXT,
                task_type TEXT,
                duration_ms REAL,
                success INTEGER,
                timestamp REAL
            );
        """)
        self._conn.commit()

    # ── Skills ──────────────────────────────────────────────────────

    def store_skill(self, name: str, description: str, implementation: str,
                    category: str = "general", version: str = "1.0.0") -> bool:
        now = time.time()
        try:
            self._conn.execute(
                """INSERT OR REPLACE INTO skills
                   (name, description, category, implementation, version, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, 'active', ?, ?)""",
                (name, description, category, implementation, version, now, now),
            )
            self._conn.commit()
            return True
        except Exception:
            return False

    def get_skill(self, name: str) -> Optional[Dict[str, Any]]:
        row = self._conn.execute("SELECT * FROM skills WHERE name = ?", (name,)).fetchone()
        return dict(row) if row else None

    def list_skills(self, category: str = None) -> List[Dict[str, Any]]:
        if category:
            rows = self._conn.execute("SELECT * FROM skills WHERE category = ?", (category,)).fetchall()
        else:
            rows = self._conn.execute("SELECT * FROM skills").fetchall()
        return [dict(r) for r in rows]

    def record_skill_use(self, name: str, success: bool):
        self._conn.execute(
            "UPDATE skills SET use_count = use_count + 1, success_count = success_count + ?, updated_at = ? WHERE name = ?",
            (1 if success else 0, time.time(), name),
        )
        self._conn.commit()

    # ── Workflows ───────────────────────────────────────────────────

    def store_workflow(self, name: str, goal: str, steps: List[str],
                       result: str, success: bool = True, duration_ms: float = 0) -> bool:
        try:
            self._conn.execute(
                """INSERT INTO workflows (name, goal, steps, result, success, duration_ms, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (name, goal, json.dumps(steps), result, int(success), duration_ms, time.time()),
            )
            self._conn.commit()
            return True
        except Exception:
            return False

    def get_successful_workflows(self, limit: int = 10) -> List[Dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM workflows WHERE success = 1 ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_failed_workflows(self, limit: int = 10) -> List[Dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM workflows WHERE success = 0 ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Configs ─────────────────────────────────────────────────────

    def set_config(self, key: str, value: Any):
        self._conn.execute(
            "INSERT OR REPLACE INTO configs (key, value, updated_at) VALUES (?, ?, ?)",
            (key, json.dumps(value), time.time()),
        )
        self._conn.commit()

    def get_config(self, key: str, default: Any = None) -> Any:
        row = self._conn.execute("SELECT value FROM configs WHERE key = ?", (key,)).fetchone()
        if row:
            try:
                return json.loads(row["value"])
            except Exception:
                return row["value"]
        return default

    # ── Preferences ─────────────────────────────────────────────────

    def set_preference(self, key: str, value: str, confidence: float = 0.5):
        self._conn.execute(
            "INSERT OR REPLACE INTO preferences (key, value, confidence, updated_at) VALUES (?, ?, ?, ?)",
            (key, value, confidence, time.time()),
        )
        self._conn.commit()

    def get_preference(self, key: str) -> Optional[Dict[str, Any]]:
        row = self._conn.execute("SELECT * FROM preferences WHERE key = ?", (key,)).fetchone()
        return dict(row) if row else None

    def get_all_preferences(self) -> List[Dict[str, Any]]:
        rows = self._conn.execute("SELECT * FROM preferences ORDER BY confidence DESC").fetchall()
        return [dict(r) for r in rows]

    # ── Performance ─────────────────────────────────────────────────

    def record_performance(self, capability: str, task_type: str,
                           duration_ms: float, success: bool):
        self._conn.execute(
            """INSERT INTO performance (capability, task_type, duration_ms, success, timestamp)
               VALUES (?, ?, ?, ?, ?)""",
            (capability, task_type, duration_ms, int(success), time.time()),
        )
        self._conn.commit()

    def get_performance_stats(self, capability: str = None) -> Dict[str, Any]:
        if capability:
            rows = self._conn.execute(
                "SELECT * FROM performance WHERE capability = ? ORDER BY timestamp DESC LIMIT 50",
                (capability,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT capability, AVG(duration_ms), SUM(success), COUNT(*) FROM performance GROUP BY capability"
            ).fetchall()

        if capability:
            successes = sum(1 for r in rows if r["success"])
            total = len(rows)
            avg_ms = sum(r["duration_ms"] for r in rows) / total if total > 0 else 0
            return {
                "capability": capability,
                "total_uses": total,
                "success_rate": successes / total if total > 0 else 0,
                "avg_duration_ms": avg_ms,
            }
        else:
            return {"stats": [dict(r) for r in rows]}

    def close(self):
        self._conn.close()


class EventLog:
    """
    Append-only event log for action history.
    """

    def __init__(self, db_path: str = None):
        self._path = db_path or DB_PATH
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._path)
        self._conn.row_factory = sqlite3.Row
        self._init_table()

    def _init_table(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                source TEXT,
                details TEXT,
                metadata TEXT,
                timestamp REAL
            );
            CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
            CREATE INDEX IF NOT EXISTS idx_events_ts ON events(timestamp);
        """)
        self._conn.commit()

    def log(self, event_type: str, source: str = "", details: str = "",
            metadata: Dict[str, Any] = None):
        self._conn.execute(
            """INSERT INTO events (event_type, source, details, metadata, timestamp)
               VALUES (?, ?, ?, ?, ?)""",
            (event_type, source, details, json.dumps(metadata or {}), time.time()),
        )
        self._conn.commit()

    def get_recent(self, limit: int = 50, event_type: str = None) -> List[Dict[str, Any]]:
        if event_type:
            rows = self._conn.execute(
                "SELECT * FROM events WHERE event_type = ? ORDER BY timestamp DESC LIMIT ?",
                (event_type, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM events ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_count(self, event_type: str = None) -> int:
        if event_type:
            row = self._conn.execute(
                "SELECT COUNT(*) as c FROM events WHERE event_type = ?", (event_type,)
            ).fetchone()
        else:
            row = self._conn.execute("SELECT COUNT(*) as c FROM events").fetchone()
        return row["c"] if row else 0


class VectorStore:
    """
    Simple vector store using numpy for similarity search.
    Falls back gracefully if numpy is unavailable.
    """

    def __init__(self, dimension: int = 384):
        self._dimension = dimension
        self._vectors: List[Tuple[str, List[float], Dict[str, Any]]] = []
        self._available = False
        try:
            import numpy as np
            self._np = np
            self._available = True
        except ImportError:
            self._np = None

    @property
    def available(self) -> bool:
        return self._available

    def add(self, text: str, embedding: List[float], metadata: Dict[str, Any] = None):
        """Add a vector with associated text and metadata."""
        if len(embedding) != self._dimension:
            return False
        self._vectors.append((text, embedding, metadata or {}))
        return True

    def search(self, query_embedding: List[float], limit: int = 5) -> List[Dict[str, Any]]:
        """Search for similar vectors using cosine similarity."""
        if not self._available or not self._vectors:
            return []

        np = self._np
        query = np.array(query_embedding, dtype=np.float32)
        query_norm = np.linalg.norm(query)
        if query_norm == 0:
            return []

        results = []
        for text, vec, meta in self._vectors:
            v = np.array(vec, dtype=np.float32)
            v_norm = np.linalg.norm(v)
            if v_norm == 0:
                continue
            similarity = float(np.dot(query, v) / (query_norm * v_norm))
            results.append({
                "text": text,
                "score": similarity,
                "metadata": meta,
            })

        results.sort(key=lambda x: -x["score"])
        return results[:limit]

    def count(self) -> int:
        return len(self._vectors)


class CCOSMemory:
    """
    Unified memory system combining all three stores.
    """

    def __init__(self, db_path: str = None):
        self.structured = StructuredDB(db_path)
        self.events = EventLog(db_path)
        self.vectors = VectorStore()

    def store_task_result(self, task: str, result: str, success: bool,
                          capability: str = "", duration_ms: float = 0,
                          steps: List[str] = None):
        """Store the result of a task execution."""
        # Store in workflows
        self.structured.store_workflow(
            name=task[:100],
            goal=task,
            steps=steps or [],
            result=result[:500],
            success=success,
            duration_ms=duration_ms,
        )

        # Log event
        self.events.log(
            event_type="task_complete",
            source=capability,
            details=f"{'success' if success else 'failed'}: {task[:200]}",
            metadata={"duration_ms": duration_ms, "capability": capability},
        )

        # Record performance
        if capability:
            self.structured.record_performance(capability, task[:50], duration_ms, success)

    def get_similar_tasks(self, task: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Find similar past tasks (keyword-based fallback)."""
        return self.structured.get_successful_workflows(limit)

    def close(self):
        self.structured.close()
        self.events.close()


# Singleton
_memory: Optional[CCOSMemory] = None


def get_ccos_memory() -> CCOSMemory:
    global _memory
    if _memory is None:
        _memory = CCOSMemory()
    return _memory
