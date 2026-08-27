"""
Agent Plugin — CCOS capability wrapper for core/agent.py and core/recursive.py.
"""
from ccos.plugins.coding.agent.agent import (
    AgentExecutionResult,
    classify_breadth_capability,
    run_agent_capability,
    run_recursive_capability,
    scoped_agent_permissions,
    test,
)

__all__ = [
    "AgentExecutionResult",
    "classify_breadth_capability",
    "run_agent_capability",
    "run_recursive_capability",
    "scoped_agent_permissions",
    "test",
]
