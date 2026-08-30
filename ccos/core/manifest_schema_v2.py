"""
Manifest Schema v2 — Specification, Validation, and Normalization.

Defines the structure and contracts for CCOS v2 plugins and capabilities:
- JSON Schema definition (MANIFEST_V2_JSON_SCHEMA)
- Pure Python validation function (validate_manifest_v2)
- Normalization function for backward compatibility with v1 manifests (normalize_manifest)
"""

from typing import Any, Dict, List, Optional, Tuple, Union

# Valid execution modes in v2
VALID_EXECUTION_MODES = {"in_process", "sandboxed_process", "isolated_daemon"}

# JSON Schema for Manifest v2.0.0
MANIFEST_V2_JSON_SCHEMA: Dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "CCOSPluginManifestV2",
    "type": "object",
    "required": ["name", "version", "description", "capabilities"],
    "properties": {
        "schema_version": {
            "type": "string",
            "default": "2.0.0",
            "pattern": r"^2\.\d+\.\d+$",
        },
        "name": {"type": "string", "minLength": 1},
        "version": {"type": "string", "minLength": 1},
        "description": {"type": "string"},
        "domain": {"type": "string"},
        "category": {"type": "string"},
        "execution_mode": {
            "type": "string",
            "enum": ["in_process", "sandboxed_process", "isolated_daemon"],
            "default": "in_process",
        },
        "entry_point": {"type": "string", "default": "__init__.py"},
        "process_spec": {
            "type": "object",
            "properties": {
                "command": {"type": "array", "items": {"type": "string"}},
                "env": {"type": "object", "additionalProperties": {"type": "string"}},
                "working_dir": {"type": ["string", "null"]},
            },
        },
        "event_triggers": {
            "type": "array",
            "items": {"type": ["string", "object"]},
        },
        "data_store": {
            "type": "object",
            "properties": {
                "type": {"type": "string", "enum": ["sqlite", "json", "ephemeral", "none"]},
                "path": {"type": ["string", "null"]},
                "tables": {"type": "array", "items": {"type": "string"}},
            },
        },
        "resource_limits": {
            "type": "object",
            "properties": {
                "max_memory_mb": {"type": ["number", "integer"]},
                "max_cpu_percent": {"type": ["number", "integer"]},
                "timeout_seconds": {"type": ["number", "integer"]},
            },
        },
        "permissions": {
            "type": "array",
            "items": {"type": "string"},
        },
        "dependencies": {
            "type": "array",
            "items": {"type": "string"},
        },
        "capabilities": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["description", "implementation"],
                "properties": {
                    "id": {"type": "string"},
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "implementation": {"type": "string"},
                    "category": {"type": "string"},
                    "dependencies": {"type": "array", "items": {"type": "string"}},
                    "hardware_requirements": {"type": "array", "items": {"type": "string"}},
                    "inputs_schema": {"type": "object"},
                    "outputs_schema": {"type": "object"},
                    "permissions": {"type": "array", "items": {"type": "string"}},
                    "timeout_seconds": {"type": ["number", "integer"]},
                },
            },
        },
        "author": {"type": "string"},
        "license": {"type": "string"},
    },
}


