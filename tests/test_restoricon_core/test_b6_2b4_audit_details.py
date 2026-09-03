"""
B6.2b-4 (final round): migrate the last 11 service-layer ``audit.log()`` sites
onto the canonical ``build_audit_details`` envelope.

Sites:
  scheduling_service.py
    3.1  update_appointment_status  (action="status_change")  -- C-none snapshot
    3.2  update_appointment         (action="update")         -- before/after diff
    3.3  upsert_schedule_config     (action="update")         -- snapshot (singleton upsert)
  automation_service.py
    3.4  upsert_business_profile    (action="update")         -- snapshot (singleton upsert)
    3.5  add_to_do_not_contact      (action="create")         -- canonical create (after=)
  business_ops_service.py
    3.6  submit_review              (action="submit_review")  -- before/after diff
    3.7  receive_purchase_order     (action="update")         -- before/after diff (gains details=)
  crm_service.py
    3.8  update_contact             (action="update")         -- before/after diff
    3.9  sync_contacts_batch        (action="update")         -- side_effects (bulk)
    3.10 submit_public_lead         (action="submit")         -- after= + side_effects
    3.11 submit_public_booking      (action="submit")         -- side_effects only

Real DatabaseManager(":memory:") / AuthService / AuditService + services, admin
AuthContext, no mocks. Payloads read back via query_logs(...).details /
details_json from the persisted audit_log, never the audit.log() return.
"""

import pytest

from restoricon_core.auth import AuthService, ROLE_ADMIN
from restoricon_core.database import DatabaseManager
from restoricon_core.models import (
    Appointment,
    BusinessProfile,
    Contact,
    Customer,
    PurchaseOrder,
    ReviewRequest,
    ScheduleConfig,
    Vendor,
)
from restoricon_core.services.audit_service import (
    AuditService,
    build_audit_details,
    _AUDITABLE_APPOINTMENT_FIELDS,
    _AUDITABLE_CONTACT_FIELDS,
    _AUDITABLE_PURCHASE_ORDER_FIELDS,
    _AUDITABLE_REVIEW_REQUEST_FIELDS,
)
from restoricon_core.services.automation_service import AutomationService
from restoricon_core.services.business_ops_service import BusinessOpsService
from restoricon_core.services.crm_service import CRMService
from restoricon_core.services.scheduling_service import SchedulingService


@pytest.fixture
def env():
    db = DatabaseManager(":memory:")
    auth = AuthService(db)
    audit = AuditService(db)
    crm = CRMService(db, audit)
    sched = SchedulingService(db, audit)
    auto = AutomationService(db, audit)
    ops = BusinessOpsService(db, audit)
    admin = auth.create_user("admin_u", "AdminPass123!", "Admin U", "admin@r.com", role=ROLE_ADMIN)
    ctx = auth.authenticate_token(auth.create_token(admin))
    cust = crm.create_customer(Customer(first_name="P", last_name="Co"), ctx)
    return {
        "db": db, "auth": auth, "audit": audit, "crm": crm, "sched": sched,
        "auto": auto, "ops": ops, "admin": ctx, "cust_id": cust.id,
    }


def _details(env, entity_type, action, entity_id=None):
    rows = env["audit"].query_logs(
        env["admin"], entity_type=entity_type, entity_id=entity_id, action=action, limit=100
    )
    assert rows, f"no audit row for {entity_type}/{action}"
    return rows[0].details


def _all_raw(env):
    conn = env["db"].get_connection()
    return [r["details_json"] for r in conn.execute("SELECT details_json FROM audit_log").fetchall()]


# --------------------------------------------------------------------------
# builders exercising every site once
# --------------------------------------------------------------------------

def _mk_appt(env, **kw):
    kw.setdefault("title", "Consult")
    kw.setdefault("status", "negotiating")
    kw.setdefault("customer_id", env["cust_id"])
    return env["sched"].create_appointment(Appointment(**kw), env["admin"])


def _mk_contact(env, **kw):
    kw.setdefault("external_id", "c_1")
    kw.setdefault("name", "Jane Doe")
    return env["crm"].create_contact(Contact(**kw), env["admin"])


def _mk_vendor(env):
    return env["ops"].create_vendor(Vendor(company_name="Ace Supply"), env["admin"])


def _mk_po(env):
    v = _mk_vendor(env)
    po = PurchaseOrder(vendor_id=v.id, total_amount=100.0)
    return env["ops"].create_purchase_order(po, env["admin"])


# --------------------------------------------------------------------------
# 1. per-site envelope shape
# --------------------------------------------------------------------------

