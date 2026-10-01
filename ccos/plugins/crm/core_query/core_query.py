"""
CRM Core-Query Plugin Implementation (CODEY_MASTER_PLAN.md 12.x).
Exposes CCOS capability wrapper functions mapped to CoreQueryClient's
read-only HTTP calls against Restoricon Core's existing CRM/sales GET
routes. Mirrors ccos/plugins/device/bridge/bridge.py's shape exactly.
"""

from typing import Any, Dict, Optional

from ccos.plugins.crm.core_query.client import (
    CoreQueryClient,
    get_default_core_query_client,
)

# NOTE: no crm.score_lead capability in this plugin. `GET
# /api/v1/leads/{id}/score` persists a write for any existing lead
# regardless of HTTP method -- see client.py's comment at the removed
# score_lead() method's former location, and this round's headline
# NEW_ISSUES.md finding. Scoped out deliberately: 9 capabilities, not
# the originally-planned 10.

_client: Optional[CoreQueryClient] = None


def _get_client() -> CoreQueryClient:
    global _client
    if _client is None:
        _client = get_default_core_query_client()
    return _client


def count_open_leads_capability(assigned_user_id: Optional[int] = None, **kwargs) -> Dict[str, Any]:
    """Count open (not converted/lost) leads, optionally scoped to one rep."""
    return _get_client().count_open_leads(assigned_user_id=assigned_user_id)


def list_leads_capability(
    status: Optional[str] = None,
    assigned_user_id: Optional[int] = None,
    territory_id: Optional[int] = None,
    **kwargs,
) -> Dict[str, Any]:
    """List leads (capped, see client.LIST_CAP), optionally filtered."""
    return _get_client().list_leads(status=status, assigned_user_id=assigned_user_id, territory_id=territory_id)


def get_lead_capability(lead_id: int, **kwargs) -> Dict[str, Any]:
    """Fetch a single lead by id."""
    return _get_client().get_lead(lead_id=lead_id)


def list_opportunities_capability(
    pipeline_stage: Optional[str] = None,
    customer_id: Optional[int] = None,
    assigned_user_id: Optional[int] = None,
    **kwargs,
) -> Dict[str, Any]:
    """List opportunities (capped, see client.LIST_CAP), optionally filtered."""
    return _get_client().list_opportunities(
        pipeline_stage=pipeline_stage, customer_id=customer_id, assigned_user_id=assigned_user_id
    )


def get_opportunity_capability(opportunity_id: int, **kwargs) -> Dict[str, Any]:
    """Fetch a single opportunity by id."""
    return _get_client().get_opportunity(opportunity_id=opportunity_id)


def get_pipeline_summary_capability(**kwargs) -> Dict[str, Any]:
    """Fetch the CRM pipeline summary."""
    return _get_client().get_pipeline_summary()


def list_customers_capability(
    status: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    territory_id: Optional[int] = None,
    **kwargs,
) -> Dict[str, Any]:
    """List customers. Inherits Core's own limit=50 default/cap -- no extra plugin-side cap needed."""
    return _get_client().list_customers(
        status=status, search=search, limit=limit, offset=offset, territory_id=territory_id
    )


def get_customer_capability(customer_id: int, **kwargs) -> Dict[str, Any]:
    """Fetch a single customer by id."""
    return _get_client().get_customer(customer_id=customer_id)


def list_tasks_capability(
    status: Optional[str] = None,
    customer_id: Optional[int] = None,
    opportunity_id: Optional[int] = None,
    lead_id: Optional[int] = None,
    assigned_user_id: Optional[int] = None,
    **kwargs,
) -> Dict[str, Any]:
    """List CRM follow-up tasks (capped, see client.LIST_CAP), optionally filtered."""
    return _get_client().list_tasks(
        status=status,
        customer_id=customer_id,
        opportunity_id=opportunity_id,
        lead_id=lead_id,
        assigned_user_id=assigned_user_id,
    )


def install() -> bool:
    """Plugin install lifecycle hook."""
    return True


def uninstall() -> bool:
    """Plugin uninstall lifecycle hook."""
    return True


def test() -> bool:
    """Plugin self-test. Exercises only the plugin's own request-shaping
    logic (params, cap, URL construction) against a mocked client, not a
    live Core server -- see tests/test_ccos_crm_read.py for the real
    integration coverage (Part E.2/3/4/5)."""
    from unittest.mock import MagicMock

    global _client
    saved = _client
    try:
        mock_client = MagicMock(spec=CoreQueryClient)
        mock_client.count_open_leads.return_value = {"count": 3, "assigned_user_id": None}
        _client = mock_client

        result = count_open_leads_capability()
        assert isinstance(result, dict) and "count" in result, "count_open_leads must return a dict with 'count'"
        return True
    finally:
        _client = saved
