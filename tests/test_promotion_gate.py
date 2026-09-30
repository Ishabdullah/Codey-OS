"""Promotion gate + CODEY_SELF_IMPROVE switch (AGI audit 2.3/2.4)."""
import json
import random

import pytest

from bench import gate
from bench.stats import mcnemar_exact
from ccos.core import self_improve as si


def rows(label, results, h="H"):
    return [{"label": label, "task": f"t{i}", "rep": 0, "passed": r, "suite_hash": h}
            for i, r in enumerate(results)]


def test_switch_default_off_and_unknown_is_off(monkeypatch):
    monkeypatch.delenv("CODEY_SELF_IMPROVE", raising=False)
    assert si.mode() == "off" and not si.enabled() and not si.may_deploy()
    monkeypatch.setenv("CODEY_SELF_IMPROVE", "banana")
    assert si.mode() == "off"
    monkeypatch.setenv("CODEY_SELF_IMPROVE", "shadow")
    assert si.enabled() and not si.may_deploy()
    monkeypatch.setenv("CODEY_SELF_IMPROVE", "ON")
    assert si.may_deploy()


def test_gate_rejects_small_sample_even_if_all_wins():
    d = gate.decide(rows("a", [False] * 8), rows("b", [True] * 8))
    assert not d.promote and any("paired results" in r for r in d.reasons)


def test_gate_promotes_clear_win_without_regressions():
    base = [False] * 20 + [True] * 20
    cand = [True] * 20 + [True] * 20
    d = gate.decide(rows("a", base), rows("b", cand))
    assert d.promote, d.reasons


def test_gate_blocks_regression_even_with_net_gain():
    base = [False] * 20 + [True] * 20
    cand = [True] * 20 + [True] * 19 + [False]
    d = gate.decide(rows("a", base), rows("b", cand))
    assert not d.promote and any("regression" in r for r in d.reasons)


def test_gate_rejects_different_suite_versions():
    d = gate.decide(rows("a", [True] * 40, "H1"), rows("b", [True] * 40, "H2"))
    assert not d.promote and "not comparable" in d.reasons[0]


def test_no_evaluator_never_promotes():
    assert gate.no_evaluator().promote is False


def test_aa_false_accept_rate_is_low():
    """Two samples of the SAME 70% agent: gate must almost never promote (measured, not assumed)."""
    rng = random.Random(1)
    trials, fa = 300, 0
    for _ in range(trials):
        a = [rng.random() < 0.7 for _ in range(40)]
        b = [rng.random() < 0.7 for _ in range(40)]
        fa += gate.decide(rows("a", a), rows("b", b)).promote
    assert fa / trials <= 0.05, fa / trials


def test_promote_cli_writes_ledger_and_exit_code(tmp_path):
    from bench import promote
    led = tmp_path / "l.jsonl"
    with open(led, "w") as f:
        for r in rows("a", [False] * 40) + rows("b", [True] * 40):
            f.write(json.dumps(r) + "\n")
    exp = tmp_path / "exp.jsonl"
    assert promote.main([str(led), "a", "b", "--experiments", str(exp)]) == 0
    assert promote.main([str(led), "a", "a", "--experiments", str(exp)]) == 1
    assert len(exp.read_text().splitlines()) == 2


def test_modules_are_inert_when_off(monkeypatch):
    monkeypatch.delenv("CODEY_SELF_IMPROVE", raising=False)
    from ccos.core.auto_improvement_loop import AutoImprovementLoop
    from ccos.core.capability_optimizer import CapabilityOptimizer
    from ccos.core.goal_engine import GoalEngine
    from ccos.core.skill_recombiner import SkillRecombiner
    assert CapabilityOptimizer.optimize(object.__new__(CapabilityOptimizer), "x") is None
    assert GoalEngine.analyze_and_generate(object.__new__(GoalEngine)) == []
    assert GoalEngine.inject_into_planner(object.__new__(GoalEngine)) is None
    assert SkillRecombiner.analyze_and_generate(object.__new__(SkillRecombiner)) == []


def test_no_runtime_core_imports_self_improvement():
    """Live agent (core/, tools/, main.py) must not import the self-improvement modules."""
    import re
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    pat = re.compile(r"(goal_engine|auto_improvement_loop|capability_optimizer|skill_recombiner)")
    hits = []
    for base in ("core", "tools", "utils"):
        for p in (root / base).rglob("*.py"):
            for ln in p.read_text(errors="ignore").splitlines():
                if re.match(r"\s*(from|import)\s", ln) and pat.search(ln):
                    hits.append(f"{p.name}: {ln.strip()}")
    assert not hits, hits
