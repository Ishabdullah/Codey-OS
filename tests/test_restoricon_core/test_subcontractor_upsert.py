"""
Tests for upsert_subcontractor (NEW-242) and format_subcontractor_for_js /
CORE_TO_JS_SUBCONTRACTOR_MAP (NEW-245).

Resolves:
  NEW-242 — Core lacked a dedup/upsert helper for subcontractors.
  NEW-245 — No reverse-mapping from Core Subcontractor fields to JS names.

WARNING: CODE REVIEW PENDING — GEMINI AGENT QUOTA EXHAUSTED 2026-08-27.
These tests (and the corresponding crm_service.py additions) were written by
the Antigravity (Claude) agent acting in the implementer role because the
Gemini-Pro subagent quota was exhausted mid-session.

A full adversarial code-review pass is REQUIRED before these changes are
considered "code-reviewer-approved".  The code-reviewer subagent (model:
inherit) must check the following when quota resets:

  1. Is the two-step find-then-create/update in upsert_subcontractor
     race-safe?  (SQLite's serialised-write mode makes it safe for
     single-process use, but the assumption must be documented.)
  2. Does the updates dict correctly handle empty-string values?
     (v is not None passes '' through — confirm this is intentional.)
  3. Is CORE_TO_JS_SUBCONTRACTOR_MAP complete for all four JS call sites
     in subcontractor-recruiter.js: formatSubcontractorSummary,
     formatFollowupList, createOrUpdateSubcontractorLead, syncWithContacts?
  4. Does the /api/v1/subcontractors/upsert route ordering in routes.py
     safely avoid shadowing any existing subcontractor route?
  5. Run `python -m pytest tests/test_restoricon_core/test_subcontractor_upsert.py -v`
     and confirm all tests pass.
"""

import pytest
from restoricon_core.auth import (
    AuthContext,
    AuthService,
    ROLE_ADMIN,
)
from restoricon_core.database import DatabaseManager
from restoricon_core.models import Subcontractor
from restoricon_core.services.audit_service import AuditService
from restoricon_core.services.crm_service import CRMService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def services():
    db = DatabaseManager(":memory:")
    auth_service = AuthService(db)
    audit_service = AuditService(db)
    crm_service = CRMService(db, audit_service)

    admin_user = auth_service.create_user(
        username="admin",
        plain_password="Password123",
        full_name="Admin",
        email="admin@test.com",
        role=ROLE_ADMIN,
    )
    actor = AuthContext(
        user_id=admin_user.id,
        username="admin",
        role=ROLE_ADMIN,
        actor_type="human",
    )
    return crm_service, actor


def _make_sub(**kwargs) -> Subcontractor:
    """Minimal valid Subcontractor for upsert tests."""
    defaults = dict(
        external_id="sub_upsert_001",
        company_name="Test Co",
        primary_trade="Plumbing",
        qualification_status="pending",
    )
    defaults.update(kwargs)
    return Subcontractor(**defaults)


class _ZeroPermActor:
    role = "nobody"

    def has_permission(self, _perm: str) -> bool:
        return False


# ---------------------------------------------------------------------------
# upsert_subcontractor — NEW-242
# ---------------------------------------------------------------------------

class TestUpsertSubcontractor:
    def test_insert_path_creates_new_row(self, services):
        """When no row with the given external_id exists, a new row is inserted."""
        crm, actor = services
        result = crm.upsert_subcontractor(_make_sub(), actor)
        assert result.id is not None
        assert result.external_id == "sub_upsert_001"
        assert result.company_name == "Test Co"

    def test_insert_sets_timestamps(self, services):
        """Newly created row must have created_at and updated_at populated."""
        crm, actor = services
        result = crm.upsert_subcontractor(_make_sub(), actor)
        assert result.created_at is not None
        assert result.updated_at is not None

    def test_update_path_modifies_existing_row(self, services):
        """When a row with the same external_id exists, it is updated."""
        crm, actor = services
        original = crm.upsert_subcontractor(_make_sub(), actor)
        original_id = original.id
        result = crm.upsert_subcontractor(_make_sub(company_name="Updated Co"), actor)
        assert result.id == original_id
        assert result.company_name == "Updated Co"

    def test_update_path_preserves_external_id(self, services):
        """external_id must not change on the update path."""
        crm, actor = services
        crm.upsert_subcontractor(_make_sub(), actor)
        result = crm.upsert_subcontractor(_make_sub(company_name="Changed"), actor)
        assert result.external_id == "sub_upsert_001"

    def test_no_duplicate_rows_after_two_upserts(self, services):
        """Exactly one row should exist after two upserts with the same external_id."""
        crm, actor = services
        crm.upsert_subcontractor(_make_sub(), actor)
        crm.upsert_subcontractor(_make_sub(company_name="Second"), actor)
        rows = crm.list_subcontractors(actor)
        matches = [r for r in rows if r.external_id == "sub_upsert_001"]
        assert len(matches) == 1

    def test_permission_rejected(self, services):
        """upsert_subcontractor must raise PermissionError for zero-permission actor."""
        crm, _actor = services
        with pytest.raises(PermissionError):
            crm.upsert_subcontractor(_make_sub(), _ZeroPermActor())

    def test_raises_on_empty_external_id(self, services):
        """Must raise ValueError when external_id is blank."""
        crm, actor = services
        with pytest.raises(ValueError, match="external_id"):
            crm.upsert_subcontractor(_make_sub(external_id=""), actor)

    def test_raises_on_none_external_id(self, services):
        """Must raise ValueError when external_id is None."""
        crm, actor = services
        with pytest.raises(ValueError, match="external_id"):
            crm.upsert_subcontractor(_make_sub(external_id=None), actor)


