"""
Unit/integration tests for B8.6d-a: reportlab-based PDF renderer
(restoricon_core/services/pdf_service.py) + its wiring into sign_contract.

Covers:
  - render_pdf produces valid PDF bytes for a real base64 PNG signature
    (the HTML5-canvas e-signature shape).
  - render_pdf produces valid PDF bytes for a non-image signature_data
    string (typed-text stamp branch), including the specific
    'portal_countersignature' sentinel and an arbitrary opaque token (the
    routes.py default 'digital_signature_token' shape) -- not just the one
    named sentinel string.
  - End-to-end: sign_contract creates a Document row (customer_id +
    document_type="contract") whose file_path genuinely exists on disk.
  - Visibility: the new document is retrievable via both the
    customer-portal documents route and the Customer 360
    /api/v1/documents?customer_id= route.
"""

from __future__ import annotations

import base64
import io
import json
import os

import pytest
from PIL import Image

from restoricon_core.api.routes import APIRouter
from restoricon_core.auth import (
    AuthContext,
    AuthService,
    ROLE_ADMIN,
    ROLE_CUSTOMER,
    ROLE_SALES,
)
from restoricon_core.database import DatabaseManager
from restoricon_core.models import Contract, Customer, Document
from restoricon_core.services.audit_service import AuditService
from restoricon_core.services.automation_service import AutomationService
from restoricon_core.services.communication_service import CommunicationService
from restoricon_core.services.crm_service import CRMService
from restoricon_core.services.operations_service import OperationsService
from restoricon_core.services.scheduling_service import SchedulingService
from restoricon_core.services.pdf_service import (
    DocumentField,
    DocumentSpec,
    SignatureAnchor,
    is_data_url_image,
    render_contract_pdf,
    render_pdf,
)


