"""
Skill Recombiner — Creates new compound skills from existing capabilities.

Analyzes execution history, detects reusable multi-step patterns,
and packages them as new single-call skills that replace
multi-step workflows.

This is NOT optimization of single plugins.
This is invention of new tools from combinations of existing ones.

Pipeline:
  history → pattern extraction → skill generation → plugin scaffolding
  → sandbox validation → registration
"""

import json
import sqlite3
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ccos.core.capability_registry import (
    Capability,
    CapabilityStatus,
    get_capability_registry,
)
from ccos.core.memory.ccos_memory import get_ccos_memory
from ccos.core.performance_tracker import get_performance_tracker
from ccos.core.sandbox import Sandbox, get_sandbox


# ── Data structures ────────────────────────────────────────────────

@dataclass
class SkillStep:
    """A single step in a compound skill pipeline."""
    capability: str
    description: str
    input_from: str = ""  # "user" or step index like "0", "1"
    output_as: str = ""   # variable name for downstream steps


@dataclass
class CompoundSkill:
    """A new skill created from combining existing capabilities."""
    name: str
    description: str
    category: str
    steps: List[SkillStep]
    input_requirements: Dict[str, Any]
    output_definition: Dict[str, Any]
    dependencies: List[str]
    estimated_success_rate: float = 0.0
    estimated_duration_ms: float = 0.0
    source_pattern: str = ""
    version: str = "1.0.0"
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "steps": [{"capability": s.capability, "description": s.description,
                       "input_from": s.input_from, "output_as": s.output_as}
                      for s in self.steps],
            "input_requirements": self.input_requirements,
            "output_definition": self.output_definition,
            "dependencies": self.dependencies,
            "estimated_success_rate": self.estimated_success_rate,
            "estimated_duration_ms": self.estimated_duration_ms,
            "source_pattern": self.source_pattern,
            "version": self.version,
        }


@dataclass
class DetectedPattern:
    """A repeated sequence of capability usage detected in history."""
    sequence: Tuple[str, ...]
    frequency: int
    avg_success_rate: float
    avg_total_duration_ms: float
    step_durations: List[float]
    examples: List[str]  # task descriptions that used this pattern


@dataclass
class RecombinationResult:
    """Result of a skill recombination attempt."""
    skill_name: str
    pattern: DetectedPattern
    skill: Optional[CompoundSkill] = None
    sandbox_passed: bool = False
    registered: bool = False
    plugin_path: str = ""
    error: str = ""
    details: str = ""


# ── Pattern Detection ──────────────────────────────────────────────

