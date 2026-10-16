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
import math
import os
import subprocess
import sys
import time
from threading import RLock
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
from ccos.core.sandbox import MAX_TIMEOUT as _SANDBOX_MAX_TIMEOUT
from ccos.core.task_context import TaskContext
from core.action_gateway import (
    ACT,
    AUTHORITY_CLASSES,
    HIGH_IMPACT,
    OUTCOME_ALLOWED,
    OUTCOME_FAILED,
    READ,
    get_action_gateway,
)
from utils.config import CODEY_STATE_DIR

# WP2.1 group 4 (NEW-910/911/912). Rank used to resolve the "raise-only
# floor" rule below -- a manifest permission tag or a handler-supplied
# authority can only move a capability's effective authority UP this
# ranking, never down.
_AUTHORITY_RANK = {READ: 0, ACT: 1, HIGH_IMPACT: 2}

# Manifest `permissions` tags that force HIGH_IMPACT regardless of what
# CAPABILITY_AUTHORITY says for that capability name -- device actuation,
# privileged device control, private-filesystem access, and audio
# recording are all treated as inherently high-impact even if a future
# capability under one of these tags is never individually added to the
# core table below. Matched by exact tag string. This can only RAISE a
# classification (see _authority_for), never lower one set by the core
# table.
_MANIFEST_RAISE_TAGS: Dict[str, str] = {
    "device:telephony": HIGH_IMPACT,
    "device:control": HIGH_IMPACT,
    "device:write": HIGH_IMPACT,
    "fs:private": HIGH_IMPACT,
    "audio:record": HIGH_IMPACT,
}

# Core-owned capability-name -> authority (READ/ACT/HIGH_IMPACT) table,
# consulted at the top of call_capability() (WP2.1 group 4, NEW-910/911/
# 912). Built by reading each capability's actual implementation, not
# guessed -- see ccos/plugins/*/*/manifest.json + their .py modules.
# Coverage for every literal call_capability() argument in core/, tools/,
# main.py, restoricon_core/, plus core/agent.py's _CRM_QUERY_CAPABILITIES
# dict values is enforced by an AST-derived test
# (tests/test_ccos_capability_authority_coverage.py) rather than trusted
# by inspection -- a hand-typed list is exactly the drift class
# core/agent.py's own _CRM_QUERY_CAPABILITIES comment warns about
# (NEW-750).
#
# Any capability name NOT in this table (and not covered by a manifest
# raise-tag or an explicit handler authority, see _authority_for) is
# refused at dispatch -- fail-closed default, not fail-open.
CAPABILITY_AUTHORITY: Dict[str, str] = {
    # coding/agent (ccos/plugins/coding/agent/manifest.json). run_agent's
    # own internal shell/write safety is already handled inside
    # core/agent.py's own gating (confirm_shell/confirm_write, the shell
    # classifier) -- this just adds an outer audit trail at the CCOS
    # dispatch boundary. run_recursive is pure draft/critique/refine LLM
    # inference (core/recursive.py) with no file/shell side effects, so
    # it is treated like a pure computation rather than a mutation.
    # classify_breadth is a pure text classifier.
    "coding.run_agent": ACT,
    "coding.run_recursive": READ,
    "coding.classify_breadth": READ,

    # crm/core_query (ccos/plugins/crm/core_query/manifest.json) -- the
    # twelve read-only CRM/sales query capabilities confirmed read-only
    # via client.py; also the only names core/agent.py's tool_crm_query()
    # whitelist (_CRM_QUERY_CAPABILITIES) is ever allowed to dispatch to.
    "crm.count_open_leads": READ,
    "crm.list_leads": READ,
    "crm.get_lead": READ,
    "crm.list_opportunities": READ,
    "crm.get_opportunity": READ,
    "crm.get_pipeline_summary": READ,
    "crm.list_customers": READ,
    "crm.get_customer": READ,
    "crm.list_tasks": READ,
    "crm.list_properties": READ,
    "crm.list_estimates": READ,
    "crm.list_communications": READ,

    # system/thermal_monitor (ccos/plugins/system/thermal_monitor/
    # manifest.json + thermal_monitor.py). monitor_snapshot/
    # monitor_render_text/thermal_status/thermal_is_throttled/
    # thermal_current_threads are pure getters; thermal_start_inference/
    # thermal_end_inference/thermal_reset each call a `-> None` mutator
    # in core/thermal.py.
    "system.monitor_snapshot": READ,
    "system.monitor_render_text": READ,
    "system.thermal_status": READ,
    "system.thermal_is_throttled": READ,
    "system.thermal_current_threads": READ,
    "system.thermal_start_inference": ACT,
    "system.thermal_end_inference": ACT,
    "system.thermal_reset": ACT,

    # system/observability (ccos/plugins/system/observability/
    # manifest.json + observability.py). Every property except
    # reset_state is a read-only computed value per that module's own
    # docstring; reset_state drops the process-wide State singleton
    # (a `-> None` mutation).
    "system.observability_tokens_used": READ,
    "system.observability_memory_loaded": READ,
    "system.observability_tasks_pending": READ,
    "system.observability_tasks_running": READ,
    "system.observability_model_active": READ,
    "system.observability_model_state": READ,
    "system.observability_temperature": READ,
    "system.observability_context_size": READ,
    "system.observability_memory_usage": READ,
    "system.observability_cpu_usage": READ,
    "system.observability_uptime": READ,
    "system.observability_daemon_pid": READ,
    "system.observability_health": READ,
    "system.observability_full_status": READ,
    "system.observability_reset_state": ACT,

    # system/system_info (ccos/plugins/system/system_info/manifest.json +
    # system_info.py) -- real registered capabilities exercised by
    # ccos/tests/test_improvement_loop.py's real (non-mocked)
    # PluginManager dispatch. Not in this round's required AST-coverage
    # scope (core/, tools/, main.py, restoricon_core/) but classified
    # anyway, disclosed beyond that list, because leaving them
    # unclassified would fail-closed-refuse a pre-existing passing test
    # for a capability that reads system info only (confirmed via its
    # implementation: platform/*proc* reads and a `ps aux` listing, no
    # mutation).
    "system.info": READ,
    "system.processes": READ,
}


