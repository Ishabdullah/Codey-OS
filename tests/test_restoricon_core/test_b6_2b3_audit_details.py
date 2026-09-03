"""
B6.2b-3: migrate the 8 operations_service.py real-update audit sites onto the
canonical ``build_audit_details(before=…, after=…)`` envelope.

Sites covered:
  1. transition_project_stage   (action="project_stage_transition")
  2. update_milestone_status    (action="status_change")
  3. update_work_order          (action="update")            -- C-none snapshot
  4. dispatch_work_order        (action="work_order_dispatch")
  5. accept_work_order          (action="work_order_accept")
  6. update_work_order_execution_status (action="status_change")
  7. deploy_equipment           (action="equipment_deploy")
  8. return_equipment           (action="equipment_return")  -- C-none snapshot

Real DatabaseManager / AuthService / AuditService / OperationsService, admin
AuthContext, no mocks. Payloads are read back through
AuditService.query_logs(...).details, never the AuditRecord returned by
audit.log().
"""

import json

import pytest

from restoricon_core.auth import AuthService, ROLE_ADMIN
from restoricon_core.database import DatabaseManager
from restoricon_core.models import (
    Equipment,
    EquipmentDeployment,
    EquipmentStatus,
    MilestoneStatus,
    Project,
    ProjectMilestone,
    ProjectStage,
    Subcontractor,
    WorkOrder,
    WorkOrderStatus,
)
from restoricon_core.models import Customer
from restoricon_core.services.audit_service import (
    AuditService,
    _AUDITABLE_DEPLOYMENT_FIELDS,
    _AUDITABLE_EQUIPMENT_FIELDS,
    _AUDITABLE_MILESTONE_FIELDS,
    _AUDITABLE_PROJECT_FIELDS,
    _AUDITABLE_WORK_ORDER_FIELDS,
)
from restoricon_core.services.crm_service import CRMService
from restoricon_core.services.operations_service import OperationsService


@pytest.fixture
def env():
    db = DatabaseManager(":memory:")
    auth = AuthService(db)
    audit = AuditService(db)
    crm = CRMService(db, audit)
    ops = OperationsService(db, audit)
    admin = auth.create_user("admin_u", "AdminPass123!", "Admin U", "admin@r.com", role=ROLE_ADMIN)
    admin_ctx = auth.authenticate_token(auth.create_token(admin))
    cust = crm.create_customer(Customer(first_name="Parent", last_name="Co"), admin_ctx)
    return {"db": db, "auth": auth, "audit": audit, "crm": crm, "ops": ops,
            "admin": admin_ctx, "cust_id": cust.id}


def _details(env, entity_type, entity_id, action):
    rows = env["audit"].query_logs(
        env["admin"], entity_type=entity_type, entity_id=entity_id, action=action, limit=50
    )
    assert rows, f"no audit row for {entity_type}/{entity_id}/{action}"
    return rows[0].details


def _rows(env, entity_type, entity_id, action=None):
    return env["audit"].query_logs(
        env["admin"], entity_type=entity_type, entity_id=entity_id, action=action, limit=50
    )


def _mk_project(env, **kw):
    kw.setdefault("title", "P")
    kw.setdefault("customer_id", env["cust_id"])
    kw.setdefault("property_address", "742 Evergreen Terrace")
    return env["crm"].create_project(Project(**kw), env["admin"])


def _mk_wo(env, pid, **kw):
    kw.setdefault("project_id", pid)
    kw.setdefault("title", "WO")
    kw.setdefault("trade", "mitigation")
    return env["ops"].create_work_order(WorkOrder(**kw), env["admin"])


def _mk_sub(env, **kw):
    kw.setdefault("company_name", "Sub")
    kw.setdefault("primary_trade", "mitigation")
    kw.setdefault("coi_received", 1)
    kw.setdefault("coi_expiration", "2099-12-31")
    return env["crm"].create_subcontractor(Subcontractor(**kw), env["admin"])


