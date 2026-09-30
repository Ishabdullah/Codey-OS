"""
Session/test-wide fixtures: telemetry metrics-dir isolation, Restoricon
document-store isolation, and a hermetic llama-server binary path (see
each fixture's own docstring for why it exists).
"""

from __future__ import annotations

import sys
from pathlib import Path

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

    Autouse and function-scoped so every test, including ones that never
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


@pytest.fixture(autouse=True)
def _isolate_restoricon_doc_store_path(tmp_path, monkeypatch):
    """
    B8.6d-a wired restoricon_core's CRMService.sign_contract into a real
    filesystem write: on every successful sign it now renders and persists
    a contract PDF under get_restoricon_doc_store_path()
    (utils/config.py), which falls back to the real
    ~/.codeyOS/restoricon_documents when RESTORICON_DOC_STORE_PATH isn't
    already set. sign_contract is exercised well outside
    tests/test_restoricon_core/ too -- e.g. tests/test_customer_portal.py
    and tests/test_b4_dashboard_portal_surfaces.py both POST to
    /api/v1/portal/contracts/<id>/sign -- so this needs the same
    whole-suite scope as _isolate_telemetry_metrics_dir above, not a
    narrower per-package conftest (a first attempt at a
    tests/test_restoricon_core/conftest.py-only fixture missed those two
    files and left real PDFs in ~/.codeyOS/restoricon_documents/contracts/
    after a full-suite run). Same "tests must not touch real persistent
    device state" principle as the telemetry fixture above.

    Autouse and function-scoped so every test gets a throwaway directory
    instead of the real one, by default, with no per-test opt-in required.
    """
    monkeypatch.setenv("RESTORICON_DOC_STORE_PATH", str(tmp_path / "restoricon_documents"))


@pytest.fixture(autouse=True)
def _hermetic_llama_server_bin(tmp_path_factory, monkeypatch):
    """
    AGI_AUDIT_PLAN.md item 1.2. core.loader_v2.ModelLoader.load_primary()
    checks that the llama-server binary exists on disk BEFORE it ever
    reaches LlamaServer. Several tests patch LlamaServer with a fake (no
    real process, per CLAUDE.md rule 2) but were still failing on any
    machine without llama.cpp built (a CI runner, a fresh clone) with
    "llama-server not found", because that binary check ran first.

    When the real binary is missing, point core.loader_v2.LLAMA_SERVER_BIN
    at an empty placeholder file so the existence check passes. The
    placeholder is never executed: every test that reaches a spawn
    patches LlamaServer. When the real binary exists (e.g. on the
    device) this fixture does nothing, so device behavior is unchanged.

    Looks the module up in sys.modules rather than importing it, so tests
    that never touch the loader don't pay the import cost.
    """
    lv = sys.modules.get("core.loader_v2")
    if lv is None or Path(str(lv.LLAMA_SERVER_BIN)).exists():
        yield
        return
    placeholder = tmp_path_factory.mktemp("fake_llama_bin") / "llama-server"
    placeholder.write_text("#!/bin/sh\n")
    monkeypatch.setattr(lv, "LLAMA_SERVER_BIN", str(placeholder))
    yield
