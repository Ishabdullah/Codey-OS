"""Fixture stand-in for ccos/core/agent_orchestrator.py -- a real,
non-test caller of validate_tool_safety, but itself unreachable from
the entry-point set (nothing imports this module), so 7c's
"caller exists but isn't itself reachable" branch (1 point, not 3)
is exercised."""
from ccos.core.tool_router import validate_tool_safety


def run(action):
    return validate_tool_safety(action)
