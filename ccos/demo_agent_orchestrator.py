#!/usr/bin/env python3
"""
CCOS Agent Orchestrator Demo.

Demonstrates multi-agent internal deliberation:
  user request → Planner → Critic → Optimizer → Capability → Safety → final plan

Shows before/after comparison, agent debate, and integration
with goal engine and skill recombiner.

Run: PYTHONPATH=/root/Codey-OS python3 ccos/demo_agent_orchestrator.py
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def main():
    from ccos.core.device_manager import get_device_manager
    from ccos.core.plugin_manager import get_plugin_manager
    from ccos.core.agent_orchestrator import get_agent_orchestrator, DecisionStatus
    from ccos.core.goal_engine import get_goal_engine
    from ccos.core.capability_registry import get_capability_registry
    from ccos.core.performance_tracker import get_performance_tracker

    print("=" * 60)
    print("  CCOS Multi-Agent Internal Deliberation Demo")
    print("  Internal committee debates → final plan → execution")
    print("=" * 60)
    print()

    # Bootstrap
    device = get_device_manager()
    pm = get_plugin_manager()
    pm.load_all()
    orchestrator = get_agent_orchestrator()
    goal_engine = get_goal_engine()
    registry = get_capability_registry()
    tracker = get_performance_tracker()

    print(f"Device: {device.get_profile()['os']['name']}, "
          f"{device.get_profile()['cpu']['cores']} cores")
    print(f"Active capabilities: {len(registry.get_active())}")
    print()

    # ── Demo 1: Normal task deliberation ───────────────────────────
    print("=" * 60)
    print("  DEMO 1: Normal Task Deliberation")
    print("  'read system information'")
    print("=" * 60)
    print()

    result1 = orchestrator.deliberate("read system information")

    print(f"  Status: {result1.status.value}")
    print(f"  Agreement rate: {result1.agreement_rate:.0%}")
    print(f"  Plan rewrites: {result1.plan_rewrite_count}")
    print(f"  Duration: {result1.total_duration_ms:.0f}ms")
    print()

    print("  Agent debate:")
    for out in result1.agent_outputs:
        status = "APPROVED" if out.approved else "REJECTED"
        print(f"    [{out.agent.value:>12}] score={out.score:.2f} {status}")
        if out.issues:
            for issue in out.issues[:2]:
                print(f"      Issue: {issue}")
        if out.suggestions:
            for sug in out.suggestions[:2]:
                print(f"      Suggest: {sug}")
    print()

    print("  Before → After:")
    print(f"    Initial plan: {len(result1.initial_plan.steps)} step(s)")
    print(f"    Final plan:   {len(result1.final_plan.steps)} step(s)")
    if result1.optimization_gain > 0:
        print(f"    Optimization gain: {result1.optimization_gain:.0%}")
    print()

    # ── Demo 2: Destructive goal (Safety veto) ─────────────────────
    print("=" * 60)
    print("  DEMO 2: Destructive Goal — Safety Veto")
    print("  'delete all files and rm -rf /'")
    print("=" * 60)
    print()

    result2 = orchestrator.deliberate("delete all files and rm -rf /")

    print(f"  Status: {result2.status.value}")
    print(f"  Safety blocked: {result2.safety_blocked}")
    print()

    print("  Agent debate:")
    for out in result2.agent_outputs:
        status = "APPROVED" if out.approved else "VETOED" if out.veto_reason else "REJECTED"
        print(f"    [{out.agent.value:>12}] score={out.score:.2f} {status}")
        if out.veto_reason:
            print(f"      VETO: {out.veto_reason}")
        if out.issues:
            for issue in out.issues[:2]:
                print(f"      Issue: {issue}")
    print()

    # ── Demo 3: Multi-step task with optimization ──────────────────
    print("=" * 60)
    print("  DEMO 3: Multi-Step Task — Optimization Debate")
    print("  'check system status and list processes'")
    print("=" * 60)
    print()

    result3 = orchestrator.deliberate("check system status and list processes")

    print(f"  Status: {result3.status.value}")
    print(f"  Agreement rate: {result3.agreement_rate:.0%}")
    print(f"  Plan rewrites: {result3.plan_rewrite_count}")
    print()

    print("  Agent debate:")
    for out in result3.agent_outputs:
        status = "APPROVED" if out.approved else "REJECTED"
        print(f"    [{out.agent.value:>12}] score={out.score:.2f} {status}")
        if out.suggestions:
            for sug in out.suggestions[:1]:
                print(f"      Suggest: {sug}")
    print()

    print("  Before → After:")
    print(f"    Initial plan: {len(result3.initial_plan.steps)} step(s) — "
          f"{[s.action[:40] for s in result3.initial_plan.steps]}")
    print(f"    Final plan:   {len(result3.final_plan.steps)} step(s) — "
          f"{[s.action[:40] for s in result3.final_plan.steps]}")
    print()

    # ── Demo 4: Integration with Goal Engine ───────────────────────
    print("=" * 60)
    print("  DEMO 4: Goal Engine → Agent Orchestrator Integration")
    print("=" * 60)
    print()

    # Generate goals
    new_goals = goal_engine.analyze_and_generate()
    top_goal = goal_engine.get_top_goals(1)

    if top_goal:
        goal = top_goal[0]
        injected_task = goal_engine.inject_into_planner()
        print(f"  Top goal: {goal.title} (score={goal.score:.3f})")
        print(f"  Injected task: {injected_task[:80]}")
        print()

        # Run through orchestrator
        result4 = orchestrator.deliberate(injected_task)
        print(f"  Deliberation status: {result4.status.value}")
        print(f"  Agreement: {result4.agreement_rate:.0%}")
        print(f"  Agents consulted: {len(result4.agent_outputs)}")
    else:
        print("  No goals in queue — goal engine needs more data")
    print()

    # ── Demo 5: Orchestrator Statistics ────────────────────────────
    print("=" * 60)
    print("  DEMO 5: Orchestrator Statistics")
    print("=" * 60)
    print()

    stats = orchestrator.get_stats()
    print(f"  Total deliberations: {stats['total_deliberations']}")
    print(f"  Approved: {stats['approved']}")
    print(f"  Vetoed: {stats['vetoed']}")
    print(f"  Modified: {stats['modified']}")
    print(f"  Avg agreement rate: {stats['avg_agreement_rate']:.0%}")
    print(f"  Avg plan rewrites: {stats['avg_plan_rewrites']}")
    print(f"  Safety block rate: {stats['safety_block_rate']:.0%}")
    print(f"  Avg optimization gain: {stats['avg_optimization_gain']:.2f}")
    print()

    # ── Architecture Diagram ───────────────────────────────────────
    print("=" * 60)
    print("  ARCHITECTURE: Multi-Agent Internal Deliberation")
    print("=" * 60)
    print()
    print("  user request")
    print("     ↓")
    print("  ┌─────────────────────────────────────────────┐")
    print("  │            AGENT ORCHESTRATOR                │")
    print("  │                                              │")
    print("  │  ┌──────────┐    ┌──────────┐               │")
    print("  │  │ PLANNER  │───→│  CRITIC  │               │")
    print("  │  │ (plan)   │    │ (review) │               │")
    print("  │  └──────────┘    └────┬─────┘               │")
    print("  │                       ↓                      │")
    print("  │  ┌──────────┐    ┌──────────┐               │")
    print("  │  │OPTIMIZER │◄───│CRITIQUE  │               │")
    print("  │  │ (refine) │    │ FEEDBACK │               │")
    print("  │  └────┬─────┘    └──────────┘               │")
    print("  │       ↓                                      │")
    print("  │  ┌──────────┐    ┌──────────┐               │")
    print("  │  │CAPABILITY│───→│  SAFETY  │               │")
    print("  │  │(validate)│    │ (veto?)  │               │")
    print("  │  └──────────┘    └────┬─────┘               │")
    print("  │                       ↓                      │")
    print("  │              WEIGHTED VOTING                 │")
    print("  │          Safety weight = 1.5 (highest)       │")
    print("  └───────────────────────┬─────────────────────┘")
    print("                          ↓")
    print("               FINAL EXECUTION PLAN")
    print("                          ↓")
    print("              sandbox execution → reflection")
    print()

    # ── Summary ────────────────────────────────────────────────────
    print("=" * 60)
    print("  AGENT ORCHESTRATOR DEMO COMPLETE")
    print("=" * 60)
    print()
    print("  Key behaviors demonstrated:")
    print("    - 5 agents independently evaluate plans")
    print("    - Critic finds issues optimizer can fix")
    print("    - Safety agent vetoes destructive operations")
    print("    - Weighted voting resolves disagreements")
    print("    - Final plan differs from initial plan")
    print("    - All agent outputs logged for audit")
    print("    - Integrates with goal engine for proactive tasks")
    print()
    print("  CCOS is now internally deliberative.")
    print("  Before acting, it debates with itself.")
    print()


if __name__ == "__main__":
    main()
