"""
Ring-buffer bounding, drop counting, writer-thread isolation, and the
"a write failure never propagates to the caller" guarantee (constraint 2
of the T0 brief). Also the kill switch: writer produces zero records
when disabled.
"""

from __future__ import annotations

import json
import queue
import time


from telemetry import envelope, store


def _rec(run_id: str, category: str = "meta", body=None):
    return envelope.build_envelope(
        category=category,
        event_type="writer_started",
        emitter="codey-os.daemon",
        pid=4242,
        run_id=run_id,
        body=body if body is not None else {"x": 1},
        correlation_id="a" * 32,
    )


def setup_function(_fn):
    envelope.reset_seq()
    store.reset_for_tests()


def teardown_function(_fn):
    store.reset_for_tests()


def test_normal_write_path_produces_valid_jsonl(tmp_path):
    st = store.Store(root=tmp_path, run_id="normalwrite0001", flush_interval_s=0.1, flush_batch=10)
    try:
        record = _rec(st.run_id)
        st.enqueue(record)
        st.shutdown(timeout=5)

        files = list((tmp_path / "events").rglob(f"meta.{st.run_id}.jsonl"))
        assert len(files) == 1
        lines = [ln for ln in files[0].read_text(encoding="utf-8").splitlines() if ln]
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert parsed["event_id"] == record["event_id"]
        assert parsed["seq"] == record["seq"]

        stats = st.stats()
        assert stats["dropped_total"] == 0
        assert stats["flush_count"] >= 1
        assert stats["bytes_written"] > 0
    finally:
        st.shutdown()


def test_multiple_categories_write_to_separate_files(tmp_path):
    st = store.Store(root=tmp_path, run_id="multicat00000001", flush_interval_s=0.1, flush_batch=10)
    try:
        st.enqueue(_rec(st.run_id, category="meta"))
        st.enqueue(_rec(st.run_id, category="gate"))
        st.shutdown(timeout=5)

        events_dir = tmp_path / "events"
        assert list(events_dir.rglob(f"meta.{st.run_id}.jsonl"))
        assert list(events_dir.rglob(f"gate.{st.run_id}.jsonl"))
    finally:
        st.shutdown()


def test_ring_buffer_full_is_dropped_and_counted(tmp_path):
    """Deterministic, not timing-dependent: forces queue.Full directly
    rather than racing a real background writer thread to fill the
    buffer first."""
    st = store.Store(root=tmp_path, run_id="ringfull00000001")
    try:
        def _always_full(_item):
            raise queue.Full()

        st._queue.put_nowait = _always_full  # type: ignore[assignment]

        st.enqueue(_rec(st.run_id, category="gate"))
        st.enqueue(_rec(st.run_id, category="gate"))
        st.enqueue(_rec(st.run_id, category="device"))

        stats = st.stats()
        assert stats["dropped_total"] == 3
        assert stats["dropped_by_category"]["gate"] == 2
        assert stats["dropped_by_category"]["device"] == 1
    finally:
        st.shutdown()


def test_enqueue_never_raises_on_malformed_record(tmp_path):
    st = store.Store(root=tmp_path, run_id="malformed0000001")
    try:
        # Not a dict at all — enqueue must not raise into the caller.
        st.enqueue("not-a-record")  # type: ignore[arg-type]
        st.enqueue(None)  # type: ignore[arg-type]
        stats = st.stats()
        assert stats["dropped_total"] >= 0  # did not raise; that's the assertion
    finally:
        st.shutdown()


