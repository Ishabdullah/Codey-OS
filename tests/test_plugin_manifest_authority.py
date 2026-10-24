"""G15g Unit A: plugin manifest authority (containment, duplicate names,
symlinks, capability collisions). Disposable roots; Popen is forbidden."""
import json
import os
import unicodedata
from pathlib import Path

import pytest

from ccos.core import plugin_manager as pm
from ccos.core.capability_registry import CapabilityRegistry
from ccos.core.plugin_manager import (
    PluginContainmentError, PluginStatus, resolve_plugin_file,
)

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _no_spawn(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    audit = tmp_path / "audit.jsonl"
    monkeypatch.setenv("CODEY_ACTION_GATEWAY_AUDIT", str(audit))

    def forbidden(*a, **k):
        raise AssertionError("real spawn attempted")
    monkeypatch.setattr(pm.subprocess, "Popen", forbidden)


def rows(tmp_path):
    f = tmp_path / "audit.jsonl"
    if not f.exists():
        return []
    return [json.loads(x) for x in f.read_text().splitlines() if x.strip()]


def mk(root, cat, d, manifest, init="", extra=None):
    p = Path(root) / cat / d
    p.mkdir(parents=True, exist_ok=True)
    (p / "manifest.json").write_text(json.dumps(manifest))
    (p / "__init__.py").write_text(init)
    for k, v in (extra or {}).items():
        (p / k).write_text(v)
    return p


def marker_init(marker, tag):
    return f"open({str(marker)!r}, 'a').write({tag!r} + '\\n')\n"


def manager(tmp_path, *roots):
    return pm.PluginManager([str(r) for r in roots], CapabilityRegistry(str(tmp_path / "reg.json")))


# ---- A1 helper -----------------------------------------------------------
@pytest.fixture
def pdir(tmp_path):
    d = tmp_path / "plugdir"
    d.mkdir()
    (d / "agent.py").write_text("")
    (d / "sub").mkdir()
    (d / "sub" / "x.py").write_text("")
    (d / "x.py").write_text("")
    (d / "~x").write_text("")
    (tmp_path / "plugdir2").mkdir()
    (tmp_path / "plugdir2" / "x.py").write_text("")
    (tmp_path / "outside.py").write_text("")
    (tmp_path / "outdir").mkdir()
    (tmp_path / "outdir" / "y.py").write_text("")
    os.symlink(d / "x.py", d / "inlink.py")
    os.symlink(tmp_path / "outside.py", d / "outlink.py")
    os.symlink(tmp_path / "outdir", d / "dirlink")
    os.symlink("loopb", d / "loopa")
    os.symlink("loopa", d / "loopb")
    return d


@pytest.mark.parametrize("rel", ["agent.py", "sub/x.py", "./x.py", "sub/../x.py", "inlink.py", "~x"])
def test_helper_accepts(pdir, rel):
    got = resolve_plugin_file(pdir, rel)
    assert str(got).startswith(os.path.realpath(pdir) + os.sep)


@pytest.mark.parametrize("rel", [
    "{abs_inside}", "/etc/passwd", "../outside.py", "a/../../outside.py", "outlink.py",
    "dirlink/y.py", "loopa", "a\x00b", "", None, 5, ".", "../plugdir2/x.py", "sub/..",
])
def test_helper_refuses(pdir, rel):
    if isinstance(rel, str):
        rel = rel.replace("{abs_inside}", str(pdir / "agent.py"))
    with pytest.raises(PluginContainmentError):
        resolve_plugin_file(pdir, rel)


def test_helper_through_symlinked_parent_no_false_refusal(tmp_path, pdir):
    alias = tmp_path / "alias"
    os.symlink(pdir, alias)
    assert resolve_plugin_file(alias, "agent.py") == Path(os.path.realpath(pdir / "agent.py"))


def test_helper_missing_entry_still_judged(pdir):
    assert resolve_plugin_file(pdir, "nope.py").name == "nope.py"
    with pytest.raises(PluginContainmentError):
        resolve_plugin_file(pdir, "../nope.py")


# ---- A2 duplicates -------------------------------------------------------
def dup_setup(tmp_path, n1="dupe", n2="dupe", two_roots=False):
    r1 = tmp_path / "r1"
    r2 = tmp_path / "r2" if two_roots else r1
    mk(r1, "c1", "genuine", {"name": n1}, marker_init(tmp_path / "m", "GEN"))
    mk(r2, "c2" if not two_roots else "c1", "planted", {"name": n2}, marker_init(tmp_path / "m", "PLANT"))
    return [r1] + ([r2] if two_roots else [])


@pytest.mark.parametrize("n1,n2,two", [
    ("dupe", "dupe", False), ("dupe", "dupe", True), ("Agent", "agent ", False),
    ("ａgent", "agent", False),
])
def test_duplicate_names_refused_for_all(tmp_path, n1, n2, two):
    roots = dup_setup(tmp_path, n1, n2, two)
    m = manager(tmp_path, *roots)
    plugins = m.list_plugins()
    assert len(plugins) == (1 if n1 == n2 else 2)
    for p in plugins:
        assert p["status"] == "disabled" and p["error"].startswith("refused: plugin name claimed")
        assert m.load(p["name"]) is False
    assert not (tmp_path / "m").exists()
    rs = [r for r in rows(tmp_path) if r["outcome"] == "refused"]
    assert rs and all(r["authority"] == "HIGH_IMPACT" for r in rs)
    assert all(r["action"].startswith("ccos.plugin_discover:") for r in rs)
    assert any("genuine" in r["command"] or "genuine" in r["reason"] for r in rs)
    assert len(m.get_status()["refused"]) == len(rs)


def test_dir_name_fallback_collides_with_manifest_name(tmp_path):
    r = tmp_path / "r"
    mk(r, "c1", "same", {}, marker_init(tmp_path / "m", "A"))
    mk(r, "c2", "other", {"name": "same"}, marker_init(tmp_path / "m", "B"))
    m = manager(tmp_path, r)
    assert [p["status"] for p in m.list_plugins()] == ["disabled"]
    assert m.load("same") is False and not (tmp_path / "m").exists()


def test_duplicate_outcome_independent_of_iterdir_order(tmp_path, monkeypatch):
    roots = dup_setup(tmp_path, "Agent", "agent ")
    mk(roots[0], "c3", "fine", {"name": "fine"})
    mk(roots[0], "c3", "s1", {"name": "same"})
    mk(roots[0], "c3", "s2", {"name": "same"})
    mk(roots[0], "c3", "s3", {"name": "same"})
    mk(roots[0], "c5", "t1", {"name": "same2"})
    mk(roots[0], "c6", "t2", {"name": "same2"})
    mk(roots[0], "c7", "t3", {"name": "same2"})
    def snap():
        m = manager(tmp_path, *roots)
        return {k: (v.status, v.error, v.path) for k, v in m._plugins.items()}
    a = snap()
    real = Path.iterdir
    monkeypatch.setattr(Path, "iterdir", lambda self: iter(reversed(list(real(self)))))
    assert snap() == a


def test_rediscover_no_spurious_refusal_and_active_not_clobbered(tmp_path):
    r = tmp_path / "r"
    mk(r, "c1", "fixture", {"name": "fixture"}, marker_init(tmp_path / "m", "OK"))
    m = manager(tmp_path, r)
    m._discover()
    assert m.get_status()["refused"] == []
    assert m.load("fixture") is True
    active = m.get_plugin("fixture")
    mk(r, "c2", "planted", {"name": "fixture"}, marker_init(tmp_path / "m", "BAD"))
    m._discover()
    assert m.get_plugin("fixture") is active and active.status == PluginStatus.ACTIVE
    assert (tmp_path / "m").read_text() == "OK\n"


# ---- A3 symlinks ---------------------------------------------------------
def test_symlinked_plugin_dir_category_dir_manifest_refused(tmp_path):
    out = tmp_path / "out"
    mk(out, "x", "evil", {"name": "evil"}, marker_init(tmp_path / "m", "EVIL"))
    mk(out, "x", "evil2", {"name": "evil2"}, marker_init(tmp_path / "m", "EVIL2"))
    r = tmp_path / "r"
    (r / "cat").mkdir(parents=True)
    os.symlink(out / "x" / "evil", r / "cat" / "linked")
    os.symlink(out / "x", r / "linkcat")
    real = mk(r, "cat2", "viaman", {"name": "viaman"}, marker_init(tmp_path / "m", "MAN"))
    (real / "manifest.json").rename(tmp_path / "real_manifest.json")
    os.symlink(tmp_path / "real_manifest.json", real / "manifest.json")
    (tmp_path / "real_manifest.json").write_text(json.dumps({"name": "viaman"}))
    m = manager(tmp_path, r)
    assert m.list_plugins() == []
    m.load_all()
    assert not (tmp_path / "m").exists()
    refs = m.get_status()["refused"]
    assert {x["reason"] for x in refs} == {
        "symlinked plugin directory", "symlinked category directory", "symlinked manifest.json"}
    assert len([r_ for r_ in rows(tmp_path) if r_["action"].startswith("ccos.plugin_discover:")]) == 3


def test_in_root_symlink_to_other_plugin_dir_refused_but_entry_file_symlink_ok(tmp_path):
    r = tmp_path / "r"
    p = mk(r, "c", "real", {"name": "real", "entry_point": "ep.py"})
    (p / "impl.py").write_text(marker_init(tmp_path / "m", "IMPL"))
    os.symlink(p / "impl.py", p / "ep.py")
    os.symlink(p, r / "c" / "alias")
    m = manager(tmp_path, r)
    assert [x["name"] for x in m.list_plugins()] == ["real"]
    assert [x["reason"] for x in m.get_status()["refused"]] == ["symlinked plugin directory"]
    assert m.load("real") is True
    assert (tmp_path / "m").read_text() == "IMPL\n"


# ---- A4 capability collision ---------------------------------------------
def test_capability_collision_refuses_all_claimants(tmp_path):
    r = tmp_path / "r"
    mk(r, "c", "a", {"name": "pa", "capabilities": [{"name": "zz.read"}]}, marker_init(tmp_path / "m", "A"))
    mk(r, "c", "b", {"name": "pb", "capabilities": [{"id": "zz.read"}]}, marker_init(tmp_path / "m", "B"))
    mk(r, "c", "ok", {"name": "pc", "capabilities": [{"name": "zz.other"}]}, marker_init(tmp_path / "m", "C"))
    m = manager(tmp_path, r)
    st = {p["name"]: p["status"] for p in m.list_plugins()}
    assert st == {"pa": "disabled", "pb": "disabled", "pc": "installed"}
    assert "zz.read" in m.get_plugin("pa").error
    assert m.load("pa") is False and m.load("pb") is False
    assert not (tmp_path / "m").exists() and m._registry.count() == 0
    assert m.load("pc") is True and m._registry.count() == 1


def test_capability_names_case_sensitive_no_false_collision(tmp_path):
    r = tmp_path / "r"
    mk(r, "c", "a", {"name": "pa", "capabilities": [{"name": "zz.Read"}]})
    mk(r, "c", "b", {"name": "pb", "capabilities": [{"name": "zz.read"}]})
    assert {p["status"] for p in manager(tmp_path, r).list_plugins()} == {"installed"}


# ---- A5 use-time ---------------------------------------------------------
def escape_setup(tmp_path, entry="../../outside.py"):
    r = tmp_path / "r"
    p = mk(r, "c", "esc", {"name": "esc", "entry_point": "ok.py"},
           marker_init(tmp_path / "m", "INIT"), {"ok.py": marker_init(tmp_path / "m", "OK")})
    (tmp_path / "outside.py").write_text(marker_init(tmp_path / "m", "OUTSIDE"))
    return manager(tmp_path, r), p, entry


@pytest.mark.parametrize("entry", ["../../outside.py", "ABS", "link.py"])
def test_escaping_entry_after_discovery_refused_no_fallback(tmp_path, monkeypatch, entry):
    m, p, _ = escape_setup(tmp_path)
    if entry == "ABS":
        entry = str(p / "ok.py")  # absolute even though inside
    if entry == "link.py":
        os.symlink(tmp_path / "outside.py", p / "link.py")
    m.get_plugin("esc").manifest["entry_point"] = entry
    spec = pm.importlib.util.spec_from_file_location
    called = []
    monkeypatch.setattr(pm.importlib.util, "spec_from_file_location",
                        lambda *a, **k: called.append(a) or spec(*a, **k))
    assert m.load("esc") is False
    assert m.get_plugin("esc").status == PluginStatus.DISABLED
    assert called == [] and not (tmp_path / "m").exists()
    rs = [r for r in rows(tmp_path) if r["action"] == "ccos.plugin_activate:esc"]
    assert len(rs) == 1 and rs[0]["outcome"] == "refused" and rs[0]["authority"] == "HIGH_IMPACT"
    assert str(tmp_path) not in rs[0]["reason"]
    assert m.load("esc") is False  # never retried


def test_entry_swapped_to_outside_symlink_after_staging_refused(tmp_path, monkeypatch):
    # Swap lands between the staging check and the use-time recheck.
    m, p, _ = escape_setup(tmp_path)
    orig = pm.resolve_plugin_file
    n = {"c": 0}
    def swapping(d, rel):
        n["c"] += 1
        if n["c"] == 3:  # first call of the use-time recheck
            (p / "ok.py").unlink()
            os.symlink(tmp_path / "outside.py", p / "ok.py")
        return orig(d, rel)
    monkeypatch.setattr(pm, "resolve_plugin_file", swapping)
    assert m.load("esc") is False
    assert m.get_plugin("esc").status == PluginStatus.DISABLED
    assert not (tmp_path / "m").exists()
    assert len([r for r in rows(tmp_path) if r["action"] == "ccos.plugin_activate:esc"]) == 1


def test_contained_missing_entry_falls_back_to_init(tmp_path):
    m, p, _ = escape_setup(tmp_path)
    m.get_plugin("esc").manifest["entry_point"] = "missing.py"
    assert m.load("esc") is True
    assert (tmp_path / "m").read_text() == "INIT\n"


def test_init_symlink_to_outside_refused(tmp_path):
    m, p, _ = escape_setup(tmp_path)
    (p / "__init__.py").unlink()
    os.symlink(tmp_path / "outside.py", p / "__init__.py")
    assert m.load("esc") is False
    assert m.get_plugin("esc").status == PluginStatus.DISABLED
    assert not (tmp_path / "m").exists()


def test_escaping_entry_on_external_plugin_with_start_command_refused_as_unit(tmp_path):
    r = tmp_path / "r"
    mk(r, "c", "ext", {"name": "ext", "execution_mode": "external_process",
                       "entry_point": "../../outside.py",
                       "process_spec": {"start_command": ["/bin/true"]}})
    m = manager(tmp_path, r)
    from unittest.mock import Mock
    m.supervisor.start_external_plugin = Mock()
    assert m.load("ext") is False
    m.supervisor.start_external_plugin.assert_not_called()
    assert m.get_plugin("ext").status == PluginStatus.DISABLED


# ---- A6 supervisor direct ------------------------------------------------
def test_supervisor_fallback_escape_refused_with_row(tmp_path):
    d = tmp_path / "pd"
    d.mkdir()
    plug = pm.Plugin(name="x", path=str(d), manifest={"entry_point": "../escape.py"},
                     execution_mode="external_process")
    (tmp_path / "escape.py").write_text("")
    assert pm.ProcessSupervisor().start_external_plugin(plug) is False
    assert plug.status == PluginStatus.DISABLED
    rs = rows(tmp_path)
    assert len(rs) == 1 and rs[0]["action"] == "ccos.plugin_spawn:x"
    assert rs[0]["outcome"] == "refused" and rs[0]["authority"] == "HIGH_IMPACT"


def test_supervisor_fallback_contained_missing_keeps_message(tmp_path):
    d = tmp_path / "pd"
    d.mkdir()
    plug = pm.Plugin(name="x", path=str(d), manifest={"entry_point": "nope.py"},
                     execution_mode="external_process")
    assert pm.ProcessSupervisor().start_external_plugin(plug) is False
    assert plug.status == PluginStatus.BROKEN
    assert plug.error == "No start_command or entry_point found for external process"
    # G15g Unit B: a not-attempted spawn (missing entry) writes one ACT
    # refusal row; Unit A had pinned "no row" before the spawn was audited.
    got = rows(tmp_path)
    assert len(got) == 1
    assert got[0]["authority"] == pm.ACT and got[0]["outcome"] == "refused"


def test_supervisor_fallback_spawns_resolved_path(tmp_path, monkeypatch):
    d = tmp_path / "pd"
    d.mkdir()
    (d / "real.py").write_text("")
    os.symlink(d / "real.py", d / "alias.py")
    seen = []

    class Fake:
        pid = 1
        stdout = stderr = None
        def poll(self): return None
        def wait(self, timeout=None): raise pm.subprocess.TimeoutExpired("x", 0)
        def terminate(self): pass
    monkeypatch.setattr(pm.subprocess, "Popen", lambda cmd, **k: seen.append(cmd) or Fake())
    plug = pm.Plugin(name="x", path=str(d), manifest={"entry_point": "alias.py"},
                     execution_mode="external_process")
    sup = pm.ProcessSupervisor()
    sup.start_external_plugin(plug)
    assert seen and seen[0][1] == os.path.realpath(d / "real.py")


# ---- A7 real-repo drift --------------------------------------------------
def test_real_manifests_all_accepted(tmp_path):
    m = manager(tmp_path, REPO / "ccos" / "plugins")
    plugins = list(m._plugins.values())
    assert len(plugins) == 19
    assert not [p for p in plugins if p.status == PluginStatus.DISABLED]
    assert m._discovery_refusals == []
    names = []
    for p in plugins:
        assert resolve_plugin_file(p.path, p.manifest.get("entry_point", "__init__.py")).is_file()
        staged = m._stage_capabilities(p)
        assert pm._declared_capability_names(p.manifest, p.name) == [c.name for c in staged]
        names += [c.name for c in staged]
    assert len(names) == len(set(names))
    assert set(pm.CAPABILITY_AUTHORITY) <= set(names)
    for dirpath, dirs, files in os.walk(REPO / "ccos" / "plugins"):
        for e in dirs + files:
            assert not os.path.islink(os.path.join(dirpath, e)), e


# ---- round 2: root dedupe, name refusal, status preservation, audit failure
def _one_root(tmp_path):
    r = tmp_path / "r"
    mk(r, "a", "one", {"name": "one"}, marker_init(tmp_path / "m", "ONE"))
    return r


def test_same_root_twice_not_self_duplicate(tmp_path):
    r = _one_root(tmp_path)
    m = manager(tmp_path, r, r)
    assert [p["status"] for p in m.list_plugins()] == ["installed"]
    assert m.get_status()["refused"] == []


def test_root_plus_symlink_alias_not_self_duplicate(tmp_path):
    r = _one_root(tmp_path)
    alias = tmp_path / "alias"
    os.symlink(r, alias)
    for roots in ((r, alias), (alias, r)):
        m = manager(tmp_path, *roots)
        assert [p["status"] for p in m.list_plugins()] == ["installed"]
        assert m.get_status()["refused"] == []


def test_overlapping_roots_same_plugin_dir_not_self_duplicate(tmp_path):
    # r2 = r/a is a root whose "categories" are plugin dirs; "one" has no
    # nested plugin dirs, so reach the same dir via a second root containing
    # a symlink-free alias path (".." component) to the same category.
    r = _one_root(tmp_path)
    m = manager(tmp_path, r, tmp_path / "r" / "a" / "..")
    assert [p["status"] for p in m.list_plugins()] == ["installed"]


def test_true_duplicate_distinct_dirs_still_refused_with_dedupe(tmp_path):
    r = _one_root(tmp_path)
    r2 = tmp_path / "r2"
    mk(r2, "a", "one", {"name": "one"}, marker_init(tmp_path / "m", "EVIL"))
    m = manager(tmp_path, r, r, r2)
    assert [p["status"] for p in m.list_plugins()] == ["disabled"]
    assert m.load("one") is False and not (tmp_path / "m").exists()


@pytest.mark.parametrize("bad", [5, "  ", ["x"], None])
def test_unusable_name_refused_with_row(tmp_path, bad):
    r = tmp_path / "r"
    mk(r, "a", "badname", {"name": bad})
    m = manager(tmp_path, r)
    assert m.list_plugins() == []
    assert [x["reason"] for x in m.get_status()["refused"]] == ["manifest name is not a non-blank string"]
    assert len(rows(tmp_path)) == 1


def test_supervisor_disabled_status_preserved_through_load(tmp_path):
    r = tmp_path / "r"
    mk(r, "c", "ext", {"name": "ext", "execution_mode": "external_process",
                       "entry_point": "../../x.py"})
    m = manager(tmp_path, r)
    m.get_plugin("ext").manifest["entry_point"] = "ok.py"  # pass manager staging
    (Path(m.get_plugin("ext").path) / "ok.py").write_text("")
    orig = pm.resolve_plugin_file
    state = {"n": 0}
    def flaky(d, rel):
        state["n"] += 1
        if state["n"] > 2:  # supervisor-level call sees an escape
            raise PluginContainmentError("x")
        return orig(d, rel)
    pm.resolve_plugin_file, saved = flaky, orig
    try:
        assert m.load("ext") is False
    finally:
        pm.resolve_plugin_file = saved
    p = m.get_plugin("ext")
    assert p.status == PluginStatus.DISABLED and p.error == "entry_point escapes plugin directory"


def test_audit_failure_cannot_crash_discovery_or_skip_cleanup(tmp_path, monkeypatch):
    class Boom:
        def refuse_exec(self, **k):
            raise RuntimeError("sink exploded")
    monkeypatch.setattr(pm, "get_action_gateway", lambda: Boom())
    roots = dup_setup(tmp_path)
    m = manager(tmp_path, *roots)  # discovery survives a failing sink
    assert [p["status"] for p in m.list_plugins()] == ["disabled"]
    r = tmp_path / "r3"
    p = mk(r, "c", "esc", {"name": "esc3", "entry_point": "ok.py"}, "", {"ok.py": ""})
    m2 = manager(tmp_path, r)
    m2.get_plugin("esc3").manifest["entry_point"] = "../../outside.py"
    assert m2.load("esc3") is False
    assert m2.get_plugin("esc3").status == PluginStatus.DISABLED
    # use-time path (except BaseException handler): cleanup still ran
    m3 = manager(tmp_path, r)
    orig = pm.resolve_plugin_file
    n = {"c": 0}
    def swap(d, rel):
        n["c"] += 1
        if n["c"] == 3:
            raise PluginContainmentError("late")
        return orig(d, rel)
    monkeypatch.setattr(pm, "resolve_plugin_file", swap)
    assert m3.load("esc3") is False
    assert m3.get_plugin("esc3").status == PluginStatus.DISABLED
    assert "esc3" not in m3._activation_attempts


def test_root_dedupe_alone_no_duplicate_refusals(tmp_path):
    # Fails if ONLY the root-level dedupe is dropped: the refusal for a
    # symlinked category happens before the plugin-dir-level dedupe.
    r = _one_root(tmp_path)
    os.symlink(tmp_path, r / "linkcat")
    for roots in ((r, r), (r, tmp_path / "r" / "a" / "..")):
        m = manager(tmp_path, *roots)
        assert [x["reason"] for x in m.get_status()["refused"]] == ["symlinked category directory"]
    assert len([x for x in rows(tmp_path) if x["action"].startswith("ccos.plugin_discover:")]) == 2


def test_audit_failure_leaves_warning_without_secrets(tmp_path, monkeypatch, caplog):
    class Boom:
        def refuse_exec(self, **k):
            raise RuntimeError("SECRET-MESSAGE")
    monkeypatch.setattr(pm, "get_action_gateway", lambda: Boom())
    with caplog.at_level("WARNING", logger=pm.__name__):
        pm._audit_plugin_refusal("ccos.plugin_discover:x", "SECRET-COMMAND", "SECRET-REASON")
    text = caplog.text
    assert "ccos.plugin_discover:x" in text and "RuntimeError" in text
    assert "SECRET" not in text
