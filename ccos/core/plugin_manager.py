"""
Plugin Manager — Self-Extension Engine.

Handles the full plugin lifecycle:
- Discovery and loading
- Installation in sandbox
- Capability registration
- External process supervision (start, stop, health checking, Rule 3 PID tracking)
- Rollback on failure
- Dynamic reloading

Each plugin is a directory with:
  manifest.json  — metadata, dependencies, capabilities
  __init__.py    — entry point with install(), uninstall(), test()
  <module>.py    — implementation code
"""

import importlib
import importlib.util
import inspect
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

from ccos.core.capability_registry import (
    Capability,
    CapabilityRegistry,
    CapabilityStatus,
    get_capability_registry,
)
from ccos.core.manifest_schema_v2 import normalize_manifest
from ccos.core.task_context import TaskContext
from utils.logger import info, warning


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
    domain: str = "general"
    execution_mode: str = "in_process"
    permissions: List[str] = field(default_factory=list)
    resource_limits: Dict[str, Any] = field(default_factory=dict)
    installed_at: float = field(default_factory=time.time)
    capabilities: List[str] = field(default_factory=list)
    error: str = ""
    pid: Optional[int] = None


class ProcessSupervisor:
    """
    Supervises external process plugins with exact PID tracking and clean shutdown.
    Strictly follows Rule 3: only operates on exact tracked PIDs, never issues wildcard kills.
    """

    def __init__(self):
        self._processes: Dict[str, subprocess.Popen] = {}
        self._pid_files: Dict[str, Path] = {}

    def start_external_plugin(
        self, plugin: Plugin, state_dir: Optional[Path] = None
    ) -> bool:
        """
        Start an external process plugin according to its process_spec.
        Tracks exact PID and creates pid file if specified.
        """
        process_spec = plugin.manifest.get("process_spec", {})
        cmd = (
            process_spec.get("start_command")
            or process_spec.get("command")
        )
        if not cmd:
            entry_point = plugin.manifest.get("entry_point", "__init__.py")
            entry_file = Path(plugin.path) / entry_point
            if entry_file.exists():
                cmd = [sys.executable, str(entry_file)]
            else:
                plugin.status = PluginStatus.BROKEN
                plugin.error = "No start_command or entry_point found for external process"
                return False

        working_dir = process_spec.get("working_dir") or plugin.path
        env = dict(os.environ)
        if "env" in process_spec and isinstance(process_spec["env"], dict):
            env.update(process_spec["env"])

        # Determine pid file location
        pid_file_str = process_spec.get("pid_file")
        pid_path = None
        if pid_file_str:
            pid_path = Path(pid_file_str)
            if not pid_path.is_absolute():
                pid_path = Path(plugin.path) / pid_file_str
            self._pid_files[plugin.name] = pid_path

        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(working_dir),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self._processes[plugin.name] = proc
            plugin.pid = proc.pid

            if pid_path:
                pid_path.parent.mkdir(parents=True, exist_ok=True)
                pid_path.write_text(str(proc.pid))

            # Optional health check verification
            health_endpoint = process_spec.get("health_endpoint")
            if health_endpoint:
                healthy = self.check_health(plugin.name, health_endpoint=health_endpoint)
                if not healthy:
                    warning(f"ProcessSupervisor: plugin '{plugin.name}' started but health check failed at {health_endpoint}")

            return True

        except Exception as e:
            plugin.status = PluginStatus.BROKEN
            plugin.error = f"Failed to spawn external process: {e}"
            return False

    def stop_external_plugin(
        self,
        plugin_name: str,
        pid_file: Optional[Union[str, Path]] = None,
        timeout: float = 3.0,
    ) -> bool:
        """
        Stop an external plugin process with clean SIGTERM -> SIGKILL escalation.
        Rule 3: only kills the exact tracked PID.
        """
        proc = self._processes.pop(plugin_name, None)
        pid = None
        if proc:
            pid = proc.pid

        # Check PID file if proc reference not available
        pid_path = Path(pid_file) if pid_file else self._pid_files.pop(plugin_name, None)
        if pid is None and pid_path and pid_path.exists():
            try:
                pid = int(pid_path.read_text().strip())
            except Exception:
                pid = None

        if pid is None or pid <= 0:
            if pid_path and pid_path.exists():
                try:
                    pid_path.unlink()
                except OSError:
                    pass
            return True

        # Rule 3: Terminate exact PID only
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        except PermissionError:
            pass

        # Wait for process to exit cleanly
        deadline = time.time() + timeout
        alive = True
        while time.time() < deadline:
            if proc:
                if proc.poll() is not None:
                    alive = False
                    break
            else:
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    alive = False
                    break
                except PermissionError:
                    alive = True
                    break
            time.sleep(0.05)

        # Escalate to SIGKILL if still alive
        if alive:
            try:
                os.kill(pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass

        if pid_path and pid_path.exists():
            try:
                pid_path.unlink()
            except OSError:
                pass

        return True

    def check_health(
        self, plugin_name: str, health_endpoint: Optional[str] = None
    ) -> bool:
        """
        Check health of an external plugin via process liveness and optional HTTP endpoint.
        """
        proc = self._processes.get(plugin_name)
        if proc:
            if proc.poll() is not None:
                return False

        if health_endpoint:
            try:
                req = urllib.request.Request(health_endpoint, headers={"User-Agent": "Codey-OS-PluginSupervisor"})
                with urllib.request.urlopen(req, timeout=1.5) as resp:
                    return resp.status < 400
            except Exception:
                return False

        return proc is not None and proc.poll() is None


class PluginManager:
    """
    Manages the plugin lifecycle: discovery, loading, unloading, execution,
    and process supervision for external_process and remote_bridge plugins.
    """

    def __init__(self, plugin_dirs: List[str] = None, registry: Optional[CapabilityRegistry] = None):
        self._plugin_dirs = plugin_dirs or [
            str(Path(__file__).parent.parent / "plugins"),
        ]
        self._plugins: Dict[str, Plugin] = {}
        self._modules: Dict[str, Any] = {}  # loaded Python modules
        self._registry = registry or get_capability_registry()
        self._handlers: Dict[str, Callable] = {}
        self.supervisor = ProcessSupervisor()
        self._discover()

    def register_capability_handler(self, cap_name: str, handler: Callable):
        """Register an in-memory direct handler for a capability."""
        self._handlers[cap_name] = handler

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
                            raw_manifest = json.loads(manifest_path.read_text())
                            manifest = normalize_manifest(raw_manifest)
                            name = manifest.get("name", plugin_subdir.name)
                            self._plugins[name] = Plugin(
                                name=name,
                                path=str(plugin_subdir),
                                manifest=manifest,
                                version=manifest.get("version", "1.0.0"),
                                domain=manifest.get("domain", "general"),
                                execution_mode=manifest.get("execution_mode", "in_process"),
                                permissions=manifest.get("permissions", []),
                                resource_limits=manifest.get("resource_limits", {}),
                            )
                        except Exception:
                            pass  # skip malformed manifests

    def list_plugins(self) -> List[Dict[str, Any]]:
        """List all discovered plugins."""
        return [
            {
                "name": p.name,
                "path": p.path,
                "status": p.status.value,
                "version": p.version,
                "execution_mode": p.execution_mode,
                "capabilities": p.capabilities,
                "error": p.error,
                "pid": p.pid,
            }
            for p in self._plugins.values()
        ]

    def get_plugin(self, name: str) -> Optional[Plugin]:
        return self._plugins.get(name)

    def load(self, name: str) -> bool:
        """
        Load a plugin: import its module or start external process, and register capabilities.
        """
        plugin = self._plugins.get(name)
        if not plugin:
            return False

        plugin_path = Path(plugin.path)
        exec_mode = plugin.execution_mode

        # External process or isolated daemon supervision
        if exec_mode in ("external_process", "isolated_daemon", "remote_bridge"):
            started = self.supervisor.start_external_plugin(plugin)
            if not started:
                return False

            # Register capabilities from manifest
            caps = plugin.manifest.get("capabilities", [])
            for cap_def in caps:
                capability = Capability(
                    name=cap_def.get("name", f"{name}.{cap_def.get('id', 'unknown')}"),
                    description=cap_def.get("description", ""),
                    implementation=cap_def.get("implementation", str(plugin_path)),
                    category=cap_def.get("category", plugin.manifest.get("domain", plugin.manifest.get("category", "general"))),
                    dependencies=cap_def.get("dependencies", []),
                    hardware_requirements=cap_def.get("hardware_requirements", []),
                    test_path=cap_def.get("test", ""),
                    status=CapabilityStatus.ACTIVE,
                    version=plugin.version,
                    execution_mode=cap_def.get("execution_mode", exec_mode),
                    resource_limits=cap_def.get("resource_limits", plugin.manifest.get("resource_limits", {})),
                    permissions=cap_def.get("permissions", plugin.manifest.get("permissions", [])),
                    inputs_schema=cap_def.get("inputs_schema", {}),
                    outputs_schema=cap_def.get("outputs_schema", {}),
                )
                self._registry.register(capability)
                plugin.capabilities.append(capability.name)

            plugin.status = PluginStatus.ACTIVE
            return True

        # In-process or sandboxed Python module loading
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
                    category=cap_def.get("category", plugin.manifest.get("domain", plugin.manifest.get("category", "general"))),
                    dependencies=cap_def.get("dependencies", []),
                    hardware_requirements=cap_def.get("hardware_requirements", []),
                    test_path=cap_def.get("test", ""),
                    status=CapabilityStatus.ACTIVE,
                    version=plugin.version,
                    execution_mode=cap_def.get("execution_mode", exec_mode),
                    resource_limits=cap_def.get("resource_limits", plugin.manifest.get("resource_limits", {})),
                    permissions=cap_def.get("permissions", plugin.manifest.get("permissions", [])),
                    inputs_schema=cap_def.get("inputs_schema", {}),
                    outputs_schema=cap_def.get("outputs_schema", {}),
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
        """Unload a plugin, stop any external process, and unregister its capabilities."""
        plugin = self._plugins.get(name)
        if not plugin:
            return False

        # Stop external process if applicable
        if plugin.execution_mode in ("external_process", "isolated_daemon", "remote_bridge"):
            pid_file = plugin.manifest.get("process_spec", {}).get("pid_file")
            self.supervisor.stop_external_plugin(name, pid_file=pid_file)
            plugin.pid = None

        # Unregister capabilities
        for cap_name in list(plugin.capabilities):
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
        Execute a function from a loaded in-process plugin.
        """
        module = self._modules.get(name)
        if not module:
            raise RuntimeError(f"Plugin '{name}' not loaded")

        func = getattr(module, function, None)
        if not func:
            raise AttributeError(f"Plugin '{name}' has no function '{function}'")

        return func(*args, **kwargs)

    def call_capability(
        self,
        cap_name: str,
        *args,
        context: Optional[TaskContext] = None,
        **kwargs,
    ) -> Any:
        """
        Execute a capability by its registered name.
        Supports in-process functions, direct handlers, and external process HTTP/IPC dispatch.
        """
        cap = self._registry.get(cap_name)
        if not cap and cap_name not in self._handlers:
            raise RuntimeError(f"Capability '{cap_name}' not found")

        # Direct/mock handler registered
        if cap_name in self._handlers:
            func = self._handlers[cap_name]
            start = time.time()
            call_kwargs = dict(kwargs)
            if context is not None:
                try:
                    sig = inspect.signature(func)
                    accepts_context = "context" in sig.parameters
                    accepts_varkw = any(
                        p.kind == inspect.Parameter.VAR_KEYWORD
                        for p in sig.parameters.values()
                    )
                    if accepts_context or accepts_varkw:
                        call_kwargs["context"] = context
                except (ValueError, TypeError):
                    pass
            try:
                result = func(*args, **call_kwargs)
                duration = (time.time() - start) * 1000
                self._registry.record_use(cap_name, True, duration)
                return result
            except Exception as e:
                duration = (time.time() - start) * 1000
                self._registry.record_use(cap_name, False, duration)
                raise

        # Find which plugin owns this capability
        for plugin in self._plugins.values():
            if cap_name in plugin.capabilities:
                # Handle external process / remote bridge dispatch via HTTP endpoint if available
                if plugin.execution_mode in ("external_process", "remote_bridge") or (
                    cap and cap.execution_mode in ("external_process", "remote_bridge")
                ):
                    impl = cap.implementation if cap else ""
                    endpoint = None
                    if impl.startswith("http://") or impl.startswith("https://"):
                        endpoint = impl
                    else:
                        proc_spec = plugin.manifest.get("process_spec", {})
                        endpoint = proc_spec.get("endpoint") or proc_spec.get("health_endpoint")

                    if endpoint and endpoint.startswith("http"):
                        # Forward request via HTTP POST
                        start = time.time()
                        try:
                            payload = {
                                "capability": cap_name,
                                "args": list(args),
                                "kwargs": kwargs,
                                "context": context.to_dict() if context else None,
                            }
                            req = urllib.request.Request(
                                endpoint,
                                data=json.dumps(payload).encode("utf-8"),
                                headers={"Content-Type": "application/json"},
                                method="POST",
                            )
                            with urllib.request.urlopen(req, timeout=10.0) as resp:
                                data = json.loads(resp.read().decode("utf-8"))
                                duration = (time.time() - start) * 1000
                                self._registry.record_use(cap_name, True, duration)
                                return data.get("result", data)
                        except Exception as e:
                            duration = (time.time() - start) * 1000
                            self._registry.record_use(cap_name, False, duration)
                            raise RuntimeError(f"External capability dispatch to {endpoint} failed: {e}") from e

                # In-process module function lookup
                impl = cap.implementation if cap else ""
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
                        call_kwargs = dict(kwargs)
                        if context is not None:
                            try:
                                sig = inspect.signature(func)
                                accepts_context = "context" in sig.parameters
                                accepts_varkw = any(
                                    p.kind == inspect.Parameter.VAR_KEYWORD
                                    for p in sig.parameters.values()
                                )
                                if accepts_context or accepts_varkw:
                                    call_kwargs["context"] = context
                            except (ValueError, TypeError):
                                pass
                        try:
                            result = func(*args, **call_kwargs)
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
