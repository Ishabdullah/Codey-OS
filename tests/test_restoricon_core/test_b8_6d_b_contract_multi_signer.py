"""
Unit/integration tests for B8.6d-b: multi-party contract signer model
(new `contract_signers` table + `ContractSigner` model + the additive
multi-party branch in CRMService.sign_contract/add_contract_signers).

Covers:
  - A contract with zero contract_signers rows behaves byte-for-byte like
    today's single-signer sign_contract (see also
    test_b8_6d_a_contract_pdf.py and test_services.py's NEW-573/575
    regression tests, all still passing unchanged).
  - add_contract_signers opts a contract into multi-party signing.
  - Each required signer can sign independently (via explicit party_role,
    or derived from actor.role when omitted); the contract only reaches
    status "signed" once every required signer has signed.
  - A signer who already signed cannot sign again (idempotent-refusal,
    same ValueError shape as the single-signer guard).
  - The regenerated PDF draws each signer's signature at their own
    anchor position, not all stacked at one spot.
"""

from __future__ import annotations

import base64
import io
import sqlite3

import pytest
from PIL import Image

from restoricon_core.auth import (
    AuthContext,
    AuthService,
    ROLE_ADMIN,
    ROLE_CUSTOMER,
    ROLE_PROJECT_MANAGER,
    ROLE_SALES,
)
from restoricon_core.database import DatabaseManager
from restoricon_core.models import Contract, Customer
from restoricon_core.services.audit_service import AuditService
from restoricon_core.services.crm_service import CRMService
from restoricon_core.services import pdf_service


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
    crm = CRMService(db, audit_service)
    auth_service = AuthService(db)

    admin_user = auth_service.create_user(
        username="msigner_admin", plain_password="Password123", full_name="Admin",
        email="msigner_admin@test.com", role=ROLE_ADMIN,
    )
    actor_admin = AuthContext(user_id=admin_user.id, username="msigner_admin", role=ROLE_ADMIN, actor_type="human")

    cust = crm.create_customer(
        Customer(first_name="Multi", last_name="Signer", email="multi_signer@test.com"), actor_admin,
    )
    customer_user = auth_service.create_user(
        username="msigner_cust", plain_password="Password123", full_name="Multi Signer",
        email="msigner_cust_login@test.com", role=ROLE_CUSTOMER, customer_id=cust.id,
    )
    actor_customer = AuthContext(
        user_id=customer_user.id, username="msigner_cust", role=ROLE_CUSTOMER,
        actor_type="human", customer_id=cust.id,
    )

    pm_user = auth_service.create_user(
        username="msigner_pm", plain_password="Password123", full_name="PM",
        email="msigner_pm@test.com", role=ROLE_PROJECT_MANAGER,
    )
    actor_pm = AuthContext(user_id=pm_user.id, username="msigner_pm", role=ROLE_PROJECT_MANAGER, actor_type="human")

    return {
        "db": db, "crm": crm, "audit": audit_service, "auth": auth_service,
        "admin": actor_admin, "cust": cust, "actor_customer": actor_customer, "actor_pm": actor_pm,
    }


def _make_contract(env, number):
    return env["crm"].create_contract(
        Contract(contract_number=number, customer_id=env["cust"].id, title="Multi-Party Contract", content="Terms..."),
        env["admin"],
    )


# ---------------------------------------------------------------------------
# Backward compatibility: no contract_signers rows -> legacy single-signer path
# ---------------------------------------------------------------------------

def test_sign_contract_without_required_signers_is_unchanged_legacy_path(env):
    contract = _make_contract(env, "CTR-MP-LEGACY-1")
    signed = env["crm"].sign_contract(contract.id, _png_data_url(), env["actor_customer"])
    assert signed.status == "signed"
    assert signed.customer_signature_data is not None


# ---------------------------------------------------------------------------
# add_contract_signers
# ---------------------------------------------------------------------------

def test_add_contract_signers_creates_unsigned_rows(env):
    contract = _make_contract(env, "CTR-MP-ADD-1")
    created = env["crm"].add_contract_signers(
        contract.id,
        [
            {"party_role": "customer", "signer_name": "Multi Signer", "anchor_label": "Customer Signature"},
            {"party_role": "project_manager", "signer_name": "PM", "anchor_label": "PM Signature"},
        ],
        env["admin"],
    )
    assert len(created) == 2
    assert {c.party_role for c in created} == {"customer", "project_manager"}
    assert all(c.signed_at is None for c in created)


