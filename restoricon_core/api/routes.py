"""
HTTP API request routing and endpoint handlers for Restoricon Core.
Exposes JSON REST endpoints with strict Bearer token authentication and RBAC.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from ..auth import AuthContext, AuthService
from ..models import (
    Contract,
    Customer,
    Document,
    Estimate,
    Invoice,
    Lead,
    Opportunity,
    Project,
)
from ..services.audit_service import AuditService
from ..services.communication_service import CommunicationService
from ..services.crm_service import CRMService


class APIRouter:
    """Dispatches HTTP requests to appropriate service handlers with RBAC and error handling."""

    def __init__(
        self,
        auth_service: AuthService,
        crm_service: CRMService,
        comm_service: CommunicationService,
        audit_service: AuditService,
    ):
        self.auth = auth_service
        self.crm = crm_service
        self.comm = comm_service
        self.audit = audit_service

    def handle_request(
        self,
        method: str,
        path_with_query: str,
        headers: Dict[str, str],
        body_bytes: bytes,
    ) -> Tuple[int, Dict[str, str], Dict[str, Any]]:
        """
        Process an incoming request and return (status_code, response_headers, response_dict).
        """
        parsed_url = urlparse(path_with_query)
        path = parsed_url.path.rstrip("/")
        query_params = parse_qs(parsed_url.query)

        json_body: Dict[str, Any] = {}
        if body_bytes:
            try:
                json_body = json.loads(body_bytes.decode("utf-8"))
            except Exception:
                return 400, {"Content-Type": "application/json"}, {"error": "Invalid JSON body"}

        # Public endpoints (no auth required)
        if method == "GET" and path in ("/api/v1/health", "/health"):
            return 200, {"Content-Type": "application/json"}, {"status": "ok", "service": "restoricon_core"}

        if method == "POST" and path == "/api/v1/auth/login":
            return self._handle_login(json_body)

        # Authenticate all other endpoints
        auth_header = headers.get("authorization", headers.get("Authorization", ""))
        token = ""
        if auth_header.lower().startswith("bearer "):
            token = auth_header[7:].strip()

        actor = self.auth.authenticate_token(token)
        if not actor:
            return 401, {"Content-Type": "application/json"}, {"error": "Unauthorized or expired token"}

        try:
            # Auth endpoints
            if path == "/api/v1/auth/me" and method == "GET":
                user = self.auth.get_user_by_id(actor.user_id)
                return 200, {"Content-Type": "application/json"}, {"user": user.to_dict() if user else None}

            if path == "/api/v1/auth/logout" and method == "POST":
                self.auth.revoke_token(actor.token or "")
                self.audit.log("auth_logout", "user", actor.user_id, f"User {actor.username} logged out", actor=actor)
                return 200, {"Content-Type": "application/json"}, {"message": "Logged out successfully"}

            # Customers
            if path == "/api/v1/customers":
                if method == "GET":
                    status = query_params.get("status", [None])[0]
                    search = query_params.get("search", [None])[0]
                    limit = int(query_params.get("limit", ["50"])[0])
                    offset = int(query_params.get("offset", ["0"])[0])
                    customers = self.crm.list_customers(actor, status=status, search_term=search, limit=limit, offset=offset)
                    return 200, {"Content-Type": "application/json"}, {"customers": [c.to_dict() for c in customers]}
                elif method == "POST":
                    cust = Customer(**json_body)
                    created = self.crm.create_customer(cust, actor)
                    return 201, {"Content-Type": "application/json"}, {"customer": created.to_dict()}

            if path.startswith("/api/v1/customers/") and method == "GET":
                cust_id = int(path.split("/")[-1])
                cust = self.crm.get_customer(cust_id, actor)
                if not cust:
                    return 404, {"Content-Type": "application/json"}, {"error": "Customer not found"}
                return 200, {"Content-Type": "application/json"}, {"customer": cust.to_dict()}

            # Leads
            if path == "/api/v1/leads":
                if method == "GET":
                    status = query_params.get("status", [None])[0]
                    leads = self.crm.list_leads(actor, status=status)
                    return 200, {"Content-Type": "application/json"}, {"leads": [l.to_dict() for l in leads]}
                elif method == "POST":
                    lead = Lead(**json_body)
                    created = self.crm.create_lead(lead, actor)
                    return 201, {"Content-Type": "application/json"}, {"lead": created.to_dict()}

            # Opportunities
            if path == "/api/v1/opportunities":
                if method == "GET":
                    stage = query_params.get("pipeline_stage", [None])[0]
                    opps = self.crm.list_opportunities(actor, pipeline_stage=stage)
                    return 200, {"Content-Type": "application/json"}, {"opportunities": [o.to_dict() for o in opps]}
                elif method == "POST":
                    opp = Opportunity(**json_body)
                    created = self.crm.create_opportunity(opp, actor)
                    return 201, {"Content-Type": "application/json"}, {"opportunity": created.to_dict()}

            # Projects
            if path == "/api/v1/projects":
                if method == "GET":
                    cid = query_params.get("customer_id", [None])[0]
                    cust_id = int(cid) if cid else None
                    projects = self.crm.list_projects(actor, customer_id=cust_id)
                    return 200, {"Content-Type": "application/json"}, {"projects": [p.to_dict() for p in projects]}
                elif method == "POST":
                    proj = Project(**json_body)
                    created = self.crm.create_project(proj, actor)
                    return 201, {"Content-Type": "application/json"}, {"project": created.to_dict()}

            if path.startswith("/api/v1/projects/") and method == "GET":
                proj_id = int(path.split("/")[-1])
                proj = self.crm.get_project(proj_id, actor)
                if not proj:
                    return 404, {"Content-Type": "application/json"}, {"error": "Project not found"}
                return 200, {"Content-Type": "application/json"}, {"project": proj.to_dict()}

            # Estimates
            if path == "/api/v1/estimates":
                if method == "POST":
                    est = Estimate(**json_body)
                    created = self.crm.create_estimate(est, actor)
                    return 201, {"Content-Type": "application/json"}, {"estimate": created.to_dict()}

            # Contracts
            if path == "/api/v1/contracts":
                if method == "POST":
                    contract = Contract(**json_body)
                    created = self.crm.create_contract(contract, actor)
                    return 201, {"Content-Type": "application/json"}, {"contract": created.to_dict()}

            if path.startswith("/api/v1/contracts/") and path.endswith("/sign") and method == "POST":
                contract_id = int(path.split("/")[-2])
                signature = json_body.get("signature_data", "digital_signature_token")
                signed = self.crm.sign_contract(contract_id, signature, actor)
                return 200, {"Content-Type": "application/json"}, {"contract": signed.to_dict()}

            # Invoices
            if path == "/api/v1/invoices":
                if method == "POST":
                    inv = Invoice(**json_body)
                    created = self.crm.create_invoice(inv, actor)
                    return 201, {"Content-Type": "application/json"}, {"invoice": created.to_dict()}

            if path.startswith("/api/v1/invoices/") and path.endswith("/pay") and method == "POST":
                inv_id = int(path.split("/")[-2])
                amount = float(json_body.get("amount", 0.0))
                method_name = json_body.get("payment_method", "credit_card")
                ref = json_body.get("reference", "manual_entry")
                updated_inv = self.crm.record_payment(inv_id, amount, method_name, ref, actor)
                return 200, {"Content-Type": "application/json"}, {"invoice": updated_inv.to_dict()}

            # Documents
            if path == "/api/v1/documents":
                if method == "POST":
                    doc = Document(**json_body)
                    created = self.crm.create_document(doc, actor)
                    return 201, {"Content-Type": "application/json"}, {"document": created.to_dict()}

            # Communication History (Append-only)
            if path == "/api/v1/communications":
                if method == "GET":
                    cid = query_params.get("customer_id", [None])[0]
                    cust_id = int(cid) if cid else None
                    pid = query_params.get("project_id", [None])[0]
                    proj_id = int(pid) if pid else None
                    channel = query_params.get("channel", [None])[0]
                    limit = int(query_params.get("limit", ["50"])[0])
                    offset = int(query_params.get("offset", ["0"])[0])
                    records = self.comm.query_communications(
                        actor, customer_id=cust_id, project_id=proj_id, channel=channel, limit=limit, offset=offset
                    )
                    return 200, {"Content-Type": "application/json"}, {"communications": [c.to_dict() for c in records]}
                elif method == "POST":
                    rec = self.comm.record_communication(
                        channel=json_body.get("channel", "email"),
                        direction=json_body.get("direction", "inbound"),
                        content=json_body.get("content", ""),
                        actor=actor,
                        subject=json_body.get("subject"),
                        customer_id=json_body.get("customer_id"),
                        project_id=json_body.get("project_id"),
                        opportunity_id=json_body.get("opportunity_id"),
                        metadata=json_body.get("metadata"),
                    )
                    return 201, {"Content-Type": "application/json"}, {"communication": rec.to_dict()}

            # Audit Log (Append-only query)
            if path == "/api/v1/audit-log" and method == "GET":
                entity_type = query_params.get("entity_type", [None])[0]
                eid = query_params.get("entity_id", [None])[0]
                entity_id = int(eid) if eid else None
                action = query_params.get("action", [None])[0]
                limit = int(query_params.get("limit", ["100"])[0])
                offset = int(query_params.get("offset", ["0"])[0])
                logs = self.audit.query_logs(
                    actor, entity_type=entity_type, entity_id=entity_id, action=action, limit=limit, offset=offset
                )
                return 200, {"Content-Type": "application/json"}, {"audit_logs": [l.to_dict() for l in logs]}

            return 404, {"Content-Type": "application/json"}, {"error": f"Endpoint not found: {method} {path}"}

        except PermissionError as pe:
            return 403, {"Content-Type": "application/json"}, {"error": str(pe)}
        except ValueError as ve:
            return 400, {"Content-Type": "application/json"}, {"error": str(ve)}
        except Exception as ex:
            return 500, {"Content-Type": "application/json"}, {"error": f"Internal server error: {str(ex)}"}

    def _handle_login(self, body: Dict[str, Any]) -> Tuple[int, Dict[str, str], Dict[str, Any]]:
        username_or_email = body.get("username", body.get("email", ""))
        password = body.get("password", "")
        if not username_or_email or not password:
            return 400, {"Content-Type": "application/json"}, {"error": "Missing username/email or password"}

        user = self.auth.authenticate_user(username_or_email, password)
        if not user:
            return 401, {"Content-Type": "application/json"}, {"error": "Invalid credentials"}

        token = self.auth.create_token(user)
        actor_ctx = AuthContext(
            user_id=user.id,
            username=user.username,
            role=user.role,
            actor_type="agent" if user.role == "ai_agent" else "human",
            customer_id=user.customer_id,
            token=token,
        )
        self.audit.log("auth_login", "user", user.id, f"User {user.username} authenticated", actor=actor_ctx)

        return 200, {"Content-Type": "application/json"}, {
            "token": token,
            "user": user.to_dict(),
        }
