"""
Bounded ring buffer + background writer thread + O_APPEND JSONL writes +
kill switch. This module is the only place in the telemetry package that
touches the filesystem or spawns a thread, and it does neither at import
time (see `_get_or_create_store()` — lazy, on first `record()` call).

Every public entry point here is exception-proof: a failure anywhere in
enqueue or write degrades to a dropped-record count plus a rate-limited
warning, never an exception propagating into the caller's hot path
(inference / gate / daemon code in later sub-tasks). This is constraint 2
of the T0 brief, not an optional nicety.
"""

from __future__ import annotations

import atexit
import json
import queue
import threading
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from utils.config import CODEY_TELEMETRY_ENABLED, METRICS_DIR
from utils.logger import warning

# Module-level boolean, read once from utils.config at import (which itself
# read the environment once at ITS import) — not re-read per record. A
# test may monkeypatch this attribute directly to flip the kill switch
# without re-importing the module (docs/telemetry_layer_design.md §5.3:
# "checked once at import ... stored in a module-level boolean").
TELEMETRY_ENABLED: bool = CODEY_TELEMETRY_ENABLED

DEFAULT_RING_BUFFER_SIZE = 512
DEFAULT_FLUSH_INTERVAL_S = 2.0
DEFAULT_FLUSH_BATCH = 64
DROP_WARNING_MIN_INTERVAL_S = 60.0


def new_run_id() -> str:
    """16 lowercase hex chars, per schema v1's run_id format."""
    return uuid.uuid4().hex[:16]


