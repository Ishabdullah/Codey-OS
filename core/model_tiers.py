"""
Model tier config — Track 3 Phase 5b / TODO.md 7.3 sub-task B.

Formalizes today's *existing* fixed model assignments (one model per role,
selected via env vars in `utils/config.py`) as data: a
`(domain, role, tier) -> ModelTierEntry` table. This is a pure data module —
nothing here loads a model, and nothing in the loader/classifier/dispatch
path reads this table yet. That wiring is later work (7.3 sub-task C logs a
classifier decision without acting on it; actually switching which model
loads per tier is sub-task E, blocked on 7.4's resource gate closing — see
WORK_QUEUE.md Track 3 item 3).

Scope for this first cut: `domain="coding"` only (Vision §11.10's
multi-domain approved-list shape is a later amendment, not required here).
Two roles: `"planner"` and `"coder"`. `"embedding"` is deliberately excluded
— `EMBED_MODEL_PATH` is a single fixed purpose today, not tiered.

Coder role notes (do not add a second local tier — see NEW-84):
`SECONDARY_MODEL_PATH` was checked directly during 7.3's scoping and is dead
config today — `core/lora_import.py`'s own NEW-84 comment block (lines
25-41) states its swap functions mutate `cfg.PLANNER_MODEL_PATH`, never
`cfg.SECONDARY_MODEL_PATH`, and that mutating `SECONDARY_MODEL_PATH` alone
"had no effect on what actually got loaded." `SECONDARY_MODEL_PATH` and
`PLANNER_MODEL_PATH` share an identical default path only by coincidence,
not because `SECONDARY_MODEL_PATH` names a real, distinct "coder-small"
model. So the `coder` role gets exactly ONE local tier here (`"large"`, 7B,
`MODEL_PATH`) plus a `"remote"` tier wherever `CODEY_BACKEND` selects one —
not two local tiers.

Planner/coder same-physical-model overlap (NEW-125, logged not fixed): the
planner's `"large"` tier (the orchestrator's 7B fallback path,
`core/orchestrator.py:plan_tasks()`, exercised when the 1.5B daemon planner
fails/is unavailable) is the SAME underlying model file as the coder role's
`"large"` tier — both point at `utils.config.MODEL_PATH` on
`PRIMARY_SERVER_PORT`. This table represents that literally (identical
`model_ref`/`port` in both entries) rather than implying two distinct
models.

Each entry also carries a `backend` field (not just a bare model
reference) — deliberate, so Vision §11.13's later "OpenRouter as a
runtime-selectable tier" work can extend this schema instead of needing to
replace it.

Contract: the `"remote"` tier key is present for a role ONLY when that
role's backend env var (`CODEY_BACKEND` for coder, `CODEY_BACKEND_P` for
planner) is actually set to a remote backend at import time — see
`cfg.is_remote_backend()`/`cfg.is_remote_planner_backend()` below. Under
the default `"local"` backend, `("coding", "coder", "remote")` and
`("coding", "planner", "remote")` are simply absent from `MODEL_TIERS`, and
`get_tier(..., "remote")` raises `KeyError` — callers (future sub-tasks C/E)
must check membership or catch `KeyError` rather than assuming a
`"remote"` tier always exists.
"""

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from utils import config as cfg

# Backend values an entry's `backend` field may hold. Mirrors
# utils.config.CODEY_BACKEND/CODEY_BACKEND_P's accepted values ("local" plus
# the two remote backends) — kept as a tuple here, not re-derived from
# CODEY_BACKEND's own module-level string, since this table declares what
# backends the coding domain's tiers CAN use, independent of which one a
# given process happens to be running with right now.
BACKENDS = ("local", "openrouter", "unlimitedclaude")


@dataclass(frozen=True)
class ModelTierEntry:
    """
    One `(domain, role, tier)` slot's model assignment.

    `model_ref` is a plain string, not a `Path` — a "local" backend entry's
    `model_ref` is a filesystem path (stringified), while a remote backend's
    `model_ref` is a model name/id (e.g. "qwen/qwen-2.5-coder-7b-instruct"),
    so a single string type covers both without a union field. `port` is
    `None` for remote-backend entries (no local server, no port).
    """

    model_ref: str
    backend: str  # one of BACKENDS
    port: Optional[int] = None


