"""
One-off / re-runnable migration script: Aigentik-CLI's live JSON data
files -> restoricon_core's SQLite database.

Phase B2 task 2 (CODEY_MASTER_PLAN.md Sec6.4, "Task 2 (data migration)
scoped 2026-08-27"). First pass covered the 4 files that mapped cleanly
onto tables landed in c30d755; this round (2026-08-27, following
customers/leads/schedule_config gaining `external_id`/a destination
table in commit 8693721) adds two more:

    subcontractors.json   -> subcontractors    (crm_service)
    calendar.json         -> appointments      (scheduling_service)
    email-rules.json      -> automation_rules, channel='email'
    sms-rules.json        -> automation_rules, channel='sms'
    profile.json          -> business_profile  (automation_service)
    customers.json         -> customers        (crm_service)
    schedule-config.json  -> schedule_config   (scheduling_service)

customers.json field mapping (NEW-212's ~46-field shape vs. Customer's
~19 columns): only 8 source fields have a direct, non-lossy destination
column (customer_id -> external_id; customer_name split on first space
-> first_name/last_name; phone; email; property_address ->
service_address; lead_source -> customer_source; last_contact ->
last_contact_at; next_followup -> next_followup_at). Every other source
field (insurance/claim fields, project-scheduling fields, lead_status/
lead_score/customer_category, customer_notes, dnc_status, etc.) is
preserved verbatim under custom_fields["aigentik_raw"] rather than
silently dropped or guessed into a CHECK-constrained column it doesn't
actually match. In particular, Customer.status
(lead/prospect/active/past/lost) and Customer.customer_type
(residential/commercial) are left at their schema defaults for every
migrated record -- the source's lead_status/customer_category/
project_type values don't correspond to those CHECK domains, and
inventing a mapping would misrepresent a record's status rather than
just failing to enrich it. See map_customer()'s docstring for the exact
field lists.

Explicitly OUT OF SCOPE this round -- this script does not read or write
anything related to this file, and reports why it is skipped:

    contacts.json - NEW-215: an Android-contacts phonebook sync (201 real
                    phone-contact records), not CRM data -- a categorical
                    data-model mismatch, independent of whether the data
                    is "real" or "test" (confirmed via direct read,
                    2026-08-27). This is a scope exclusion, not a
                    data-safety one: unlike customers.json/
                    schedule-config.json, there was never a plan to give
                    this file a destination table this round.

AuthContext bootstrap
----------------------
This script hand-constructs an AuthContext(role="ai_agent", user_id=None,
...) rather than provisioning a real `users` row via
AuthService.create_user(). Why this is safe here:

  - This is an offline maintenance script, run directly by a human
    operator on the device, never invoked over the network and never
    reachable from the API surface (restoricon_core/api/routes.py has no
    route that runs it).
  - Requirement: dry-run (no flags) must write *nothing*. If the actor
    were provisioned via create_user(), dry-run and --apply would need
    different actor-setup paths (one that writes a `users` row, one that
    doesn't) for no benefit. Hand-construction gives one identical actor
    object in both modes.
  - A persisted `ai_agent` user row would mean a synthetic password
    nobody ever rotates, sitting in production `users` forever, for a
    credential that is never actually authenticated against (this
    script never goes through AuthService.authenticate_user/
    create_token). Hand-constructing the AuthContext directly avoids
    fabricating that unused credential.
  - user_id=None is deliberate, not an oversight: AuditService.log() is
    the only place any of the three services read `actor.user_id` (as
    `audit_log.actor_id`), and `audit_log.actor_id` is a nullable FK
    (`ON DELETE SET NULL`) -- SQLite does not enforce FK constraints
    against NULL child key values, so this inserts cleanly. Every audit
    row this script produces has `actor_role='ai_agent'`,
    `actor_type='agent'`, `actor_id=NULL` -- identifiable as a
    migration-run actor, not attributable to a specific human/agent
    account (there isn't one).

Idempotency strategy (two different strategies, on purpose)
-------------------------------------------------------------
- subcontractors / appointments / automation_rules / customers:
  SKIP-IF-EXISTS. Each of these tables has UNIQUE(external_id) and its
  service now has a get_*_by_external_id lookup (NEW-217/NEW-212 for
  customers, added in this and the prior task). This script looks up by
  Aigentik's own string ID before every insert and skips (reporting the
  skip) if a row already exists. Chosen over update-if-changed because
  only lookup methods were added this round -- no generic field-level
  update method exists for these tables, and building one is a separate,
  unscoped change.
- business_profile / schedule_config: UPDATE-ALWAYS (upsert).
  automation_service.upsert_business_profile() and
  scheduling_service.upsert_schedule_config() both do an
  INSERT ... ON CONFLICT(id) DO UPDATE against a fixed id=1 singleton
  row -- there is nothing to "skip"; re-running this script just
  refreshes the row to whatever the source file currently says, which is
  correct for a singleton config record synced from a live source file.

Known limitation (NEW-218, logged, not fixed here)
----------------------------------------------------
create_subcontractor/create_appointment/create_rule/create_customer all
unconditionally overwrite created_at (and, for the first three,
updated_at) with the current timestamp before INSERT, discarding any
value already set on the dataclass passed in. This means historical
created_at values from Aigentik's JSON (e.g. an email rule genuinely
created months ago, or a customer's real created_at) are replaced with
this script's own run time. Every other timestamp field (last_contact_at,
next_followup_at, setup_date, etc.) lives in its own column and is
preserved correctly -- only the universal created_at/updated_at columns
are affected. customers.json's own `updated_at` field has no
corresponding column on the Customer dataclass at all (Customer only has
created_at) and is preserved, un-acted-on, inside custom_fields
["aigentik_raw"]. Not fixed here: doing so requires changing the service
layer's create_* signatures, which is out of this migration script's
scope. See NEW-218 in NEW_ISSUES.md.

Defensive read behavior (live-writer safety)
-----------------------------------------------
Aigentik-CLI (`node index.js`) uses non-atomic writeFileSync() for all of
these files. A read landing mid-write can yield a truncated-but-
syntactically-valid JSON array/object (e.g. a shorter array that still
parses). `_read_json_stable()` guards against this with a
read-wait-reread-compare loop (not a bare record-count floor, since
sms-rules.json legitimately has 0 records today and a floor would
misclassify that as a torn read) plus a small number of retries with
backoff for outright read errors (file appears, disappears, or is
momentarily unreadable mid-rename).

Usage
-----
    python -m restoricon_core.migrate_aigentik                  # dry run
    python -m restoricon_core.migrate_aigentik --apply           # writes
    python -m restoricon_core.migrate_aigentik --source-dir DIR --db-path PATH
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from .auth import AuthContext, ROLE_AI_AGENT
from .database import DatabaseManager
from .models import (
    Appointment,
    AutomationRule,
    BusinessProfile,
    Customer,
    ScheduleConfig,
    Subcontractor,
)
from .services.audit_service import AuditService
from .services.automation_service import AutomationService
from .services.crm_service import CRMService
from .services.scheduling_service import SchedulingService

DEFAULT_SOURCE_DIR = os.path.expanduser("~/Aigentik-CLI/data")

OUT_OF_SCOPE_FILES = {
    "contacts.json": "NEW-215: Android-contacts phonebook sync, not CRM data -- categorical data-model mismatch, not a data-safety exclusion",
}

VALID_CHANNELS = {"email", "sms"}
VALID_APPT_STATUSES = {"confirmed", "negotiating", "cancelled", "completed"}
VALID_APPT_TYPES = {"call", "in_person"}

# customers.json source keys with a direct, non-lossy mapping onto a
# Customer column (see map_customer()). Every other source key present
# on a record is preserved verbatim under custom_fields["aigentik_raw"]
# rather than being dropped or guessed into a column it doesn't match.
CUSTOMER_MAPPED_SOURCE_KEYS = {
    "customer_id",
    "customer_name",
    "phone",
    "email",
    "property_address",
    "lead_source",
    "last_contact",
    "next_followup",
}


def build_migration_actor() -> AuthContext:
    """Hand-constructed AuthContext for this offline script. See the
    module docstring's "AuthContext bootstrap" section for why this is
    safe here rather than provisioning a real users row."""
    return AuthContext(
        user_id=None,  # type: ignore[arg-type]  # see docstring: only audit_log.actor_id reads this, and it's a nullable FK
        username="migration_script",
        role=ROLE_AI_AGENT,
        actor_type="agent",
        customer_id=None,
        token=None,
    )


def _read_json_stable(
    path: str,
    max_retries: int = 3,
    backoff_seconds: float = 0.25,
    stability_delay_seconds: float = 0.05,
) -> Tuple[Any, str]:
    """Read and parse a JSON file defensively against a live,
    non-atomically-writing process (Aigentik-CLI's writeFileSync()).

    Returns (data, "absent") if the file does not exist -- distinct from
    (data, "present") with an empty list/dict, per requirement 6.

    Guards against torn reads by re-reading after a short delay and
    requiring two consecutive parses to agree, rather than a bare
    record-count floor (a floor would misclassify a legitimately empty
    file, e.g. sms-rules.json, as a torn read). Retries with backoff on
    outright read/parse errors (the file can momentarily disappear or be
    unreadable mid-rename).
    """
    if not os.path.exists(path):
        return None, "absent"

    last_error: Optional[BaseException] = None
    for attempt in range(max_retries):
        try:
            with open(path, "r", encoding="utf-8") as f:
                first = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            last_error = exc
            time.sleep(backoff_seconds * (attempt + 1))
            continue

        time.sleep(stability_delay_seconds)

        try:
            with open(path, "r", encoding="utf-8") as f:
                second = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            last_error = exc
            time.sleep(backoff_seconds * (attempt + 1))
            continue

        if first == second:
            return first, "present"

        last_error = RuntimeError(
            f"{path}: two consecutive reads disagree (possible torn write mid-migration)"
        )
        time.sleep(backoff_seconds * (attempt + 1))

    raise RuntimeError(
        f"Failed to get a stable read of {path} after {max_retries} attempts: {last_error}"
    )


def _bool01(rec: Dict[str, Any], key: str, errors: List[str], default: int = 0) -> int:
    """Coerce a JSON boolean to the 0/1 int the NOT NULL CHECK columns
    expect. Missing key -> default. Also accepts a bare integer 0 or 1:
    Aigentik's B2-fin-1 write-through cache writes ints to profile.json
    for configured/agent_name_set/onboarding_sent. Anything else present
    (2, -1, 1.0, "1", "true", ...) is a validation error, reported (not
    raised) so dry-run surfaces it.

    String "0"/"1" are deliberately NOT accepted: the real
    ~/Codey-Aigentik/data/profile.json has bare JSON ints, nothing emits
    string booleans, and unrequested widening is barred by CLAUDE.md
    conventions."""
    if key not in rec or rec[key] is None:
        return default
    v = rec[key]
    # bool check must stay first: isinstance(True, int) is True.
    if isinstance(v, bool):
        return 1 if v else 0
    # isinstance(v, int) guard is required: 1.0 in (0, 1) and
    # True in (0, 1) are both True without it.
    if isinstance(v, int) and v in (0, 1):
        return v
    errors.append(f"{key}: expected boolean or 0/1, got {v!r}")
    return default


def _nullable_bool01(rec: Dict[str, Any], key: str, errors: List[str]) -> Optional[int]:
    """Same as _bool01 but preserves None for nullable CHECK columns
    (e.g. subcontractors.license_required, which the schema explicitly
    allows to be NULL). Also accepts a bare integer 0 or 1 (see _bool01
    for the B2-fin-1 write-through rationale). String "0"/"1" are
    deliberately NOT accepted."""
    v = rec.get(key)
    if v is None:
        return None
    # bool check must stay first: isinstance(True, int) is True.
    if isinstance(v, bool):
        return 1 if v else 0
    # isinstance(v, int) guard is required: 1.0 in (0, 1) is True without it.
    if isinstance(v, int) and v in (0, 1):
        return v
    errors.append(f"{key}: expected boolean, 0/1, or null, got {v!r}")
    return None


def map_subcontractor(rec: Dict[str, Any]) -> Tuple[Optional[Subcontractor], List[str]]:
    """Map one subcontractors.json record to a Subcontractor, validating
    every NOT NULL / CHECK domain the subcontractors table enforces so a
    bad record is reported in dry-run rather than thrown as an
    IntegrityError during --apply."""
    errors: List[str] = []

    external_id = rec.get("subcontractor_id")
    if not external_id:
        errors.append("subcontractor_id (external_id) is required for idempotent migration")

    company_name = (rec.get("company_name") or "").strip()
    if not company_name:
        errors.append("company_name is required (NOT NULL) but missing/blank")

    sub = Subcontractor(
        external_id=external_id,
        contact_external_id=rec.get("contact_id"),
        company_name=company_name,
        legal_name=rec.get("legal_name"),
        dba=rec.get("dba"),
        contact_name=rec.get("contact_name"),
        title=rec.get("title"),
        phone=rec.get("phone"),
        email=rec.get("email"),
        website=rec.get("website"),
        primary_trade=rec.get("primary_trade"),
        secondary_trades=rec.get("secondary_trades") or [],
        service_area=rec.get("service_area"),
        years_in_business=rec.get("years_in_business"),
        crew_size=rec.get("crew_size"),
        residential_experience=rec.get("residential_experience"),
        commercial_experience=rec.get("commercial_experience"),
        typical_project_size=rec.get("typical_project_size"),
        availability=rec.get("availability"),
        emergency_availability=rec.get("emergency_availability"),
        license_required=_nullable_bool01(rec, "license_required", errors),
        license_type=rec.get("license_type"),
        license_number=rec.get("license_number"),
        license_expiration=rec.get("license_expiration"),
        license_status=rec.get("license_status"),
        general_liability=rec.get("general_liability"),
        workers_comp=rec.get("workers_comp"),
        coi_received=_bool01(rec, "coi_received", errors),
        coi_expiration=rec.get("coi_expiration"),
        additional_insured_status=rec.get("additional_insured_status"),
        insurance_status=rec.get("insurance_status"),
        w9_received=_bool01(rec, "w9_received", errors),
        msa_sent=_bool01(rec, "msa_sent", errors),
        msa_signed=_bool01(rec, "msa_signed", errors),
        references=rec.get("references") or [],
        portfolio_url=rec.get("portfolio_url"),
        qualification_status=rec.get("qualification_status") or "QUALIFICATION_IN_PROGRESS",
        recruitment_step=rec.get("recruitment_step"),
        lead_source=rec.get("lead_source"),
        last_contact_at=rec.get("last_contact"),
        next_followup_at=rec.get("next_followup"),
        contact_attempts=rec.get("contact_attempts") or 0,
        dnc_status=_bool01(rec, "dnc_status", errors),
        notes=rec.get("notes"),
        qualification_data=rec.get("qualification_data") or {},
    )

    if errors:
        return None, errors
    return sub, []


def map_appointment(rec: Dict[str, Any]) -> Tuple[Optional[Appointment], List[str]]:
    """Map one calendar.json record to an Appointment, validating the
    appointments table's NOT NULL/CHECK domains (status,
    appointment_type) up front."""
    errors: List[str] = []

    external_id = rec.get("id")
    if not external_id:
        errors.append("id (external_id) is required for idempotent migration")

    title = (rec.get("title") or "").strip()
    if not title:
        errors.append("title is required (NOT NULL) but missing/blank")

    status = rec.get("status") or "confirmed"
    if status not in VALID_APPT_STATUSES:
        errors.append(f"status: {status!r} not in {sorted(VALID_APPT_STATUSES)}")

    appt_type = rec.get("appointment_type")
    if appt_type is not None and appt_type not in VALID_APPT_TYPES:
        errors.append(
            f"appointment_type: {appt_type!r} not in {sorted(VALID_APPT_TYPES)} or null"
        )

    appt = Appointment(
        external_id=external_id,
        uid=rec.get("uid"),
        ics_sequence=rec.get("ics_sequence") or 0,
        title=title,
        start_time=rec.get("start"),
        end_time=rec.get("end"),
        # No reliable match to a Core customer exists yet -- contacts.json
        # (the would-be link) is out of scope this round (NEW-215).
        customer_id=None,
        contact_external_id=rec.get("contact_id"),
        attendee_name=rec.get("attendee_name"),
        attendee_email=rec.get("attendee_email"),
        appointment_type=appt_type,
        status=status,
        rsvp_status=rec.get("rsvp_status") or "pending",
        offered_slots=rec.get("offered_slots") or [],
        requested_datetime=rec.get("requested_datetime"),
        pending_reschedule=rec.get("pending_reschedule"),
        form_sent=_bool01(rec, "form_sent", errors),
        created_via=rec.get("created_via") or "owner",
        notes=rec.get("notes"),
        history=rec.get("history") or [],
    )

    if errors:
        return None, errors
    return appt, []


def map_rule(rec: Dict[str, Any], channel: str) -> Tuple[Optional[AutomationRule], List[str]]:
    """Map one email-rules.json/sms-rules.json record to an
    AutomationRule, validating the automation_rules table's NOT
    NULL/CHECK domains (channel, condition_type, condition_value,
    action)."""
    errors: List[str] = []

    external_id = rec.get("id")
    if not external_id:
        errors.append("id (external_id) is required for idempotent migration")

    condition_type = rec.get("condition_type")
    condition_value = rec.get("condition_value")
    action = rec.get("action")

    if not condition_type:
        errors.append("condition_type is required (NOT NULL) but missing/blank")
    if not condition_value:
        errors.append("condition_value is required (NOT NULL) but missing/blank")
    if not action:
        errors.append("action is required (NOT NULL) but missing/blank")
    if channel not in VALID_CHANNELS:
        errors.append(f"channel: {channel!r} not in {sorted(VALID_CHANNELS)}")

    rule = AutomationRule(
        external_id=external_id,
        channel=channel,
        description=rec.get("description"),
        condition_type=condition_type or "",
        condition_value=condition_value or "",
        action=action or "",
        added_by=rec.get("added_by"),
        match_count=rec.get("match_count") or 0,
    )

    if errors:
        return None, errors
    return rule, []


def map_profile(rec: Dict[str, Any]) -> Tuple[Optional[BusinessProfile], List[str]]:
    """Map profile.json (a single object, not a list) to a
    BusinessProfile, validating its boolean CHECK columns."""
    errors: List[str] = []

    profile = BusinessProfile(
        configured=_bool01(rec, "configured", errors),
        aigentik_name=rec.get("aigentik_name"),
        agent_name_set=_bool01(rec, "agent_name_set", errors),
        owner_name=rec.get("owner_name"),
        business_name=rec.get("business_name"),
        business_description=rec.get("business_description"),
        onboarding_sent=_bool01(rec, "onboarding_sent", errors),
        setup_date=rec.get("setup_date"),
    )

    if errors:
        return None, errors
    return profile, []


def map_customer(rec: Dict[str, Any]) -> Tuple[Optional[Customer], List[str]]:
    """Map one customers.json record to a Customer.

    Only 8 of the source's ~46 fields (CUSTOMER_MAPPED_SOURCE_KEYS) have a
    direct, non-lossy destination column:

        customer_id      -> external_id
        customer_name     -> first_name/last_name (split on first space;
                             single-word names, e.g. "Prospective
                             Customer" being two words is the common
                             case, get last_name="")
        phone             -> phone
        email             -> email
        property_address -> service_address
        lead_source       -> customer_source
        last_contact      -> last_contact_at
        next_followup     -> next_followup_at

    Every other field on the record (insurance/claim fields, project-
    scheduling fields, customer_category/lead_status/lead_score,
    customer_notes, dnc_status, appointment_*, created_at/updated_at,
    etc.) is preserved verbatim under custom_fields["aigentik_raw"] --
    not dropped, and not guessed into Customer.status or
    Customer.customer_type, both of which are CHECK-constrained to
    domains (lead/prospect/active/past/lost;
    residential/commercial) that none of the source's status-like fields
    actually match. Those two columns are left at their Customer
    dataclass defaults ('lead', 'residential') for every migrated
    record; see the module docstring for why guessing was rejected.
    """
    errors: List[str] = []

    external_id = rec.get("customer_id")
    if not external_id:
        errors.append("customer_id (external_id) is required for idempotent migration")

    raw_name = (rec.get("customer_name") or "").strip()
    if not raw_name:
        errors.append("customer_name is required but missing/blank")
    name_parts = raw_name.split(" ", 1)
    first_name = name_parts[0]
    last_name = name_parts[1] if len(name_parts) > 1 else ""

    aigentik_raw = {
        k: v for k, v in rec.items() if k not in CUSTOMER_MAPPED_SOURCE_KEYS
    }

    customer = Customer(
        external_id=external_id,
        first_name=first_name,
        last_name=last_name,
        phone=rec.get("phone"),
        email=rec.get("email"),
        service_address=rec.get("property_address"),
        customer_source=rec.get("lead_source"),
        last_contact_at=rec.get("last_contact"),
        next_followup_at=rec.get("next_followup"),
        custom_fields={"aigentik_raw": aigentik_raw},
    )

    if errors:
        return None, errors
    return customer, []


def map_schedule_config(rec: Dict[str, Any]) -> Tuple[Optional[ScheduleConfig], List[str]]:
    """Map schedule-config.json (a single object, not a list) to a
    ScheduleConfig. All fields map 1:1 -- no CHECK-constrained columns
    beyond the fixed id=1 the upsert always sets, and no unmappable
    fields (unlike customers.json)."""
    config = ScheduleConfig(
        working_hours=rec.get("working_hours") or {},
        default_duration_minutes=rec.get("default_duration_minutes") or 30,
        buffer_minutes=rec.get("buffer_minutes") or 15,
        booking_window_days=rec.get("booking_window_days") or 365,
        duration_by_relationship=rec.get("duration_by_relationship") or {},
    )
    return config, []


def _empty_list_entry() -> Dict[str, Any]:
    return {
        "file_status": "absent",
        "total_records": 0,
        "would_insert": 0,
        "would_skip": 0,
        "invalid": [],
        "inserted": 0,
        "skipped": 0,
    }


def _migrate_list_file(
    *,
    source_dir: str,
    filename: str,
    mapper: Callable[[Dict[str, Any]], Tuple[Optional[Any], List[str]]],
    lookup_fn: Callable[[str, AuthContext], Optional[Any]],
    create_fn: Callable[[Any, AuthContext], Any],
    actor: AuthContext,
    apply: bool,
) -> Dict[str, Any]:
    """Shared driver for the three skip-if-exists tables (subcontractors,
    appointments, automation_rules per channel)."""
    path = os.path.join(source_dir, filename)
    try:
        data, file_status = _read_json_stable(path)
    except Exception as exc:
        return {"file_status": "error", "error": str(exc)}

    if file_status == "absent":
        return _empty_list_entry()

    if not isinstance(data, list):
        return {
            "file_status": "present",
            "error": f"expected a JSON array in {filename}, got {type(data).__name__}",
        }

    entry = _empty_list_entry()
    entry["file_status"] = "present"
    entry["total_records"] = len(data)

    for idx, rec in enumerate(data):
        obj, errors = mapper(rec)
        if errors:
            entry["invalid"].append(
                {"index": idx, "source_record": rec, "errors": errors}
            )
            continue

        existing = lookup_fn(obj.external_id, actor) if obj.external_id else None
        if existing is not None:
            entry["would_skip"] += 1
            if apply:
                entry["skipped"] += 1
            continue

        entry["would_insert"] += 1
        if apply:
            create_fn(obj, actor)
            entry["inserted"] += 1

    return entry


def _migrate_profile_file(
    *,
    source_dir: str,
    filename: str,
    automation_service: AutomationService,
    actor: AuthContext,
    apply: bool,
) -> Dict[str, Any]:
    """business_profile is a singleton, update-always (upsert) target --
    see the module docstring's idempotency-strategy section."""
    path = os.path.join(source_dir, filename)
    try:
        data, file_status = _read_json_stable(path)
    except Exception as exc:
        return {"file_status": "error", "error": str(exc)}

    if file_status == "absent":
        return {
            "file_status": "absent",
            "total_records": 0,
            "would_upsert": 0,
            "invalid": [],
            "upserted": 0,
        }

    if not isinstance(data, dict):
        return {
            "file_status": "present",
            "error": f"expected a JSON object in {filename}, got {type(data).__name__}",
        }

    entry: Dict[str, Any] = {
        "file_status": "present",
        "total_records": 1,
        "would_upsert": 0,
        "invalid": [],
        "upserted": 0,
    }

    profile, errors = map_profile(data)
    if errors:
        entry["invalid"].append({"index": 0, "source_record": data, "errors": errors})
        return entry

    entry["would_upsert"] = 1
    if apply:
        automation_service.upsert_business_profile(profile, actor)
        entry["upserted"] = 1

    return entry


