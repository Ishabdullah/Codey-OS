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
import logging
import math
import hashlib
import os
import re
import shlex
import subprocess
import sys
import time
import unicodedata
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


def _audit_plugin_refusal(action: str, command: str, reason: str) -> None:
    """Write one HIGH_IMPACT `refused` gateway row for a security refusal.

    Rows are best effort by the gateway's own design (an audit sink OSError
    is swallowed there); the refusal itself never depends on the row.
    """
    try:
        get_action_gateway().refuse_exec(
            authority=HIGH_IMPACT, action=action, command=command, reason=reason,
        )
    except Exception as exc:
        # Safe: the refusal (placeholder / DISABLED / return False) is
        # enacted by the caller independent of this row. A failing audit
        # sink must not crash discovery or skip activation cleanup; the
        # gateway already treats rows as best effort (R7).
        # Leave a signal: action name and exception type only, never the
        # command text, reason or exception message.
        logging.getLogger(__name__).warning(
            "plugin refusal audit row failed: action=%s error=%s",
            action, type(exc).__name__)


def _plugin_child_env(process_spec: Dict[str, Any]) -> "tuple[Dict[str, str], str]":
    """Environment for an external plugin child, plus its policy label.

    Today the child inherits the parent's entire environment plus the
    manifest's `process_spec.env` overrides (policy "inherit-all"). This is
    the single seam where G15h/D-10 will substitute an allowlist; the audit
    row's `env_policy` reads the label returned here so it stays truthful.
    """
    env = dict(os.environ)
    if isinstance(process_spec.get("env"), dict):
        env.update(process_spec["env"])
    return env, "inherit-all"


_CRED_LIKE_ENV_RE = re.compile(r"(KEY|TOKEN|SECRET|PASS|CRED|AUTH|COOKIE)", re.IGNORECASE)


def _spawn_audit_command(plugin: "Plugin", cmd: Any, cwd: str,
                         env: Dict[str, str], env_policy: str,
                         process_spec: Dict[str, Any]) -> str:
    """One-line audit text for a plugin spawn attempt or pre-spawn refusal.

    Records argv (truncated at 512 chars, plus a hash of the full argv), cwd,
    manifest env-override NAMES, and the child-env NAMES that look
    credential-like (a heuristic, not a completeness claim). Environment
    values are never read into the row. `cmd` may be None when no argv could
    be resolved (missing entry).
    """
    if cmd is None:
        full = ""
        argv = "<unresolved>"
    else:
        if isinstance(cmd, (list, tuple)):
            full = shlex.join(str(a) for a in cmd)
        else:
            full = str(cmd)
        argv = full[:512]
    digest = hashlib.sha256(full.encode("utf-8", "replace")).hexdigest()[:16]
    overrides = process_spec.get("env")
    override_names = sorted(str(k) for k in overrides) if isinstance(overrides, dict) else []
    cred_names = sorted(str(k) for k in env if _CRED_LIKE_ENV_RE.search(str(k)))[:20]
    return (
        f"plugin={plugin.name} mode={plugin.execution_mode} cwd={cwd} "
        f"argv={argv} argv_sha256={digest} env_policy={env_policy} "
        f"env_override_keys={json.dumps(override_names)} "
        f"cred_like_env_names={json.dumps(cred_names)}"
    )


def _audit_spawn_refusal(plugin_name: str, command: str, reason: str) -> None:
    """Write one ACT `refused` row for a spawn that was not attempted.

    Best effort like `_audit_plugin_refusal`: the refusal (status/return
    False) is enacted by the caller regardless of whether the row lands.
    """
    try:
        get_action_gateway().refuse_exec(
            authority=ACT, action=f"ccos.plugin_spawn:{plugin_name}",
            command=command, reason=reason,
        )
    except Exception as exc:
        # Safe: the caller already refuses the spawn; a failing audit sink
        # must not turn a refusal into a crash. Log type only, never text.
        logging.getLogger(__name__).warning(
            "plugin spawn refusal audit row failed: plugin=%s error=%s",
            plugin_name, type(exc).__name__)


def _capability_name(definition: Dict[str, Any], plugin_name: str) -> Any:
    """The one derivation of a capability's registered name (staging and
    discovery both call this so the collision check cannot drift from what
    activation registers)."""
    return definition.get("name", f"{plugin_name}.{definition.get('id', 'unknown')}")


