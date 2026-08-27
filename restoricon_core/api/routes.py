"""
HTTP API request routing and endpoint handlers for Restoricon Core.
Exposes JSON REST endpoints with strict Bearer token authentication and RBAC.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from ..auth import AuthContext, AuthService, PERM_READ_ALL_CUSTOMERS
from ..models import (
    Appointment,
    AutomationRule,
    BusinessProfile,
    Contract,
    Customer,
    Document,
    Estimate,
    Invoice,
    Lead,
    Opportunity,
    Project,
    Subcontractor,
)
from ..services.audit_service import AuditService
from ..services.automation_service import AutomationService
from ..services.communication_service import CommunicationService
from ..services.crm_service import CRMService
from ..services.scheduling_service import SchedulingService


class APIRouter:
    """Dispatches HTTP requests to appropriate service handlers with RBAC and error handling.

    RBAC is enforced entirely in the *service* layer (every service method
    calls `actor.has_permission(...)` and raises `PermissionError` on
    denial) -- this router's only auth job is resolving the Bearer token
    to an `AuthContext` below and letting the global `except PermissionError`
    handler in `handle_request` turn that rejection into a 403. Routes
    never call `has_permission()` directly.
    """

    def __init__(
        self,
        auth_service: AuthService,
        crm_service: CRMService,
        comm_service: CommunicationService,
        audit_service: AuditService,
        scheduling_service: SchedulingService,
        automation_service: AutomationService,
    ):
        self.auth = auth_service
        self.crm = crm_service
        self.comm = comm_service
        self.audit = audit_service
        self.scheduling = scheduling_service
        self.automation = automation_service

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

            if path.startswith("/api/v1/customers/") and "/" not in path[len("/api/v1/customers/"):] and method == "GET":
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

            if path.startswith("/api/v1/projects/") and "/" not in path[len("/api/v1/projects/"):] and method == "GET":
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
                    # customer_id resolution (NEW-233): if the caller doesn't
                    # already know the internal customer_id (true for the
                    # JS write-through, which only has the sender's raw
                    # address), resolve it here from from_email before the
                    # single record_communication() call below, rather than
                    # making the caller do a separate lookup call first --
                    # two HTTP calls would give a retry queue two independent
                    # failure points instead of one atomic attempt. Ambiguous
                    # (2+ matches) or unmatched emails resolve to None, same
                    # as if the field were never given. Gated on the actor
                    # actually holding PERM_READ_ALL_CUSTOMERS -- ROLE_TECHNICIAN
                    # holds PERM_LOG_COMMUNICATION (checked inside
                    # record_communication() below) but not
                    # PERM_READ_ALL_CUSTOMERS, so calling get_customer_by_email()
                    # unconditionally would turn an otherwise-valid log write
                    # into a PermissionError for that role. Fail open to
                    # customer_id=None rather than failing the whole write --
                    # a communication that can't be auto-linked to a customer
                    # is still far better than one that's silently never logged.
                    customer_id = json_body.get("customer_id")
                    from_email = json_body.get("from_email")
                    if customer_id is None and from_email and actor.has_permission(PERM_READ_ALL_CUSTOMERS):
                        resolved = self.crm.get_customer_by_email(from_email, actor)
                        customer_id = resolved.id if resolved else None
                    provider_message_id = json_body.get("provider_message_id")
                    if provider_message_id is not None and not isinstance(provider_message_id, str):
                        return (
                            400,
                            {"Content-Type": "application/json"},
                            {"error": "provider_message_id must be a string"},
                        )
                    rec = self.comm.record_communication(
                        channel=json_body.get("channel", "email"),
                        direction=json_body.get("direction", "inbound"),
                        content=json_body.get("content", ""),
                        actor=actor,
                        subject=json_body.get("subject"),
                        customer_id=customer_id,
                        project_id=json_body.get("project_id"),
                        opportunity_id=json_body.get("opportunity_id"),
                        metadata=json_body.get("metadata"),
                        provider_message_id=provider_message_id,
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

            # Subcontractors
            if path == "/api/v1/subcontractors":
                if method == "GET":
                    # find_subcontractor() fuzzy lookup (B2 task 4, third
                    # module continuation, 2026-08-27, CODEY_MASTER_PLAN.md
                    # Sec6.4) -- an optional `q` query param branches to
                    # the fuzzy phone/email/name lookup instead of the
                    # list behavior below. A blank/whitespace-only `q`
                    # (?q= or ?q=%20) is treated the same as no `q` at
                    # all and falls through to list_subcontractors -- the
                    # method's own empty-query guard must never even be
                    # reached from a stray trailing `?q=`.
                    q = query_params.get("q", [None])[0]
                    if q is not None and q.strip():
                        found = self.crm.find_subcontractor(q, actor)
                        if not found:
                            return 404, {"Content-Type": "application/json"}, {"error": "Subcontractor not found"}
                        return 200, {"Content-Type": "application/json"}, {"subcontractor": found.to_dict()}

                    qualification_status = query_params.get("qualification_status", [None])[0]
                    primary_trade = query_params.get("primary_trade", [None])[0]
                    limit = int(query_params.get("limit", ["50"])[0])
                    offset = int(query_params.get("offset", ["0"])[0])
                    subs = self.crm.list_subcontractors(
                        actor,
                        qualification_status=qualification_status,
                        primary_trade=primary_trade,
                        limit=limit,
                        offset=offset,
                    )
                    return 200, {"Content-Type": "application/json"}, {"subcontractors": [s.to_dict() for s in subs]}
                elif method == "POST":
                    sub = Subcontractor(**json_body)
                    created = self.crm.create_subcontractor(sub, actor)
                    return 201, {"Content-Type": "application/json"}, {"subcontractor": created.to_dict()}

            if path.startswith("/api/v1/subcontractors/") and path.endswith("/qualification") and method == "POST":
                sub_id = int(path.split("/")[-2])
                qualification_status = json_body.get("qualification_status")
                recruitment_step = json_body.get("recruitment_step")
                updated_sub = self.crm.update_subcontractor_qualification(
                    sub_id, qualification_status, actor, recruitment_step
                )
                if not updated_sub:
                    return 404, {"Content-Type": "application/json"}, {"error": "Subcontractor not found"}
                return 200, {"Content-Type": "application/json"}, {"subcontractor": updated_sub.to_dict()}

            if path.startswith("/api/v1/subcontractors/") and path.endswith("/update") and method == "POST":
                sub_id = int(path.split("/")[-2])
                updated_sub = self.crm.update_subcontractor(sub_id, json_body, actor)
                if not updated_sub:
                    return 404, {"Content-Type": "application/json"}, {"error": "Subcontractor not found"}
                return 200, {"Content-Type": "application/json"}, {"subcontractor": updated_sub.to_dict()}

            if path.startswith("/api/v1/subcontractors/") and "/" not in path[len("/api/v1/subcontractors/"):] and method == "GET":
                sub_id = int(path.split("/")[-1])
                sub = self.crm.get_subcontractor(sub_id, actor)
                if not sub:
                    return 404, {"Content-Type": "application/json"}, {"error": "Subcontractor not found"}
                return 200, {"Content-Type": "application/json"}, {"subcontractor": sub.to_dict()}

            # Appointments
            if path == "/api/v1/appointments":
                if method == "GET":
                    cid = query_params.get("customer_id", [None])[0]
                    cust_id = int(cid) if cid else None
                    status = query_params.get("status", [None])[0]
                    limit = int(query_params.get("limit", ["50"])[0])
                    offset = int(query_params.get("offset", ["0"])[0])
                    appts = self.scheduling.list_appointments(
                        actor, customer_id=cust_id, status=status, limit=limit, offset=offset
                    )
                    return 200, {"Content-Type": "application/json"}, {"appointments": [a.to_dict() for a in appts]}
                elif method == "POST":
                    appt = Appointment(**json_body)
                    created = self.scheduling.create_appointment(appt, actor)
                    return 201, {"Content-Type": "application/json"}, {"appointment": created.to_dict()}

            if path.startswith("/api/v1/appointments/") and path.endswith("/status") and method == "POST":
                appt_id = int(path.split("/")[-2])
                status = json_body.get("status")
                updated_appt = self.scheduling.update_appointment_status(appt_id, status, actor)
                if not updated_appt:
                    return 404, {"Content-Type": "application/json"}, {"error": "Appointment not found"}
                return 200, {"Content-Type": "application/json"}, {"appointment": updated_appt.to_dict()}

            if path.startswith("/api/v1/appointments/") and "/" not in path[len("/api/v1/appointments/"):] and method == "GET":
                appt_id = int(path.split("/")[-1])
                appt = self.scheduling.get_appointment(appt_id, actor)
                if not appt:
                    return 404, {"Content-Type": "application/json"}, {"error": "Appointment not found"}
                return 200, {"Content-Type": "application/json"}, {"appointment": appt.to_dict()}

            # Automation Rules
            if path == "/api/v1/automation-rules":
                if method == "GET":
                    channel = query_params.get("channel", [None])[0]
                    limit = int(query_params.get("limit", ["100"])[0])
                    offset = int(query_params.get("offset", ["0"])[0])
                    rules = self.automation.list_rules(actor, channel=channel, limit=limit, offset=offset)
                    return 200, {"Content-Type": "application/json"}, {"automation_rules": [r.to_dict() for r in rules]}
                elif method == "POST":
                    rule = AutomationRule(**json_body)
                    created = self.automation.create_rule(rule, actor)
                    return 201, {"Content-Type": "application/json"}, {"automation_rule": created.to_dict()}

            if path.startswith("/api/v1/automation-rules/") and path.endswith("/match") and method == "POST":
                rule_id = int(path.split("/")[-2])
                updated_rule = self.automation.record_rule_match(rule_id, actor)
                if not updated_rule:
                    return 404, {"Content-Type": "application/json"}, {"error": "Automation rule not found"}
                return 200, {"Content-Type": "application/json"}, {"automation_rule": updated_rule.to_dict()}

            if path.startswith("/api/v1/automation-rules/") and path.endswith("/delete") and method == "POST":
                rule_id = int(path.split("/")[-2])
                deleted = self.automation.delete_rule(rule_id, actor)
                return 200, {"Content-Type": "application/json"}, {"deleted": deleted}

            # Business Profile (singleton)
            if path == "/api/v1/business-profile":
                if method == "GET":
                    profile = self.automation.get_business_profile(actor)
                    if not profile:
                        return 404, {"Content-Type": "application/json"}, {"error": "Business profile not configured"}
                    return 200, {"Content-Type": "application/json"}, {"business_profile": profile.to_dict()}
                elif method == "POST":
                    profile = BusinessProfile(**json_body)
                    saved = self.automation.upsert_business_profile(profile, actor)
                    return 200, {"Content-Type": "application/json"}, {"business_profile": saved.to_dict()}

            # Do-Not-Contact
            if path == "/api/v1/do-not-contact":
                if method == "GET":
                    limit = int(query_params.get("limit", ["100"])[0])
                    offset = int(query_params.get("offset", ["0"])[0])
                    entries = self.automation.list_do_not_contact(actor, limit=limit, offset=offset)
                    return 200, {"Content-Type": "application/json"}, {"do_not_contact": [e.to_dict() for e in entries]}
                elif method == "POST":
                    identifier = json_body.get("identifier", "")
                    entry = self.automation.add_to_do_not_contact(
                        identifier,
                        actor,
                        name=json_body.get("name"),
                        reason=json_body.get("reason"),
                        source=json_body.get("source"),
                    )
                    if not entry:
                        return 400, {"Content-Type": "application/json"}, {"error": "Identifier could not be classified as email or phone"}
                    return 201, {"Content-Type": "application/json"}, {"do_not_contact": entry.to_dict()}

            if path == "/api/v1/do-not-contact/remove" and method == "POST":
                identifier = json_body.get("identifier", "")
                removed = self.automation.remove_from_do_not_contact(identifier, actor)
                return 200, {"Content-Type": "application/json"}, {"removed": removed}

            if path == "/api/v1/do-not-contact/check" and method == "GET":
                identifier = query_params.get("identifier", [""])[0]
                blocked = self.automation.is_blocked(identifier, actor)
                return 200, {"Content-Type": "application/json"}, {"blocked": blocked}

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