def validate_manifest_v2(manifest_dict: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validate a manifest dictionary against Manifest Schema v2 rules.
    Pure Python validation without external dependencies.

    Returns:
        (is_valid, list_of_error_messages)
    """
    errors: List[str] = []

    if not isinstance(manifest_dict, dict):
        return False, ["Manifest must be a JSON/dict object"]

    # Top-level required fields
    for req_field in ("name", "version", "description"):
        val = manifest_dict.get(req_field)
        if val is None or not isinstance(val, str) or not val.strip():
            errors.append(f"Missing or invalid required field '{req_field}' (must be non-empty string)")

    # Schema version
    schema_ver = manifest_dict.get("schema_version")
    if schema_ver is not None:
        if not isinstance(schema_ver, str) or not schema_ver.startswith("2."):
            errors.append(f"Invalid schema_version '{schema_ver}': expected 2.x.x")

    # Execution mode
    exec_mode = manifest_dict.get("execution_mode")
    if exec_mode is not None:
        if not isinstance(exec_mode, str) or exec_mode not in VALID_EXECUTION_MODES:
            errors.append(
                f"Invalid execution_mode '{exec_mode}': must be one of {sorted(list(VALID_EXECUTION_MODES))}"
            )

    # Domain / category
    domain = manifest_dict.get("domain")
    if domain is not None and not isinstance(domain, str):
        errors.append("Field 'domain' must be a string")

    category = manifest_dict.get("category")
    if category is not None and not isinstance(category, str):
        errors.append("Field 'category' must be a string")

    # Entry point
    entry_point = manifest_dict.get("entry_point")
    if entry_point is not None and not isinstance(entry_point, str):
        errors.append("Field 'entry_point' must be a string")

    # Resource limits
    resource_limits = manifest_dict.get("resource_limits")
    if resource_limits is not None:
        if not isinstance(resource_limits, dict):
            errors.append("Field 'resource_limits' must be an object/dict")
        else:
            for k in ("max_memory_mb", "max_cpu_percent", "timeout_seconds"):
                if k in resource_limits and not isinstance(resource_limits[k], (int, float)):
                    errors.append(f"resource_limits.{k} must be a number")

    # Permissions
    permissions = manifest_dict.get("permissions")
    if permissions is not None:
        if not isinstance(permissions, list) or not all(isinstance(p, str) for p in permissions):
            errors.append("Field 'permissions' must be a list of strings")

    # Dependencies
    dependencies = manifest_dict.get("dependencies")
    if dependencies is not None:
        if not isinstance(dependencies, list) or not all(isinstance(d, str) for d in dependencies):
            errors.append("Field 'dependencies' must be a list of strings")

    # Process spec
    process_spec = manifest_dict.get("process_spec")
    if process_spec is not None:
        if not isinstance(process_spec, dict):
            errors.append("Field 'process_spec' must be an object/dict")
        else:
            if "command" in process_spec:
                cmd = process_spec["command"]
                if not isinstance(cmd, list) or not all(isinstance(c, str) for c in cmd):
                    errors.append("process_spec.command must be a list of strings")
            if "env" in process_spec:
                env = process_spec["env"]
                if not isinstance(env, dict) or not all(
                    isinstance(k, str) and isinstance(v, str) for k, v in env.items()
                ):
                    errors.append("process_spec.env must be a dict of string key-values")

    # Event triggers
    event_triggers = manifest_dict.get("event_triggers")
    if event_triggers is not None:
        if not isinstance(event_triggers, list):
            errors.append("Field 'event_triggers' must be a list")

    # Data store
    data_store = manifest_dict.get("data_store")
    if data_store is not None:
        if not isinstance(data_store, dict):
            errors.append("Field 'data_store' must be an object/dict")

    # Capabilities
    caps = manifest_dict.get("capabilities")
    if caps is None:
        errors.append("Missing required field 'capabilities'")
    elif not isinstance(caps, list):
        errors.append("Field 'capabilities' must be a list")
    else:
        for idx, cap in enumerate(caps):
            if not isinstance(cap, dict):
                errors.append(f"capabilities[{idx}] must be a dict")
                continue

            cap_id = cap.get("id") or cap.get("name")
            if not cap_id or not isinstance(cap_id, str):
                errors.append(f"capabilities[{idx}] must specify a string 'id' or 'name'")

            impl = cap.get("implementation")
            if not impl or not isinstance(impl, str):
                errors.append(f"capabilities[{idx}] must specify a string 'implementation'")

            desc = cap.get("description")
            if desc is not None and not isinstance(desc, str):
                errors.append(f"capabilities[{idx}].description must be a string")

            if "inputs_schema" in cap and not isinstance(cap["inputs_schema"], dict):
                errors.append(f"capabilities[{idx}].inputs_schema must be a dict")

            if "outputs_schema" in cap and not isinstance(cap["outputs_schema"], dict):
                errors.append(f"capabilities[{idx}].outputs_schema must be a dict")

            if "dependencies" in cap:
                if not isinstance(cap["dependencies"], list) or not all(
                    isinstance(d, str) for d in cap["dependencies"]
                ):
                    errors.append(f"capabilities[{idx}].dependencies must be a list of strings")

            if "hardware_requirements" in cap:
                if not isinstance(cap["hardware_requirements"], list) or not all(
                    isinstance(h, str) for h in cap["hardware_requirements"]
                ):
                    errors.append(f"capabilities[{idx}].hardware_requirements must be a list of strings")

            if "permissions" in cap:
                if not isinstance(cap["permissions"], list) or not all(
                    isinstance(p, str) for p in cap["permissions"]
                ):
                    errors.append(f"capabilities[{idx}].permissions must be a list of strings")

            if "timeout_seconds" in cap and not isinstance(cap["timeout_seconds"], (int, float)):
                errors.append(f"capabilities[{idx}].timeout_seconds must be a number")

    return len(errors) == 0, errors


def normalize_manifest(manifest_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize a manifest (v1 or v2) into a compliant Schema v2 structure.
    Ensures backward compatibility while filling in v2 defaults.
    """
    if not isinstance(manifest_dict, dict):
        return {}

    normalized: Dict[str, Any] = dict(manifest_dict)

    # Default schema version
    normalized["schema_version"] = manifest_dict.get("schema_version", "2.0.0")

    # Domain fallback to category or 'general'
    domain = manifest_dict.get("domain") or manifest_dict.get("category") or "general"
    normalized["domain"] = domain
    if "category" not in normalized:
        normalized["category"] = domain

    # Execution mode
    normalized["execution_mode"] = manifest_dict.get("execution_mode", "in_process")
    if normalized["execution_mode"] not in VALID_EXECUTION_MODES:
        normalized["execution_mode"] = "in_process"

    # Entry point
    normalized["entry_point"] = manifest_dict.get("entry_point", "__init__.py")

    # Process spec, event triggers, data store, resource limits, permissions, dependencies
    normalized["process_spec"] = manifest_dict.get("process_spec", {})
    normalized["event_triggers"] = manifest_dict.get("event_triggers", [])
    normalized["data_store"] = manifest_dict.get("data_store", {})
    normalized["resource_limits"] = manifest_dict.get("resource_limits", {})
    normalized["permissions"] = manifest_dict.get("permissions", [])
    normalized["dependencies"] = manifest_dict.get("dependencies", [])

    # Capabilities normalization
    caps = manifest_dict.get("capabilities", [])
    normalized_caps = []
    if isinstance(caps, list):
        for cap in caps:
            if not isinstance(cap, dict):
                continue
            cap_copy = dict(cap)
            cap_id = cap.get("id") or cap.get("name", "")
            cap_name = cap.get("name") or cap.get("id", "")
            cap_copy["id"] = cap_id
            cap_copy["name"] = cap_name
            cap_copy["description"] = cap.get("description", "")
            cap_copy["implementation"] = cap.get("implementation", "")
            cap_copy["category"] = cap.get("category", domain)
            cap_copy["dependencies"] = cap.get("dependencies", [])
            cap_copy["hardware_requirements"] = cap.get("hardware_requirements", [])
            cap_copy["inputs_schema"] = cap.get("inputs_schema", {})
            cap_copy["outputs_schema"] = cap.get("outputs_schema", {})
            cap_copy["permissions"] = cap.get("permissions", normalized["permissions"])
            cap_copy["timeout_seconds"] = cap.get("timeout_seconds", 0)
            normalized_caps.append(cap_copy)

    normalized["capabilities"] = normalized_caps
    return normalized
