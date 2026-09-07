"""
Integration tests for coding.run_agent CCOS capability wrapper (Item 4.3).

Verifies that PluginManager.call_capability("coding.run_agent", ...) works for
both interactive and daemon permission profiles without config leakage.
"""
import asyncio
from unittest.mock import MagicMock, patch
import pytest

from ccos.core.capability_registry import get_capability_registry
from ccos.core.plugin_manager import PluginManager
from core.daemon_config import DaemonConfig
from core.state import StateStore
from core.task_executor import TaskExecutor
import utils.config


@pytest.fixture(autouse=True)
def preserve_agent_config():
    saved = dict(utils.config.AGENT_CONFIG)
    try:
        yield
    finally:
        utils.config.AGENT_CONFIG.clear()
        utils.config.AGENT_CONFIG.update(saved)


def test_agent_plugin_discovery_and_registration():
    pm = PluginManager()
    assert pm.load("agent") is True

    reg = get_capability_registry()
    assert reg.get("coding.run_agent") is not None
    assert reg.get("coding.run_recursive") is not None
    assert reg.get("coding.classify_breadth") is not None


def test_interactive_permission_profile():
    pm = PluginManager()
    pm.load("agent")

    utils.config.AGENT_CONFIG["confirm_shell"] = True
    utils.config.AGENT_CONFIG["confirm_write"] = True
    utils.config.AGENT_CONFIG["_shell_fn"] = None

    captured_config = {}

    def fake_run_agent(user_message, history, **kwargs):
        captured_config["confirm_shell"] = utils.config.AGENT_CONFIG.get("confirm_shell")
        captured_config["confirm_write"] = utils.config.AGENT_CONFIG.get("confirm_write")
        captured_config["_shell_fn"] = utils.config.AGENT_CONFIG.get("_shell_fn")
        return "interactive response", [{"role": "user", "content": user_message}, {"role": "assistant", "content": "interactive response"}]

    with patch("core.agent.run_agent", side_effect=fake_run_agent):
        result = pm.call_capability(
            "coding.run_agent",
            prompt="interactive task",
            history=[],
            confirm_shell=True,
            confirm_write=True,
        )

        resp, hist = result
        assert resp == "interactive response"
        assert len(hist) == 2
        assert result.success is True

    assert captured_config["confirm_shell"] is True
    assert captured_config["confirm_write"] is True
    assert captured_config["_shell_fn"] is None

    # Global config remains unchanged
    assert utils.config.AGENT_CONFIG.get("confirm_shell") is True
    assert utils.config.AGENT_CONFIG.get("confirm_write") is True
    assert utils.config.AGENT_CONFIG.get("_shell_fn") is None


def test_daemon_permission_profile():
    pm = PluginManager()
    pm.load("agent")

    # Baseline interactive config
    utils.config.AGENT_CONFIG["confirm_shell"] = True
    utils.config.AGENT_CONFIG["confirm_write"] = True
    utils.config.AGENT_CONFIG["_shell_fn"] = None

    captured_config = {}
    daemon_shell_mock = MagicMock(return_value="daemon shell output")

    def fake_run_agent(user_message, history, **kwargs):
        captured_config["confirm_shell"] = utils.config.AGENT_CONFIG.get("confirm_shell")
        captured_config["confirm_write"] = utils.config.AGENT_CONFIG.get("confirm_write")
        captured_config["_shell_fn"] = utils.config.AGENT_CONFIG.get("_shell_fn")
        captured_config["in_subtask"] = kwargs.get("_in_subtask")
        captured_config["yolo"] = kwargs.get("yolo")
        captured_config["no_plan"] = kwargs.get("no_plan")
        return "daemon response", [{"role": "user", "content": user_message}, {"role": "assistant", "content": "daemon response"}]

    with patch("core.agent.run_agent", side_effect=fake_run_agent):
        result = pm.call_capability(
            "coding.run_agent",
            prompt="daemon step 1",
            history=[],
            yolo=True,
            no_plan=True,
            in_subtask=True,
            confirm_shell=False,
            confirm_write=False,
            shell_fn=daemon_shell_mock,
        )

        resp, hist = result
        assert resp == "daemon response"
        assert result.success is True

    # Inside run_agent, daemon permissions were active
    assert captured_config["confirm_shell"] is False
    assert captured_config["confirm_write"] is False
    assert captured_config["_shell_fn"] is daemon_shell_mock
    assert captured_config["in_subtask"] is True
    assert captured_config["yolo"] is True
    assert captured_config["no_plan"] is True

    # After execution, global config is completely restored
    assert utils.config.AGENT_CONFIG.get("confirm_shell") is True
    assert utils.config.AGENT_CONFIG.get("confirm_write") is True
    assert utils.config.AGENT_CONFIG.get("_shell_fn") is None


