"""WP2.1 slice 14f: generated-artifact boundaries (NEW-976, NEW-980, NEW-981).

Recombiner candidates stage OUTSIDE the plugin discovery roots and the
sandbox ALLOWED_DIRS, and are promoted only after an approving GateDecision
AND a HIGH_IMPACT gateway confirmation. The optimizer's deploy copy is
contained to approved plugin roots. Everything here uses tmp dirs, fake
sandbox/memory/registry; nothing touches the real ccos/plugins tree, the real
CCOS DB, models, network or subprocesses.
"""

import json
import os
from pathlib import Path

import pytest

import ccos.core.capability_optimizer as co
import ccos.core.skill_recombiner as sr
from bench.gate import GateDecision, no_evaluator
from ccos.core.capability_registry import Capability, CapabilityRegistry, CapabilityStatus
from ccos.core.memory.ccos_memory import CCOSMemory
from ccos.core.sandbox import ALLOWED_DIRS, SandboxResult

REPO_PLUGINS = Path(sr.__file__).resolve().parent.parent / "plugins"
APPROVE = GateDecision(True, ["test-approved"])


class _FakeSandbox:
    def __init__(self, ok=True):
        self.ok = ok
        self.calls = []

    def run_command(self, command, timeout=30, cwd=None, env=None):
        self.calls.append((command, cwd))
        return SandboxResult(success=self.ok, stderr="" if self.ok else "boom")


def _audit_rows():
    p = Path(os.environ["CODEY_ACTION_GATEWAY_AUDIT"])
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text().splitlines() if line.strip()]


@pytest.fixture
def rig(tmp_path, monkeypatch):
    registry = CapabilityRegistry(store_path=str(tmp_path / "reg.json"))
    memory = CCOSMemory(db_path=str(tmp_path / "mem.db"))
    monkeypatch.setattr(sr, "get_capability_registry", lambda: registry)
    monkeypatch.setattr(sr, "get_ccos_memory", lambda: memory)
    monkeypatch.setattr(sr, "get_sandbox", lambda: _FakeSandbox())
    import core.action_gateway as ag
    ag.reset_action_gateway()
    plugin_base = tmp_path / "plugins" / "compound"
    plugin_base.mkdir(parents=True)
    staging = tmp_path / "staging" / "compound"
    rc = sr.SkillRecombiner(plugin_base=plugin_base, staging_base=staging)
    pattern = sr.DetectedPattern(
        sequence=("system.info", "system.processes"), frequency=5,
        avg_success_rate=1.0, avg_total_duration_ms=100,
        step_durations=[50, 50], examples=["x"])
    yield rc, pattern, registry, memory, plugin_base, staging
    ag.reset_action_gateway()


def _tree_files(root):
    return sorted(str(p) for p in Path(root).rglob("*") if p.is_file())


def _no_dynamic_import(monkeypatch):
    import importlib.util

    def _boom(*a, **k):
        raise AssertionError("generated code must not be imported/executed")
    monkeypatch.setattr(importlib.util, "spec_from_file_location", _boom)


# ── Recombiner ─────────────────────────────────────────────────────

def test_shadow_mode_leaves_no_runnable_plugin_in_discovery_roots(rig, monkeypatch):
    rc, pattern, registry, memory, plugin_base, staging = rig
    monkeypatch.setenv("CODEY_SELF_IMPROVE", "shadow")
    _no_dynamic_import(monkeypatch)
    res = rc._process_pattern(pattern, gate_decision=APPROVE, confirm=lambda: True)
    assert res.registered is False
    assert _tree_files(plugin_base) == []
    assert any(f.endswith("pipeline.py") for f in _tree_files(staging))
    assert not registry.has(res.skill_name)
    assert _audit_rows() == []
    # Real discovery over the discovery root finds nothing.
    from ccos.core.plugin_manager import PluginManager
    pm = PluginManager(plugin_dirs=[str(plugin_base)], registry=registry)
    assert pm._plugins == {}


