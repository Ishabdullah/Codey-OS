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
    ScheduleConfig,
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
        lambda crm, sched, auto, actor: crm.update_subcontractor(1, {"phone": "x"}, actor),
        lambda crm, sched, auto, actor: crm.find_subcontractor("acme", actor),
    ],
)
def test_subcontractor_methods_reject_zero_permission_actor(setup_ops_services, call):
    _, _, _, crm_service, scheduling_service, automation_service = setup_ops_services
    with pytest.raises(PermissionError):
        call(crm_service, scheduling_service, automation_service, ZeroPermissionActor())


# ==========================================
# update_subcontractor() -- B2 task 4, third module, 2026-08-27
# ==========================================


def _make_test_subcontractor(crm_service, admin_actor, **overrides):
    kwargs = dict(
        external_id="sub_9001",
        company_name="  Acme Roofing  ",
        email="Acme@Example.com",
        primary_trade="roofing",
        qualification_data={"years_licensed": 5, "notes": "solid"},
        secondary_trades=["gutters"],
    )
    kwargs.update(overrides)
    sub = Subcontractor(**kwargs)
    return crm_service.create_subcontractor(sub, admin_actor)


def test_update_subcontractor_rejects_unknown_key(setup_ops_services, admin_actor):
    _, _, _, crm_service, _, _ = setup_ops_services
    created = _make_test_subcontractor(crm_service, admin_actor)
    with pytest.raises(ValueError):
        crm_service.update_subcontractor(created.id, {"not_a_real_field": "x"}, admin_actor)


def test_update_subcontractor_rejects_none_valued_key(setup_ops_services, admin_actor):
    _, _, _, crm_service, _, _ = setup_ops_services
    created = _make_test_subcontractor(crm_service, admin_actor)
    with pytest.raises(ValueError):
        crm_service.update_subcontractor(created.id, {"phone": None}, admin_actor)


def test_update_subcontractor_qualification_data_merges_preserving_existing_keys(setup_ops_services, admin_actor):
    _, _, audit_service, crm_service, _, _ = setup_ops_services
    created = _make_test_subcontractor(crm_service, admin_actor)
    before = created.last_contact_at
    updated = crm_service.update_subcontractor(
        created.id, {"qualification_data": {"notes": "updated note"}}, admin_actor
    )
    assert updated.qualification_data == {"years_licensed": 5, "notes": "updated note"}

    # last_contact_at bumps on every real write (spec point 7 / NEW-236)
    assert updated.last_contact_at is not None
    assert updated.last_contact_at != before

    # Audit log gets exactly one "update" row naming the changed field
    logs = audit_service.query_logs(admin_actor, entity_type="subcontractor", entity_id=created.id, action="update")
    assert len(logs) == 1
    assert "qualification_data" in logs[0].change_summary


def test_update_subcontractor_secondary_trades_replaces_not_merges(setup_ops_services, admin_actor):
    _, _, _, crm_service, _, _ = setup_ops_services
    created = _make_test_subcontractor(crm_service, admin_actor)
    updated = crm_service.update_subcontractor(
        created.id, {"secondary_trades": ["siding"]}, admin_actor
    )
    assert updated.secondary_trades == ["siding"]


def test_update_subcontractor_normalizes_email_and_company_name(setup_ops_services, admin_actor):
    _, _, _, crm_service, _, _ = setup_ops_services
    created = _make_test_subcontractor(crm_service, admin_actor)
    updated = crm_service.update_subcontractor(
        created.id, {"email": " New@Example.COM ", "company_name": "  New Name  "}, admin_actor
    )
    assert updated.email == "new@example.com"
    assert updated.company_name == "New Name"


def test_update_subcontractor_empty_email_normalizes_to_none(setup_ops_services, admin_actor):
    """NEW-238: an empty-string email (after strip) becomes NULL, matching
    create_subcontractor's own normalization instead of storing ''."""
    _, _, _, crm_service, _, _ = setup_ops_services
    created = _make_test_subcontractor(crm_service, admin_actor)
    updated = crm_service.update_subcontractor(created.id, {"email": "   "}, admin_actor)
    assert updated.email is None


