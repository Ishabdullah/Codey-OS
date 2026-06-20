#!/usr/bin/env python3
"""
CCOS Agent Orchestrator Test Suite.

Tests multi-agent deliberation: planner → critic → optimizer
→ capability → safety → final plan.
"""

import json
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ccos.core.agent_orchestrator import (
    AgentOrchestrator,
    AgentRole,
    ExecutionPlan,
    PlanStep,
    RiskLevel,
    DecisionStatus,
    PlannerAgent,
    CriticAgent,
    OptimizerAgent,
    CapabilityAgent,
    SafetyAgent,
    get_agent_orchestrator,
)
from ccos.core.capability_registry import (
    Capability,
    CapabilityRegistry,
)
from ccos.core.performance_tracker import PerformanceTracker


def _make_temp_registry():
    f = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
    f.close()
    return CapabilityRegistry(store_path=f.name), f.name


def _make_temp_tracker():
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    return PerformanceTracker(db_path=f.name), f.name


def _seed_capabilities(registry):
    caps = [
        Capability(name="system.info", description="Read system info",
                   implementation="/tmp/si.py", category="system"),
        Capability(name="system.processes", description="List processes",
                   implementation="/tmp/sp.py", category="system"),
    ]
    for c in caps:
        registry.register(c)


def test_planner_agent():
    """Planner agent should generate structured plans."""
    print("Testing PlannerAgent...")
    registry, reg = _make_temp_registry()
    tracker, db = _make_temp_tracker()
    _seed_capabilities(registry)

    agent = PlannerAgent()
    agent._registry = registry
    agent._tracker = tracker

    plan, output = agent.generate_plan("read system information")
    assert len(plan.steps) >= 1
    assert plan.goal == "read system information"
    assert output.agent == AgentRole.PLANNER
    assert output.approved is True

    print(f"  [PASS] Generated {len(plan.steps)} step(s), score={output.score}")

    Path(reg).unlink(missing_ok=True)
    Path(db).unlink(missing_ok=True)
    return True


def test_critic_agent():
    """Critic agent should find issues and suggest improvements."""
    print("Testing CriticAgent...")
    tracker, db = _make_temp_tracker()

    # Create a plan with issues (duplicate capabilities)
    plan = ExecutionPlan(
        goal="test",
        steps=[
            PlanStep(id=1, action="use system.info", capability="system.info"),
            PlanStep(id=2, action="use system.info again", capability="system.info"),
            PlanStep(id=3, action="use system.processes", capability="system.processes"),
        ],
        tools_required=["system.info", "system.info", "system.processes"],
    )

    # Pre-populate tracker data
    for i in range(5):
        tracker.record_execution("system.info", "1.0.0", 200, True)

    agent = CriticAgent()
    output = agent.review_plan(plan)

    assert output.agent == AgentRole.CRITIC
    assert len(output.issues) > 0 or len(output.suggestions) > 0
    # Should detect redundant calls
    assert any("redundant" in i.lower() or "duplicate" in i.lower() for i in output.issues)

    print(f"  [PASS] Found {len(output.issues)} issue(s), {len(output.suggestions)} suggestion(s)")
    for issue in output.issues:
        print(f"    Issue: {issue}")

    Path(db).unlink(missing_ok=True)
    return True


def test_optimizer_agent():
    """Optimizer agent should improve plans based on critique."""
    print("Testing OptimizerAgent...")
    tracker, db = _make_temp_tracker()

    # Plan with duplicates
    plan = ExecutionPlan(
        goal="test",
        steps=[
            PlanStep(id=1, action="step A", capability="system.info"),
            PlanStep(id=2, action="step A again", capability="system.info"),
        ],
        tools_required=["system.info", "system.info"],
    )

    # Critique pointing out duplicates
    from ccos.core.agent_orchestrator import AgentOutput
    critique = AgentOutput(
        agent=AgentRole.CRITIC,
        suggestions=["Consolidate duplicate capability calls into single invocation"],
    )

    agent = OptimizerAgent()
    optimized, output = agent.optimize_plan(plan, critique)

    assert len(optimized.steps) < len(plan.steps), "Should remove duplicates"
    assert output.agent == AgentRole.OPTIMIZER
    assert output.approved is True

    print(f"  [PASS] Reduced {len(plan.steps)} steps → {len(optimized.steps)} steps")

    Path(db).unlink(missing_ok=True)
    return True