def test_default_staging_is_outside_discovery_roots_and_sandbox_allowlist(monkeypatch, tmp_path):
    registry = CapabilityRegistry(store_path=str(tmp_path / "reg.json"))
    monkeypatch.setattr(sr, "get_capability_registry", lambda: registry)
    monkeypatch.setattr(sr, "get_ccos_memory", lambda: CCOSMemory(db_path=str(tmp_path / "m.db")))
    monkeypatch.setattr(sr, "get_sandbox", lambda: _FakeSandbox())
    rc = sr.SkillRecombiner()
    staging = rc._staging_base.resolve()
    with pytest.raises(ValueError):
        staging.relative_to(REPO_PLUGINS.resolve())
    for allowed in ALLOWED_DIRS:
        with pytest.raises(ValueError):
            staging.relative_to(Path(allowed).resolve())
    assert rc._plugin_base.resolve().relative_to(REPO_PLUGINS.resolve())


def test_real_sandbox_rejects_staging_dir(rig, tmp_path, monkeypatch):
    # With the real sandbox and a staging dir outside ALLOWED_DIRS the
    # candidate is refused (broken-safe), not silently accepted.
    from ccos.core.sandbox import Sandbox
    sb = Sandbox(allowed_dirs=[str(tmp_path / "somewhere_else")])
    res = sb.run_command("true", cwd=str(tmp_path / "staging"))
    assert not res.success and "SANDBOX VIOLATION" in res.stderr
    sb.cleanup()


def test_no_confirm_denied_leaves_nothing_deployed_and_records_refusal(rig, monkeypatch):
    rc, pattern, registry, memory, plugin_base, staging = rig
    monkeypatch.setenv("CODEY_SELF_IMPROVE", "on")
    res = rc._process_pattern(pattern, gate_decision=APPROVE, confirm=None)
    assert res.registered is False and _tree_files(plugin_base) == []
    assert not registry.has(res.skill_name)
    rows = _audit_rows()
    assert len(rows) == 1 and rows[0]["authority"] == "HIGH_IMPACT"
    assert rows[0]["outcome"] == "refused"
    assert rows[0]["action"] == "skill_recombiner.deploy"
    assert any(e["event_type"] == "skill_deploy_refused" for e in memory.events.get_recent(limit=20))


def test_declined_confirm_leaves_nothing_deployed(rig, monkeypatch):
    rc, pattern, registry, memory, plugin_base, staging = rig
    monkeypatch.setenv("CODEY_SELF_IMPROVE", "on")
    calls = []
    res = rc._process_pattern(pattern, gate_decision=APPROVE,
                              confirm=lambda: calls.append(1) or False)
    assert calls == [1]
    assert res.registered is False and _tree_files(plugin_base) == []
    assert not registry.has(res.skill_name)
    assert [r["outcome"] for r in _audit_rows()] == ["refused"]
    assert any(e["event_type"] == "skill_deploy_refused" for e in memory.events.get_recent(limit=20))


def test_gate_decision_reject_blocks_even_with_confirm_and_env_on(rig, monkeypatch):
    rc, pattern, registry, memory, plugin_base, staging = rig
    monkeypatch.setenv("CODEY_SELF_IMPROVE", "on")
    called = []
    for gd in (None, no_evaluator(), GateDecision(False, ["no"])):
        res = rc._process_pattern(pattern, gate_decision=gd,
                                  confirm=lambda: called.append(1) or True)
        assert res.registered is False
    assert called == []  # human never even prompted for a gate-rejected candidate
    assert _tree_files(plugin_base) == []
    assert not registry.has(res.skill_name)
    assert _audit_rows() == []
    assert any(e["event_type"] == "skill_deploy_refused" for e in memory.events.get_recent(limit=20))


def test_approved_path_deploys_once_with_one_high_audit_row_and_no_leak(rig, monkeypatch, tmp_path):
    rc, pattern, registry, memory, plugin_base, staging = rig
    monkeypatch.setenv("CODEY_SELF_IMPROVE", "on")
    _no_dynamic_import(monkeypatch)
    calls = []
    res = rc._process_pattern(pattern, gate_decision=APPROVE,
                              confirm=lambda: calls.append(1) or True)
    assert calls == [1]
    assert res.registered is True
    deployed = plugin_base / res.skill_name.replace(".", "_")
    assert sorted(p.name for p in deployed.iterdir()) == ["manifest.json", "pipeline.py", "test.py"]
    cap = registry.get(res.skill_name)
    assert cap.status == CapabilityStatus.EXPERIMENTAL
    assert Path(cap.implementation) == deployed / "pipeline.py"
    rows = _audit_rows()
    assert len(rows) == 1
    assert rows[0]["outcome"] == "allowed" and rows[0]["action"] == "skill_recombiner.deploy"
    assert rows[0]["authority"] == "HIGH_IMPACT"
    raw = Path(os.environ["CODEY_ACTION_GATEWAY_AUDIT"]).read_text()
    assert "def run" not in raw and str(tmp_path) not in raw and "pipeline.py" not in raw
    assert res.skill_name not in raw