def test_daemon_permission_profile_restores_on_exception():
    pm = PluginManager()
    pm.load("agent")

    utils.config.AGENT_CONFIG["confirm_shell"] = True
    utils.config.AGENT_CONFIG["confirm_write"] = True
    utils.config.AGENT_CONFIG["_shell_fn"] = None

    daemon_shell_mock = MagicMock()

    def crashing_run_agent(*args, **kwargs):
        raise RuntimeError("simulated inference crash")

    with patch("core.agent.run_agent", side_effect=crashing_run_agent):
        result = pm.call_capability(
            "coding.run_agent",
            prompt="doomed task",
            history=[],
            confirm_shell=False,
            confirm_write=False,
            shell_fn=daemon_shell_mock,
        )

        assert result.success is False
        assert "simulated inference crash" in result.error

    # utils.config.AGENT_CONFIG restored despite exception
    assert utils.config.AGENT_CONFIG.get("confirm_shell") is True
    assert utils.config.AGENT_CONFIG.get("confirm_write") is True
    assert utils.config.AGENT_CONFIG.get("_shell_fn") is None


def test_task_executor_uses_capability(tmp_path):
    state = StateStore(db_path=tmp_path / "state.db")
    config = DaemonConfig()
    executor = TaskExecutor(state=state, config=config)

    utils.config.AGENT_CONFIG["confirm_shell"] = True
    utils.config.AGENT_CONFIG["confirm_write"] = True
    utils.config.AGENT_CONFIG["_shell_fn"] = None

    captured_config = {}

    def fake_run_agent(user_message, history, **kwargs):
        captured_config["confirm_shell"] = utils.config.AGENT_CONFIG.get("confirm_shell")
        captured_config["confirm_write"] = utils.config.AGENT_CONFIG.get("confirm_write")
        captured_config["_shell_fn"] = utils.config.AGENT_CONFIG.get("_shell_fn")
        captured_config["in_subtask"] = kwargs.get("_in_subtask")
        return "step completed", history

    with patch("core.agent.run_agent", side_effect=fake_run_agent):
        resp = asyncio.run(executor._execute_task("Build feature X"))
        assert resp == "step completed"

    assert captured_config["confirm_shell"] is False
    assert captured_config["confirm_write"] is False
    assert captured_config["_shell_fn"] == executor._daemon_shell
    assert captured_config["in_subtask"] is True

    # Global config restored
    assert utils.config.AGENT_CONFIG.get("confirm_shell") is True
    assert utils.config.AGENT_CONFIG.get("confirm_write") is True
    assert utils.config.AGENT_CONFIG.get("_shell_fn") is None


def test_recursive_and_breadth_capabilities():
    pm = PluginManager()
    pm.load("agent")

    # coding.classify_breadth
    assert pm.call_capability("coding.classify_breadth", user_message="hello") == "minimal"
    assert pm.call_capability("coding.classify_breadth", user_message="build a database with auth and test suite") == "deep"

    # coding.run_recursive with mocked recursive_infer
    with patch("core.recursive.recursive_infer", return_value="refined code") as mock_rec:
        res = pm.call_capability("coding.run_recursive", messages=[{"role": "user", "content": "write code"}])
        assert res == "refined code"
        mock_rec.assert_called_once()


def test_task_executor_raises_on_agent_failure(tmp_path):
    state = StateStore(db_path=tmp_path / "state.db")
    config = DaemonConfig()
    executor = TaskExecutor(state=state, config=config)

    def failing_run_agent(*args, **kwargs):
        raise RuntimeError("simulated capability failure")

    with patch("core.agent.run_agent", side_effect=failing_run_agent):
        with pytest.raises(RuntimeError, match="simulated capability failure"):
            asyncio.run(executor._execute_task("Doomed task"))

