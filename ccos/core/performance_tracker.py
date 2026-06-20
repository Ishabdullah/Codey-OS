"""
Performance Tracker — Detailed metrics for every capability.

Tracks per-capability:
- success rate, execution time, retries, error frequency
- version history with per-version metrics
- performance trends over time
- failure reason classification

All metrics stored in CCOS memory DB (additive tables).
"""

import json
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

DB_PATH = str(Path(__file__).parent.parent / "data" / "ccos_memory.db")


@dataclass
class CapabilitySnapshot:
    """Point-in-time performance snapshot for a capability."""
    capability_name: str
    version: str
    timestamp: float
    total_uses: int
    success_count: int
    failure_count: int
    avg_duration_ms: float
    p95_duration_ms: float
    retries: int
    error_categories: Dict[str, int]
    performance_score: float


class PerformanceTracker:
    """
    Tracks detailed performance metrics for every CCOS capability.

    Extends the basic registry metrics with:
    - Per-version tracking (v1, v2, v3...)
    - Retry counting
    - Error classification
    - Performance score computation
    - Trend detection (improving/degrading/stable)
    """

    def __init__(self, db_path: str = None):
        self._path = db_path or DB_PATH
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._path)
        self._conn.row_factory = sqlite3.Row
        self._init_tables()

    def _init_tables(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS cap_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                capability TEXT NOT NULL,
                version TEXT NOT NULL DEFAULT '1.0.0',
                task_hash TEXT,
                duration_ms REAL,
                success INTEGER,
                retries INTEGER DEFAULT 0,
                error_category TEXT,
                error_detail TEXT,
                timestamp REAL
            );
            CREATE INDEX IF NOT EXISTS idx_cap_metrics_name ON cap_metrics(capability);
            CREATE INDEX IF NOT EXISTS idx_cap_metrics_ts ON cap_metrics(timestamp);

            CREATE TABLE IF NOT EXISTS cap_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                capability TEXT NOT NULL,
                version TEXT NOT NULL,
                implementation_path TEXT,
                registered_at REAL,
                deprecated_at REAL,
                performance_score REAL DEFAULT 0.0,
                total_uses INTEGER DEFAULT 0,
                success_count INTEGER DEFAULT 0,
                failure_count INTEGER DEFAULT 0,
                avg_duration_ms REAL DEFAULT 0,
                is_current INTEGER DEFAULT 1,
                UNIQUE(capability, version)
            );

            CREATE TABLE IF NOT EXISTS cap_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                capability TEXT NOT NULL,
                version TEXT,
                snapshot_json TEXT,
                timestamp REAL
            );
            CREATE INDEX IF NOT EXISTS idx_snap_name ON cap_snapshots(capability);
        """)
        self._conn.commit()

    def record_execution(
        self,
        capability: str,
        version: str = "1.0.0",
        duration_ms: float = 0,
        success: bool = True,
        retries: int = 0,
        error_category: str = "",
        error_detail: str = "",
        task_hash: str = "",
    ):
        """Record a single capability execution."""
        self._conn.execute(
            """INSERT INTO cap_metrics
               (capability, version, task_hash, duration_ms, success, retries,
                error_category, error_detail, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                capability, version, task_hash, duration_ms,
                int(success), retries, error_category, error_detail,
                time.time(),
            ),
        )
        self._conn.commit()

        # Update version stats
        self._update_version_stats(capability, version, success, duration_ms)

    def _update_version_stats(self, capability: str, version: str,
                               success: bool, duration_ms: float):
        """Update aggregate stats for a capability version."""
        row = self._conn.execute(
            "SELECT * FROM cap_versions WHERE capability = ? AND version = ?",
            (capability, version),
        ).fetchone()

        if row:
            new_total = row["total_uses"] + 1
            new_success = row["success_count"] + (1 if success else 0)
            new_failure = row["failure_count"] + (0 if success else 1)
            new_avg = ((row["avg_duration_ms"] * row["total_uses"]) + duration_ms) / new_total
            score = self._compute_score(new_success, new_failure, new_avg)

            self._conn.execute(
                """UPDATE cap_versions
                   SET total_uses = ?, success_count = ?, failure_count = ?,
                       avg_duration_ms = ?, performance_score = ?
                   WHERE capability = ? AND version = ?""",
                (new_total, new_success, new_failure, new_avg, score, capability, version),
            )
        else:
            score = self._compute_score(1 if success else 0, 0 if success else 1, duration_ms)
            self._conn.execute(
                """INSERT INTO cap_versions
                   (capability, version, registered_at, performance_score,
                    total_uses, success_count, failure_count, avg_duration_ms, is_current)
                   VALUES (?, ?, ?, ?, 1, ?, ?, ?, 1)""",
                (capability, version, time.time(), score,
                 1 if success else 0, 0 if success else 1, duration_ms),
            )
        self._conn.commit()

    def _compute_score(self, successes: int, failures: int, avg_ms: float) -> float:
        """
        Compute a 0-100 performance score.
        Weighted: 70% success rate, 30% speed.
        """
        total = successes + failures
        if total == 0:
            return 50.0
        success_rate = successes / total
        # Speed score: 100 for <100ms, 0 for >10s, linear in between
        speed_score = max(0, min(100, 100 - (avg_ms / 100)))
        return round(success_rate * 70 + speed_score * 0.3, 1)

    def get_capability_metrics(self, capability: str) -> Dict[str, Any]:
        """Get comprehensive metrics for a capability."""
        rows = self._conn.execute(
            "SELECT * FROM cap_metrics WHERE capability = ? ORDER BY timestamp DESC",
            (capability,),
        ).fetchall()

        if not rows:
            return {"capability": capability, "total_uses": 0}

        successes = sum(1 for r in rows if r["success"])
        failures = len(rows) - successes
        durations = [r["duration_ms"] for r in rows if r["duration_ms"] > 0]
        avg_ms = sum(durations) / len(durations) if durations else 0
        durations.sort()
        p95_idx = int(len(durations) * 0.95)
        p95_ms = durations[p95_idx] if durations else 0

        # Error breakdown
        error_cats = {}
        for r in rows:
            if r["error_category"]:
                error_cats[r["error_category"]] = error_cats.get(r["error_category"], 0) + 1

        # Retry stats
        total_retries = sum(r["retries"] for r in rows)

        return {
            "capability": capability,
            "total_uses": len(rows),
            "success_count": successes,
            "failure_count": failures,
            "success_rate": round(successes / len(rows), 3) if rows else 0,
            "avg_duration_ms": round(avg_ms, 1),
            "p95_duration_ms": round(p95_ms, 1),
            "total_retries": total_retries,
            "error_categories": error_cats,
            "performance_score": self._compute_score(successes, failures, avg_ms),
        }

    def get_version_history(self, capability: str) -> List[Dict[str, Any]]:
        """Get all versions of a capability with their metrics."""
        rows = self._conn.execute(
            "SELECT * FROM cap_versions WHERE capability = ? ORDER BY registered_at ASC",
            (capability,),
        ).fetchall()
        return [dict(r) for r in rows]

    def register_version(self, capability: str, version: str,
                         implementation_path: str = ""):
        """Register a new version of a capability."""
        # Mark old versions as not current
        self._conn.execute(
            "UPDATE cap_versions SET is_current = 0 WHERE capability = ?",
            (capability,),
        )
        self._conn.execute(
            """INSERT OR REPLACE INTO cap_versions
               (capability, version, implementation_path, registered_at, is_current)
               VALUES (?, ?, ?, ?, 1)""",
            (capability, version, implementation_path, time.time()),
        )
        self._conn.commit()

    def deprecate_version(self, capability: str, version: str):
        """Mark a version as deprecated."""
        self._conn.execute(
            "UPDATE cap_versions SET deprecated_at = ?, is_current = 0 WHERE capability = ? AND version = ?",
            (time.time(), capability, version),
        )
        self._conn.commit()

    def get_trend(self, capability: str, window: int = 20) -> str:
        """
        Detect performance trend: 'improving', 'degrading', 'stable', 'insufficient'.
        Compares first half vs second half of recent executions.
        """
        rows = self._conn.execute(
            "SELECT success, duration_ms FROM cap_metrics WHERE capability = ? ORDER BY timestamp DESC LIMIT ?",
            (capability, window),
        ).fetchall()

        if len(rows) < 4:
            return "insufficient"

        mid = len(rows) // 2
        recent = rows[:mid]
        older = rows[mid:]

        recent_score = sum(1 for r in recent if r["success"]) / len(recent)
        older_score = sum(1 for r in older if r["success"]) / len(older)

        diff = recent_score - older_score
        if diff > 0.15:
            return "improving"
        elif diff < -0.15:
            return "degrading"
        return "stable"

    def get_weak_capabilities(self, min_uses: int = 3, max_score: float = 60) -> List[Dict[str, Any]]:
        """
        Find capabilities with poor performance that should be optimized.
        """
        rows = self._conn.execute(
            """SELECT capability, performance_score, total_uses, success_count, failure_count
               FROM cap_versions
               WHERE is_current = 1 AND total_uses >= ?
               ORDER BY performance_score ASC""",
            (min_uses,),
        ).fetchall()

        weak = []
        for r in rows:
            if r["performance_score"] < max_score:
                weak.append(dict(r))
        return weak

    def take_snapshot(self, capability: str):
        """Store a point-in-time snapshot of capability metrics."""
        metrics = self.get_capability_metrics(capability)
        version_row = self._conn.execute(
            "SELECT version FROM cap_versions WHERE capability = ? AND is_current = 1",
            (capability,),
        ).fetchone()
        version = version_row["version"] if version_row else "1.0.0"

        self._conn.execute(
            "INSERT INTO cap_snapshots (capability, version, snapshot_json, timestamp) VALUES (?, ?, ?, ?)",
            (capability, version, json.dumps(metrics), time.time()),
        )
        self._conn.commit()

    def get_all_metrics(self) -> List[Dict[str, Any]]:
        """Get metrics overview for all tracked capabilities."""
        rows = self._conn.execute(
            "SELECT * FROM cap_versions WHERE is_current = 1 ORDER BY performance_score ASC"
        ).fetchall()
        return [dict(r) for r in rows]

    def close(self):
        self._conn.close()


# Singleton
_tracker: Optional[PerformanceTracker] = None


def get_performance_tracker() -> PerformanceTracker:
    global _tracker
    if _tracker is None:
        _tracker = PerformanceTracker()
    return _tracker
