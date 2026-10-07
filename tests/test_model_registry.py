"""
WP1.3 (CODEY_OS_MASTER_BLUEPRINT.md §21, CLAUDE.md rule 1's missing 4th
element): core/model_registry.py's own CRUD, isolated from the real
on-device state DB.
"""
import pytest

import core.state as state_module
from core.state import StateStore


class _FakeGateDecision:
    def __init__(self, promote, reasons=None, stats=None):
        self.promote = promote
        self.reasons = reasons or []
        self.stats = stats or {}


@pytest.fixture
def isolated_registry(tmp_path, monkeypatch):
    """Points the shared state store at a scratch DB so these tests never
    touch this device's real ~/.codeyOS state."""
    store = StateStore(db_path=tmp_path / "test_state.db")
    monkeypatch.setattr(state_module, "_state_store", store)
    import core.model_registry as reg
    reg._extend_state_schema()  # table must exist on the fresh store
    yield reg
    store.close()


def test_record_refused_attempt(isolated_registry):
    reg = isolated_registry
    decision = _FakeGateDecision(False, reasons=["only 3 paired results (< 30)"])
    entry_id = reg.record_adoption_attempt("primary", decision, adapter_path="/tmp/adapter", adopted=False)

    entry = reg.get_adoption(entry_id)
    assert entry["adopted"] is False
    assert entry["rolled_back"] is False
    assert entry["gate_promote"] == 0
    assert entry["gate_reasons"] == ["only 3 paired results (< 30)"]
    assert entry["operator_override"] is False


def test_operator_override_independent_of_gate_promote(isolated_registry):
    """operator_override is a separate column from gate_promote -- a row
    can be gate_promote=0 (real gate refused, or no gate ran) AND
    operator_override=True at the same time, and the two must never be
    conflated: filtering on gate_promote=1 alone must never surface an
    operator bypass as if it were a real benchmark pass."""
    reg = isolated_registry
    refused = _FakeGateDecision(False, reasons=["no evaluator exists for this target; refusing to promote"])

    override_id = reg.record_adoption_attempt(
        "primary", refused, adapter_path="/tmp/a", backup_path="/tmp/b",
        adopted=True, operator_override=True,
    )

    entry = reg.get_adoption(override_id)
    assert entry["gate_promote"] == 0
    assert entry["operator_override"] is True
    assert entry["adopted"] is True

    listed = reg.list_adoptions()
    assert listed[0]["operator_override"] is True
    assert listed[0]["gate_promote"] == 0


def test_record_adopted_attempt_and_list(isolated_registry):
    reg = isolated_registry
    decision = _FakeGateDecision(True, reasons=["all criteria met"], stats={"n": 30, "p_value": 0.01})
    entry_id = reg.record_adoption_attempt(
        "primary", decision, adapter_path="/tmp/a", model_path="/tmp/m.gguf",
        backup_path="/tmp/m.backup.gguf", adopted=True,
    )

    entry = reg.get_adoption(entry_id)
    assert entry["adopted"] is True
    assert entry["gate_stats"] == {"n": 30, "p_value": 0.01}

    listed = reg.list_adoptions()
    assert len(listed) == 1
    assert listed[0]["id"] == entry_id


def test_get_latest_adopted_skips_refused_and_rolled_back(isolated_registry):
    reg = isolated_registry
    refused = _FakeGateDecision(False)
    adopted = _FakeGateDecision(True)

    reg.record_adoption_attempt("primary", refused, adopted=False)
    good_id = reg.record_adoption_attempt("primary", adopted, backup_path="/tmp/b1", adopted=True)

    latest = reg.get_latest_adopted("primary")
    assert latest["id"] == good_id

    reg.mark_rolled_back(good_id)
    assert reg.get_latest_adopted("primary") is None  # nothing live anymore


def test_mark_rolled_back_never_deletes_the_row(isolated_registry):
    reg = isolated_registry
    decision = _FakeGateDecision(True)
    entry_id = reg.record_adoption_attempt("primary", decision, backup_path="/tmp/b", adopted=True)
    reg.mark_rolled_back(entry_id)

    entry = reg.get_adoption(entry_id)
    assert entry is not None
    assert entry["rolled_back"] is True
    assert entry["rolled_back_at"] is not None


def test_prune_adoptions_keeps_most_recent(isolated_registry):
    """prune_adoptions() must never remove a LIVE (adopted, not-yet-rolled-
    back) row, no matter how old it is -- that row is the only pointer
    get_latest_adopted()/rollback_adoption() have to what's currently
    running. Regression for the bug where purely recency-based pruning
    could silently prune the one live entry once enough newer refused
    attempts accumulated, after which rollback_adoption() would
    permanently fail with "no registry entry found"."""
    reg = isolated_registry
    adopted_decision = _FakeGateDecision(True)
    refused_decision = _FakeGateDecision(False)

    # One live adopted entry, created first (so it's the OLDEST row).
    live_id = reg.record_adoption_attempt("primary", adopted_decision, backup_path="/tmp/b", adopted=True)

    # Several newer refused attempts -- more than keep_count.
    refused_ids = [
        reg.record_adoption_attempt("primary", refused_decision, adopted=False) for _ in range(5)
    ]

    removed = reg.prune_adoptions(keep_count=2)

    # The live entry survives regardless of its recency rank.
    assert reg.get_adoption(live_id) is not None

    # Normal recency-based pruning still happened among the refused
    # entries -- don't let this pass vacuously by everything surviving.
    assert removed > 0
    remaining_ids = {e["id"] for e in reg.list_adoptions(limit=100)}
    assert live_id in remaining_ids
    assert remaining_ids == {live_id} | set(refused_ids[-2:])
