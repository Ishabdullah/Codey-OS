"""
Agent Orchestrator — Multi-agent internal deliberation for CCOS.

Replaces single-path decision making with parallel internal agents
that propose, critique, optimize, validate, and approve execution
plans before any action is taken.

Agent roles:
  1. Planner Agent    — decomposes goals, generates initial plans
  2. Critic Agent     — reviews plans, finds inefficiencies and risks
  3. Optimizer Agent  — refines plans based on critique
  4. Capability Agent — verifies tools/skills, suggests substitutions
  5. Safety Agent     — validates sandbox constraints, can veto

All agents are lightweight functions using structured prompts,
not separate models. Communication is via structured JSON.
"""

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from ccos.core.capability_registry import get_capability_registry
from ccos.core.performance_tracker import get_performance_tracker
from ccos.core.sandbox import BLOCKED_COMMANDS


# ── Data structures ────────────────────────────────────────────────

class AgentRole(str, Enum):
    PLANNER = "planner"
    CRITIC = "critic"
    OPTIMIZER = "optimizer"
    CAPABILITY = "capability"
    SAFETY = "safety"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class DecisionStatus(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    MODIFIED = "modified"
    VETOED = "vetoed"


@dataclass
class PlanStep:
    """A single step in an execution plan."""
    id: int
    action: str
    capability: str = ""
    tool: str = ""
    args: Dict[str, Any] = field(default_factory=dict)
    risk: RiskLevel = RiskLevel.LOW
    notes: str = ""


@dataclass
class ExecutionPlan:
    """Standardized plan representation."""
    goal: str
    steps: List[PlanStep]
    tools_required: List[str] = field(default_factory=list)
    estimated_cost: str = "low"
    risk_level: RiskLevel = RiskLevel.LOW
    estimated_duration_ms: float = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal": self.goal,
            "steps": [
                {
                    "id": s.id, "action": s.action,
                    "capability": s.capability, "tool": s.tool,
                    "risk": s.risk.value, "notes": s.notes,
                }
                for s in self.steps
            ],
            "tools_required": self.tools_required,
            "estimated_cost": self.estimated_cost,
            "risk_level": self.risk_level.value,
            "estimated_duration_ms": self.estimated_duration_ms,
        }


@dataclass
class AgentOutput:
    """Structured output from an internal agent."""
    agent: AgentRole
    timestamp: float = field(default_factory=time.time)
    plan_input: Dict[str, Any] = field(default_factory=dict)
    plan_output: Dict[str, Any] = field(default_factory=dict)
    issues: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    score: float = 0.0
    approved: bool = True
    veto_reason: str = ""
    duration_ms: float = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent": self.agent.value,
            "timestamp": self.timestamp,
            "issues": self.issues,
            "suggestions": self.suggestions,
            "score": round(self.score, 3),
            "approved": self.approved,
            "veto_reason": self.veto_reason,
            "duration_ms": round(self.duration_ms, 1),
        }


@dataclass
class DeliberationResult:
    """Result of the full multi-agent deliberation."""
    goal: str
    initial_plan: ExecutionPlan
    final_plan: ExecutionPlan
    agent_outputs: List[AgentOutput]
    status: DecisionStatus
    agreement_rate: float = 0.0
    plan_rewrite_count: int = 0
    safety_blocked: bool = False
    optimization_gain: float = 0.0
    total_duration_ms: float = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal": self.goal,
            "status": self.status.value,
            "agreement_rate": round(self.agreement_rate, 3),
            "plan_rewrite_count": self.plan_rewrite_count,
            "safety_blocked": self.safety_blocked,
            "optimization_gain": round(self.optimization_gain, 3),
            "total_duration_ms": round(self.total_duration_ms, 1),
            "agents": [a.to_dict() for a in self.agent_outputs],
            "initial_steps": len(self.initial_plan.steps),
            "final_steps": len(self.final_plan.steps),
        }


# ── Agent weights for voting ───────────────────────────────────────

AGENT_WEIGHTS = {
    AgentRole.PLANNER: 1.0,
    AgentRole.CRITIC: 1.2,
    AgentRole.OPTIMIZER: 1.0,
    AgentRole.CAPABILITY: 1.3,
    AgentRole.SAFETY: 1.5,  # Highest — can veto
}