def _mk_equipment(env, **kw):
    kw.setdefault("asset_tag", "EQ-1")
    kw.setdefault("name", "Dehumidifier")
    kw.setdefault("category", "dehumidifier")
    return env["ops"].create_equipment(Equipment(**kw), env["admin"])


def _dispatched_wo(env, pid):
    wo = _mk_wo(env, pid)
    sub = _mk_sub(env)
    env["ops"].dispatch_work_order(wo.id, sub.id, env["admin"])
    return wo


# ===========================================================================
# 1. per-site envelope shape
# ===========================================================================

def test_shape_transition_project_stage(env):
    p = _mk_project(env)
    env["ops"].transition_project_stage(p.id, ProjectStage.ASSESSMENT_SCOPING, env["admin"])
    d = _details(env, "project", p.id, "project_stage_transition")
    assert "changed_fields" in d
    assert "snapshot" not in d
    # ASSESSMENT_SCOPING from INTAKE ensures default milestones
    assert d["side_effects"]["default_milestones_ensured"] is True


def test_shape_update_milestone_status(env):
    p = _mk_project(env)
    m = env["ops"].create_milestone(
        ProjectMilestone(project_id=p.id, name="M1", stage=ProjectStage.INTAKE,
                         status=MilestoneStatus.PENDING),
        env["admin"],
    )
    env["ops"].update_milestone_status(m.id, MilestoneStatus.IN_PROGRESS, env["admin"])
    d = _details(env, "milestone", m.id, "status_change")
    assert "changed_fields" in d
    assert "side_effects" not in d
    assert "snapshot" not in d


def test_shape_update_work_order(env):
    p = _mk_project(env)
    wo = _mk_wo(env, p.id)
    wo.title = "WO renamed"
    env["ops"].update_work_order(wo, env["admin"])
    d = _details(env, "work_order", wo.id, "update")
    assert set(d) == {"snapshot"}
    assert d["snapshot"]["title"] == "WO renamed"


def test_shape_dispatch_work_order(env):
    p = _mk_project(env)
    wo = _mk_wo(env, p.id)
    sub = _mk_sub(env)
    env["ops"].dispatch_work_order(wo.id, sub.id, env["admin"])
    d = _details(env, "work_order", wo.id, "work_order_dispatch")
    assert "changed_fields" in d
    assert "snapshot" not in d
    # compliant sub, no override -> no side_effects
    assert "side_effects" not in d


def test_shape_accept_work_order(env):
    p = _mk_project(env)
    wo = _dispatched_wo(env, p.id)
    env["ops"].accept_work_order(wo.id, env["admin"])
    d = _details(env, "work_order", wo.id, "work_order_accept")
    assert set(d) == {"changed_fields"}


def test_shape_update_work_order_execution_status(env):
    p = _mk_project(env)
    wo = _dispatched_wo(env, p.id)
    env["ops"].accept_work_order(wo.id, env["admin"])
    env["ops"].update_work_order_execution_status(wo.id, WorkOrderStatus.IN_PROGRESS, env["admin"])
    d = _details(env, "work_order", wo.id, "status_change")
    assert set(d) == {"changed_fields"}


def test_shape_deploy_equipment(env):
    p = _mk_project(env)
    eq = _mk_equipment(env)
    env["ops"].deploy_equipment(eq.id, p.id, env["admin"], initial_reading="RH 80%")
    d = _details(env, "equipment", eq.id, "equipment_deploy")
    assert "changed_fields" in d
    assert "snapshot" not in d
    assert "deployment_created" in d["side_effects"]


def test_shape_return_equipment(env):
    p = _mk_project(env)
    eq = _mk_equipment(env)
    dep = env["ops"].deploy_equipment(eq.id, p.id, env["admin"])
    env["ops"].return_equipment(dep.id, env["admin"], final_reading="RH 35%")
    d = _details(env, "equipment", eq.id, "equipment_return")
    assert set(d) == {"snapshot", "side_effects"}
    assert set(d["snapshot"]) == {"status", "current_project_id"}


