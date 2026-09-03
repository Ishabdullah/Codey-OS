"""
Category-G run provenance (docs/telemetry_layer_design.md §2.G, §3.4).

T0 scope note: this module builds the provenance *body* dict and the
model-digest *cache-read* path. Nothing in T0 calls it — no sub-task
before T2 emits a `run_start` record — so none of the subprocess/getprop/
git calls below run at import time or as a side effect of importing
`telemetry`. Every public function here is called lazily, by a future
call site.

Model hashing (fact 0.23: ~5.2s for the primary model) is deliberately
NOT performed synchronously anywhere in this module. `get_model_digest()`
only ever reads `model_digests.json`; if the cache is stale or missing it
returns `sha256=None, sha256_source="not_computed"` and leaves the actual
hashing to whichever later sub-task owns a background writer-thread
job (design §3.4). Computing a 5.2s hash inline here would make importing
or calling this module during T0's dead-code phase a footgun for whatever
sub-task wires it in first.
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from utils.config import (
    METRICS_DIR,
    TELEMETRY_ENV_ALLOW_LIST,
    TELEMETRY_SECRET_PRESENCE_ONLY_ENV,
)

GIT_TIMEOUT_S = 2.0
MODEL_DIGEST_CACHE_FILE = "model_digests.json"


def get_git_provenance(repo_dir: Optional[Path] = None) -> Dict[str, Any]:
    """
    Returns {commit_sha, dirty, dirty_file_count, branch}, each null +
    `git_command_unavailable` on any failure (git missing, not a repo,
    timeout, non-zero exit). Never raises.
    """
    cwd = str(repo_dir) if repo_dir is not None else None
    result: Dict[str, Any] = {
        "commit_sha": None,
        "dirty": None,
        "dirty_file_count": None,
        "branch": None,
    }
    try:
        sha = _run_git(["rev-parse", "HEAD"], cwd)
        result["commit_sha"] = sha or None
    except Exception:
        # git missing, not a repo, or timed out — an honest null, not a
        # reason to fail whatever is building the provenance record.
        pass
    try:
        porcelain = _run_git(["status", "--porcelain"], cwd)
        lines = [line for line in porcelain.splitlines() if line.strip()]
        result["dirty"] = len(lines) > 0
        result["dirty_file_count"] = len(lines)
    except Exception:
        pass
    try:
        branch = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd)
        result["branch"] = branch or None
    except Exception:
        pass
    return result


def _run_git(args: List[str], cwd: Optional[str]) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=GIT_TIMEOUT_S,
        check=True,
    )
    return proc.stdout.strip()


def get_device_provenance() -> Dict[str, Any]:
    """Best-effort device/runtime facts. Every field independently
    wrapped so one unreadable prop doesn't null out the rest."""
    info: Dict[str, Any] = {
        "device_model": None,
        "android_release": None,
        "android_sdk": None,
        "kernel_version": None,
        "termux_version": os.environ.get("TERMUX_VERSION") or None,
        "python_version": platform.python_version(),
        "node_version": None,
        "cpu_core_count": os.cpu_count(),
    }
    info["device_model"] = _getprop("ro.product.model")
    info["android_release"] = _getprop("ro.build.version.release")
    sdk_raw = _getprop("ro.build.version.sdk")
    if sdk_raw is not None:
        try:
            info["android_sdk"] = int(sdk_raw)
        except ValueError:
            info["android_sdk"] = None
    else:
        info["android_sdk"] = None
    try:
        info["kernel_version"] = os.uname().release
    except (AttributeError, OSError):
        # os.uname() is POSIX-only and can, in principle, fail — an
        # honest null rather than a crashed provenance record.
        info["kernel_version"] = None
    return info


def _getprop(name: str) -> Optional[str]:
    try:
        proc = subprocess.run(
            ["getprop", name],
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_S,
            check=True,
        )
        value = proc.stdout.strip()
        return value or None
    except Exception:
        # getprop not present (non-Android dev box) or the specific
        # property is unset — honest null, not a crash.
        return None


