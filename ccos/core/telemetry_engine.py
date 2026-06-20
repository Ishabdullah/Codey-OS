"""
Telemetry Engine — Real-world execution monitoring for CCOS.

Records every real execution, detects performance drift,
compares sandbox vs real-world results, and feeds aggregated
insights back into the improvement loops.

This is the layer that makes CCOS evolve based on REAL behavior,
not only internal simulation or test data.

Design rules:
- Telemetry must not slow execution significantly
- Logging is buffered (batch writes)
- No sensitive data leakage outside system boundary
- Only aggregated insights feed back into system
- Telemetry never interferes with agent decisions directly
"""

import json
import sqlite3
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

DB_PATH = str(Path(__file__).parent.parent / "data" / "ccos_memory.db")


# ── Data structures ────────────────────────────────────────────────

@dataclass
class ExecutionRecord:
    """A single real-world execution record."""
    record_id: str = ""
    timestamp: float = field(default_factory=time.time)
    task: str = ""
    goal_id: str = ""
    project_id: str = ""
    capability: str = ""
    execution_time_ms: float = 0
    agents_used: List[str] = field(default_factory=list)
    tools_used: List[str] = field(default_factory=list)
    success: bool = True
    errors: List[str] = field(default_factory=list)
    resource_usage: Dict[str, Any] = field(default_factory=dict)
    source: str = "real"  # "real" or "sandbox"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DriftAlert:
    """An alert when performance drift is detected."""
    capability: str
    drift_type: str  # "speed", "reliability", "error_rate"
    baseline_value: float
    current_value: float
    drift_pct: float
    severity: str  # "low", "medium", "high"
    details: str = ""
    timestamp: float = field(default_factory=time.time)


@dataclass
class HealthReport:
    """System-wide health assessment."""
    health_score: float  # 0-1
    trend: str  # "improving", "stable", "degrading"
    risk_flags: List[str]
    component_scores: Dict[str, float]
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ccos_health_score": round(self.health_score, 3),
            "trend": self.trend,
            "risk_flags": self.risk_flags,
            "components": {k: round(v, 3) for k, v in self.component_scores.items()},
            "timestamp": self.timestamp,
        }


# ── Telemetry Engine ───────────────────────────────────────────────