def test_write_failure_degrades_to_dropped_count_not_exception(tmp_path):
    st = store.Store(root=tmp_path, run_id="writefail0000001", flush_interval_s=0.1, flush_batch=10)
    try:
        def _boom(_date_str, _category):
            raise OSError("simulated disk failure")

        st._path_for = _boom  # type: ignore[assignment]

        record = _rec(st.run_id)
        st.enqueue(record)  # must not raise despite the writer thread
        # failing on every write attempt for this record

        deadline = time.monotonic() + 5
        while st.stats()["dropped_total"] == 0 and time.monotonic() < deadline:
            time.sleep(0.05)

        stats = st.stats()
        assert stats["dropped_total"] >= 1
        assert stats["dropped_by_category"].get("meta", 0) >= 1
        # The writer thread itself must have survived the failure.
        assert st._thread.is_alive()
    finally:
        st.shutdown()


def test_buffer_high_water_tracks_peak_occupancy(tmp_path):
    st = store.Store(root=tmp_path, run_id="highwater00000a", flush_interval_s=10, flush_batch=1000)
    try:
        for _ in range(5):
            st.enqueue(_rec(st.run_id))
        # Give the writer a brief window; high water should have observed
        # at least 1 item queued at some point regardless of drain speed.
        deadline = time.monotonic() + 2
        while st.stats()["buffer_high_water"] == 0 and time.monotonic() < deadline:
            time.sleep(0.02)
        assert st.stats()["buffer_high_water"] >= 1
    finally:
        st.shutdown()


def test_shutdown_is_idempotent(tmp_path):
    st = store.Store(root=tmp_path, run_id="idempotent00000")
    st.shutdown()
    st.shutdown()  # must not raise or hang the second time


# ── kill switch ──────────────────────────────────────────────────────────

def test_kill_switch_disabled_produces_zero_records(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "TELEMETRY_ENABLED", False)
    monkeypatch.setattr(store, "METRICS_DIR", tmp_path)

    record = _rec("killswitchoff01")
    store.record(record)
    store.record(record)

    assert store._singleton_store is None
    assert not (tmp_path / "events").exists()


def test_kill_switch_enabled_writes_records(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "TELEMETRY_ENABLED", True)
    monkeypatch.setattr(store, "METRICS_DIR", tmp_path)

    record = _rec("killswitchon001", category="meta")
    store.record(record)

    deadline = time.monotonic() + 5
    while not list((tmp_path / "events").rglob("meta.*.jsonl")) and time.monotonic() < deadline:
        time.sleep(0.05)

    files = list((tmp_path / "events").rglob("meta.*.jsonl"))
    assert files, "expected at least one meta jsonl file to have been written"


def test_get_run_id_is_stable_within_process(monkeypatch):
    store.reset_for_tests()
    r1 = store.get_run_id()
    r2 = store.get_run_id()
    assert r1 == r2
    assert len(r1) == 16


# ── NEW-358: claim_run_start()/mark_run_start_recorded() ───────────────────


def test_claim_run_start_true_once_then_false():
    """First caller in the process claims it; every subsequent caller in
    the same process gets False -- the one-shot CAS core/loader_v2.py's
    fallback depends on."""
    assert store.claim_run_start() is True
    assert store.claim_run_start() is False
    assert store.claim_run_start() is False


def test_reset_for_tests_resets_claim_run_start():
    assert store.claim_run_start() is True
    store.reset_for_tests()
    assert store.claim_run_start() is True


def test_mark_run_start_recorded_then_claim_returns_false():
    """Simulates the real-caller-ran-first case (core/daemon.py,
    main.py's default repl path): once mark_run_start_recorded() has been
    called, claim_run_start() must report the flag as already taken."""
    store.mark_run_start_recorded()
    assert store.claim_run_start() is False


def test_unclaim_run_start_allows_a_fresh_claim():
    """A claim released by unclaim_run_start() (e.g. after the claiming
    caller's own record_run_start() attempt failed) must be re-claimable
    -- code-reviewer round 1 finding: without this, a single transient
    failure permanently latches the flag True, silently reintroducing
    NEW-358's own orphaned-run_start bug for the rest of the process."""
    assert store.claim_run_start() is True
    assert store.claim_run_start() is False  # already claimed
    store.unclaim_run_start()
    assert store.claim_run_start() is True  # released, claimable again