@pytest.mark.parametrize(
    "field, bad_value",
    [("qualification_data", "not-a-dict"), ("secondary_trades", "not-a-list")],
)
def test_update_subcontractor_rejects_malformed_types_cleanly(
    setup_ops_services, admin_actor, field, bad_value
):
    """NEW-239: a malformed qualification_data/secondary_trades value raises
    a clean ValueError, not a TypeError from deep inside the merge/dumps
    logic."""
    _, _, _, crm_service, _, _ = setup_ops_services
    created = _make_test_subcontractor(crm_service, admin_actor)
    with pytest.raises(ValueError):
        crm_service.update_subcontractor(created.id, {field: bad_value}, admin_actor)


def test_update_subcontractor_returns_none_for_nonexistent_id(setup_ops_services, admin_actor):
    _, _, _, crm_service, _, _ = setup_ops_services
    assert crm_service.update_subcontractor(999999, {"phone": "555-1234"}, admin_actor) is None


def test_update_subcontractor_empty_updates_is_noop(setup_ops_services, admin_actor):
    _, _, audit_service, crm_service, _, _ = setup_ops_services
    created = _make_test_subcontractor(crm_service, admin_actor)
    before = crm_service.get_subcontractor(created.id, admin_actor)
    result = crm_service.update_subcontractor(created.id, {}, admin_actor)
    assert result.to_dict() == before.to_dict()
    logs = audit_service.query_logs(admin_actor, entity_type="subcontractor", entity_id=created.id, action="update")
    assert logs == []


@pytest.mark.parametrize("excluded_key", ["qualification_status", "recruitment_step"])
def test_update_subcontractor_rejects_qualification_status_and_recruitment_step(
    setup_ops_services, admin_actor, excluded_key
):
    _, _, _, crm_service, _, _ = setup_ops_services
    created = _make_test_subcontractor(crm_service, admin_actor)
    with pytest.raises(ValueError):
        crm_service.update_subcontractor(created.id, {excluded_key: "QUALIFIED"}, admin_actor)


# ==========================================
# find_subcontractor() -- B2 task 4, third module continuation,
# 2026-08-27, CODEY_MASTER_PLAN.md Sec6.4
# ==========================================


def _seed_lookup_subcontractors(crm_service, admin_actor):
    """Two rows in a known id order, matching several predicates at
    once by design so the "first match wins, in ascending-id order"
    behavior is actually exercised, not just individually-true checks."""
    first = crm_service.create_subcontractor(
        Subcontractor(
            external_id="sub_1001",
            company_name="Acme Roofing Co",
            legal_name="Acme Roofing LLC",
            dba="Acme Roofers",
            contact_name="Bob Acme",
            email="bob@acmeroofing.com",
            phone="860-555-0101",
        ),
        admin_actor,
    )
    second = crm_service.create_subcontractor(
        Subcontractor(
            external_id="sub_1002",
            company_name="Zenith Roofing",
            legal_name="Zenith Roofing Inc",
            dba="ZenRoof",
            contact_name="Alice Zenith",
            email="alice@zenithroofing.com",
            phone="860-555-0202",
        ),
        admin_actor,
    )
    return first, second


def test_find_subcontractor_exact_external_id_match_case_insensitive(setup_ops_services, admin_actor):
    _, _, _, crm_service, _, _ = setup_ops_services
    first, _ = _seed_lookup_subcontractors(crm_service, admin_actor)
    found = crm_service.find_subcontractor("SUB_1001", admin_actor)
    assert found is not None
    assert found.id == first.id


def test_find_subcontractor_exact_email_match_case_insensitive(setup_ops_services, admin_actor):
    _, _, _, crm_service, _, _ = setup_ops_services
    _, second = _seed_lookup_subcontractors(crm_service, admin_actor)
    found = crm_service.find_subcontractor("ALICE@ZENITHROOFING.COM", admin_actor)
    assert found is not None
    assert found.id == second.id


@pytest.mark.parametrize(
    "field,query,expected_index",
    [
        ("company_name", "roofing co", 0),
        ("legal_name", "roofing llc", 0),
        ("dba", "roofers", 0),
        ("contact_name", "bob acme", 0),
        ("company_name", "zenith", 1),
        ("legal_name", "zenith roofing inc", 1),
        ("dba", "zenroof", 1),
        ("contact_name", "alice zenith", 1),
    ],
)
def test_find_subcontractor_substring_match_case_insensitive(
    setup_ops_services, admin_actor, field, query, expected_index
):
    _, _, _, crm_service, _, _ = setup_ops_services
    seeded = _seed_lookup_subcontractors(crm_service, admin_actor)
    found = crm_service.find_subcontractor(query, admin_actor)
    assert found is not None
    assert found.id == seeded[expected_index].id