def test_add_contract_signers_requires_perm_write_contracts(env):
    contract = _make_contract(env, "CTR-MP-ADD-PERM")
    with pytest.raises(PermissionError):
        env["crm"].add_contract_signers(
            contract.id, [{"party_role": "customer"}], env["actor_customer"],
        )


def test_add_contract_signers_rejects_already_signed_contract(env):
    contract = _make_contract(env, "CTR-MP-ADD-SIGNED")
    env["crm"].sign_contract(contract.id, _png_data_url(), env["actor_customer"])
    with pytest.raises(ValueError):
        env["crm"].add_contract_signers(contract.id, [{"party_role": "customer"}], env["admin"])


# ---------------------------------------------------------------------------
# Multi-party signing: independent signers, completion gate, idempotency
# ---------------------------------------------------------------------------

def test_multi_party_contract_only_signed_once_all_parties_sign(env):
    contract = _make_contract(env, "CTR-MP-FLOW-1")
    crm = env["crm"]
    crm.add_contract_signers(
        contract.id,
        [
            {"party_role": "customer", "signer_name": "Multi Signer"},
            {"party_role": "project_manager", "signer_name": "PM"},
        ],
        env["admin"],
    )

    after_first = crm.sign_contract(contract.id, _png_data_url(), env["actor_customer"], party_role="customer")
    assert after_first.status != "signed"

    still_fetched = crm.get_contract(contract.id, env["admin"])
    assert still_fetched.status != "signed"

    after_second = crm.sign_contract(contract.id, "portal_countersignature", env["actor_pm"], party_role="project_manager")
    assert after_second.status == "signed"

    final = crm.get_contract(contract.id, env["admin"])
    assert final.status == "signed"


def test_partial_multi_party_sign_audit_records_which_party_signed(env):
    """NEW-595: a partial (1-of-N) multi-party sign's audit entry must
    carry the specific party's attribution (party_role + signer_name) in
    `side_effects`, not just `{"signature_captured": True}` -- otherwise
    the audit trail can't answer "who specifically signed" without
    cross-referencing contract_signers directly."""
    import json

    contract = _make_contract(env, "CTR-MP-AUDIT-1")
    crm = env["crm"]
    crm.add_contract_signers(
        contract.id,
        [
            {"party_role": "customer", "signer_name": "Multi Signer"},
            {"party_role": "project_manager", "signer_name": "PM"},
        ],
        env["admin"],
    )

    after_first = crm.sign_contract(contract.id, _png_data_url(), env["actor_customer"], party_role="customer")
    assert after_first.status != "signed"

    conn = env["db"].get_connection()
    row = conn.execute(
        "SELECT details_json FROM audit_log WHERE action = 'sign' AND entity_id = ? ORDER BY id DESC LIMIT 1;",
        (contract.id,),
    ).fetchone()
    assert row is not None
    details = json.loads(row["details_json"])
    side_effects = details["side_effects"]
    assert side_effects["signature_captured"] is True
    assert side_effects["party_role"] == "customer"
    assert side_effects["signer_name"] == "Multi Signer"


def test_multi_party_signer_role_derived_from_actor_when_omitted(env):
    contract = _make_contract(env, "CTR-MP-DERIVE-1")
    crm = env["crm"]
    crm.add_contract_signers(
        contract.id,
        [
            {"party_role": "customer", "signer_name": "Multi Signer"},
            {"party_role": "project_manager", "signer_name": "PM"},
        ],
        env["admin"],
    )
    # No party_role kwarg -- derived from actor.role (ROLE_CUSTOMER -> 'customer').
    signed_customer_leg = crm.sign_contract(contract.id, _png_data_url(), env["actor_customer"])
    assert signed_customer_leg.status != "signed"
    signed_final = crm.sign_contract(contract.id, "portal_countersignature", env["actor_pm"])
    assert signed_final.status == "signed"


