"""
Unit tests for the B2/NEW-209 schema expansion: subcontractors
(crm_service.py), appointments (scheduling_service.py), and automation
rules / business profile / do-not-contact (automation_service.py).

Includes a parametrized zero-permission-actor reproduction (per NEW-189's
own finding shape) for every new public read/write method, run
proactively this round rather than found later by a review pass.
"""

import pytest

from restoricon_core.auth import (
    AuthContext,
    AuthService,
    ROLE_ADMIN,
    ROLE_AI_AGENT,
    ROLE_PROJECT_MANAGER,
    ROLE_SALES,
)
from restoricon_core.database import DatabaseManager
from restoricon_core.models import (
    Appointment,
    AutomationRule,
    BusinessProfile,
    Subcontractor,
)
from restoricon_core.services.audit_service import AuditService
from restoricon_core.services.automation_service import (
    AutomationService,
    classify_identifier,
    normalize_email,
    normalize_phone,
)
from restoricon_core.services.crm_service import CRMService
from restoricon_core.services.scheduling_service import SchedulingService


@pytest.fixture
def setup_ops_services():
    db = DatabaseManager(":memory:")
    auth_service = AuthService(db)
    audit_service = AuditService(db)
    crm_service = CRMService(db, audit_service)
    scheduling_service = SchedulingService(db, audit_service)
    automation_service = AutomationService(db, audit_service)
    return db, auth_service, audit_service, crm_service, scheduling_service, automation_service


@pytest.fixture
def admin_actor(setup_ops_services):
    _, auth_service, *_ = setup_ops_services
    user = auth_service.create_user(
        username="admin", plain_password="Password123", full_name="Admin", email="admin@test.com", role=ROLE_ADMIN
    )
    return AuthContext(user_id=user.id, username="admin", role=ROLE_ADMIN, actor_type="human")


@pytest.fixture
def agent_actor(setup_ops_services):
    _, auth_service, *_ = setup_ops_services
    user = auth_service.create_user(
        username="aigentik", plain_password="Password123", full_name="Aigentik", email="agent@test.com", role=ROLE_AI_AGENT
    )
    return AuthContext(user_id=user.id, username="aigentik", role=ROLE_AI_AGENT, actor_type="agent")


@pytest.fixture
def sales_actor(setup_ops_services):
    _, auth_service, *_ = setup_ops_services
    user = auth_service.create_user(
        username="sales_rep", plain_password="Password123", full_name="Sales Rep", email="sales@test.com", role=ROLE_SALES
    )
    return AuthContext(user_id=user.id, username="sales_rep", role=ROLE_SALES, actor_type="human")


@pytest.fixture
def project_manager_actor(setup_ops_services):
    _, auth_service, *_ = setup_ops_services
    user = auth_service.create_user(
        username="pm", plain_password="Password123", full_name="PM", email="pm@test.com", role=ROLE_PROJECT_MANAGER
    )
    return AuthContext(user_id=user.id, username="pm", role=ROLE_PROJECT_MANAGER, actor_type="human")


class ZeroPermissionActor:
    """A constructed actor whose has_permission() returns False
    unconditionally, regardless of what permission is asked for -- the
    exact reproduction shape NEW-189's review used to prove
    get_project()/list_projects() had no gate at all. Every new method
    below must reject this actor before touching the database."""

    user_id = 999999
    username = "nobody"
    role = "nobody"
    actor_type = "agent"
    customer_id = None
    token = None

    def has_permission(self, permission: str) -> bool:
        return False


# ==========================================
# SUBCONTRACTORS (crm_service.py)
# ==========================================