def get_ram_swap_bytes() -> Dict[str, Optional[int]]:
    """MemTotal / SwapTotal in bytes from /proc/meminfo, read
    independently of core/resource_gate.py's read_meminfo() (§1.1: this
    package imports nothing from core.resource_gate — see recorders.py's
    module docstring for the same reasoning applied there)."""
    result: Dict[str, Optional[int]] = {"ram_total_bytes": None, "swap_total_bytes": None}
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    result["ram_total_bytes"] = _kb_line_to_bytes(line)
                elif line.startswith("SwapTotal:"):
                    result["swap_total_bytes"] = _kb_line_to_bytes(line)
    except OSError:
        # /proc/meminfo unreadable — honest null (state_store_unreadable
        # class of failure), never raised.
        pass
    return result


def _kb_line_to_bytes(line: str) -> Optional[int]:
    parts = line.split()
    if len(parts) < 2:
        return None
    try:
        return int(parts[1]) * 1024
    except ValueError:
        return None


def build_env_overrides() -> Dict[str, Any]:
    """
    Allow-list-only projection of the environment (§2.G / §8 item 4). Only
    names in utils.config.TELEMETRY_ENV_ALLOW_LIST may appear as literal
    keys; secret-bearing names appear only as `{"<name>_set": bool}`. A
    wholesale os.environ dump never happens here or anywhere else in this
    module.
    """
    overrides: Dict[str, Any] = {}
    for name in TELEMETRY_ENV_ALLOW_LIST:
        if name in os.environ:
            overrides[name] = os.environ[name]
    for secret_name in TELEMETRY_SECRET_PRESENCE_ONLY_ENV:
        overrides[f"{secret_name.lower()}_set"] = secret_name in os.environ
    return overrides


def build_config_snapshot() -> Dict[str, Any]:
    """
    Explicit projection of the config constants actually in force
    (§2.G). Each constant is read defensively (getattr with a default)
    so a rename/removal in utils.config degrades one field to absent
    rather than breaking provenance collection entirely — this module has
    no compile-time dependency on utils.config's exact constant set
    beyond the telemetry-specific names it imports at the top.
    """
    import utils.config as _cfg  # local import: keeps the module-level

    snapshot: Dict[str, Any] = {"_policy": "v1"}
    for name in (
        "MODEL_CONFIG",
        "THERMAL_CONFIG",
        "MAX_CONCURRENT_MODEL_BUDGET_BYTES",
        "DISPATCH_MIN_HEADROOM_BYTES",
        "DEVICE_CEILING_USABLE_FRACTION",
        "REQUIRED_HEADROOM_FACTOR",
        "CONTEXT_BUDGET_SAFETY_MARGIN_FRACTION",
        "CONTEXT_QUEUE_POLL_INTERVAL_SECONDS",
    ):
        value = getattr(_cfg, name, None)
        if value is not None:
            snapshot[name] = value
    return snapshot


def get_model_digest(
    path: Path, cache_path: Optional[Path] = None
) -> Dict[str, Any]:
    """
    Cache-READ only (T0 scope — see module docstring). Keys on
    (size_bytes, mtime_ns) per design §3.4: if the file's current stat
    matches the cached entry, returns the cached digest with
    sha256_source="cached". On any mismatch, missing cache, or unreadable
    file, returns sha256=None, sha256_source="not_computed" — never
    computes the hash inline.
    """
    cache_file = cache_path or (METRICS_DIR / MODEL_DIGEST_CACHE_FILE)
    result: Dict[str, Any] = {
        "path": str(path),
        "size_bytes": None,
        "mtime_ns": None,
        "sha256": None,
        "sha256_source": "not_computed",
    }
    try:
        stat = path.stat()
        result["size_bytes"] = stat.st_size
        result["mtime_ns"] = stat.st_mtime_ns
    except OSError:
        # File doesn't exist / unreadable — return the not-computed shape
        # as-is; this is an honest null, not a crash.
        return result

    try:
        with open(cache_file, "r", encoding="utf-8") as f:
            cache: Dict[str, Any] = json.load(f)
    except (OSError, json.JSONDecodeError):
        # No cache yet, or the cache file is corrupt — treat as a cold
        # cache, not an error worth surfacing to the caller.
        return result

    entry = cache.get(str(path))
    if (
        isinstance(entry, dict)
        and entry.get("size_bytes") == result["size_bytes"]
        and entry.get("mtime_ns") == result["mtime_ns"]
        and entry.get("sha256")
    ):
        result["sha256"] = entry["sha256"]
        result["sha256_source"] = "cached"

    return result


