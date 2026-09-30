"""Master switch for CCOS self-improvement (AGI audit 2.3; CLAUDE.md rule 1).

CODEY_SELF_IMPROVE = off (default) | shadow | on
  off    -- optimizer/loop/goal engine/recombiner do nothing.
  shadow -- may generate and sandbox-test candidates and LOG them; never deploys.
  on     -- may deploy, but ONLY with an approving bench.gate.GateDecision.
Unknown values are treated as off.
"""
import os


def mode() -> str:
    m = os.environ.get("CODEY_SELF_IMPROVE", "off").strip().lower()
    return m if m in ("off", "shadow", "on") else "off"


def enabled() -> bool:
    return mode() != "off"


def may_deploy() -> bool:
    return mode() == "on"