# ===========================================================================
# 2. per-site exact changed_fields key set
# ===========================================================================

def test_cf_transition_project_stage(env):
    p = _mk_project(env)
    env["ops"].transition_project_stage(p.id, ProjectStage.ASSESSMENT_SCOPING, env["admin"])
    cf = _details(env, "project", p.id, "project_stage_transition")["changed_fields"]
    assert set(cf) == {"stage", "stage_entered_at", "updated_at"}
    assert cf["stage"] == {"old": "intake", "new": "assessment_scoping"}


def test_cf_transition_completed_sets_actual_completion(env):
    p = _mk_project(env)
    env["ops"].transition_project_stage(p.id, ProjectStage.ON_HOLD, env["admin"])
    env["ops"].transition_project_stage(p.id, ProjectStage.COMPLETED, env["admin"])
    d = _details(env, "project", p.id, "project_stage_transition")
    cf = d["changed_fields"]
    assert "actual_completion" in cf
    assert cf["actual_completion"]["old"] is None
    assert cf["actual_completion"]["new"] is not None
    # same-entity column effect -> changed_fields ONLY, never echoed to side_effects
    assert "actual_completion" not in json.dumps(d.get("side_effects", {}))
    assert "status" in cf and cf["status"]["new"] == "completed"


def test_cf_update_milestone_status(env):
    p = _mk_project(env)
    m = env["ops"].create_milestone(
        ProjectMilestone(project_id=p.id, name="M", stage=ProjectStage.INTAKE,
                         status=MilestoneStatus.PENDING),
        env["admin"],
    )
    env["ops"].update_milestone_status(m.id, MilestoneStatus.COMPLETED, env["admin"])
    cf = _details(env, "milestone", m.id, "status_change")["changed_fields"]
    assert set(cf) == {"status", "completion_date", "updated_at"}
    assert cf["status"] == {"old": "pending", "new": "completed"}
    assert cf["completion_date"]["old"] is None


def test_cf_update_work_order_snapshot_keys(env):
    p = _mk_project(env)
    wo = _mk_wo(env, p.id)
    env["ops"].update_work_order(wo, env["admin"])
    snap = _details(env, "work_order", wo.id, "update")["snapshot"]
    assert set(snap) == set(WorkOrder().to_dict().keys())


def test_cf_dispatch_work_order(env):
    p = _mk_project(env)
    wo = _mk_wo(env, p.id)
    sub = _mk_sub(env)
    env["ops"].dispatch_work_order(
        wo.id, sub.id, env["admin"],
        scheduled_start="2026-09-01T08:00:00Z", scheduled_end="2026-09-01T17:00:00Z",
        instructions="lockbox 1234",
    )
    cf = _details(env, "work_order", wo.id, "work_order_dispatch")["changed_fields"]
    assert set(cf) == {
        "assigned_subcontractor_id", "status", "dispatched_at",
        "scheduled_start", "scheduled_end", "instructions", "updated_at",
    }
    assert cf["assigned_subcontractor_id"] == {"old": None, "new": sub.id}
    assert cf["status"]["new"] == WorkOrderStatus.DISPATCHED


def test_cf_accept_work_order(env):
    p = _mk_project(env)
    wo = _dispatched_wo(env, p.id)
    env["ops"].accept_work_order(wo.id, env["admin"], notes="on it")
    cf = _details(env, "work_order", wo.id, "work_order_accept")["changed_fields"]
    assert set(cf) == {"status", "accepted_at", "notes", "updated_at"}
    assert cf["status"] == {"old": WorkOrderStatus.DISPATCHED, "new": WorkOrderStatus.ACCEPTED}
    assert cf["notes"]["new"] == "on it"


