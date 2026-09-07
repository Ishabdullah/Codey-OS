#!/usr/bin/env python3
"""
Multi-Process Scheduler & OS Resource Bus — Codey-OS Track A (Item 9.2).

Provides unified resource arbitration across all Codey processes:
- SQLite WAL + flock coordination at ~/.codey/resource_bus.db
- Dynamic priority levels with time-based priority aging
- Multi-resource leasing: context tokens, model slots, CPU threads, memory
- Thermal state gating (integrated with core/thermal.py)
- Memory headroom tracking (integrated with /proc/meminfo)
- Safe dead-PID and stale lease reaping (Rule 3 compliant: exact PIDs only)
"""

from __future__ import annotations

import fcntl
import json
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum, IntEnum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from utils.config import CODEY_STATE_DIR


class PriorityLevel(IntEnum):
    """Priority levels for resource allocation."""
    CRITICAL = 100
    HIGH = 75
    NORMAL = 50
    LOW = 25


class ReservationStatus(str, Enum):
    """Lifecycle status for requests and leases."""
    PENDING = "pending"
    ACQUIRED = "acquired"
    RELEASED = "released"
    EXPIRED = "expired"
    REJECTED = "rejected"


class ThermalThrottleState(str, Enum):
    """Thermal condition states."""
    NORMAL = "normal"
    WARM = "warm"
    CRITICAL = "critical"


@dataclass
class ResourceRequest:
    """A resource allocation request."""
    request_id: str
    resource_type: str
    requester_id: str
    pid: int
    priority: int
    created_at: float
    units: int
    metadata: Dict[str, Any] = field(default_factory=dict)
    status: str = ReservationStatus.PENDING.value
    effective_priority: Optional[int] = None


@dataclass
class ResourceLease:
    """An active lease for a granted resource."""
    lease_id: str
    request_id: str
    resource_type: str
    requester_id: str
    pid: int
    units: int
    priority: int
    granted_at: float
    expires_at: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    status: str = ReservationStatus.ACQUIRED.value


@dataclass
class BusDecision:
    """Decision returned by the resource bus for an allocation request."""
    admitted: bool
    lease_id: Optional[str]
    effective_priority: int
    thermal_state: str
    reason: str
    available_units: int
    requested_units: int
    metadata: Dict[str, Any] = field(default_factory=dict)


# Default lease durations and timeouts
DEFAULT_LEASE_DURATION_SEC = 60.0
MAX_STALE_REQUEST_AGE_SEC = 300.0


def _get_db_path(state_dir: Optional[Path] = None) -> Path:
    base = Path(state_dir) if state_dir is not None else Path(CODEY_STATE_DIR)
    base.mkdir(parents=True, exist_ok=True)
    return base / "resource_bus.db"


def _get_lock_path(state_dir: Optional[Path] = None) -> Path:
    base = Path(state_dir) if state_dir is not None else Path(CODEY_STATE_DIR)
    base.mkdir(parents=True, exist_ok=True)
    return base / "resource_bus.lock"


