"""
Tests for restoricon_core/migrate_aigentik.py (Phase B2 task 2,
2026-08-27). Covers: dry-run vs apply, idempotent re-run (skip-if-exists
for subcontractors/appointments/automation_rules; update-always/upsert
for business_profile), missing-file vs present-empty-file handling, and
CHECK/NOT NULL constraint-domain validation being reported in dry-run
rather than raised as sqlite3.IntegrityError.

Every test uses an in-memory DB (never the real restoricon_core default
path) and a tmp_path source directory (never the real
~/Aigentik-CLI/data) -- this suite must never touch production data.
"""

import json

import pytest

from restoricon_core.database import DatabaseManager
from restoricon_core.migrate_aigentik import (
    build_migration_actor,
    map_profile,
    map_subcontractor,
    run_migration,
)
from restoricon_core.services.audit_service import AuditService
from restoricon_core.services.automation_service import AutomationService
from restoricon_core.services.crm_service import CRMService
from restoricon_core.services.scheduling_service import SchedulingService

VALID_SUBCONTRACTOR = {
    "subcontractor_id": "sub_0001",
    "contact_id": "contact_0197",
    "company_name": "John Smith",
    "legal_name": "John Smith",
    "dba": None,
    "contact_name": "John Smith",
    "title": None,
    "phone": None,
    "email": "john.smith@example.com",
    "website": None,
    "primary_trade": None,
    "secondary_trades": [],
    "service_area": None,
    "years_in_business": None,
    "crew_size": None,
    "residential_experience": None,
    "commercial_experience": None,
    "typical_project_size": None,
    "availability": None,
    "emergency_availability": None,
    "license_required": None,
    "license_type": None,
    "license_number": None,
    "license_expiration": None,
    "license_status": None,
    "general_liability": None,
    "workers_comp": None,
    "coi_received": False,
    "coi_expiration": None,
    "additional_insured_status": None,
    "insurance_status": None,
    "w9_received": False,
    "msa_sent": False,
    "msa_signed": False,
    "references": [],
    "portfolio_url": None,
    "qualification_status": "QUALIFICATION_IN_PROGRESS",
    "recruitment_step": "OPENING",
    "lead_source": "incoming_email",
    "last_contact": "2026-08-26T13:12:18.428Z",
    "next_followup": None,
    "contact_attempts": 1,
    "dnc_status": False,
    "notes": None,
    "qualification_data": {},
}

VALID_APPOINTMENT = {
    "id": "appt_0001",
    "uid": "appt_0001@aigentik.local",
    "ics_sequence": 0,
    "title": "Appointment with 8609822868",
    "start": None,
    "end": None,
    "contact_id": "contact_0202",
    "attendee_name": "8609822868",
    "attendee_email": None,
    "appointment_type": None,
    "status": "negotiating",
    "form_sent": True,
    "rsvp_status": "pending",
    "pending_reschedule": None,
    "offered_slots": [],
    "requested_datetime": None,
    "created_via": "sms",
    "notes": None,
    "created_at": "2026-08-27T01:13:18.188Z",
    "updated_at": "2026-08-27T01:13:21.131Z",
    "history": [{"event": "proposed", "at": "2026-08-27T01:13:18.188Z"}],
}

VALID_EMAIL_RULES = [
    {
        "id": "er_1771729675570",
        "description": "Emails from CarGirus should be marked as spam",
        "condition_type": "from",
        "condition_value": "CarGirus",
        "action": "spam",
        "added_by": "owner",
        "created_at": "2026-02-22T03:07:55.570Z",
        "match_count": 0,
    },
    {
        "id": "er_1771724421209",
        "description": "Mark emails that look like spam as spam",
        "condition_type": "message_contains",
        "condition_value": "spam",
        "action": "spam",
        "added_by": "owner",
        "created_at": "2026-02-22T01:40:21.210Z",
        "match_count": 0,
    },
]