def test_subcontractor_lifecycle(setup_ops_services, admin_actor):
    _, _, _, crm_service, _, _ = setup_ops_services

    sub = Subcontractor(
        external_id="sub_0001",
        contact_external_id="contact_0197",
        company_name="John Smith",
        email="john.smith@example.com",
        qualification_status="QUALIFICATION_IN_PROGRESS",
    )
    created = crm_service.create_subcontractor(sub, admin_actor)
    assert created.id is not None
    assert created.email == "john.smith@example.com"

    fetched = crm_service.get_subcontractor(created.id, admin_actor)
    assert fetched is not None
    assert fetched.company_name == "John Smith"

    listed = crm_service.list_subcontractors(admin_actor, qualification_status="QUALIFICATION_IN_PROGRESS")
    assert len(listed) == 1

    updated = crm_service.update_subcontractor_qualification(
        created.id, "QUALIFIED", admin_actor, recruitment_step="CLOSING"
    )
    assert updated.qualification_status == "QUALIFIED"
    assert updated.recruitment_step == "CLOSING"

    assert crm_service.update_subcontractor_qualification(999999, "QUALIFIED", admin_actor) is None


@pytest.mark.parametrize(
    "call",
    [
        lambda crm, sched, auto, actor: crm.create_subcontractor(Subcontractor(company_name="X"), actor),
        lambda crm, sched, auto, actor: crm.get_subcontractor(1, actor),
        lambda crm, sched, auto, actor: crm.list_subcontractors(actor),
        lambda crm, sched, auto, actor: crm.update_subcontractor_qualification(1, "QUALIFIED", actor),
    ],
)
def test_subcontractor_methods_reject_zero_permission_actor(setup_ops_services, call):
    _, _, _, crm_service, scheduling_service, automation_service = setup_ops_services
    with pytest.raises(PermissionError):
        call(crm_service, scheduling_service, automation_service, ZeroPermissionActor())


# ==========================================
# APPOINTMENTS (scheduling_service.py)
# ==========================================


def test_appointment_lifecycle(setup_ops_services, admin_actor):
    _, _, _, _, scheduling_service, _ = setup_ops_services

    appt = Appointment(
        external_id="1",
        title="Estimate walkthrough",
        start_time="2026-09-01T15:00:00Z",
        end_time="2026-09-01T15:30:00Z",
        attendee_email="Customer@Example.com",
        status="negotiating",
    )
    created = scheduling_service.create_appointment(appt, admin_actor)
    assert created.id is not None
    assert created.history and created.history[0]["event"] == "created"

    fetched = scheduling_service.get_appointment(created.id, admin_actor)
    assert fetched.status == "negotiating"
    assert fetched.attendee_email == "customer@example.com"  # normalized on read from DB

    confirmed = scheduling_service.update_appointment_status(created.id, "confirmed", admin_actor)
    assert confirmed.status == "confirmed"
    assert len(confirmed.history) == 2

    listed = scheduling_service.list_appointments(admin_actor, status="confirmed")
    assert len(listed) == 1

    with pytest.raises(ValueError):
        scheduling_service.create_appointment(Appointment(title="Bad", status="not_a_status"), admin_actor)

    assert scheduling_service.update_appointment_status(999999, "confirmed", admin_actor) is None


@pytest.mark.parametrize(
    "call",
    [
        lambda sched, actor: sched.create_appointment(Appointment(title="X"), actor),
        lambda sched, actor: sched.get_appointment(1, actor),
        lambda sched, actor: sched.list_appointments(actor),
        lambda sched, actor: sched.update_appointment_status(1, "confirmed", actor),
    ],
)
def test_appointment_methods_reject_zero_permission_actor(setup_ops_services, call):
    _, _, _, _, scheduling_service, _ = setup_ops_services
    with pytest.raises(PermissionError):
        call(scheduling_service, ZeroPermissionActor())


# ==========================================
# AUTOMATION RULES
# ==========================================


