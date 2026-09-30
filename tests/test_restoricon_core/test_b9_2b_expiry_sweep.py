"""
Tests for Phase B9.2b -- estimate expiry sweep
(`restoricon_core/services/estimate_service.py`'s `sweep_expired()` and
`restoricon_core/api/expiry_sweep.py`'s `EstimateExpirySweepThread`).

Split the same way `test_b9_4_public_share_link.py` splits its coverage:
service-level (`sweep_expired()` itself, via the plain `env` fixture) and
thread-level (start/stop lifecycle, `run_once()` as the fast/testable
entry point instead of a real hour-long sleep).
"""

import time

import pytest

from restoricon_core.api.expiry_sweep import EstimateExpirySweepThread
from restoricon_core.auth import AuthContext, AuthService, ROLE_ADMIN, ROLE_SALES
from restoricon_core.database import DatabaseManager
from restoricon_core.models import Customer
from restoricon_core.services.audit_service import AuditService
from restoricon_core.services.crm_service import CRMService
from restoricon_core.services.estimate_service import EstimateService

PAST = "2020-01-01T00:00:00+00:00"
FUTURE = "2999-01-01T00:00:00+00:00"


@pytest.fixture
def env():
    db = DatabaseManager(":memory:")
    auth = AuthService(db)
    audit = AuditService(db)
    crm = CRMService(db, audit)
    svc = EstimateService(db, audit)

    admin_user = auth.create_user("admin1", "Pass123!", "Admin One", "admin1@restoricon.com", role=ROLE_ADMIN)
    admin = AuthContext(admin_user.id, admin_user.username, ROLE_ADMIN, "human")

    sales_user = auth.create_user("sales1", "Pass123!", "Sales One", "sales1@restoricon.com", role=ROLE_SALES)
    sales = AuthContext(sales_user.id, sales_user.username, ROLE_SALES, "human")

    customer = crm.create_customer(Customer(first_name="Jane", last_name="Doe"), admin)

    return {"db": db, "svc": svc, "audit": audit, "admin": admin, "sales": sales, "customer_id": customer.id}


def _material_line(**overrides):
    line = {
        "line_type": "material",
        "description": "Drywall sheets",
        "customer_description": "Drywall",
        "quantity": 10,
        "unit": "SF",
        "unit_cost_cents": 1000,
        "package_qty": 1,
    }
    line.update(overrides)
    return line


def _make_estimate(env, expires_at, status):
    """Create a real estimate (with a line, so it can legally reach SENT)
    and force it directly to `status` with `expires_at` via raw SQL --
    same convention `test_b9_2_estimate_service.py`/
    `test_b9_4_public_share_link.py` already use for setting up states
    `transition()`'s own actor-driven table can't reach directly (e.g.
    VIEWED, or a past `expires_at`, which `create()` accepts uncritically
    but the normal send flow never produces)."""
    svc = env["svc"]
    header = svc.create(customer_id=env["customer_id"], actor=env["sales"], expires_at=expires_at)
    svc.add_line(header.id, _material_line(), env["sales"])
    conn = env["db"].get_connection()
    with conn:
        conn.execute(
            "UPDATE estimates SET workflow_status = ?, expires_at = ? WHERE id = ?;",
            (status, expires_at, header.id),
        )
    return header.id


def _audit_rows_for(env, estimate_id):
    """Only 'transition' rows -- create() already writes its own 'create'
    audit row for every estimate this fixture builds, which is not what
    these assertions are about."""
    conn = env["db"].get_connection()
    return conn.execute(
        "SELECT action, change_summary, actor_id, actor_role, actor_type FROM audit_log "
        "WHERE entity_type = 'estimate' AND entity_id = ? AND action = 'transition' ORDER BY id ASC;",
        (estimate_id,),
    ).fetchall()


def _status_of(env, estimate_id):
    row = env["db"].get_connection().execute(
        "SELECT workflow_status FROM estimates WHERE id = ?;", (estimate_id,)
    ).fetchone()
    return row["workflow_status"]


# ------------------------------------------------------------------
# sweep_expired() -- service-level
# ------------------------------------------------------------------

def test_sweep_expires_sent_past_expiry_with_audit_entry(env):
    estimate_id = _make_estimate(env, PAST, "SENT")

    expired_ids = env["svc"].sweep_expired()

    assert expired_ids == [estimate_id]
    assert _status_of(env, estimate_id) == "EXPIRED"
    rows = _audit_rows_for(env, estimate_id)
    assert len(rows) == 1
    assert rows[0]["action"] == "transition"
    assert rows[0]["change_summary"] == "SENT -> EXPIRED"
    # actor=None per AuditService.log()'s own contract -- system-driven,
    # no authenticated caller (matches record_share_link_view()'s VIEWED
    # transition, which uses the identical actor=None convention).
    assert rows[0]["actor_id"] is None
    assert rows[0]["actor_role"] == "system"
    assert rows[0]["actor_type"] == "agent"


def test_sweep_expires_viewed_past_expiry_with_audit_entry(env):
    estimate_id = _make_estimate(env, PAST, "VIEWED")

    expired_ids = env["svc"].sweep_expired()

    assert expired_ids == [estimate_id]
    assert _status_of(env, estimate_id) == "EXPIRED"
    rows = _audit_rows_for(env, estimate_id)
    assert len(rows) == 1
    assert rows[0]["change_summary"] == "VIEWED -> EXPIRED"