def _migrate_schedule_config_file(
    *,
    source_dir: str,
    filename: str,
    scheduling_service: SchedulingService,
    actor: AuthContext,
    apply: bool,
) -> Dict[str, Any]:
    """schedule_config is a singleton, update-always (upsert) target,
    mirroring _migrate_profile_file's pattern exactly. No pre-read via
    get_schedule_config() -- there is nothing to compare against or
    report beyond would_upsert/upserted, and it would only add another
    permission gate for no benefit."""
    path = os.path.join(source_dir, filename)
    try:
        data, file_status = _read_json_stable(path)
    except Exception as exc:
        return {"file_status": "error", "error": str(exc)}

    if file_status == "absent":
        return {
            "file_status": "absent",
            "total_records": 0,
            "would_upsert": 0,
            "invalid": [],
            "upserted": 0,
        }

    if not isinstance(data, dict):
        return {
            "file_status": "present",
            "error": f"expected a JSON object in {filename}, got {type(data).__name__}",
        }

    entry: Dict[str, Any] = {
        "file_status": "present",
        "total_records": 1,
        "would_upsert": 0,
        "invalid": [],
        "upserted": 0,
    }

    config, errors = map_schedule_config(data)
    if errors:
        entry["invalid"].append({"index": 0, "source_record": data, "errors": errors})
        return entry

    entry["would_upsert"] = 1
    if apply:
        scheduling_service.upsert_schedule_config(config, actor)
        entry["upserted"] = 1

    return entry


