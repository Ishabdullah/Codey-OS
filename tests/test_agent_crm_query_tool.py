"""
Dispatch-level tests for core/agent.py's `crm_query` tool
(CODEY_MASTER_PLAN.md 12.x Part C) -- mirrors tests/test_agent_capability.py's
pattern of mocking the dependency one layer down (here,
ccos.core.plugin_manager.get_plugin_manager) rather than a live Core server
(see tests/test_ccos_crm_read.py for that).
"""
import json
from unittest.mock import MagicMock, patch

import pytest

from core.agent import TOOLS, ROGUE_TAG_MAP, execute_tool, tool_crm_query


def _mock_pm(call_capability_return=None, call_capability_side_effect=None, load_return=True):
    pm = MagicMock()
    pm._modules = {}  # "not yet loaded" -- forces the load() path
    pm.load.return_value = load_return
    if call_capability_side_effect is not None:
        pm.call_capability.side_effect = call_capability_side_effect
    else:
        pm.call_capability.return_value = call_capability_return
    return pm


def test_crm_query_registered_in_tools_and_rogue_tag_map():
    assert "crm_query" in TOOLS
    assert ROGUE_TAG_MAP["crm_query"] == "crm_query"


def test_crm_query_dispatches_via_call_capability(monkeypatch):
    monkeypatch.delenv("CODEY_CRM_TOOL_ENABLED", raising=False)
    pm = _mock_pm(call_capability_return={"count": 3, "assigned_user_id": None})

    with patch("ccos.core.plugin_manager.get_plugin_manager", return_value=pm):
        result = execute_tool({"name": "crm_query", "args": {"kind": "count_open_leads"}})

    pm.load.assert_called_once_with("crm_core_query")
    pm.call_capability.assert_called_once_with("crm.count_open_leads")
    assert json.loads(result) == {"count": 3, "assigned_user_id": None}


def test_crm_query_forwards_non_kind_args_as_kwargs(monkeypatch):
    monkeypatch.delenv("CODEY_CRM_TOOL_ENABLED", raising=False)
    pm = _mock_pm(call_capability_return={"leads": [], "returned": 0, "truncated": False})

    with patch("ccos.core.plugin_manager.get_plugin_manager", return_value=pm):
        execute_tool({"name": "crm_query", "args": {"kind": "list_leads", "assigned_user_id": 7, "status": "new"}})

    pm.call_capability.assert_called_once_with("crm.list_leads", assigned_user_id=7, status="new")


def test_crm_query_rejects_unknown_kind(monkeypatch):
    monkeypatch.delenv("CODEY_CRM_TOOL_ENABLED", raising=False)
    pm = _mock_pm()

    with patch("ccos.core.plugin_manager.get_plugin_manager", return_value=pm):
        result = execute_tool({"name": "crm_query", "args": {"kind": "list_everything"}})

    assert result.startswith("[ERROR]")
    assert "Unknown crm_query kind" in result
    pm.call_capability.assert_not_called()


def test_crm_query_never_exposes_score_lead_kind(monkeypatch):
    """crm.score_lead was deliberately removed this round (see
    ccos/plugins/crm/core_query/client.py's comment) -- 'score_lead' must
    not be a dispatchable kind."""
    monkeypatch.delenv("CODEY_CRM_TOOL_ENABLED", raising=False)
    pm = _mock_pm()

    with patch("ccos.core.plugin_manager.get_plugin_manager", return_value=pm):
        result = execute_tool({"name": "crm_query", "args": {"kind": "score_lead", "lead_id": 1}})

    assert result.startswith("[ERROR]")
    assert "Unknown crm_query kind" in result


def test_crm_query_is_a_whitelist_not_a_passthrough(monkeypatch):
    """A model-supplied `kind` must never be able to reach an arbitrary
    registered capability (e.g. coding.run_agent) through this tool."""
    monkeypatch.delenv("CODEY_CRM_TOOL_ENABLED", raising=False)
    pm = _mock_pm()

    with patch("ccos.core.plugin_manager.get_plugin_manager", return_value=pm):
        result = execute_tool({"name": "crm_query", "args": {"kind": "coding.run_agent"}})

    assert result.startswith("[ERROR]")
    pm.call_capability.assert_not_called()


def test_crm_query_fails_open_on_plugin_load_failure(monkeypatch):
    monkeypatch.delenv("CODEY_CRM_TOOL_ENABLED", raising=False)
    pm = _mock_pm(load_return=False)
    pm.get_plugin.return_value = MagicMock(error="entry point not found")

    with patch("ccos.core.plugin_manager.get_plugin_manager", return_value=pm):
        result = execute_tool({"name": "crm_query", "args": {"kind": "count_open_leads"}})

    assert result.startswith("[ERROR]")
    pm.call_capability.assert_not_called()


def test_crm_query_fails_open_on_call_capability_exception(monkeypatch):
    monkeypatch.delenv("CODEY_CRM_TOOL_ENABLED", raising=False)
    pm = _mock_pm(call_capability_side_effect=RuntimeError("Core unreachable"))

    with patch("ccos.core.plugin_manager.get_plugin_manager", return_value=pm):
        result = execute_tool({"name": "crm_query", "args": {"kind": "count_open_leads"}})

    assert result.startswith("[ERROR]")
    assert "Core unreachable" in result


@pytest.mark.parametrize("off_value", ["0", "false", "False", "no", "off"])
def test_crm_query_kill_switch_off_is_a_noop(monkeypatch, off_value):
    monkeypatch.setenv("CODEY_CRM_TOOL_ENABLED", off_value)
    pm = _mock_pm(call_capability_return={"count": 99})

    with patch("ccos.core.plugin_manager.get_plugin_manager", return_value=pm):
        result = execute_tool({"name": "crm_query", "args": {"kind": "count_open_leads"}})

    assert result.startswith("[ERROR]")
    assert "disabled" in result
    pm.load.assert_not_called()
    pm.call_capability.assert_not_called()


def test_crm_query_kill_switch_default_is_on(monkeypatch):
    monkeypatch.delenv("CODEY_CRM_TOOL_ENABLED", raising=False)
    pm = _mock_pm(call_capability_return={"count": 1})

    with patch("ccos.core.plugin_manager.get_plugin_manager", return_value=pm):
        result = tool_crm_query({"kind": "count_open_leads"})

    assert not result.startswith("[ERROR]")
    pm.call_capability.assert_called_once()