VALID_PROFILE = {
    "configured": True,
    "aigentik_name": "Restoricon",
    "agent_name_set": True,
    "setup_date": "2026-02-21T00:00:00.000Z",
    "owner_name": "Ish",
    "business_name": "RESTORICON LLC",
    "business_description": "General Contracting.",
    "onboarding_sent": True,
}


# Verbatim from the real ~/Codey-Aigentik/data/profile.json after the
# B2-fin-1 write-through cache change: bare JSON ints for the boolean
# fields, plus the unmapped id + updated_at keys.
INT_PROFILE = {"id": 1, "configured": 1, "aigentik_name": "Restoricon", "agent_name_set": 1,
    "owner_name": "Ish", "business_name": "RESTORICON LLC",
    "business_description": "General Contracting.", "onboarding_sent": 1,
    "setup_date": "2026-02-21T00:00:00.000Z", "updated_at": "2026-09-07T05:06:36.438770+00:00"}


def test_map_profile_accepts_integer_booleans():
    profile, errors = map_profile(INT_PROFILE)
    assert errors == []
    assert profile is not None
    assert profile.configured == 1
    assert profile.agent_name_set == 1
    assert profile.onboarding_sent == 1
    assert profile.business_name == "RESTORICON LLC"


def test_map_profile_still_accepts_bool_shaped_profile():
    # Regression proof: the pre-B2-fin-1 bool-shaped profile still maps.
    profile, errors = map_profile(VALID_PROFILE)
    assert errors == []
    assert profile is not None
    assert profile.configured == 1
    assert profile.business_name == "RESTORICON LLC"


def test_map_profile_rejects_out_of_range_int():
    profile, errors = map_profile({**INT_PROFILE, "configured": 2})
    assert profile is None
    assert any("configured" in e for e in errors)


def test_map_profile_rejects_float_one():
    # Guards against a sloppy int(bool(v)) / bare `in (0, 1)` impl that
    # would pass the happy path while accepting 1.0.
    profile, errors = map_profile({**INT_PROFILE, "configured": 1.0})
    assert profile is None
    assert any("configured" in e for e in errors)


def test_map_subcontractor_accepts_integer_bool_field():
    sub, errors = map_subcontractor({**VALID_SUBCONTRACTOR, "coi_received": 1})
    assert not any("coi_received" in e for e in errors)
    assert sub is not None
    assert sub.coi_received == 1


def _write_valid_source_dir(tmp_path, sms_rules="[]"):
    (tmp_path / "subcontractors.json").write_text(json.dumps([VALID_SUBCONTRACTOR]))
    (tmp_path / "calendar.json").write_text(json.dumps([VALID_APPOINTMENT]))
    (tmp_path / "email-rules.json").write_text(json.dumps(VALID_EMAIL_RULES))
    (tmp_path / "sms-rules.json").write_text(sms_rules)
    (tmp_path / "profile.json").write_text(json.dumps(VALID_PROFILE))
    return tmp_path


@pytest.fixture
def db_manager():
    return DatabaseManager(":memory:")


@pytest.fixture
def services(db_manager):
    audit_service = AuditService(db_manager)
    return {
        "crm": CRMService(db_manager, audit_service),
        "scheduling": SchedulingService(db_manager, audit_service),
        "automation": AutomationService(db_manager, audit_service),
    }


def test_dry_run_writes_nothing(tmp_path, db_manager, services):
    source_dir = _write_valid_source_dir(tmp_path)
    actor = build_migration_actor()

    report = run_migration(str(source_dir), db_manager, apply=False)

    assert report["subcontractors"]["would_insert"] == 1
    assert report["subcontractors"]["inserted"] == 0
    assert report["appointments"]["would_insert"] == 1
    assert report["automation_rules_email"]["would_insert"] == 2
    assert report["automation_rules_sms"]["file_status"] == "present"
    assert report["automation_rules_sms"]["total_records"] == 0
    assert report["business_profile"]["would_upsert"] == 1
    assert report["business_profile"]["upserted"] == 0

    # Nothing actually written.
    assert services["crm"].list_subcontractors(actor) == []
    assert services["scheduling"].list_appointments(actor) == []
    assert services["automation"].list_rules(actor) == []
    assert services["automation"].get_business_profile(actor) is None