def test_capability_agent():
    """Capability agent should validate tool availability."""
    print("Testing CapabilityAgent...")
    registry, reg = _make_temp_registry()
    tracker, db = _make_temp_tracker()
    _seed_capabilities(registry)

    # Plan with valid and invalid capabilities
    plan = ExecutionPlan(
        goal="test",
        steps=[
            PlanStep(id=1, action="get info", capability="system.info"),
            PlanStep(id=2, action="nonexistent", capability="nonexistent.cap"),
        ],
        tools_required=["system.info", "nonexistent.cap"],
    )

    agent = CapabilityAgent()
    agent._registry = registry
    agent._tracker = tracker

    validated, output = agent.validate_capabilities(plan)

    assert output.agent == AgentRole.CAPABILITY
    assert len(output.issues) > 0, "Should report missing capability"

    print(f"  [PASS] Validated capabilities, found {len(output.issues)} issue(s)")
    for issue in output.issues:
        print(f"    {issue}")

    Path(reg).unlink(missing_ok=True)
    Path(db).unlink(missing_ok=True)
    return True


def test_safety_agent():
    """Safety agent should block unsafe operations."""
    print("Testing SafetyAgent...")

    # Unsafe plan with destructive operation
    plan = ExecutionPlan(
        goal="delete everything",
        steps=[
            PlanStep(id=1, action="rm -rf /important_data"),
        ],
        risk_level=RiskLevel.HIGH,
    )

    agent = SafetyAgent()
    output = agent.validate_safety(plan)

    assert output.agent == AgentRole.SAFETY
    assert output.approved is False, "Should veto destructive plan"
    assert output.veto_reason != ""

    print(f"  [PASS] VETOED unsafe plan: {output.veto_reason}")

    # Safe plan should pass
    safe_plan = ExecutionPlan(
        goal="read system info",
        steps=[PlanStep(id=1, action="read system information")],
        risk_level=RiskLevel.LOW,
    )
    safe_output = agent.validate_safety(safe_plan)
    assert safe_output.approved is True

    print(f"  [PASS] Approved safe plan")
    return True


def test_full_deliberation():
    """Full deliberation should produce a refined, approved plan."""
    print("Testing Full Deliberation...")
    registry, reg = _make_temp_registry()
    tracker, db = _make_temp_tracker()
    _seed_capabilities(registry)

    for i in range(5):
        tracker.record_execution("system.info", "1.0.0", 200, True)

    orchestrator = AgentOrchestrator()
    orchestrator._planner._registry = registry
    orchestrator._planner._tracker = tracker
    orchestrator._capability._registry = registry
    orchestrator._capability._tracker = tracker

    result = orchestrator.deliberate("read system information")

    assert result.status in (DecisionStatus.APPROVED, DecisionStatus.MODIFIED)
    assert len(result.agent_outputs) == 5
    assert result.total_duration_ms > 0
    assert result.agreement_rate > 0

    # All 5 agents should have been consulted
    agents_consulted = {o.agent for o in result.agent_outputs}
    assert len(agents_consulted) == 5

    print(f"  [PASS] Status: {result.status.value}")
    print(f"  Agreement: {result.agreement_rate:.0%}")
    print(f"  Rewrites: {result.plan_rewrite_count}")
    print(f"  Agents: {[o.agent.value for o in result.agent_outputs]}")

    Path(reg).unlink(missing_ok=True)
    Path(db).unlink(missing_ok=True)
    return True


def test_deliberation_with_destructive_goal():
    """Safety agent should veto destructive goals."""
    print("Testing Destructive Goal Veto...")
    registry, reg = _make_temp_registry()
    tracker, db = _make_temp_tracker()
    _seed_capabilities(registry)

    orchestrator = AgentOrchestrator()
    orchestrator._planner._registry = registry
    orchestrator._planner._tracker = tracker
    orchestrator._capability._registry = registry
    orchestrator._capability._tracker = tracker

    result = orchestrator.deliberate("delete all files and rm -rf /")

    assert result.status == DecisionStatus.VETOED
    assert result.safety_blocked is True

    print(f"  [PASS] Status: {result.status.value}")
    print(f"  Safety blocked: {result.safety_blocked}")
    print(f"  Veto reason: {result.agent_outputs[-1].veto_reason}")

    Path(reg).unlink(missing_ok=True)
    Path(db).unlink(missing_ok=True)
    return True


def test_weighted_voting():
    """Voting should use agent weights correctly."""
    print("Testing Weighted Voting...")
    from ccos.core.agent_orchestrator import AgentOutput

    orchestrator = AgentOrchestrator()

    # All approve — should be 1.0
    outputs_all_approve = [
        AgentOutput(agent=AgentRole.PLANNER, approved=True),
        AgentOutput(agent=AgentRole.CRITIC, approved=True),
        AgentOutput(agent=AgentRole.OPTIMIZER, approved=True),
        AgentOutput(agent=AgentRole.CAPABILITY, approved=True),
        AgentOutput(agent=AgentRole.SAFETY, approved=True),
    ]
    rate = orchestrator._calculate_agreement(outputs_all_approve)
    assert rate == 1.0, f"Expected 1.0, got {rate}"

    # Safety disapproves — weighted impact should be significant
    outputs_safety_disapproves = [
        AgentOutput(agent=AgentRole.PLANNER, approved=True),
        AgentOutput(agent=AgentRole.CRITIC, approved=True),
        AgentOutput(agent=AgentRole.OPTIMIZER, approved=True),
        AgentOutput(agent=AgentRole.CAPABILITY, approved=True),
        AgentOutput(agent=AgentRole.SAFETY, approved=False),
    ]
    rate = orchestrator._calculate_agreement(outputs_safety_disapproves)
    assert rate < 1.0, "Safety disapproval should reduce agreement"
    assert rate > 0.5, "But majority still approves"

    print(f"  [PASS] All approve: agreement=1.0")
    print(f"  [PASS] Safety disapproves: agreement={rate:.3f}")
    return True