def test_find_subcontractor_returns_lowest_id_when_multiple_rows_match(setup_ops_services, admin_actor):
    """Pins the spec's ORDER BY id ASC requirement -- distinct from
    list_subcontractors()'s ORDER BY id DESC a few lines below this
    method in crm_service.py, a live copy-paste hazard the spec calls
    out twice (returns the *first* record, not a best/highest-priority
    match; ascending id is the closest analog to the JS array's
    insertion order)."""
    _, _, _, crm_service, _, _ = setup_ops_services
    first, second = _seed_lookup_subcontractors(crm_service, admin_actor)
    # "roofing" is a company_name substring of BOTH seeded rows -- the
    # JS returns the first array element, so ascending id must win.
    found = crm_service.find_subcontractor("roofing", admin_actor)
    assert found.id == first.id
    assert found.id != second.id


def test_find_subcontractor_phone_digit_match_query_substring_of_stored(setup_ops_services, admin_actor):
    _, _, _, crm_service, _, _ = setup_ops_services
    first, _ = _seed_lookup_subcontractors(crm_service, admin_actor)
    # query's digits (7) are a substring of the stored 10-digit number
    found = crm_service.find_subcontractor("5550101", admin_actor)
    assert found is not None
    assert found.id == first.id


def test_find_subcontractor_phone_digit_match_stored_substring_of_query(setup_ops_services, admin_actor):
    _, _, _, crm_service, _, _ = setup_ops_services
    _, second = _seed_lookup_subcontractors(crm_service, admin_actor)
    # stored digits are a substring of a longer query (e.g. dialed with a
    # leading country code)
    found = crm_service.find_subcontractor("18605550202", admin_actor)
    assert found is not None
    assert found.id == second.id


def test_find_subcontractor_phone_match_not_attempted_under_seven_digits(setup_ops_services, admin_actor):
    _, _, _, crm_service, _, _ = setup_ops_services
    _seed_lookup_subcontractors(crm_service, admin_actor)
    # "555010" is 6 digits -- below the >=7 threshold -- and matches no
    # other field, so this must return None, not a phone match.
    assert crm_service.find_subcontractor("555010", admin_actor) is None


def test_find_subcontractor_no_match_returns_none(setup_ops_services, admin_actor):
    _, _, _, crm_service, _, _ = setup_ops_services
    _seed_lookup_subcontractors(crm_service, admin_actor)
    assert crm_service.find_subcontractor("nonexistent company xyz", admin_actor) is None


def test_find_subcontractor_empty_string_query_returns_none_not_first_row(setup_ops_services, admin_actor):
    """The bug this spec exists to prevent: an unguarded empty query
    would substring-match every non-null company_name and silently
    return the table's first row. Two seeded rows make "returned the
    first row" unambiguous if the guard is ever removed."""
    _, _, _, crm_service, _, _ = setup_ops_services
    _seed_lookup_subcontractors(crm_service, admin_actor)
    assert crm_service.find_subcontractor("", admin_actor) is None


def test_find_subcontractor_whitespace_only_query_returns_none(setup_ops_services, admin_actor):
    _, _, _, crm_service, _, _ = setup_ops_services
    _seed_lookup_subcontractors(crm_service, admin_actor)
    assert crm_service.find_subcontractor("   ", admin_actor) is None


def test_find_subcontractor_normalizes_leading_trailing_whitespace(setup_ops_services, admin_actor):
    _, _, _, crm_service, _, _ = setup_ops_services
    first, _ = _seed_lookup_subcontractors(crm_service, admin_actor)
    found = crm_service.find_subcontractor("  sub_1001  ", admin_actor)
    assert found is not None
    assert found.id == first.id


def test_find_subcontractor_permission_error_for_zero_permission_actor(setup_ops_services, admin_actor):
    _, _, _, crm_service, _, _ = setup_ops_services
    _seed_lookup_subcontractors(crm_service, admin_actor)
    with pytest.raises(PermissionError):
        crm_service.find_subcontractor("acme", ZeroPermissionActor())