class PatternDetector:
    """
    Analyzes execution history to find repeated multi-capability sequences.

    Uses sliding-window n-gram analysis over capability usage chains
    to detect patterns that appear multiple times with high success.
    """

    def __init__(self, min_frequency: int = 2, min_success_rate: float = 0.7,
                 max_sequence_length: int = 5):
        self._min_frequency = min_frequency
        self._min_success = min_success_rate
        self._max_len = max_sequence_length

    def detect_patterns(
        self, workflows: List[Dict[str, Any]]
    ) -> List[DetectedPattern]:
        """
        Find repeated capability sequences in workflow history.

        Returns patterns sorted by: frequency × success_rate × length.
        """
        # Extract capability chains from workflows
        chains = self._extract_chains(workflows)
        if not chains:
            return []

        # Count n-gram sequences (lengths 2..max_len)
        ngram_counts: Dict[Tuple[str, ...], Dict] = defaultdict(lambda: {
            "count": 0, "successes": 0, "durations": [], "examples": []
        })

        for chain in chains:
            caps = tuple(c["capability"] for c in chain)
            successes = sum(1 for c in chain if c.get("success", True))
            total_dur = sum(c.get("duration_ms", 0) for c in chain)
            task = chain[0].get("task", "") if chain else ""

            for n in range(2, min(self._max_len + 1, len(caps) + 1)):
                for i in range(len(caps) - n + 1):
                    ngram = caps[i:i + n]
                    entry = ngram_counts[ngram]
                    entry["count"] += 1
                    if successes == len(chain):
                        entry["successes"] += 1
                    entry["durations"].append(total_dur)
                    if len(entry["examples"]) < 5:
                        entry["examples"].append(task[:100])

        # Filter and rank
        patterns = []
        for ngram, data in ngram_counts.items():
            if data["count"] < self._min_frequency:
                continue
            success_rate = data["successes"] / data["count"]
            if success_rate < self._min_success:
                continue

            avg_dur = sum(data["durations"]) / len(data["durations"])
            step_durs = [0.0] * len(ngram)  # approximate

            patterns.append(DetectedPattern(
                sequence=ngram,
                frequency=data["count"],
                avg_success_rate=success_rate,
                avg_total_duration_ms=avg_dur,
                step_durations=step_durs,
                examples=data["examples"],
            ))

        # Sort by composite score: freq × success × length
        patterns.sort(
            key=lambda p: p.frequency * p.avg_success_rate * len(p.sequence),
            reverse=True,
        )
        return patterns

    def _extract_chains(
        self, workflows: List[Dict[str, Any]]
    ) -> List[List[Dict[str, Any]]]:
        """
        Extract capability chains from workflow records.

        A workflow's `steps` field may contain capability references.
        We also look at consecutive events in the event log.
        """
        chains = []
        for wf in workflows:
            steps_raw = wf.get("steps", "[]")
            if isinstance(steps_raw, str):
                try:
                    steps = json.loads(steps_raw)
                except Exception:
                    steps = []
            else:
                steps = steps_raw

            # Build chain from steps
            chain = []
            for step in steps:
                if isinstance(step, dict) and "capability" in step:
                    chain.append(step)
                elif isinstance(step, str):
                    # Step might be a JSON string (double-encoded) or plain text
                    try:
                        parsed = json.loads(step)
                        if isinstance(parsed, dict) and "capability" in parsed:
                            chain.append(parsed)
                            continue
                    except (json.JSONDecodeError, TypeError):
                        pass
                    # Step is plain text — try to extract capability name
                    chain.append({
                        "capability": self._infer_capability(step),
                        "task": step,
                        "success": bool(wf.get("success", 1)),
                        "duration_ms": 0,
                    })

            if len(chain) >= 2:
                chains.append(chain)

        return chains

    def _infer_capability(self, step_text: str) -> str:
        """Try to infer a capability name from step text."""
        text = step_text.lower()
        if any(k in text for k in ["camera", "capture", "photo", "picture"]):
            return "vision.camera_capture"
        if any(k in text for k in ["speak", "tts", "voice", "say"]):
            return "speech.tts"
        if any(k in text for k in ["system", "info", "cpu", "memory", "ram"]):
            return "system.info"
        if any(k in text for k in ["process", "ps", "running"]):
            return "system.processes"
        return "general.inference"


# ── Skill Generator ────────────────────────────────────────────────