def _declared_capability_names(manifest: Dict[str, Any], plugin_name: str) -> List[str]:
    """Non-empty string capability names a normalized manifest declares.

    Malformed shapes are ignored here; staging still rejects them before any
    executable effect.
    """
    caps = manifest.get("capabilities", []) if isinstance(manifest, dict) else []
    if not isinstance(caps, list):
        return []
    names = []
    for definition in caps:
        if isinstance(definition, dict):
            name = _capability_name(definition, plugin_name)
            if isinstance(name, str) and name:
                names.append(name)
    return names


# Default_Ignorable / blank code points outside Cf/Mn (Unicode
# DerivedCoreProperties): Hangul fillers, halfwidth filler, braille blank,
# Mongolian vowel separator. Cf (ZW*, BOM, soft hyphen, bidi, tag chars) and
# Mn/Me (combining marks, variation selectors, U+034F) are dropped by category.
_BLANK_LETTERS = frozenset(
    (0x115F, 0x1160, 0x3164, 0xFFA0, 0x2800, 0x180E, 0x17B4, 0x17B5))


def _plugin_name_key(name: str) -> str:
    """Duplicate-detection key: NFKC + drop Unicode format/control chars
    (Cf/Cc/Mn/Me: ZWSP/ZWJ/ZWNJ, BOM, soft hyphen, bidi, tags, controls,
    combining marks, variation selectors, plus _BLANK_LETTERS; real plugin
    names are ASCII slugs, so stripping marks cannot merge legit names)
    + strip + casefold, so `Agent`, `agent `, full-width and zero-width
    variants cannot impersonate one another.

    ACCEPTED RESIDUAL (S2-B, Ish 2026-10-24): cross-script homoglyphs (a
    Cyrillic `a` in `agent`) are not NFKC-equivalent and still yield a
    distinct key; closing that needs a confusables table, out of scope.
    """
    # NFKD first so precomposed letters (g + U+0301 -> U+01F5) are split
    # and their marks stripped before recomposition.
    text = unicodedata.normalize("NFKD", name)
    text = "".join(
        c for c in text
        if unicodedata.category(c) not in ("Cf", "Cc", "Mn", "Me")
        and ord(c) not in _BLANK_LETTERS)
    return unicodedata.normalize("NFKC", text).strip().casefold()


# S2-B (M25b): the canonical plugin tree. A capability name classified in
# CAPABILITY_AUTHORITY is bound to this tree; a plugin discovered under any
# other plugin_dir may not claim it (see PluginManager._discover).
_CANONICAL_PLUGIN_ROOT = os.path.realpath(Path(__file__).resolve().parent.parent / "plugins")


def _scan_canonical_capability_names() -> frozenset:
    """Every capability name declared by a canonical manifest under
    ccos/plugins, derived with the same helpers discovery/staging use, unioned
    with the CAPABILITY_AUTHORITY names. Fails closed to the table alone
    (logged) if the canonical tree cannot be read, never to an empty set."""
    names = set(CAPABILITY_AUTHORITY)
    try:
        root = Path(_CANONICAL_PLUGIN_ROOT)
        manifests = sorted(root.glob("*/*/manifest.json"))
        if not manifests:
            raise OSError("no canonical manifests found")
        for mf in manifests:
            try:
                manifest = normalize_manifest(json.loads(mf.read_text()))
                pname = manifest.get("name", mf.parent.name)
                if isinstance(pname, str):
                    names.update(_declared_capability_names(manifest, pname))
            except Exception:
                continue  # malformed manifest: discovery skips it too
    except Exception as exc:
        logging.getLogger(__name__).warning(
            "canonical capability scan failed (%s); binding only the "
            "CAPABILITY_AUTHORITY names", type(exc).__name__)
    return frozenset(names)


# Import-time snapshot: later mutation of the CAPABILITY_AUTHORITY dict (e.g.
# a test or plugin adding a synthetic name) cannot widen or shrink the set.
_CANONICAL_CAPABILITY_NAMES = _scan_canonical_capability_names()


