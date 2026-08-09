"""
core/daemon.py's `DaemonServer._handle_release_model_slot()` — TODO.md 7.4
sub-task 4 (the NEW-69 prerequisite: a daemon-side command an external
process, e.g. the CLI in sub-task 5, can use to ask the daemon to free a
model slot).

No real llama-server subprocess and no real resource_gate state store are
touched anywhere in this file (CLAUDE.md rule 2 RAM discipline) — the
loader, thermal manager, and SWAP_GUARD are all faked/patched. Coroutines
are driven directly via `asyncio.run()` since this project has no
pytest-asyncio dependency (see other daemon tests / grep for `async def
test_` before assuming otherwise).
"""
import asyncio
from unittest.mock import MagicMock, patch

import pytest

import core.daemon as daemon_mod
import core.loader_v2 as loader_v2_mod


class FakeLoader:
    """Stand-in for ModelLoader/PlannerLoader exposing is_loaded()/unload()."""

    def __init__(self, loaded: bool, unload_raises: Exception = None):
        self._loaded = loaded
        self._unload_raises = unload_raises
        self.unload_calls = 0

    def is_loaded(self) -> bool:
        return self._loaded

    def unload(self):
        self.unload_calls += 1
        if self._unload_raises:
            raise self._unload_raises
        self._loaded = False


def _server():
    return daemon_mod.DaemonServer(state=MagicMock())


def _run(coro):
    return asyncio.run(coro)


def _idle_thermal():
    tm = MagicMock()
    tm.is_inference_active.return_value = False
    return tm


@pytest.fixture(autouse=True)
def _released_swap_guard():
    """Ensure SWAP_GUARD starts (and ends) unheld across every test in this
    file — a leaked hold from a failed test would wrongly report every
    subsequent test's request as busy_swap_in_flight."""
    assert loader_v2_mod.SWAP_GUARD.acquire(blocking=False)
    loader_v2_mod.SWAP_GUARD.release()
    yield
    # Defensive: release again if a failing test left it held, so later
    # tests in the same run aren't spuriously affected.
    if loader_v2_mod.SWAP_GUARD.acquire(blocking=False):
        loader_v2_mod.SWAP_GUARD.release()


def test_invalid_model_id_is_error():
    server = _server()
    resp = _run(server._handle_release_model_slot({"model_id": "nonsense"}))
    assert resp["status"] == "error"
    assert resp["released"] is False
    assert resp["outcome"] == daemon_mod.RELEASE_OUTCOME_INVALID_MODEL


def test_missing_model_id_is_error():
    server = _server()
    resp = _run(server._handle_release_model_slot({}))
    assert resp["status"] == "error"
    assert resp["outcome"] == daemon_mod.RELEASE_OUTCOME_INVALID_MODEL


def test_declines_when_task_actively_inferring():
    server = _server()
    tm = MagicMock()
    tm.is_inference_active.return_value = True
    fake_loader = FakeLoader(loaded=True)

    with patch("core.thermal.get_thermal_manager", return_value=tm), patch(
        "core.loader_v2.get_loader", return_value=fake_loader
    ):
        resp = _run(server._handle_release_model_slot({"model_id": "primary"}))

    assert resp["status"] == "ok"
    assert resp["released"] is False
    assert resp["outcome"] == daemon_mod.RELEASE_OUTCOME_BUSY_TASK
    # Must never even attempt the unload while busy.
    assert fake_loader.unload_calls == 0


def test_thermal_check_exception_fails_closed_to_busy():
    server = _server()
    fake_loader = FakeLoader(loaded=True)

    with patch("core.thermal.get_thermal_manager", side_effect=RuntimeError("boom")), patch(
        "core.loader_v2.get_loader", return_value=fake_loader
    ):
        resp = _run(server._handle_release_model_slot({"model_id": "primary"}))

    assert resp["status"] == "ok"
    assert resp["released"] is False
    assert resp["outcome"] == daemon_mod.RELEASE_OUTCOME_BUSY_TASK
    assert fake_loader.unload_calls == 0


def test_declines_when_swap_guard_held():
    server = _server()
    fake_loader = FakeLoader(loaded=True)

    # Simulate another thread mid-swap (ensure_model()/ensure_planner()
    # holds SWAP_GUARD for their entire body).
    assert loader_v2_mod.SWAP_GUARD.acquire(blocking=False)
    try:
        with patch("core.thermal.get_thermal_manager", return_value=_idle_thermal()), patch(
            "core.loader_v2.get_loader", return_value=fake_loader
        ):
            resp = _run(server._handle_release_model_slot({"model_id": "primary"}))
    finally:
        loader_v2_mod.SWAP_GUARD.release()

    assert resp["status"] == "ok"
    assert resp["released"] is False
    assert resp["outcome"] == daemon_mod.RELEASE_OUTCOME_BUSY_SWAP
    assert fake_loader.unload_calls == 0


def test_already_unloaded_is_clean_noop_success():
    server = _server()
    fake_loader = FakeLoader(loaded=False)

    with patch("core.thermal.get_thermal_manager", return_value=_idle_thermal()), patch(
        "core.loader_v2.get_loader", return_value=fake_loader
    ):
        resp = _run(server._handle_release_model_slot({"model_id": "primary"}))

    assert resp["status"] == "ok"
    assert resp["released"] is False
    assert resp["outcome"] == daemon_mod.RELEASE_OUTCOME_ALREADY_UNLOADED
    assert fake_loader.unload_calls == 0