# ── Coding domain, "planner" role ───────────────────────────────────────────
# M1-D (2026-08-23): a "small" tier used to sit here — the dedicated 1.5B
# daemon planner on its own port (8081, core/plannd.py). That process is
# retired (core/planner_loader.py deleted); planning is now a thinking-mode
# request against the same primary server the "large"/coder tier already
# points at. Formalizing that as a table entry means "small" and "large"
# would be byte-for-byte identical (same model_ref, same port) — removed
# rather than kept as a duplicate of "large" below, since a distinct tier
# key that resolves to the exact same server isn't a real second tier.
#
# "large": the orchestrator's 7B fallback path (core/orchestrator.py's
#          plan_tasks(), used when the daemon planner fails/is unavailable)
#          — same physical model as the coder role's "large" tier below
#          (NEW-125), represented literally, not as a distinct model.
# "remote": present ONLY when CODEY_BACKEND_P is actually set to a remote
#          backend (cfg.is_remote_planner_backend()) — when the process is
#          running "local" (the default), there is no remote assignment
#          active today, so this table doesn't invent a phantom remote entry
#          for a backend nothing is currently pointed at.
_PLANNER_TIERS: Dict[str, ModelTierEntry] = {
    "large": ModelTierEntry(
        model_ref=str(cfg.MODEL_PATH),
        backend="local",
        port=cfg.PRIMARY_SERVER_PORT,
    ),
}
if cfg.is_remote_planner_backend():
    _PLANNER_TIERS["remote"] = ModelTierEntry(
        model_ref=(
            cfg.UNLIMITEDCLAUDE_PLANNER_MODEL
            if cfg.CODEY_PLANNER_BACKEND == "unlimitedclaude"
            else cfg.OPENROUTER_PLANNER_MODEL
        ),
        backend=cfg.CODEY_PLANNER_BACKEND,
        port=None,
    )

# ── Coding domain, "coder" role ─────────────────────────────────────────────
# "large": the ONLY local tier (7B, MODEL_PATH, port 8080). No "small" local
#          tier — see module docstring / NEW-84.
# "remote": present ONLY when CODEY_BACKEND is actually set to a remote
#          backend (cfg.is_remote_backend()) — same reasoning as the planner
#          role above.
_CODER_TIERS: Dict[str, ModelTierEntry] = {
    "large": ModelTierEntry(
        model_ref=str(cfg.MODEL_PATH),
        backend="local",
        port=cfg.PRIMARY_SERVER_PORT,
    ),
}
if cfg.is_remote_backend():
    _CODER_TIERS["remote"] = ModelTierEntry(
        model_ref=(cfg.UNLIMITEDCLAUDE_MODEL if cfg.CODEY_BACKEND == "unlimitedclaude" else cfg.OPENROUTER_MODEL),
        backend=cfg.CODEY_BACKEND,
        port=None,
    )

# The full table: (domain, role, tier) -> ModelTierEntry.
# `domain` is fixed to "coding" for this first cut (Vision §11.10's
# multi-domain shape is out of scope here). Built from _PLANNER_TIERS /
# _CODER_TIERS above rather than written out flat, so each role's tier set
# stays readable as its own small dict.
MODEL_TIERS: Dict[Tuple[str, str, str], ModelTierEntry] = {
    ("coding", "planner", tier): entry for tier, entry in _PLANNER_TIERS.items()
}
MODEL_TIERS.update({("coding", "coder", tier): entry for tier, entry in _CODER_TIERS.items()})


def get_tier(domain: str, role: str, tier: str) -> ModelTierEntry:
    """
    Look up a single `(domain, role, tier)` entry.

    Raises KeyError (loud, not a silent None) on an unrecognized key —
    matching this project's fail-loud-on-bad-config convention elsewhere
    (e.g. utils/config.py's CODEY_N_CTX validation) rather than returning a
    default that could mask a typo'd role/tier name.
    """
    return MODEL_TIERS[(domain, role, tier)]


def tiers_for_role(domain: str, role: str) -> Dict[str, ModelTierEntry]:
    """Return all tiers configured for `(domain, role)`, keyed by tier name."""
    return {tier: entry for (d, r, tier), entry in MODEL_TIERS.items() if d == domain and r == role}
