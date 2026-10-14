"""PluginManager.call_capability() gating/authority tests (WP2.1 group 4,
NEW-910/911/912).

Covers: fail-closed default for unclassified names, the manifest-tag
raise-only floor, handler-registered authority (required kwarg, raise-
only relative to the core table), record_use accounting (ALLOWED/FAILED
only, never on REFUSED), exact audit record shape, and exception-
identity/`__cause__` preservation on both the in-process and the HTTP
dispatch paths.
"""
import json
from unittest import mock

import pytest

from ccos.core.capability_registry import Capability, CapabilityRegistry
from ccos.core.plugin_manager import (
    CAPABILITY_AUTHORITY,
    CapabilityRefused,
    Plugin,
    PluginManager,
    PluginStatus,
)
from core.action_gateway import ACT, HIGH_IMPACT, READ, ActionGateway


@pytest.fixture
def pm_and_gateway(tmp_path, monkeypatch):
    """A PluginManager wired to its own fresh registry, and the real
    ActionGateway singleton redirected to a tmp_path audit file -- same
    monkeypatch-the-getter pattern as tests/test_shell_refusal_accounting.py's
    `gateway` fixture, applied to the module plugin_manager.py actually
    imports `get_action_gateway` from."""
    import ccos.core.plugin_manager as plugin_manager_module

    audit = tmp_path / "audit.jsonl"
    instance = ActionGateway(audit_file=audit)
    monkeypatch.setattr(plugin_manager_module, "get_action_gateway", lambda: instance)

    registry = CapabilityRegistry(store_path=str(tmp_path / "caps.json"))
    pm = PluginManager(registry=registry)
    return pm, instance, audit


def _audit_rows(audit_path):
    if not audit_path.exists():
        return []
    return [json.loads(line) for line in audit_path.read_text().splitlines()]


# ── Fail-closed default for unclassified names ──────────────────────────

def test_unclassified_registry_capability_is_refused(pm_and_gateway):
    pm, gateway, audit = pm_and_gateway
    pm._registry.register(
        Capability(name="unclassified.thing", description="", implementation="x:y")
    )
    pm._modules["x"] = mock.Mock()

    with pytest.raises(CapabilityRefused, match="fail-closed default"):
        pm.call_capability("unclassified.thing")

    rows = _audit_rows(audit)
    assert len(rows) == 1
    assert rows[0]["authority"] == HIGH_IMPACT
    assert rows[0]["outcome"] == "refused"
    assert rows[0]["command"] == "unclassified.thing"
    assert "fail-closed default" in rows[0]["reason"]

    cap = pm._registry.get("unclassified.thing")
    assert cap.use_count == 0  # REFUSED must never be recorded


def test_refused_dispatch_never_calls_record_use(pm_and_gateway, tmp_path):
    """Code-reviewer W3: record_use must never fire on OUTCOME_REFUSED,
    for both the unclassified-default and manifest-raise-tag refusal
    shapes, not just the registry use_count proxy check above."""
    pm, gateway, audit = pm_and_gateway
    pm._registry.register(
        Capability(name="unclassified.other", description="", implementation="x:y")
    )
    pm._registry.register(
        Capability(
            name="device.another_unknown",
            description="",
            implementation="x:y",
            permissions=["device:control"],
        )
    )
    pm._modules["x"] = mock.Mock()
    plugin = Plugin(
        name="x", path=str(tmp_path), manifest={}, status=PluginStatus.ACTIVE,
        capabilities=["unclassified.other", "device.another_unknown"],
    )
    pm._plugins["x"] = plugin

    with mock.patch.object(pm._registry, "record_use") as record_use:
        with pytest.raises(CapabilityRefused):
            pm.call_capability("unclassified.other")
        with pytest.raises(CapabilityRefused):
            pm.call_capability("device.another_unknown")
        record_use.assert_not_called()


def test_not_found_capability_still_raises_plain_runtime_error(pm_and_gateway):
    """Pre-existing "not found" behavior (unregistered name) is distinct
    from CapabilityRefused (registered/handler-registered but refused)."""
    pm, gateway, audit = pm_and_gateway
    with pytest.raises(RuntimeError) as exc_info:
        pm.call_capability("nonexistent.capability")
    assert not isinstance(exc_info.value, CapabilityRefused)
    assert not audit.exists()