@pytest.mark.parametrize(
    "status",
    [
        "DRAFT", "INTERNAL_REVIEW", "APPROVED_INTERNAL", "ACCEPTED", "DECLINED",
        "CHANGES_REQUESTED", "EXPIRED", "CANCELLED", "CONVERTED",
    ],
)
def test_sweep_leaves_other_statuses_untouched_even_with_past_expiry(env, status):
    estimate_id = _make_estimate(env, PAST, status)

    expired_ids = env["svc"].sweep_expired()

    assert expired_ids == []
    assert _status_of(env, estimate_id) == status
    assert _audit_rows_for(env, estimate_id) == []


def test_sweep_leaves_future_expiry_untouched(env):
    estimate_id = _make_estimate(env, FUTURE, "SENT")

    expired_ids = env["svc"].sweep_expired()

    assert expired_ids == []
    assert _status_of(env, estimate_id) == "SENT"
    assert _audit_rows_for(env, estimate_id) == []


def test_sweep_one_bad_row_does_not_abort_the_rest_of_the_batch(env, monkeypatch):
    """Simulate a row that raises mid-transition (audit.log() blowing up
    for one specific estimate) and confirm the OTHER candidate in the same
    pass still gets transitioned -- the row-level try/except in
    sweep_expired()'s docstring. The bad row itself must be left
    completely untouched (still its original status, no audit row) --
    the status UPDATE and its audit.log() call share one `with conn:`
    block specifically so a failing audit write rolls the status change
    back with it, rather than leaving a committed-but-unaudited EXPIRED
    row (which would violate §9 item 3's per-row-audit requirement just
    as much as a bulk silent update would)."""
    bad_id = _make_estimate(env, PAST, "SENT")
    good_id = _make_estimate(env, PAST, "VIEWED")

    real_log = env["audit"].log

    def flaky_log(*args, **kwargs):
        if kwargs.get("entity_id") == bad_id:
            raise RuntimeError("simulated audit failure for bad row")
        return real_log(*args, **kwargs)

    monkeypatch.setattr(env["audit"], "log", flaky_log)

    expired_ids = env["svc"].sweep_expired()

    assert expired_ids == [good_id]
    assert _status_of(env, good_id) == "EXPIRED"
    assert _audit_rows_for(env, good_id)[0]["change_summary"] == "VIEWED -> EXPIRED"

    # The bad row's failing audit call rolled its status UPDATE back too --
    # still SENT, not silently EXPIRED-with-no-audit-trail. It will be
    # picked back up and retried on the next sweep tick.
    assert bad_id not in expired_ids
    assert _status_of(env, bad_id) == "SENT"
    assert _audit_rows_for(env, bad_id) == []


# ------------------------------------------------------------------
# EstimateExpirySweepThread -- lifecycle
# ------------------------------------------------------------------

def test_run_once_triggers_a_real_sweep_pass_without_waiting_on_the_interval(env):
    estimate_id = _make_estimate(env, PAST, "SENT")
    thread = EstimateExpirySweepThread(env["svc"], interval_s=3600.0)

    expired_ids = thread.run_once()

    assert expired_ids == [estimate_id]
    assert _status_of(env, estimate_id) == "EXPIRED"


def test_thread_starts_and_stops_cleanly(env):
    # Fast interval so the loop actually completes at least one tick
    # during this test without a real hour-long wait.
    thread = EstimateExpirySweepThread(env["svc"], interval_s=0.05)
    estimate_id = _make_estimate(env, PAST, "SENT")

    thread.start()
    try:
        deadline = time.monotonic() + 5.0
        while _status_of(env, estimate_id) != "EXPIRED" and time.monotonic() < deadline:
            time.sleep(0.02)
        assert _status_of(env, estimate_id) == "EXPIRED"
    finally:
        thread.stop(timeout=5.0)

    assert thread._thread is not None
    assert not thread._thread.is_alive()


def test_thread_start_twice_is_a_no_op(env):
    thread = EstimateExpirySweepThread(env["svc"], interval_s=3600.0)
    thread.start()
    first_thread_obj = thread._thread
    try:
        thread.start()
        assert thread._thread is first_thread_obj
    finally:
        thread.stop(timeout=5.0)


def test_thread_stop_without_start_does_not_raise(env):
    thread = EstimateExpirySweepThread(env["svc"], interval_s=3600.0)
    thread.stop(timeout=1.0)  # no-op, must not raise


def test_thread_loop_survives_sweep_expired_raising(env, monkeypatch):
    """Tick-level isolation: sweep_expired() itself raising must not kill
    the thread -- it should just log and retry on the next tick."""
    call_count = {"n": 0}
    real_sweep = env["svc"].sweep_expired

    def flaky_sweep():
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("simulated sweep-level failure")
        return real_sweep()

    monkeypatch.setattr(env["svc"], "sweep_expired", flaky_sweep)

    estimate_id = _make_estimate(env, PAST, "SENT")
    thread = EstimateExpirySweepThread(env["svc"], interval_s=0.05)
    thread.start()
    try:
        deadline = time.monotonic() + 5.0
        while call_count["n"] < 2 and time.monotonic() < deadline:
            time.sleep(0.02)
        assert call_count["n"] >= 2  # thread survived the first raise and ticked again
    finally:
        thread.stop(timeout=5.0)