class CapabilityRefused(RuntimeError):
    """Raised when call_capability() refuses to dispatch a capability.

    Covers both the fail-closed "no authority classification" default
    and an ordinary HIGH_IMPACT-with-no-confirmation-path refusal.
    Distinguishable in logs/except clauses from the pre-existing
    "Capability '...' not found" RuntimeError (unregistered capability
    name) raised earlier in call_capability() -- that case means nothing
    with this name exists at all; this one means something exists but
    dispatch was not permitted.
    """


def _max_authority(authorities: List[str]) -> str:
    """Highest-ranked authority among `authorities` (see _AUTHORITY_RANK)."""
    return max(authorities, key=lambda a: _AUTHORITY_RANK[a])


# WP2.1 group 5 (dormant remote_bridge/external_process HTTP dispatch
# timeout enforcement). Mirrors group 4's raise-only-floor pattern,
# inverted: there a manifest tag could only RAISE authority above the
# core floor, never lower it; here _DISPATCH_TIMEOUT_CEILING is a
# core-owned ceiling a manifest/capability can only request something
# TIGHTER than, never looser. Reuses ccos.core.sandbox's existing
# MAX_TIMEOUT constant rather than duplicating the number -- sandbox.py
# has no imports back into this module or capability_registry/
# manifest_schema_v2, so this import carries no circular-import risk.
_DISPATCH_TIMEOUT_CEILING = _SANDBOX_MAX_TIMEOUT
_DEFAULT_DISPATCH_TIMEOUT = 10.0


def _merge_capability_resource_limits(
    cap_def: Dict[str, Any], plugin_manifest: Dict[str, Any]
) -> Dict[str, Any]:
    """Build the `resource_limits` dict for a `Capability` constructed from
    `cap_def`, folding in the capability's own `timeout_seconds` override.

    normalize_manifest() (manifest_schema_v2.py) places a per-capability
    `timeout_seconds` as a *sibling* key directly on each capability dict
    (defaulted to 0 when absent) -- it is never nested under that same
    capability's `resource_limits`. Reading `cap.resource_limits` alone
    therefore only ever sees the plugin-level `resource_limits` dict
    (or a capability-level one if a manifest author wrote one by hand);
    a per-capability `timeout_seconds` override is silently dropped
    unless folded in here. A falsy cap-level value (0 or absent) does not
    shadow a real plugin-level default.
    """
    limits = dict(cap_def.get("resource_limits", plugin_manifest.get("resource_limits", {})))
    cap_timeout = cap_def.get("timeout_seconds")
    if cap_timeout:
        limits["timeout_seconds"] = cap_timeout
    return limits

# NEW-278: manifests may specify a bare/relative `pid_file` (e.g.
# "aigentik.pid"). Resolve those against the runtime state dir, not the
# plugin's source directory in the repo — matches the convention
# lib/service_manager.sh already uses (its PID files all live under
# $DAEMON_DIR, i.e. CODEY_STATE_DIR). A dedicated "plugins" subdirectory
# is used rather than CODEY_STATE_DIR directly because some plugin names
# (e.g. "aigentik") collide with a filename service_manager.sh's shell
# service already owns directly under CODEY_STATE_DIR
# (AIGENTIK_PID_FILE="$DAEMON_DIR/aigentik.pid") — that shell service and
# this plugin's external_process both start conceptually-named "aigentik"
# processes but are independent supervisors, so sharing one PID file path
# would let either one signal a PID the other spawned (a Rule 3
# violation). Namespacing under "plugins/" keeps the two writers apart
# while still keeping plugin PID files out of the source tree.
PLUGIN_PID_DIR = CODEY_STATE_DIR / "plugins"