# ── Internal Agents ────────────────────────────────────────────────

class PlannerAgent:
    """
    Decomposes user goal into execution steps.
    Generates initial plan with tool selections.
    """

    def __init__(self):
        self._registry = get_capability_registry()
        self._tracker = get_performance_tracker()

    def generate_plan(self, goal: str, context: Dict[str, Any] = None) -> Tuple[ExecutionPlan, AgentOutput]:
        """Generate an initial execution plan."""
        start = time.time()
        issues = []
        suggestions = []

        # Analyze available capabilities
        hardware_hints = context.get("hardware_hints", []) if context else []
        candidates = self._registry.find_for_task(goal, hardware_hints)

        # Build steps
        steps = []
        tools = []
        goal_lower = goal.lower()

        # Step 1: Check if we have matching capabilities
        if candidates:
            best = candidates[0]
            steps.append(PlanStep(
                id=1,
                action=f"Execute using {best.name}",
                capability=best.name,
                tool=best.implementation,
            ))
            tools.append(best.name)

            # Add additional steps for multi-capability tasks
            if len(candidates) > 1:
                for i, cap in enumerate(candidates[1:3], 2):
                    steps.append(PlanStep(
                        id=i,
                        action=f"Use {cap.name} for additional processing",
                        capability=cap.name,
                        tool=cap.implementation,
                    ))
                    tools.append(cap.name)
        else:
            # No direct capability — plan for inference
            steps.append(PlanStep(
                id=1,
                action="Process via general inference",
                capability="general.inference",
                notes="No specific capability matched",
            ))
            suggestions.append("Consider creating a dedicated capability for this task type")

        # Estimate risk
        risk = RiskLevel.LOW
        if any(k in goal_lower for k in ["delete", "remove", "rm", "drop"]):
            risk = RiskLevel.HIGH
            issues.append("Plan involves destructive operations")
        elif any(k in goal_lower for k in ["system", "config", "install", "modify"]):
            risk = RiskLevel.MEDIUM

        plan = ExecutionPlan(
            goal=goal,
            steps=steps,
            tools_required=tools,
            risk_level=risk,
            estimated_duration_ms=sum(
                self._tracker.get_capability_metrics(t).get("avg_duration_ms", 100)
                for t in tools
            ),
        )

        output = AgentOutput(
            agent=AgentRole.PLANNER,
            plan_input={"goal": goal, "candidates": len(candidates)},
            plan_output=plan.to_dict(),
            issues=issues,
            suggestions=suggestions,
            score=0.8,
            approved=True,
            duration_ms=(time.time() - start) * 1000,
        )

        return plan, output


class CriticAgent:
    """
    Reviews plans for inefficiencies, risks, and missing steps.
    Suggests improvements.
    """

    def review_plan(self, plan: ExecutionPlan, context: Dict[str, Any] = None) -> AgentOutput:
        """Critically review an execution plan."""
        start = time.time()
        issues = []
        suggestions = []
        score = 1.0

        # Check for redundant steps
        caps_used = [s.capability for s in plan.steps if s.capability]
        if len(caps_used) != len(set(caps_used)):
            issues.append("Redundant capability calls detected — same capability used multiple times")
            suggestions.append("Consolidate duplicate capability calls into single invocation")
            score -= 0.15

        # Check for missing error handling
        has_error_step = any("error" in s.action.lower() or "fallback" in s.action.lower()
                           for s in plan.steps)
        if not has_error_step and len(plan.steps) > 1:
            suggestions.append("Add error handling step for multi-step plans")
            score -= 0.05

        # Check risk level
        if plan.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            issues.append(f"Plan risk level is {plan.risk_level.value}")
            suggestions.append("Add validation step before high-risk operations")
            score -= 0.2

        # Check for capability performance
        for tool in plan.tools_required:
            metrics = get_performance_tracker().get_capability_metrics(tool)
            if metrics.get("success_rate", 1.0) < 0.7:
                issues.append(f"Tool '{tool}' has low success rate ({metrics['success_rate']:.0%})")
                suggestions.append(f"Consider fallback for '{tool}' or pre-validation")
                score -= 0.1
            if metrics.get("avg_duration_ms", 0) > 5000:
                issues.append(f"Tool '{tool}' is slow (avg {metrics['avg_duration_ms']:.0f}ms)")
                suggestions.append(f"Consider timeout guard for '{tool}'")
                score -= 0.05

        # Check for missing compound skill opportunities
        if len(caps_used) >= 2:
            suggestions.append(
                f"Steps use {len(caps_used)} capabilities — "
                "check if a compound skill exists that combines them"
            )

        # Estimate efficiency
        if len(plan.steps) > 5:
            issues.append("Plan has many steps — consider simplification")
            suggestions.append("Look for steps that can be merged or parallelized")
            score -= 0.1

        score = max(0.0, min(1.0, score))

        return AgentOutput(
            agent=AgentRole.CRITIC,
            plan_input=plan.to_dict(),
            issues=issues,
            suggestions=suggestions,
            score=score,
            approved=score >= 0.5,
            duration_ms=(time.time() - start) * 1000,
        )