def test_3_1_update_appointment_status_snapshot(env):
    a = _mk_appt(env)
    env["sched"].update_appointment_status(a.id, "confirmed", env["admin"])
    d = _details(env, "appointment", "status_change", a.id)
    assert d == {"snapshot": {"status": "confirmed"}}


def test_3_2_update_appointment_diff(env):
    a = _mk_appt(env, title="Old")
    env["sched"].update_appointment(a.id, {"title": "New", "notes": "hi"}, env["admin"])
    d = _details(env, "appointment", "update", a.id)
    assert set(d["changed_fields"]) == {"title", "notes", "updated_at"}
    assert d["changed_fields"]["title"] == {"old": "Old", "new": "New"}
    assert "side_effects" not in d
    assert "snapshot" not in d


def test_3_3_upsert_schedule_config_snapshot(env):
    cfg = ScheduleConfig(working_hours={"mon": {"start": "09:00", "end": "17:00"}})
    env["sched"].upsert_schedule_config(cfg, env["admin"])
    d = _details(env, "schedule_config", "update", 1)
    assert d["snapshot"] == cfg.to_dict()
    assert "changed_fields" not in d


def test_3_4_upsert_business_profile_snapshot(env):
    p = BusinessProfile(business_name="Restoricon", owner_name="Ish")
    env["auto"].upsert_business_profile(p, env["admin"])
    d = _details(env, "business_profile", "update", 1)
    assert d["snapshot"] == p.to_dict()
    assert "changed_fields" not in d


def test_3_5_add_to_do_not_contact_create(env):
    entry = env["auto"].add_to_do_not_contact("spam@bad.com", env["admin"], reason="asked")
    d = _details(env, "do_not_contact", "create", entry.id)
    cf = d["changed_fields"]
    # canonical create shape: every field {"old": None, "new": v}
    for k, v in cf.items():
        assert v["old"] is None
    assert cf["value"]["new"] == "spam@bad.com"
    assert "snapshot" not in d
    assert "side_effects" not in d


def test_3_6_submit_review_diff(env):
    req = env["ops"].create_review_request(
        ReviewRequest(customer_id=env["cust_id"], platform="google"), env["admin"]
    )
    env["ops"].submit_review(req.id, 4, "great", env["admin"])
    d = _details(env, "review_request", "submit_review", req.id)
    cf = d["changed_fields"]
    assert set(cf) == {"rating", "feedback", "status", "completed_at"}
    assert cf["rating"] == {"old": None, "new": 4}
    assert cf["feedback"] == {"old": None, "new": "great"}
    assert cf["status"] == {"old": "sent", "new": "completed"}
    assert cf["completed_at"]["old"] is None
    assert cf["completed_at"]["new"] is not None
    assert "side_effects" not in d


def test_3_7_receive_purchase_order_diff(env):
    po = _mk_po(env)
    env["ops"].receive_purchase_order(po.id, env["admin"])
    d = _details(env, "purchase_order", "update", po.id)
    cf = d["changed_fields"]
    assert set(cf) == {"status", "received_date", "updated_at"}
    assert cf["status"] == {"old": "draft", "new": "received"}
    assert cf["received_date"]["old"] is None
    assert cf["received_date"]["new"] is not None
    assert "side_effects" not in d


def test_3_8_update_contact_diff(env):
    c = _mk_contact(env, name="Old Name")
    env["crm"].update_contact(c.id, {"name": "New Name", "notes": "vip"}, env["admin"])
    d = _details(env, "contact", "update", c.id)
    assert set(d["changed_fields"]) == {"name", "notes", "updated_at"}
    assert d["changed_fields"]["name"] == {"old": "Old Name", "new": "New Name"}


def test_3_9_sync_contacts_batch_side_effects(env):
    res = env["crm"].sync_contacts_batch(
        [Contact(external_id="a_1", name="Andy", phones=["5551112222"])], env["admin"]
    )
    d = _details(env, "contact", "update", None)
    assert d["side_effects"] == {
        "android": 1, "added": res["added"], "updated": res["updated"], "total": res["total"],
    }
    assert "changed_fields" not in d


def test_3_10_submit_public_lead_after_and_side_effects(env):
    res = env["crm"].submit_public_lead({"name": "Web Lead", "email": "w@l.com", "description": "flood"})
    d = _details(env, "lead", "submit", res["lead_id"])
    assert d["changed_fields"]["id"] == {"old": None, "new": res["lead_id"]}
    se = d["side_effects"]
    assert set(se) == {"customer_id", "opportunity_id", "score"}
    assert se["customer_id"] == res["customer_id"]
    assert se["opportunity_id"] == res["opportunity_id"]
    assert isinstance(se["score"], dict) and "score" in se["score"]