def test_cf_update_work_order_execution_status(env):
    p = _mk_project(env)
    wo = _dispatched_wo(env, p.id)
    env["ops"].accept_work_order(wo.id, env["admin"])
    env["ops"].update_work_order_execution_status(
        wo.id, WorkOrderStatus.COMPLETED, env["admin"], notes="finished"
    )
    cf = _details(env, "work_order", wo.id, "status_change")["changed_fields"]
    assert set(cf) == {"status", "actual_end", "completed_at", "notes", "updated_at"}
    assert cf["status"]["new"] == WorkOrderStatus.COMPLETED


def test_cf_deploy_equipment(env):
    p = _mk_project(env)
    eq = _mk_equipment(env)
    env["ops"].deploy_equipment(eq.id, p.id, env["admin"], initial_reading="RH 80%")
    cf = _details(env, "equipment", eq.id, "equipment_deploy")["changed_fields"]
    assert set(cf) == {"status", "current_project_id", "updated_at"}
    assert cf["status"] == {"old": EquipmentStatus.AVAILABLE, "new": EquipmentStatus.DEPLOYED}
    assert cf["current_project_id"] == {"old": None, "new": p.id}


def test_cf_return_equipment(env):
    p = _mk_project(env)
    eq = _mk_equipment(env)
    dep = env["ops"].deploy_equipment(eq.id, p.id, env["admin"])
    env["ops"].return_equipment(dep.id, env["admin"], final_reading="RH 35%", condition_in="good")
    d = _details(env, "equipment", eq.id, "equipment_return")
    assert d["snapshot"] == {"status": EquipmentStatus.AVAILABLE, "current_project_id": None}
    dr = d["side_effects"]["deployment_returned"]
    assert dr["deployment_id"] == dep.id
    dcf = dr["changed_fields"]
    assert {"returned_at", "condition_in", "final_reading"} <= set(dcf)
    assert dcf["final_reading"]["new"] == "RH 35%"


# ===========================================================================
# 3. NEW-313 COALESCE regression -- omitted field ABSENT from changed_fields
# ===========================================================================

def test_new313_dispatch_instructions_omitted_absent(env):
    p = _mk_project(env)
    wo = _mk_wo(env, p.id)
    sub = _mk_sub(env)
    env["ops"].dispatch_work_order(wo.id, sub.id, env["admin"])  # no instructions
    cf = _details(env, "work_order", wo.id, "work_order_dispatch")["changed_fields"]
    assert "instructions" not in cf


def test_new313_dispatch_instructions_empty_string_recorded(env):
    p = _mk_project(env)
    wo = _mk_wo(env, p.id)
    sub = _mk_sub(env)
    env["ops"].dispatch_work_order(wo.id, sub.id, env["admin"], instructions="")
    cf = _details(env, "work_order", wo.id, "work_order_dispatch")["changed_fields"]
    assert cf["instructions"]["new"] == ""


def test_new313_accept_notes_omitted_absent(env):
    p = _mk_project(env)
    wo = _dispatched_wo(env, p.id)
    env["ops"].accept_work_order(wo.id, env["admin"])  # no notes
    cf = _details(env, "work_order", wo.id, "work_order_accept")["changed_fields"]
    assert "notes" not in cf


def test_new313_execution_status_notes_omitted_absent(env):
    p = _mk_project(env)
    wo = _dispatched_wo(env, p.id)
    env["ops"].accept_work_order(wo.id, env["admin"])
    env["ops"].update_work_order_execution_status(wo.id, WorkOrderStatus.IN_PROGRESS, env["admin"])
    cf = _details(env, "work_order", wo.id, "status_change")["changed_fields"]
    assert "notes" not in cf