class Store:
    """
    One Store = one writer for the whole life of one run_id (design §3.2:
    "every file has exactly one writer for its whole life" — no lock, no
    cross-process coordination needed). A process constructs at most one
    Store via the module-level singleton; tests construct extra ones
    pointed at a tmp_path root.
    """

    def __init__(
        self,
        root: Path,
        run_id: str,
        ring_buffer_size: int = DEFAULT_RING_BUFFER_SIZE,
        flush_interval_s: float = DEFAULT_FLUSH_INTERVAL_S,
        flush_batch: int = DEFAULT_FLUSH_BATCH,
    ) -> None:
        self.root = Path(root)
        self.run_id = run_id
        self._flush_interval_s = flush_interval_s
        self._flush_batch = flush_batch

        # queue.Queue (not a bare deque) so a full buffer can be detected
        # and counted via queue.Full rather than silently discarding the
        # oldest record the way a deque(maxlen=N) would — the drop count
        # is a required, load-bearing part of the contract (constraint 2),
        # not an optimization.
        self._queue: "queue.Queue[Dict[str, Any]]" = queue.Queue(maxsize=ring_buffer_size)

        self._stats_lock = threading.Lock()
        self._dropped_total = 0
        self._dropped_by_category: Dict[str, int] = defaultdict(int)
        self._buffer_high_water = 0
        self._flush_count = 0
        self._bytes_written = 0
        self._last_drop_warn_ts = 0.0

        self._stop_event = threading.Event()
        self._stopped = False
        self._thread = threading.Thread(
            target=self._writer_loop, name="telemetry-writer", daemon=True
        )
        self._thread.start()
        atexit.register(self.shutdown)

    # ── public API ───────────────────────────────────────────────────────

    def enqueue(self, record: Dict[str, Any]) -> None:
        """
        Never raises. On any failure — full buffer, or something wrong
        with the record itself — counts a drop and returns.
        """
        try:
            self._queue.put_nowait(record)
            with self._stats_lock:
                self._buffer_high_water = max(self._buffer_high_water, self._queue.qsize())
        except queue.Full:
            self._record_drop(_safe_category(record), "ring_buffer_full")
        except Exception:
            # Anything else (e.g. a caller passed a non-dict) must not
            # propagate into the instrumented call site — that call site
            # is doing real work (inference, gate decisions) and cannot
            # be made to fail because measurement failed.
            self._record_drop(_safe_category(record), "serialize_failed")

    def stats(self) -> Dict[str, Any]:
        with self._stats_lock:
            return {
                "dropped_total": self._dropped_total,
                "dropped_by_category": dict(self._dropped_by_category),
                "buffer_high_water": self._buffer_high_water,
                "flush_count": self._flush_count,
                "bytes_written": self._bytes_written,
            }

    def shutdown(self, timeout: float = 5.0) -> None:
        """Flush what's buffered, stop the thread, and join with a bound.
        Registered with atexit; also callable directly by tests."""
        if self._stopped:
            return
        self._stopped = True
        self._stop_event.set()
        self._thread.join(timeout=timeout)

    # ── internals ────────────────────────────────────────────────────────

    def _record_drop(self, category: str, reason: str) -> None:
        with self._stats_lock:
            self._dropped_total += 1
            self._dropped_by_category[category] += 1
            total = self._dropped_total
            now = time.monotonic()
            should_warn = total == 1 or (now - self._last_drop_warn_ts) >= DROP_WARNING_MIN_INTERVAL_S
            if should_warn:
                self._last_drop_warn_ts = now
        if should_warn:
            # Rate-limited (§2.meta: "records_dropped is emitted on the
            # first drop and then at most once per 60s") so a sustained
            # drop condition doesn't itself become a console/log-spam
            # problem on top of the data loss it's reporting.
            try:
                warning(
                    f"telemetry: dropped record (category={category}, reason={reason}), "
                    f"dropped_total={total} this run"
                )
            except Exception:
                # _record_drop is called from enqueue()'s except blocks,
                # which must never raise (enqueue's own docstring: "Never
                # raises") — a failure in the logger itself (e.g. a
                # broken/closed stream) must not propagate into the
                # instrumented call site on top of the drop it's
                # reporting.
                pass

    def _writer_loop(self) -> None:
        while not self._stop_event.is_set():
            batch = self._collect_batch()
            if batch:
                self._write_batch(batch)
        # Drain whatever is left in the queue on shutdown — best-effort,
        # bounded by whatever is already enqueued (no new records can
        # arrive after _stop_event is set and callers stop enqueueing).
        final_batch = self._collect_batch(block=False)
        if final_batch:
            self._write_batch(final_batch)

    def _collect_batch(self, block: bool = True) -> List[Dict[str, Any]]:
        batch: List[Dict[str, Any]] = []
        deadline = time.monotonic() + self._flush_interval_s
        while len(batch) < self._flush_batch:
            remaining = deadline - time.monotonic()
            if not block or remaining <= 0:
                try:
                    batch.append(self._queue.get_nowait())
                except queue.Empty:
                    break
            else:
                try:
                    batch.append(self._queue.get(timeout=remaining))
                except queue.Empty:
                    break
        return batch

    def _write_batch(self, batch: List[Dict[str, Any]]) -> None:
        by_category_and_date: Dict[Any, List[Dict[str, Any]]] = defaultdict(list)
        for rec in batch:
            try:
                date_str = _date_for_record(rec)
                category = _safe_category(rec)
                by_category_and_date[(date_str, category)].append(rec)
            except Exception:
                # A malformed record (e.g. enqueue() was handed a non-dict
                # — enqueue() itself only guards against a full buffer,
                # not a malformed payload) must not crash the writer
                # thread's grouping pass, which would silently stop ALL
                # future telemetry for this run with no further signal.
                self._record_drop(_safe_category(rec), "serialize_failed")

        for (date_str, category), records in by_category_and_date.items():
            try:
                path = self._path_for(date_str, category)
                path.parent.mkdir(parents=True, exist_ok=True)
                # O_APPEND: append-only at the OS level, no seek/rewrite
                # possible via this handle. No fsync per event (constraint
                # 3 / design §5.2) — fdatasync happens only at rotation
                # boundaries and writer_stopped (T4), not here.
                with open(path, "a", encoding="utf-8") as f:
                    written = 0
                    for rec in records:
                        line = json.dumps(rec, separators=(",", ":"), default=str)
                        f.write(line)
                        f.write("\n")
                        written += len(line) + 1
                with self._stats_lock:
                    self._flush_count += 1
                    self._bytes_written += written
            except Exception as exc:
                # A write failure (disk full, permission change, etc.)
                # degrades to counted drops for this sub-batch — it must
                # never kill the writer thread, since that would silently
                # stop ALL future telemetry with no further signal.
                for rec in records:
                    self._record_drop(category, "write_failed")
                warning(f"telemetry: write batch failed for category={category}: {exc!r}")

    def _path_for(self, date_str: str, category: str) -> Path:
        return self.root / "events" / date_str / f"{category}.{self.run_id}.jsonl"


def _safe_category(record: Any) -> str:
    if isinstance(record, dict):
        category = record.get("category")
        if isinstance(category, str) and category:
            return category
    return "unknown"