def _is_canonical_root(root_real: str) -> bool:
    try:
        return os.path.commonpath([_CANONICAL_PLUGIN_ROOT, root_real]) == _CANONICAL_PLUGIN_ROOT
    except ValueError:
        return False


def _authority_relaxing_args(args: tuple, kwargs: Dict[str, Any]) -> List[str]:
    """Arguments refused by the public keyword-data contract (S2-B, M26).

    Refuse every positional tail argument: its target parameter name is
    unknown here, so it could bind to a permission or consent override.
    Also refuse yolo truthy, confirm_* other than None/True, shell_fn,
    or any callable supplied by keyword.
    """
    # Key-name matching is exact-lowercase on purpose: any future plugin that
    # reads case-variant or nested config knobs needs a re-audit of this list.
    found = [f"args[{i}]" for i in range(len(args))]
    for key, value in kwargs.items():
        k = str(key).lower()
        if (callable(value) or (k == "shell_fn" and value is not None)
                or (k == "yolo" and value)
                or (k.startswith("confirm") and value is not None and value is not True)):
            found.append(str(key))
    return found


def _manifest_enabled_refusal(manifest: Dict[str, Any]) -> Optional[str]:
    """Static fail-closed enabled policy, including legacy/direct callers."""
    enabled = manifest.get("enabled", True)
    if type(enabled) is not bool:
        return "Invalid manifest enabled field: expected boolean"
    if not enabled:
        return "Plugin disabled by manifest (enabled=false)"
    return None


class PluginContainmentError(ValueError):
    """A manifest path escapes the plugin's own directory (or is malformed)."""