def test_apply_writes_records(tmp_path, db_manager, services):
    source_dir = _write_valid_source_dir(tmp_path)
    actor = build_migration_actor()

    report = run_migration(str(source_dir), db_manager, apply=True)

    assert report["subcontractors"]["inserted"] == 1
    assert report["appointments"]["inserted"] == 1
    assert report["automation_rules_email"]["inserted"] == 2
    assert report["automation_rules_sms"]["inserted"] == 0
    assert report["business_profile"]["upserted"] == 1

    subs = services["crm"].list_subcontractors(actor)
    assert len(subs) == 1
    assert subs[0].external_id == "sub_0001"
    assert subs[0].coi_received == 0  # bool False -> int 0

    appts = services["scheduling"].list_appointments(actor)
    assert len(appts) == 1
    assert appts[0].external_id == "appt_0001"
    assert appts[0].status == "negotiating"

    rules = services["automation"].list_rules(actor)
    assert len(rules) == 2
    assert {r.channel for r in rules} == {"email"}

    profile = services["automation"].get_business_profile(actor)
    assert profile is not None
    assert profile.business_name == "RESTORICON LLC"


def test_idempotent_rerun_no_duplicates(tmp_path, db_manager, services):
    source_dir = _write_valid_source_dir(tmp_path)

    first = run_migration(str(source_dir), db_manager, apply=True)
    assert first["subcontractors"]["inserted"] == 1
    assert first["appointments"]["inserted"] == 1
    assert first["automation_rules_email"]["inserted"] == 2

    second = run_migration(str(source_dir), db_manager, apply=True)

    # Second run must skip everything that already exists, not raise
    # sqlite3.IntegrityError and not create duplicate rows.
    assert second["subcontractors"]["inserted"] == 0
    assert second["subcontractors"]["skipped"] == 1
    assert second["appointments"]["inserted"] == 0
    assert second["appointments"]["skipped"] == 1
    assert second["automation_rules_email"]["inserted"] == 0
    assert second["automation_rules_email"]["skipped"] == 2

    actor = build_migration_actor()
    assert len(services["crm"].list_subcontractors(actor)) == 1
    assert len(services["scheduling"].list_appointments(actor)) == 1
    assert len(services["automation"].list_rules(actor)) == 2

    # business_profile is update-always (upsert), not skip-if-exists --
    # the second run still reports an upsert, and the singleton row is
    # still exactly one row, not a duplicate.
    assert second["business_profile"]["upserted"] == 1
    profile = services["automation"].get_business_profile(actor)
    assert profile.id == 1


def test_missing_file_is_absent_not_error(tmp_path, db_manager):
    source_dir = _write_valid_source_dir(tmp_path)
    (source_dir / "sms-rules.json").unlink()

    report = run_migration(str(source_dir), db_manager, apply=False)

    assert report["automation_rules_sms"]["file_status"] == "absent"
    assert report["automation_rules_sms"]["total_records"] == 0


def test_present_empty_file_is_distinct_from_absent(tmp_path, db_manager):
    source_dir = _write_valid_source_dir(tmp_path, sms_rules="[]")

    report = run_migration(str(source_dir), db_manager, apply=False)

    assert report["automation_rules_sms"]["file_status"] == "present"
    assert report["automation_rules_sms"]["total_records"] == 0


def test_missing_calendar_file_treated_as_absent(tmp_path, db_manager):
    source_dir = _write_valid_source_dir(tmp_path)
    (source_dir / "calendar.json").unlink()

    report = run_migration(str(source_dir), db_manager, apply=True)

    assert report["appointments"]["file_status"] == "absent"
    assert report["appointments"]["inserted"] == 0


