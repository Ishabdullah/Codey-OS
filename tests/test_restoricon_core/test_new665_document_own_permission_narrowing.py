"""
Unit tests for NEW-665: crm_service.py's list_documents/get_document narrowed
row access by permission, not by `actor.role == ROLE_CUSTOMER`.

Before this fix, the customer-row isolation in both methods keyed
specifically on `actor.role == ROLE_CUSTOMER`, even though
custom_permissions_json can grant PERM_READ_OWN_DOCUMENTS to any role.
A non-customer actor custom-granted PERM_READ_OWN_DOCUMENTS alone (lacking
the broader PERM_READ_DOCUMENTS) got the SAME unrestricted, company-wide
document access as a full PERM_READ_DOCUMENTS holder -- the "own" in the
permission's name was unenforced for anyone but literal ROLE_CUSTOMER.

The fix narrows by `not actor.has_permission(PERM_READ_DOCUMENTS)` instead,
and fails closed (empty list / PermissionError, not "everything") when the
narrowed actor's customer_id is None -- the normal case for a non-customer
role, since customer_id is only meaningfully populated for ROLE_CUSTOMER
accounts today.
"""

import pytest

from restoricon_core.auth import (
    AuthContext,
    AuthService,
    PERM_READ_DOCUMENTS,
    PERM_READ_OWN_DOCUMENTS,
    ROLE_ADMIN,
    ROLE_CUSTOMER,
    ROLE_TECHNICIAN,
)
from restoricon_core.database import DatabaseManager
from restoricon_core.models import Customer, Document
from restoricon_core.services.audit_service import AuditService
from restoricon_core.services.crm_service import CRMService


@pytest.fixture
def env():
    db = DatabaseManager(":memory:")
    auth_service = AuthService(db)
    audit_service = AuditService(db)
    crm_service = CRMService(db, audit_service)
    return {
        "db": db,
        "auth": auth_service,
        "crm": crm_service,
    }


@pytest.fixture
def actors(env):
    auth = env["auth"]
    u_admin = auth.create_user("admin_665", "Pass123!", "Admin", "admin_665@test.com", role=ROLE_ADMIN)
    ctx_admin = AuthContext(u_admin.id, u_admin.username, ROLE_ADMIN, "human")

    u_tech = auth.create_user("tech_665", "Pass123!", "Tech", "tech_665@test.com", role=ROLE_TECHNICIAN)
    # custom_permissions_json grant of PERM_READ_OWN_DOCUMENTS to a
    # non-customer role, with no customer_id -- the exact latent gap
    # NEW-665 describes. ROLE_TECHNICIAN holds PERM_READ_DOCUMENTS by
    # default (like every non-customer built-in role), so it's explicitly
    # overridden False here to simulate an actor who only ever holds the
    # narrower PERM_READ_OWN_DOCUMENTS grant.
    ctx_tech_own_docs = AuthContext(
        u_tech.id,
        u_tech.username,
        ROLE_TECHNICIAN,
        "human",
        custom_permissions={PERM_READ_DOCUMENTS: False, PERM_READ_OWN_DOCUMENTS: True},
    )

    return {
        "admin": ctx_admin,
        "tech_own_docs": ctx_tech_own_docs,
    }


@pytest.fixture
def customers(env, actors):
    cust_a = env["crm"].create_customer(
        Customer(first_name="Alice", last_name="A", email="alice_665@example.com"),
        actors["admin"],
    )
    cust_b = env["crm"].create_customer(
        Customer(first_name="Bob", last_name="B", email="bob_665@example.com"),
        actors["admin"],
    )
    return {"a": cust_a, "b": cust_b}


def _make_customer_ctx(env, customer):
    auth = env["auth"]
    u = auth.create_user(
        f"cust_665_{customer.id}",
        "Pass123!",
        "Customer",
        f"cust_665_{customer.id}@example.com",
        role=ROLE_CUSTOMER,
        customer_id=customer.id,
    )
    return AuthContext(u.id, u.username, ROLE_CUSTOMER, "human", customer_id=customer.id)