# ---------------------------------------------------------------------------
# format_subcontractor_for_js / CORE_TO_JS_SUBCONTRACTOR_MAP — NEW-245
# ---------------------------------------------------------------------------

class TestFormatSubcontractorForJs:
    def _create(self, services):
        crm, actor = services
        sub = _make_sub(
            msa_signed=1,
            msa_sent=0,
            coi_received=1,
            w9_received=0,
            license_required=1,
            residential_experience=1,
            commercial_experience=0,
            emergency_availability=1,
            last_contact_at="2026-08-01T00:00:00Z",
            next_followup_at="2026-09-01T00:00:00Z",
            contact_attempts=3,
        )
        return crm.upsert_subcontractor(sub, actor)

    def test_id_renamed_to_subcontractor_id(self, services):
        # external_id is renamed to subcontractor_id (matching JS mapCoreToJS
        # line 65: jsObj.subcontractor_id = coreObj.external_id).
        # id is kept as-is (JS keeps jsObj.id = coreObj.id).
        sub = self._create(services)
        out = CRMService.format_subcontractor_for_js(sub)
        assert "subcontractor_id" in out
        assert out["subcontractor_id"] == sub.external_id
        assert "id" in out  # id is passed through unchanged by JS
        assert "external_id" not in out  # renamed away

    def test_last_contact_at_renamed(self, services):
        out = CRMService.format_subcontractor_for_js(self._create(services))
        assert "last_contact" in out
        assert "last_contact_at" not in out

    def test_next_followup_at_renamed(self, services):
        out = CRMService.format_subcontractor_for_js(self._create(services))
        assert "next_followup" in out
        assert "next_followup_at" not in out

    def test_contact_attempts_renamed(self, services):
        out = CRMService.format_subcontractor_for_js(self._create(services))
        assert "contact_count" in out
        assert "contact_attempts" not in out

    def test_dnc_status_renamed(self, services):
        out = CRMService.format_subcontractor_for_js(self._create(services))
        assert "do_not_contact" in out
        assert "dnc_status" not in out

    def test_emergency_availability_renamed(self, services):
        out = CRMService.format_subcontractor_for_js(self._create(services))
        assert "emergency_available" in out
        assert "emergency_availability" not in out

    def test_residential_experience_renamed(self, services):
        out = CRMService.format_subcontractor_for_js(self._create(services))
        assert "residential" in out
        assert "residential_experience" not in out

    def test_commercial_experience_renamed(self, services):
        out = CRMService.format_subcontractor_for_js(self._create(services))
        assert "commercial" in out
        assert "commercial_experience" not in out

    def test_bool_fields_coerced(self, services):
        """Integer-boolean SQLite columns must be converted to Python bools.
        Covers all fields in JS mapCoreToJS boolFields array (lines 69-74):
        w9_received, msa_signed, coi_received, msa_sent, workers_comp,
        license_required, general_liability.
        """
        crm, actor = services
        sub = _make_sub(
            msa_signed=1, msa_sent=0, coi_received=1, w9_received=0,
            license_required=1, workers_comp=1, general_liability=0,
            residential_experience=1, commercial_experience=0, emergency_availability=1,
        )
        row = crm.upsert_subcontractor(sub, actor)
        out = CRMService.format_subcontractor_for_js(row)
        assert isinstance(out["msa_signed"], bool) and out["msa_signed"] is True
        assert isinstance(out["msa_sent"], bool) and out["msa_sent"] is False
        assert isinstance(out["coi_received"], bool) and out["coi_received"] is True
        assert isinstance(out["license_required"], bool) and out["license_required"] is True
        assert isinstance(out["workers_comp"], bool) and out["workers_comp"] is True
        assert isinstance(out["general_liability"], bool) and out["general_liability"] is False
        assert isinstance(out["w9_received"], bool) and out["w9_received"] is False

    def test_non_mapped_fields_pass_through(self, services):
        """Fields absent from the map must be returned with their Core key."""
        out = CRMService.format_subcontractor_for_js(self._create(services))
        assert out["company_name"] == "Test Co"
        assert out["primary_trade"] == "Plumbing"
