#!/usr/bin/env python3
"""Plugin-level test for crm_core_query (CODEY_MASTER_PLAN.md 12.x).

Mirrors ccos/plugins/device/bridge/test.py's shape: one assertion per
capability's expected response shape, against a mocked CoreQueryClient --
not a live Core server (see tests/test_ccos_crm_read.py for that).
"""

from pathlib import Path
from unittest.mock import MagicMock

_pathutil_path = Path(__file__).resolve().parent.parent.parent / "_pathutil.py"
import importlib.util
_spec = importlib.util.spec_from_file_location("_pathutil", _pathutil_path)
_pathutil = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_pathutil)
_pathutil.ensure_repo_root_on_path()

import ccos.plugins.crm.core_query.core_query as core_query
from ccos.plugins.crm.core_query.client import CoreQueryClient
from ccos.plugins.crm.core_query import test as plugin_self_test


def _mocked_client() -> MagicMock:
    client = MagicMock(spec=CoreQueryClient)
    client.count_open_leads.return_value = {"count": 2, "assigned_user_id": None}
    client.list_leads.return_value = {"leads": [{"id": 1}], "returned": 1, "truncated": False}
    client.get_lead.return_value = {"lead": {"id": 1}}
    client.list_opportunities.return_value = {"opportunities": [{"id": 1}], "returned": 1, "truncated": False}
    client.get_opportunity.return_value = {"opportunity": {"id": 1}}
    client.get_pipeline_summary.return_value = {"pipeline": {}, "summary": {}}
    client.list_customers.return_value = {"customers": [{"id": 1}]}
    client.get_customer.return_value = {"customer": {"id": 1}}
    client.list_tasks.return_value = {"tasks": [{"id": 1}], "returned": 1, "truncated": False}
    client.list_properties.return_value = {"properties": [{"id": 1}], "returned": 1, "truncated": False}
    client.list_estimates.return_value = {"estimates": [{"id": 1}], "returned": 1, "truncated": False}
    client.list_communications.return_value = {"communications": [{"id": 1}], "returned": 1, "truncated": False}
    return client


def test_all_twelve_capabilities_each_backed_by_one_route():
    # 9 (12.x) + 3 (B8.11 Part C, 2026-10-01) = 12, not the originally-
    # planned 10 for 12.x -- crm.score_lead was removed that round:
    # GET /api/v1/leads/{id}/score persists via update_lead() for any
    # existing lead regardless of HTTP method, so it 403s under this
    # plugin's deny-list token (see client.py's comment and
    # NEW_ISSUES.md's headline finding for that round).
    core_query._client = _mocked_client()
    try:
        assert core_query.count_open_leads_capability()["count"] == 2
        assert core_query.list_leads_capability()["leads"] == [{"id": 1}]
        assert core_query.get_lead_capability(lead_id=1)["lead"]["id"] == 1
        assert core_query.list_opportunities_capability()["opportunities"] == [{"id": 1}]
        assert core_query.get_opportunity_capability(opportunity_id=1)["opportunity"]["id"] == 1
        assert core_query.get_pipeline_summary_capability() == {"pipeline": {}, "summary": {}}
        assert core_query.list_customers_capability()["customers"] == [{"id": 1}]
        assert core_query.get_customer_capability(customer_id=1)["customer"]["id"] == 1
        assert core_query.list_tasks_capability()["tasks"] == [{"id": 1}]
        assert core_query.list_properties_capability()["properties"] == [{"id": 1}]
        assert core_query.list_estimates_capability()["estimates"] == [{"id": 1}]
        assert core_query.list_communications_capability()["communications"] == [{"id": 1}]
    finally:
        core_query._client = None


def test_plugin_self_test_passes():
    assert plugin_self_test() is True


if __name__ == "__main__":
    test_all_twelve_capabilities_each_backed_by_one_route()
    test_plugin_self_test_passes()
    print("All crm_core_query plugin tests passed!")
