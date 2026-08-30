#!/usr/bin/env python3
"""
Unit tests for Manifest Schema v2 validation, normalization, and plugin integration.
"""

import copy
import json
import pytest
from pathlib import Path

from ccos.core.manifest_schema_v2 import (
    MANIFEST_V2_JSON_SCHEMA,
    VALID_EXECUTION_MODES,
    validate_manifest_v2,
    normalize_manifest,
)
from ccos.core.capability_registry import Capability, CapabilityRegistry, CapabilityStatus
from ccos.core.plugin_manager import PluginManager, PluginStatus


@pytest.fixture
def sample_valid_v2_manifest():
    return {
        "schema_version": "2.0.0",
        "name": "sample_plugin",
        "version": "2.1.0",
        "description": "Sample plugin for testing Schema v2",
        "domain": "system",
        "execution_mode": "sandboxed_process",
        "entry_point": "sample.py",
        "process_spec": {
            "command": ["python3", "sample.py"],
            "env": {"DEBUG": "1"},
        },
        "resource_limits": {
            "max_memory_mb": 256,
            "max_cpu_percent": 50,
            "timeout_seconds": 15,
        },
        "permissions": ["system:read", "fs:read"],
        "dependencies": ["requests"],
        "capabilities": [
            {
                "name": "system.sample_action",
                "description": "Performs sample action",
                "implementation": "sample:run_sample",
                "category": "system",
                "dependencies": [],
                "hardware_requirements": [],
                "inputs_schema": {
                    "type": "object",
                    "properties": {"arg1": {"type": "string"}},
                },
                "outputs_schema": {
                    "type": "object",
                    "properties": {"result": {"type": "string"}},
                },
                "permissions": ["system:read"],
                "timeout_seconds": 10,
            }
        ],
    }


def test_valid_manifest_v2_validation(sample_valid_v2_manifest):
    valid, errors = validate_manifest_v2(sample_valid_v2_manifest)
    assert valid is True
    assert len(errors) == 0


def test_invalid_manifest_missing_required_fields():
    # Not a dict
    valid, errors = validate_manifest_v2("not a dict")
    assert valid is False
    assert any("JSON/dict object" in e for e in errors)

    # Missing name, version, description, capabilities
    valid, errors = validate_manifest_v2({})
    assert valid is False
    assert any("name" in e for e in errors)
    assert any("version" in e for e in errors)
    assert any("description" in e for e in errors)
    assert any("capabilities" in e for e in errors)


def test_invalid_manifest_schema_version():
    manifest = {
        "schema_version": "1.0.0",
        "name": "test",
        "version": "1.0.0",
        "description": "test",
        "capabilities": [
            {"name": "test.cap", "description": "test", "implementation": "test:test"}
        ],
    }
    valid, errors = validate_manifest_v2(manifest)
    assert valid is False
    assert any("schema_version" in e for e in errors)


def test_invalid_execution_mode(sample_valid_v2_manifest):
    bad = copy.deepcopy(sample_valid_v2_manifest)
    bad["execution_mode"] = "invalid_kernel_mode"
    valid, errors = validate_manifest_v2(bad)
    assert valid is False
    assert any("execution_mode" in e for e in errors)


def test_invalid_resource_limits_and_permissions(sample_valid_v2_manifest):
    bad = copy.deepcopy(sample_valid_v2_manifest)
    bad["resource_limits"] = {"max_memory_mb": "not_a_number"}
    bad["permissions"] = "not_a_list"
    valid, errors = validate_manifest_v2(bad)
    assert valid is False
    assert any("resource_limits.max_memory_mb" in e for e in errors)
    assert any("permissions" in e for e in errors)


def test_invalid_capabilities(sample_valid_v2_manifest):
    bad = copy.deepcopy(sample_valid_v2_manifest)
    bad["capabilities"] = [
        {"description": "no name or impl"},  # missing id/name and implementation
        {
            "id": "cap2",
            "implementation": "test:test",
            "inputs_schema": "not_a_dict",
        },
    ]
    valid, errors = validate_manifest_v2(bad)
    assert valid is False
    assert any("id" in e or "name" in e for e in errors)
    assert any("implementation" in e for e in errors)
    assert any("inputs_schema" in e for e in errors)