def test_deploy_failure_audit_has_fixed_message_and_cleans_up(rig, monkeypatch, tmp_path):
    rc, pattern, registry, memory, plugin_base, staging = rig
    monkeypatch.setenv("CODEY_SELF_IMPROVE", "on")
    skill = rc._generator.generate_skill(pattern)
    existing = plugin_base / skill.name.replace(".", "_")
    existing.mkdir()
    (existing / "keep.txt").write_text("mine")
    res = rc._process_pattern(pattern, gate_decision=APPROVE, confirm=lambda: True)
    assert res.registered is False
    assert (existing / "keep.txt").read_text() == "mine"
    assert sorted(p.name for p in existing.iterdir()) == ["keep.txt"]
    rows = _audit_rows()
    assert [r["outcome"] for r in rows] == ["failed"]
    assert rows[0]["reason"] == "compound skill deployment failed"
    assert str(tmp_path) not in json.dumps(rows)
    assert not registry.has(skill.name)


def test_registry_failure_removes_created_dir(rig, monkeypatch):
    rc, pattern, registry, memory, plugin_base, staging = rig
    monkeypatch.setenv("CODEY_SELF_IMPROVE", "on")

    def _bad(cap):
        raise OSError("/secret/path exploded")
    monkeypatch.setattr(registry, "register", _bad)
    res = rc._process_pattern(pattern, gate_decision=APPROVE, confirm=lambda: True)
    assert res.registered is False
    assert _tree_files(plugin_base) == []
    assert not list(plugin_base.iterdir())
    assert "secret" not in json.dumps(_audit_rows())


def test_execute_compound_skill_refused_and_never_imports(rig, monkeypatch, tmp_path):
    rc, pattern, registry, memory, plugin_base, staging = rig
    marker = tmp_path / "ran.marker"
    impl = tmp_path / "pipeline.py"
    impl.write_text(f"open({str(marker)!r}, 'w').write('x')\ndef run(x=None):\n    return {{'success': True}}\n")
    registry.register(Capability(name="skill.demo", description="d", implementation=str(impl),
                                 category="c", status=CapabilityStatus.ACTIVE))
    out = rc.execute_compound_skill("skill.demo")
    assert out["success"] is False
    assert not marker.exists()
    rows = _audit_rows()
    assert [r["outcome"] for r in rows] == ["refused"]
    assert rows[0]["action"] == "skill_recombiner.execute"
    assert str(tmp_path) not in json.dumps(rows) and "skill.demo" not in json.dumps(rows)


# ── Optimizer ──────────────────────────────────────────────────────

@pytest.fixture
def orig(tmp_path, monkeypatch):
    import core.action_gateway as ag
    ag.reset_action_gateway()
    monkeypatch.setattr(co, "get_sandbox", lambda: _FakeSandbox())
    registry = CapabilityRegistry(store_path=str(tmp_path / "optreg.json"))
    root = tmp_path / "plug"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    data = tmp_path / "data"
    opt = co.CapabilityOptimizer(data_base=data, plugin_roots=[root])
    opt._registry = registry
    cand = tmp_path / "cand.py"
    cand.write_text("NEW = 1\n")
    monkeypatch.setenv("CODEY_SELF_IMPROVE", "on")
    yield opt, registry, root, outside, data, cand
    ag.reset_action_gateway()


def _register(registry, impl):
    registry.register(Capability(name="t.cap", description="d", implementation=impl,
                                 category="c", version="1.0.0"))


def _upgrade(opt, cand, confirm=lambda: True):
    return opt.compare_and_upgrade("t.cap", "1.0.1", str(cand), True, {},
                                   gate_decision=APPROVE, confirm=confirm)