class OptimizerAgent:
    """
    Refines plans based on critic feedback.
    Reduces cost, improves speed, reduces tool usage.
    """

    def optimize_plan(self, plan: ExecutionPlan, critique: AgentOutput) -> Tuple[ExecutionPlan, AgentOutput]:
        """Optimize a plan based on critique."""
        start = time.time()
        issues = []
        suggestions = []
        rewrites = 0

        new_steps = list(plan.steps)  # Copy

        # Apply critic suggestions
        for suggestion in critique.suggestions:
            if "consolidate duplicate" in suggestion.lower():
                # Remove duplicate capability calls
                seen_caps = set()
                deduped = []
                for step in new_steps:
                    if step.capability not in seen_caps or not step.capability:
                        deduped.append(step)
                        seen_caps.add(step.capability)
                    else:
                        rewrites += 1
                new_steps = deduped

            elif "error handling" in suggestion.lower():
                # Add error handling step
                has_error = any("error" in s.action.lower() for s in new_steps)
                if not has_error:
                    max_id = max((s.id for s in new_steps), default=0)
                    new_steps.append(PlanStep(
                        id=max_id + 1,
                        action="Validate results and handle errors",
                        notes="Added by optimizer for error resilience",
                    ))
                    rewrites += 1

            elif "timeout guard" in suggestion.lower():
                # Mark slow steps with timeout notes
                for step in new_steps:
                    if step.capability:
                        metrics = get_performance_tracker().get_capability_metrics(step.capability)
                        if metrics.get("avg_duration_ms", 0) > 5000:
                            step.notes = f"TIMEOUT GUARD: {step.notes}" if step.notes else "TIMEOUT GUARD"
                            rewrites += 1

        # Re-number steps
        for i, step in enumerate(new_steps, 1):
            step.id = i

        # Calculate optimization gain
        original_steps = len(plan.steps)
        new_step_count = len(new_steps)
        gain = 0.0
        if original_steps > 0:
            gain = max(0, (original_steps - new_step_count) / original_steps)
            # Also gain from error handling additions
            if any("error" in s.action.lower() for s in new_steps) and not any("error" in s.action.lower() for s in plan.steps):
                gain += 0.1

        optimized = ExecutionPlan(
            goal=plan.goal,
            steps=new_steps,
            tools_required=plan.tools_required,
            risk_level=plan.risk_level,
            estimated_duration_ms=plan.estimated_duration_ms * 0.9 if rewrites > 0 else plan.estimated_duration_ms,
            metadata={"optimizer_rewrites": rewrites},
        )

        output = AgentOutput(
            agent=AgentRole.OPTIMIZER,
            plan_input=plan.to_dict(),
            plan_output=optimized.to_dict(),
            issues=issues,
            suggestions=suggestions,
            score=0.85,
            approved=True,
            duration_ms=(time.time() - start) * 1000,
        )

        return optimized, output