@pytest.fixture
def documents(env, actors, customers):
    doc_a = env["crm"].create_document(
        Document(customer_id=customers["a"].id, document_type="contract", title="Doc A", file_path="/tmp/a.pdf"),
        actors["admin"],
    )
    doc_b = env["crm"].create_document(
        Document(customer_id=customers["b"].id, document_type="contract", title="Doc B", file_path="/tmp/b.pdf"),
        actors["admin"],
    )
    # A document with no customer_id at all (company-wide, not linked to
    # any customer's "own" scope).
    doc_unlinked = env["crm"].create_document(
        Document(customer_id=None, document_type="permit", title="Unlinked", file_path="/tmp/u.pdf"),
        actors["admin"],
    )
    return {"a": doc_a, "b": doc_b, "unlinked": doc_unlinked}


# ==========================================
# ROLE_CUSTOMER -- existing behavior must be unchanged
# ==========================================


def test_customer_list_documents_sees_only_own(env, customers, documents):
    ctx = _make_customer_ctx(env, customers["a"])
    docs = env["crm"].list_documents(ctx)
    ids = {d.id for d in docs}
    assert documents["a"].id in ids
    assert documents["b"].id not in ids
    assert documents["unlinked"].id not in ids


def test_customer_get_document_denied_for_other_customers_doc(env, customers, documents):
    ctx = _make_customer_ctx(env, customers["a"])
    assert env["crm"].get_document(documents["a"].id, ctx) is not None
    with pytest.raises(PermissionError):
        env["crm"].get_document(documents["b"].id, ctx)


# ==========================================
# NEW-665: non-customer role custom-granted PERM_READ_OWN_DOCUMENTS
# ==========================================


def test_non_customer_own_docs_actor_cannot_list_other_customers_documents(env, actors, documents):
    """This is the gap: before the fix, a non-customer actor holding only
    PERM_READ_OWN_DOCUMENTS (no customer_id) saw every document, identical
    to a PERM_READ_DOCUMENTS holder. After the fix, they see none -- fail
    closed, not an error."""
    assert not actors["tech_own_docs"].has_permission(PERM_READ_DOCUMENTS)
    assert actors["tech_own_docs"].has_permission(PERM_READ_OWN_DOCUMENTS)
    assert actors["tech_own_docs"].customer_id is None

    docs = env["crm"].list_documents(actors["tech_own_docs"])
    assert docs == []


def test_non_customer_own_docs_actor_cannot_get_other_customers_document(env, actors, documents):
    with pytest.raises(PermissionError):
        env["crm"].get_document(documents["a"].id, actors["tech_own_docs"])
    with pytest.raises(PermissionError):
        env["crm"].get_document(documents["unlinked"].id, actors["tech_own_docs"])


def test_non_customer_own_docs_actor_with_customer_id_sees_only_that_customer(env, actors, customers, documents):
    """Positive case: the narrowing must actually narrow to the actor's
    own customer_id, not blanket-deny everyone lacking PERM_READ_DOCUMENTS.
    A non-customer role custom-granted PERM_READ_OWN_DOCUMENTS AND a
    customer_id sees that customer's documents, not the other customer's."""
    ctx = AuthContext(
        actors["tech_own_docs"].user_id,
        actors["tech_own_docs"].username,
        actors["tech_own_docs"].role,
        "human",
        customer_id=customers["a"].id,
        custom_permissions={PERM_READ_DOCUMENTS: False, PERM_READ_OWN_DOCUMENTS: True},
    )

    docs = env["crm"].list_documents(ctx)
    ids = {d.id for d in docs}
    assert documents["a"].id in ids
    assert documents["b"].id not in ids
    assert documents["unlinked"].id not in ids

    assert env["crm"].get_document(documents["a"].id, ctx) is not None
    with pytest.raises(PermissionError):
        env["crm"].get_document(documents["b"].id, ctx)


def test_read_documents_holder_still_sees_everything(env, actors, documents):
    """Regression: a genuine PERM_READ_DOCUMENTS holder (admin) is
    unaffected by this narrowing."""
    docs = env["crm"].list_documents(actors["admin"])
    ids = {d.id for d in docs}
    assert documents["a"].id in ids
    assert documents["b"].id in ids
    assert documents["unlinked"].id in ids

    assert env["crm"].get_document(documents["a"].id, actors["admin"]) is not None
    assert env["crm"].get_document(documents["b"].id, actors["admin"]) is not None