def test_3_11_submit_public_booking_side_effects_only(env):
    res = env["crm"].submit_public_booking({"name": "Book Me", "email": "b@m.com", "preferred_date": "2026-10-01"})
    d = _details(env, "appointment", "submit", res["appointment_id"])
    assert d == {"side_effects": {
        "appointment_id": res["appointment_id"], "customer_id": res["customer_id"],
    }}


# --------------------------------------------------------------------------
# 2. action / change_summary byte-identical (persisted values)
# --------------------------------------------------------------------------

def test_action_and_change_summary_unchanged(env):
    a = _mk_appt(env, title="T")
    env["sched"].update_appointment_status(a.id, "confirmed", env["admin"])
    env["sched"].update_appointment(a.id, {"notes": "n"}, env["admin"])
    env["sched"].upsert_schedule_config(ScheduleConfig(), env["admin"])
    env["auto"].upsert_business_profile(BusinessProfile(business_name="R"), env["admin"])
    dnc = env["auto"].add_to_do_not_contact("x@y.com", env["admin"])
    req = env["ops"].create_review_request(ReviewRequest(customer_id=env["cust_id"]), env["admin"])
    env["ops"].submit_review(req.id, 3, "ok", env["admin"])
    po = _mk_po(env)
    env["ops"].receive_purchase_order(po.id, env["admin"])
    c = _mk_contact(env, name="N")
    env["crm"].update_contact(c.id, {"notes": "z"}, env["admin"])
    env["crm"].sync_contacts_batch([Contact(external_id="s_1", name="S")], env["admin"])
    lead = env["crm"].submit_public_lead({"name": "L", "description": "d"})
    booking = env["crm"].submit_public_booking({"name": "B", "preferred_date": "2026-10-02"})

    conn = env["db"].get_connection()
    seen = {
        (r["action"], r["change_summary"])
        for r in conn.execute("SELECT action, change_summary FROM audit_log").fetchall()
    }
    expected = {
        ("status_change", f"Appointment {a.id} status set to 'confirmed'"),
        ("update", f"Updated appointment {a.id}"),
        ("update", "Schedule config updated"),
        ("update", "Business profile updated"),
        ("create", f"Added email to do-not-contact: {dnc.value}"),
        ("submit_review", f"Submitted review for request {req.id} (rating 3)"),
        ("update", f"Received PO #{po.po_number}"),
        ("update", f"Contact {c.id} updated (notes)"),
        ("update", "Synced batch of 1 contacts (added: 1, updated: 0)"),
        ("submit", f"Inbound website lead from L (Score: {lead['score']})"),
        ("submit", f"Inbound booking request from B for 2026-10-02"),
    }
    missing = expected - seen
    assert not missing, missing


# --------------------------------------------------------------------------
# 3. NEW-312 remedy: None post-commit re-read must not raise
# --------------------------------------------------------------------------

class _EmptyResult:
    """Wraps a real cursor but forces fetchone()/fetchall() empty."""

    def __init__(self, cur):
        self._cur = cur

    def fetchone(self):
        return None

    def fetchall(self):
        return []

    def __iter__(self):
        return iter(())

    def __getattr__(self, name):
        return getattr(self._cur, name)


class _ConnProxy:
    """Delegates to a real sqlite3 connection but returns an empty result
    for the Nth call whose SQL contains `drop_marker` -- simulating a
    post-commit re-read that finds the row gone."""

    def __init__(self, real, drop_marker, drop_on_hit):
        self._real = real
        self._marker = drop_marker
        self._target = drop_on_hit
        self._hits = 0

    def __getattr__(self, name):
        return getattr(self._real, name)

    def __enter__(self):
        self._real.__enter__()
        return self

    def __exit__(self, *exc):
        return self._real.__exit__(*exc)

    def execute(self, sql, *args, **kw):
        cur = self._real.execute(sql, *args, **kw)
        if self._marker in sql:
            self._hits += 1
            if self._hits == self._target:
                return _EmptyResult(cur)
        return cur


def test_new312_update_appointment_after_read_none(env, monkeypatch):
    a = _mk_appt(env, title="Base")
    real_conn = env["db"].get_connection()
    proxy = _ConnProxy(real_conn, "FROM appointments WHERE id = ?", drop_on_hit=2)
    monkeypatch.setattr(env["db"], "get_connection", lambda: proxy)

    env["sched"].update_appointment(a.id, {"title": "X"}, env["admin"])

    monkeypatch.undo()
    d = _details(env, "appointment", "update", a.id)
    assert d["changed_fields"]["title"] == {"old": "Base", "new": None}