def run_migration(source_dir: str, db_manager: DatabaseManager, apply: bool) -> Dict[str, Any]:
    """Run the migration (dry-run unless apply=True) and return a
    structured, per-file report. Never writes to the database unless
    apply is True."""
    actor = build_migration_actor()
    audit_service = AuditService(db_manager)
    crm_service = CRMService(db_manager, audit_service)
    scheduling_service = SchedulingService(db_manager, audit_service)
    automation_service = AutomationService(db_manager, audit_service)

    report: Dict[str, Any] = {}

    report["subcontractors"] = _migrate_list_file(
        source_dir=source_dir,
        filename="subcontractors.json",
        mapper=map_subcontractor,
        lookup_fn=crm_service.get_subcontractor_by_external_id,
        create_fn=crm_service.create_subcontractor,
        actor=actor,
        apply=apply,
    )

    report["appointments"] = _migrate_list_file(
        source_dir=source_dir,
        filename="calendar.json",
        mapper=map_appointment,
        lookup_fn=scheduling_service.get_appointment_by_external_id,
        create_fn=scheduling_service.create_appointment,
        actor=actor,
        apply=apply,
    )

    report["automation_rules_email"] = _migrate_list_file(
        source_dir=source_dir,
        filename="email-rules.json",
        mapper=lambda rec: map_rule(rec, "email"),
        lookup_fn=automation_service.get_automation_rule_by_external_id,
        create_fn=automation_service.create_rule,
        actor=actor,
        apply=apply,
    )

    report["automation_rules_sms"] = _migrate_list_file(
        source_dir=source_dir,
        filename="sms-rules.json",
        mapper=lambda rec: map_rule(rec, "sms"),
        lookup_fn=automation_service.get_automation_rule_by_external_id,
        create_fn=automation_service.create_rule,
        actor=actor,
        apply=apply,
    )

    report["business_profile"] = _migrate_profile_file(
        source_dir=source_dir,
        filename="profile.json",
        automation_service=automation_service,
        actor=actor,
        apply=apply,
    )

    report["customers"] = _migrate_list_file(
        source_dir=source_dir,
        filename="customers.json",
        mapper=map_customer,
        lookup_fn=crm_service.get_customer_by_external_id,
        create_fn=crm_service.create_customer,
        actor=actor,
        apply=apply,
    )

    report["schedule_config"] = _migrate_schedule_config_file(
        source_dir=source_dir,
        filename="schedule-config.json",
        scheduling_service=scheduling_service,
        actor=actor,
        apply=apply,
    )

    report["skipped_out_of_scope"] = dict(OUT_OF_SCOPE_FILES)

    return report


