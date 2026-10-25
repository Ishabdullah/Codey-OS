"""S2 unit B: zero-width plugin-name key (NEW.norm.zero_width), refusal of
positional tail args and authority-relaxing kwargs (M26), canonical-tree binding of
CAPABILITY_AUTHORITY names (M25b). Disposable roots; Popen is forbidden."""
import json
from pathlib import Path

import pytest

from ccos.core import plugin_manager as pm
from ccos.core.capability_registry import Capability, CapabilityRegistry
from ccos.core.plugin_manager import CapabilityRefused, PluginStatus, _plugin_name_key
from core.action_gateway import ACT, HIGH_IMPACT, READ

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _iso(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CODEY_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("CODEY_ACTION_GATEWAY_AUDIT", str(tmp_path / "audit.jsonl"))

    def forbidden(*a, **k):
        raise AssertionError("real spawn attempted")
    monkeypatch.setattr(pm.subprocess, "Popen", forbidden)


def rows(tmp_path):
    f = tmp_path / "audit.jsonl"
    return [json.loads(x) for x in f.read_text().splitlines() if x.strip()] if f.exists() else []


def mk(root, cat, d, manifest):
    p = Path(root) / cat / d
    p.mkdir(parents=True, exist_ok=True)
    (p / "manifest.json").write_text(json.dumps(manifest))
    (p / "__init__.py").write_text("")
    return p


def manager(tmp_path, *roots):
    return pm.PluginManager([str(r) for r in roots], CapabilityRegistry(str(tmp_path / "reg.json")))


# ---- Fix 1: name key ------------------------------------------------------
INVISIBLE = ["\u034f", "\u0301", "\ufe0f", "\ufe00", "\U000e0100", "\u3164", "\u115f",
             "\u1160", "\u2800", "\u180e", "\U000e0041", "\uffa0", "\u17b4",
             "​", "‌", "‍", "‎", "‏", "⁠", "﻿",
             "­", "‮", "‪", "⁦", "\x00", "\x07", "\x7f"]


@pytest.mark.parametrize("ch", INVISIBLE)
def test_invisible_chars_do_not_change_key(ch):
    assert _plugin_name_key("agent" + ch) == _plugin_name_key("agent")
    assert _plugin_name_key("ag" + ch + "ent") == _plugin_name_key("agent")
    assert _plugin_name_key(ch + "AGENT") == _plugin_name_key("agent")


def test_distinct_names_stay_distinct():
    assert _plugin_name_key("agent") != _plugin_name_key("agents")
    assert _plugin_name_key("agent-a") != _plugin_name_key("agent_a")
    # accepted residual: cross-script homoglyph is NOT folded
    assert _plugin_name_key("agent") != _plugin_name_key("аgent")


def test_zero_width_duplicate_refused_both(tmp_path):
    root = tmp_path / "r"
    mk(root, "c", "one", {"name": "agent", "capabilities": [{"name": "x.one"}]})
    mk(root, "c", "two", {"name": "agent​", "capabilities": [{"name": "x.two"}]})
    m = manager(tmp_path, root)
    assert m.get_plugin("agent").status == PluginStatus.DISABLED
    assert m.get_plugin("agent​").status == PluginStatus.DISABLED
    assert any(r["action"].startswith("ccos.plugin_discover:") for r in rows(tmp_path))


# ---- Fix 2: M26 -----------------------------------------------------------
@pytest.fixture
def mgr(tmp_path):
    m = manager(tmp_path, tmp_path / "empty")
    calls = []
    m.register_capability_handler("t.cap", lambda *a, **k: calls.append((a, k)) or "ok",
                                  authority=ACT)
    m.calls = calls
    return m


@pytest.mark.parametrize("kw", [
    {"yolo": True},
    {"confirm_shell": False},
    {"confirm_write": False},
    {"confirm_anything": False},
    {"shell_fn": lambda c: c},
    {"whatever": lambda: 1},
    {"CONFIRM_SHELL": False},
])
def test_relaxing_kwargs_refused_and_audited(mgr, tmp_path, kw):
    with pytest.raises(CapabilityRefused):
        mgr.call_capability("t.cap", prompt="x", **kw)
    assert mgr.calls == []
    refusals = [r for r in rows(tmp_path) if r["action"] == "ccos.call_capability:t.cap"]
    assert refusals and "authority-relaxing" in json.dumps(refusals[-1])


def test_callable_positional_refused(mgr):
    with pytest.raises(CapabilityRefused):
        mgr.call_capability("t.cap", lambda: 1)
    assert mgr.calls == []


def test_smuggled_trusted_flag_does_not_bypass(mgr):
    with pytest.raises(TypeError):
        mgr.call_capability("t.cap", _trusted=True, yolo=True)
    assert mgr.calls == []


@pytest.mark.parametrize("kw", [
    {"yolo": False}, {"confirm_shell": True}, {"confirm_write": None},
    {"shell_fn": None}, {"prompt": "hello", "n": 3},
])
def test_benign_kwargs_pass(mgr, kw):
    assert mgr.call_capability("t.cap", **kw) == "ok"
    assert mgr.calls[-1][1] == kw


def test_trusted_path_passes_relaxed(mgr):
    fn = lambda c: c
    assert mgr.call_capability_trusted(
        "t.cap", yolo=True, confirm_shell=False, shell_fn=fn) == "ok"
    assert mgr.calls[-1][1]["shell_fn"] is fn


def test_run_agent_capability_via_public_path_refused(tmp_path):
    """Real coding plugin: public path never reaches the inner agent."""
    from unittest.mock import patch
    m = manager(tmp_path, REPO / "ccos" / "plugins")
    assert m.load("agent")
    with patch("core.agent.run_agent", side_effect=AssertionError("reached")) as ra:
        with pytest.raises(CapabilityRefused):
            m.call_capability("coding.run_agent", prompt="x", yolo=True,
                              confirm_shell=False, confirm_write=False,
                              shell_fn=lambda c: c)
        ra.assert_not_called()


@pytest.mark.parametrize("args", [("hello",), (False,), (None,), ({"x": 1},)])
def test_benign_positional_data_refused_and_audited(mgr, tmp_path, args):
    with pytest.raises(CapabilityRefused, match=r"args\[0\]"):
        mgr.call_capability("t.cap", *args)
    assert mgr.calls == []
    row = rows(tmp_path)[-1]
    assert row["action"] == "ccos.call_capability:t.cap"
    assert row["authority"] == HIGH_IMPACT
    assert row["outcome"] == "refused"


def test_trusted_positional_data_retained(mgr):
    assert mgr.call_capability_trusted("t.cap", "hello", False) == "ok"
    assert mgr.calls == [(("hello", False), {})]


@pytest.fixture
def canonical_agent(tmp_path, monkeypatch):
    """Load the real wrapper; replace only its inner agent, never run a model."""
    from unittest.mock import Mock
    import core.agent
    m = manager(tmp_path, REPO / "ccos" / "plugins")
    assert m.load("agent")
    inner = Mock(return_value=("mock-only", []))
    monkeypatch.setattr(core.agent, "run_agent", inner)
    return m, inner


@pytest.mark.parametrize("args", [
    # Reviewer exploit: positional yolo and both confirmation overrides.
    ("probe", [], True, False, True, False, "", False, False),
    ("probe", [], True),
    ("probe", [], False, False, True, False, "", False),
    ("probe", [], False, False, True, False, "", True, False),
    ("benign prompt",),
])
def test_real_canonical_wrapper_positional_refused(canonical_agent, tmp_path, args):
    m, inner = canonical_agent
    with pytest.raises(CapabilityRefused, match=r"args\[0\]"):
        m.call_capability("coding.run_agent", *args)
    inner.assert_not_called()
    row = rows(tmp_path)[-1]
    assert row["action"] == "ccos.call_capability:coding.run_agent"
    assert row["authority"] == HIGH_IMPACT
    assert row["outcome"] == "refused"


def test_real_canonical_wrapper_keyword_data_works(canonical_agent):
    m, inner = canonical_agent
    result = m.call_capability("coding.run_agent", prompt="safe", history=[],
                               yolo=False, confirm_shell=True, confirm_write=True)
    assert result["response"] == "mock-only"
    assert result["success"] is True
    assert inner.call_args.kwargs["user_message"] == "safe"
    assert inner.call_args.kwargs["yolo"] is False


def test_real_canonical_wrapper_trusted_positional_retained(canonical_agent, monkeypatch):
    import utils.config
    m, inner = canonical_agent
    observed = []
    monkeypatch.setitem(utils.config.AGENT_CONFIG, "confirm_shell", True)
    monkeypatch.setitem(utils.config.AGENT_CONFIG, "confirm_write", True)

    def fake_agent(**kwargs):
        observed.append((kwargs["yolo"], utils.config.AGENT_CONFIG["confirm_shell"],
                         utils.config.AGENT_CONFIG["confirm_write"]))
        return "trusted-mock", []

    inner.side_effect = fake_agent
    result = m.call_capability_trusted(
        "coding.run_agent", "probe", [], True, False, True, False, "", False, False)
    assert result["response"] == "trusted-mock"
    assert observed == [(True, False, False)]
    assert utils.config.AGENT_CONFIG["confirm_shell"] is True
    assert utils.config.AGENT_CONFIG["confirm_write"] is True


def test_remote_positional_refused_before_http(tmp_path, monkeypatch):
    from unittest.mock import Mock
    m = manager(tmp_path, tmp_path / "empty")
    m._plugins["remote"] = pm.Plugin(
        name="remote", path=str(tmp_path), manifest={}, status=PluginStatus.ACTIVE,
        execution_mode="remote_bridge", capabilities=["remote.cap"])
    m._registry.register(Capability(
        name="remote.cap", description="", implementation="http://invalid.test/cap",
        execution_mode="remote_bridge"))
    monkeypatch.setitem(pm.CAPABILITY_AUTHORITY, "remote.cap", READ)
    http = Mock(side_effect=AssertionError("HTTP attempted"))
    monkeypatch.setattr(pm.urllib.request, "urlopen", http)
    with pytest.raises(CapabilityRefused, match=r"args\[0\]"):
        m.call_capability("remote.cap", "data")
    http.assert_not_called()
    row = rows(tmp_path)[-1]
    assert row["authority"] == HIGH_IMPACT
    assert row["outcome"] == "refused"


def test_internal_callers_use_trusted_path():
    import re
    for f, needle in [("core/task_executor.py", "call_capability_trusted(\n                    \"coding.run_agent\""),
                      ("main.py", "call_capability_trusted(\n        \"coding.run_agent\"")]:
        assert needle in (REPO / f).read_text(), f


# ---- Fix 3: M25b ----------------------------------------------------------
def test_noncanonical_plugin_cannot_claim_authority_name(tmp_path):
    root = tmp_path / "evil"
    mk(root, "sys", "evil", {"name": "evil", "capabilities": [{"name": "system.info"}]})
    m = manager(tmp_path, root)
    p = m.get_plugin("evil")
    assert p.status == PluginStatus.DISABLED and "canonical" in p.error
    assert m.load("evil") is False
    with pytest.raises(RuntimeError):
        m.call_capability("system.info")
    rs = [r for r in rows(tmp_path) if r["action"] == "ccos.plugin_discover:evil"]
    assert rs and "canonical" in json.dumps(rs[0])


def test_noncanonical_unlisted_name_still_loads(tmp_path):
    root = tmp_path / "ok"
    mk(root, "sys", "fine", {"name": "fine", "capabilities": [{"name": "zz.custom_cap"}]})
    m = manager(tmp_path, root)
    assert m.get_plugin("fine").status != PluginStatus.DISABLED


def test_noncanonical_refusal_does_not_disable_canonical(tmp_path):
    evil = tmp_path / "evil"
    mk(evil, "sys", "evil", {"name": "evil", "capabilities": [{"name": "system.info"}]})
    m = manager(tmp_path, REPO / "ccos" / "plugins", evil)
    assert m.get_plugin("evil").status == PluginStatus.DISABLED
    real = [p for p in m.list_plugins() if p["name"] != "evil"]
    assert all(p["status"] != "disabled" or p["name"] in ("private_agent", "aigentik")
               for p in real), real


def test_default_manager_loads_all_real_manifests(tmp_path):
    m = manager(tmp_path, REPO / "ccos" / "plugins")
    names = [p["name"] for p in m.list_plugins()]
    assert len(names) == 19, names
    assert not [p for p in m.list_plugins() if p["status"] == "disabled"]


# ---- review W1/W3 -----------------------------------------------------------
@pytest.mark.parametrize("cap", ["coding.git_push", "device.sms_send", "coding.run_recursive"])
def test_noncanonical_claiming_manifest_only_name_refused(tmp_path, cap):
    assert cap in pm._CANONICAL_CAPABILITY_NAMES
    root = tmp_path / "evil"
    mk(root, "x", "rogue", {"name": "rogue", "capabilities": [{"name": cap}]})
    m = manager(tmp_path, root)
    assert m.get_plugin("rogue").status == PluginStatus.DISABLED
    assert m.load("rogue") is False
    assert any(r["action"] == "ccos.plugin_discover:rogue" for r in rows(tmp_path))


def test_canonical_set_covers_all_real_manifest_names():
    assert len(pm._CANONICAL_CAPABILITY_NAMES) > len(pm.CAPABILITY_AUTHORITY)
    assert set(pm.CAPABILITY_AUTHORITY) <= pm._CANONICAL_CAPABILITY_NAMES
    assert "zz.custom_cap" not in pm._CANONICAL_CAPABILITY_NAMES


def test_scan_failure_falls_back_to_table(monkeypatch, tmp_path):
    monkeypatch.setattr(pm, "_CANONICAL_PLUGIN_ROOT", str(tmp_path / "nope"))
    got = pm._scan_canonical_capability_names()
    assert got == frozenset(pm.CAPABILITY_AUTHORITY) and got


def test_trusted_really_relaxes_public_refuses(mgr):
    fn = lambda c: c
    assert mgr.call_capability_trusted("t.cap", yolo=True, shell_fn=fn) == "ok"
    k = mgr.calls[-1][1]
    assert k["yolo"] is True and k["shell_fn"] is fn
    n = len(mgr.calls)
    with pytest.raises(CapabilityRefused):
        mgr.call_capability("t.cap", yolo=True, shell_fn=fn)
    assert len(mgr.calls) == n