def test_automation_rule_lifecycle(setup_ops_services, admin_actor):
    _, _, _, _, _, automation_service = setup_ops_services

    rule = AutomationRule(
        external_id="er_1771729675570",
        channel="email",
        description="Mark CarGurus emails as spam",
        condition_type="from",
        condition_value="CarGurus",
        action="spam",
        added_by="owner",
    )
    created = automation_service.create_rule(rule, admin_actor)
    assert created.id is not None

    matched = automation_service.record_rule_match(created.id, admin_actor)
    assert matched.match_count == 1

    listed = automation_service.list_rules(admin_actor, channel="email")
    assert len(listed) == 1
    assert listed[0].match_count == 1

    with pytest.raises(ValueError):
        automation_service.create_rule(AutomationRule(channel="fax"), admin_actor)

    assert automation_service.record_rule_match(999999, admin_actor) is None


def test_record_rule_match_does_not_write_audit_log(setup_ops_services, admin_actor):
    """match_count increments are deliberately not audit-logged (see
    automation_service.py's record_rule_match docstring) -- confirm no
    audit_log row is created for the match itself, distinct from the
    'create' row from create_rule."""
    _, _, audit_service, _, _, automation_service = setup_ops_services

    rule = automation_service.create_rule(
        AutomationRule(channel="sms", condition_type="from", condition_value="x", action="spam"),
        admin_actor,
    )
    logs_after_create = audit_service.query_logs(admin_actor, entity_type="automation_rule")
    assert len(logs_after_create) == 1

    automation_service.record_rule_match(rule.id, admin_actor)
    automation_service.record_rule_match(rule.id, admin_actor)
    logs_after_matches = audit_service.query_logs(admin_actor, entity_type="automation_rule")
    assert len(logs_after_matches) == 1  # unchanged


@pytest.mark.parametrize(
    "call",
    [
        lambda auto, actor: auto.create_rule(AutomationRule(channel="email"), actor),
        lambda auto, actor: auto.list_rules(actor),
        lambda auto, actor: auto.record_rule_match(1, actor),
    ],
)
def test_automation_rule_methods_reject_zero_permission_actor(setup_ops_services, call):
    _, _, _, _, _, automation_service = setup_ops_services
    with pytest.raises(PermissionError):
        call(automation_service, ZeroPermissionActor())


# ==========================================
# BUSINESS PROFILE (singleton)
# ==========================================


def test_business_profile_upsert_is_singleton(setup_ops_services, admin_actor):
    _, _, _, _, _, automation_service = setup_ops_services

    assert automation_service.get_business_profile(admin_actor) is None

    profile = BusinessProfile(
        configured=1,
        aigentik_name="Restoricon",
        owner_name="Ish",
        business_name="RESTORICON LLC",
    )
    automation_service.upsert_business_profile(profile, admin_actor)
    fetched = automation_service.get_business_profile(admin_actor)
    assert fetched.business_name == "RESTORICON LLC"

    # Upsert again with a change — must update the same row, not add a second.
    profile2 = BusinessProfile(configured=1, business_name="RESTORICON LLC (updated)")
    automation_service.upsert_business_profile(profile2, admin_actor)
    fetched2 = automation_service.get_business_profile(admin_actor)
    assert fetched2.business_name == "RESTORICON LLC (updated)"

    conn = automation_service.db.get_connection()
    count = conn.execute("SELECT COUNT(*) AS c FROM business_profile;").fetchone()["c"]
    assert count == 1


@pytest.mark.parametrize(
    "call",
    [
        lambda auto, actor: auto.get_business_profile(actor),
        lambda auto, actor: auto.upsert_business_profile(BusinessProfile(), actor),
    ],
)
def test_business_profile_methods_reject_zero_permission_actor(setup_ops_services, call):
    _, _, _, _, _, automation_service = setup_ops_services
    with pytest.raises(PermissionError):
        call(automation_service, ZeroPermissionActor())


# ==========================================
# DO-NOT-CONTACT
# ==========================================


