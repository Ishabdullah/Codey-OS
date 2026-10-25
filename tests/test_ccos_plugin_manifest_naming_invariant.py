"""Class-closing invariant for the NEW-750 bug class (WP2.1 group 6).

Three manifests (device/bridge, device/termux_api, device/termux_api_extended)
each had capabilities whose `implementation` string's module-name prefix
didn't match the manifest's own `"name"` field -- `PluginManager._discover()`
keys `self._modules` by `"name"`, so `call_capability()`'s in-process lookup
(`self._modules.get(mod_name)`) always missed, falling through to a bare,
unaudited `RuntimeError` instead of reaching the authority gate. This is the
third recurrence of the exact same mismatch (see NEW_ISSUES.md's original
`device_bridge` finding), so this test scans every real manifest under
`ccos/plugins/` rather than point-checking the three known instances --
a 4th future manifest with the same mismatch should fail this test, not
wait for live dispatch to surface it again.
"""
import json
from pathlib import Path

import pytest

from ccos.core.manifest_schema_v2 import normalize_manifest

_PLUGINS_ROOT = Path(__file__).resolve().parent.parent / "ccos" / "plugins"

# Execution modes dispatched via an external process/HTTP bridge, not
# PluginManager._modules in-process lookup -- call_capability()'s module-
# name-prefix invariant does not apply to these (see plugin_manager.py's
# own external_process/isolated_daemon/remote_bridge branches).
_EXTERNAL_EXECUTION_MODES = {"external_process", "remote_bridge", "isolated_daemon"}


def _discovered_manifests():
    """Ask a real PluginManager what _discover() accepts (G15g Unit A added
    symlink/duplicate refusals a hand-written directory walk would miss), so
    this scan can never silently diverge from what is actually loaded.
    Empty refusal placeholders are excluded; intentionally disabled full
    definitions remain covered so opt-out cannot erase naming invariants.
    """
    import tempfile

    from ccos.core.capability_registry import CapabilityRegistry
    from ccos.core.plugin_manager import PluginManager, PluginStatus

    with tempfile.TemporaryDirectory(prefix="naming-inv-") as tmp:
        manager = PluginManager([str(_PLUGINS_ROOT)], CapabilityRegistry(str(Path(tmp) / "reg.json")))
        return sorted(
            Path(p.path) / "manifest.json"
            for p in manager._plugins.values() if p.manifest
        )


MANIFEST_PATHS = _discovered_manifests()


def test_discovery_found_the_expected_real_manifests():
    """Guards the scan itself -- if this count is 0 or absurdly small,
    the invariant test below would silently pass over everything."""
    assert len(MANIFEST_PATHS) >= 18, sorted(p.parent.name for p in MANIFEST_PATHS)


@pytest.mark.parametrize(
    "manifest_path", MANIFEST_PATHS, ids=lambda p: f"{p.parent.parent.name}/{p.parent.name}"
)
def test_in_process_capability_implementation_prefix_matches_manifest_name(manifest_path):
    raw = json.loads(manifest_path.read_text())
    manifest = normalize_manifest(raw)
    name = manifest.get("name", manifest_path.parent.name)
    plugin_mode = manifest.get("execution_mode", "in_process")

    for cap in manifest.get("capabilities", []):
        cap_mode = cap.get("execution_mode", plugin_mode)
        if cap_mode in _EXTERNAL_EXECUTION_MODES:
            continue

        impl = cap.get("implementation", "")
        if ":" not in impl or impl.startswith("http://") or impl.startswith("https://"):
            continue

        mod_name = impl.split(":", 1)[0]
        assert mod_name == name, (
            f"{manifest_path}: capability {cap.get('name')!r} implementation "
            f"{impl!r} prefix {mod_name!r} != manifest name {name!r} -- "
            "PluginManager._discover() keys self._modules by the manifest's "
            "own 'name', so this capability would be dispatch-unreachable "
            "(NEW-750 bug class)."
        )