def test_new312_update_contact_after_read_none(env, monkeypatch):
    c = _mk_contact(env, name="Base")
    real_conn = env["db"].get_connection()
    proxy = _ConnProxy(real_conn, "FROM contacts WHERE id = ?", drop_on_hit=2)
    monkeypatch.setattr(env["db"], "get_connection", lambda: proxy)

    env["crm"].update_contact(c.id, {"name": "X"}, env["admin"])

    monkeypatch.undo()
    d = _details(env, "contact", "update", c.id)
    assert d["changed_fields"]["name"] == {"old": "Base", "new": None}


def test_phantom_diff_appointment_json_column(env):
    slots = [{"date": "2026-10-01", "slot": "am"}]
    a = _mk_appt(env, offered_slots=slots)
    # re-set the SAME value -> stored normalized form must equal before -> no entry
    env["sched"].update_appointment(a.id, {"offered_slots": slots}, env["admin"])
    d = _details(env, "appointment", "update", a.id)
    assert "offered_slots" not in d.get("changed_fields", {})


def test_phantom_diff_contact_json_column(env):
    c = _mk_contact(env, phones=["5551110000"])
    env["crm"].update_contact(c.id, {"phones": ["5551110000"]}, env["admin"])
    d = _details(env, "contact", "update", c.id)
    assert "phones" not in d.get("changed_fields", {})


# --------------------------------------------------------------------------
# 6. drift guards
# --------------------------------------------------------------------------

def test_drift_contact_fields():
    assert _AUDITABLE_CONTACT_FIELDS == set(Contact().to_dict()) - {"license_number", "references"}


def test_drift_appointment_fields():
    assert _AUDITABLE_APPOINTMENT_FIELDS == set(Appointment().to_dict())


def test_drift_review_request_fields():
    assert _AUDITABLE_REVIEW_REQUEST_FIELDS == set(ReviewRequest().to_dict())


def test_drift_purchase_order_fields():
    assert _AUDITABLE_PURCHASE_ORDER_FIELDS == set(PurchaseOrder().to_dict())


# --------------------------------------------------------------------------
# 7. negative control: the fields= filter is what strips license_number/references
# --------------------------------------------------------------------------

def test_negative_control_contact_filter():
    c = Contact(external_id="c", name="N")
    before = c.to_dict()
    after = dict(before)
    after["license_number"] = "LIC-999"
    after["references"] = [{"name": "Ref", "phone": "5550000000"}]
    after["name"] = "N2"

    unfiltered = build_audit_details(before=before, after=after)
    assert "license_number" in unfiltered["changed_fields"]
    assert "references" in unfiltered["changed_fields"]

    filtered = build_audit_details(before=before, after=after, fields=_AUDITABLE_CONTACT_FIELDS)
    assert "license_number" not in filtered["changed_fields"]
    assert "references" not in filtered["changed_fields"]
    assert "name" in filtered["changed_fields"]


# --------------------------------------------------------------------------
# 8. secret-leak sweep over the persisted audit_log for all 11 sites
# --------------------------------------------------------------------------

def test_no_secret_leaks_all_sites(env):
    a = _mk_appt(env, title="T")
    env["sched"].update_appointment_status(a.id, "confirmed", env["admin"])
    env["sched"].update_appointment(a.id, {"notes": "n"}, env["admin"])
    env["sched"].upsert_schedule_config(ScheduleConfig(), env["admin"])
    env["auto"].upsert_business_profile(BusinessProfile(business_name="R"), env["admin"])
    env["auto"].add_to_do_not_contact("x@y.com", env["admin"])
    req = env["ops"].create_review_request(ReviewRequest(customer_id=env["cust_id"]), env["admin"])
    env["ops"].submit_review(req.id, 3, "ok", env["admin"])
    po = _mk_po(env)
    env["ops"].receive_purchase_order(po.id, env["admin"])
    c = _mk_contact(env, name="N", license_number="LIC-1", references=[{"name": "R", "phone": "5550000000"}])
    env["crm"].update_contact(
        c.id, {"notes": "z", "license_number": "LIC-2", "references": [{"name": "R2", "phone": "5551111111"}]},
        env["admin"],
    )
    env["crm"].sync_contacts_batch([Contact(external_id="s_1", name="S")], env["admin"])
    env["crm"].submit_public_lead({"name": "L", "description": "d"})
    env["crm"].submit_public_booking({"name": "B", "preferred_date": "2026-10-02"})

    for raw in _all_raw(env):
        assert raw is not None
        low = raw.lower()
        assert "password" not in low
        assert "secret" not in low
        assert '"token"' not in low

    # the contact update payload specifically must not carry the credential /
    # third-party reference list
    d = _details(env, "contact", "update", c.id)
    assert "license_number" not in d["changed_fields"]
    assert "references" not in d["changed_fields"]