# ── Manifest-tag raise-only floor ────────────────────────────────────────

def test_manifest_raise_tag_forces_high_impact_and_refuses(pm_and_gateway, tmp_path):
    pm, gateway, audit = pm_and_gateway
    # Not in CAPABILITY_AUTHORITY at all -- classified ONLY by the
    # device:write raise tag, demonstrating the tag alone is sufficient
    # to classify (and, since HIGH_IMPACT fails closed unconditionally
    # this round, to refuse) an otherwise-unclassified name.
    assert "device.unknown_action" not in CAPABILITY_AUTHORITY
    pm._registry.register(
        Capability(
            name="device.unknown_action",
            description="",
            implementation="x:y",
            permissions=["device:write"],
        )
    )
    pm._modules["x"] = mock.Mock()
    plugin = Plugin(
        name="x",
        path=str(tmp_path),
        manifest={},
        status=PluginStatus.ACTIVE,
        capabilities=["device.unknown_action"],
    )
    pm._plugins["x"] = plugin

    with pytest.raises(CapabilityRefused, match="HIGH_IMPACT"):
        pm.call_capability("device.unknown_action")

    rows = _audit_rows(audit)
    assert len(rows) == 1
    assert rows[0]["authority"] == HIGH_IMPACT
    assert rows[0]["outcome"] == "refused"


def test_manifest_tag_cannot_lower_core_table_classification(pm_and_gateway):
    """crm_core_query's actual manifest tag is "crm:read" (not a raise
    tag) -- confirms a non-raise tag leaves the core table's READ
    classification untouched, i.e. it can't accidentally be read as
    lowering anything."""
    pm, gateway, audit = pm_and_gateway
    cap = Capability(
        name="crm.list_leads",
        description="",
        implementation="x:y",
        permissions=["crm:read"],
    )
    pm._registry.register(cap)
    authority = pm._authority_for("crm.list_leads", cap)
    assert authority == READ


# ── Handler-registered authority ─────────────────────────────────────────

def test_register_capability_handler_requires_authority_kwarg(pm_and_gateway):
    pm, gateway, audit = pm_and_gateway
    with pytest.raises(TypeError):
        pm.register_capability_handler("some.handler", lambda: None)


def test_register_capability_handler_rejects_unknown_authority(pm_and_gateway):
    pm, gateway, audit = pm_and_gateway
    with pytest.raises(ValueError, match="Unknown authority class"):
        pm.register_capability_handler("some.handler", lambda: None, authority="not-a-real-class")


def test_handler_only_capability_dispatches_with_explicit_authority(pm_and_gateway):
    pm, gateway, audit = pm_and_gateway
    pm.register_capability_handler("handler.only", lambda: "ok", authority=READ)
    result = pm.call_capability("handler.only")
    assert result == "ok"

    rows = _audit_rows(audit)
    assert len(rows) == 1
    assert rows[0]["authority"] == READ
    assert rows[0]["outcome"] == "allowed"
    assert rows[0]["command"] == "handler.only"
    # Audit record shape stays simple: no argument keys/values recorded.
    assert set(rows[0].keys()) == {"ts", "authority", "action", "command", "outcome", "reason"}

    cap = pm._registry.get("handler.only")
    assert cap is None  # confirms this really is the cap-is-None handler-only path


def test_handler_authority_cannot_shadow_core_table_downward(pm_and_gateway):
    """coding.run_agent is ACT in the core table; a handler registered
    with authority=READ must NOT lower the effective classification."""
    pm, gateway, audit = pm_and_gateway
    pm.register_capability_handler("coding.run_agent", lambda **kw: "handled", authority=READ)
    effective = pm._authority_for("coding.run_agent", pm._registry.get("coding.run_agent"))
    assert effective == ACT


# ── record_use accounting: ALLOWED / FAILED only, never REFUSED ─────────

def test_allowed_dispatch_records_success(pm_and_gateway):
    pm, gateway, audit = pm_and_gateway
    pm.register_capability_handler("handler.read", lambda: 42, authority=READ)
    assert pm.call_capability("handler.read") == 42
    cap = pm._registry.get("handler.read")
    assert cap is None  # handler-only: nothing to assert on registry use_count