def _date_for_record(record: Dict[str, Any]) -> str:
    ts_wall = record.get("ts_wall")
    try:
        dt = datetime.fromtimestamp(float(ts_wall), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        # Malformed/missing ts_wall must not lose the record entirely —
        # fall back to "now" so it still lands somewhere on disk rather
        # than being dropped for a cosmetic reason.
        dt = datetime.now(tz=timezone.utc)
    return dt.strftime("%Y-%m-%d")


# ── process-wide singleton ──────────────────────────────────────────────

_singleton_lock = threading.Lock()
_singleton_store: Optional[Store] = None
_singleton_run_id: Optional[str] = None

# NEW-358: deliberately a separate lock from _singleton_lock. get_run_id()
# above documents that _singleton_lock is not reentrant and that acquiring
# it from inside another acquisition of itself deadlocks the first record()
# on a fresh process. claim_run_start()/mark_run_start_recorded() guard an
# unrelated flag and must not be coupled to that same reentrancy hazard for
# no benefit.
_run_start_lock = threading.Lock()
_run_start_recorded: bool = False


def mark_run_start_recorded() -> None:
    """
    Unconditional set, called by recorders.record_run_start() itself once
    it has actually emitted a run_start record for this process -- not a
    claim/guard, just a breadcrumb. Zero behavior change for
    record_run_start()'s existing real callers (core/daemon.py,
    main.py's default repl path), which always emit regardless of this
    flag's prior state.
    """
    global _run_start_recorded
    with _run_start_lock:
        _run_start_recorded = True


def claim_run_start() -> bool:
    """
    Atomic test-and-set, exposed ONLY for core/loader_v2.py's
    load_primary() fallback (NEW-358): returns True if no run_start has
    been recorded yet for this process (and atomically marks the flag
    CLAIMED, so a second concurrent caller of this specific function
    gets False), False otherwise. Claimed is not the same as recorded --
    a True return is permission to attempt record_run_start(), not proof
    it succeeded; a caller whose subsequent attempt fails must call
    unclaim_run_start() to release the claim for a future retry (see
    core/loader_v2.py::_ensure_run_start_fallback() for that pattern).
    recorders.record_run_start() does NOT call this -- it always emits
    unconditionally (see mark_run_start_recorded()) so a future
    per-caller record_run_start() call (e.g. if core/lora_import.py is
    later given its own richer-identity call, per NEW-358's deferred
    note) is never silently suppressed by an earlier loader-side
    fallback having already claimed the flag.

    Deliberately NOT the same signal as get_run_id() having minted a
    run_id: get_run_id() is invoked by many OTHER telemetry emissions
    (e.g. loader_v2._emit_gate_telemetry()'s record_gate_decision(),
    which runs earlier in load_primary() than the argv-provenance
    emission) well before any caller gets around to calling
    record_run_start() -- "a run_id exists" is not a valid proxy for
    "record_run_start() ran."

    Uses a dedicated lock (_run_start_lock), NOT _singleton_lock -- see
    get_run_id()'s docstring above for the reentrancy/deadlock hazard of
    reusing that lock for an unrelated flag.
    """
    global _run_start_recorded
    with _run_start_lock:
        if _run_start_recorded:
            return False
        _run_start_recorded = True
        return True


def unclaim_run_start() -> None:
    """
    Releases a claim taken by claim_run_start() when the emission it was
    guarding never actually happened -- e.g. loader_v2._ensure_run_start_
    fallback()'s record_run_start() call raised before write_run_
    provenance() ever ran, so mark_run_start_recorded() was never reached.
    Without this, a single transient failure (git/getprop subprocess
    trouble in build_run_start_body(), for instance) would permanently
    latch the flag True for the rest of the process's life -- silently
    reintroducing the exact orphaned-run_start_amended gap NEW-358 exists
    to close, for every subsequent load_primary() call in that process
    (e.g. an unload/reload cycle), with no way to retry.

    The only caller is _ensure_run_start_fallback()'s own except block,
    which only runs when its OWN record_run_start() call raised -- and
    record_run_start() calls mark_run_start_recorded() strictly after
    write_run_provenance() succeeds, so a raised call never reached that
    mark. Not made fully safe against every theoretical interleaving: if
    a second thread in the same process independently completed a real,
    successful record_run_start() call in the narrow window between this
    caller's claim and its own failed emission, this unclaim would
    incorrectly clear that success too. Not guarded against, because the
    consequence is bounded and already accepted elsewhere in this design
    (NEW-358's fix direction already treats a possible duplicate
    run_start as the safer failure mode vs. a silently-dropped one, and
    codey-metrics doctor already flags duplicate_run_start_runs
    non-fatally) -- worth revisiting only if this ever becomes a genuine
    multi-threaded call pattern, which it is not today.
    """
    global _run_start_recorded
    with _run_start_lock:
        _run_start_recorded = False


def get_run_id() -> str:
    """
    Lazily allocates this process's run_id on first use — not at import,
    per constraint 5's ban on any import-time side effect. Cached for the
    life of the process.
    """
    global _singleton_run_id
    if _singleton_run_id is None:
        with _singleton_lock:
            if _singleton_run_id is None:
                _singleton_run_id = new_run_id()
    return _singleton_run_id


def _get_or_create_store() -> Optional[Store]:
    global _singleton_store
    if not TELEMETRY_ENABLED:
        return None
    if _singleton_store is None:
        # get_run_id() must be resolved BEFORE acquiring _singleton_lock:
        # it takes the same lock itself, and threading.Lock is not
        # reentrant — calling it from inside the `with` block below
        # deadlocked the very first record() on a fresh process (caught
        # by tests/test_telemetry_store.py's kill-switch-enabled test).
        run_id = get_run_id()
        with _singleton_lock:
            if _singleton_store is None:
                try:
                    _singleton_store = Store(root=METRICS_DIR, run_id=run_id)
                except Exception as exc:
                    # Even Store construction (thread start, directory
                    # object setup) must not take down the caller —
                    # telemetry is diagnostic, never load-bearing.
                    warning(f"telemetry: failed to initialize store: {exc!r}")
                    return None
    return _singleton_store


def record(rec: Dict[str, Any]) -> None:
    """
    The single write entry point every telemetry/recorders.py function
    funnels through. No-ops immediately (no store, no thread, no
    directory) when TELEMETRY_ENABLED is False.
    """
    if not TELEMETRY_ENABLED:
        return
    store = _get_or_create_store()
    if store is None:
        return
    store.enqueue(rec)


def write_run_provenance(record: Dict[str, Any], root: Optional[Path] = None) -> None:
    """
    Design §3.1: `runs/<run_id>.json` — written once, never reopened for
    write. This is a direct, synchronous write (not routed through the
    ring buffer / background writer thread) because it must exist even if
    the process exits abruptly before the writer thread's first flush —
    provenance is meant to be the first durable fact about a run, not
    something that can be lost to the same 2s buffering window as every
    other record. Exception-wrapped like every other public entry point
    in this module (constraint 2 / T0 brief): a failure here degrades to
    a logged warning, never a crash of whatever called record_run_start().

    No-ops (writes nothing) when telemetry is disabled or the record has
    no run_id, and refuses to overwrite an existing file for the same
    run_id — `run_id` is allocated once per process (store.get_run_id()),
    so a second write attempt would only happen from a bug, and silently
    clobbering the first file would destroy evidence rather than protect
    it.
    """
    if not TELEMETRY_ENABLED:
        return
    run_id = record.get("run_id")
    if not run_id:
        return
    base = Path(root) if root is not None else METRICS_DIR
    path = base / "runs" / f"{run_id}.json"
    try:
        if path.exists():
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_name(path.name + ".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(record, f, separators=(",", ":"), default=str)
        tmp_path.replace(path)
    except Exception as exc:
        # Disk full, permission change, etc. — the run_start record is
        # still enqueued into the normal JSONL stream via record(), so
        # this failure only loses the runs/<id>.json convenience copy,
        # not the evidence itself. Never raised into the caller.
        warning(f"telemetry: failed to write run provenance file for run_id={run_id}: {exc!r}")


def reset_for_tests() -> None:
    """
    Test-only. Shuts down and discards the process-wide singleton so a
    subsequent test's `record()` calls create a fresh Store (e.g. after
    monkeypatching TELEMETRY_ENABLED or METRICS_DIR). Not part of the
    production API.
    """
    global _singleton_store, _singleton_run_id, _run_start_recorded
    with _singleton_lock:
        if _singleton_store is not None:
            _singleton_store.shutdown()
        _singleton_store = None
        _singleton_run_id = None
    with _run_start_lock:
        _run_start_recorded = False