def build_run_start_body(
    *,
    run_id: str,
    boot_id: Optional[str],
    emitter: str,
    pid: int,
    started_ts_wall: float,
    repo: str,
    repo_dir: Optional[Path] = None,
    models: Optional[List[Dict[str, Any]]] = None,
    llama_server_bin: Optional[str] = None,
    schema_version: int,
    schema_sha256: str,
) -> Dict[str, Any]:
    """
    Assembles the category-G `run_start` body (§2.G). Composition-only —
    no I/O beyond what get_git_provenance/get_device_provenance/
    get_ram_swap_bytes/build_env_overrides/build_config_snapshot already
    do individually, each independently failure-isolated.
    """
    git_info = get_git_provenance(repo_dir)
    device_info = get_device_provenance()
    mem_info = get_ram_swap_bytes()

    return {
        "run_id": run_id,
        "boot_id": boot_id,
        "emitter": emitter,
        "pid": pid,
        "started_ts_wall": started_ts_wall,
        "git_commit_sha": git_info["commit_sha"],
        "git_dirty": git_info["dirty"],
        "git_dirty_file_count": git_info["dirty_file_count"],
        "git_branch": git_info["branch"],
        "repo": repo,
        "device_model": device_info["device_model"],
        "android_release": device_info["android_release"],
        "android_sdk": device_info["android_sdk"],
        "kernel_version": device_info["kernel_version"],
        "termux_version": device_info["termux_version"],
        "python_version": device_info["python_version"],
        "node_version": device_info["node_version"],
        "ram_total_bytes": mem_info["ram_total_bytes"],
        "swap_total_bytes": mem_info["swap_total_bytes"],
        "cpu_core_count": device_info["cpu_core_count"],
        "device_uptime_sec": None,  # always null — fact 0.2, see recorders.py
        "models": models if models is not None else [],
        "llama_server_bin": llama_server_bin,
        "llama_build_info": None,  # backfilled by a later sub-task (§2.G)
        "llama_server_argv": None,  # populated by T9 (core/loader_v2.py)
        "env_overrides": build_env_overrides(),
        "config_snapshot": build_config_snapshot(),
        "schema_version": schema_version,
        "schema_sha256": schema_sha256,
    }


def build_run_start_nulls(body: Dict[str, Any]) -> Dict[str, str]:
    """
    Derives the honest-null `nulls` dict for a run_start body built by
    build_run_start_body(), mirroring recorders.record_device_sample's
    pattern: every field that came back None from a fallible collector
    gets a reason code so telemetry/recorders.py's _emit() keeps it in
    the record as a named null instead of silently pruning it.

    - git_commit_sha / git_dirty / git_dirty_file_count / git_branch:
      "git_command_unavailable" (git missing, not a repo, or the 2s
      timeout in get_git_provenance()) — schema-defined reason for
      exactly this case (telemetry/schema/v1.json's null_reason_codes).
    - ram_total_bytes / swap_total_bytes: "state_store_unreadable"
      (/proc/meminfo unreadable in get_ram_swap_bytes()).
    - device_uptime_sec: always "proc_uptime_permission_denied" — a
      permanent, device-wide null (fact 0.2), not a per-call failure,
      so it is set unconditionally rather than only when body[...] is
      None (it is always None in build_run_start_body()).
    """
    nulls: Dict[str, str] = {}
    for field in ("git_commit_sha", "git_dirty", "git_dirty_file_count", "git_branch"):
        if body.get(field) is None:
            nulls[f"body.{field}"] = "git_command_unavailable"
    for field in ("ram_total_bytes", "swap_total_bytes"):
        if body.get(field) is None:
            nulls[f"body.{field}"] = "state_store_unreadable"
    nulls["body.device_uptime_sec"] = "proc_uptime_permission_denied"
    return nulls