def test_new313_milestone_notes_omitted_absent(env):
    p = _mk_project(env)
    m = env["ops"].create_milestone(
        ProjectMilestone(project_id=p.id, name="M", stage=ProjectStage.INTAKE,
                         status=MilestoneStatus.PENDING, notes="orig"),
        env["admin"],
    )
    env["ops"].update_milestone_status(m.id, MilestoneStatus.IN_PROGRESS, env["admin"])  # no notes
    cf = _details(env, "milestone", m.id, "status_change")["changed_fields"]
    assert "notes" not in cf


def test_new313_transition_notes_omitted_absent(env):
    p = _mk_project(env, notes="orig note")
    env["ops"].transition_project_stage(p.id, ProjectStage.ASSESSMENT_SCOPING, env["admin"])
    cf = _details(env, "project", p.id, "project_stage_transition")["changed_fields"]
    assert "notes" not in cf


# ===========================================================================
# 4. side_effects content
# ===========================================================================

def test_se_transition_default_milestones_flag_not_dicts(env):
    p = _mk_project(env)
    env["ops"].transition_project_stage(p.id, ProjectStage.ASSESSMENT_SCOPING, env["admin"])
    d = _details(env, "project", p.id, "project_stage_transition")
    assert d["side_effects"] == {"default_milestones_ensured": True}
    # milestones created as their own rows, not embedded
    mrows = env["audit"].query_logs(env["admin"], entity_type="milestone", action="create", limit=50)
    assert len(mrows) >= 1
    assert "Initial Site Inspection" not in json.dumps(d)


def test_se_transition_cancelled_reason(env):
    p = _mk_project(env)
    env["ops"].transition_project_stage(
        p.id, ProjectStage.CANCELLED, env["admin"], reason="customer terminated"
    )
    d = _details(env, "project", p.id, "project_stage_transition")
    assert d["side_effects"]["transition_reason"] == "customer terminated"


def test_se_transition_no_reason_no_side_effects(env):
    p = _mk_project(env)
    env["ops"].transition_project_stage(p.id, ProjectStage.ON_HOLD, env["admin"])
    d = _details(env, "project", p.id, "project_stage_transition")
    assert "side_effects" not in d


def test_se_dispatch_compliance_overridden(env):
    p = _mk_project(env)
    wo = _mk_wo(env, p.id)
    sub = _mk_sub(env, coi_expiration="2020-01-01", license_number="LIC-1")
    env["ops"].dispatch_work_order(wo.id, sub.id, env["admin"], override_compliance=True)
    d = _details(env, "work_order", wo.id, "work_order_dispatch")
    assert d["side_effects"]["compliance_overridden"] is True


def test_se_dispatch_override_but_nothing_bypassed_no_key(env):
    """override_compliance=True but the sub is fully compliant, so no check was
    actually bypassed -> compliance_overridden key must be absent."""
    p = _mk_project(env)
    wo = _mk_wo(env, p.id)
    sub = _mk_sub(env)
    env["ops"].dispatch_work_order(wo.id, sub.id, env["admin"], override_compliance=True)
    d = _details(env, "work_order", wo.id, "work_order_dispatch")
    assert "side_effects" not in d


def test_se_dispatch_license_bypass_sets_flag(env):
    """The license branch now runs even under override; the raise is preserved
    without override and the flag is set with it."""
    p = _mk_project(env)
    wo = _mk_wo(env, p.id)
    sub = _mk_sub(env, license_required=1, license_status="expired", license_number=None)
    with pytest.raises(ValueError, match="license is not active"):
        env["ops"].dispatch_work_order(wo.id, sub.id, env["admin"])
    env["ops"].dispatch_work_order(wo.id, sub.id, env["admin"], override_compliance=True)
    d = _details(env, "work_order", wo.id, "work_order_dispatch")
    assert d["side_effects"]["compliance_overridden"] is True