def test_optimizer_refuses_non_file_targets(orig, tmp_path, monkeypatch):
    opt, registry, root, outside, data, cand = orig
    monkeypatch.chdir(tmp_path)
    victim = outside / "victim.py"
    victim.write_text("SECRET\n")
    (root / "adir").mkdir()
    link = root / "link.py"
    link.symlink_to(victim)
    linkdir = root / "linkdir"
    linkdir.symlink_to(outside, target_is_directory=True)
    bad = [
        "mypkg.module:function", "https://evil.example/x.py", "",
        str(root / "missing.py"), str(root / "adir"),
        str(root / ".." / "outside" / "victim.py"),
        str(victim), str(link), str(linkdir / "victim.py"),
        "relative/path.py", "x\x00y",
    ]
    before = set(os.listdir(tmp_path)) | {"optreg.json"}  # registry store is the test's own
    for impl in bad:
        _register(registry, impl)
        res = _upgrade(opt, cand)
        assert res.improved is False, impl
    assert victim.read_text() == "SECRET\n"
    assert not data.exists()  # no backup dir created before containment passed
    assert set(os.listdir(tmp_path)) == before
    assert _audit_rows() == []  # refused before reaching the gateway


def test_optimizer_deploys_contained_target_with_confirm_once(orig):
    opt, registry, root, outside, data, cand = orig
    target = root / "real.py"
    target.write_text("OLD = 1\n")
    alias = root / "alias.py"
    alias.symlink_to(target)  # symlink that stays inside the root is fine
    _register(registry, str(alias))
    calls = []
    res = _upgrade(opt, cand, confirm=lambda: calls.append(1) or True)
    assert res.improved is True and calls == [1]
    assert target.read_text() == "NEW = 1\n"
    assert alias.is_symlink()
    rows = _audit_rows()
    assert len(rows) == 1 and rows[0]["outcome"] == "allowed"
    assert rows[0]["authority"] == "HIGH_IMPACT"
    assert rows[0]["action"] == "capability_optimizer.deploy"
    assert str(root) not in json.dumps(rows)


def test_optimizer_without_confirm_or_when_declined_changes_nothing(orig):
    opt, registry, root, outside, data, cand = orig
    target = root / "real.py"
    target.write_text("OLD = 1\n")
    _register(registry, str(target))
    for conf in (None, lambda: False):
        res = _upgrade(opt, cand, confirm=conf)
        assert res.improved is False
    assert target.read_text() == "OLD = 1\n"
    assert not data.exists()
    assert [r["outcome"] for r in _audit_rows()] == ["refused", "refused"]


def test_optimizer_gate_logic_unchanged_without_gate_decision(orig):
    opt, registry, root, outside, data, cand = orig
    target = root / "real.py"
    target.write_text("OLD = 1\n")
    _register(registry, str(target))
    res = opt.compare_and_upgrade("t.cap", "1.0.1", str(cand), True, {},
                                  gate_decision=no_evaluator(), confirm=lambda: True)
    assert res.improved is False and "promotion gate" in res.details
    assert target.read_text() == "OLD = 1\n" and _audit_rows() == []


def test_optimizer_copy_failure_audit_is_fixed_message(orig, tmp_path):
    opt, registry, root, outside, data, cand = orig
    target = root / "real.py"
    target.write_text("OLD = 1\n")
    _register(registry, str(target))
    res = opt.compare_and_upgrade("t.cap", "1.0.1", str(tmp_path / "no_such_cand.py"), True, {},
                                  gate_decision=APPROVE, confirm=lambda: True)
    assert res.improved is False
    rows = _audit_rows()
    assert [r["outcome"] for r in rows] == ["failed"]
    assert rows[0]["reason"] == "capability deployment failed"
    assert str(tmp_path) not in json.dumps(rows)
    assert target.read_text() == "OLD = 1\n"


def test_real_ccos_plugin_tree_untouched_by_these_tests():
    # Guard: the module-level default plugin root must not have been used.
    assert not (REPO_PLUGINS / "compound").exists() or not any(
        p.name.startswith("skill_") for p in (REPO_PLUGINS / "compound").iterdir())