def _png_data_url() -> str:
    img = Image.new("RGBA", (20, 10), (10, 20, 30, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _assert_valid_pdf(pdf_bytes: bytes) -> None:
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 200
    assert pdf_bytes.startswith(b"%PDF-")
    assert b"%%EOF" in pdf_bytes


# ---------------------------------------------------------------------------
# Renderer unit tests
# ---------------------------------------------------------------------------

def _spec():
    return DocumentSpec(
        title="Test Contract",
        fields=[DocumentField("Contract Number", "CTR-TEST-1"), DocumentField("Status", "signed")],
        body="Line one of the contract body.\nLine two.",
        signature_anchors=[SignatureAnchor(party_role="customer", page=1, x=54, y=120, label="Signature")],
    )


def test_render_pdf_with_real_base64_png_signature():
    data_url = _png_data_url()
    assert is_data_url_image(data_url) is True
    pdf_bytes = render_pdf(_spec(), data_url, signer_label="Signed by Jane Doe on 2026-09-22T00:00:00Z")
    _assert_valid_pdf(pdf_bytes)


def test_render_pdf_with_portal_countersignature_text_stamp():
    assert is_data_url_image("portal_countersignature") is False
    pdf_bytes = render_pdf(_spec(), "portal_countersignature", signer_label="Signed by Staff User on 2026-09-22T00:00:00Z")
    _assert_valid_pdf(pdf_bytes)


def test_render_pdf_with_arbitrary_opaque_token_also_uses_text_stamp():
    """Not just the one named 'portal_countersignature' sentinel --
    routes.py's real default ('digital_signature_token') and ad hoc test
    tokens (e.g. 'sig-admin-2') must also land in the typed-text branch,
    not raise trying to decode them as an image."""
    assert is_data_url_image("digital_signature_token") is False
    assert is_data_url_image("sig-admin-2") is False
    pdf_bytes = render_pdf(_spec(), "digital_signature_token", signer_label="Signed by Rep on 2026-09-22T00:00:00Z")
    _assert_valid_pdf(pdf_bytes)


def test_render_pdf_with_malformed_image_data_url_falls_back_to_text():
    """An image-shaped but corrupt data URL must not raise -- it falls
    back to the typed-text stamp instead of aborting PDF generation."""
    bad_data_url = "data:image/png;base64,not-valid-base64!!!"
    pdf_bytes = render_pdf(_spec(), bad_data_url, signer_label="Signed by Jane Doe on 2026-09-22T00:00:00Z")
    _assert_valid_pdf(pdf_bytes)


def test_render_contract_pdf_builds_spec_from_contract_fields():
    contract = Contract(
        id=1, contract_number="CTR-9", customer_id=5, title="Roof Repair Agreement",
        content="Scope of work...", status="signed", customer_signed_at="2026-09-22T00:00:00Z",
        customer_signature_data=_png_data_url(),
    )
    pdf_bytes = render_contract_pdf(contract, "Signed by Jane Doe on 2026-09-22T00:00:00Z")
    _assert_valid_pdf(pdf_bytes)


# ---------------------------------------------------------------------------
# End-to-end: sign_contract -> Document row + real file on disk
# ---------------------------------------------------------------------------

@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("RESTORICON_DOC_STORE_PATH", str(tmp_path / "docstore"))
    db = DatabaseManager(":memory:")
    audit_service = AuditService(db)
    crm_service = CRMService(db, audit_service)
    auth_service = AuthService(db)

    admin_user = auth_service.create_user(
        username="pdf_admin", plain_password="Password123", full_name="Admin",
        email="pdf_admin@test.com", role=ROLE_ADMIN,
    )
    admin = AuthContext(user_id=admin_user.id, username="pdf_admin", role=ROLE_ADMIN, actor_type="human")

    cust = crm_service.create_customer(
        Customer(first_name="Pat", last_name="Signer", email="pat_signer@test.com"), admin,
    )
    customer_user = auth_service.create_user(
        username="pat_signer", plain_password="Password123", full_name="Pat Signer",
        email="pat_signer_login@test.com", role=ROLE_CUSTOMER, customer_id=cust.id,
    )
    actor_customer = AuthContext(
        user_id=customer_user.id, username="pat_signer", role=ROLE_CUSTOMER,
        actor_type="human", customer_id=cust.id,
    )

    contract = crm_service.create_contract(
        Contract(contract_number="CTR-E2E-1", customer_id=cust.id, title="E2E Contract", content="Body text."),
        admin,
    )
    return {
        "db": db, "crm": crm_service, "audit": audit_service, "auth": auth_service,
        "admin": admin, "cust": cust, "actor_customer": actor_customer, "contract": contract,
    }


def test_sign_contract_creates_pdf_document_row_and_file(env):
    crm = env["crm"]
    signed = crm.sign_contract(env["contract"].id, _png_data_url(), env["actor_customer"])
    assert signed.status == "signed"

    docs = crm.list_documents(env["admin"], customer_id=env["cust"].id, document_type="contract")
    assert len(docs) == 1
    doc = docs[0]
    assert doc.customer_id == env["cust"].id
    assert doc.document_type == "contract"
    assert doc.mime_type == "application/pdf"
    assert doc.file_size_bytes > 200
    assert os.path.isfile(doc.file_path)
    with open(doc.file_path, "rb") as fh:
        _assert_valid_pdf(fh.read())


def test_sign_contract_customer_self_sign_does_not_permission_error_on_pdf_side_effect(env):
    """ROLE_CUSTOMER holds PERM_SIGN_CONTRACTS but not PERM_WRITE_DOCUMENTS
    (auth.py) -- the PDF-generation side effect must use its own system
    actor for create_document, not the real signer, or this raises."""
    crm = env["crm"]
    signed = crm.sign_contract(env["contract"].id, "portal_countersignature", env["actor_customer"])
    assert signed.status == "signed"
    docs = crm.list_documents(env["admin"], customer_id=env["cust"].id, document_type="contract")
    assert len(docs) == 1


# ---------------------------------------------------------------------------
# Route-level visibility: portal documents route + Customer 360 route
# ---------------------------------------------------------------------------

@pytest.fixture
def route_env(tmp_path, monkeypatch):
    monkeypatch.setenv("RESTORICON_DOC_STORE_PATH", str(tmp_path / "docstore"))
    db = DatabaseManager(":memory:")
    auth_service = AuthService(db)
    audit_service = AuditService(db)
    comm_service = CommunicationService(db)
    crm_service = CRMService(db, audit_service)
    sched_service = SchedulingService(db, audit_service)
    auto_service = AutomationService(db, audit_service)
    ops_service = OperationsService(db, audit_service)
    router = APIRouter(
        auth_service=auth_service,
        crm_service=crm_service,
        comm_service=comm_service,
        audit_service=audit_service,
        scheduling_service=sched_service,
        automation_service=auto_service,
        operations_service=ops_service,
    )

    admin_user = auth_service.create_user("pdf_route_admin", "Pass123!", "Admin", "pdf_route_admin@r.com", role=ROLE_ADMIN)
    admin_token = auth_service.create_token(admin_user)
    actor_admin = AuthContext(admin_user.id, "pdf_route_admin", ROLE_ADMIN, "human", token=admin_token)

    sales_user = auth_service.create_user("pdf_route_sales", "Pass123!", "Sales", "pdf_route_sales@r.com", role=ROLE_SALES)
    sales_token = auth_service.create_token(sales_user)
    actor_sales = AuthContext(sales_user.id, "pdf_route_sales", ROLE_SALES, "human", token=sales_token)

    cust = crm_service.create_customer(
        Customer(first_name="Route", last_name="Pdf", email="route_pdf@r.com"), actor_admin,
    )
    customer_user = auth_service.create_user(
        "pdf_route_cust", "Pass123!", "Route Pdf", "route_pdf_login@r.com", role=ROLE_CUSTOMER, customer_id=cust.id,
    )
    customer_token = auth_service.create_token(customer_user)
    actor_customer = AuthContext(
        customer_user.id, "pdf_route_cust", ROLE_CUSTOMER, "human", customer_id=cust.id, token=customer_token,
    )

    contract = crm_service.create_contract(
        Contract(contract_number="CTR-RT-PDF-1", customer_id=cust.id, title="Route PDF Contract", content="Body."),
        actor_admin,
    )
    crm_service.sign_contract(contract.id, _png_data_url(), actor_customer)

    return {
        "router": router, "cust": cust,
        "actor_admin": actor_admin, "actor_sales": actor_sales, "actor_customer": actor_customer,
    }


def _hdr(ctx):
    return {"Authorization": f"Bearer {ctx.token}"}


def test_signed_contract_pdf_visible_via_portal_documents_route(route_env):
    status, _, data = route_env["router"].handle_request(
        "GET", "/api/v1/portal/documents", _hdr(route_env["actor_customer"]), b"",
    )
    assert status == 200
    contract_docs = [d for d in data["documents"] if d["document_type"] == "contract"]
    assert len(contract_docs) == 1
    assert contract_docs[0]["customer_id"] == route_env["cust"].id


def test_signed_contract_pdf_visible_via_customer_360_documents_route(route_env):
    status, _, data = route_env["router"].handle_request(
        "GET", f"/api/v1/documents?customer_id={route_env['cust'].id}",
        _hdr(route_env["actor_sales"]), b"",
    )
    assert status == 200
    contract_docs = [d for d in data["documents"] if d["document_type"] == "contract"]
    assert len(contract_docs) == 1
    assert contract_docs[0]["customer_id"] == route_env["cust"].id