def resolve_plugin_file(plugin_dir, relative) -> Path:
    """Resolve manifest path `relative` inside `plugin_dir`, or refuse.

    Both sides are resolved (realpath) so symlinks and the /data/data vs
    /data/user/0 alias cannot cause a false accept or refusal; containment
    is judged with commonpath, never a string prefix. Absolute values are
    refused even when they point inside the directory. The returned
    resolved path (which need not exist) is what callers must execute --
    never the raw manifest string.
    """
    if not isinstance(relative, str) or not relative or "\x00" in relative:
        raise PluginContainmentError("malformed path")
    if os.path.isabs(relative):
        raise PluginContainmentError("absolute path")
    try:
        base = os.path.realpath(os.fspath(plugin_dir))
        real = os.path.realpath(os.path.join(base, relative))
        inside = os.path.commonpath([base, real]) == base
        try:
            os.stat(real)
        except FileNotFoundError:
            pass  # a missing entry is judged by containment alone
        except NotADirectoryError:
            pass  # a path under a regular file is likewise just absent
    except (OSError, RuntimeError, ValueError, TypeError) as exc:
        raise PluginContainmentError("unresolvable path") from exc
    if not inside or real == base:
        raise PluginContainmentError("path escapes plugin directory")
    return Path(real)


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
            reason = _manifest_enabled_refusal(plugin.manifest)
            if reason:
                # Do not inspect/stop an existing owner or touch PID files.
                _audit_plugin_refusal(
                    f"ccos.plugin_spawn:{plugin.name}", plugin.name, reason)
                return False
            process_spec = plugin.manifest.get("process_spec", {})
            cmd = process_spec.get("start_command") or process_spec.get("command")
            cwd = str(process_spec.get("working_dir") or plugin.path)
            env, env_policy = _plugin_child_env(process_spec)
            owned = self._processes.get(plugin.name)
            if owned is not None:
                try:
                    alive = owned.poll() is None
                except Exception:
                    # Unknown liveness cannot authorize a duplicate child.
                    _audit_spawn_refusal(
                        plugin.name,
                        _spawn_audit_command(plugin, cmd or None, cwd, env, env_policy, process_spec),
                        "Owned process liveness unreadable; spawn not attempted",
                    )
                    return False
                if alive:
                    plugin.pid = owned.pid
                    return plugin.name in self._ready
                if not self.stop_external_plugin(plugin.name):
                    _audit_spawn_refusal(
                        plugin.name,
                        _spawn_audit_command(plugin, cmd or None, cwd, env, env_policy, process_spec),
                        "Dead owned process could not be stopped; spawn not attempted",
                    )
                    return False
                plugin.pid = None

            if not cmd:
                entry_point = plugin.manifest.get("entry_point", "__init__.py")
                try:
                    entry_file = resolve_plugin_file(plugin.path, entry_point)
                except PluginContainmentError:
                    # Defense in depth for direct supervisor callers: the
                    # manager refuses an escaping entry_point before it gets
                    # here, but the spawn re-checks and executes only the
                    # resolved path.
                    plugin.status = PluginStatus.DISABLED
                    plugin.error = "entry_point escapes plugin directory"
                    _audit_plugin_refusal(
                        f"ccos.plugin_spawn:{plugin.name}",
                        f"plugin={plugin.name} entry_point={entry_point!r}"[:200],
                        "entry_point escapes plugin directory",
                    )
                    return False
                if not entry_file.is_file():
                    plugin.status = PluginStatus.BROKEN
                    plugin.error = "No start_command or entry_point found for external process"
                    _audit_spawn_refusal(
                        plugin.name,
                        _spawn_audit_command(plugin, None, cwd, env, env_policy, process_spec),
                        plugin.error,
                    )
                    return False
                cmd = [sys.executable, str(entry_file)]
            audit_command = _spawn_audit_command(
                plugin, cmd, cwd, env, env_policy, process_spec)
            pid_file = process_spec.get("pid_file")
            pid_path = _resolve_pid_path(pid_file) if pid_file else None
            # An integer file from another supervisor/session is evidence,
            # never permission to signal it or start a duplicate alongside it.
            if pid_path is not None and os.path.lexists(pid_path):
                plugin.status = PluginStatus.BROKEN
                plugin.error = "Unowned PID record blocks external process startup"
                _audit_spawn_refusal(plugin.name, audit_command, plugin.error)
                return False

            def _spawn():
                # Handle ownership is recorded inside the thunk, atomically
                # with the child's existence: if the gateway raises after
                # this returns (non-OSError audit failure), the cleanup in
                # the except below still finds and stops our child.
                proc = subprocess.Popen(
                    cmd, cwd=cwd, env=env,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                )
                self._processes[plugin.name] = proc
                plugin.pid = proc.pid
                return proc

            try:
                decision = get_action_gateway().gate_exec(
                    authority=ACT, action=f"ccos.plugin_spawn:{plugin.name}",
                    command=audit_command, confirm_available=False,
                    execute=_spawn,
                )
                if decision.outcome != OUTCOME_ALLOWED:
                    # Popen failed (FAILED) or the gateway refused: no
                    # handle was stored; the shared except path below sets
                    # the same BROKEN status/message as before.
                    raise RuntimeError(decision.reason)
                proc = decision.detail["result"]
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
        self._disabled_capabilities: Dict[str, str] = {}
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
        """Observe policy changes without racing activation or dispatch."""
        with self._lifecycle_lock:
            return self._discover_locked()

    def _discover_locked(self):
        """Scan plugin directories and register plugins, refusing ambiguity.

        Walk is sorted (deterministic). Symlinked category dirs, plugin dirs
        and manifest.json are refused outright. A plugin name (NFKC/casefold
        key, across ALL plugin_dirs) or a capability name claimed by more
        than one manifest is refused for every claimant: each becomes a
        DISABLED placeholder, so directory order can never pick a winner.
        A placeholder never replaces an ACTIVE or mid-activation plugin.
        """
        self._discovery_refusals = []
        self._disabled_capabilities = {}

        def refuse(rel, reason, action_name):
            self._discovery_refusals.append({"path": rel, "reason": reason})
            _audit_plugin_refusal(f"ccos.plugin_discover:{action_name}", rel, reason)

        claims = []  # (name, abs_path_str, rel_path, manifest)
        noncanonical = set()  # claim indexes found outside the canonical tree
        seen_roots = set()
        seen_plugin_dirs = set()
        for plugin_dir in self._plugin_dirs:
            plugin_path = Path(plugin_dir)
            if not plugin_path.exists():
                continue
            root_real = os.path.realpath(plugin_path)
            if root_real in seen_roots:
                continue  # same root listed twice / via alias: keep the first
            seen_roots.add(root_real)

            def inside(child, parent):
                try:
                    return os.path.commonpath([parent, os.path.realpath(child)]) == parent
                except (OSError, ValueError):
                    return False

            for category_dir in sorted(plugin_path.iterdir()):
                if category_dir.name.startswith("_"):
                    continue
                if category_dir.is_symlink():
                    if category_dir.is_dir():
                        refuse(category_dir.name, "symlinked category directory", category_dir.name)
                    continue
                if not category_dir.is_dir() or not inside(category_dir, root_real) \
                        or os.path.realpath(category_dir) == root_real:
                    continue
                for plugin_subdir in sorted(category_dir.iterdir()):
                    if plugin_subdir.name.startswith("_"):
                        continue
                    rel = f"{category_dir.name}/{plugin_subdir.name}"
                    if plugin_subdir.is_symlink():
                        if plugin_subdir.is_dir():
                            refuse(rel, "symlinked plugin directory", plugin_subdir.name)
                        continue
                    if not plugin_subdir.is_dir():
                        continue
                    if not inside(plugin_subdir, root_real):
                        refuse(rel, "plugin directory resolves outside plugin root", plugin_subdir.name)
                        continue
                    manifest_path = plugin_subdir / "manifest.json"
                    if manifest_path.is_symlink():
                        refuse(rel + "/manifest.json", "symlinked manifest.json", plugin_subdir.name)
                        continue
                    if not manifest_path.exists():
                        continue
                    if not inside(manifest_path, os.path.realpath(plugin_subdir)):
                        refuse(rel + "/manifest.json", "manifest.json resolves outside plugin directory",
                               plugin_subdir.name)
                        continue
                    real_dir = os.path.realpath(plugin_subdir)
                    if real_dir in seen_plugin_dirs:
                        # Defense in depth: with distinct realpath roots and
                        # symlinked category/plugin dirs refused, no filesystem
                        # layout reaches one plugin dir from two roots, so this
                        # guard is not independently testable.
                        continue  # overlapping roots reaching one dir: not a rival claim
                    try:
                        raw_manifest = json.loads(manifest_path.read_text())
                        manifest = normalize_manifest(raw_manifest)
                        name = manifest.get("name", plugin_subdir.name)
                    except Exception:
                        continue  # skip malformed manifests
                    seen_plugin_dirs.add(real_dir)
                    if not isinstance(name, str) or not name.strip():
                        # Untrusted/unusable name: no sensible registry key,
                        # so refuse with an audit row and no placeholder.
                        refuse(rel, "manifest name is not a non-blank string", plugin_subdir.name)
                        continue
                    claims.append((name, str(plugin_subdir), rel, manifest))
                    if not _is_canonical_root(root_real):
                        noncanonical.add(len(claims) - 1)

        # Refusing ALL claimants of a contested name/capability is a
        # deliberate fail-closed trade-off: a planted same-name or
        # same-capability directory also disables the legitimate plugin
        # (denial of service). Accepted because planting requires write
        # access to the plugin tree, which already allows corrupting the
        # genuine plugin; the alternative (a winner by order) is hijack.
        refused = {}  # claim index -> reason
        by_key = {}
        for idx, (name, _path, _rel, _m) in enumerate(claims):
            by_key.setdefault(_plugin_name_key(name), []).append(idx)
        for idxs in by_key.values():
            if len(idxs) > 1:
                rels = sorted(claims[i][2] for i in idxs)
                for i in idxs:
                    refused[i] = f"refused: plugin name claimed by {len(idxs)} manifests: {rels}"
        # S2-B (M25b): names classified in CAPABILITY_AUTHORITY (== every
        # canonical manifest capability, per the coverage test) belong to the
        # canonical tree; a plugin from another plugin_dir may not claim one,
        # even when the canonical plugin is not in this manager's dirs.
        for idx in sorted(noncanonical):
            if idx in refused:
                continue
            name, _path, _rel, manifest = claims[idx]
            bound = sorted(c for c in set(_declared_capability_names(manifest, name))
                           if c in _CANONICAL_CAPABILITY_NAMES)
            if bound:
                refused[idx] = ("refused: capability name(s) %r are bound to the canonical "
                                "plugin tree; plugin is outside it" % bound)
        by_cap = {}
        for idx, (name, _path, _rel, manifest) in enumerate(claims):
            if idx in refused:
                continue
            for cap_name in set(_declared_capability_names(manifest, name)):
                by_cap.setdefault(cap_name, []).append(idx)
        for cap_name, idxs in sorted(by_cap.items()):
            if len(idxs) > 1:
                owners = sorted(claims[i][0] for i in idxs)
                for i in idxs:
                    refused.setdefault(
                        i, f"refused: capability {cap_name!r} declared by {owners}")

        logged = set()
        for idx, (name, path, rel, manifest) in enumerate(claims):
            policy_reason = _manifest_enabled_refusal(manifest)
            existing = self._plugins.get(name)
            live = existing is not None and (
                existing.status == PluginStatus.ACTIVE or name in self._activation_attempts)
            if policy_reason:
                # Keep reservations even for collision placeholders and stale
                # registry entries. Disabled declarations still participate in
                # all name/capability conflict checks above.
                for cap_name in _declared_capability_names(manifest, name):
                    self._disabled_capabilities[cap_name] = policy_reason
                if live:
                    # Preserve ownership/process_spec and the exact Plugin
                    # object. Block new work; explicit unload still owns cleanup.
                    existing.manifest["enabled"] = manifest["enabled"]
                    existing.error = policy_reason
            if idx in refused:
                if (name, refused[idx]) not in logged:
                    logged.add((name, refused[idx]))
                    refuse(rel, refused[idx], name)
                existing = self._plugins.get(name)
                if existing is not None and (
                    existing.status == PluginStatus.ACTIVE or name in self._activation_attempts
                ):
                    continue  # a live lifecycle is never rewritten
                self._plugins[name] = Plugin(
                    name=name, path=path, manifest={},
                    status=PluginStatus.DISABLED, error=refused[idx],
                )
                continue
            if live and _manifest_enabled_refusal(existing.manifest):
                # Re-enabling an observed-disabled live owner requires explicit
                # unload/restart, never replacement of its lifecycle record.
                continue
            if policy_reason and type(manifest["enabled"]) is not bool:
                refuse(rel, policy_reason, name)
            # enabled:false is an installed policy, not an attempted action.
            # Explicit load/start/dispatch refusals are audited at those gates.
            self._plugins[name] = Plugin(
                name=name,
                path=path,
                manifest=manifest,
                status=PluginStatus.DISABLED if policy_reason else PluginStatus.INSTALLED,
                error=policy_reason or "",
                capabilities=_declared_capability_names(manifest, name) if policy_reason else [],
                version=manifest.get("version", "1.0.0"),
                domain=manifest.get("domain", "general"),
                execution_mode=manifest.get("execution_mode", "in_process"),
                permissions=manifest.get("permissions", []),
                resource_limits=manifest.get("resource_limits", {}),
            )

    def list_plugins(self) -> List[Dict[str, Any]]:
        """List all discovered plugins."""
        return [
            {
                "name": p.name,
                "path": p.path,
                "status": p.status.value,
                "enabled": p.manifest.get("enabled", True),
                "version": p.version,
                "execution_mode": p.execution_mode,
                "capabilities": p.capabilities,
                "error": _manifest_enabled_refusal(p.manifest) or p.error,
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

        reason = _manifest_enabled_refusal(plugin.manifest)
        if reason:
            _audit_plugin_refusal(f"ccos.plugin_activate:{name}", name, reason)
            return False
        if plugin.status == PluginStatus.DISABLED:
            return False  # refused plugins are never retried in-process

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

        # Containment, checked once here (before any executable effect) and
        # again right before use below. An escaping value refuses the load
        # for every execution mode and never falls back to __init__.py.
        try:
            resolve_plugin_file(plugin.path, plugin.manifest.get("entry_point", "__init__.py"))
            resolve_plugin_file(plugin.path, "__init__.py")
        except PluginContainmentError:
            self._refuse_containment(plugin)
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
                # Use-time recheck: the resolved path is what gets executed.
                entry_real = resolve_plugin_file(
                    plugin.path, plugin.manifest.get("entry_point", "__init__.py"))
                init_real = resolve_plugin_file(plugin.path, "__init__.py")
                module_file = entry_real if entry_real.is_file() else init_real
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
            if plugin.status != PluginStatus.DISABLED:
                # DISABLED set by the supervisor's containment refusal is kept.
                plugin.status = PluginStatus.BROKEN
                plugin.error = attempt["failure_error"]
            if isinstance(exc, PluginContainmentError):
                # Use-time recheck refused: disable, never retry.
                plugin.status = PluginStatus.DISABLED
                plugin.error = "entry_point escapes plugin directory"
                _audit_plugin_refusal(
                    f"ccos.plugin_activate:{name}", f"plugin={name}", plugin.error)
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

    def _refuse_containment(self, plugin: Plugin) -> None:
        """Disable a plugin whose entry_point escapes its directory and
        write the refusal row (no raw manifest text in the stored error)."""
        plugin.status = PluginStatus.DISABLED
        plugin.error = "entry_point escapes plugin directory"
        _audit_plugin_refusal(
            f"ccos.plugin_activate:{plugin.name}", f"plugin={plugin.name}", plugin.error)

    def _stage_capabilities(self, plugin: Plugin) -> List[Capability]:
        """Validate only activation-consumed shapes, before executable effects."""
        manifest = plugin.manifest
        if not isinstance(manifest, dict):
            raise ValueError("manifest")
        if _manifest_enabled_refusal(manifest):
            raise ValueError("manifest enabled policy refuses activation")
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
            cap_name = _capability_name(definition, plugin.name)
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
        plugin = self._plugins.get(name)
        reason = _manifest_enabled_refusal(plugin.manifest) if plugin is not None else None
        if reason:
            decision = get_action_gateway().refuse_exec(
                authority=HIGH_IMPACT, action=f"ccos.plugin_execute:{name}",
                command=name, reason=reason)
            raise CapabilityRefused(decision.reason)
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
        """Keep activation state, authority and execution in one lifecycle epoch.

        Capability data must be supplied by keyword. Every positional tail
        argument is refused and audited before dispatch, as are authority-
        relaxing keywords (yolo, confirm_*=False, shell_fn, any callable).
        In-repo code that deliberately supplies positional arguments or
        relaxes authority uses call_capability_trusted().
        """
        with self._lifecycle_lock:
            return self._call_capability(
                cap_name, *args, context=context, _trusted=False, **kwargs)

    def call_capability_trusted(
        self,
        cap_name: str,
        *args,
        context: Optional[TaskContext] = None,
        **kwargs,
    ) -> Any:
        """call_capability() for in-repo callers that deliberately set the
        relaxed daemon/CLI profile in code (core/task_executor.py, main.py).
        Retains positional argument support. Never route model-, plan- or
        user-data-supplied args or kwargs through this.
        """
        with self._lifecycle_lock:
            return self._call_capability(
                cap_name, *args, context=context, _trusted=True, **kwargs)

    def _call_capability(
        self,
        cap_name: str,
        *args,
        context: Optional[TaskContext] = None,
        _trusted: bool = False,
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
        gateway = get_action_gateway()
        action_label = f"ccos.call_capability:{cap_name}"
        reason = self._disabled_capabilities.get(cap_name)
        for plugin in self._plugins.values():
            policy_reason = _manifest_enabled_refusal(plugin.manifest)
            if policy_reason and (cap_name in plugin.capabilities or cap_name in
                                  _declared_capability_names(plugin.manifest, plugin.name)):
                reason = policy_reason
                break
        if reason:
            decision = gateway.refuse_exec(
                authority=HIGH_IMPACT, action=action_label, command=cap_name, reason=reason)
            raise CapabilityRefused(decision.reason)
        if not cap and cap_name not in self._handlers:
            raise RuntimeError(f"Capability '{cap_name}' not found")
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
        if not _trusted:
            relaxing = _authority_relaxing_args(args, kwargs)
            if relaxing:
                decision = gateway.refuse_exec(
                    authority=HIGH_IMPACT, action=action_label, command=cap_name,
                    reason=("caller-supplied authority-relaxing argument(s) %s refused "
                            "on a mediated capability call" % sorted(relaxing)),
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
            "refused": list(self._discovery_refusals),
        }


# Singleton
_manager: Optional[PluginManager] = None


def get_plugin_manager() -> PluginManager:
    global _manager
    if _manager is None:
        _manager = PluginManager()
    return _manager