class TelemetryEngine:
    """
    Records real-world executions, detects drift, and feeds
    insights back into CCOS improvement loops.

    Uses SQLite for persistent storage with buffered writes
    to minimize execution overhead.
    """

    def __init__(self, db_path: str = None):
        self._path = db_path or DB_PATH
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._buffer: List[ExecutionRecord] = []
        self._buffer_size = 10
        self._baselines: Dict[str, Dict[str, float]] = {}
        self._drift_alerts: List[DriftAlert] = []
        self._init_tables()
        self._load_baselines()

    def _init_tables(self):
        with self._lock:
            self._conn.executescript("""
                CREATE TABLE IF NOT EXISTS exec_telemetry (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    record_id TEXT UNIQUE,
                    timestamp REAL,
                    task TEXT,
                    goal_id TEXT,
                    project_id TEXT,
                    capability TEXT,
                    execution_time_ms REAL,
                    agents_used TEXT,
                    tools_used TEXT,
                    success INTEGER,
                    errors TEXT,
                    resource_usage TEXT,
                    source TEXT DEFAULT 'real',
                    metadata TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_tel_ts ON exec_telemetry(timestamp);
                CREATE INDEX IF NOT EXISTS idx_tel_cap ON exec_telemetry(capability);
                CREATE INDEX IF NOT EXISTS idx_tel_source ON exec_telemetry(source);

                CREATE TABLE IF NOT EXISTS perf_baselines (
                    capability TEXT PRIMARY KEY,
                    baseline_duration_ms REAL,
                    baseline_success_rate REAL,
                    baseline_error_rate REAL,
                    sample_count INTEGER,
                    last_updated REAL
                );

                CREATE TABLE IF NOT EXISTS drift_alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    capability TEXT,
                    drift_type TEXT,
                    baseline_value REAL,
                    current_value REAL,
                    drift_pct REAL,
                    severity TEXT,
                    details TEXT,
                    timestamp REAL
                );
            """)
            self._conn.commit()

    # ── Execution Logging ──────────────────────────────────────────

    def record_execution(self, record: ExecutionRecord):
        """
        Record a real-world execution. Buffered for performance.
        """
        if not record.record_id:
            record.record_id = f"exec_{int(time.time() * 1000)}_{id(record) % 10000}"

        self._buffer.append(record)

        if len(self._buffer) >= self._buffer_size:
            self._flush_buffer()

    def record(self, task: str, success: bool, capability: str = "",
               duration_ms: float = 0, goal_id: str = "", project_id: str = "",
               agents: List[str] = None, tools: List[str] = None,
               errors: List[str] = None, source: str = "real",
               metadata: Dict[str, Any] = None):
        """Convenience method to record an execution."""
        self.record_execution(ExecutionRecord(
            task=task,
            goal_id=goal_id,
            project_id=project_id,
            capability=capability,
            execution_time_ms=duration_ms,
            agents_used=agents or [],
            tools_used=tools or [],
            success=success,
            errors=errors or [],
            source=source,
            metadata=metadata or {},
        ))

    def _flush_buffer(self):
        """Write buffered records to database."""
        if not self._buffer:
            return

        with self._lock:
            for rec in self._buffer:
                try:
                    self._conn.execute(
                        """INSERT OR IGNORE INTO exec_telemetry
                           (record_id, timestamp, task, goal_id, project_id,
                            capability, execution_time_ms, agents_used, tools_used,
                            success, errors, resource_usage, source, metadata)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            rec.record_id, rec.timestamp, rec.task[:500],
                            rec.goal_id, rec.project_id, rec.capability,
                            rec.execution_time_ms,
                            json.dumps(rec.agents_used),
                            json.dumps(rec.tools_used),
                            int(rec.success),
                            json.dumps(rec.errors),
                            json.dumps(rec.resource_usage),
                            rec.source,
                            json.dumps(rec.metadata),
                        ),
                    )
                except Exception:
                    pass
            self._conn.commit()
            self._buffer.clear()

    def force_flush(self):
        """Force flush the buffer."""
        self._flush_buffer()

    # ── Performance Drift Detection ────────────────────────────────

    def update_baseline(self, capability: str):
        """
        Update baseline performance for a capability
        from recent real-world executions.
        """
        rows = self._conn.execute(
            """SELECT execution_time_ms, success
               FROM exec_telemetry
               WHERE capability = ? AND source = 'real'
               ORDER BY timestamp DESC LIMIT 50""",
            (capability,),
        ).fetchall()

        if len(rows) < 3:
            return

        durations = [r["execution_time_ms"] for r in rows if r["execution_time_ms"] > 0]
        successes = sum(1 for r in rows if r["success"])
        total = len(rows)

        if not durations:
            return

        avg_duration = sum(durations) / len(durations)
        success_rate = successes / total
        error_rate = 1.0 - success_rate

        self._baselines[capability] = {
            "duration_ms": avg_duration,
            "success_rate": success_rate,
            "error_rate": error_rate,
            "sample_count": total,
        }

        with self._lock:
            self._conn.execute(
                """INSERT OR REPLACE INTO perf_baselines
                   (capability, baseline_duration_ms, baseline_success_rate,
                    baseline_error_rate, sample_count, last_updated)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (capability, avg_duration, success_rate, error_rate, total, time.time()),
            )
            self._conn.commit()

    def detect_drift(self, capability: str, window: int = 20) -> Optional[DriftAlert]:
        """
        Detect performance drift by comparing recent executions
        against stored baseline.

        Returns DriftAlert if drift detected, None otherwise.
        """
        baseline = self._baselines.get(capability)
        if not baseline:
            self._load_baseline_for(capability)
            baseline = self._baselines.get(capability)
        if not baseline:
            return None

        # Get recent real executions
        rows = self._conn.execute(
            """SELECT execution_time_ms, success
               FROM exec_telemetry
               WHERE capability = ? AND source = 'real'
               ORDER BY timestamp DESC LIMIT ?""",
            (capability, window),
        ).fetchall()

        if len(rows) < 3:
            return None

        durations = [r["execution_time_ms"] for r in rows if r["execution_time_ms"] > 0]
        successes = sum(1 for r in rows if r["success"])
        total = len(rows)

        if not durations:
            return None

        current_duration = sum(durations) / len(durations)
        current_success_rate = successes / total
        current_error_rate = 1.0 - current_success_rate

        alerts = []

        # Speed drift
        if baseline["duration_ms"] > 0:
            speed_drift = (current_duration - baseline["duration_ms"]) / baseline["duration_ms"]
            if speed_drift > 0.3:  # 30% slower
                severity = "high" if speed_drift > 0.5 else "medium"
                alerts.append(DriftAlert(
                    capability=capability,
                    drift_type="speed",
                    baseline_value=baseline["duration_ms"],
                    current_value=current_duration,
                    drift_pct=speed_drift * 100,
                    severity=severity,
                    details=f"{capability} is {speed_drift*100:.0f}% slower than baseline",
                ))

        # Reliability drift
        error_drift = current_error_rate - baseline["error_rate"]
        if error_drift > 0.15:  # 15% more errors
            severity = "high" if error_drift > 0.3 else "medium"
            alerts.append(DriftAlert(
                capability=capability,
                drift_type="reliability",
                baseline_value=baseline["success_rate"],
                current_value=current_success_rate,
                drift_pct=error_drift * 100,
                severity=severity,
                details=f"{capability} error rate increased by {error_drift*100:.0f}%",
            ))

        if alerts:
            worst = max(alerts, key=lambda a: a.drift_pct)
            self._drift_alerts.append(worst)
            self._save_drift_alert(worst)
            return worst

        return None

    def get_drift_alerts(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent drift alerts."""
        rows = self._conn.execute(
            "SELECT * FROM drift_alerts ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Sandbox vs Real Gap Analysis ───────────────────────────────

    def compare_sandbox_vs_real(self, capability: str) -> Dict[str, Any]:
        """
        Compare sandbox test results vs real-world execution results.
        Returns gap analysis.
        """
        # Sandbox results
        sandbox_rows = self._conn.execute(
            """SELECT AVG(execution_time_ms) as avg_ms,
                      SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) * 1.0 / COUNT(*) as success_rate,
                      COUNT(*) as count
               FROM exec_telemetry
               WHERE capability = ? AND source = 'sandbox'""",
            (capability,),
        ).fetchone()

        # Real results
        real_rows = self._conn.execute(
            """SELECT AVG(execution_time_ms) as avg_ms,
                      SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) * 1.0 / COUNT(*) as success_rate,
                      COUNT(*) as count
               FROM exec_telemetry
               WHERE capability = ? AND source = 'real'""",
            (capability,),
        ).fetchone()

        sandbox_count = sandbox_rows["count"] if sandbox_rows else 0
        real_count = real_rows["count"] if real_rows else 0

        if sandbox_count == 0 or real_count == 0:
            return {
                "capability": capability,
                "available": False,
                "reason": "Insufficient data (need both sandbox and real executions)",
            }

        sandbox_avg = sandbox_rows["avg_ms"] or 0
        real_avg = real_rows["avg_ms"] or 0
        sandbox_success = sandbox_rows["success_rate"] or 0
        real_success = real_rows["success_rate"] or 0

        speed_delta = ((real_avg - sandbox_avg) / sandbox_avg * 100) if sandbox_avg > 0 else 0
        success_delta = (real_success - sandbox_success) * 100

        insight = ""
        if abs(speed_delta) > 10:
            direction = "slower" if speed_delta > 0 else "faster"
            insight = f"{capability} performs {abs(speed_delta):.0f}% {direction} in real usage than sandbox"
        if abs(success_delta) > 5:
            direction = "worse" if success_delta < 0 else "better"
            if insight:
                insight += f"; success rate {abs(success_delta):.0f}% {direction}"
            else:
                insight = f"{capability} success rate {abs(success_delta):.0f}% {direction} in real usage"

        return {
            "capability": capability,
            "available": True,
            "sandbox": {"avg_ms": round(sandbox_avg, 1), "success_rate": round(sandbox_success, 3), "count": sandbox_count},
            "real": {"avg_ms": round(real_avg, 1), "success_rate": round(real_success, 3), "count": real_count},
            "speed_delta_pct": round(speed_delta, 1),
            "success_delta_pct": round(success_delta, 1),
            "insight": insight,
        }

    # ── System Health Scoring ──────────────────────────────────────

    def get_health_report(self) -> HealthReport:
        """
        Compute global CCOS health score from real-world telemetry.
        """
        components = {}
        risk_flags = []

        # 1. Execution stability (success rate over last 100)
        rows = self._conn.execute(
            """SELECT success FROM exec_telemetry
               WHERE source = 'real' ORDER BY timestamp DESC LIMIT 100"""
        ).fetchall()
        if rows:
            stability = sum(1 for r in rows if r["success"]) / len(rows)
            components["execution_stability"] = stability
            if stability < 0.8:
                risk_flags.append(f"Low execution stability: {stability:.0%}")
        else:
            components["execution_stability"] = 1.0

        # 2. Average task success rate
        cap_rows = self._conn.execute(
            """SELECT capability,
                      SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) * 1.0 / COUNT(*) as rate
               FROM exec_telemetry
               WHERE source = 'real' AND capability != ''
               GROUP BY capability"""
        ).fetchall()
        if cap_rows:
            avg_rate = sum(r["rate"] for r in cap_rows) / len(cap_rows)
            components["avg_task_success"] = avg_rate
            for r in cap_rows:
                if r["rate"] < 0.7:
                    risk_flags.append(f"Low success rate for {r['capability']}: {r['rate']:.0%}")
        else:
            components["avg_task_success"] = 1.0

        # 3. Drift severity
        recent_alerts = self._conn.execute(
            "SELECT severity FROM drift_alerts ORDER BY timestamp DESC LIMIT 20"
        ).fetchall()
        if recent_alerts:
            high_drift = sum(1 for a in recent_alerts if a["severity"] == "high")
            med_drift = sum(1 for a in recent_alerts if a["severity"] == "medium")
            drift_score = max(0, 1.0 - high_drift * 0.2 - med_drift * 0.1)
            components["drift_health"] = drift_score
            if high_drift > 0:
                risk_flags.append(f"{high_drift} high-severity drift alerts")
        else:
            components["drift_health"] = 1.0

        # 4. Execution volume (healthy system has consistent usage)
        recent_count = self._conn.execute(
            """SELECT COUNT(*) as c FROM exec_telemetry
               WHERE timestamp > ?""",
            (time.time() - 86400,),
        ).fetchone()
        volume = min(1.0, (recent_count["c"] or 0) / 10)  # 10+ per day = healthy
        components["activity_level"] = volume

        # Compute overall health (weighted average)
        weights = {
            "execution_stability": 0.35,
            "avg_task_success": 0.30,
            "drift_health": 0.20,
            "activity_level": 0.15,
        }
        health_score = sum(
            components.get(k, 1.0) * w for k, w in weights.items()
        )

        # Determine trend
        trend = "stable"
        if len(rows) >= 20:
            mid = len(rows) // 2
            recent_success = sum(1 for r in rows[:mid] if r["success"]) / mid
            older_success = sum(1 for r in rows[mid:] if r["success"]) / (len(rows) - mid)
            diff = recent_success - older_success
            if diff > 0.1:
                trend = "improving"
            elif diff < -0.1:
                trend = "degrading"

        return HealthReport(
            health_score=health_score,
            trend=trend,
            risk_flags=risk_flags,
            component_scores=components,
        )

    # ── Feedback Injection ─────────────────────────────────────────

    def get_insights_for_goal_engine(self) -> List[Dict[str, Any]]:
        """
        Generate insights from telemetry that should influence
        the goal engine's priority scoring.
        """
        insights = []

        # Find capabilities with drift
        alerts = self.get_drift_alerts(limit=10)
        for alert in alerts:
            insights.append({
                "type": "drift",
                "capability": alert.get("capability", ""),
                "drift_type": alert.get("drift_type", ""),
                "severity": alert.get("severity", ""),
                "suggestion": f"Investigate {alert.get('drift_type', '')} drift in {alert.get('capability', '')}",
            })

        # Find sandbox-real gaps
        caps = self._conn.execute(
            "SELECT DISTINCT capability FROM exec_telemetry WHERE capability != ''"
        ).fetchall()
        for row in caps:
            gap = self.compare_sandbox_vs_real(row["capability"])
            if gap.get("available") and abs(gap.get("speed_delta_pct", 0)) > 15:
                insights.append({
                    "type": "sandbox_gap",
                    "capability": row["capability"],
                    "speed_delta": gap["speed_delta_pct"],
                    "suggestion": gap.get("insight", ""),
                })

        return insights

    def get_optimization_recommendations(self) -> List[Dict[str, Any]]:
        """
        Generate recommendations for the capability optimizer
        based on real-world performance data.
        """
        recs = []

        # Find capabilities that perform worse in real-world
        caps = self._conn.execute(
            """SELECT capability,
                      AVG(execution_time_ms) as avg_ms,
                      SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) * 1.0 / COUNT(*) as success_rate,
                      COUNT(*) as count
               FROM exec_telemetry
               WHERE source = 'real' AND capability != ''
               GROUP BY capability
               HAVING count >= 3"""
        ).fetchall()

        for row in caps:
            if row["success_rate"] < 0.8:
                recs.append({
                    "capability": row["capability"],
                    "issue": "low_real_success_rate",
                    "current_rate": round(row["success_rate"], 3),
                    "recommendation": f"Optimize {row['capability']} — real-world success rate is {row['success_rate']:.0%}",
                })
            if row["avg_ms"] > 3000:
                recs.append({
                    "capability": row["capability"],
                    "issue": "slow_real_execution",
                    "current_ms": round(row["avg_ms"], 1),
                    "recommendation": f"Speed up {row['capability']} — real-world avg is {row['avg_ms']:.0f}ms",
                })

        return recs

    # ── Query Methods ──────────────────────────────────────────────

    def get_recent_executions(self, limit: int = 20,
                              source: str = None) -> List[Dict[str, Any]]:
        """Get recent execution records."""
        if source:
            rows = self._conn.execute(
                """SELECT * FROM exec_telemetry
                   WHERE source = ? ORDER BY timestamp DESC LIMIT ?""",
                (source, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM exec_telemetry ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_execution_stats(self) -> Dict[str, Any]:
        """Get overall execution statistics."""
        total = self._conn.execute(
            "SELECT COUNT(*) as c FROM exec_telemetry"
        ).fetchone()["c"]

        real = self._conn.execute(
            "SELECT COUNT(*) as c FROM exec_telemetry WHERE source = 'real'"
        ).fetchone()["c"]

        sandbox = self._conn.execute(
            "SELECT COUNT(*) as c FROM exec_telemetry WHERE source = 'sandbox'"
        ).fetchone()["c"]

        real_success = self._conn.execute(
            """SELECT SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) * 1.0 / COUNT(*)
               FROM exec_telemetry WHERE source = 'real'"""
        ).fetchone()

        return {
            "total_executions": total,
            "real_executions": real,
            "sandbox_executions": sandbox,
            "real_success_rate": round(real_success[0] or 0, 3) if real else 0,
            "drift_alerts": len(self._drift_alerts),
        }

    def get_baselines(self) -> Dict[str, Dict[str, float]]:
        """Get all stored baselines."""
        return dict(self._baselines)

    # ── Persistence helpers ────────────────────────────────────────

    def _load_baselines(self):
        """Load baselines from database."""
        rows = self._conn.execute("SELECT * FROM perf_baselines").fetchall()
        for row in rows:
            self._baselines[row["capability"]] = {
                "duration_ms": row["baseline_duration_ms"],
                "success_rate": row["baseline_success_rate"],
                "error_rate": row["baseline_error_rate"],
                "sample_count": row["sample_count"],
            }

    def _load_baseline_for(self, capability: str):
        """Load baseline for a specific capability."""
        row = self._conn.execute(
            "SELECT * FROM perf_baselines WHERE capability = ?",
            (capability,),
        ).fetchone()
        if row:
            self._baselines[capability] = {
                "duration_ms": row["baseline_duration_ms"],
                "success_rate": row["baseline_success_rate"],
                "error_rate": row["baseline_error_rate"],
                "sample_count": row["sample_count"],
            }

    def _save_drift_alert(self, alert: DriftAlert):
        """Save drift alert to database."""
        with self._lock:
            self._conn.execute(
                """INSERT INTO drift_alerts
                   (capability, drift_type, baseline_value, current_value,
                    drift_pct, severity, details, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    alert.capability, alert.drift_type,
                    alert.baseline_value, alert.current_value,
                    alert.drift_pct, alert.severity, alert.details,
                    alert.timestamp,
                ),
            )
            self._conn.commit()

    def close(self):
        """Flush and close."""
        self._flush_buffer()
        self._conn.close()


# Singleton
_engine: Optional[TelemetryEngine] = None


def get_telemetry_engine() -> TelemetryEngine:
    global _engine
    if _engine is None:
        _engine = TelemetryEngine()
    return _engine
