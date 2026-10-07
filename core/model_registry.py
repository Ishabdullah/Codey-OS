#!/usr/bin/env python3
"""
Model/adapter promotion registry (WP1.3, CLAUDE.md rule 1's missing 4th
element -- CODEY_OS_MASTER_BLUEPRINT.md §17.2/§21).

Rule 1 requires: a promotion gate, a frozen benchmark, an append-only
ledger, AND rollback. The gate (bench/gate.py) and frozen suite already
exist; this closes the other two gaps the 2026-10-06 census found:
core/lora_import.py consulted no gate at all before swapping a model
into place, and no registry recorded which model/adapter was adopted,
when, under what gate decision, or how to undo it.

Records every adoption ATTEMPT -- gated or refused, not just successful
ones -- so a later developer or auditor can answer "what's live, why,
and how do I undo it" without guessing. Mirrors core/checkpoint.py's
existing create/list/prune shape and reuses its same underlying
SQLite store (core/state.get_state_store()) rather than inventing a
new storage format.

Deliberately does NOT call core/checkpoint.py's create_checkpoint()/
rollback() -- those back up every core/*.py file and create a real git
commit, a much heavier side effect than a model swap warrants, and
this subsystem has zero production callers today (census §17.2: the
only caller of compare_and_upgrade hardcodes no_evaluator()). The
model FILE's own reversibility is handled by core/lora_import.py's
existing create_backup_before_import()/rollback_to_backup(), which is
already correct (NEW-91/NEW-163 fixed its one real bug); this module
adds the missing record of what happened, keyed to that same backup
path, and is what core/lora_import.py now consults before ever
swapping a model in.

NOT rule 1's append-only benchmark ledger: this registry's
prune_adoptions() below DOES delete old rows (refused attempts and
rolled-back adoptions), which is fine here -- it is an operational
"what's currently live and how do I undo it" record, not the
append-only evaluation ledger rule 1 requires. That ledger is
bench/'s separate, currently-empty ledger (CODEY_OS_MASTER_BLUEPRINT.md
§21); do not conflate the two or treat this module's pruning as a
rule-1 violation.
"""
import json
import time
from typing import Any, Dict, List, Optional

from core.state import get_state_store


def _extend_state_schema():
    """Add the model_adoptions table to the shared state schema."""
    state = get_state_store()
    state.execute("""
        CREATE TABLE IF NOT EXISTS model_adoptions (
            id TEXT PRIMARY KEY,
            created_at INTEGER NOT NULL,
            model_variant TEXT NOT NULL,
            adapter_path TEXT,
            model_path TEXT,
            backup_path TEXT,
            gate_promote INTEGER NOT NULL,
            gate_reasons TEXT,
            gate_stats TEXT,
            adopted INTEGER NOT NULL,
            rolled_back INTEGER NOT NULL DEFAULT 0,
            rolled_back_at INTEGER,
            is_operator_override INTEGER NOT NULL DEFAULT 0
        )
    """)


# Initialize on import, same convention as core/checkpoint.py.
_extend_state_schema()


def record_adoption_attempt(
    model_variant: str,
    gate_decision: Any,
    adapter_path: Optional[str] = None,
    model_path: Optional[str] = None,
    backup_path: Optional[str] = None,
    adopted: bool = False,
    operator_override: bool = False,
) -> str:
    """Record one adoption attempt -- refused or adopted either way.

    `gate_decision` is a bench.gate.GateDecision (or anything with
    .promote/.reasons/.stats attributes -- duck-typed so tests can pass
    a plain object without importing bench.gate). Returns the new
    entry's id.

    `operator_override` is INDEPENDENT of `gate_decision.promote` -- it
    records whether a human operator explicitly bypassed the gate (e.g.
    core/lora_import.py's --lora-force-adopt path), not whether the gate
    itself said yes. A row can and should show BOTH facts at once: the
    real gate's verdict (gate_promote, honest, never fabricated) AND
    whether an operator overrode it (is_operator_override) -- one must
    never overwrite or stand in for the other, so a query filtering on
    gate_promote=1 alone can never mistake an operator bypass for a real
    benchmark pass.
    """
    # time_ns(), not time()*1000: a tight loop (automated adoption attempts,
    # or this module's own tests) can call this more than once per
    # millisecond, and the id must stay unique for the SQL PRIMARY KEY.
    entry_id = f"{time.time_ns()}"
    state = get_state_store()
    state.execute(
        """INSERT INTO model_adoptions
           (id, created_at, model_variant, adapter_path, model_path, backup_path,
            gate_promote, gate_reasons, gate_stats, adopted, rolled_back,
            is_operator_override)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)""",
        (
            entry_id, int(time.time()), model_variant, adapter_path, model_path, backup_path,
            int(bool(getattr(gate_decision, "promote", False))),
            json.dumps(list(getattr(gate_decision, "reasons", []) or [])),
            json.dumps(dict(getattr(gate_decision, "stats", {}) or {})),
            int(bool(adopted)),
            int(bool(operator_override)),
        ),
    )
    return entry_id