class CapabilityAgent:
    """
    Verifies available capabilities, checks performance scores,
    suggests skill substitutions or upgrades.
    """

    def __init__(self):
        self._registry = get_capability_registry()
        self._tracker = get_performance_tracker()

    def validate_capabilities(self, plan: ExecutionPlan) -> Tuple[ExecutionPlan, AgentOutput]:
        """Validate that all required capabilities exist and perform well."""
        start = time.time()
        issues = []
        suggestions = []

        new_steps = list(plan.steps)
        valid_tools = []

        for step in new_steps:
            if not step.capability:
                continue

            cap = self._registry.get(step.capability)

            if not cap:
                issues.append(f"Capability '{step.capability}' not found in registry")
                # Try to find substitute
                alternatives = self._registry.find_for_task(step.action)
                if alternatives:
                    best_alt = alternatives[0]
                    step.capability = best_alt.name
                    step.tool = best_alt.implementation
                    suggestions.append(
                        f"Substituted '{step.capability}' with '{best_alt.name}' "
                        f"(score: {best_alt.success_rate:.0%})"
                    )
                else:
                    step.notes = f"UNAVAILABLE: {step.notes}" if step.notes else "UNAVAILABLE"
                    issues.append(f"No alternative found for '{step.capability}'")
            else:
                # Check performance
                metrics = self._tracker.get_capability_metrics(step.capability)
                success_rate = metrics.get("success_rate", cap.success_rate)

                if success_rate < 0.5:
                    issues.append(
                        f"Capability '{step.capability}' has very low success rate ({success_rate:.0%})"
                    )
                    suggestions.append(f"Consider rebuilding or replacing '{step.capability}'")

                # Check for compound skill alternatives
                compound_candidates = [
                    c for c in self._registry.get_active()
                    if c.metadata.get("compound")
                    and step.capability in c.metadata.get("pipeline_steps", [])
                ]
                if compound_candidates:
                    best_compound = compound_candidates[0]
                    suggestions.append(
                        f"Compound skill '{best_compound.name}' includes '{step.capability}' "
                        f"— consider using it for better integration"
                    )

                valid_tools.append(step.capability)

        # Check if any compound skill covers multiple steps
        if len(valid_tools) >= 2:
            for cap in self._registry.get_active():
                if not cap.metadata.get("compound"):
                    continue
                pipeline = cap.metadata.get("pipeline_steps", [])
                covered = sum(1 for t in valid_tools if t in pipeline)
                if covered >= 2:
                    suggestions.append(
                        f"Compound skill '{cap.name}' covers {covered} of "
                        f"{len(valid_tools)} steps — consider using it"
                    )

        plan_out = ExecutionPlan(
            goal=plan.goal,
            steps=new_steps,
            tools_required=valid_tools,
            risk_level=plan.risk_level,
            estimated_duration_ms=plan.estimated_duration_ms,
        )

        output = AgentOutput(
            agent=AgentRole.CAPABILITY,
            plan_input=plan.to_dict(),
            plan_output=plan_out.to_dict(),
            issues=issues,
            suggestions=suggestions,
            score=0.9 if not issues else 0.6,
            approved=len([i for i in issues if "UNAVAILABLE" in i]) == 0,
            duration_ms=(time.time() - start) * 1000,
        )

        return plan_out, output


