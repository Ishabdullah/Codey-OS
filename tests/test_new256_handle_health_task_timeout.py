"""
NEW-256 — `core/daemon.py`'s `DaemonServer._handle_health()` used to hardcode
its stuck-task threshold to a literal `1800` instead of reading the same
`task_timeout` config key `_handle_status()`'s `running_active` filter (and
`_process_planner_tasks()`) already read — so the two call sites silently
disagreed about which running tasks count as "stuck" whenever `task_timeout`
was ever configured away from its default.

Mirrors `tests/test_new145_149_155_option_c.py`'s `_handle_status()`
`running_active` tests (same fake-state/fake-config shape, same "use a
non-default task_timeout so a hardcode-masking coincidence can't pass"
negative-control design) — see that file's
`test_handle_status_running_active_reads_configured_non_default_timeout` for
the full rationale this borrows.

Patches the module-level `core.daemon.get_config` singleton (what
`_handle_health()` actually reads), not `handler._config` — `DaemonServer`
never sets that attribute.
"""
import asyncio
import time
from unittest.mock import patch

import core.daemon as daemon_mod


def _run(coro):
    return asyncio.run(coro)


class _FakeState:
    def __init__(self, all_tasks):
        self._all_tasks = all_tasks

    def get_all_tasks(self):
        return self._all_tasks

    def get_recent_actions(self, limit=50):
        return []

    def get(self, key, default=None):
        return default


class _FakeConfig:
    def __init__(self, task_timeout=1800):
        self._task_timeout = task_timeout

    def get(self, section, key, default=None):
        if section == "tasks" and key == "task_timeout":
            return self._task_timeout
        return default


def _handler(all_tasks):
    handler = daemon_mod.DaemonServer.__new__(daemon_mod.DaemonServer)
    handler.state = _FakeState(all_tasks)
    return handler


def test_handle_health_stuck_tasks_uses_default_timeout():
    now = int(time.time())
    fresh = {"id": 1, "status": "running", "started_at": now - 10}
    stale = {"id": 2, "status": "running", "started_at": now - 5000}
    handler = _handler([fresh, stale])

    with patch.object(daemon_mod, "get_config", return_value=_FakeConfig(task_timeout=1800)):
        result = _run(handler._handle_health({}))

    assert result["tasks"]["stuck"] == [2]


def test_handle_health_stuck_tasks_reads_configured_non_default_timeout():
    """Negative control: a task 100s old must be reported stuck against a
    configured 60s task_timeout, but would NOT be under the old hardcoded
    1800s literal — a silent hardcode would make this test fail (stuck
    list would incorrectly stay empty)."""
    now = int(time.time())
    task = {"id": 1, "status": "running", "started_at": now - 100}
    handler = _handler([task])

    with patch.object(daemon_mod, "get_config", return_value=_FakeConfig(task_timeout=60)):
        result = _run(handler._handle_health({}))

    assert result["tasks"]["stuck"] == [1]


def test_handle_health_stuck_tasks_empty_when_within_configured_timeout():
    now = int(time.time())
    task = {"id": 1, "status": "running", "started_at": now - 100}
    handler = _handler([task])

    with patch.object(daemon_mod, "get_config", return_value=_FakeConfig(task_timeout=1800)):
        result = _run(handler._handle_health({}))

    assert result["tasks"]["stuck"] == []