def test_failed_dispatch_records_failure_and_reraises_original(pm_and_gateway):
    pm, gateway, audit = pm_and_gateway
    original = ValueError("boom")

    def _boom():
        raise original

    pm.register_capability_handler("handler.boom", _boom, authority=ACT)

    with pytest.raises(ValueError) as exc_info:
        pm.call_capability("handler.boom")

    assert exc_info.value is original

    rows = _audit_rows(audit)
    assert len(rows) == 1
    assert rows[0]["outcome"] == "failed"
    assert rows[0]["authority"] == ACT


# ── In-process module dispatch: exception identity + __cause__ ─────────

def test_in_process_dispatch_preserves_exception_identity_and_cause(pm_and_gateway, tmp_path):
    pm, gateway, audit = pm_and_gateway
    root_cause = KeyError("root cause")
    original = RuntimeError("in-process failure")
    original.__cause__ = root_cause

    def _raiser(**kwargs):
        raise original

    module = mock.Mock()
    module.do_thing = _raiser
    pm._modules["in_process_plugin"] = module

    plugin = Plugin(
        name="in_process_plugin",
        path=str(tmp_path),
        manifest={},
        status=PluginStatus.ACTIVE,
        capabilities=["in_process.cap"],
    )
    pm._plugins["in_process_plugin"] = plugin
    pm._registry.register(
        Capability(
            name="in_process.cap",
            description="",
            implementation="in_process_plugin:do_thing",
            execution_mode="in_process",
        )
    )
    import ccos.core.plugin_manager as plugin_manager_module

    monkeypatch_table = plugin_manager_module.CAPABILITY_AUTHORITY
    monkeypatch_table["in_process.cap"] = READ
    try:
        with pytest.raises(RuntimeError) as exc_info:
            pm.call_capability("in_process.cap")
        assert exc_info.value is original
        assert exc_info.value.__cause__ is root_cause
    finally:
        monkeypatch_table.pop("in_process.cap", None)

    rows = _audit_rows(audit)
    assert len(rows) == 1
    assert rows[0]["outcome"] == "failed"


# ── HTTP/remote_bridge dispatch: exception identity + __cause__ ────────

def test_http_dispatch_preserves_exception_identity_and_cause(pm_and_gateway, tmp_path):
    pm, gateway, audit = pm_and_gateway
    plugin = Plugin(
        name="http_plugin",
        path=str(tmp_path),
        manifest={"process_spec": {"endpoint": "http://127.0.0.1:9/transcribe"}},
        status=PluginStatus.ACTIVE,
        execution_mode="remote_bridge",
        capabilities=["http.cap"],
    )
    pm._plugins["http_plugin"] = plugin
    pm._registry.register(
        Capability(
            name="http.cap",
            description="",
            implementation="http.cap",  # not itself a URL; endpoint comes from process_spec
            execution_mode="remote_bridge",
        )
    )
    import ccos.core.plugin_manager as plugin_manager_module

    plugin_manager_module.CAPABILITY_AUTHORITY["http.cap"] = READ
    underlying = ConnectionRefusedError("connection refused")
    try:
        with mock.patch("urllib.request.urlopen", side_effect=underlying):
            with pytest.raises(RuntimeError) as exc_info:
                pm.call_capability("http.cap")
        assert "connection refused" in str(exc_info.value)
        assert exc_info.value.__cause__ is underlying
        first_raise = exc_info.value
        # Re-run to confirm call_capability() re-raises the SAME wrapped
        # object its own thunk built, not a fresh stringified rebuild.
        with mock.patch("urllib.request.urlopen", side_effect=underlying):
            with pytest.raises(RuntimeError) as exc_info_2:
                pm.call_capability("http.cap")
        assert exc_info_2.value is not first_raise  # distinct calls, distinct objects
        assert exc_info_2.value.__cause__ is underlying
    finally:
        plugin_manager_module.CAPABILITY_AUTHORITY.pop("http.cap", None)

    rows = _audit_rows(audit)
    assert len(rows) == 2
    assert all(r["outcome"] == "failed" for r in rows)