def test_normalization_matches_do_not_contact_js():
    """Pins the Python normalization to the exact behavior of
    do-not-contact.js's normalizeEmail()/normalizePhone() -- see
    automation_service.py's module docstring for why a mismatch here is
    safety-relevant, not cosmetic."""
    assert normalize_email("  Foo@Example.COM ") == "foo@example.com"
    assert normalize_phone("+1 (555) 123-4567") == "5551234567"
    assert classify_identifier("foo@example.com") == {"type": "email", "value": "foo@example.com"}
    assert classify_identifier("(555) 123-4567") == {"type": "phone", "value": "5551234567"}
    assert classify_identifier("123") is None


def test_do_not_contact_lifecycle(setup_ops_services, admin_actor):
    _, _, _, _, _, automation_service = setup_ops_services

    assert automation_service.is_blocked("foo@example.com", admin_actor) is False

    entry = automation_service.add_to_do_not_contact(
        "Foo@Example.com", admin_actor, name="Foo Bar", reason="requested removal", source="email"
    )
    assert entry.type == "email"
    assert entry.value == "foo@example.com"

    assert automation_service.is_blocked("foo@example.com", admin_actor) is True
    assert automation_service.is_blocked("FOO@EXAMPLE.COM", admin_actor) is True  # normalization applies both ways

    # Idempotent re-add refreshes fields without creating a duplicate row.
    automation_service.add_to_do_not_contact("foo@example.com", admin_actor, reason="asked again")
    listed = automation_service.list_do_not_contact(admin_actor)
    assert len(listed) == 1
    assert listed[0].reason == "asked again"

    removed = automation_service.remove_from_do_not_contact("foo@example.com", admin_actor)
    assert removed is True
    assert automation_service.is_blocked("foo@example.com", admin_actor) is False
    assert automation_service.remove_from_do_not_contact("foo@example.com", admin_actor) is False


def test_sales_and_project_manager_can_check_is_blocked(setup_ops_services, sales_actor, project_manager_actor):
    # NEW-214: sales/project_manager hold PERM_LOG_COMMUNICATION (i.e. are
    # the roles most plausibly about to actually contact someone) and must
    # be able to check the DNC list before doing so -- a PermissionError
    # here would mean the roles most likely to need this compliance check
    # are the ones structurally unable to run it.
    _, _, _, _, _, automation_service = setup_ops_services
    assert automation_service.is_blocked("nobody@example.com", sales_actor) is False
    assert automation_service.is_blocked("nobody@example.com", project_manager_actor) is False


@pytest.mark.parametrize(
    "call",
    [
        lambda auto, actor: auto.add_to_do_not_contact("foo@example.com", actor),
        lambda auto, actor: auto.remove_from_do_not_contact("foo@example.com", actor),
        lambda auto, actor: auto.is_blocked("foo@example.com", actor),
        lambda auto, actor: auto.list_do_not_contact(actor),
    ],
)
def test_do_not_contact_methods_reject_zero_permission_actor(setup_ops_services, call):
    _, _, _, _, _, automation_service = setup_ops_services
    with pytest.raises(PermissionError):
        call(automation_service, ZeroPermissionActor())


# ==========================================
# ai_agent role is the intended B2 write-through actor for all five —
# confirm it actually holds every relevant permission end-to-end.
# ==========================================


def test_ai_agent_role_can_use_all_five_new_services(setup_ops_services, agent_actor):
    _, _, _, crm_service, scheduling_service, automation_service = setup_ops_services

    sub = crm_service.create_subcontractor(Subcontractor(company_name="Agent Sub"), agent_actor)
    assert sub.id is not None

    appt = scheduling_service.create_appointment(Appointment(title="Agent Appt"), agent_actor)
    assert appt.id is not None

    rule = automation_service.create_rule(
        AutomationRule(channel="email", condition_type="from", condition_value="x", action="spam"),
        agent_actor,
    )
    assert rule.id is not None

    automation_service.upsert_business_profile(BusinessProfile(business_name="Test Co"), agent_actor)
    assert automation_service.get_business_profile(agent_actor) is not None

    entry = automation_service.add_to_do_not_contact("agent-blocked@example.com", agent_actor)
    assert entry is not None