def test_successful_release_confirmed_freed():
    server = _server()
    fake_loader = FakeLoader(loaded=True)

    with patch("core.thermal.get_thermal_manager", return_value=_idle_thermal()), patch(
        "core.loader_v2.get_loader", return_value=fake_loader
    ), patch("core.loader_v2.probe_port_health", return_value=False):
        resp = _run(server._handle_release_model_slot({"model_id": "primary"}))

    assert resp["status"] == "ok"
    assert resp["released"] is True
    assert resp["outcome"] == daemon_mod.RELEASE_OUTCOME_RELEASED
    assert fake_loader.unload_calls == 1
    assert not fake_loader.is_loaded()


def test_release_of_planner_routes_to_planner_loader():
    server = _server()
    primary_loader = FakeLoader(loaded=True)
    planner_loader = FakeLoader(loaded=True)

    with patch("core.thermal.get_thermal_manager", return_value=_idle_thermal()), patch(
        "core.loader_v2.get_loader", return_value=primary_loader
    ), patch(
        "core.planner_loader.get_planner_loader", return_value=planner_loader
    ), patch("core.loader_v2.probe_port_health", return_value=False):
        resp = _run(server._handle_release_model_slot({"model_id": "planner"}))

    assert resp["outcome"] == daemon_mod.RELEASE_OUTCOME_RELEASED
    assert planner_loader.unload_calls == 1
    assert primary_loader.unload_calls == 0


def test_unload_exception_returns_error_and_releases_swap_guard():
    server = _server()
    fake_loader = FakeLoader(loaded=True, unload_raises=RuntimeError("spawn gone wrong"))

    with patch("core.thermal.get_thermal_manager", return_value=_idle_thermal()), patch(
        "core.loader_v2.get_loader", return_value=fake_loader
    ):
        resp = _run(server._handle_release_model_slot({"model_id": "primary"}))

    assert resp["status"] == "error"
    assert resp["released"] is False
    assert resp["outcome"] == daemon_mod.RELEASE_OUTCOME_ERROR
    # SWAP_GUARD must be released even though unload() raised.
    assert loader_v2_mod.SWAP_GUARD.acquire(blocking=False)
    loader_v2_mod.SWAP_GUARD.release()


def test_unconfirmed_release_reported_distinctly():
    server = _server()
    fake_loader = FakeLoader(loaded=True)

    with patch("core.thermal.get_thermal_manager", return_value=_idle_thermal()), patch(
        "core.loader_v2.get_loader", return_value=fake_loader
    ), patch("core.loader_v2.probe_port_health", return_value=True), patch.object(
        daemon_mod, "RELEASE_CONFIRM_TIMEOUT_S", 0.05
    ), patch.object(daemon_mod, "RELEASE_CONFIRM_POLL_INTERVAL_S", 0.02):
        resp = _run(server._handle_release_model_slot({"model_id": "primary"}))

    assert resp["status"] == "ok"
    assert resp["released"] is False
    assert resp["outcome"] == daemon_mod.RELEASE_OUTCOME_UNCONFIRMED
    # unload() was still called even though we couldn't confirm the port
    # stopped answering in time.
    assert fake_loader.unload_calls == 1


def test_cooldown_declines_immediate_repeat_release():
    server = _server()
    fake_loader = FakeLoader(loaded=True)

    with patch("core.thermal.get_thermal_manager", return_value=_idle_thermal()), patch(
        "core.loader_v2.get_loader", return_value=fake_loader
    ), patch("core.loader_v2.probe_port_health", return_value=False):
        first = _run(server._handle_release_model_slot({"model_id": "primary"}))
        assert first["outcome"] == daemon_mod.RELEASE_OUTCOME_RELEASED

        # Re-loaded between requests (e.g. watchdog reload) so a second
        # release attempt is otherwise legitimate — cooldown should still
        # decline it since it's within the window.
        fake_loader._loaded = True
        second = _run(server._handle_release_model_slot({"model_id": "primary"}))

    assert second["status"] == "ok"
    assert second["released"] is False
    assert second["outcome"] == daemon_mod.RELEASE_OUTCOME_COOLDOWN
    # unload() must not have been called a second time.
    assert fake_loader.unload_calls == 1


def test_busy_decline_does_not_arm_cooldown():
    """A busy decline must not burn the cooldown budget — a legitimate
    retry right after busy clears should not be punished for the decline."""
    server = _server()
    fake_loader = FakeLoader(loaded=True)
    busy_tm = MagicMock()
    busy_tm.is_inference_active.return_value = True
    idle_tm = _idle_thermal()

    with patch("core.loader_v2.get_loader", return_value=fake_loader), patch(
        "core.loader_v2.probe_port_health", return_value=False
    ):
        with patch("core.thermal.get_thermal_manager", return_value=busy_tm):
            busy_resp = _run(server._handle_release_model_slot({"model_id": "primary"}))
        assert busy_resp["outcome"] == daemon_mod.RELEASE_OUTCOME_BUSY_TASK

        with patch("core.thermal.get_thermal_manager", return_value=idle_tm):
            retry_resp = _run(server._handle_release_model_slot({"model_id": "primary"}))

    assert retry_resp["outcome"] == daemon_mod.RELEASE_OUTCOME_RELEASED


def test_release_model_slot_registered_as_a_handler():
    server = _server()
    assert "release_model_slot" in server._handlers
    assert server._handlers["release_model_slot"] == server._handle_release_model_slot
