"""
HTTP API request routing and endpoint handlers for Restoricon Core.
Exposes JSON REST endpoints with strict Bearer token authentication and RBAC.
"""

import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from ..auth import AuthContext, AuthService, PERM_READ_ALL_CUSTOMERS, PERM_LOG_COMMUNICATION
from ..models import (
    Appointment,
    AutomationRule,
    BusinessProfile,
    ComplianceItem,
    Contact,
    Contract,
    Customer,
    Document,
    Employee,
    Equipment,
    EquipmentDeployment,
    Estimate,
    FinancialTransaction,
    Invoice,
    Lead,
    MarketingCampaign,
    Opportunity,
    Project,
    ProjectMilestone,
    PurchaseOrder,
    ReviewRequest,
    ScheduleConfig,
    Subcontractor,
    Task,
    Timesheet,
    Vendor,
    WorkOrder,
)
from .rate_limiter import RateLimiter
from ..services.analytics_search_service import AnalyticsSearchService
from ..services.audit_service import AuditService
from ..services.automation_service import AutomationService
from ..services.business_ops_service import BusinessOpsService
from ..services.communication_service import CommunicationService
from ..services.crm_service import CRMService
from ..services.finance_service import FinanceService
from ..services.operations_service import OperationsService
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
        operations_service: Optional[OperationsService] = None,
        rate_limiter: Optional[RateLimiter] = None,
        finance_service: Optional[FinanceService] = None,
        business_ops_service: Optional[BusinessOpsService] = None,
        analytics_search_service: Optional[AnalyticsSearchService] = None,
    ):
        self.auth = auth_service
        self.crm = crm_service
        self.comm = comm_service
        self.audit = audit_service
        self.scheduling = scheduling_service
        self.automation = automation_service
        self.operations = operations_service or OperationsService(crm_service.db, audit_service)
        self.finance = finance_service or FinanceService(crm_service.db, audit_service)
        self.business_ops = business_ops_service or BusinessOpsService(crm_service.db, audit_service)
        self.analytics_search = analytics_search_service or AnalyticsSearchService(crm_service.db)
        self.rate_limiter = rate_limiter or RateLimiter(max_requests=60, window_seconds=60)

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

        # Resolve client IP (supporting reverse proxy / Cloudflare Tunnel headers)
        client_ip = (
            headers.get("cf-connecting-ip")
            or headers.get("x-forwarded-for", "").split(",")[0].strip()
            or headers.get("x-real-ip")
            or "127.0.0.1"
        )

        # Public endpoints (no auth required)
        if method == "GET" and path in ("/api/v1/health", "/health"):
            return 200, {"Content-Type": "application/json"}, {"status": "ok", "service": "restoricon_core"}

        if method == "POST" and path == "/api/v1/auth/login":
            return self._handle_login(json_body)

        # Public intake endpoints (rate-limited, no Bearer auth required)
        if path.startswith("/api/v1/public/"):
            allowed, remaining, reset_in = self.rate_limiter.is_allowed(client_ip)
            rate_headers = {
                "Content-Type": "application/json",
                "X-RateLimit-Limit": str(self.rate_limiter.max_requests),
                "X-RateLimit-Remaining": str(remaining),
                "X-RateLimit-Reset": str(reset_in),
            }
            if not allowed:
                return 429, rate_headers, {"error": "Rate limit exceeded. Please try again later."}

            if method == "POST" and path == "/api/v1/public/leads":
                try:
                    result = self.crm.submit_public_lead(json_body, client_ip=client_ip)
                    return 201, rate_headers, result
                except ValueError as e:
                    return 400, rate_headers, {"error": str(e)}

            if method == "POST" and path == "/api/v1/public/booking":
                try:
                    result = self.crm.submit_public_booking(json_body, client_ip=client_ip)
                    return 201, rate_headers, result
                except ValueError as e:
                    return 400, rate_headers, {"error": str(e)}

            return 404, rate_headers, {"error": f"Not found: {method} {path}"}

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

            if path == "/api/v1/customers/upsert" and method == "POST":
                cust = Customer(**json_body)
                result = self.crm.upsert_customer(cust, actor)
                return 200, {"Content-Type": "application/json"}, {"customer": result.to_dict()}

            if path == "/api/v1/customers/search" and method == "GET":
                q = query_params.get("q", [None])[0]
                if not q or not q.strip():
                    return 400, {"Content-Type": "application/json"}, {"error": "Missing required query parameter: q"}
                found = self.crm.find_customer(q, actor)
                if not found:
                    return 404, {"Content-Type": "application/json"}, {"error": "Customer not found"}
                return 200, {"Content-Type": "application/json"}, {"customer": found.to_dict()}

            if path.startswith("/api/v1/customers/") and path.endswith("/update") and method == "POST":
                cust_id = int(path.split("/")[-2])
                updated_cust = self.crm.update_customer(cust_id, json_body, actor)
                if not updated_cust:
                    return 404, {"Content-Type": "application/json"}, {"error": "Customer not found"}
                return 200, {"Content-Type": "application/json"}, {"customer": updated_cust.to_dict()}

            if path.startswith("/api/v1/customers/") and "/" not in path[len("/api/v1/customers/"):] and method == "GET":
                sub_path = path[len("/api/v1/customers/"):]
                if sub_path.isdigit():
                    cust_id = int(sub_path)
                    cust = self.crm.get_customer(cust_id, actor)
                    if not cust:
                        return 404, {"Content-Type": "application/json"}, {"error": "Customer not found"}
                    return 200, {"Content-Type": "application/json"}, {"customer": cust.to_dict()}

            # CRM Pipeline Summary
            if path == "/api/v1/crm/pipeline" and method == "GET":
                summary = self.crm.get_pipeline_summary(actor)
                return 200, {"Content-Type": "application/json"}, {"pipeline": summary, "summary": summary}

            # CRM Tasks & Follow-up Cadence
            if path == "/api/v1/crm/tasks":
                if method == "GET":
                    status = query_params.get("status", [None])[0]
                    cid = query_params.get("customer_id", [None])[0]
                    oid = query_params.get("opportunity_id", [None])[0]
                    lid = query_params.get("lead_id", [None])[0]
                    uid = query_params.get("assigned_user_id", [None])[0]
                    tasks = self.crm.list_tasks(
                        actor,
                        status=status,
                        customer_id=int(cid) if cid else None,
                        opportunity_id=int(oid) if oid else None,
                        lead_id=int(lid) if lid else None,
                        assigned_user_id=int(uid) if uid else None,
                    )
                    return 200, {"Content-Type": "application/json"}, {"tasks": [t.to_dict() for t in tasks]}
                elif method == "POST":
                    task = Task(**json_body)
                    created = self.crm.create_task(task, actor)
                    return 201, {"Content-Type": "application/json"}, {"task": created.to_dict()}

            if path.startswith("/api/v1/crm/tasks/") and path.endswith("/complete") and method == "POST":
                task_id = int(path.split("/")[-2])
                notes = json_body.get("notes")
                completed = self.crm.complete_task(task_id, actor, notes=notes)
                return 200, {"Content-Type": "application/json"}, {"task": completed.to_dict()}

            if path.startswith("/api/v1/crm/tasks/") and path.endswith("/update") and method == "POST":
                task_id = int(path.split("/")[-2])
                updated = self.crm.update_task(task_id, json_body, actor)
                if not updated:
                    return 404, {"Content-Type": "application/json"}, {"error": "Task not found"}
                return 200, {"Content-Type": "application/json"}, {"task": updated.to_dict()}

            if path.startswith("/api/v1/crm/tasks/") and "/" not in path[len("/api/v1/crm/tasks/"):] and method == "GET":
                task_id = int(path.split("/")[-1])
                task = self.crm.get_task(task_id, actor)
                if not task:
                    return 404, {"Content-Type": "application/json"}, {"error": "Task not found"}
                return 200, {"Content-Type": "application/json"}, {"task": task.to_dict()}

            if path == "/api/v1/crm/generate-cadence-tasks" and method == "POST":
                opp_id = json_body.get("opportunity_id")
                if not opp_id:
                    return 400, {"Content-Type": "application/json"}, {"error": "Missing opportunity_id parameter"}
                cadence_tasks = self.crm.generate_cadence_tasks(int(opp_id), actor)
                return 200, {"Content-Type": "application/json"}, {"tasks": [t.to_dict() for t in cadence_tasks]}

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

            if path.startswith("/api/v1/leads/") and path.endswith("/score"):
                lead_id = int(path.split("/")[4])
                if method == "GET":
                    score_res = self.crm.score_lead(lead_id, actor)
                    return 200, {"Content-Type": "application/json"}, score_res
                elif method == "POST":
                    score_res = self.crm.score_lead(lead_id, actor, factors=json_body)
                    return 200, {"Content-Type": "application/json"}, score_res

            if path.startswith("/api/v1/leads/") and path.endswith("/update") and method == "POST":
                lead_id = int(path.split("/")[-2])
                updated = self.crm.update_lead(lead_id, json_body, actor)
                if not updated:
                    return 404, {"Content-Type": "application/json"}, {"error": "Lead not found"}
                return 200, {"Content-Type": "application/json"}, {"lead": updated.to_dict()}

            if path.startswith("/api/v1/leads/") and "/" not in path[len("/api/v1/leads/"):] and method == "GET":
                sub = path[len("/api/v1/leads/"):]
                if sub.isdigit():
                    lead_id = int(sub)
                    lead = self.crm.get_lead(lead_id, actor)
                    if not lead:
                        return 404, {"Content-Type": "application/json"}, {"error": "Lead not found"}
                    return 200, {"Content-Type": "application/json"}, {"lead": lead.to_dict()}

            # Opportunities
            if path == "/api/v1/opportunities":
                if method == "GET":
                    stage = query_params.get("pipeline_stage", [None])[0]
                    cid = query_params.get("customer_id", [None])[0]
                    uid = query_params.get("assigned_user_id", [None])[0]
                    opps = self.crm.list_opportunities(
                        actor,
                        pipeline_stage=stage,
                        customer_id=int(cid) if cid else None,
                        assigned_user_id=int(uid) if uid else None,
                    )
                    return 200, {"Content-Type": "application/json"}, {"opportunities": [o.to_dict() for o in opps]}
                elif method == "POST":
                    opp = Opportunity(**json_body)
                    created = self.crm.create_opportunity(opp, actor)
                    return 201, {"Content-Type": "application/json"}, {"opportunity": created.to_dict()}

            if path.startswith("/api/v1/opportunities/") and path.endswith("/transition") and method == "POST":
                opp_id = int(path.split("/")[-2])
                new_stage = json_body.get("stage", json_body.get("pipeline_stage", ""))
                lost_reason = json_body.get("lost_reason")
                notes = json_body.get("notes")
                trans = self.crm.transition_opportunity_stage(
                    opp_id, new_stage=new_stage, actor=actor, lost_reason=lost_reason, notes=notes
                )
                return 200, {"Content-Type": "application/json"}, {"opportunity": trans.to_dict()}

            if path.startswith("/api/v1/opportunities/") and path.endswith("/update") and method == "POST":
                opp_id = int(path.split("/")[-2])
                updated = self.crm.update_opportunity(opp_id, json_body, actor)
                if not updated:
                    return 404, {"Content-Type": "application/json"}, {"error": "Opportunity not found"}
                return 200, {"Content-Type": "application/json"}, {"opportunity": updated.to_dict()}

            if path.startswith("/api/v1/opportunities/") and "/" not in path[len("/api/v1/opportunities/"):] and method == "GET":
                sub = path[len("/api/v1/opportunities/"):]
                if sub.isdigit():
                    opp_id = int(sub)
                    opp = self.crm.get_opportunity(opp_id, actor)
                    if not opp:
                        return 404, {"Content-Type": "application/json"}, {"error": "Opportunity not found"}
                    return 200, {"Content-Type": "application/json"}, {"opportunity": opp.to_dict()}

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
                if method == "GET":
                    cid = query_params.get("customer_id", [None])[0]
                    pid = query_params.get("project_id", [None])[0]
                    estimates = self.crm.list_estimates(
                        actor,
                        customer_id=int(cid) if cid else None,
                        project_id=int(pid) if pid else None,
                    )
                    return 200, {"Content-Type": "application/json"}, {"estimates": [e.to_dict() for e in estimates]}
                elif method == "POST":
                    est = Estimate(**json_body)
                    created = self.crm.create_estimate(est, actor)
                    return 201, {"Content-Type": "application/json"}, {"estimate": created.to_dict()}

            if path.startswith("/api/v1/estimates/") and "/" not in path[len("/api/v1/estimates/"):] and method == "GET":
                est_id = int(path.split("/")[-1])
                estimate = self.crm.get_estimate(est_id, actor)
                if not estimate:
                    return 404, {"Content-Type": "application/json"}, {"error": "Estimate not found"}
                return 200, {"Content-Type": "application/json"}, {"estimate": estimate.to_dict()}

            # Contracts
            if path == "/api/v1/contracts":
                if method == "GET":
                    cid = query_params.get("customer_id", [None])[0]
                    pid = query_params.get("project_id", [None])[0]
                    contracts = self.crm.list_contracts(
                        actor,
                        customer_id=int(cid) if cid else None,
                        project_id=int(pid) if pid else None,
                    )
                    return 200, {"Content-Type": "application/json"}, {"contracts": [c.to_dict() for c in contracts]}
                elif method == "POST":
                    contract = Contract(**json_body)
                    created = self.crm.create_contract(contract, actor)
                    return 201, {"Content-Type": "application/json"}, {"contract": created.to_dict()}

            if path.startswith("/api/v1/contracts/") and "/" not in path[len("/api/v1/contracts/"):] and method == "GET":
                contract_id = int(path.split("/")[-1])
                contract = self.crm.get_contract(contract_id, actor)
                if not contract:
                    return 404, {"Content-Type": "application/json"}, {"error": "Contract not found"}
                return 200, {"Content-Type": "application/json"}, {"contract": contract.to_dict()}

            if path.startswith("/api/v1/contracts/") and path.endswith("/sign") and method == "POST":
                contract_id = int(path.split("/")[-2])
                signature = json_body.get("signature_data", "digital_signature_token")
                signed = self.crm.sign_contract(contract_id, signature, actor)
                return 200, {"Content-Type": "application/json"}, {"contract": signed.to_dict()}

            # Invoices
            if path == "/api/v1/invoices":
                if method == "GET":
                    cid = query_params.get("customer_id", [None])[0]
                    pid = query_params.get("project_id", [None])[0]
                    invoices = self.crm.list_invoices(
                        actor,
                        customer_id=int(cid) if cid else None,
                        project_id=int(pid) if pid else None,
                    )
                    return 200, {"Content-Type": "application/json"}, {"invoices": [i.to_dict() for i in invoices]}
                elif method == "POST":
                    inv = Invoice(**json_body)
                    created = self.crm.create_invoice(inv, actor)
                    return 201, {"Content-Type": "application/json"}, {"invoice": created.to_dict()}

            if path.startswith("/api/v1/invoices/") and "/" not in path[len("/api/v1/invoices/"):] and method == "GET":
                inv_id = int(path.split("/")[-1])
                invoice = self.crm.get_invoice(inv_id, actor)
                if not invoice:
                    return 404, {"Content-Type": "application/json"}, {"error": "Invoice not found"}
                return 200, {"Content-Type": "application/json"}, {"invoice": invoice.to_dict()}

            if path.startswith("/api/v1/invoices/") and path.endswith("/pay") and method == "POST":
                inv_id = int(path.split("/")[-2])
                amount = float(json_body.get("amount", 0.0))
                method_name = json_body.get("payment_method", "credit_card")
                ref = json_body.get("reference", "manual_entry")
                updated_inv = self.crm.record_payment(inv_id, amount, method_name, ref, actor)
                return 200, {"Content-Type": "application/json"}, {"invoice": updated_inv.to_dict()}

            # Documents
            if path == "/api/v1/documents":
                if method == "GET":
                    cid = query_params.get("customer_id", [None])[0]
                    pid = query_params.get("project_id", [None])[0]
                    dtype = query_params.get("document_type", [None])[0]
                    documents = self.crm.list_documents(
                        actor,
                        customer_id=int(cid) if cid else None,
                        project_id=int(pid) if pid else None,
                        document_type=dtype,
                    )
                    return 200, {"Content-Type": "application/json"}, {"documents": [d.to_dict() for d in documents]}
                elif method == "POST":
                    doc = Document(**json_body)
                    created = self.crm.create_document(doc, actor)
                    return 201, {"Content-Type": "application/json"}, {"document": created.to_dict()}

            if path.startswith("/api/v1/documents/") and "/" not in path[len("/api/v1/documents/"):] and method == "GET":
                doc_id = int(path.split("/")[-1])
                doc = self.crm.get_document(doc_id, actor)
                if not doc:
                    return 404, {"Content-Type": "application/json"}, {"error": "Document not found"}
                return 200, {"Content-Type": "application/json"}, {"document": doc.to_dict()}

            # Customer Portal Endpoints (/api/v1/portal/*)
            if path.startswith("/api/v1/portal/"):
                if path == "/api/v1/portal/profile" and method == "GET":
                    if not actor.customer_id:
                        return 403, {"Content-Type": "application/json"}, {"error": "Actor is not linked to a customer record"}
                    cust = self.crm.get_customer(actor.customer_id, actor)
                    return 200, {"Content-Type": "application/json"}, {"profile": cust.to_dict() if cust else None}

                if path == "/api/v1/portal/projects" and method == "GET":
                    projects = self.crm.list_projects(actor, customer_id=actor.customer_id)
                    return 200, {"Content-Type": "application/json"}, {"projects": [p.to_dict() for p in projects]}

                if path.startswith("/api/v1/portal/projects/") and path.endswith("/milestones") and method == "GET":
                    proj_id = int(path.split("/")[-2])
                    milestones = self.operations.list_milestones(proj_id, actor)
                    return 200, {"Content-Type": "application/json"}, {"milestones": [m.to_dict() for m in milestones]}

                if path.startswith("/api/v1/portal/projects/") and "/" not in path[len("/api/v1/portal/projects/"):] and method == "GET":
                    proj_id = int(path.split("/")[-1])
                    proj = self.crm.get_project(proj_id, actor)
                    if not proj:
                        return 404, {"Content-Type": "application/json"}, {"error": "Project not found"}
                    return 200, {"Content-Type": "application/json"}, {"project": proj.to_dict()}

                if path == "/api/v1/portal/estimates" and method == "GET":
                    pid = query_params.get("project_id", [None])[0]
                    proj_id = int(pid) if pid else None
                    estimates = self.crm.list_estimates(actor, customer_id=actor.customer_id, project_id=proj_id)
                    return 200, {"Content-Type": "application/json"}, {"estimates": [e.to_dict() for e in estimates]}

                if path == "/api/v1/portal/contracts" and method == "GET":
                    pid = query_params.get("project_id", [None])[0]
                    proj_id = int(pid) if pid else None
                    contracts = self.crm.list_contracts(actor, customer_id=actor.customer_id, project_id=proj_id)
                    return 200, {"Content-Type": "application/json"}, {"contracts": [c.to_dict() for c in contracts]}

                if path.startswith("/api/v1/portal/contracts/") and path.endswith("/sign") and method == "POST":
                    contract_id = int(path.split("/")[-2])
                    signature = json_body.get("signature_data", "")
                    if not signature:
                        return 400, {"Content-Type": "application/json"}, {"error": "signature_data is required"}
                    signed = self.crm.sign_contract(contract_id, signature, actor)
                    return 200, {"Content-Type": "application/json"}, {"contract": signed.to_dict()}

                if path == "/api/v1/portal/invoices" and method == "GET":
                    pid = query_params.get("project_id", [None])[0]
                    proj_id = int(pid) if pid else None
                    invoices = self.crm.list_invoices(actor, customer_id=actor.customer_id, project_id=proj_id)
                    return 200, {"Content-Type": "application/json"}, {"invoices": [i.to_dict() for i in invoices]}

                if path == "/api/v1/portal/documents" and method == "GET":
                    pid = query_params.get("project_id", [None])[0]
                    proj_id = int(pid) if pid else None
                    dtype = query_params.get("document_type", [None])[0]
                    documents = self.crm.list_documents(actor, customer_id=actor.customer_id, project_id=proj_id, document_type=dtype)
                    return 200, {"Content-Type": "application/json"}, {"documents": [d.to_dict() for d in documents]}

                if path == "/api/v1/portal/messages" and method == "POST":
                    content = json_body.get("message", json_body.get("content", ""))
                    if not content:
                        return 400, {"Content-Type": "application/json"}, {"error": "Message content is required"}
                    pid = json_body.get("project_id")
                    rec = self.comm.record_communication(
                        channel="web_chat",
                        direction="inbound",
                        content=content,
                        actor=actor,
                        subject=json_body.get("subject", "Portal Message"),
                        customer_id=actor.customer_id,
                        project_id=int(pid) if pid else None,
                        metadata={"source": "customer_portal", "ip": client_ip},
                    )
                    return 201, {"Content-Type": "application/json"}, {"message": rec.to_dict()}

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

            # Upsert (create-or-update) endpoint — resolves NEW-242/NEW-245.
            # Keyed on external_id; returns a JS-compatible dict via
            # format_subcontractor_for_js.  Always returns 200 (upsert semantics).
            if path == "/api/v1/subcontractors/upsert" and method == "POST":
                sub = Subcontractor(**json_body)
                result = self.crm.upsert_subcontractor(sub, actor)
                return 200, {"Content-Type": "application/json"}, {
                    "subcontractor": self.crm.format_subcontractor_for_js(result)
                }

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

            # Contacts (Aigentik Contact Directory)
            if path == "/api/v1/contacts":
                if method == "GET":
                    type_filter = query_params.get("type", [None])[0]
                    role_filter = query_params.get("active_role", [None])[0]
                    trade_filter = query_params.get("trade", [None])[0]
                    limit = int(query_params.get("limit", ["50"])[0])
                    offset = int(query_params.get("offset", ["0"])[0])
                    contacts_list = self.crm.list_contacts(
                        actor,
                        type=type_filter,
                        active_role=role_filter,
                        trade=trade_filter,
                        limit=limit,
                        offset=offset,
                    )
                    return 200, {"Content-Type": "application/json"}, {"contacts": [c.to_dict() for c in contacts_list]}
                elif method == "POST":
                    contact = Contact(**json_body)
                    created = self.crm.create_contact(contact, actor)
                    return 201, {"Content-Type": "application/json"}, {"contact": created.to_dict()}

            if path in ("/api/v1/contacts/find", "/api/v1/contacts/search") and method == "GET":
                q = query_params.get("q", [None])[0]
                if not q or not q.strip():
                    return 400, {"Content-Type": "application/json"}, {"error": "Missing required query parameter: q"}
                found = self.crm.find_contact(q, actor)
                if not found:
                    return 404, {"Content-Type": "application/json"}, {"error": "Contact not found"}
                return 200, {"Content-Type": "application/json"}, {"contact": found.to_dict()}

            if path == "/api/v1/contacts/upsert" and method == "POST":
                contact = Contact(**json_body)
                result = self.crm.upsert_contact(contact, actor)
                return 200, {"Content-Type": "application/json"}, {"contact": result.to_dict()}

            if path == "/api/v1/contacts/sync" and method == "POST":
                contact_list = [Contact(**c) for c in json_body.get("contacts", [])]
                stats = self.crm.sync_contacts_batch(contact_list, actor)
                return 200, {"Content-Type": "application/json"}, {"status": "ok", "stats": stats}

            if path.startswith("/api/v1/contacts/") and path.endswith("/update") and method == "POST":
                id_str = path.split("/")[-2]
                if id_str.isdigit():
                    cid = int(id_str)
                else:
                    existing = self.crm.get_contact_by_external_id(id_str, actor)
                    cid = existing.id if existing else None
                if not cid:
                    return 404, {"Content-Type": "application/json"}, {"error": "Contact not found"}
                updated_c = self.crm.update_contact(cid, json_body, actor)
                if not updated_c:
                    return 404, {"Content-Type": "application/json"}, {"error": "Contact not found"}
                return 200, {"Content-Type": "application/json"}, {"contact": updated_c.to_dict()}

            if path.startswith("/api/v1/contacts/") and (path.endswith("/delete") and method == "POST" or method == "DELETE"):
                id_str = path.split("/")[-2] if path.endswith("/delete") else path[len("/api/v1/contacts/"):]
                if id_str.isdigit():
                    cid = int(id_str)
                else:
                    existing = self.crm.get_contact_by_external_id(id_str, actor)
                    cid = existing.id if existing else None
                if not cid:
                    return 404, {"Content-Type": "application/json"}, {"error": "Contact not found"}
                deleted = self.crm.delete_contact(cid, actor)
                if not deleted:
                    return 404, {"Content-Type": "application/json"}, {"error": "Contact not found"}
                return 200, {"Content-Type": "application/json"}, {"deleted": True}

            if path.startswith("/api/v1/contacts/") and "/" not in path[len("/api/v1/contacts/"):] and method == "GET":
                sub_path = path[len("/api/v1/contacts/"):]
                if sub_path.isdigit():
                    c = self.crm.get_contact(int(sub_path), actor)
                else:
                    c = self.crm.get_contact_by_external_id(sub_path, actor)
                if not c:
                    return 404, {"Content-Type": "application/json"}, {"error": "Contact not found"}
                return 200, {"Content-Type": "application/json"}, {"contact": c.to_dict()}

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

            if path == "/api/v1/appointments/upsert" and method == "POST":
                appt = Appointment(**json_body)
                saved = self.scheduling.upsert_appointment(appt, actor, raw_updates=json_body)
                return 200, {"Content-Type": "application/json"}, {"appointment": saved.to_dict()}

            if path.startswith("/api/v1/appointments/") and path.endswith("/status") and method == "POST":
                appt_id = int(path.split("/")[-2])
                status = json_body.get("status")
                updated_appt = self.scheduling.update_appointment_status(appt_id, status, actor)
                if not updated_appt:
                    return 404, {"Content-Type": "application/json"}, {"error": "Appointment not found"}
                return 200, {"Content-Type": "application/json"}, {"appointment": updated_appt.to_dict()}

            if path.startswith("/api/v1/appointments/") and path.endswith("/update") and method == "POST":
                appt_id = int(path.split("/")[-2])
                updated_appt = self.scheduling.update_appointment(appt_id, json_body, actor)
                if not updated_appt:
                    return 404, {"Content-Type": "application/json"}, {"error": "Appointment not found"}
                return 200, {"Content-Type": "application/json"}, {"appointment": updated_appt.to_dict()}

            if path.startswith("/api/v1/appointments/") and "/" not in path[len("/api/v1/appointments/"):] and method == "GET":
                appt_id = int(path.split("/")[-1])
                appt = self.scheduling.get_appointment(appt_id, actor)
                if not appt:
                    return 404, {"Content-Type": "application/json"}, {"error": "Appointment not found"}
                return 200, {"Content-Type": "application/json"}, {"appointment": appt.to_dict()}

            # Schedule Config (singleton, NEW-216)
            if path == "/api/v1/schedule-config":
                if method == "GET":
                    sc = self.scheduling.get_schedule_config(actor)
                    if not sc:
                        return 404, {"Content-Type": "application/json"}, {"error": "Schedule config not configured"}
                    return 200, {"Content-Type": "application/json"}, {"schedule_config": sc.to_dict()}
                elif method == "POST":
                    sc = ScheduleConfig(**json_body)
                    saved = self.scheduling.upsert_schedule_config(sc, actor)
                    return 200, {"Content-Type": "application/json"}, {"schedule_config": saved.to_dict()}

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

            # AI Chat Proxy with Context-Budget Admission Gating (Phase B2, NEW-211)
            if path == "/api/v1/ai/chat" and method == "POST":
                if not (
                    actor.role in ("admin", "manager", "sales", "project_manager", "ai_agent")
                    or actor.has_permission(PERM_READ_ALL_CUSTOMERS)
                    or actor.has_permission(PERM_LOG_COMMUNICATION)
                ):
                    raise PermissionError("Actor lacks permission to invoke AI completion")

                messages = json_body.get("messages", [])
                if not messages:
                    return 400, {"Content-Type": "application/json"}, {"error": "Missing messages in request body"}
                max_tokens = int(json_body.get("max_tokens", 512))
                temperature = float(json_body.get("temperature", 0.3))
                enable_thinking = bool(json_body.get("enable_thinking", False))
                model_name = json_body.get("model", "codey")

                port = int(os.getenv("PRIMARY_SERVER_PORT", "8080"))
                host = os.getenv("PRIMARY_SERVER_HOST", "127.0.0.1")

                reservation_token = None
                try:
                    from core.resource_gate import (
                        release_context_budget,
                        wait_and_reserve_context_budget,
                    )

                    budget_decision = wait_and_reserve_context_budget(
                        port, messages, max_tokens, host=host
                    )
                    if not budget_decision.admitted:
                        return 429, {"Content-Type": "application/json"}, {
                            "error": f"AI model context-budget admission refused: {budget_decision.reason}"
                        }
                    reservation_token = budget_decision.reservation_token
                except ImportError:
                    pass
                except Exception as e:
                    return 503, {"Content-Type": "application/json"}, {
                        "error": f"Context budget gate error: {str(e)}"
                    }

                try:
                    req_payload = {
                        "model": model_name,
                        "messages": messages,
                        "max_tokens": max_tokens,
                        "temperature": temperature,
                        "chat_template_kwargs": {"enable_thinking": enable_thinking},
                    }
                    data_bytes = json.dumps(req_payload).encode("utf-8")
                    req = urllib.request.Request(
                        f"http://{host}:{port}/v1/chat/completions",
                        data=data_bytes,
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    with urllib.request.urlopen(req, timeout=180.0) as resp:
                        resp_data = json.loads(resp.read().decode("utf-8"))
                        return resp.status, {"Content-Type": "application/json"}, resp_data
                except urllib.error.HTTPError as http_err:
                    err_body = http_err.read().decode("utf-8", errors="replace")
                    try:
                        err_json = json.loads(err_body)
                    except Exception:
                        err_json = {"error": err_body or str(http_err)}
                    return http_err.code, {"Content-Type": "application/json"}, err_json
                except Exception as e:
                    return 502, {"Content-Type": "application/json"}, {
                        "error": f"AI completion upstream error: {str(e)}"
                    }
                finally:
                    if reservation_token:
                        try:
                            from core.resource_gate import release_context_budget

                            release_context_budget(port, reservation_token)
                        except Exception:
                            pass

            # ==========================================
            # OPERATIONS DOMAIN ENGINE (Phase B3)
            # ==========================================

            # Project Lifecycle & Summary
            if path.startswith("/api/v1/operations/projects/") and (path.endswith("/stage") or path.endswith("/transition")) and method == "POST":
                proj_id = int(path.split("/")[5])
                target_stage = json_body.get("target_stage") or json_body.get("stage", "")
                notes = json_body.get("notes")
                reason = json_body.get("reason")
                updated_p = self.operations.transition_project_stage(proj_id, target_stage, actor, notes=notes, reason=reason)
                return 200, {"Content-Type": "application/json"}, {"status": "ok", "project": updated_p.to_dict()}

            if path.startswith("/api/v1/operations/projects/") and path.endswith("/summary") and method == "GET":
                proj_id = int(path.split("/")[5])
                summary = self.operations.get_project_summary(proj_id, actor)
                return 200, {"Content-Type": "application/json"}, summary

            # Project Milestones
            if path.startswith("/api/v1/operations/projects/") and path.endswith("/milestones"):
                proj_id = int(path.split("/")[5])
                if method == "GET":
                    milestones = self.operations.list_milestones(proj_id, actor)
                    return 200, {"Content-Type": "application/json"}, {"milestones": [m.to_dict() for m in milestones]}
                elif method == "POST":
                    m_data = dict(json_body)
                    m_data["project_id"] = proj_id
                    milestone = ProjectMilestone(**m_data)
                    created_m = self.operations.create_milestone(milestone, actor)
                    return 201, {"Content-Type": "application/json"}, {"status": "created", "milestone": created_m.to_dict()}

            if path.startswith("/api/v1/operations/projects/") and path.endswith("/equipment") and method == "GET":
                proj_id = int(path.split("/")[5])
                active_only = query_params.get("active_only", ["false"])[0].lower() in ("true", "1")
                deps = self.operations.list_project_deployments(proj_id, actor, active_only=active_only)
                return 200, {"Content-Type": "application/json"}, {"deployments": [d.to_dict() for d in deps]}

            if path.startswith("/api/v1/operations/milestones/"):
                sub_path = path[len("/api/v1/operations/milestones/"):]
                if "/" not in sub_path:
                    mid = int(sub_path)
                    if method == "GET":
                        m = self.operations.get_milestone(mid, actor)
                        if not m:
                            return 404, {"Content-Type": "application/json"}, {"error": "Milestone not found"}
                        return 200, {"Content-Type": "application/json"}, {"milestone": m.to_dict()}
                    elif method in ("PATCH", "POST"):
                        status = json_body.get("status")
                        notes = json_body.get("notes")
                        if status:
                            updated_m = self.operations.update_milestone_status(mid, status, actor, notes=notes)
                        else:
                            m = self.operations.get_milestone(mid, actor)
                            if not m:
                                return 404, {"Content-Type": "application/json"}, {"error": "Milestone not found"}
                            for k, v in json_body.items():
                                if hasattr(m, k):
                                    setattr(m, k, v)
                            updated_m = self.operations.update_milestone(m, actor)
                        return 200, {"Content-Type": "application/json"}, {"status": "ok", "milestone": updated_m.to_dict()}
                elif sub_path.endswith("/status") and method == "POST":
                    mid = int(sub_path.split("/")[0])
                    status = json_body.get("status", "")
                    notes = json_body.get("notes")
                    updated_m = self.operations.update_milestone_status(mid, status, actor, notes=notes)
                    return 200, {"Content-Type": "application/json"}, {"status": "ok", "milestone": updated_m.to_dict()}

            # Work Orders
            if path == "/api/v1/operations/work-orders":
                if method == "GET":
                    pid = query_params.get("project_id", [None])[0]
                    proj_id = int(pid) if pid else None
                    trade = query_params.get("trade", [None])[0]
                    status = query_params.get("status", [None])[0]
                    sid = query_params.get("subcontractor_id", [None])[0]
                    sub_id = int(sid) if sid else None
                    wos = self.operations.list_work_orders(
                        actor, project_id=proj_id, trade=trade, status=status, subcontractor_id=sub_id
                    )
                    return 200, {"Content-Type": "application/json"}, {"work_orders": [wo.to_dict() for wo in wos]}
                elif method == "POST":
                    wo = WorkOrder(**json_body)
                    created_wo = self.operations.create_work_order(wo, actor)
                    return 201, {"Content-Type": "application/json"}, {"status": "created", "work_order": created_wo.to_dict()}

            if path.startswith("/api/v1/operations/work-orders/") and path.endswith("/dispatch") and method == "POST":
                wo_id = int(path.split("/")[5])
                sub_id = int(json_body.get("subcontractor_id", 0))
                start = json_body.get("scheduled_start")
                end = json_body.get("scheduled_end")
                inst = json_body.get("instructions")
                override = bool(json_body.get("override_compliance", False))
                dispatched = self.operations.dispatch_work_order(
                    wo_id, sub_id, actor, scheduled_start=start, scheduled_end=end, instructions=inst, override_compliance=override
                )
                return 200, {"Content-Type": "application/json"}, {"status": "dispatched", "work_order": dispatched.to_dict()}

            if path.startswith("/api/v1/operations/work-orders/") and path.endswith("/accept") and method == "POST":
                wo_id = int(path.split("/")[5])
                notes = json_body.get("notes")
                accepted = self.operations.accept_work_order(wo_id, actor, notes=notes)
                return 200, {"Content-Type": "application/json"}, {"status": "accepted", "work_order": accepted.to_dict()}

            if path.startswith("/api/v1/operations/work-orders/") and path.endswith("/complete") and method == "POST":
                wo_id = int(path.split("/")[5])
                actual_end = json_body.get("actual_end")
                notes = json_body.get("notes")
                completed = self.operations.complete_work_order(wo_id, actor, actual_end=actual_end, notes=notes)
                return 200, {"Content-Type": "application/json"}, {"status": "completed", "work_order": completed.to_dict()}

            if path.startswith("/api/v1/operations/work-orders/") and path.endswith("/verify") and method == "POST":
                wo_id = int(path.split("/")[5])
                notes = json_body.get("notes")
                verified = self.operations.verify_work_order(wo_id, actor, notes=notes)
                return 200, {"Content-Type": "application/json"}, {"status": "verified", "work_order": verified.to_dict()}

            if path.startswith("/api/v1/operations/work-orders/") and path.endswith("/status") and method == "POST":
                wo_id = int(path.split("/")[5])
                status = json_body.get("status", "")
                start = json_body.get("actual_start")
                end = json_body.get("actual_end")
                notes = json_body.get("notes")
                updated_wo = self.operations.update_work_order_execution_status(
                    wo_id, status, actor, actual_start=start, actual_end=end, notes=notes
                )
                return 200, {"Content-Type": "application/json"}, {"status": "ok", "work_order": updated_wo.to_dict()}

            if path.startswith("/api/v1/operations/work-orders/") and "/" not in path[len("/api/v1/operations/work-orders/"):]:
                wo_id = int(path[len("/api/v1/operations/work-orders/"):])
                if method == "GET":
                    wo = self.operations.get_work_order(wo_id, actor)
                    if not wo:
                        return 404, {"Content-Type": "application/json"}, {"error": "Work order not found"}
                    return 200, {"Content-Type": "application/json"}, {"work_order": wo.to_dict()}
                elif method in ("PATCH", "POST", "PUT"):
                    existing_wo = self.operations.get_work_order(wo_id, actor)
                    if not existing_wo:
                        return 404, {"Content-Type": "application/json"}, {"error": "Work order not found"}
                    for k, v in json_body.items():
                        if hasattr(existing_wo, k):
                            setattr(existing_wo, k, v)
                    updated_wo = self.operations.update_work_order(existing_wo, actor)
                    return 200, {"Content-Type": "application/json"}, {"status": "ok", "work_order": updated_wo.to_dict()}

            # Subcontractor Matching
            if path == "/api/v1/operations/subcontractors/match" and method == "GET":
                trade = query_params.get("trade", [""])[0]
                if not trade:
                    return 400, {"Content-Type": "application/json"}, {"error": "Missing required query parameter: trade"}
                req_date = query_params.get("date", query_params.get("required_date", [None]))[0]
                area = query_params.get("service_area", [None])[0]
                req_ins = query_params.get("require_active_insurance", ["true"])[0].lower() in ("true", "1")
                matches = self.operations.match_subcontractors_for_trade(
                    trade, actor, required_date=req_date, service_area=area, require_active_insurance=req_ins
                )
                return 200, {"Content-Type": "application/json"}, {"matches": matches}

            # Equipment & Resource Tracking
            if path == "/api/v1/operations/equipment":
                if method == "GET":
                    cat = query_params.get("category", [None])[0]
                    st = query_params.get("status", [None])[0]
                    pid = query_params.get("project_id", [None])[0]
                    proj_id = int(pid) if pid else None
                    eq_list = self.operations.list_equipment(actor, category=cat, status=st, project_id=proj_id)
                    return 200, {"Content-Type": "application/json"}, {"equipment": [e.to_dict() for e in eq_list]}
                elif method == "POST":
                    eq = Equipment(**json_body)
                    created_eq = self.operations.create_equipment(eq, actor)
                    return 201, {"Content-Type": "application/json"}, {"status": "created", "equipment": created_eq.to_dict()}

            if path == "/api/v1/operations/equipment/deploy" and method == "POST":
                eq_id = int(json_body.get("equipment_id", 0))
                proj_id = int(json_body.get("project_id", 0))
                wo_id = int(json_body.get("work_order_id")) if json_body.get("work_order_id") else None
                return_due = json_body.get("return_due_at")
                initial_reading = json_body.get("initial_reading")
                condition_out = json_body.get("condition_out", "good")
                notes = json_body.get("notes")
                dep = self.operations.deploy_equipment(
                    eq_id,
                    proj_id,
                    actor,
                    work_order_id=wo_id,
                    return_due_at=return_due,
                    initial_reading=initial_reading,
                    condition_out=condition_out,
                    notes=notes,
                )
                return 200, {"Content-Type": "application/json"}, {"status": "deployed", "deployment": dep.to_dict()}

            if path == "/api/v1/operations/equipment/return" and method == "POST":
                dep_id = int(json_body.get("deployment_id", 0))
                final_reading = json_body.get("final_reading")
                condition_in = json_body.get("condition_in", "good")
                mark_maint = bool(json_body.get("mark_for_maintenance", False))
                notes = json_body.get("notes")
                dep = self.operations.return_equipment(
                    dep_id,
                    actor,
                    final_reading=final_reading,
                    condition_in=condition_in,
                    mark_for_maintenance=mark_maint,
                    notes=notes,
                )
                return 200, {"Content-Type": "application/json"}, {"status": "returned", "deployment": dep.to_dict()}

            if path.startswith("/api/v1/operations/equipment/") and path[len("/api/v1/operations/equipment/"):].isdigit() and method == "GET":
                eq_id = int(path[len("/api/v1/operations/equipment/"):])
                eq = self.operations.get_equipment(eq_id, actor)
                if not eq:
                    return 404, {"Content-Type": "application/json"}, {"error": "Equipment not found"}
                return 200, {"Content-Type": "application/json"}, {"equipment": eq.to_dict()}

            # -------------------------------------------------------------
            # Phase B5a: Finance & Bookkeeping Domain Endpoints
            # -------------------------------------------------------------
            if path == "/api/v1/finance/transactions" and method == "POST":
                txn = FinancialTransaction(
                    transaction_number=json_body.get("transaction_number", ""),
                    transaction_type=json_body.get("transaction_type", "payment_received"),
                    amount=float(json_body.get("amount", 0.0)),
                    category=json_body.get("category"),
                    payment_method=json_body.get("payment_method"),
                    reference_number=json_body.get("reference_number"),
                    customer_id=json_body.get("customer_id"),
                    project_id=json_body.get("project_id"),
                    invoice_id=json_body.get("invoice_id"),
                    vendor_id=json_body.get("vendor_id"),
                    transaction_date=json_body.get("transaction_date", ""),
                    notes=json_body.get("notes"),
                )
                res = self.finance.record_transaction(txn, actor)
                return 201, {"Content-Type": "application/json"}, {"status": "created", "transaction": res.to_dict()}

            if path == "/api/v1/finance/transactions" and method == "GET":
                proj_id = int(query_params["project_id"][0]) if "project_id" in query_params else None
                cust_id = int(query_params["customer_id"][0]) if "customer_id" in query_params else None
                ttype = query_params["transaction_type"][0] if "transaction_type" in query_params else None
                limit = int(query_params.get("limit", [50])[0])
                offset = int(query_params.get("offset", [0])[0])
                txns = self.finance.list_transactions(actor, project_id=proj_id, customer_id=cust_id, transaction_type=ttype, limit=limit, offset=offset)
                return 200, {"Content-Type": "application/json"}, {"transactions": [t.to_dict() for t in txns]}

            if path.startswith("/api/v1/finance/projects/") and path.endswith("/pnl") and method == "GET":
                proj_id = int(path.split("/")[-2])
                pnl = self.finance.get_project_pnl(proj_id, actor)
                return 200, {"Content-Type": "application/json"}, {"pnl": pnl}

            if path == "/api/v1/finance/ar-aging" and method == "GET":
                aging = self.finance.get_ar_aging(actor)
                return 200, {"Content-Type": "application/json"}, {"ar_aging": aging}

            if path == "/api/v1/finance/summary" and method == "GET":
                summary = self.finance.get_financial_summary(actor)
                return 200, {"Content-Type": "application/json"}, {"financial_summary": summary}

            # -------------------------------------------------------------
            # Phase B5a: Marketing & Review Management Endpoints
            # -------------------------------------------------------------
            if path == "/api/v1/marketing/campaigns" and method == "POST":
                camp = MarketingCampaign(
                    name=json_body.get("name", ""),
                    channel=json_body.get("channel", "google_ads"),
                    status=json_body.get("status", "planning"),
                    budget=float(json_body.get("budget", 0.0)),
                    actual_spend=float(json_body.get("actual_spend", 0.0)),
                    leads_generated=int(json_body.get("leads_generated", 0)),
                    revenue_attributed=float(json_body.get("revenue_attributed", 0.0)),
                    start_date=json_body.get("start_date"),
                    end_date=json_body.get("end_date"),
                    notes=json_body.get("notes"),
                )
                res = self.business_ops.create_campaign(camp, actor)
                return 201, {"Content-Type": "application/json"}, {"status": "created", "campaign": res.to_dict()}

            if path == "/api/v1/marketing/campaigns" and method == "GET":
                camps = self.business_ops.list_campaigns(actor)
                return 200, {"Content-Type": "application/json"}, {"campaigns": [c.to_dict() for c in camps]}

            if path == "/api/v1/marketing/reviews/request" and method == "POST":
                req = ReviewRequest(
                    customer_id=int(json_body.get("customer_id", 0)),
                    project_id=json_body.get("project_id"),
                    platform=json_body.get("platform", "google"),
                )
                res = self.business_ops.create_review_request(req, actor)
                return 201, {"Content-Type": "application/json"}, {"status": "sent", "review_request": res.to_dict()}

            if path.startswith("/api/v1/marketing/reviews/") and path.endswith("/submit") and method == "POST":
                req_id = int(path.split("/")[-2])
                rating = int(json_body.get("rating", 5))
                feedback = json_body.get("feedback", "")
                res = self.business_ops.submit_review(req_id, rating, feedback)
                return 200, {"Content-Type": "application/json"}, {"status": "submitted", "review": res.to_dict()}

            if path == "/api/v1/marketing/reviews" and method == "GET":
                reviews = self.business_ops.list_reviews(actor)
                return 200, {"Content-Type": "application/json"}, {"reviews": [r.to_dict() for r in reviews]}

            # -------------------------------------------------------------
            # Phase B5a: Compliance & Certifications Endpoints
            # -------------------------------------------------------------
            if path == "/api/v1/compliance/items" and method == "POST":
                item = ComplianceItem(
                    title=json_body.get("title", ""),
                    category=json_body.get("category", "general_liability"),
                    entity_type=json_body.get("entity_type", "company"),
                    entity_id=json_body.get("entity_id"),
                    license_number=json_body.get("license_number"),
                    issuer=json_body.get("issuer"),
                    issue_date=json_body.get("issue_date"),
                    expiration_date=json_body.get("expiration_date", ""),
                    document_id=json_body.get("document_id"),
                    notes=json_body.get("notes"),
                )
                res = self.business_ops.create_compliance_item(item, actor)
                return 201, {"Content-Type": "application/json"}, {"status": "created", "compliance_item": res.to_dict()}

            if path == "/api/v1/compliance/items" and method == "GET":
                etype = query_params["entity_type"][0] if "entity_type" in query_params else None
                stat = query_params["status"][0] if "status" in query_params else None
                items = self.business_ops.list_compliance_items(actor, entity_type=etype, status=stat)
                return 200, {"Content-Type": "application/json"}, {"compliance_items": [i.to_dict() for i in items]}

            if path == "/api/v1/compliance/scan" and method == "POST":
                days = int(json_body.get("threshold_days", 30))
                scan_res = self.business_ops.scan_compliance_expirations(actor, threshold_days=days)
                return 200, {"Content-Type": "application/json"}, {"status": "scanned", "results": scan_res}

            # -------------------------------------------------------------
            # Phase B5a: HR & Timesheets Endpoints
            # -------------------------------------------------------------
            if path == "/api/v1/hr/employees" and method == "POST":
                emp = Employee(
                    user_id=json_body.get("user_id"),
                    first_name=json_body.get("first_name", ""),
                    last_name=json_body.get("last_name", ""),
                    role_title=json_body.get("role_title", ""),
                    department=json_body.get("department", "operations"),
                    phone=json_body.get("phone"),
                    email=json_body.get("email"),
                    hourly_rate=float(json_body.get("hourly_rate", 0.0)),
                    hire_date=json_body.get("hire_date"),
                    status=json_body.get("status", "active"),
                    emergency_contact=json_body.get("emergency_contact"),
                )
                res = self.business_ops.create_employee(emp, actor)
                return 201, {"Content-Type": "application/json"}, {"status": "created", "employee": res.to_dict()}

            if path == "/api/v1/hr/employees" and method == "GET":
                dept = query_params["department"][0] if "department" in query_params else None
                stat = query_params["status"][0] if "status" in query_params else None
                emps = self.business_ops.list_employees(actor, department=dept, status=stat)
                return 200, {"Content-Type": "application/json"}, {"employees": [e.to_dict() for e in emps]}

            if path == "/api/v1/hr/timesheets" and method == "POST":
                ts = Timesheet(
                    employee_id=int(json_body.get("employee_id", 0)),
                    project_id=json_body.get("project_id"),
                    work_order_id=json_body.get("work_order_id"),
                    work_date=json_body.get("work_date", ""),
                    hours_worked=float(json_body.get("hours_worked", 0.0)),
                    work_type=json_body.get("work_type", "regular"),
                    hourly_rate=float(json_body.get("hourly_rate", 0.0)),
                    notes=json_body.get("notes"),
                    status=json_body.get("status", "submitted"),
                )
                res = self.business_ops.submit_timesheet(ts, actor)
                return 201, {"Content-Type": "application/json"}, {"status": "submitted", "timesheet": res.to_dict()}

            if path == "/api/v1/hr/timesheets" and method == "GET":
                emp_id = int(query_params["employee_id"][0]) if "employee_id" in query_params else None
                proj_id = int(query_params["project_id"][0]) if "project_id" in query_params else None
                stat = query_params["status"][0] if "status" in query_params else None
                timesheets = self.business_ops.list_timesheets(actor, employee_id=emp_id, project_id=proj_id, status=stat)
                return 200, {"Content-Type": "application/json"}, {"timesheets": [t.to_dict() for t in timesheets]}

            if path.startswith("/api/v1/hr/timesheets/") and path.endswith("/approve") and method == "POST":
                ts_id = int(path.split("/")[-2])
                res = self.business_ops.approve_timesheet(ts_id, actor)
                return 200, {"Content-Type": "application/json"}, {"status": "approved", "timesheet": res.to_dict()}

            # -------------------------------------------------------------
            # Phase B5a: Procurement & Vendors Endpoints
            # -------------------------------------------------------------
            if path == "/api/v1/procurement/vendors" and method == "POST":
                vendor = Vendor(
                    company_name=json_body.get("company_name", ""),
                    contact_name=json_body.get("contact_name"),
                    phone=json_body.get("phone"),
                    email=json_body.get("email"),
                    address=json_body.get("address"),
                    category=json_body.get("category", "building_materials"),
                    payment_terms=json_body.get("payment_terms", "net_30"),
                    rating=float(json_body.get("rating")) if json_body.get("rating") is not None else None,
                    notes=json_body.get("notes"),
                )
                res = self.business_ops.create_vendor(vendor, actor)
                return 201, {"Content-Type": "application/json"}, {"status": "created", "vendor": res.to_dict()}

            if path == "/api/v1/procurement/vendors" and method == "GET":
                cat = query_params["category"][0] if "category" in query_params else None
                vendors = self.business_ops.list_vendors(actor, category=cat)
                return 200, {"Content-Type": "application/json"}, {"vendors": [v.to_dict() for v in vendors]}

            if path == "/api/v1/procurement/purchase-orders" and method == "POST":
                po = PurchaseOrder(
                    po_number=json_body.get("po_number", ""),
                    vendor_id=int(json_body.get("vendor_id", 0)),
                    project_id=json_body.get("project_id"),
                    status=json_body.get("status", "draft"),
                    items=json_body.get("items", []),
                    subtotal=float(json_body.get("subtotal", 0.0)),
                    tax_amount=float(json_body.get("tax_amount", 0.0)),
                    total_amount=float(json_body.get("total_amount", 0.0)),
                    expected_date=json_body.get("expected_date"),
                    notes=json_body.get("notes"),
                )
                res = self.business_ops.create_purchase_order(po, actor)
                return 201, {"Content-Type": "application/json"}, {"status": "created", "purchase_order": res.to_dict()}

            if path == "/api/v1/procurement/purchase-orders" and method == "GET":
                ven_id = int(query_params["vendor_id"][0]) if "vendor_id" in query_params else None
                proj_id = int(query_params["project_id"][0]) if "project_id" in query_params else None
                stat = query_params["status"][0] if "status" in query_params else None
                pos = self.business_ops.list_purchase_orders(actor, vendor_id=ven_id, project_id=proj_id, status=stat)
                return 200, {"Content-Type": "application/json"}, {"purchase_orders": [p.to_dict() for p in pos]}

            if path.startswith("/api/v1/procurement/purchase-orders/") and path.endswith("/receive") and method == "POST":
                po_id = int(path.split("/")[-2])
                res = self.business_ops.receive_purchase_order(po_id, actor)
                return 200, {"Content-Type": "application/json"}, {"status": "received", "purchase_order": res.to_dict()}

            # -------------------------------------------------------------
            # Phase B5a: Global Search & Executive Reporting Endpoints
            # -------------------------------------------------------------
            if path == "/api/v1/search" and method == "GET":
                q = query_params.get("q", [""])[0]
                limit_cat = int(query_params.get("limit", [10])[0])
                search_res = self.analytics_search.global_search(q, actor, limit_per_category=limit_cat)
                return 200, {"Content-Type": "application/json"}, search_res

            if path == "/api/v1/reports/summary" and method == "GET":
                summary = self.analytics_search.get_executive_dashboard(actor)
                return 200, {"Content-Type": "application/json"}, {"dashboard": summary}

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