def print_report(report: Dict[str, Any], apply: bool) -> None:
    mode = "APPLY (writes performed)" if apply else "DRY RUN (no writes performed)"
    print(f"=== Aigentik-CLI -> restoricon_core migration report [{mode}] ===")

    for key in (
        "subcontractors",
        "appointments",
        "automation_rules_email",
        "automation_rules_sms",
        "business_profile",
        "customers",
        "schedule_config",
    ):
        entry = report[key]
        print(f"\n[{key}]")
        print(f"  file_status: {entry['file_status']}")
        if "error" in entry:
            print(f"  ERROR: {entry['error']}")
            continue
        print(f"  total_records: {entry['total_records']}")
        if "would_insert" in entry:
            print(f"  would_insert: {entry['would_insert']}  would_skip: {entry['would_skip']}")
            if apply:
                print(f"  inserted: {entry['inserted']}  skipped: {entry['skipped']}")
        else:
            print(f"  would_upsert: {entry['would_upsert']}")
            if apply:
                print(f"  upserted: {entry['upserted']}")
        if entry["invalid"]:
            print(f"  INVALID records ({len(entry['invalid'])}):")
            for bad in entry["invalid"]:
                print(f"    - index {bad['index']}: {'; '.join(bad['errors'])}")

    print("\n[skipped_out_of_scope]")
    for filename, reason in report["skipped_out_of_scope"].items():
        print(f"  {filename}: {reason}")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Migrate Aigentik-CLI's live JSON data into restoricon_core's SQLite DB."
    )
    parser.add_argument(
        "--source-dir",
        default=DEFAULT_SOURCE_DIR,
        help=f"Directory containing Aigentik-CLI's JSON data files (default: {DEFAULT_SOURCE_DIR})",
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help="Path to restoricon_core's SQLite DB (default: restoricon_core.database.DEFAULT_DB_PATH)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually write to the database. Without this flag, the script only reports what it would do.",
    )
    args = parser.parse_args(argv)

    db_manager = DatabaseManager(args.db_path) if args.db_path else DatabaseManager()
    report = run_migration(args.source_dir, db_manager, args.apply)
    print_report(report, args.apply)
    return 0


if __name__ == "__main__":
    sys.exit(main())