def test_se_deploy_equipment_deployment_created(env):
    p = _mk_project(env)
    eq = _mk_equipment(env)
    wo = _mk_wo(env, p.id)
    dep = env["ops"].deploy_equipment(
        eq.id, p.id, env["admin"], work_order_id=wo.id,
        initial_reading="RH 80%", condition_out="good", return_due_at="2026-10-01",
    )
    dc = _details(env, "equipment", eq.id, "equipment_deploy")["side_effects"]["deployment_created"]
    assert dc["deployment_id"] == dep.id
    assert dc["project_id"] == p.id
    assert dc["work_order_id"] == wo.id
    assert dc["condition_out"] == "good"
    assert dc["initial_reading"] == "RH 80%"


# ===========================================================================
# 5. no-op / deliberate-write pins
# ===========================================================================

def test_transition_target_equals_current_no_row(env):
    p = _mk_project(env)
    env["ops"].transition_project_stage(p.id, ProjectStage.INTAKE, env["admin"])
    assert _rows(env, "project", p.id, "project_stage_transition") == []


def test_update_milestone_same_status_still_writes_row(env):
    """update_milestone_status has no _meaningful gate: a same-status call
    deliberately still writes an audit row (updated_at moves)."""
    p = _mk_project(env)
    m = env["ops"].create_milestone(
        ProjectMilestone(project_id=p.id, name="M", stage=ProjectStage.INTAKE,
                         status=MilestoneStatus.PENDING),
        env["admin"],
    )
    env["ops"].update_milestone_status(m.id, MilestoneStatus.PENDING, env["admin"])
    cf = _details(env, "milestone", m.id, "status_change")["changed_fields"]
    assert set(cf) == {"updated_at"}


# ===========================================================================
# 6. drift guards
# ===========================================================================

def test_drift_work_order_fields():
    assert _AUDITABLE_WORK_ORDER_FIELDS == frozenset(WorkOrder().to_dict().keys())


def test_drift_milestone_fields():
    assert _AUDITABLE_MILESTONE_FIELDS == frozenset(ProjectMilestone().to_dict().keys())


def test_drift_equipment_fields():
    assert _AUDITABLE_EQUIPMENT_FIELDS == frozenset(Equipment().to_dict().keys())


def test_drift_deployment_fields():
    assert _AUDITABLE_DEPLOYMENT_FIELDS == frozenset(EquipmentDeployment().to_dict().keys())


# ===========================================================================
# 7. secret / out-of-domain key sweep
# ===========================================================================

@pytest.mark.parametrize("scenario", [
    "transition", "milestone", "update_wo", "dispatch", "accept",
    "exec_status", "deploy", "return",
])
def test_no_out_of_domain_keys(env, scenario):
    p = _mk_project(env)
    if scenario == "transition":
        env["ops"].transition_project_stage(p.id, ProjectStage.ASSESSMENT_SCOPING, env["admin"])
    elif scenario == "milestone":
        m = env["ops"].create_milestone(
            ProjectMilestone(project_id=p.id, name="M", stage=ProjectStage.INTAKE,
                             status=MilestoneStatus.PENDING),
            env["admin"],
        )
        env["ops"].update_milestone_status(m.id, MilestoneStatus.IN_PROGRESS, env["admin"])
    elif scenario == "update_wo":
        wo = _mk_wo(env, p.id)
        env["ops"].update_work_order(wo, env["admin"])
    elif scenario == "dispatch":
        _dispatched_wo(env, p.id)
    elif scenario == "accept":
        wo = _dispatched_wo(env, p.id)
        env["ops"].accept_work_order(wo.id, env["admin"])
    elif scenario == "exec_status":
        wo = _dispatched_wo(env, p.id)
        env["ops"].accept_work_order(wo.id, env["admin"])
        env["ops"].update_work_order_execution_status(wo.id, WorkOrderStatus.IN_PROGRESS, env["admin"])
    elif scenario == "deploy":
        eq = _mk_equipment(env)
        env["ops"].deploy_equipment(eq.id, p.id, env["admin"])
    elif scenario == "return":
        eq = _mk_equipment(env)
        dep = env["ops"].deploy_equipment(eq.id, p.id, env["admin"])
        env["ops"].return_equipment(dep.id, env["admin"])

    allow = (
        _AUDITABLE_PROJECT_FIELDS | _AUDITABLE_MILESTONE_FIELDS
        | _AUDITABLE_WORK_ORDER_FIELDS | _AUDITABLE_EQUIPMENT_FIELDS
        | {"status", "current_project_id"}  # scoped snapshots
    )
    # only the 8 operations_service real-update sites under test
    site_actions = {
        "project_stage_transition", "status_change", "update",
        "work_order_dispatch", "work_order_accept",
        "equipment_deploy", "equipment_return",
    }
    conn = env["db"].get_connection()
    rows = conn.execute(
        "SELECT action, details_json FROM audit_log WHERE entity_type IN ('project','milestone','work_order','equipment')"
    ).fetchall()
    for r in rows:
        if r["action"] not in site_actions:
            continue
        d = json.loads(r["details_json"])
        for slot in ("changed_fields", "snapshot"):
            for k in d.get(slot, {}):
                assert k in allow, f"{scenario}: unexpected {slot} key {k!r}"


