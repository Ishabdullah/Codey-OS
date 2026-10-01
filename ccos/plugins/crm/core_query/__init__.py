"""CRM Core-Query Plugin Package."""
from ccos.plugins.crm.core_query.core_query import (
    count_open_leads_capability,
    list_leads_capability,
    get_lead_capability,
    list_opportunities_capability,
    get_opportunity_capability,
    get_pipeline_summary_capability,
    list_customers_capability,
    get_customer_capability,
    list_tasks_capability,
    install,
    uninstall,
    test,
)

__all__ = [
    "count_open_leads_capability",
    "list_leads_capability",
    "get_lead_capability",
    "list_opportunities_capability",
    "get_opportunity_capability",
    "get_pipeline_summary_capability",
    "list_customers_capability",
    "get_customer_capability",
    "list_tasks_capability",
    "install",
    "uninstall",
    "test",
]
