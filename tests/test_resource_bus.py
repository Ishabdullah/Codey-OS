#!/usr/bin/env python3
"""
Unit tests for Multi-Process Scheduler & OS Resource Bus (core/resource_bus.py).
Tests priority ordering, priority aging, thermal throttle gating,
dead PID / stale record reaping, and multi-process contention.
"""

import time

from core.resource_bus import (
    PriorityLevel,
    ThermalThrottleState,
    compute_effective_priority,
    get_thermal_throttle_state,
    _pid_alive,
    reap_stale_records,
    acquire_context_lease,
    release_context_lease,
    request_resource,
    poll_queue,
)


def test_priority_aging():
    """Verify priority aging adds +5 every 5s up to max +30."""
    t0 = 1000.0
    base = PriorityLevel.NORMAL.value  # 50

    assert compute_effective_priority(base, t0, now=1000.0) == 50
    assert compute_effective_priority(base, t0, now=1004.9) == 50
    assert compute_effective_priority(base, t0, now=1005.0) == 55
    assert compute_effective_priority(base, t0, now=1010.0) == 60
    assert compute_effective_priority(base, t0, now=1020.0) == 70
    assert compute_effective_priority(base, t0, now=1030.0) == 80  # capped at +30
    assert compute_effective_priority(base, t0, now=1100.0) == 80  # still capped at 80


def test_poll_queue_ordering_and_aging(tmp_path):
    """Verify pending requests are ordered by effective priority, with aging promoting older requests."""
    t0 = time.time() - 30.0  # created 30s ago -> +30 bonus

    # Normal request created 30s ago (base 50 + 30 = 80)
    decision1 = request_resource(
        resource_type="cpu_threads",
        units=4,
        requester_id="req1",
        priority=PriorityLevel.NORMAL.value,
        capacity=2,  # capacity 2 < units 4 -> queued as pending
        state_dir=tmp_path,
    )
    assert decision1.admitted is False

    # Backdate req1 created_at
    from core.resource_bus import _locked_db
    with _locked_db(tmp_path) as conn:
        conn.execute("UPDATE resource_requests SET created_at = ?", (t0,))

    # High request created just now (base 75 + 0 = 75)
    decision2 = request_resource(
        resource_type="cpu_threads",
        units=4,
        requester_id="req2",
        priority=PriorityLevel.HIGH.value,
        capacity=2,
        state_dir=tmp_path,
    )
    assert decision2.admitted is False

    # Queue should order req1 (effective 80) ahead of req2 (effective 75) due to aging!
    queue = poll_queue(resource_type="cpu_threads", state_dir=tmp_path)
    assert len(queue) == 2
    assert queue[0].requester_id == "req1"
    assert queue[0].effective_priority == 80
    assert queue[1].requester_id == "req2"
    assert queue[1].effective_priority == 75


def test_thermal_throttle_gating(tmp_path):
    """Critical temp rejects non-critical requests and admits critical priority."""
    # Under critical temp (e.g. 92°C)
    fake_temp_critical = lambda: 92.0

    assert get_thermal_throttle_state(read_temp_fn=fake_temp_critical) == ThermalThrottleState.CRITICAL

    # Non-critical request is rejected
    decision_normal = request_resource(
        resource_type="model_slot",
        units=1,
        requester_id="proc_normal",
        priority=PriorityLevel.NORMAL.value,
        capacity=5,
        state_dir=tmp_path,
        read_temp_fn=fake_temp_critical,
    )
    assert decision_normal.admitted is False
    assert decision_normal.thermal_state == ThermalThrottleState.CRITICAL.value
    assert "throttled" in decision_normal.reason

    # Critical request is admitted even under critical temperature
    decision_critical = request_resource(
        resource_type="model_slot",
        units=1,
        requester_id="proc_critical",
        priority=PriorityLevel.CRITICAL.value,
        capacity=5,
        state_dir=tmp_path,
        read_temp_fn=fake_temp_critical,
    )
    assert decision_critical.admitted is True
    assert decision_critical.thermal_state == ThermalThrottleState.CRITICAL.value


def test_dead_pid_and_stale_lease_reaping(tmp_path):
    """Dead PIDs and expired leases are safely reaped (Rule 3 compliant)."""
    # 1. Lease with dead PID
    dead_pid = 99999999
    assert not _pid_alive(dead_pid)

    decision = request_resource(
        resource_type="memory_bytes",
        units=1024,
        requester_id="dead_proc",
        pid=dead_pid,
        capacity=2048,
        state_dir=tmp_path,
        lease_duration=3600.0,
    )
    assert decision.admitted is True
    lease_id = decision.lease_id

    # Reap should detect dead PID and mark expired
    reaped = reap_stale_records(state_dir=tmp_path)
    assert reaped >= 1

    # Capacity should be freed up
    decision2 = request_resource(
        resource_type="memory_bytes",
        units=2048,
        requester_id="live_proc",
        capacity=2048,
        state_dir=tmp_path,
    )
    assert decision2.admitted is True


def test_context_lease_lifecycle(tmp_path):
    """Acquiring and releasing context leases works and enforces ceiling."""
    port = 8080
    n_ctx = 8192
    ceiling = int(8192 * 0.85)

    admitted, lease_id1, other, ceil, reason = acquire_context_lease(
        port=port,
        reserved_tokens=4000,
        effective_n_ctx=n_ctx,
        state_dir=tmp_path,
    )
    assert admitted is True
    assert lease_id1 is not None

    # Second lease that exceeds ceiling (4000 + 4000 = 8000 > 6963)
    admitted2, lease_id2, other2, _, reason2 = acquire_context_lease(
        port=port,
        reserved_tokens=4000,
        effective_n_ctx=n_ctx,
        state_dir=tmp_path,
    )
    assert admitted2 is False
    assert other2 == 4000
    assert "exceed" in reason2

    # Release first lease
    assert release_context_lease(lease_id1, state_dir=tmp_path) is True

    # Now second lease fits
    admitted3, lease_id3, other3, _, _ = acquire_context_lease(
        port=port,
        reserved_tokens=4000,
        effective_n_ctx=n_ctx,
        state_dir=tmp_path,
    )
    assert admitted3 is True
    assert other3 == 0


def test_multiprocess_concurrency(tmp_path):
    """Verify concurrent requests from separate processes/threads coordinate safely with SQLite WAL + flock."""
    import concurrent.futures

    def _make_request(idx: int):
        dec = request_resource(
            resource_type="tokens",
            units=10,
            requester_id=f"worker_{idx}",
            capacity=50,
            state_dir=tmp_path,
            lease_duration=10.0,
        )
        return dec.admitted

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(_make_request, range(10)))

    # Capacity is 50, each takes 10 -> exactly 5 should be admitted, 5 queued
    admitted_count = sum(1 for r in results if r is True)
    assert admitted_count == 5
