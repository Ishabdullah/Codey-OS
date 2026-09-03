"""
Session/test-wide fixtures. Currently just one: telemetry metrics-dir
isolation (see the fixture's own docstring for why it exists).
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_telemetry_metrics_dir(tmp_path_factory, monkeypatch):
    """
    Sub-task T2 (docs/telemetry_layer_design.md) wired
    telemetry.recorders.record_run_start() into real process-start call
    sites: restoricon_core/api/server.py's RestoriconAPIServer.start()
    and main.py's TUI entry. Several existing tests exercise those call
    sites for real (e.g. tests/test_restoricon_core/test_api.py's
    `api_server` fixture calls `server.start(background=True)`) — left
    unhandled, every one of those tests would write real
    runs/<run_id>.json + model_digests.json + events/*.jsonl files into
    this device's actual ~/.codeyOS/metrics directory as a side effect of
    running the test suite. That is never intended, and it is exactly the
    kind of device-state leak CLAUDE.md rule 2's discipline exists to
    prevent (it's not a RAM/model-load concern here, but the same
    "tests must not touch real persistent device state" principle).

    Autouse + session-wide so every test, including ones that never
    mention telemetry at all, gets a throwaway directory instead of the
    real one, by default. Tests that specifically exercise telemetry
    behaviour (tests/test_telemetry_*.py) apply their own more targeted
    monkeypatch of the same module attributes on top of this — pytest's
    monkeypatch fixture composes cleanly across fixtures (LIFO teardown),
    so this does not conflict with or need to know about those.

    Also defaults TELEMETRY_ENABLED to False for the same reason, one
    level earlier: record_run_start() checks this flag FIRST, before any
    git/getprop/meminfo collection or background model-digest hashing —
    with a *fresh* isolated METRICS_DIR per test (no warm cache to hit),
    every test exercising a real run_start call site would otherwise
    spawn its own never-joined background thread hashing the full 2.74GB
    model file, accumulating across the whole test session. Tests that
    specifically need telemetry ON (tests/test_telemetry_t2_run_start.py,
    tests/test_telemetry_store.py's kill-switch-enabled cases) already
    set TELEMETRY_ENABLED=True explicitly themselves, overriding this
    default the same way they already override METRICS_DIR above.
    tests/test_telemetry_recorders.py's record_run_start()-specific tests
    needed the same explicit opt-in added to their fixture for this reason
    (see that file's _capture_store fixture).
    """
    from telemetry import provenance, store

    isolated_dir = tmp_path_factory.mktemp("telemetry_metrics_isolated")
    monkeypatch.setattr(store, "METRICS_DIR", isolated_dir)
    monkeypatch.setattr(provenance, "METRICS_DIR", isolated_dir)
    monkeypatch.setattr(store, "TELEMETRY_ENABLED", False)
    yield
    store.reset_for_tests()
