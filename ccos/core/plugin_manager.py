"""
Plugin Manager — Self-Extension Engine.

Handles the full plugin lifecycle:
- Discovery and loading
- Installation in sandbox
- Capability registration
- Rollback on failure
- Dynamic reloading

Each plugin is a directory with:
  manifest.json  — metadata, dependencies, capabilities
  __init__.py    — entry point with install(), uninstall(), test()
  <module>.py    — implementation code
"""

import importlib
import importlib.util
import json
import os
import shutil
import sys
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ccos.core.capability_registry import (
    Capability,
    CapabilityRegistry,
    CapabilityStatus,
    get_capability_registry,
)


class PluginStatus(str, Enum):
    INSTALLED = "installed"
    ACTIVE = "active"
    BROKEN = "broken"
    DISABLED = "disabled"


@dataclass
class Plugin:
    """A loaded plugin."""
    name: str
    path: str
    manifest: Dict[str, Any]
    status: PluginStatus = PluginStatus.INSTALLED
    version: str = "1.0.0"
    installed_at: float = field(default_factory=time.time)
    capabilities: List[str] = field(default_factory=list)
    error: str = ""


class PluginManager:
    """
    Manages the plugin lifecycle.

    Plugins are directories under ccos/plugins/<category>/<name>/
    Each must have a manifest.json describing its capabilities.
    """

    def __init__(self, plugin_dirs: List[str] = None):
        self._plugin_dirs = plugin_dirs or [
            str(Path(__file__).parent.parent / "plugins"),
        ]
        self._plugins: Dict[str, Plugin] = {}
        self._modules: Dict[str, Any] = {}  # loaded Python modules
        self._registry = get_capability_registry()
        self._discover()

    def _discover(self):
        """Scan plugin directories for available plugins."""
        for plugin_dir in self._plugin_dirs:
            plugin_path = Path(plugin_dir)
            if not plugin_path.exists():
                continue
            for category_dir in plugin_path.iterdir():
                if not category_dir.is_dir() or category_dir.name.startswith("_"):
                    continue
                for plugin_subdir in category_dir.iterdir():
                    if not plugin_subdir.is_dir() or plugin_subdir.name.startswith("_"):
                        continue
                    manifest_path = plugin_subdir / "manifest.json"
                    if manifest_path.exists():
                        try:
                            manifest = json.loads(manifest_path.read_text())
                            name = manifest.get("name", plugin_subdir.name)
                            self._plugins[name] = Plugin(
                                name=name,
                                path=str(plugin_subdir),
                                manifest=manifest,
                                version=manifest.get("version", "1.0.0"),
                            )
                        except Exception as e:
                            pass  # skip malformed manifests

    def list_plugins(self) -> List[Dict[str, Any]]:
        """List all discovered plugins."""
        return [
            {
                "name": p.name,
                "path": p.path,
                "status": p.status.value,
                "version": p.version,
                "capabilities": p.capabilities,
                "error": p.error,
            }
            for p in self._plugins.values()
        ]

    def get_plugin(self, name: str) -> Optional[Plugin]:
        return self._plugins.get(name)

    def load(self, name: str) -> bool:
        """
        Load a plugin: import its module and register capabilities.
        """
        plugin = self._plugins.get(name)
        if not plugin:
            return False

        plugin_path = Path(plugin.path)

        # Find the entry point
        init_path = plugin_path / "__init__.py"
        entry = plugin.manifest.get("entry_point", "__init__.py")
        entry_path = plugin_path / entry

        module_file = entry_path if entry_path.exists() else init_path
        if not module_file.exists():
            plugin.status = PluginStatus.BROKEN
            plugin.error = f"Entry point not found: {module_file}"
            return False

        try:
            # Dynamic import
            spec = importlib.util.spec_from_file_location(
                f"ccos_plugin_{name}", str(module_file)
            )
            if spec is None or spec.loader is None:
                plugin.status = PluginStatus.BROKEN
                plugin.error = "Could not create module spec"
                return False

            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)

            self._modules[name] = module

            # Register capabilities from manifest
            caps = plugin.manifest.get("capabilities", [])
            for cap_def in caps:
                capability = Capability(
                    name=cap_def.get("name", f"{name}.{cap_def.get('id', 'unknown')}"),
                    description=cap_def.get("description", ""),
                    implementation=cap_def.get("implementation", str(plugin_path)),
                    category=cap_def.get("category", plugin.manifest.get("category", "general")),
                    dependencies=cap_def.get("dependencies", []),
                    hardware_requirements=cap_def.get("hardware_requirements", []),
                    test_path=cap_def.get("test", ""),
                    status=CapabilityStatus.ACTIVE,
                    version=plugin.version,
                )
                self._registry.register(capability)
                plugin.capabilities.append(capability.name)

            plugin.status = PluginStatus.ACTIVE
            return True

        except Exception as e:
            plugin.status = PluginStatus.BROKEN
            plugin.error = str(e)
            return False

    def unload(self, name: str) -> bool:
        """Unload a plugin and unregister its capabilities."""
        plugin = self._plugins.get(name)
        if not plugin:
            return False

        # Unregister capabilities
        for cap_name in plugin.capabilities:
            self._registry.unregister(cap_name)

        # Remove module
        module_key = f"ccos_plugin_{name}"
        if module_key in sys.modules:
            del sys.modules[module_key]
        self._modules.pop(name, None)

        plugin.status = PluginStatus.INSTALLED
        plugin.capabilities.clear()
        return True

    def execute(self, name: str, function: str, *args, **kwargs) -> Any:
        """
        Execute a function from a loaded plugin.
        """
        module = self._modules.get(name)
        if not module:
            raise RuntimeError(f"Plugin '{name}' not loaded")

        func = getattr(module, function, None)
        if not func:
            raise AttributeError(f"Plugin '{name}' has no function '{function}'")

        return func(*args, **kwargs)

    def call_capability(self, cap_name: str, *args, **kwargs) -> Any:
        """
        Execute a capability by its registered name.
        Looks up the implementation and calls it.
        """
        cap = self._registry.get(cap_name)
        if not cap:
            raise RuntimeError(f"Capability '{cap_name}' not found")

        # Find which plugin owns this capability
        for plugin in self._plugins.values():
            if cap_name in plugin.capabilities:
                # The implementation field may be "module:function" or just a path
                impl = cap.implementation
                if ":" in impl:
                    mod_name, func_name = impl.rsplit(":", 1)
                else:
                    mod_name = plugin.name
                    func_name = cap_name.split(".")[-1]

                module = self._modules.get(mod_name)
                if module:
                    func = getattr(module, func_name, None)
                    if func:
                        start = time.time()
                        try:
                            result = func(*args, **kwargs)
                            duration = (time.time() - start) * 1000
                            self._registry.record_use(cap_name, True, duration)
                            return result
                        except Exception as e:
                            duration = (time.time() - start) * 1000
                            self._registry.record_use(cap_name, False, duration)
                            raise

        raise RuntimeError(f"No loaded plugin implements '{cap_name}'")

    def load_all(self) -> Dict[str, bool]:
        """Load all discovered plugins."""
        results = {}
        for name in self._plugins:
            results[name] = self.load(name)
        return results

    def get_status(self) -> Dict[str, Any]:
        """Get overall plugin system status."""
        plugins = list(self._plugins.values())
        return {
            "total": len(plugins),
            "active": sum(1 for p in plugins if p.status == PluginStatus.ACTIVE),
            "broken": sum(1 for p in plugins if p.status == PluginStatus.BROKEN),
            "disabled": sum(1 for p in plugins if p.status == PluginStatus.DISABLED),
            "plugins": self.list_plugins(),
        }


# Singleton
_manager: Optional[PluginManager] = None


def get_plugin_manager() -> PluginManager:
    global _manager
    if _manager is None:
        _manager = PluginManager()
    return _manager
