"""
Unit tests for B8.7c (D6, sales_rep_portal.md §4 Phase 3, Ish-answered
2026-09-23): the portfolio-override commission -- a config-driven 5%
residual on gross collected revenue from major general-contracting
projects, for a config-driven 12 months from a customer's initial
HomeCare enrollment, gated independently by an employment-termination
check on the ORIGINATING (HomeCare) rep, never the GC contract's own
assigned_user_id/owner.

Covers CRMService._resolve_portfolio_override_eligibility's 5 gates in
isolation via record_payment (the only caller), plus
AuthService.set_user_active's new terminated_at transition-edge
semantics.
"""

from __future__ import annotations

import base64
import io

import pytest
from PIL import Image

from restoricon_core.auth import (
    AuthContext,
    AuthService,
    ROLE_ADMIN,
    ROLE_CUSTOMER,
    ROLE_SALES,
)
from restoricon_core.database import DatabaseManager
from restoricon_core.models import Contract, Customer, Invoice, Project
from restoricon_core.services.audit_service import AuditService
from restoricon_core.services.commission_service import CommissionService
from restoricon_core.services.crm_service import CRMService


def _png_data_url() -> str:
    img = Image.new("RGBA", (20, 10), (10, 20, 30, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("RESTORICON_DOC_STORE_PATH", str(tmp_path / "docstore"))
    db = DatabaseManager(":memory:")
    audit_service = AuditService(db)
    commission_service = CommissionService(db, audit_service)
    crm = CRMService(db, audit_service, commission_service=commission_service)
    auth_service = AuthService(db)

    admin_user = auth_service.create_user(
        username="po_admin", plain_password="Password123", full_name="Admin",
        email="po_admin@test.com", role=ROLE_ADMIN,
    )
    admin = AuthContext(user_id=admin_user.id, username="po_admin", role=ROLE_ADMIN, actor_type="human")

    hc_rep_user = auth_service.create_user(
        username="po_hc_rep", plain_password="Password123", full_name="HomeCare Rep",
        email="po_hc_rep@test.com", role=ROLE_SALES,
    )
    hc_rep = AuthContext(user_id=hc_rep_user.id, username="po_hc_rep", role=ROLE_SALES, actor_type="human")

    gc_rep_user = auth_service.create_user(
        username="po_gc_rep", plain_password="Password123", full_name="GC Rep",
        email="po_gc_rep@test.com", role=ROLE_SALES,
    )
    gc_rep = AuthContext(user_id=gc_rep_user.id, username="po_gc_rep", role=ROLE_SALES, actor_type="human")

    cust = crm.create_customer(
        Customer(first_name="Portfolio", last_name="Owner", email="portfolio_owner@test.com"),
        admin,
    )
    customer_user = auth_service.create_user(
        username="po_cust", plain_password="Password123", full_name="Portfolio Owner",
        email="po_cust_login@test.com", role=ROLE_CUSTOMER, customer_id=cust.id,
    )
    actor_customer = AuthContext(
        user_id=customer_user.id, username="po_cust", role=ROLE_CUSTOMER,
        actor_type="human", customer_id=cust.id,
    )

    return {
        "db": db, "crm": crm, "audit": audit_service, "auth": auth_service,
        "commission": commission_service, "admin": admin,
        "hc_rep": hc_rep, "gc_rep": gc_rep, "cust": cust,
        "actor_customer": actor_customer,
    }


def _enroll_homecare(env, contract_number="CTR-HC-1"):
    """HomeCare originating enrollment, owned by hc_rep."""
    contract = env["crm"].create_contract(
        Contract(
            contract_number=contract_number,
            customer_id=env["cust"].id,
            title="HomeCare Agreement",
            template_name="homecare_basic",
            content="Terms...",
        ),
        env["hc_rep"],
    )
    signed = env["crm"].sign_contract(contract.id, _png_data_url(), env["actor_customer"])
    assert signed.status == "signed"
    conn = env["db"].get_connection()
    sub = conn.execute(
        "SELECT * FROM homecare_subscriptions WHERE contract_id = ?;", (contract.id,)
    ).fetchone()
    assert sub["originating_rep_user_id"] == env["hc_rep"].user_id
    return sub


def _make_gc_project_and_contract(env, contract_number="CTR-GC-1", actor=None):
    """A GC project + signed general_remodeling contract, owned by gc_rep
    (deliberately a DIFFERENT rep from the HomeCare originating rep, so
    attribution tests can't pass by coincidence)."""
    project = env["crm"].create_project(
        Project(
            customer_id=env["cust"].id,
            title="Full Remodel",
            property_address="123 Main St",
            project_type="remodel",
        ),
        env["admin"],
    )
    contract = env["crm"].create_contract(
        Contract(
            contract_number=contract_number,
            customer_id=env["cust"].id,
            project_id=project.id,
            title="GC Agreement",
            template_name="general_remodeling",
            content="Terms...",
        ),
        actor or env["gc_rep"],
    )
    signed = env["crm"].sign_contract(contract.id, _png_data_url(), env["actor_customer"])
    assert signed.status == "signed"
    return project, signed


def _make_gc_invoice(env, project, amount=50000.0):
    return env["crm"].create_invoice(
        Invoice(customer_id=env["cust"].id, project_id=project.id, amount=amount, invoice_type="project"),
        env["admin"],
    )


def _backdate(db, table, id_field, id_value, field, iso_value):
    conn = db.get_connection()
    with conn:
        conn.execute(f"UPDATE {table} SET {field} = ? WHERE {id_field} = ?;", (iso_value, id_value))


def _make_gc_project_and_multiparty_contract(env, contract_number="CTR-GC-MP-1"):
    """A GC project + a contract opted into multi-party signing (B8.6d-b)
    via add_contract_signers, signed by TWO parties (customer, then
    admin as the last/completing signer) -- the path that flips
    contracts.status to 'signed' via sign_contract's `all_signed` branch
    WITHOUT ever writing Contract.customer_signed_at (round-2 Critical
    fix under test). Returns (project, contract, last_signed_iso) where
    last_signed_iso is the real completion timestamp
    (MAX(contract_signers.signed_at))."""
    project = env["crm"].create_project(
        Project(
            customer_id=env["cust"].id,
            title="Full Remodel (multi-party)",
            property_address="789 Elm St",
            project_type="remodel",
        ),
        env["admin"],
    )
    contract = env["crm"].create_contract(
        Contract(
            contract_number=contract_number,
            customer_id=env["cust"].id,
            project_id=project.id,
            title="GC Agreement (multi-party)",
            template_name="general_remodeling",
            content="Terms...",
        ),
        env["gc_rep"],
    )
    env["crm"].add_contract_signers(
        contract.id,
        [{"party_role": "customer"}, {"party_role": "admin"}],
        env["admin"],
    )
    partial = env["crm"].sign_contract(
        contract.id, _png_data_url(), env["actor_customer"], party_role="customer"
    )
    assert partial.status != "signed"  # one signer down, one pending
    completed = env["crm"].sign_contract(
        contract.id, _png_data_url(), env["admin"], party_role="admin"
    )
    assert completed.status == "signed"
    assert completed.customer_signed_at is None  # the bug's precondition

    conn = env["db"].get_connection()
    last_signed = conn.execute(
        "SELECT MAX(signed_at) AS ts FROM contract_signers WHERE contract_id = ?;",
        (contract.id,),
    ).fetchone()["ts"]
    assert last_signed is not None
    return project, completed, last_signed


# ---------------------------------------------------------------------------
# Core positive case
# ---------------------------------------------------------------------------

def test_eligible_gc_payment_produces_one_correctly_attributed_and_computed_override(env):
    _enroll_homecare(env)
    project, contract = _make_gc_project_and_contract(env)
    invoice = _make_gc_invoice(env, project, amount=50000.0)

    updated = env["crm"].record_payment(invoice.id, 10000.0, "check", "TXN-1", env["admin"])
    assert updated.status == "partially_paid"

    entries = env["commission"].list_commissions(env["admin"], rep_user_id=env["hc_rep"].user_id)
    override_entries = [e for e in entries if e.source_type == "portfolio_override"]
    assert len(override_entries) == 1
    entry = override_entries[0]
    assert entry.source_id == invoice.id
    # Attributed to the ORIGINATING (HomeCare) rep, never the GC
    # contract's own assigned_user_id (gc_rep).
    assert entry.rep_user_id == env["hc_rep"].user_id
    assert entry.rep_user_id != env["gc_rep"].user_id
    assert entry.basis_amount == 10000.0  # the increment, not the invoice total
    assert entry.commission_rate_or_flat == 0.05
    assert entry.commission_amount == 500.0
    assert entry.status == "earned"

    logs = env["audit"].query_logs(
        env["admin"], entity_type="invoice", entity_id=invoice.id, action="commission_recording_failed"
    )
    assert logs == []


def test_second_payment_on_same_invoice_produces_a_second_override_row_on_its_own_increment(env):
    """Not a status-transition edge -- fires on every record_payment call,
    basis = that call's own increment."""
    _enroll_homecare(env)
    project, contract = _make_gc_project_and_contract(env)
    invoice = _make_gc_invoice(env, project, amount=50000.0)

    env["crm"].record_payment(invoice.id, 10000.0, "check", "TXN-1", env["admin"])
    env["crm"].record_payment(invoice.id, 5000.0, "check", "TXN-2", env["admin"])

    entries = env["commission"].list_commissions(env["admin"], rep_user_id=env["hc_rep"].user_id)
    override_entries = [e for e in entries if e.source_type == "portfolio_override"]
    assert len(override_entries) == 2
    amounts = sorted(e.commission_amount for e in override_entries)
    assert amounts == [250.0, 500.0]


# ---------------------------------------------------------------------------
# 12-month window
# ---------------------------------------------------------------------------

def test_payment_more_than_window_past_initial_enrollment_produces_no_override(env):
    sub = _enroll_homecare(env)
    _backdate(env["db"], "homecare_subscriptions", "id", sub["id"], "enrolled_at", "2020-01-01T00:00:00+00:00")

    project, contract = _make_gc_project_and_contract(env)
    invoice = _make_gc_invoice(env, project)

    updated = env["crm"].record_payment(invoice.id, 10000.0, "check", "TXN-1", env["admin"])
    assert updated.status == "partially_paid"

    entries = env["commission"].list_commissions(env["admin"])
    override_entries = [e for e in entries if e.source_type == "portfolio_override"]
    assert override_entries == []
    logs = env["audit"].query_logs(
        env["admin"], entity_type="invoice", entity_id=invoice.id, action="commission_recording_failed"
    )
    assert logs == []


# ---------------------------------------------------------------------------
# Termination gate -- the counter-intuitive rule, tested explicitly
# ---------------------------------------------------------------------------

def test_gc_contract_signed_after_originating_rep_termination_produces_no_override(env):
    _enroll_homecare(env)

    # Terminate the ORIGINATING (HomeCare) rep BEFORE the GC contract is
    # signed -- note this is hc_rep, not gc_rep (the GC contract's own
    # owner), matching the real rule: the gate is on the originating
    # rep's employment status, not the GC contract owner's.
    env["auth"].set_user_active(env["hc_rep"].user_id, 0, env["admin"])

    project, contract = _make_gc_project_and_contract(env)  # signed after termination
    invoice = _make_gc_invoice(env, project)

    updated = env["crm"].record_payment(invoice.id, 10000.0, "check", "TXN-1", env["admin"])
    assert updated.status == "partially_paid"

    entries = env["commission"].list_commissions(env["admin"])
    override_entries = [e for e in entries if e.source_type == "portfolio_override"]
    assert override_entries == []
    logs = env["audit"].query_logs(
        env["admin"], entity_type="invoice", entity_id=invoice.id, action="commission_recording_failed"
    )
    assert logs == []


def test_gc_contract_signed_before_termination_still_pays_after_rep_leaves(env):
    """The specific, counter-intuitive rule from the real contract text: a
    naive "is the rep currently active" check would get this backwards."""
    _enroll_homecare(env)

    project, contract = _make_gc_project_and_contract(env)  # signed while hc_rep is still active

    # NOW terminate the originating rep -- AFTER the GC contract was
    # already signed.
    env["auth"].set_user_active(env["hc_rep"].user_id, 0, env["admin"])

    invoice = _make_gc_invoice(env, project)
    updated = env["crm"].record_payment(invoice.id, 10000.0, "check", "TXN-1", env["admin"])
    assert updated.status == "partially_paid"

    entries = env["commission"].list_commissions(env["admin"], rep_user_id=env["hc_rep"].user_id)
    override_entries = [e for e in entries if e.source_type == "portfolio_override"]
    assert len(override_entries) == 1
    assert override_entries[0].commission_amount == 500.0


# ---------------------------------------------------------------------------
# Round-2 Critical fix: multi-party-signed GC contracts (B8.6d-b) never
# write Contract.customer_signed_at, so gate 5's termination check (and
# gate 1b's contract-selection ORDER BY) must resolve the real signed
# timestamp via MAX(contract_signers.signed_at) instead.
# ---------------------------------------------------------------------------

def test_multiparty_signed_gc_contract_after_termination_produces_no_override(env):
    """The reviewer's exact live-reproduced Critical: terminate the
    originating rep BEFORE the GC project/contract even exists, sign the
    GC contract via multi-party (add_contract_signers + two sign_contract
    calls), record a payment -- must NOT produce an override. Before the
    fix, gate 5 always fell through to eligible=True for this path
    because customer_signed_at was permanently NULL."""
    _enroll_homecare(env)

    # Terminate the ORIGINATING (HomeCare) rep before the GC project or
    # contract exist at all.
    env["auth"].set_user_active(env["hc_rep"].user_id, 0, env["admin"])

    project, contract, last_signed = _make_gc_project_and_multiparty_contract(env)
    invoice = _make_gc_invoice(env, project)

    updated = env["crm"].record_payment(invoice.id, 10000.0, "check", "TXN-1", env["admin"])
    assert updated.status == "partially_paid"

    entries = env["commission"].list_commissions(env["admin"])
    override_entries = [e for e in entries if e.source_type == "portfolio_override"]
    assert override_entries == []
    logs = env["audit"].query_logs(
        env["admin"], entity_type="invoice", entity_id=invoice.id, action="commission_recording_failed"
    )
    assert logs == []


def test_multiparty_signed_gc_contract_before_termination_still_pays(env):
    """Counterpart to the Critical-fix test above: the originating rep is
    still active (never terminated) when a multi-party-signed GC contract
    completes and a payment is recorded -- the override MUST still fire
    and be attributed to the originating rep. Proves the fix doesn't
    overcorrect and break the legitimate multi-party case."""
    _enroll_homecare(env)
    project, contract, last_signed = _make_gc_project_and_multiparty_contract(env)
    invoice = _make_gc_invoice(env, project)

    updated = env["crm"].record_payment(invoice.id, 10000.0, "check", "TXN-1", env["admin"])
    assert updated.status == "partially_paid"

    entries = env["commission"].list_commissions(env["admin"], rep_user_id=env["hc_rep"].user_id)
    override_entries = [e for e in entries if e.source_type == "portfolio_override"]
    assert len(override_entries) == 1
    assert override_entries[0].rep_user_id == env["hc_rep"].user_id
    assert override_entries[0].commission_amount == 500.0


def test_multiparty_signed_gc_contract_terminated_after_completion_still_pays(env):
    """Same counter-intuitive termination rule as the single-signer test
    above, but for the multi-party path: the rep is terminated AFTER the
    multi-party contract's last signer completes -- override still
    fires."""
    _enroll_homecare(env)
    project, contract, last_signed = _make_gc_project_and_multiparty_contract(env)

    env["auth"].set_user_active(env["hc_rep"].user_id, 0, env["admin"])

    invoice = _make_gc_invoice(env, project)
    updated = env["crm"].record_payment(invoice.id, 10000.0, "check", "TXN-1", env["admin"])
    assert updated.status == "partially_paid"

    entries = env["commission"].list_commissions(env["admin"], rep_user_id=env["hc_rep"].user_id)
    override_entries = [e for e in entries if e.source_type == "portfolio_override"]
    assert len(override_entries) == 1
    assert override_entries[0].commission_amount == 500.0


def test_gate1b_contract_selection_uses_resolved_signed_at_not_raw_column(env):
    """Gate 1b's contract-selection ORDER BY must not systematically
    deprioritize a multi-party-signed contract just because
    customer_signed_at is NULL for it. Sets up a project with TWO signed
    GC contracts: a single-signer one with an OLDER customer_signed_at,
    and a multi-party one that is genuinely more recently completed. The
    multi-party contract must be selected as "the" contract for this
    project (most recently signed), which is only observable here via
    gate 5: the originating rep is terminated at a time BETWEEN the two
    contracts' real signed timestamps, so correctly selecting the more
    recent (multi-party) contract must produce NO override (its real
    signed_at is after termination), while the buggy NULL-sorts-last
    behavior would have picked the older single-signer contract instead
    and produced one."""
    _enroll_homecare(env)

    project = env["crm"].create_project(
        Project(customer_id=env["cust"].id, title="Two Contracts", property_address="1 Ordering Way", project_type="remodel"),
        env["admin"],
    )

    # Older, single-signer GC contract, signed 2024-01-01.
    old_contract = env["crm"].create_contract(
        Contract(
            contract_number="CTR-GC-OLD",
            customer_id=env["cust"].id,
            project_id=project.id,
            title="Old GC Agreement",
            template_name="general_remodeling",
            content="Terms...",
        ),
        env["gc_rep"],
    )
    signed_old = env["crm"].sign_contract(old_contract.id, _png_data_url(), env["actor_customer"])
    assert signed_old.status == "signed"
    _backdate(env["db"], "contracts", "id", old_contract.id, "customer_signed_at", "2024-01-01T00:00:00+00:00")

    # Newer, multi-party GC contract for the SAME project -- real
    # completion time (post-fix backdated) is 2024-06-01, later than the
    # single-signer contract above.
    new_contract = env["crm"].create_contract(
        Contract(
            contract_number="CTR-GC-NEW",
            customer_id=env["cust"].id,
            project_id=project.id,
            title="New GC Agreement (multi-party)",
            template_name="general_remodeling",
            content="Terms...",
        ),
        env["gc_rep"],
    )
    env["crm"].add_contract_signers(
        new_contract.id, [{"party_role": "customer"}, {"party_role": "admin"}], env["admin"],
    )
    env["crm"].sign_contract(new_contract.id, _png_data_url(), env["actor_customer"], party_role="customer")
    env["crm"].sign_contract(new_contract.id, _png_data_url(), env["admin"], party_role="admin")
    conn = env["db"].get_connection()
    with conn:
        conn.execute(
            "UPDATE contract_signers SET signed_at = ? WHERE contract_id = ?;",
            ("2024-06-01T00:00:00+00:00", new_contract.id),
        )

    # Terminate the originating rep between the two contracts' real
    # signed timestamps: after the old contract (2024-01-01), before the
    # new/multi-party one (2024-06-01).
    _backdate(env["db"], "users", "id", env["hc_rep"].user_id, "terminated_at", "2024-03-01T00:00:00+00:00")
    _backdate(env["db"], "users", "id", env["hc_rep"].user_id, "active", 0)

    invoice = _make_gc_invoice(env, project)
    updated = env["crm"].record_payment(invoice.id, 10000.0, "check", "TXN-1", env["admin"])
    assert updated.status == "partially_paid"

    entries = env["commission"].list_commissions(env["admin"])
    override_entries = [e for e in entries if e.source_type == "portfolio_override"]
    # The correctly-selected (more recent, multi-party) contract was
    # signed AFTER the rep's termination -- no override. If gate 1b had
    # instead picked the older single-signer contract (signed BEFORE
    # termination) due to the NULL-sorts-last bug, this would incorrectly
    # produce one.
    assert override_entries == []


# ---------------------------------------------------------------------------
# Invoice classification
# ---------------------------------------------------------------------------

def test_assessment_invoice_never_triggers_portfolio_override(env):
    _enroll_homecare(env)
    project, contract = _make_gc_project_and_contract(env)
    invoice = env["crm"].create_invoice(
        Invoice(customer_id=env["cust"].id, project_id=project.id, amount=299.0, invoice_type="assessment"),
        env["admin"],
    )
    env["crm"].record_payment(invoice.id, 299.0, "check", "TXN-1", env["admin"])
    entries = env["commission"].list_commissions(env["admin"], rep_user_id=env["hc_rep"].user_id)
    override_entries = [e for e in entries if e.source_type == "portfolio_override"]
    assert override_entries == []


def test_subscription_invoice_never_triggers_portfolio_override(env):
    _enroll_homecare(env)
    project, contract = _make_gc_project_and_contract(env)
    invoice = env["crm"].create_invoice(
        Invoice(customer_id=env["cust"].id, project_id=project.id, amount=119.0, invoice_type="subscription"),
        env["admin"],
    )
    env["crm"].record_payment(invoice.id, 119.0, "check", "TXN-1", env["admin"])
    entries = env["commission"].list_commissions(env["admin"], rep_user_id=env["hc_rep"].user_id)
    override_entries = [e for e in entries if e.source_type == "portfolio_override"]
    assert override_entries == []


# ---------------------------------------------------------------------------
# HomeCare cancellation (live-evaluated, no caching)
# ---------------------------------------------------------------------------

def test_cancelled_homecare_subscription_produces_no_override_on_later_gc_payments(env):
    sub = _enroll_homecare(env)
    conn = env["db"].get_connection()
    with conn:
        conn.execute(
            "UPDATE homecare_subscriptions SET status = 'cancelled', cancelled_at = ? WHERE id = ?;",
            (sub["enrolled_at"], sub["id"]),
        )

    project, contract = _make_gc_project_and_contract(env)
    invoice = _make_gc_invoice(env, project)

    updated = env["crm"].record_payment(invoice.id, 10000.0, "check", "TXN-1", env["admin"])
    assert updated.status == "partially_paid"

    entries = env["commission"].list_commissions(env["admin"])
    override_entries = [e for e in entries if e.source_type == "portfolio_override"]
    assert override_entries == []
    logs = env["audit"].query_logs(
        env["admin"], entity_type="invoice", entity_id=invoice.id, action="commission_recording_failed"
    )
    assert logs == []


# ---------------------------------------------------------------------------
# Config-read-inside-try regression (B8.7a's round-1 bug class)
# ---------------------------------------------------------------------------

def test_config_read_failure_does_not_fail_the_already_committed_payment(env, monkeypatch):
    _enroll_homecare(env)
    project, contract = _make_gc_project_and_contract(env)
    invoice = _make_gc_invoice(env, project)

    def _raise(*args, **kwargs):
        raise RuntimeError("simulated get_commission_plan_config failure")

    monkeypatch.setattr(CommissionService, "get_commission_plan_config", _raise)

    updated = env["crm"].record_payment(invoice.id, 10000.0, "check", "TXN-1", env["admin"])
    assert updated.status == "partially_paid"

    entries = env["commission"].list_commissions(env["admin"])
    override_entries = [e for e in entries if e.source_type == "portfolio_override"]
    assert override_entries == []

    logs = env["audit"].query_logs(
        env["admin"], entity_type="invoice", entity_id=invoice.id, action="commission_recording_failed"
    )
    # Both the Phase-1 assessment block (not applicable here, invoice_type
    # != 'assessment') and this Phase-3 block share the audit action name --
    # only the Phase-3 failure is expected for this invoice_type.
    assert len(logs) == 1
    assert "simulated get_commission_plan_config failure" in logs[0].change_summary


# ---------------------------------------------------------------------------
# Fail-closed contract-link resolution
# ---------------------------------------------------------------------------

def test_missing_project_id_link_skips_and_audit_logs_without_crashing(env):
    _enroll_homecare(env)
    # No project_id at all on this invoice -- the disclosed fail-closed gap.
    invoice = env["crm"].create_invoice(
        Invoice(customer_id=env["cust"].id, amount=50000.0, invoice_type="project"),
        env["admin"],
    )
    updated = env["crm"].record_payment(invoice.id, 10000.0, "check", "TXN-1", env["admin"])
    assert updated.status == "partially_paid"

    entries = env["commission"].list_commissions(env["admin"])
    override_entries = [e for e in entries if e.source_type == "portfolio_override"]
    assert override_entries == []

    logs = env["audit"].query_logs(
        env["admin"], entity_type="invoice", entity_id=invoice.id, action="commission_skipped_no_contract_link"
    )
    assert len(logs) == 1

    failure_logs = env["audit"].query_logs(
        env["admin"], entity_type="invoice", entity_id=invoice.id, action="commission_recording_failed"
    )
    assert failure_logs == []


def test_project_with_no_signed_gc_contract_skips_and_audit_logs_link_missing(env):
    """A project exists and is linked, but has no signed general_remodeling
    contract at all -- same fail-closed shape as the missing project_id
    case above."""
    _enroll_homecare(env)
    project = env["crm"].create_project(
        Project(customer_id=env["cust"].id, title="No Contract Yet", property_address="456 Oak Ave", project_type="remodel"),
        env["admin"],
    )
    invoice = _make_gc_invoice(env, project)

    updated = env["crm"].record_payment(invoice.id, 10000.0, "check", "TXN-1", env["admin"])
    assert updated.status == "partially_paid"

    entries = env["commission"].list_commissions(env["admin"])
    override_entries = [e for e in entries if e.source_type == "portfolio_override"]
    assert override_entries == []
    logs = env["audit"].query_logs(
        env["admin"], entity_type="invoice", entity_id=invoice.id, action="commission_skipped_no_contract_link"
    )
    assert len(logs) == 1


def test_customer_with_no_homecare_enrollment_produces_no_override_no_log(env):
    """A GC-only customer (never enrolled in HomeCare) -- normal ineligible
    outcome, not a link gap, not logged."""
    project, contract = _make_gc_project_and_contract(env)
    invoice = _make_gc_invoice(env, project)

    updated = env["crm"].record_payment(invoice.id, 10000.0, "check", "TXN-1", env["admin"])
    assert updated.status == "partially_paid"

    entries = env["commission"].list_commissions(env["admin"])
    override_entries = [e for e in entries if e.source_type == "portfolio_override"]
    assert override_entries == []
    logs = env["audit"].query_logs(
        env["admin"], entity_type="invoice", entity_id=invoice.id, action="commission_skipped_no_contract_link"
    )
    assert logs == []
    failure_logs = env["audit"].query_logs(
        env["admin"], entity_type="invoice", entity_id=invoice.id, action="commission_recording_failed"
    )
    assert failure_logs == []


# ---------------------------------------------------------------------------
# AuthService.set_user_active's new terminated_at transition-edge semantics
# ---------------------------------------------------------------------------

def test_suspend_sets_terminated_at_only_on_genuine_1_to_0_transition(env):
    updated = env["auth"].set_user_active(env["hc_rep"].user_id, 0, env["admin"])
    assert updated.active == 0
    assert updated.terminated_at is not None
    first_terminated_at = updated.terminated_at

    # Repeated suspend call against an already-suspended user must NOT
    # keep bumping terminated_at forward.
    updated_again = env["auth"].set_user_active(env["hc_rep"].user_id, 0, env["admin"])
    assert updated_again.active == 0
    assert updated_again.terminated_at == first_terminated_at


def test_reactivate_clears_terminated_at_on_genuine_0_to_1_transition(env):
    env["auth"].set_user_active(env["hc_rep"].user_id, 0, env["admin"])
    reactivated = env["auth"].set_user_active(env["hc_rep"].user_id, 1, env["admin"])
    assert reactivated.active == 1
    assert reactivated.terminated_at is None


def test_repeated_activate_call_on_already_active_user_is_a_no_op(env):
    """No transition ever occurred -- terminated_at stays None (it was
    never set), and must not be affected by an activate call on a user
    who was never suspended."""
    updated = env["auth"].set_user_active(env["hc_rep"].user_id, 1, env["admin"])
    assert updated.active == 1
    assert updated.terminated_at is None