def test_multi_party_signer_cannot_sign_twice(env):
    contract = _make_contract(env, "CTR-MP-DOUBLE-1")
    crm = env["crm"]
    crm.add_contract_signers(
        contract.id,
        [
            {"party_role": "customer", "signer_name": "Multi Signer"},
            {"party_role": "project_manager", "signer_name": "PM"},
        ],
        env["admin"],
    )
    crm.sign_contract(contract.id, _png_data_url(), env["actor_customer"], party_role="customer")
    with pytest.raises(ValueError):
        crm.sign_contract(contract.id, _png_data_url(), env["actor_customer"], party_role="customer")


def test_multi_party_unresolvable_role_raises_value_error(env):
    """An actor.role with no unambiguous unsigned row match (here: nothing
    matches ROLE_SALES's derived party_role 'rep' at all) must raise, not
    silently pick a different party's row."""
    contract = _make_contract(env, "CTR-MP-AMBIG-1")
    crm = env["crm"]
    crm.add_contract_signers(
        contract.id,
        [{"party_role": "customer", "signer_name": "Multi Signer"}],
        env["admin"],
    )
    with pytest.raises(ValueError):
        crm.sign_contract(contract.id, "sig", env["actor_pm"])  # PM has no row on this contract


def test_multi_party_fully_signed_contract_rejects_further_sign_calls(env):
    contract = _make_contract(env, "CTR-MP-DONE-1")
    crm = env["crm"]
    crm.add_contract_signers(
        contract.id,
        [{"party_role": "customer", "signer_name": "Multi Signer"}],
        env["admin"],
    )
    crm.sign_contract(contract.id, _png_data_url(), env["actor_customer"], party_role="customer")
    with pytest.raises(ValueError):
        crm.sign_contract(contract.id, "sig-again", env["actor_customer"], party_role="customer")


# ---------------------------------------------------------------------------
# NEW-593 regression: final signer's row UPDATE and the contracts.status
# UPDATE must commit atomically, or a crash between them leaves the
# contract permanently stuck fully-signed-by-every-party but never
# reaching status "signed", with no recovery path through sign_contract
# (idempotency guard blocks retry) or update_contract (status is not in
# its allow-list).
# ---------------------------------------------------------------------------

def test_sign_contract_final_signer_status_flip_is_atomic(env, monkeypatch):
    """Crash-injection regression test for NEW-593 (code-reviewer,
    B8.6d-b round 1), reproducing the technique used in
    d2_sales_manager_role_users_table_rebuild_approved.md: a real crash is
    injected mid-transaction by raising from inside conn.execute() when it
    sees the `UPDATE contracts SET status` statement, and the resulting
    on-disk state is inspected afterwards.

    A live sqlite3.Connection's execute()/__class__ cannot be swapped
    post-hoc (`execute` is a read-only attribute on the instance, and
    `__class__` reassignment raises TypeError for this C type), so the
    injection has to happen on a fresh connection created via
    `factory=`. CRMService.db.get_connection is monkeypatched to hand out
    one such fresh, poisoned connection (sharing the same
    `cache=shared` in-memory URI as the fixture's existing connection, so
    no data already committed is lost) for the duration of this test.

    Before the NEW-593 fix, the final signer's contract_signers UPDATE
    committed in its own `with conn:` block before the (separate)
    contracts.status UPDATE ever ran, so this crash would leave the
    signer row signed while contracts.status stayed stuck -- exactly the
    unrecoverable state this test guards against. After the fix, both
    UPDATEs are inside one `with conn:` block, so the crash rolls back
    the whole transaction and NEITHER update is persisted.
    """
    contract = _make_contract(env, "CTR-MP-ATOMIC-1")
    crm = env["crm"]
    crm.add_contract_signers(
        contract.id,
        [{"party_role": "customer", "signer_name": "Multi Signer"}],
        env["admin"],
    )

    class _PoisonConnection(sqlite3.Connection):
        armed = True

        def execute(self, sql, *args, **kwargs):
            if self.armed and "update contracts set status" in sql.lower():
                raise sqlite3.OperationalError("injected crash (NEW-593 regression test)")
            return super().execute(sql, *args, **kwargs)

    db = crm.db
    orig_get_connection = db.get_connection
    poison_holder: dict = {}

    def get_poison_connection():
        if "conn" not in poison_holder:
            poison_conn = sqlite3.connect(
                db.db_path,
                timeout=30.0,
                check_same_thread=False,
                uri=db.is_memory,
                factory=_PoisonConnection,
            )
            poison_conn.row_factory = sqlite3.Row
            poison_holder["conn"] = poison_conn
        return poison_holder["conn"]

    monkeypatch.setattr(db, "get_connection", get_poison_connection)

    with pytest.raises(sqlite3.OperationalError):
        crm.sign_contract(contract.id, _png_data_url(), env["actor_customer"], party_role="customer")

    # Restore the original (unpoisoned) connection accessor before reading
    # state back -- reads must go through a connection that isn't primed to
    # raise on the next `UPDATE contracts SET status` it happens to see
    # (there isn't one in the read-only assertions below, but this keeps the
    # test's intent explicit and matches how the real service would recover).
    monkeypatch.setattr(db, "get_connection", orig_get_connection)

    if "conn" in poison_holder:
        poison_holder["conn"].close()

    stuck = crm.get_contract(contract.id, env["admin"])
    assert stuck.status != "signed"

    conn = db.get_connection()
    signer_row = conn.execute(
        "SELECT signed_at FROM contract_signers WHERE contract_id = ? AND party_role = ?;",
        (contract.id, "customer"),
    ).fetchone()
    assert signer_row["signed_at"] is None, (
        "signer row must not be committed either -- if this is not None while "
        "contracts.status stayed unsigned, the two updates are not atomic and "
        "the contract is now stuck in the NEW-593 unrecoverable state (all "
        "signers done, status never flips, no recovery path through "
        "sign_contract or update_contract)."
    )

    # And the fix must not have broken the normal (non-crash) path: signing
    # again for real now succeeds and reaches "signed".
    recovered = crm.sign_contract(contract.id, _png_data_url(), env["actor_customer"], party_role="customer")
    assert recovered.status == "signed"