def test_check_constraint_violation_reported_not_raised(tmp_path, db_manager, services):
    """An appointment with a status value outside the CHECK constraint's
    domain must be caught by dry-run validation, not thrown as
    sqlite3.IntegrityError during --apply."""
    bad_appointment = dict(VALID_APPOINTMENT)
    bad_appointment["id"] = "appt_bad"
    bad_appointment["status"] = "not_a_real_status"
    source_dir = _write_valid_source_dir(tmp_path)
    (source_dir / "calendar.json").write_text(json.dumps([VALID_APPOINTMENT, bad_appointment]))

    dry_report = run_migration(str(source_dir), db_manager, apply=False)
    assert dry_report["appointments"]["total_records"] == 2
    assert dry_report["appointments"]["would_insert"] == 1
    assert len(dry_report["appointments"]["invalid"]) == 1
    assert "status" in dry_report["appointments"]["invalid"][0]["errors"][0]

    # apply must not raise and must not insert the bad record
    apply_report = run_migration(str(source_dir), db_manager, apply=True)
    assert apply_report["appointments"]["inserted"] == 1
    assert len(apply_report["appointments"]["invalid"]) == 1

    actor = build_migration_actor()
    appts = services["scheduling"].list_appointments(actor)
    assert len(appts) == 1
    assert appts[0].external_id == "appt_0001"


def test_not_null_violation_reported_not_raised(tmp_path, db_manager, services):
    """A subcontractor record missing the NOT NULL company_name must be
    caught by validation, not thrown as sqlite3.IntegrityError."""
    bad_sub = dict(VALID_SUBCONTRACTOR)
    bad_sub["subcontractor_id"] = "sub_bad"
    bad_sub["company_name"] = ""
    source_dir = _write_valid_source_dir(tmp_path)
    (source_dir / "subcontractors.json").write_text(
        json.dumps([VALID_SUBCONTRACTOR, bad_sub])
    )

    dry_report = run_migration(str(source_dir), db_manager, apply=False)
    assert dry_report["subcontractors"]["would_insert"] == 1
    assert len(dry_report["subcontractors"]["invalid"]) == 1
    assert "company_name" in dry_report["subcontractors"]["invalid"][0]["errors"][0]

    apply_report = run_migration(str(source_dir), db_manager, apply=True)
    assert apply_report["subcontractors"]["inserted"] == 1

    actor = build_migration_actor()
    subs = services["crm"].list_subcontractors(actor)
    assert len(subs) == 1


def test_channel_check_violation_reported_for_rules(tmp_path, db_manager):
    """condition_type/condition_value/action are NOT NULL on
    automation_rules -- a rule missing one must be reported, not raised."""
    bad_rule = {
        "id": "er_bad",
        "description": "broken rule",
        "condition_type": "",
        "condition_value": "",
        "action": "",
        "added_by": "owner",
        "created_at": "2026-01-01T00:00:00.000Z",
        "match_count": 0,
    }
    source_dir = _write_valid_source_dir(tmp_path)
    (source_dir / "email-rules.json").write_text(json.dumps(VALID_EMAIL_RULES + [bad_rule]))

    dry_report = run_migration(str(source_dir), db_manager, apply=False)
    assert dry_report["automation_rules_email"]["would_insert"] == 2
    assert len(dry_report["automation_rules_email"]["invalid"]) == 1


def test_out_of_scope_files_reported_not_touched(tmp_path, db_manager):
    """contacts.json remains excluded (NEW-215, data-model mismatch);
    customers.json/schedule-config.json are no longer out of scope as of
    this task -- see test_customer_migration.py-style tests below."""
    source_dir = _write_valid_source_dir(tmp_path)
    (source_dir / "contacts.json").write_text(json.dumps([{"id": "c1"}]))

    report = run_migration(str(source_dir), db_manager, apply=True)

    assert set(report["skipped_out_of_scope"].keys()) == {"contacts.json"}
    for reason in report["skipped_out_of_scope"].values():
        assert reason  # non-empty explanation logged, not silently dropped