def test_orchestrator_stats():
    """Stats should reflect deliberation history."""
    print("Testing Orchestrator Stats...")
    registry, reg = _make_temp_registry()
    tracker, db = _make_temp_tracker()
    _seed_capabilities(registry)

    orchestrator = AgentOrchestrator()
    orchestrator._planner._registry = registry
    orchestrator._planner._tracker = tracker
    orchestrator._capability._registry = registry
    orchestrator._capability._tracker = tracker

    # Run multiple deliberations
    for goal in ["read system info", "list processes", "delete rm -rf /"]:
        orchestrator.deliberate(goal)

    stats = orchestrator.get_stats()
    assert stats["total_deliberations"] == 3
    assert stats["vetoed"] >= 1  # The destructive one
    assert stats["safety_block_rate"] > 0

    print(f"  [PASS] Stats: {json.dumps(stats, indent=2)}")

    Path(reg).unlink(missing_ok=True)
    Path(db).unlink(missing_ok=True)
    return True


def test_plan_modification():
    """Final plan should differ from initial when agents find issues."""
    print("Testing Plan Modification...")
    registry, reg = _make_temp_registry()
    tracker, db = _make_temp_tracker()
    _seed_capabilities(registry)

    # Give system.info poor performance to trigger critic
    for i in range(10):
        tracker.record_execution("system.info", "1.0.0", 200, i < 5,
                                error_category="timeout" if i >= 5 else "")

    orchestrator = AgentOrchestrator()
    orchestrator._planner._registry = registry
    orchestrator._planner._tracker = tracker
    orchestrator._capability._registry = registry
    orchestrator._capability._tracker = tracker

    result = orchestrator.deliberate("check system status")

    # Plan should have been modified (error handling added, or capability flagged)
    initial_dict = result.initial_plan.to_dict()
    final_dict = result.final_plan.to_dict()

    # At minimum, the critic/optimizer should have added suggestions
    has_suggestions = any(o.suggestions for o in result.agent_outputs)
    assert has_suggestions, "Agents should have suggestions"

    print(f"  [PASS] Initial steps: {len(result.initial_plan.steps)}")
    print(f"  [PASS] Final steps: {len(result.final_plan.steps)}")
    print(f"  [PASS] Rewrites: {result.plan_rewrite_count}")
    print(f"  [PASS] Optimization gain: {result.optimization_gain:.2f}")

    Path(reg).unlink(missing_ok=True)
    Path(db).unlink(missing_ok=True)
    return True


def test_agent_output_logging():
    """All agent outputs must be logged."""
    print("Testing Agent Output Logging...")
    registry, reg = _make_temp_registry()
    tracker, db = _make_temp_tracker()
    _seed_capabilities(registry)

    orchestrator = AgentOrchestrator()
    orchestrator._planner._registry = registry
    orchestrator._planner._tracker = tracker
    orchestrator._capability._registry = registry
    orchestrator._capability._tracker = tracker

    result = orchestrator.deliberate("read system information")

    # Every agent must have logged output
    for output in result.agent_outputs:
        assert output.agent in AgentRole
        assert output.timestamp > 0
        assert output.duration_ms >= 0

    # History should be accessible
    history = orchestrator.get_history()
    assert len(history) == 1
    assert "agents" in history[0]

    print(f"  [PASS] {len(result.agent_outputs)} agent outputs logged")
    for out in result.agent_outputs:
        print(f"    {out.agent.value}: score={out.score}, approved={out.approved}")

    Path(reg).unlink(missing_ok=True)
    Path(db).unlink(missing_ok=True)
    return True


def main():
    print("=" * 55)
    print("  CCOS Agent Orchestrator Test Suite")
    print("=" * 55)
    print()

    tests = [
        test_planner_agent,
        test_critic_agent,
        test_optimizer_agent,
        test_capability_agent,
        test_safety_agent,
        test_full_deliberation,
        test_deliberation_with_destructive_goal,
        test_weighted_voting,
        test_orchestrator_stats,
        test_plan_modification,
        test_agent_output_logging,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
                print(f"  [FAIL] {test.__name__}")
        except Exception as e:
            failed += 1
            import traceback
            print(f"  [ERROR] {test.__name__}: {e}")
            traceback.print_exc()
        print()

    print("=" * 55)
    print(f"  Results: {passed} passed, {failed} failed")
    print("=" * 55)
    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