# ---------------------------------------------------------------------------
# PDF: each signer's signature drawn at their own anchor, not stacked
# ---------------------------------------------------------------------------

def test_multi_party_pdf_draws_each_signature_at_distinct_anchor(env, monkeypatch):
    contract = _make_contract(env, "CTR-MP-PDF-1")
    crm = env["crm"]
    crm.add_contract_signers(
        contract.id,
        [
            {"party_role": "customer", "signer_name": "Multi Signer", "anchor_label": "Customer Signature"},
            {"party_role": "project_manager", "signer_name": "PM", "anchor_label": "PM Signature"},
        ],
        env["admin"],
    )
    crm.sign_contract(contract.id, _png_data_url(), env["actor_customer"], party_role="customer")

    drawn_strings = []
    drawn_images = []
    orig_draw_string = pdf_service.rl_canvas.Canvas.drawString
    orig_draw_image = pdf_service.rl_canvas.Canvas.drawImage

    def spy_draw_string(self, x, y, text, *a, **kw):
        drawn_strings.append((x, y, text))
        return orig_draw_string(self, x, y, text, *a, **kw)

    def spy_draw_image(self, image, x, y, *a, **kw):
        drawn_images.append((x, y))
        return orig_draw_image(self, image, x, y, *a, **kw)

    monkeypatch.setattr(pdf_service.rl_canvas.Canvas, "drawString", spy_draw_string)
    monkeypatch.setattr(pdf_service.rl_canvas.Canvas, "drawImage", spy_draw_image)

    crm.sign_contract(contract.id, "portal_countersignature", env["actor_pm"], party_role="project_manager")

    # One drawImage call for the customer's real PNG signature.
    assert len(drawn_images) == 1

    # Two distinct anchor-label lines (one per signer), at two distinct y values.
    anchor_label_lines = [(x, y) for (x, y, text) in drawn_strings if "Signature (" in text]
    assert len(anchor_label_lines) == 2
    ys = {y for (_, y) in anchor_label_lines}
    assert len(ys) == 2  # distinct positions, not stacked

    # PM's text-stamp signature line is present with PM's own label text.
    assert any("PM" in text and "on" in text for (_, _, text) in drawn_strings)