VALID_CUSTOMER = {
    "customer_id": "CUST-MT9QP39R-7620",
    "customer_name": "Alice Johnson",
    "preferred_name": None,
    "phone": "8602223344",
    "email": "alice@restoricon-test.com",
    "property_address": "100 Main St",
    "city": "Hartford",
    "state": "CT",
    "zip": None,
    "property_type": "Single-family",
    "owner_status": True,
    "occupancy_status": "Occupied",
    "customer_category": "NEW_CUSTOMER",
    "project_category": "remodeling",
    "project_type": "kitchen_remodeling",
    "project_description": None,
    "customer_goal": None,
    "rooms_affected": [],
    "approximate_size": None,
    "materials_requested": None,
    "design_needed": False,
    "project_urgency": "Standard",
    "desired_start_date": None,
    "desired_completion_date": None,
    "customer_budget": None,
    "insurance_related": False,
    "insurance_company": None,
    "claim_number": None,
    "adjuster": None,
    "incident_date": None,
    "photos_received": [],
    "documents_received": [],
    "lead_source": "inbound",
    "lead_status": "APPOINTMENT_SCHEDULED",
    "lead_score": "HOT",
    "appointment_date": "2026-09-05",
    "appointment_time": "2:00 PM",
    "appointment_status": None,
    "last_contact": "2026-08-26T06:55:34.094Z",
    "next_followup": None,
    "contact_preference": "sms",
    "best_contact_time": None,
    "customer_notes": [],
    "dnc_status": False,
    "escalation_status": None,
    "created_at": "2026-08-26T06:55:34.094Z",
    "updated_at": "2026-08-26T06:55:34.198Z",
}

VALID_SCHEDULE_CONFIG = {
    "working_hours": {
        "sun": {"start": "00:00", "end": "23:59"},
        "mon": {"start": "09:00", "end": "18:00"},
    },
    "default_duration_minutes": 30,
    "buffer_minutes": 15,
    "booking_window_days": 365,
    "duration_by_relationship": {},
}


def _write_customers_and_schedule_config(source_dir, customers=None, schedule_config=None):
    (source_dir / "customers.json").write_text(
        json.dumps(customers if customers is not None else [VALID_CUSTOMER])
    )
    (source_dir / "schedule-config.json").write_text(
        json.dumps(schedule_config if schedule_config is not None else VALID_SCHEDULE_CONFIG)
    )
    return source_dir


def test_customer_dry_run_writes_nothing(tmp_path, db_manager, services):
    source_dir = _write_valid_source_dir(tmp_path)
    _write_customers_and_schedule_config(source_dir)
    actor = build_migration_actor()

    report = run_migration(str(source_dir), db_manager, apply=False)

    assert report["customers"]["would_insert"] == 1
    assert report["customers"]["inserted"] == 0
    assert report["schedule_config"]["would_upsert"] == 1
    assert report["schedule_config"]["upserted"] == 0
    assert services["crm"].list_customers(actor) == []
    assert services["scheduling"].get_schedule_config(actor) is None