class SafetyAgent:
    """
    Validates sandbox constraints and execution safety.
    Can VETO any plan — highest authority in the agent system.
    """

    def validate_safety(self, plan: ExecutionPlan) -> AgentOutput:
        """Validate plan against safety rules."""
        start = time.time()
        issues = []
        suggestions = []
        veto = False
        veto_reason = ""

        # Check goal text for destructive patterns
        goal_lower = plan.goal.lower()
        for blocked in BLOCKED_COMMANDS:
            if blocked.lower() in goal_lower:
                issues.append(f"Goal contains blocked command pattern: '{blocked}'")
                veto = True
                veto_reason = f"Blocked command in goal: {blocked}"

        destructive_keywords = [
            "rm -rf", "delete all", "drop table", "truncate",
            "format disk", "mkfs", "dd if=",
        ]
        for kw in destructive_keywords:
            if kw in goal_lower:
                issues.append(f"Goal is destructive: '{kw}'")
                veto = True
                veto_reason = f"Destructive goal: {kw}"

        # Check risk level
        if plan.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            issues.append(f"Plan risk level is {plan.risk_level.value}")
            suggestions.append("Add validation step before high-risk operations")

        for step in plan.steps:
            action_lower = step.action.lower()

            # Check for blocked commands
            for blocked in BLOCKED_COMMANDS:
                if blocked.lower() in action_lower:
                    issues.append(f"Step {step.id} contains blocked command pattern: '{blocked}'")
                    veto = True
                    veto_reason = f"Blocked command detected: {blocked}"

            # Check for destructive operations
            destructive_keywords = [
                "rm -rf", "delete all", "drop table", "truncate",
                "format disk", "mkfs", "dd if=",
            ]
            for kw in destructive_keywords:
                if kw in action_lower:
                    issues.append(f"Step {step.id} is destructive: '{kw}'")
                    veto = True
                    veto_reason = f"Destructive operation: {kw}"

            # Check for unsandboxed execution
            if "shell" in step.tool.lower() or "exec" in step.tool.lower():
                if not step.notes or "sandbox" not in step.notes.lower():
                    suggestions.append(f"Step {step.id} should run in sandbox")
                    step.notes = f"SANDBOX REQUIRED: {step.notes}" if step.notes else "SANDBOX REQUIRED"

            # Check for network operations
            if any(k in action_lower for k in ["curl", "wget", "download", "upload", "fetch"]):
                suggestions.append(f"Step {step.id} involves network — validate target")

            # Check for file system operations outside allowed dirs
            if any(k in action_lower for k in ["/etc/", "/var/", "/usr/", "/root/"]):
                if not any(k in action_lower for k in ["read", "list", "check", "inspect"]):
                    issues.append(f"Step {step.id} modifies system directories")
                    veto = True
                    veto_reason = f"System directory modification in step {step.id}"

        # Risk escalation
        if plan.risk_level == RiskLevel.CRITICAL:
            issues.append("Plan risk level is CRITICAL — requires manual approval")
            suggestions.append("Add confirmation step before critical operations")

        score = 1.0
        if veto:
            score = 0.0
        elif issues:
            score = max(0.3, 1.0 - len(issues) * 0.2)

        return AgentOutput(
            agent=AgentRole.SAFETY,
            plan_input=plan.to_dict(),
            issues=issues,
            suggestions=suggestions,
            score=score,
            approved=not veto,
            veto_reason=veto_reason,
            duration_ms=(time.time() - start) * 1000,
        )


# ── Agent Orchestrator ─────────────────────────────────────────────