def mark_rolled_back(adoption_id: str) -> bool:
    """Mark an adoption entry as rolled back. The row itself is never
    deleted by this -- the registry's whole purpose is an undeletable
    record of what happened, even after the model is reverted."""
    state = get_state_store()
    return state.mark_model_adoption_rolled_back(adoption_id, int(time.time()))


def list_adoptions(limit: int = 10) -> List[Dict]:
    """List recent adoption attempts, newest first, with gate fields
    deserialized back into Python values."""
    state = get_state_store()
    out = []
    for row in state.get_model_adoptions(limit):
        row = dict(row)
        row["gate_reasons"] = json.loads(row["gate_reasons"] or "[]")
        row["gate_stats"] = json.loads(row["gate_stats"] or "{}")
        row["adopted"] = bool(row["adopted"])
        row["rolled_back"] = bool(row["rolled_back"])
        row["operator_override"] = bool(row["is_operator_override"])
        out.append(row)
    return out


def get_adoption(adoption_id: str) -> Optional[Dict]:
    """Get a specific adoption attempt by id, deserialized like list_adoptions()."""
    state = get_state_store()
    row = state.get_model_adoption(adoption_id)
    if row is None:
        return None
    row = dict(row)
    row["gate_reasons"] = json.loads(row["gate_reasons"] or "[]")
    row["gate_stats"] = json.loads(row["gate_stats"] or "{}")
    row["adopted"] = bool(row["adopted"])
    row["rolled_back"] = bool(row["rolled_back"])
    row["operator_override"] = bool(row["is_operator_override"])
    return row


def get_latest_adopted(model_variant: Optional[str] = None) -> Optional[Dict]:
    """Most recent entry that was actually adopted and not yet rolled
    back -- "what's live right now", for an auditor or a future rollback
    call that needs to know what it would be reverting."""
    state = get_state_store()
    for row in state.get_model_adoptions(100):
        if not row["adopted"] or row["rolled_back"]:
            continue
        if model_variant is not None and row["model_variant"] != model_variant:
            continue
        return get_adoption(row["id"])
    return None


def prune_adoptions(keep_count: int = 20) -> int:
    """Remove old adoption entries, keeping only the most recent ones.
    Mirrors core/checkpoint.py's prune_checkpoints(). Returns the number
    of entries removed.

    A row that is currently LIVE (adopted=True, rolled_back=False) is
    always kept, regardless of its recency rank -- it is the only
    pointer get_latest_adopted()/rollback_adoption() have to what's
    actually running right now, so pruning it purely by age would leave
    the system with a live model nothing can roll back (rollback_adoption()
    would permanently fail with "no registry entry found"). keep_count
    applies to the remaining (non-live) rows: the `keep_count` most
    recent of those survive, the rest are removed oldest-first.
    """
    state = get_state_store()
    rows = state.get_model_adoptions(100000)
    prunable = [row for row in rows if not (row["adopted"] and not row["rolled_back"])]
    to_remove = prunable[keep_count:]
    for row in to_remove:
        state.delete_model_adoption(row["id"])
    return len(to_remove)