def test_find_subcontractor_mirrors_js_nullphone_shadow_bug_new246(setup_ops_services, admin_actor):
    """Pins NEW-246: a NULL/blank-phone row matches any query with
    >=7 stripped digits, because this deliberately mirrors
    subcontractor-recruiter.js:213-216 exactly (see crm_service.py's
    find_subcontractor() comment) rather than "fixing" it and silently
    diverging from the JS this Core method exists to be drop-in
    parity for. If this test starts failing, the phone-match logic
    changed -- confirm the change is an intentional, jointly-landed fix
    to both this method and the JS file (NEW-246), not an accidental
    "improvement"."""
    _, _, _, crm_service, _, _ = setup_ops_services
    no_phone = crm_service.create_subcontractor(
        Subcontractor(external_id="sub_2001", company_name="No Phone Co", phone=None),
        admin_actor,
    )
    found = crm_service.find_subcontractor("5551234567", admin_actor)
    assert found is not None
    assert found.id == no_phone.id


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
        lambda auto, actor: auto.delete_rule(1, actor),
    ],
)
def test_automation_rule_methods_reject_zero_permission_actor(setup_ops_services, call):
    _, _, _, _, _, automation_service = setup_ops_services
    with pytest.raises(PermissionError):
        call(automation_service, ZeroPermissionActor())


def test_delete_rule_removes_row_and_audit_logs(setup_ops_services, admin_actor):
    """NEW-230: delete_rule() happy path -- row is gone from list_rules,
    an audit log entry is written (unlike record_rule_match), and a
    second delete of the same already-gone id returns False rather than
    erroring."""
    _, _, audit_service, _, _, automation_service = setup_ops_services

    rule = automation_service.create_rule(
        AutomationRule(channel="email", condition_type="from", condition_value="x", action="spam"),
        admin_actor,
    )

    deleted = automation_service.delete_rule(rule.id, admin_actor)
    assert deleted is True
    assert automation_service.list_rules(admin_actor, channel="email") == []

    logs = audit_service.query_logs(admin_actor, entity_type="automation_rule", action="delete")
    assert len(logs) == 1

    # Deleting an already-gone id is not an error -- returns False.
    assert automation_service.delete_rule(rule.id, admin_actor) is False


def test_delete_rule_rejects_zero_permission_actor_and_leaves_row_intact(setup_ops_services, admin_actor):
    """A denied delete_rule() call must not remove the row -- confirm the
    permission check happens before any DB mutation, not just that the
    exception is raised."""
    _, _, _, _, _, automation_service = setup_ops_services

    rule = automation_service.create_rule(
        AutomationRule(channel="sms", condition_type="from_number", condition_value="555", action="spam"),
        admin_actor,
    )

    with pytest.raises(PermissionError):
        automation_service.delete_rule(rule.id, ZeroPermissionActor())

    listed = automation_service.list_rules(admin_actor, channel="sms")
    assert len(listed) == 1
    assert listed[0].id == rule.id


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
# SCHEDULE CONFIG (singleton, NEW-216, 2026-08-27)
# ==========================================


def test_schedule_config_upsert_is_singleton(setup_ops_services, admin_actor):
    _, _, _, _, scheduling_service, _ = setup_ops_services

    assert scheduling_service.get_schedule_config(admin_actor) is None

    config = ScheduleConfig(
        working_hours={"mon": {"start": "09:00", "end": "18:00"}},
        default_duration_minutes=30,
        buffer_minutes=15,
        booking_window_days=365,
        duration_by_relationship={},
    )
    scheduling_service.upsert_schedule_config(config, admin_actor)
    fetched = scheduling_service.get_schedule_config(admin_actor)
    assert fetched.working_hours == {"mon": {"start": "09:00", "end": "18:00"}}
    assert fetched.default_duration_minutes == 30

    # Upsert again with a change -- must update the same row, not add a second.
    config2 = ScheduleConfig(default_duration_minutes=45, buffer_minutes=20)
    scheduling_service.upsert_schedule_config(config2, admin_actor)
    fetched2 = scheduling_service.get_schedule_config(admin_actor)
    assert fetched2.default_duration_minutes == 45
    assert fetched2.buffer_minutes == 20

    conn = scheduling_service.db.get_connection()
    count = conn.execute("SELECT COUNT(*) AS c FROM schedule_config;").fetchone()["c"]
    assert count == 1


@pytest.mark.parametrize(
    "call",
    [
        lambda sched, actor: sched.get_schedule_config(actor),
        lambda sched, actor: sched.upsert_schedule_config(ScheduleConfig(), actor),
    ],
)
def test_schedule_config_methods_reject_zero_permission_actor(setup_ops_services, call):
    _, _, _, _, scheduling_service, _ = setup_ops_services
    with pytest.raises(PermissionError):
        call(scheduling_service, ZeroPermissionActor())


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