class AgentOrchestrator:
    """
    Orchestrates multi-agent internal deliberation.

    Flow: user request → Planner → Critic → Optimizer → Capability → Safety → final plan

    Uses weighted voting when agents disagree.
    Safety agent has veto power.
    All agent outputs are logged.
    """

    def __init__(self):
        self._planner = PlannerAgent()
        self._critic = CriticAgent()
        self._optimizer = OptimizerAgent()
        self._capability = CapabilityAgent()
        self._safety = SafetyAgent()
        self._history: List[DeliberationResult] = []

    def deliberate(self, goal: str, context: Dict[str, Any] = None) -> DeliberationResult:
        """
        Full multi-agent deliberation on a goal.

        Returns DeliberationResult with the final approved plan
        and full audit trail of all agent deliberations.
        """
        start = time.time()
        agent_outputs = []
        rewrites = 0

        # ── Step 1: Planner generates initial plan ──────────────────
        plan, planner_out = self._planner.generate_plan(goal, context)
        agent_outputs.append(planner_out)
        initial_plan = ExecutionPlan(
            goal=plan.goal,
            steps=list(plan.steps),
            tools_required=list(plan.tools_required),
            risk_level=plan.risk_level,
            estimated_duration_ms=plan.estimated_duration_ms,
        )

        # ── Step 2: Critic reviews the plan ─────────────────────────
        critic_out = self._critic.review_plan(plan, context)
        agent_outputs.append(critic_out)

        # ── Step 3: Optimizer refines based on critique ─────────────
        if critic_out.suggestions:
            plan, optimizer_out = self._optimizer.optimize_plan(plan, critic_out)
            rewrites += plan.metadata.get("optimizer_rewrites", 0)
        else:
            optimizer_out = AgentOutput(
                agent=AgentRole.OPTIMIZER,
                score=1.0,
                approved=True,
                suggestions=["No optimizations needed — plan is already efficient"],
            )
        agent_outputs.append(optimizer_out)

        # ── Step 4: Capability agent validates tools ─────────────────
        plan, cap_out = self._capability.validate_capabilities(plan)
        agent_outputs.append(cap_out)

        # ── Step 5: Safety agent validates and potentially vetoes ───
        safety_out = self._safety.validate_safety(plan)
        agent_outputs.append(safety_out)

        # ── Step 6: Weighted voting ─────────────────────────────────
        agreement_rate = self._calculate_agreement(agent_outputs)
        status = self._determine_status(agent_outputs, safety_out)

        # If safety vetoes, mark plan as vetoed
        safety_blocked = not safety_out.approved
        if safety_blocked:
            status = DecisionStatus.VETOED

        # Calculate optimization gain
        optimization_gain = 0.0
        if initial_plan.steps and plan.steps:
            step_diff = len(initial_plan.steps) - len(plan.steps)
            optimization_gain = max(0, step_diff / len(initial_plan.steps))
            # Also count error handling additions as gain
            has_error_handling = any("error" in s.action.lower() for s in plan.steps)
            if has_error_handling and not any("error" in s.action.lower() for s in initial_plan.steps):
                optimization_gain += 0.15

        result = DeliberationResult(
            goal=goal,
            initial_plan=initial_plan,
            final_plan=plan,
            agent_outputs=agent_outputs,
            status=status,
            agreement_rate=agreement_rate,
            plan_rewrite_count=rewrites,
            safety_blocked=safety_blocked,
            optimization_gain=optimization_gain,
            total_duration_ms=(time.time() - start) * 1000,
        )

        self._history.append(result)
        return result

    def _calculate_agreement(self, outputs: List[AgentOutput]) -> float:
        """
        Calculate weighted agreement rate among agents.
        Uses agent weights for scoring.
        """
        if not outputs:
            return 0.0

        weighted_sum = 0.0
        weight_total = 0.0

        for out in outputs:
            weight = AGENT_WEIGHTS.get(out.agent, 1.0)
            weighted_sum += (1.0 if out.approved else 0.0) * weight
            weight_total += weight

        return weighted_sum / weight_total if weight_total > 0 else 0.0

    def _determine_status(self, outputs: List[AgentOutput],
                          safety_out: AgentOutput) -> DecisionStatus:
        """Determine final decision status."""
        if not safety_out.approved:
            return DecisionStatus.VETOED

        approvals = sum(1 for o in outputs if o.approved)
        total = len(outputs)

        if approvals == total:
            return DecisionStatus.APPROVED
        elif approvals >= total * 0.6:
            return DecisionStatus.MODIFIED
        else:
            return DecisionStatus.REJECTED

    def get_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent deliberation history."""
        return [d.to_dict() for d in self._history[-limit:]]

    def get_stats(self) -> Dict[str, Any]:
        """Get orchestrator statistics."""
        if not self._history:
            return {"total_deliberations": 0}

        total = len(self._history)
        approved = sum(1 for d in self._history if d.status == DecisionStatus.APPROVED)
        vetoed = sum(1 for d in self._history if d.status == DecisionStatus.VETOED)
        modified = sum(1 for d in self._history if d.status == DecisionStatus.MODIFIED)

        avg_agreement = sum(d.agreement_rate for d in self._history) / total
        avg_rewrites = sum(d.plan_rewrite_count for d in self._history) / total
        avg_gain = sum(d.optimization_gain for d in self._history) / total

        return {
            "total_deliberations": total,
            "approved": approved,
            "vetoed": vetoed,
            "modified": modified,
            "avg_agreement_rate": round(avg_agreement, 3),
            "avg_plan_rewrites": round(avg_rewrites, 1),
            "avg_optimization_gain": round(avg_gain, 3),
            "safety_block_rate": round(vetoed / total, 3) if total > 0 else 0,
        }


# Singleton
_orchestrator: Optional[AgentOrchestrator] = None


def get_agent_orchestrator() -> AgentOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = AgentOrchestrator()
    return _orchestrator