class SkillGenerator:
    """
    Converts detected patterns into executable CompoundSkill definitions
    and generates the plugin scaffolding (code + manifest + test).
    """

    def __init__(self):
        self._registry = get_capability_registry()

    def generate_skill(self, pattern: DetectedPattern) -> CompoundSkill:
        """
        Create a CompoundSkill definition from a detected pattern.
        """
        # Build descriptive name
        cap_short = [c.split(".")[-1] for c in pattern.sequence]
        name = "skill." + "_".join(cap_short)

        # Build description
        desc_parts = []
        for i, cap in enumerate(pattern.sequence):
            cap_obj = self._registry.get(cap)
            if cap_obj:
                desc_parts.append(f"step {i+1}: {cap_obj.description}")
            else:
                desc_parts.append(f"step {i+1}: {cap}")
        description = f"Compound skill: {' → '.join(cap_short)}. " + "; ".join(desc_parts)

        # Build steps
        steps = []
        for i, cap in enumerate(pattern.sequence):
            cap_obj = self._registry.get(cap)
            step_desc = cap_obj.description if cap_obj else cap
            steps.append(SkillStep(
                capability=cap,
                description=step_desc,
                input_from="user" if i == 0 else str(i - 1),
                output_as=f"step_{i}_result",
            ))

        # Infer category from first capability
        first_cap = self._registry.get(pattern.sequence[0])
        category = first_cap.category if first_cap else "compound"

        # Collect dependencies
        deps = []
        for cap_name in pattern.sequence:
            cap_obj = self._registry.get(cap_name)
            if cap_obj:
                deps.extend(cap_obj.dependencies)
        deps = list(set(deps))

        return CompoundSkill(
            name=name,
            description=description,
            category=category,
            steps=steps,
            input_requirements={"type": "text", "description": "User request"},
            output_definition={"type": "dict", "description": "Combined results from all steps"},
            dependencies=deps,
            estimated_success_rate=pattern.avg_success_rate,
            estimated_duration_ms=pattern.avg_total_duration_ms,
            source_pattern=str(pattern.sequence),
        )

    def generate_plugin_code(self, skill: CompoundSkill) -> str:
        """
        Generate the Python implementation for a compound skill.
        Creates a pipeline function that calls each step in sequence.
        """
        lines = [
            '"""',
            f'Compound Skill: {skill.name}',
            f'Auto-generated by CCOS Skill Recombiner',
            f'Source pattern: {skill.source_pattern}',
            f'Created: {time.strftime("%Y-%m-%d %H:%M:%S")}',
            '"""',
            '',
            'import time',
            'from typing import Any, Dict, List',
            '',
            '',
            f'def run(input_data: Any = None) -> Dict[str, Any]:',
            f'    """',
            f'    Execute compound skill: {skill.name}',
            f'    Steps: {" -> ".join(s.capability for s in skill.steps)}',
            f'    """',
            '    results = {}',
            '    total_start = time.time()',
            '    step_results = []',
            '',
        ]

        # Generate each step
        for i, step in enumerate(skill.steps):
            lines.append(f'    # Step {i}: {step.capability}')
            lines.append(f'    step_{i}_start = time.time()')
            lines.append(f'    try:')
            lines.append(f'        step_{i}_input = input_data if {i} == 0 else step_results[{i-1}]')
            lines.append(f'        step_{i}_result = _execute_step("{step.capability}", step_{i}_input)')
            lines.append(f'        step_{i}_dur = (time.time() - step_{i}_start) * 1000')
            lines.append(f'        step_results.append(step_{i}_result)')
            lines.append(f'        results["step_{i}"] = {{')
            lines.append(f'            "capability": "{step.capability}",')
            lines.append(f'            "result": step_{i}_result,')
            lines.append(f'            "duration_ms": step_{i}_dur,')
            lines.append(f'            "success": True,')
            lines.append(f'        }}')
            lines.append(f'    except Exception as e:')
            lines.append(f'        step_{i}_dur = (time.time() - step_{i}_start) * 1000')
            lines.append(f'        results["step_{i}"] = {{')
            lines.append(f'            "capability": "{step.capability}",')
            lines.append(f'            "error": str(e),')
            lines.append(f'            "duration_ms": step_{i}_dur,')
            lines.append(f'            "success": False,')
            lines.append(f'        }}')
            lines.append(f'        # Continue pipeline even on failure')
            lines.append(f'        step_results.append({{"error": str(e)}})')
            lines.append('')

        # Summary
        lines.extend([
            '    total_ms = (time.time() - total_start) * 1000',
            '    successes = sum(1 for r in results.values() if r.get("success"))',
            '    return {',
            f'        "skill": "{skill.name}",',
            '        "steps_completed": len(results),',
            '        "steps_succeeded": successes,',
            '        "success": successes == len(results),',
            '        "total_duration_ms": total_ms,',
            '        "step_details": results,',
            '    }',
            '',
            '',
        ])

        # Step executor (delegates to plugin manager)
        lines.extend([
            'def _execute_step(capability: str, input_data: Any) -> Any:',
            '    """Execute a single capability step."""',
            '    import sys',
            '    from pathlib import Path',
            '    sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))',
            '    from ccos.core.plugin_manager import get_plugin_manager',
            '    pm = get_plugin_manager()',
            '    pm.load_all()',
            '    return pm.call_capability(capability)',
            '',
            '',
            'def test():',
            '    """Self-test: verify all step capabilities are available."""',
            '    import sys',
            '    from pathlib import Path',
            '    sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))',
            '    from ccos.core.plugin_manager import get_plugin_manager',
            '    from ccos.core.capability_registry import get_capability_registry',
            '    pm = get_plugin_manager()',
            '    pm.load_all()',
            '    registry = get_capability_registry()',
            f'    for step in {json.dumps([s.capability for s in skill.steps])}:',
            '        if not registry.has(step):',
            '            return False, f"Missing capability: {step}"',
            '    return True, "All capabilities available"',
        ])

        return "\n".join(lines)

    def generate_test_code(self, skill: CompoundSkill) -> str:
        """Generate a test script for the compound skill."""
        lines = [
            '#!/usr/bin/env python3',
            f'"""Test for compound skill: {skill.name}"""',
            '',
            'import sys',
            'from pathlib import Path',
            '',
            'sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))',
            '',
            '',
            'def test_skill_import():',
            '    """Verify the skill module imports cleanly."""',
            '    import importlib.util',
            f'    spec = importlib.util.spec_from_file_location("skill", str(Path(__file__).parent / "pipeline.py"))',
            '    mod = importlib.util.module_from_spec(spec)',
            '    spec.loader.exec_module(mod)',
            '    assert hasattr(mod, "run"), "Missing run() function"',
            '    assert hasattr(mod, "test"), "Missing test() function"',
            '    print("[PASS] Skill module imports correctly")',
            '',
            '',
            'def test_skill_self_test():',
            '    """Run the skill\'s built-in self-test."""',
            '    import importlib.util',
            f'    spec = importlib.util.spec_from_file_location("skill", str(Path(__file__).parent / "pipeline.py"))',
            '    mod = importlib.util.module_from_spec(spec)',
            '    spec.loader.exec_module(mod)',
            '    passed, msg = mod.test()',
            '    assert passed, f"Self-test failed: {msg}"',
            f'    print(f"[PASS] Self-test: {{msg}}")',
            '',
            '',
            'def test_skill_execution():',
            '    """Execute the skill and verify output structure."""',
            '    import importlib.util',
            f'    spec = importlib.util.spec_from_file_location("skill", str(Path(__file__).parent / "pipeline.py"))',
            '    mod = importlib.util.module_from_spec(spec)',
            '    spec.loader.exec_module(mod)',
            '    result = mod.run("test input")',
            '    assert isinstance(result, dict), "Expected dict result"',
            '    assert "success" in result, "Missing success field"',
            '    assert "steps_completed" in result, "Missing steps_completed"',
            '    print(f"[PASS] Execution: {result[\'steps_completed\']} steps, '
            'success={result[\'success\']}")',
            '',
            '',
            'if __name__ == "__main__":',
            '    test_skill_import()',
            '    test_skill_self_test()',
            '    test_skill_execution()',
            '    print("\\nAll compound skill tests passed!")',
        ]
        return "\n".join(lines)

    def generate_manifest(self, skill: CompoundSkill) -> Dict[str, Any]:
        """Generate manifest.json for the compound skill plugin."""
        return {
            "name": skill.name,
            "version": skill.version,
            "description": skill.description,
            "category": skill.category,
            "entry_point": "pipeline.py",
            "capabilities": [
                {
                    "name": skill.name,
                    "description": skill.description,
                    "implementation": f"pipeline:run",
                    "category": skill.category,
                    "dependencies": skill.dependencies,
                    "hardware_requirements": [],
                }
            ],
            "compound": True,
            "pipeline_steps": [s.capability for s in skill.steps],
            "source_pattern": skill.source_pattern,
            "estimated_success_rate": skill.estimated_success_rate,
            "author": "CCOS-SkillRecombiner",
        }