# ===========================================================================
# 8. after-image Optional-guard (counting monkeypatch: first call real, rest None)
# ===========================================================================

def _count_patch(monkeypatch, obj, name):
    real = getattr(obj, name)
    state = {"n": 0}

    def fake(*a, **k):
        state["n"] += 1
        return real(*a, **k) if state["n"] == 1 else None

    monkeypatch.setattr(obj, name, fake)


def test_guard_dispatch_after_none(env, monkeypatch):
    p = _mk_project(env)
    wo = _mk_wo(env, p.id)
    sub = _mk_sub(env)
    _count_patch(monkeypatch, env["ops"], "get_work_order")
    env["ops"].dispatch_work_order(wo.id, sub.id, env["admin"])
    d = _details(env, "work_order", wo.id, "work_order_dispatch")
    assert "changed_fields" in d  # before-only diff still recorded


def test_guard_accept_after_none(env, monkeypatch):
    p = _mk_project(env)
    wo = _dispatched_wo(env, p.id)
    _count_patch(monkeypatch, env["ops"], "get_work_order")
    env["ops"].accept_work_order(wo.id, env["admin"])
    assert _rows(env, "work_order", wo.id, "work_order_accept")


def test_guard_exec_status_after_none(env, monkeypatch):
    p = _mk_project(env)
    wo = _dispatched_wo(env, p.id)
    env["ops"].accept_work_order(wo.id, env["admin"])
    _count_patch(monkeypatch, env["ops"], "get_work_order")
    env["ops"].update_work_order_execution_status(wo.id, WorkOrderStatus.IN_PROGRESS, env["admin"])
    assert _rows(env, "work_order", wo.id, "status_change")


def test_guard_deploy_after_none(env, monkeypatch):
    p = _mk_project(env)
    eq = _mk_equipment(env)
    _count_patch(monkeypatch, env["ops"], "get_equipment")
    env["ops"].deploy_equipment(eq.id, p.id, env["admin"])
    d = _details(env, "equipment", eq.id, "equipment_deploy")
    assert "side_effects" in d  # deployment_created still recorded


def test_guard_milestone_after_none(env, monkeypatch):
    p = _mk_project(env)
    m = env["ops"].create_milestone(
        ProjectMilestone(project_id=p.id, name="M", stage=ProjectStage.INTAKE,
                         status=MilestoneStatus.PENDING),
        env["admin"],
    )
    _count_patch(monkeypatch, env["ops"], "get_milestone")
    env["ops"].update_milestone_status(m.id, MilestoneStatus.IN_PROGRESS, env["admin"])
    assert _rows(env, "milestone", m.id, "status_change")