def test_customer_apply_writes_and_maps_fields(tmp_path, db_manager, services):
    source_dir = _write_valid_source_dir(tmp_path)
    _write_customers_and_schedule_config(source_dir)
    actor = build_migration_actor()

    report = run_migration(str(source_dir), db_manager, apply=True)

    assert report["customers"]["inserted"] == 1
    assert report["schedule_config"]["upserted"] == 1

    customers = services["crm"].list_customers(actor)
    assert len(customers) == 1
    cust = customers[0]
    assert cust.external_id == "CUST-MT9QP39R-7620"
    assert cust.first_name == "Alice"
    assert cust.last_name == "Johnson"
    assert cust.phone == "8602223344"
    assert cust.email == "alice@restoricon-test.com"
    assert cust.service_address == "100 Main St"
    assert cust.customer_source == "inbound"
    assert cust.last_contact_at == "2026-08-26T06:55:34.094Z"
    # CHECK-constrained columns left at schema defaults -- not guessed
    # from lead_status/customer_category (see map_customer's docstring).
    assert cust.status == "lead"
    assert cust.customer_type == "residential"
    # Unmapped fields preserved verbatim, not dropped.
    assert cust.custom_fields["aigentik_raw"]["lead_status"] == "APPOINTMENT_SCHEDULED"
    assert cust.custom_fields["aigentik_raw"]["insurance_related"] is False
    assert cust.custom_fields["aigentik_raw"]["city"] == "Hartford"

    config = services["scheduling"].get_schedule_config(actor)
    assert config is not None
    assert config.default_duration_minutes == 30
    assert config.working_hours["mon"]["start"] == "09:00"


def test_customer_idempotent_rerun_no_duplicates(tmp_path, db_manager, services):
    source_dir = _write_valid_source_dir(tmp_path)
    _write_customers_and_schedule_config(source_dir)

    first = run_migration(str(source_dir), db_manager, apply=True)
    assert first["customers"]["inserted"] == 1
    assert first["schedule_config"]["upserted"] == 1

    second = run_migration(str(source_dir), db_manager, apply=True)
    assert second["customers"]["inserted"] == 0
    assert second["customers"]["skipped"] == 1
    # schedule_config is update-always -- still reports an upsert, still
    # exactly one singleton row.
    assert second["schedule_config"]["upserted"] == 1

    actor = build_migration_actor()
    assert len(services["crm"].list_customers(actor)) == 1
    config = services["scheduling"].get_schedule_config(actor)
    assert config.id == 1


def test_customer_missing_customer_id_reported_not_raised(tmp_path, db_manager):
    bad_customer = dict(VALID_CUSTOMER)
    bad_customer["customer_id"] = None
    source_dir = _write_valid_source_dir(tmp_path)
    _write_customers_and_schedule_config(source_dir, customers=[VALID_CUSTOMER, bad_customer])

    dry_report = run_migration(str(source_dir), db_manager, apply=False)
    assert dry_report["customers"]["total_records"] == 2
    assert dry_report["customers"]["would_insert"] == 1
    assert len(dry_report["customers"]["invalid"]) == 1
    assert "customer_id" in dry_report["customers"]["invalid"][0]["errors"][0]

    apply_report = run_migration(str(source_dir), db_manager, apply=True)
    assert apply_report["customers"]["inserted"] == 1
    assert len(apply_report["customers"]["invalid"]) == 1


def test_customer_single_word_name_gets_empty_last_name(tmp_path, db_manager, services):
    single_word = dict(VALID_CUSTOMER)
    single_word["customer_id"] = "CUST-SINGLE-0001"
    single_word["customer_name"] = "Prospective"
    source_dir = _write_valid_source_dir(tmp_path)
    _write_customers_and_schedule_config(source_dir, customers=[single_word])

    report = run_migration(str(source_dir), db_manager, apply=True)
    assert report["customers"]["inserted"] == 1

    actor = build_migration_actor()
    cust = services["crm"].list_customers(actor)[0]
    assert cust.first_name == "Prospective"
    assert cust.last_name == ""


def test_schedule_config_missing_file_is_absent_not_error(tmp_path, db_manager):
    source_dir = _write_valid_source_dir(tmp_path)
    (source_dir / "customers.json").write_text(json.dumps([VALID_CUSTOMER]))
    # schedule-config.json intentionally not written.

    report = run_migration(str(source_dir), db_manager, apply=False)

    assert report["schedule_config"]["file_status"] == "absent"
    assert report["schedule_config"]["would_upsert"] == 0