def test_normalize_manifest_legacy_v1():
    legacy_v1 = {
        "name": "legacy_plugin",
        "version": "1.0.0",
        "description": "Legacy plugin without v2 fields",
        "category": "coding",
        "entry_point": "legacy.py",
        "capabilities": [
            {
                "name": "coding.legacy_action",
                "description": "Legacy action",
                "implementation": "legacy:action",
                "dependencies": ["git"],
            }
        ],
    }

    normalized = normalize_manifest(legacy_v1)
    assert normalized["schema_version"] == "2.0.0"
    assert normalized["domain"] == "coding"
    assert normalized["execution_mode"] == "in_process"
    assert isinstance(normalized["resource_limits"], dict)
    assert isinstance(normalized["permissions"], list)
    assert len(normalized["capabilities"]) == 1

    cap = normalized["capabilities"][0]
    assert cap["name"] == "coding.legacy_action"
    assert cap["id"] == "coding.legacy_action"
    assert cap["inputs_schema"] == {}
    assert cap["outputs_schema"] == {}
    assert cap["dependencies"] == ["git"]

    # Validate the normalized manifest
    valid, errors = validate_manifest_v2(normalized)
    assert valid is True
    assert len(errors) == 0


def test_capability_dataclass_v2_fields():
    cap = Capability(
        name="test.v2_cap",
        description="Test v2 capability",
        implementation="test:v2_cap",
        category="test",
        execution_mode="isolated_daemon",
        resource_limits={"max_memory_mb": 128},
        permissions=["device:read"],
        inputs_schema={"type": "object"},
        outputs_schema={"type": "object"},
    )
    cap_dict = cap.to_dict()
    assert cap_dict["execution_mode"] == "isolated_daemon"
    assert cap_dict["resource_limits"]["max_memory_mb"] == 128
    assert cap_dict["permissions"] == ["device:read"]
    assert cap_dict["inputs_schema"] == {"type": "object"}
    assert cap_dict["outputs_schema"] == {"type": "object"}


def test_plugin_manager_v2_metadata_parsing(tmp_path):
    # Create a temporary plugin directory
    plugin_cat = tmp_path / "system"
    plugin_cat.mkdir(parents=True)
    plugin_dir = plugin_cat / "v2_test_plugin"
    plugin_dir.mkdir()

    manifest_content = {
        "schema_version": "2.0.0",
        "name": "v2_test_plugin",
        "version": "2.0.0",
        "description": "V2 test plugin",
        "domain": "system",
        "execution_mode": "sandboxed_process",
        "entry_point": "__init__.py",
        "permissions": ["system:read"],
        "resource_limits": {"max_memory_mb": 512},
        "capabilities": [
            {
                "name": "system.v2_action",
                "description": "V2 Action",
                "implementation": "v2_test_plugin:action",
                "inputs_schema": {"type": "object"},
                "outputs_schema": {"type": "object"},
            }
        ],
    }
    (plugin_dir / "manifest.json").write_text(json.dumps(manifest_content))
    (plugin_dir / "__init__.py").write_text("def action(): return 'success'\n")

    registry = CapabilityRegistry(store_path=str(tmp_path / "caps.json"))
    pm = PluginManager(plugin_dirs=[str(tmp_path)], registry=registry)

    plugin = pm.get_plugin("v2_test_plugin")
    assert plugin is not None
    assert plugin.domain == "system"
    assert plugin.execution_mode == "sandboxed_process"
    assert plugin.permissions == ["system:read"]
    assert plugin.resource_limits == {"max_memory_mb": 512}

    assert pm.load("v2_test_plugin") is True
    cap = registry.get("system.v2_action")
    assert cap is not None
    assert cap.execution_mode == "sandboxed_process"
    assert cap.permissions == ["system:read"]
    assert cap.resource_limits == {"max_memory_mb": 512}
    assert cap.inputs_schema == {"type": "object"}