def _init_db(conn: sqlite3.Connection):
    """Initialize SQLite WAL schema."""
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS resource_requests (
            request_id TEXT PRIMARY KEY,
            resource_type TEXT NOT NULL,
            requester_id TEXT NOT NULL,
            pid INTEGER NOT NULL,
            priority INTEGER NOT NULL,
            created_at REAL NOT NULL,
            units INTEGER NOT NULL,
            metadata TEXT NOT NULL,
            status TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS resource_leases (
            lease_id TEXT PRIMARY KEY,
            request_id TEXT NOT NULL,
            resource_type TEXT NOT NULL,
            requester_id TEXT NOT NULL,
            pid INTEGER NOT NULL,
            units INTEGER NOT NULL,
            priority INTEGER NOT NULL,
            granted_at REAL NOT NULL,
            expires_at REAL NOT NULL,
            metadata TEXT NOT NULL,
            status TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_leases_status ON resource_leases(status, resource_type);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_requests_status ON resource_requests(status, resource_type, priority);")
    conn.commit()


@contextmanager
def _locked_db(state_dir: Optional[Path] = None):
    """Atomic multi-process lock and SQLite connection."""
    lock_file = _get_lock_path(state_dir)
    db_file = _get_db_path(state_dir)
    with open(lock_file, "w") as lf:
        fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
        try:
            conn = sqlite3.connect(str(db_file), timeout=10.0)
            conn.row_factory = sqlite3.Row
            _init_db(conn)
            yield conn
            conn.commit()
            conn.close()
        finally:
            fcntl.flock(lf.fileno(), fcntl.LOCK_UN)


def compute_effective_priority(
    base_priority: int, created_at: float, now: Optional[float] = None
) -> int:
    """
    Calculate dynamic priority with aging bonus:
    effective_priority = base_priority + min(30, int((now - created_at) / 5) * 5)
    Increases priority by +5 every 5 seconds waiting in queue, capped at +30.
    """
    if now is None:
        now = time.time()
    elapsed = max(0.0, now - created_at)
    aging_bonus = min(30, int(elapsed / 5.0) * 5)
    return int(base_priority + aging_bonus)


def get_thermal_throttle_state(read_temp_fn=None) -> ThermalThrottleState:
    """
    Check current CPU thermal status.
    Returns NORMAL, WARM, or CRITICAL.
    """
    if read_temp_fn is None:
        try:
            from core.thermal import get_current_temp_c
            read_temp_fn = get_current_temp_c
        except Exception:
            read_temp_fn = lambda: None
    try:
        temp = read_temp_fn()
    except Exception:
        temp = None

    if temp is None:
        return ThermalThrottleState.NORMAL

    try:
        from utils.config import THERMAL_CONFIG
        crit = THERMAL_CONFIG.get("temp_critical", 90)
        warn = THERMAL_CONFIG.get("temp_warn", 75)
    except Exception:
        crit, warn = 90, 75

    if temp >= crit:
        return ThermalThrottleState.CRITICAL
    elif temp >= warn:
        return ThermalThrottleState.WARM
    return ThermalThrottleState.NORMAL


def get_memory_headroom(meminfo: Optional[Dict[str, int]] = None) -> int:
    """
    Return available system RAM headroom in bytes from /proc/meminfo.
    """
    if meminfo is None:
        try:
            from core.resource_gate import read_meminfo
            meminfo = read_meminfo()
        except Exception:
            return 0
    return max(0, meminfo.get("MemAvailable", 0))


def _pid_alive(pid: int) -> bool:
    """
    Rule 3 compliant PID liveness check.
    Checks exact tracked PID only, never issues pattern/wildcard kills.
    """
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _reap_stale_records_locked(conn: sqlite3.Connection, now: float) -> int:
    """Reap expired leases and dead PIDs with already held lock/connection."""
    reaped_count = 0
    cursor = conn.cursor()
    # 1. Active leases
    cursor.execute(
        "SELECT lease_id, pid, expires_at FROM resource_leases WHERE status = ?",
        (ReservationStatus.ACQUIRED.value,),
    )
    for row in cursor.fetchall():
        lease_id = row["lease_id"]
        pid = row["pid"]
        expires_at = row["expires_at"]
        if (expires_at is not None and now > expires_at) or (pid and not _pid_alive(pid)):
            cursor.execute(
                "UPDATE resource_leases SET status = ? WHERE lease_id = ?",
                (ReservationStatus.EXPIRED.value, lease_id),
            )
            reaped_count += 1

    # 2. Pending requests
    cursor.execute(
        "SELECT request_id, pid, created_at FROM resource_requests WHERE status = ?",
        (ReservationStatus.PENDING.value,),
    )
    for row in cursor.fetchall():
        req_id = row["request_id"]
        pid = row["pid"]
        created_at = row["created_at"]
        if (now - created_at > MAX_STALE_REQUEST_AGE_SEC) or (pid and not _pid_alive(pid)):
            cursor.execute(
                "UPDATE resource_requests SET status = ? WHERE request_id = ?",
                (ReservationStatus.EXPIRED.value, req_id),
            )
            reaped_count += 1

    return reaped_count


def reap_stale_records(
    state_dir: Optional[Path] = None, now: Optional[float] = None
) -> int:
    """
    Reap expired leases and dead PID records from SQLite.
    Rule 3 compliant: checks exact tracked PIDs only.
    Returns the count of reaped records.
    """
    if now is None:
        now = time.time()
    with _locked_db(state_dir) as conn:
        return _reap_stale_records_locked(conn, now)


def acquire_context_lease(
    port: int,
    reserved_tokens: int,
    effective_n_ctx: Optional[int],
    safety_margin_fraction: float = 0.15,
    slots_tokens: int = 0,
    priority: int = PriorityLevel.NORMAL.value,
    pid: Optional[int] = None,
    state_dir: Optional[Path] = None,
    lease_duration: float = DEFAULT_LEASE_DURATION_SEC,
    read_temp_fn=None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, Optional[str], int, int, str]:
    """
    Admit and reserve context tokens on the resource bus.

    Returns:
        (admitted, lease_id, other_reserved_tokens, ceiling_tokens, reason)
    """
    if pid is None:
        pid = os.getpid()

    if effective_n_ctx is None or effective_n_ctx <= 0:
        return (
            False,
            None,
            0,
            0,
            "cannot resolve the shared server's real n_ctx from the slot store or /proc — refusing this admission rather than guessing (CLAUDE.md rule 12)",
        )

    ceiling_tokens = int(effective_n_ctx * (1.0 - safety_margin_fraction))
    now = time.time()

    # Check thermal gating for non-critical requests
    thermal_state = get_thermal_throttle_state(read_temp_fn=read_temp_fn)
    if thermal_state == ThermalThrottleState.CRITICAL and priority < PriorityLevel.CRITICAL.value:
        return (
            False,
            None,
            0,
            ceiling_tokens,
            "refused: CPU temperature is critical, non-critical requests throttled",
        )

    with _locked_db(state_dir) as conn:
        cursor = conn.cursor()
        # Reap expired records first
        _reap_stale_records_locked(conn, now)

        # Sum active context leases for this port
        cursor.execute(
            "SELECT lease_id, units, metadata FROM resource_leases WHERE status = ? AND resource_type = ?",
            (ReservationStatus.ACQUIRED.value, "context_tokens"),
        )
        other_reserved = 0
        for row in cursor.fetchall():
            meta = json.loads(row["metadata"]) if row["metadata"] else {}
            if meta.get("port") == port:
                other_reserved += row["units"]

        # Check legacy JSON context store entries if present
        legacy_reserved = 0
        try:
            from core.resource_gate import _state_paths, _read_state_locked, _write_state_locked, _CONTEXT_STATE_FILENAME, _CONTEXT_LOCK_FILENAME, CONTEXT_RESERVATION_MAX_AGE_SECONDS
            state_path, _ = _state_paths(state_dir, _CONTEXT_STATE_FILENAME, _CONTEXT_LOCK_FILENAME)
            if state_path.exists():
                records = _read_state_locked(state_path)
                valid_records = [
                    r
                    for r in records
                    if (r.get("pid") is None or _pid_alive(r["pid"]))
                    and (now - r.get("created_at", 0)) < CONTEXT_RESERVATION_MAX_AGE_SECONDS
                ]
                if len(valid_records) != len(records):
                    _write_state_locked(state_path, valid_records)
                legacy_reserved = sum(
                    r.get("reserved_tokens", 0)
                    for r in valid_records
                    if r.get("port") == port
                )
        except Exception:
            legacy_reserved = 0

        total_other_reserved = other_reserved + legacy_reserved
        combined = slots_tokens + total_other_reserved + reserved_tokens

        if combined > ceiling_tokens:
            reason = (
                f"combined estimated context {combined} tokens would exceed "
                f"the {safety_margin_fraction:.0%}-margin ceiling "
                f"{ceiling_tokens} of n_ctx={effective_n_ctx} "
                f"(slots={slots_tokens}, other_reservations={total_other_reserved}, "
                f"this_request={reserved_tokens})"
            )
            return False, None, total_other_reserved, ceiling_tokens, reason

        lease_id = uuid.uuid4().hex
        req_id = uuid.uuid4().hex
        meta_dict = dict(metadata or {})
        meta_dict["port"] = port

        cursor.execute(
            """
            INSERT INTO resource_leases (
                lease_id, request_id, resource_type, requester_id, pid,
                units, priority, granted_at, expires_at, metadata, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                lease_id,
                req_id,
                "context_tokens",
                str(pid),
                pid,
                reserved_tokens,
                priority,
                now,
                now + lease_duration,
                json.dumps(meta_dict),
                ReservationStatus.ACQUIRED.value,
            ),
        )

        return True, lease_id, total_other_reserved, ceiling_tokens, "admitted"


def release_context_lease(lease_id: str, state_dir: Optional[Path] = None) -> bool:
    """
    Release an active context token lease.
    Returns True if found and released, False otherwise.
    """
    found = False

    # Check and release legacy JSON store if needed
    try:
        from core.resource_gate import _state_paths, _read_state_locked, _write_state_locked, _CONTEXT_STATE_FILENAME, _CONTEXT_LOCK_FILENAME
        state_path, _ = _state_paths(state_dir, _CONTEXT_STATE_FILENAME, _CONTEXT_LOCK_FILENAME)
        if state_path.exists():
            records = _read_state_locked(state_path)
            remaining = [r for r in records if r.get("reservation_id") != lease_id]
            if len(remaining) != len(records):
                found = True
                _write_state_locked(state_path, remaining)
    except Exception:
        pass

    with _locked_db(state_dir) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE resource_leases SET status = ? WHERE lease_id = ? AND status = ?",
            (ReservationStatus.RELEASED.value, lease_id, ReservationStatus.ACQUIRED.value),
        )
        if cursor.rowcount > 0:
            found = True

    return found


def request_resource(
    resource_type: str,
    units: int,
    requester_id: str,
    priority: int = PriorityLevel.NORMAL.value,
    capacity: Optional[int] = None,
    pid: Optional[int] = None,
    state_dir: Optional[Path] = None,
    lease_duration: float = DEFAULT_LEASE_DURATION_SEC,
    read_temp_fn=None,
    metadata: Optional[Dict[str, Any]] = None,
) -> BusDecision:
    """
    Generic resource allocation request on the OS resource bus.
    Supports token budgets, thread allocations, model residency slots, and memory.
    """
    if pid is None:
        pid = os.getpid()

    now = time.time()
    eff_priority = compute_effective_priority(priority, now, now)
    thermal_state = get_thermal_throttle_state(read_temp_fn=read_temp_fn)

    # Thermal throttle check
    if thermal_state == ThermalThrottleState.CRITICAL and priority < PriorityLevel.CRITICAL.value:
        return BusDecision(
            admitted=False,
            lease_id=None,
            effective_priority=eff_priority,
            thermal_state=thermal_state.value,
            reason="rejected: CPU thermal critical (throttled)",
            available_units=0,
            requested_units=units,
            metadata=metadata or {},
        )

    with _locked_db(state_dir) as conn:
        cursor = conn.cursor()
        _reap_stale_records_locked(conn, now)

        # Check existing occupied units
        cursor.execute(
            "SELECT SUM(units) as total_used FROM resource_leases WHERE status = ? AND resource_type = ?",
            (ReservationStatus.ACQUIRED.value, resource_type),
        )
        row = cursor.fetchone()
        used = row["total_used"] or 0

        available = 999999 if capacity is None else max(0, capacity - used)

        if capacity is not None and (used + units) > capacity:
            req_id = uuid.uuid4().hex
            cursor.execute(
                """
                INSERT INTO resource_requests (
                    request_id, resource_type, requester_id, pid, priority,
                    created_at, units, metadata, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    req_id,
                    resource_type,
                    requester_id,
                    pid,
                    priority,
                    now,
                    units,
                    json.dumps(metadata or {}),
                    ReservationStatus.PENDING.value,
                ),
            )
            return BusDecision(
                admitted=False,
                lease_id=None,
                effective_priority=eff_priority,
                thermal_state=thermal_state.value,
                reason=f"capacity exceeded: requested {units}, available {available} of {capacity}",
                available_units=available,
                requested_units=units,
                metadata={"request_id": req_id, **(metadata or {})},
            )

        # Admitted
        lease_id = uuid.uuid4().hex
        req_id = uuid.uuid4().hex
        cursor.execute(
            """
            INSERT INTO resource_leases (
                lease_id, request_id, resource_type, requester_id, pid,
                units, priority, granted_at, expires_at, metadata, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                lease_id,
                req_id,
                resource_type,
                requester_id,
                pid,
                units,
                priority,
                now,
                now + lease_duration,
                json.dumps(metadata or {}),
                ReservationStatus.ACQUIRED.value,
            ),
        )

        return BusDecision(
            admitted=True,
            lease_id=lease_id,
            effective_priority=eff_priority,
            thermal_state=thermal_state.value,
            reason="admitted",
            available_units=available - units,
            requested_units=units,
            metadata=metadata or {},
        )


def release_lease(lease_id: str, state_dir: Optional[Path] = None) -> bool:
    """
    Release any resource lease by lease_id.
    """
    with _locked_db(state_dir) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE resource_leases SET status = ? WHERE lease_id = ? AND status = ?",
            (ReservationStatus.RELEASED.value, lease_id, ReservationStatus.ACQUIRED.value),
        )
        return cursor.rowcount > 0


def poll_queue(
    resource_type: str, state_dir: Optional[Path] = None, now: Optional[float] = None
) -> List[ResourceRequest]:
    """
    Fetch pending requests for a resource type, ordered by effective priority (aging).
    Highest effective priority first; FIFO for ties.
    """
    if now is None:
        now = time.time()

    with _locked_db(state_dir) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT request_id, resource_type, requester_id, pid, priority,
                   created_at, units, metadata, status
            FROM resource_requests
            WHERE status = ? AND resource_type = ?
            """,
            (ReservationStatus.PENDING.value, resource_type),
        )
        requests: List[ResourceRequest] = []
        for row in cursor.fetchall():
            meta = json.loads(row["metadata"]) if row["metadata"] else {}
            eff_pri = compute_effective_priority(row["priority"], row["created_at"], now)
            req = ResourceRequest(
                request_id=row["request_id"],
                resource_type=row["resource_type"],
                requester_id=row["requester_id"],
                pid=row["pid"],
                priority=row["priority"],
                created_at=row["created_at"],
                units=row["units"],
                metadata=meta,
                status=row["status"],
                effective_priority=eff_pri,
            )
            requests.append(req)

        # Sort descending by effective_priority, ascending by created_at
        requests.sort(key=lambda r: (-r.effective_priority, r.created_at))
        return requests
