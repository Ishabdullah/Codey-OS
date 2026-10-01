"""
CoreQueryClient — thin HTTP client wrapping `requests` calls to Restoricon
Core's existing read-only CRM/sales REST routes (CODEY_MASTER_PLAN.md 12.x).

This client speaks only to routes already exposed by
`restoricon_core/api/routes.py`; it adds no new Core API route and performs
no writes. Host/port come from `utils.config.get_restoricon_api_config()`
(the single source of truth for Core's address — never hardcode it here).
The bearer token comes from `~/.codeyOS/ccos_crm_read_token`
(`utils.config.CODEY_STATE_DIR`, the single source of truth for
"~/.codeyOS" — never hardcode that path string either), a file this client
only ever reads, never writes; it is provisioned out-of-band by
`tools/provision_ai_agent_auth.py --username codey-ccos-crm-reader` and
pasted there manually, same operational pattern as Aigentik's
`core_api.token` deployment.

Context-size discipline: every list-shaped method below applies a hard
plugin-side cap independent of whatever Core itself returns, truncating
and flagging it explicitly (`truncated`/`returned`/`note` keys) rather
than silently dropping rows — this survives serialization (e.g.
`json.dumps`) since it's part of the returned dict, not a side effect of
the call site that invoked it (see core/agent.py's `tool_crm_query` and
tests/test_ccos_crm_read.py, which both exercise this through
`pm.call_capability()` directly).

`requests.Session(trust_env=False)` is deliberate, not an oversight: an
ambient `HTTP_PROXY`/`http_proxy` env var (already a documented footgun on
this project's own dev machine — see MEMORY.md's "Sandbox proxy test
artifact" note) would otherwise route a loopback call to Core through a
proxy, which is never correct for this client and has previously produced
a false test-failure signal elsewhere in this project.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import requests

from utils.config import CODEY_STATE_DIR, get_restoricon_api_config

CRM_READ_TOKEN_FILE = CODEY_STATE_DIR / "ccos_crm_read_token"

# Hard, plugin-side cap for every list-shaped capability (crm.list_leads,
# crm.list_opportunities, crm.list_tasks) — independent of whatever limit
# Core's own route applies, per 12.x's context-size-discipline requirement.
LIST_CAP = 50


class CoreQueryError(RuntimeError):
    """Raised on a non-2xx response or a transport-level failure talking to Core."""


def _read_token() -> str:
    try:
        token = CRM_READ_TOKEN_FILE.read_text().strip()
    except (FileNotFoundError, OSError) as e:
        raise CoreQueryError(
            f"CRM read token not found at {CRM_READ_TOKEN_FILE} — provision it via "
            f"'python -m tools.provision_ai_agent_auth --username codey-ccos-crm-reader' "
            f"and paste the printed token into that file."
        ) from e
    if not token:
        raise CoreQueryError(f"CRM read token file {CRM_READ_TOKEN_FILE} is empty.")
    return token


def _apply_list_cap(items: List[Dict[str, Any]], key: str, limit: int = LIST_CAP) -> Dict[str, Any]:
    """Wrap a list payload under `key` with a hard cap and an explicit
    truncation marker — never a silent truncation."""
    total = len(items)
    truncated = total > limit
    capped = items[:limit] if truncated else items
    result: Dict[str, Any] = {key: capped, "returned": len(capped), "truncated": truncated}
    if truncated:
        result["note"] = f"{total - limit} more not shown, narrow your query"
    return result


class CoreQueryClient:
    """Read-only HTTP client for Restoricon Core's CRM/sales GET routes."""

    def __init__(self, host: Optional[str] = None, port: Optional[int] = None, token: Optional[str] = None):
        cfg = get_restoricon_api_config()
        self._host = host or cfg["host"]
        self._port = port or cfg["port"]
        self._token = token  # lazily read from CRM_READ_TOKEN_FILE if not given
        self._session = requests.Session()
        self._session.trust_env = False  # never go through an ambient proxy for loopback Core calls

    def _base_url(self) -> str:
        return f"http://{self._host}:{self._port}"

    def _headers(self) -> Dict[str, str]:
        token = self._token or _read_token()
        return {"Authorization": f"Bearer {token}"}

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = self._base_url() + path
        try:
            resp = self._session.get(url, headers=self._headers(), params=params or {}, timeout=10.0)
        except requests.RequestException as e:
            raise CoreQueryError(f"GET {path} failed: {e}") from e
        if resp.status_code >= 400:
            raise CoreQueryError(f"GET {path} returned {resp.status_code}: {resp.text[:300]}")
        try:
            return resp.json()
        except ValueError as e:
            raise CoreQueryError(f"GET {path} returned non-JSON body: {e}") from e

    # Lead.status has no "open" value (models.py: new/contacted/qualified/
    # unqualified/converted/lost) and /api/v1/leads only supports a single
    # exact-match `status` filter -- passing status="open" would silently
    # return zero rows every time. "Open" here means not yet resolved
    # either way, so this is a client-side filter over the unfiltered
    # response, excluding the two terminal statuses.
    _CLOSED_LEAD_STATUSES = {"converted", "lost"}

    # ── Leads ────────────────────────────────────────────────────────────
    def count_open_leads(self, assigned_user_id: Optional[int] = None) -> Dict[str, Any]:
        body = self._get("/api/v1/leads", params=_clean({"assigned_user_id": assigned_user_id}))
        leads = body.get("leads", [])
        open_leads = [l for l in leads if l.get("status") not in self._CLOSED_LEAD_STATUSES]
        return {"count": len(open_leads), "assigned_user_id": assigned_user_id}

    def list_leads(
        self,
        status: Optional[str] = None,
        assigned_user_id: Optional[int] = None,
        territory_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        body = self._get(
            "/api/v1/leads",
            params=_clean({"status": status, "assigned_user_id": assigned_user_id, "territory_id": territory_id}),
        )
        return _apply_list_cap(body.get("leads", []), "leads")

    def get_lead(self, lead_id: int) -> Dict[str, Any]:
        return self._get(f"/api/v1/leads/{int(lead_id)}")

    # NOTE: no score_lead() method here. `GET /api/v1/leads/{id}/score`
    # looked read-only from the route dispatch alone (no request body) but
    # is NOT: restoricon_core/services/crm_service.py's score_lead()
    # persists the computed score via self.update_lead(lead_id, ...,
    # actor) for ANY existing lead_id regardless of HTTP method
    # (crm_service.py:1432-1446, reached from routes.py's GET branch at
    # ~line 1154-1156) -- a side effect this plugin's deny-list-provisioned
    # token deliberately cannot perform (write:leads/write:crm are both
    # denied, see tools/provision_ai_agent_auth.py's CRM_READER_DENY_PERMISSIONS).
    # Scoped out of this round rather than wrapped (see NEW_ISSUES.md,
    # headline finding of this round, and CODEY_MASTER_PLAN.md 12.x) --
    # calling it would 403 for every real lead_id under this token anyway.

    # ── Opportunities ────────────────────────────────────────────────────
    def list_opportunities(
        self,
        pipeline_stage: Optional[str] = None,
        customer_id: Optional[int] = None,
        assigned_user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        body = self._get(
            "/api/v1/opportunities",
            params=_clean({
                "pipeline_stage": pipeline_stage,
                "customer_id": customer_id,
                "assigned_user_id": assigned_user_id,
            }),
        )
        return _apply_list_cap(body.get("opportunities", []), "opportunities")

    def get_opportunity(self, opportunity_id: int) -> Dict[str, Any]:
        return self._get(f"/api/v1/opportunities/{int(opportunity_id)}")

    # ── Pipeline summary ─────────────────────────────────────────────────
    def get_pipeline_summary(self) -> Dict[str, Any]:
        return self._get("/api/v1/crm/pipeline")

    # ── Customers ────────────────────────────────────────────────────────
    def list_customers(
        self,
        status: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        territory_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        # Core's own list_customers() already defaults/caps at limit=50
        # (routes.py's _parse_int_query_param(..., 50, minimum=1, maximum=1000));
        # just pass a sane limit through, no extra plugin-side cap needed.
        body = self._get(
            "/api/v1/customers",
            params=_clean({
                "status": status, "search": search, "limit": limit, "offset": offset, "territory_id": territory_id,
            }),
        )
        return body

    def get_customer(self, customer_id: int) -> Dict[str, Any]:
        return self._get(f"/api/v1/customers/{int(customer_id)}")

    # ── Properties ───────────────────────────────────────────────────────
    def list_properties(self, customer_id: Optional[int] = None) -> Dict[str, Any]:
        """List properties, optionally scoped to one customer. Appointment-
        prep's only caller of this (B8.11 Part C) always passes customer_id
        -- see the fan-out-from-customer_id derivation in this plugin's
        round's spec, since Appointment has no property_id/lead_id/
        opportunity_id of its own (restoricon_core/models.py:1032)."""
        body = self._get("/api/v1/properties", params=_clean({"customer_id": customer_id}))
        return _apply_list_cap(body.get("properties", []), "properties")

    # ── Estimates ────────────────────────────────────────────────────────
    # B8.11 Part C MANDATORY FIX: CRMService._row_to_estimate()
    # (crm_service.py:3332-3347) masks these 4 cost fields by ROLE
    # (`actor_role in (ROLE_CUSTOMER, ROLE_TECHNICIAN)`), NOT by
    # PERM_READ_ESTIMATE_COSTS -- the permission this round's deny-list
    # denies for codey-ccos-crm-reader. ROLE_AI_AGENT is neither masked
    # role, so Core returns these 4 fields IN FULL to this token despite
    # that permission being denied. Stripped here, client-side, by exact
    # field name (never substring match), before the capability layer ever
    # sees them. This only fixes this one caller -- the underlying Core
    # masking defect remains for every other ai_agent-role caller of
    # get_estimate/list_estimates (both go through the same masking
    # function) -- see NEW_ISSUES.md NEW-752, logged as a Confirmed
    # finding, not closed by this patch. Confirmed (crm_service.py:3216-
    # 3237, `_compute_line_item_costs`) that an Estimate's line_items use
    # `quantity`/`unit_cost`/`category` field names, never these 4 -- so a
    # top-level-only strip is sufficient; no nested occurrence to also strip.
    _ESTIMATE_COST_FIELDS_TO_STRIP = ("materials_cost", "labor_cost", "subcontractor_cost", "markup_percent")

    def list_estimates(
        self,
        customer_id: Optional[int] = None,
        project_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        body = self._get(
            "/api/v1/estimates",
            params=_clean({"customer_id": customer_id, "project_id": project_id}),
        )
        stripped = [
            {k: v for k, v in e.items() if k not in self._ESTIMATE_COST_FIELDS_TO_STRIP}
            for e in body.get("estimates", [])
        ]
        return _apply_list_cap(stripped, "estimates")

    # ── Communications ───────────────────────────────────────────────────
    def list_communications(
        self,
        customer_id: Optional[int] = None,
        project_id: Optional[int] = None,
        lead_id: Optional[int] = None,
        channel: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        body = self._get(
            "/api/v1/communications",
            params=_clean({
                "customer_id": customer_id,
                "project_id": project_id,
                "lead_id": lead_id,
                "channel": channel,
                "limit": limit,
                "offset": offset,
            }),
        )
        return _apply_list_cap(body.get("communications", []), "communications")

    # ── Tasks ────────────────────────────────────────────────────────────
    def list_tasks(
        self,
        status: Optional[str] = None,
        customer_id: Optional[int] = None,
        opportunity_id: Optional[int] = None,
        lead_id: Optional[int] = None,
        assigned_user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        body = self._get(
            "/api/v1/crm/tasks",
            params=_clean({
                "status": status,
                "customer_id": customer_id,
                "opportunity_id": opportunity_id,
                "lead_id": lead_id,
                "assigned_user_id": assigned_user_id,
            }),
        )
        return _apply_list_cap(body.get("tasks", []), "tasks")


def _clean(params: Dict[str, Any]) -> Dict[str, Any]:
    """Drop None-valued query params so they're omitted from the request
    entirely, matching routes.py's own `query_params.get(..., [None])[0]`
    "absent means unset" convention rather than sending the string 'None'."""
    return {k: v for k, v in params.items() if v is not None}


_default_client: Optional[CoreQueryClient] = None


def get_default_core_query_client() -> CoreQueryClient:
    global _default_client
    if _default_client is None:
        _default_client = CoreQueryClient()
    return _default_client