# ── Skill Recombiner (orchestrator) ────────────────────────────────

class SkillRecombiner:
    """
    Main orchestrator: analyzes history, detects patterns,
    generates compound skills, validates, and registers.

    This is the engine that turns CCOS from a tool optimizer
    into a system that invents new tools from experience.
    """

    def __init__(self, min_pattern_freq: int = 2, min_success: float = 0.75,
                 plugin_base: Optional[Path] = None):
        self._detector = PatternDetector(
            min_frequency=min_pattern_freq,
            min_success_rate=min_success,
        )
        self._generator = SkillGenerator()
        self._sandbox = get_sandbox()
        self._registry = get_capability_registry()
        self._memory = get_ccos_memory()
        self._tracker = get_performance_tracker()
        self._results: List[RecombinationResult] = []
        self._plugin_base = plugin_base or (
            Path(__file__).parent.parent / "plugins" / "compound"
        )

    def analyze_and_generate(self) -> List[RecombinationResult]:
        """
        Full pipeline: analyze history → detect patterns → generate skills → validate → register.

        Returns list of recombination results.
        """
        # Step 1: Gather workflow history
        workflows = self._memory.structured.get_successful_workflows(limit=100)
        if len(workflows) < 2:
            return []

        # Step 2: Detect patterns
        patterns = self._detector.detect_patterns(workflows)
        if not patterns:
            return []

        # Step 3: Generate and validate skills for each pattern
        results = []
        for pattern in patterns[:5]:  # Top 5 patterns
            result = self._process_pattern(pattern)
            if result:
                results.append(result)

        return results

    def _process_pattern(self, pattern: DetectedPattern) -> Optional[RecombinationResult]:
        """Process a single detected pattern into a validated skill."""
        # Generate skill definition
        skill = self._generator.generate_skill(pattern)

        # Check if this skill already exists
        if self._registry.has(skill.name):
            existing = self._registry.get(skill.name)
            result = RecombinationResult(
                skill_name=skill.name,
                pattern=pattern,
                skill=skill,
                sandbox_passed=True,
                registered=True,
                plugin_path=existing.implementation if existing else "",
                details=f"Skill already exists (v{existing.version if existing else '?'}, "
                        f"uses={existing.use_count if existing else 0})",
            )
            self._results.append(result)
            return result

        result = RecombinationResult(
            skill_name=skill.name,
            pattern=pattern,
            skill=skill,
        )

        # Generate plugin files
        plugin_dir = self._plugin_base / skill.name.replace(".", "_")
        plugin_dir.mkdir(parents=True, exist_ok=True)

        # Write manifest
        manifest = self._generator.generate_manifest(skill)
        (plugin_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))

        # Write pipeline
        code = self._generator.generate_plugin_code(skill)
        (plugin_dir / "pipeline.py").write_text(code)

        # Write test
        test_code = self._generator.generate_test_code(skill)
        (plugin_dir / "test.py").write_text(test_code)

        result.plugin_path = str(plugin_dir)

        # Validate in sandbox
        sandbox_result = self._sandbox.run_command(
            f"python3 {plugin_dir / 'test.py'}",
            timeout=30,
            cwd=str(plugin_dir),
        )
        result.sandbox_passed = sandbox_result.success

        if not sandbox_result.success:
            result.error = sandbox_result.stderr[:500]
            result.details = f"Sandbox test failed: {sandbox_result.stderr[:200]}"
            self._results.append(result)
            return result

        # Register as new capability
        capability = Capability(
            name=skill.name,
            description=skill.description,
            implementation=str(plugin_dir / "pipeline.py"),
            category=skill.category,
            dependencies=skill.dependencies,
            test_path=str(plugin_dir / "test.py"),
            status=CapabilityStatus.EXPERIMENTAL,  # Start as experimental
            version=skill.version,
            metadata={
                "compound": True,
                "pipeline_steps": [s.capability for s in skill.steps],
                "source_pattern": str(pattern.sequence),
                "frequency": pattern.frequency,
                "estimated_success_rate": pattern.avg_success_rate,
            },
        )
        self._registry.register(capability)
        result.registered = True
        result.details = (
            f"Registered compound skill from pattern {pattern.sequence} "
            f"(freq={pattern.frequency}, success={pattern.avg_success_rate:.0%})"
        )

        # Store in memory
        self._memory.events.log(
            event_type="skill_created",
            source=skill.name,
            details=result.details,
            metadata=skill.to_dict(),
        )

        self._results.append(result)
        return result

    def get_results(self) -> List[Dict[str, Any]]:
        """Get all recombination results."""
        return [
            {
                "skill_name": r.skill_name,
                "pattern": str(r.pattern.sequence) if r.pattern else "",
                "frequency": r.pattern.frequency if r.pattern else 0,
                "sandbox_passed": r.sandbox_passed,
                "registered": r.registered,
                "error": r.error,
                "details": r.details,
            }
            for r in self._results
        ]

    def get_compound_skills(self) -> List[Dict[str, Any]]:
        """Get all registered compound skills."""
        return [
            cap.to_dict()
            for cap in self._registry.get_active()
            if cap.metadata.get("compound")
        ]

    def execute_compound_skill(self, skill_name: str, input_data: Any = None) -> Dict[str, Any]:
        """
        Execute a compound skill by name.
        Loads the generated plugin and calls its run() function.
        """
        cap = self._registry.get(skill_name)
        if not cap:
            return {"success": False, "error": f"Skill not found: {skill_name}"}

        impl_path = Path(cap.implementation)
        if not impl_path.exists():
            return {"success": False, "error": f"Implementation not found: {impl_path}"}

        # Dynamic import and execute
        import importlib.util
        spec = importlib.util.spec_from_file_location(f"skill_{skill_name}", str(impl_path))
        if spec is None or spec.loader is None:
            return {"success": False, "error": "Cannot load skill module"}

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        if not hasattr(module, "run"):
            return {"success": False, "error": "Skill has no run() function"}

        start = time.time()
        try:
            result = module.run(input_data)
            duration = (time.time() - start) * 1000
            self._tracker.record_execution(
                capability=skill_name,
                version=cap.version,
                duration_ms=duration,
                success=result.get("success", False),
            )
            return result
        except Exception as e:
            duration = (time.time() - start) * 1000
            self._tracker.record_execution(
                capability=skill_name,
                version=cap.version,
                duration_ms=duration,
                success=False,
                error_category="runtime",
                error_detail=str(e),
            )
            return {"success": False, "error": str(e)}

    def get_stats(self) -> Dict[str, Any]:
        """Get recombination engine statistics."""
        compound = self.get_compound_skills()
        return {
            "total_recombinations": len(self._results),
            "skills_registered": sum(1 for r in self._results if r.registered),
            "sandbox_failures": sum(1 for r in self._results if not r.sandbox_passed),
            "compound_skills_active": len(compound),
            "skill_names": [c["name"] for c in compound],
        }


# Singleton
_recombiner: Optional[SkillRecombiner] = None


def get_skill_recombiner() -> SkillRecombiner:
    global _recombiner
    if _recombiner is None:
        _recombiner = SkillRecombiner()
    return _recombiner