def _resolve_pid_path(pid_file_str: Union[str, Path]) -> Path:
    """Resolve a manifest `process_spec.pid_file` value.

    Absolute values are used as-is. Relative values are resolved against
    PLUGIN_PID_DIR (the runtime state dir), never against the plugin's
    source directory — see NEW-278.
    """
    pid_path = Path(pid_file_str)
    if not pid_path.is_absolute():
        pid_path = PLUGIN_PID_DIR / pid_path
    return pid_path


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
    """Own Popen children until confirmed exit; PID files confer no ownership."""

    _STARTUP_OBSERVE_SECONDS = 0.1

    def __init__(self):
        self._processes: Dict[str, subprocess.Popen] = {}
        self._pid_files: Dict[str, Path] = {}
        self._pid_records = {}
        self._ready = set()
        # start may invoke stop after failed setup. Reentrancy keeps that
        # cleanup serialized without giving concurrent starts a second child.
        self._lock = RLock()

    @staticmethod
    def _record_signature(stat):
        return (stat.st_dev, stat.st_ino, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size)

    def _publish_pid(self, name, path, proc):
        path.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive create rejects existing files and symlinks, including a
        # record another supervisor published after our pre-spawn check.
        with path.open("xb") as stream:
            self._pid_files[name] = path
            payload = str(proc.pid).encode("ascii")
            stream.write(payload)
            stream.flush()
            self._pid_records[name] = (self._record_signature(os.fstat(stream.fileno())), payload)

    def _remove_owned_record(self, name):
        path = self._pid_files.get(name)
        snapshot = self._pid_records.get(name)
        if path is None or snapshot is None:
            return
        try:
            # O_NOFOLLOW rejects a symlink replacement. Compare both the
            # opened inode and current directory entry immediately before
            # unlinking; this is a local stale-record defense, not pidfd or
            # an account-adversary-proof atomic compare-and-unlink primitive.
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd, "rb") as stream:
                opened = self._record_signature(os.fstat(stream.fileno()))
                if opened != snapshot[0]:
                    return
                data = stream.read(len(snapshot[1]) + 1)
                current = self._record_signature(path.lstat())
            if opened == current == snapshot[0] and data == snapshot[1]:
                path.unlink()
        except OSError:
            # Record replacement or cleanup failure cannot make an exited
            # child live again; preserve the evidence rather than deleting
            # an entry we cannot verify as our unchanged publication.
            return

    def start_external_plugin(
        self, plugin: Plugin, state_dir: Optional[Path] = None
    ) -> bool:
        """Start one owned child and observe early exit / configured health."""
        with self._lock:
            owned = self._processes.get(plugin.name)
            if owned is not None:
                try:
                    alive = owned.poll() is None
                except Exception:
                    # Unknown liveness cannot authorize a duplicate child.
                    return False
                if alive:
                    plugin.pid = owned.pid
                    return plugin.name in self._ready
                if not self.stop_external_plugin(plugin.name):
                    return False
                plugin.pid = None

            process_spec = plugin.manifest.get("process_spec", {})
            cmd = process_spec.get("start_command") or process_spec.get("command")
            if not cmd:
                entry_file = Path(plugin.path) / plugin.manifest.get("entry_point", "__init__.py")
                if not entry_file.exists():
                    plugin.status = PluginStatus.BROKEN
                    plugin.error = "No start_command or entry_point found for external process"
                    return False
                cmd = [sys.executable, str(entry_file)]
            pid_file = process_spec.get("pid_file")
            pid_path = _resolve_pid_path(pid_file) if pid_file else None
            # An integer file from another supervisor/session is evidence,
            # never permission to signal it or start a duplicate alongside it.
            if pid_path is not None and os.path.lexists(pid_path):
                plugin.status = PluginStatus.BROKEN
                plugin.error = "Unowned PID record blocks external process startup"
                return False
            env = dict(os.environ)
            if isinstance(process_spec.get("env"), dict):
                env.update(process_spec["env"])
            try:
                proc = subprocess.Popen(
                    cmd, cwd=str(process_spec.get("working_dir") or plugin.path),
                    env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                )
                self._processes[plugin.name] = proc
                plugin.pid = proc.pid
                if pid_path is not None:
                    self._publish_pid(plugin.name, pid_path, proc)
                try:
                    proc.wait(timeout=self._STARTUP_OBSERVE_SECONDS)
                except subprocess.TimeoutExpired:
                    pass  # Expected: the bounded startup observation is over.
                else:
                    raise RuntimeError("External process exited during startup")
                if not self.check_health(plugin.name, process_spec.get("health_endpoint")):
                    raise RuntimeError("External process startup health check failed")
                self._ready.add(plugin.name)
                plugin.error = ""
                return True
            except Exception:
                # Setup may fail after Popen. Cleanup only our retained handle;
                # if cleanup is incomplete, keep it for a later stop attempt.
                self._ready.discard(plugin.name)
                if plugin.name in self._processes:
                    stopped = self.stop_external_plugin(plugin.name)
                    if stopped:
                        plugin.pid = None
                plugin.status = PluginStatus.BROKEN
                plugin.error = "External process startup failed"
                return False

    def stop_external_plugin(
        self, plugin_name: str, pid_file: Optional[Union[str, Path]] = None,
        timeout: float = 3.0,
    ) -> bool:
        """Stop/reap only an owned Popen; retain all tracking on uncertainty."""
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout < 0:
            return False
        with self._lock:
            proc = self._processes.get(plugin_name)
            if proc is None:
                path = _resolve_pid_path(pid_file) if pid_file else self._pid_files.get(plugin_name)
                return path is None or not os.path.lexists(path)
            try:
                if proc.poll() is None:
                    try:
                        proc.terminate()
                    except ProcessLookupError:
                        pass  # Still require wait/poll to confirm our child exited.
                    try:
                        proc.wait(timeout=timeout)
                    except subprocess.TimeoutExpired:
                        # Poll again before escalation; it may have exited at
                        # the timeout boundary. Signal only the Popen handle.
                        if proc.poll() is None:
                            proc.kill()
                        proc.wait(timeout=timeout)
                else:
                    proc.wait(timeout=timeout)  # reap an already exited child
                if proc.poll() is None:
                    return False
            except Exception:
                # Permission errors, failed waits and unconfirmed termination
                # do not authorize dropping the only owned process handle.
                return False
            self._remove_owned_record(plugin_name)
            self._processes.pop(plugin_name, None)
            self._pid_files.pop(plugin_name, None)
            self._pid_records.pop(plugin_name, None)
            self._ready.discard(plugin_name)
            for stream in (proc.stdout, proc.stderr):
                if stream is not None:
                    try:
                        stream.close()
                    except Exception:
                        pass  # Child is reaped; a pipe-close error is not liveness.
            return True

    def check_health(self, plugin_name: str, health_endpoint: Optional[str] = None) -> bool:
        """Require an owned live child, plus optional bounded HTTP readiness."""
        with self._lock:
            proc = self._processes.get(plugin_name)
            if proc is None or proc.poll() is not None:
                return False
            if health_endpoint:
                try:
                    req = urllib.request.Request(health_endpoint, headers={"User-Agent": "Codey-OS-PluginSupervisor"})
                    with urllib.request.urlopen(req, timeout=1.5) as response:
                        healthy = response.status < 400
                    return healthy and proc.poll() is None
                except Exception:
                    return False
            return proc.poll() is None


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
        self._handler_authority: Dict[str, str] = {}
        self.supervisor = ProcessSupervisor()
        self._lifecycle_lock = RLock()
        self._external_health_failures = set()
        self._activation_attempts = {}
        self._discover()

    def register_capability_handler(self, cap_name: str, handler: Callable, *, authority: str):
        """Register an in-memory direct handler for a capability.

        `authority` (one of READ/ACT/HIGH_IMPACT, see core.action_gateway)
        is required and keyword-only, with no default -- a defaulted
        kwarg acting as a safety boundary is exactly NEW-763's already-
        logged `allow_dangerous` defect class. Effective authority for
        `cap_name` is max(core-table-if-present, this value): a handler
        registration can only raise the classification CAPABILITY_AUTHORITY
        already assigns that name, never shadow it downward (see
        _authority_for).
        """
        if authority not in AUTHORITY_CLASSES:
            raise ValueError(f"Unknown authority class: {authority!r}")
        self._handlers[cap_name] = handler
        self._handler_authority[cap_name] = authority

    def _resolve_dispatch_timeout(self, cap: Optional[Capability], plugin: Plugin) -> float:
        """Resolve the `urlopen()` timeout for an external_process/
        remote_bridge HTTP dispatch call (WP2.1 group 5).

        Precedence: the capability's own `resource_limits.timeout_seconds`
        (folded in by `_merge_capability_resource_limits()` at load() time,
        so a per-capability override already wins over the plugin-level
        value there) > the plugin's `resource_limits.timeout_seconds` >
        `_DEFAULT_DISPATCH_TIMEOUT`. A candidate is only used if it is a
        real positive number -- 0 is "unset" (not "no timeout";
        `urlopen(timeout=0)` is a non-blocking socket that fails near-
        instantly), and a negative, NaN, non-numeric, or bool value is
        treated the same as unset rather than raising or being passed
        through, since `_discover()` never runs manifests through
        `validate_manifest_v2()` -- a malformed value must fall back to
        the default, not blow up before `call_capability()`'s fail-closed
        authority gate even gets a chance to refuse/audit the call. The
        chosen value is clamped to `_DISPATCH_TIMEOUT_CEILING`: a
        manifest/capability may only request something TIGHTER than the
        core ceiling, never looser.
        """

        def _is_valid(value: Any) -> bool:
            return (
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and value == value  # excludes NaN
                and value > 0
            )

        for raw in (
            cap.resource_limits.get("timeout_seconds") if cap is not None else None,
            plugin.resource_limits.get("timeout_seconds"),
        ):
            if _is_valid(raw):
                return min(float(raw), float(_DISPATCH_TIMEOUT_CEILING))
        return _DEFAULT_DISPATCH_TIMEOUT

    def _authority_for(self, cap_name: str, cap: Optional[Capability]) -> Optional[str]:
        """Classify cap_name's effective dispatch authority, or None if
        unclassified (the fail-closed default then applies in
        call_capability()).

        The core table (CAPABILITY_AUTHORITY) is the floor. Two sources
        can only RAISE it, never lower it: a registry-backed capability's
        manifest `permissions` tags (_MANIFEST_RAISE_TAGS) -- checked
        whenever `cap` is not None, including for a name that is also
        handler-registered -- and, for a handler-registered name, the
        authority supplied to register_capability_handler(). This means a
        test-registered handler can never shadow a core classification
        downward, and a handler-only capability (cap is None, the
        _handlers-dict path with zero production callers) still gets a
        real classification from its required registration argument.
        """
        candidates: List[str] = []

        base = CAPABILITY_AUTHORITY.get(cap_name)
        if base is not None:
            candidates.append(base)

        if cap is not None:
            for tag in cap.permissions:
                raised = _MANIFEST_RAISE_TAGS.get(tag)
                if raised is not None:
                    candidates.append(raised)

        handler_authority = self._handler_authority.get(cap_name)
        if handler_authority is not None:
            candidates.append(handler_authority)

        if not candidates:
            return None
        return _max_authority(candidates)

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
        """Serialize startup and capability registration for one manager."""
        with self._lifecycle_lock:
            return self._load(name)

    def _load(self, name: str) -> bool:
        """Import/start and register capabilities while lifecycle lock is held."""
        plugin = self._plugins.get(name)
        if not plugin:
            return False

        if plugin.status == PluginStatus.ACTIVE:
            if plugin.execution_mode in ("external_process", "isolated_daemon", "remote_bridge"):
                if self.supervisor.check_health(
                    name, plugin.manifest.get("process_spec", {}).get("health_endpoint"),
                ):
                    return True
                # This load attempt explicitly observed failed readiness. Do
                # not keep advertising capabilities as active, and retain the
                # owned child until a later unload/retry confirms its exit.
                plugin.status = PluginStatus.BROKEN
                plugin.error = "External process health check failed"
                self._external_health_failures.add(name)
                for cap_name in plugin.capabilities:
                    capability = self._registry.get(cap_name)
                    if capability is not None:
                        capability.status = CapabilityStatus.BROKEN
                        self._registry.register(capability)
                return False
            return True

        if name in self._external_health_failures:
            # A retry of this explicit health failure must resolve the prior
            # lifecycle first. Failed stop preserves child, broken capability
            # state and this retry marker; no second child is started.
            if not self._unload(name):
                return False

        if name in self._activation_attempts:
            if not self._cleanup_activation(plugin):
                return False

        try:
            staged = self._stage_capabilities(plugin)
        except Exception:
            plugin.status = PluginStatus.BROKEN
            plugin.error = "Invalid activation capability or manifest fields"
            return False

        module_key = f"ccos_plugin_{name}"
        attempt = {
            "staged": {cap.name: cap for cap in staged},
            "previous": {cap.name: self._registry.get(cap.name) for cap in staged},
            "touched": [], "external": plugin.execution_mode in (
                "external_process", "isolated_daemon", "remote_bridge"),
            "spawn_attempted": False, "failure_error": "Plugin activation failed",
            "module_key": module_key, "module": None,
            "sys_previous": sys.modules.get(module_key),
            "manager_previous": self._modules.get(name),
        }
        self._activation_attempts[name] = attempt
        try:
            if attempt["external"]:
                # Record before calling: startup itself can fail/interrupt
                # after Popen, with an owned child still in the supervisor.
                attempt["failure_error"] = "External plugin activation startup failed"
                attempt["spawn_attempted"] = True
                if not self.supervisor.start_external_plugin(plugin):
                    raise RuntimeError("External startup failed")
            else:
                attempt["failure_error"] = "Plugin activation module setup failed"
                plugin_path = Path(plugin.path)
                entry_path = plugin_path / plugin.manifest.get("entry_point", "__init__.py")
                module_file = entry_path if entry_path.exists() else plugin_path / "__init__.py"
                spec = importlib.util.spec_from_file_location(module_key, str(module_file))
                if spec is None or spec.loader is None:
                    raise RuntimeError("Could not create module spec")
                module = importlib.util.module_from_spec(spec)
                attempt["module"] = module
                sys.modules[module_key] = module
                spec.loader.exec_module(module)
                self._modules[name] = module

            attempt["failure_error"] = "Plugin activation capability registration failed"
            for capability in staged:
                # Include the current registration before invoking the API:
                # a registry implementation may mutate and then raise.
                attempt["touched"].append(capability.name)
                if self._registry.register(capability) is not True:
                    raise RuntimeError("Capability registration failed")
            plugin.capabilities = [cap.name for cap in staged]
            plugin.status = PluginStatus.ACTIVE
            plugin.error = ""
            del self._activation_attempts[name]
            return True
        except BaseException as exc:
            plugin.status = PluginStatus.BROKEN
            plugin.error = attempt["failure_error"]
            try:
                self._cleanup_activation(plugin)
            except BaseException:
                # The attempt remains recorded and dispatch-blocked even if
                # cleanup itself is interrupted. Preserve the original signal.
                if isinstance(exc, Exception):
                    raise
            if not isinstance(exc, Exception):
                raise
            return False

    def _stage_capabilities(self, plugin: Plugin) -> List[Capability]:
        """Validate only activation-consumed shapes, before executable effects."""
        manifest = plugin.manifest
        if not isinstance(manifest, dict):
            raise ValueError("manifest")
        for key in ("entry_point", "domain", "category"):
            if key in manifest and not isinstance(manifest[key], str):
                raise ValueError(key)
        for key in ("resource_limits", "process_spec"):
            if key in manifest and not isinstance(manifest[key], dict):
                raise ValueError(key)
        if "permissions" in manifest and not self._string_list(manifest["permissions"]):
            raise ValueError("permissions")
        process_spec = manifest.get("process_spec", {})
        for key in ("command", "start_command"):
            if key in process_spec and not self._string_list(process_spec[key]):
                raise ValueError(key)
        for key in ("pid_file", "working_dir", "endpoint", "health_endpoint"):
            if process_spec.get(key) is not None and not isinstance(process_spec[key], str):
                raise ValueError(key)
        if "env" in process_spec and (
            not isinstance(process_spec["env"], dict)
            or not all(isinstance(key, str) and isinstance(value, str)
                       for key, value in process_spec["env"].items())
        ):
            raise ValueError("process environment")
        caps = manifest.get("capabilities", [])
        if not isinstance(caps, list):
            raise ValueError("capabilities")
        staged = []
        names = set()
        for definition in caps:
            if not isinstance(definition, dict):
                raise ValueError("capability")
            for key in ("name", "id", "description", "implementation", "category", "test", "execution_mode"):
                if key in definition and not isinstance(definition[key], str):
                    raise ValueError(key)
            for key in ("dependencies", "hardware_requirements", "permissions"):
                if key in definition and not self._string_list(definition[key]):
                    raise ValueError(key)
            for key in ("resource_limits", "inputs_schema", "outputs_schema"):
                if key in definition and not isinstance(definition[key], dict):
                    raise ValueError(key)
            cap_name = definition.get("name", f"{plugin.name}.{definition.get('id', 'unknown')}")
            if not cap_name or cap_name in names:
                raise ValueError("duplicate or empty capability name")
            names.add(cap_name)
            staged.append(Capability(
                name=cap_name, description=definition.get("description", ""),
                implementation=definition.get("implementation", plugin.path),
                category=definition.get("category", manifest.get("domain", manifest.get("category", "general"))),
                dependencies=definition.get("dependencies", []),
                hardware_requirements=definition.get("hardware_requirements", []),
                test_path=definition.get("test", ""), status=CapabilityStatus.ACTIVE,
                version=plugin.version, execution_mode=definition.get("execution_mode", plugin.execution_mode),
                resource_limits=_merge_capability_resource_limits(definition, manifest),
                permissions=definition.get("permissions", manifest.get("permissions", [])),
                inputs_schema=definition.get("inputs_schema", {}),
                outputs_schema=definition.get("outputs_schema", {}),
            ))
        return staged

    @staticmethod
    def _string_list(value):
        return isinstance(value, list) and all(isinstance(item, str) for item in value)

    def _cleanup_activation(self, plugin: Plugin) -> bool:
        """Retry exact attempt cleanup; API failures retain dispatch-blocked debt.

        Registry._save swallows I/O errors: this is in-memory bookkeeping,
        not a durable registry transaction. Import side effects are not undone.
        """
        attempt = self._activation_attempts[plugin.name]
        clean = True
        if attempt["spawn_attempted"]:
            try:
                pid_file = plugin.manifest.get("process_spec", {}).get("pid_file")
                pid_file = str(_resolve_pid_path(pid_file)) if pid_file else None
                if self.supervisor.stop_external_plugin(plugin.name, pid_file=pid_file) is not True:
                    clean = False
                else:
                    plugin.pid = None
                    attempt["spawn_attempted"] = False
            except Exception:
                clean = False  # Retain supervisor ownership and retry marker.
        for cap_name in list(attempt["touched"]):
            try:
                previous = attempt["previous"][cap_name]
                current = self._registry.get(cap_name)
                if current is previous:
                    pass  # Original entry (including absence) already restored.
                elif current is attempt["staged"][cap_name] or current is None:
                    if previous is None:
                        result = self._registry.unregister(cap_name)
                        if result is not True and self._registry.get(cap_name) is not None:
                            raise RuntimeError("Capability removal failed")
                    elif self._registry.register(previous) is not True:
                        raise RuntimeError("Capability restoration failed")
                    if self._registry.get(cap_name) is not previous:
                        raise RuntimeError("Capability restoration not observed")
                else:
                    # Someone replaced this name independently. Do not erase it
                    # or claim that we restored the original snapshot.
                    raise RuntimeError("Capability changed during cleanup")
                attempt["touched"].remove(cap_name)
            except Exception:
                clean = False
        module = attempt["module"]
        if module is not None:
            for mapping, key, previous in (
                (sys.modules, attempt["module_key"], attempt["sys_previous"]),
                (self._modules, plugin.name, attempt["manager_previous"]),
            ):
                if mapping.get(key) is module:
                    if previous is None:
                        mapping.pop(key, None)
                    else:
                        mapping[key] = previous
        if clean:
            del self._activation_attempts[plugin.name]
        else:
            plugin.error = attempt["failure_error"] + "; cleanup pending"
        return clean

    def unload(self, name: str) -> bool:
        """Preserve plugin/capability state until external stop is confirmed."""
        with self._lifecycle_lock:
            return self._unload(name)

    def _unload(self, name: str) -> bool:
        """Stop and unregister while lifecycle lock is held."""
        plugin = self._plugins.get(name)
        if not plugin:
            return False

        if name in self._activation_attempts:
            if not self._cleanup_activation(plugin):
                return False
            plugin.status = PluginStatus.INSTALLED
            plugin.error = ""
            self._external_health_failures.discard(name)
            return True

        # Stop external process if applicable
        if plugin.execution_mode in ("external_process", "isolated_daemon", "remote_bridge"):
            pid_file = plugin.manifest.get("process_spec", {}).get("pid_file")
            # Resolve relative manifest values the same way start_external_plugin
            # does (NEW-278) — otherwise a relative pid_file here would fall
            # through to stop_external_plugin's own Path(pid_file), which
            # resolves it against the current working directory instead, and
            # the file start_external_plugin actually wrote would never be
            # found or unlinked.
            if pid_file:
                pid_file = str(_resolve_pid_path(pid_file))
            if not self.supervisor.stop_external_plugin(name, pid_file=pid_file):
                return False
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
        self._external_health_failures.discard(name)
        return True

    def execute(self, name: str, function: str, *args, **kwargs) -> Any:
        """Execute a loaded module function in a consistent lifecycle epoch."""
        with self._lifecycle_lock:
            return self._execute(name, function, *args, **kwargs)

    def _execute(self, name: str, function: str, *args, **kwargs) -> Any:
        """Caller holds lifecycle lock through guard, lookup and callback."""
        if name in self._activation_attempts:
            raise RuntimeError("Plugin activation incomplete; execution unavailable")
        module = self._modules.get(name)
        if not module:
            raise RuntimeError(f"Plugin '{name}' not loaded")

        func = getattr(module, function, None)
        if not func:
            raise AttributeError(f"Plugin '{name}' has no function '{function}'")

        return func(*args, **kwargs)

    def _build_call_kwargs(
        self, func: Callable, kwargs: Dict[str, Any], context: Optional[TaskContext]
    ) -> Dict[str, Any]:
        """Inject `context` into kwargs when `func` accepts it (by name or **kwargs)."""
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
        return call_kwargs

    def call_capability(
        self,
        cap_name: str,
        *args,
        context: Optional[TaskContext] = None,
        **kwargs,
    ) -> Any:
        """Keep activation state, authority and execution in one lifecycle epoch."""
        with self._lifecycle_lock:
            return self._call_capability(cap_name, *args, context=context, **kwargs)

    def _call_capability(
        self,
        cap_name: str,
        *args,
        context: Optional[TaskContext] = None,
        **kwargs,
    ) -> Any:
        """
        Execute a capability by its registered name.
        Supports in-process functions, direct handlers, and external process HTTP/IPC dispatch.

        WP2.1 group 4 (NEW-910/911/912): every dispatch path below is
        mediated through core.action_gateway's gate_exec()/refuse_exec(),
        the same mechanism already used for shell/peer-delegate gating.
        This is the first authority classification + audit trail at this
        single, production-reachable dispatch point. A capability with no
        classification (see _authority_for) is refused, not allowed
        through -- fail-closed default. HIGH_IMPACT capabilities always
        fail closed this round: no confirmation path exists yet for CCOS
        dispatch (confirm_available=False unconditionally below).
        """
        cap = self._registry.get(cap_name)
        if not cap and cap_name not in self._handlers:
            raise RuntimeError(f"Capability '{cap_name}' not found")

        gateway = get_action_gateway()
        action_label = f"ccos.call_capability:{cap_name}"
        # Only capabilities owned by an unfinished activation are blocked.
        # Restored/preexisting entries and independent direct handlers retain
        # their prior contract. Keep this refusal in the existing audit path.
        if any(attempt["staged"].get(cap_name) is cap and cap is not None
               for attempt in tuple(self._activation_attempts.values())):
            decision = gateway.refuse_exec(
                authority=HIGH_IMPACT, action=action_label, command=cap_name,
                reason="plugin activation incomplete; capability unavailable",
            )
            raise CapabilityRefused(decision.reason)
        authority = self._authority_for(cap_name, cap)

        if authority is None:
            decision = gateway.refuse_exec(
                authority=HIGH_IMPACT,
                action=action_label,
                command=cap_name,
                reason=(
                    "capability has no authority classification; refusing "
                    "per fail-closed default"
                ),
            )
            raise CapabilityRefused(decision.reason)

        # HIGH_IMPACT fails closed unconditionally this round -- no
        # confirmation path exists yet for CCOS dispatch (see module-level
        # docs above). READ/ACT are unaffected by this value.
        confirm_available = False

        # Direct/mock handler registered
        if cap_name in self._handlers:
            func = self._handlers[cap_name]
            call_kwargs = self._build_call_kwargs(func, kwargs, context)
            exc_holder: List[BaseException] = []

            def _execute() -> Any:
                try:
                    return func(*args, **call_kwargs)
                except Exception as e:
                    exc_holder.append(e)
                    raise

            start = time.time()
            decision = gateway.gate_exec(
                authority=authority,
                action=action_label,
                command=cap_name,
                confirm_available=confirm_available,
                execute=_execute,
            )
            duration = (time.time() - start) * 1000
            if decision.outcome == OUTCOME_ALLOWED:
                self._registry.record_use(cap_name, True, duration)
                return decision.detail["result"]
            if decision.outcome == OUTCOME_FAILED:
                self._registry.record_use(cap_name, False, duration)
                if exc_holder:
                    raise exc_holder[0]
                raise RuntimeError(decision.reason)
            # OUTCOME_REFUSED (HIGH_IMPACT, no confirmation path): nothing
            # was attempted -- do not record_use, it would corrupt
            # success_rate and erase the refused-vs-failed distinction the
            # gateway exists to preserve.
            raise CapabilityRefused(decision.reason)

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
                        exc_holder = []

                        def _execute() -> Any:
                            try:
                                # Resolved inside the gated execute() callback,
                                # not before gate_exec() runs: a malformed
                                # manifest value must never raise ahead of
                                # the fail-closed authority refusal/audit
                                # trail above, and (though
                                # _resolve_dispatch_timeout() itself never
                                # raises) this keeps the HIGH_IMPACT-refused
                                # case from doing this work at all.
                                dispatch_timeout = self._resolve_dispatch_timeout(cap, plugin)
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
                                with urllib.request.urlopen(req, timeout=dispatch_timeout) as resp:
                                    data = json.loads(resp.read().decode("utf-8"))
                                    return data.get("result", data)
                            except Exception as e:
                                wrapped = RuntimeError(
                                    f"External capability dispatch to {endpoint} failed: {e}"
                                )
                                wrapped.__cause__ = e
                                exc_holder.append(wrapped)
                                raise wrapped from e

                        start = time.time()
                        decision = gateway.gate_exec(
                            authority=authority,
                            action=action_label,
                            command=cap_name,
                            confirm_available=confirm_available,
                            execute=_execute,
                        )
                        duration = (time.time() - start) * 1000
                        if decision.outcome == OUTCOME_ALLOWED:
                            self._registry.record_use(cap_name, True, duration)
                            return decision.detail["result"]
                        if decision.outcome == OUTCOME_FAILED:
                            self._registry.record_use(cap_name, False, duration)
                            if exc_holder:
                                raise exc_holder[0]
                            raise RuntimeError(decision.reason)
                        raise CapabilityRefused(decision.reason)

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
                        call_kwargs = self._build_call_kwargs(func, kwargs, context)
                        exc_holder = []

                        def _execute() -> Any:
                            try:
                                return func(*args, **call_kwargs)
                            except Exception as e:
                                exc_holder.append(e)
                                raise

                        start = time.time()
                        decision = gateway.gate_exec(
                            authority=authority,
                            action=action_label,
                            command=cap_name,
                            confirm_available=confirm_available,
                            execute=_execute,
                        )
                        duration = (time.time() - start) * 1000
                        if decision.outcome == OUTCOME_ALLOWED:
                            self._registry.record_use(cap_name, True, duration)
                            return decision.detail["result"]
                        if decision.outcome == OUTCOME_FAILED:
                            self._registry.record_use(cap_name, False, duration)
                            if exc_holder:
                                raise exc_holder[0]
                            raise RuntimeError(decision.reason)
                        raise CapabilityRefused(decision.reason)

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
