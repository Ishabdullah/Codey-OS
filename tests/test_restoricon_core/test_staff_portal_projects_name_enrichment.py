"""NEW-660: same bug class as NEW-656/the sales-portal fix (4d57d50), a
different portal. _render_staff_portal_base() -- the shared template for
the PM/technician/subcontractor portals -- showed a raw customer_id
number ("Cust #3") in its "Assignments" table instead of a customer name.

Covers the server-side response-shape change (new `customer_name` key on
GET /api/v1/projects, attached alongside the existing customer_id key,
which stays for other consumers -- the admin CRM panel's project list/
create form and the Document Handoff panel all consume this same route
and only read p.id/p.title/p.status/p.stage/p.project_type, so the new
key is harmless there) plus the rendered HTML/JS shape of the shared
staff portal template.
"""

from restoricon_core.api.routes import APIRouter
from restoricon_core.api.web_surfaces import (
    render_pm_surface,
    render_tech_surface,
    render_subcontractor_surface,
)
from restoricon_core.auth import AuthContext, AuthService, ROLE_ADMIN, ROLE_SALES, ROLE_TECHNICIAN
from restoricon_core.database import DatabaseManager
from restoricon_core.models import Customer, Project
from restoricon_core.services.audit_service import AuditService
from restoricon_core.services.automation_service import AutomationService
from restoricon_core.services.communication_service import CommunicationService
from restoricon_core.services.crm_service import CRMService
from restoricon_core.services.scheduling_service import SchedulingService

import pytest


@pytest.fixture
def env():
    db = DatabaseManager(":memory:")
    auth = AuthService(db)
    audit = AuditService(db)
    comm = CommunicationService(db)
    crm = CRMService(db, audit)
    sched = SchedulingService(db, audit)
    auto = AutomationService(db, audit)
    router = APIRouter(auth, crm, comm, audit, sched, auto)

    admin_user = auth.create_user("admin_user", "Pass123!", "Admin User", "admin@test.com", ROLE_ADMIN)
    admin_actor = AuthContext(admin_user.id, "admin_user", ROLE_ADMIN, "human")

    cust = crm.create_customer(
        Customer(first_name="Jane", last_name="Doe", email="jane@test.com"), admin_actor
    )

    linked_project = crm.create_project(
        Project(customer_id=cust.id, title="Roof Replacement"), admin_actor
    )

    return {
        "router": router,
        "admin_token": auth.create_token(admin_user),
        "admin_actor": admin_actor,
        "cust": cust,
        "linked_project": linked_project,
    }


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def test_list_projects_includes_customer_name(env):
    status, _, data = env["router"].handle_request(
        "GET", "/api/v1/projects", _headers(env["admin_token"]), b""
    )
    assert status == 200
    by_id = {p["id"]: p for p in data["projects"]}

    linked = by_id[env["linked_project"].id]
    assert linked["customer_id"] == env["cust"].id, "existing customer_id key must not be removed"
    assert linked["customer_name"] == "Jane Doe"


def test_list_projects_customer_name_survives_technician_actor_narrowing(env):
    """Task item 3: enrichment must happen server-side on the full
    response, before crm_service.list_projects's own actor-based
    narrowing (technicians only see projects where they're in
    assigned_employees) is applied by a DIFFERENT actor than admin. Uses
    a real technician token/route round trip, not just an admin token,
    to actually exercise that narrowing rather than assume it composes
    correctly with the new enrichment."""
    auth = env["router"].auth
    tech_user = auth.create_user(
        "tech_user_660", "Pass123!", "Tech User", "tech660@test.com", ROLE_TECHNICIAN
    )
    tech_token = auth.create_token(tech_user)

    crm = env["router"].crm
    admin_actor = env["admin_actor"]

    assigned_project = crm.create_project(
        Project(
            customer_id=env["cust"].id,
            title="Tech's assigned job",
            assigned_employees=[tech_user.id],
        ),
        admin_actor,
    )
    unassigned_project = crm.create_project(
        Project(customer_id=env["cust"].id, title="Not tech's job"),
        admin_actor,
    )

    status, _, data = env["router"].handle_request(
        "GET", "/api/v1/projects", _headers(tech_token), b""
    )
    assert status == 200
    ids = {p["id"] for p in data["projects"]}
    assert assigned_project.id in ids, "technician narrowing must still return their assigned project"
    assert unassigned_project.id not in ids, "technician narrowing must still exclude unassigned projects"

    by_id = {p["id"]: p for p in data["projects"]}
    assert by_id[assigned_project.id]["customer_name"] == "Jane Doe", (
        "customer_name enrichment must survive technician-actor narrowing, "
        "not just work for the admin token used elsewhere in this file"
    )


def test_get_customer_display_name_nonexistent_id_falls_back_to_none(env):
    """Project.customer_id is a NOT NULL FK (unlike Lead's nullable
    customer_id) -- there is no genuinely-unlinked project to exercise via
    the route, so the fallback-to-None path is covered directly against
    the same ungated resolver the route uses."""
    assert env["router"].crm._get_customer_display_name(999999) is None


def test_staff_portals_render_customer_name_not_raw_id():
    """The old 'Cust #' string was deliberately eliminated project-wide in
    the sales-portal round (4d57d50) -- it must not reappear here, and the
    shared staff portal template must prefer customer_name with the same
    'Customer #' + id fallback convention used by the sales portal."""
    for html in (render_pm_surface(), render_tech_surface(), render_subcontractor_surface()):
        assert "'Cust #'" not in html
        assert "p.customer_name || ('Customer #' + p.customer_id)" in html


def test_staff_portal_assignments_use_full_response_before_role_filtering():
    """The customer_name enrichment happens server-side on the full
    /api/v1/projects response, before any client-side role narrowing
    (project_manager_id / subcontractors_json filtering) -- so the
    rendering line consuming customer_name must sit in the same
    myProjects.map() block regardless of role, not be duplicated per
    role-filter branch."""
    for html in (render_pm_surface(), render_tech_surface(), render_subcontractor_surface()):
        start = html.index("async function loadDashboard()")
        end = html.index("window.onload = loadDashboard;")
        dashboard_js = html[start:end]
        assert dashboard_js.count("p.customer_name || ('Customer #' + p.customer_id)") == 1
