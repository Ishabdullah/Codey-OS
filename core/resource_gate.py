#!/usr/bin/env python3
"""
Resource gate — Track 3 Phase 5a / CODEY_OS_MASTER_VISION.md Section 7.4
(2026-08-08 amendment), sub-task 1 of 5.

This module is the "single authority" for model-load admission decisions
described in 7.4, built as a standalone, unit-testable component. It is
NOT wired into `core/daemon.py`, `core/loader_v2.py`, `core/planner_loader.py`,
or `main.py` yet — that migration is sub-tasks 2-5, each gated behind its own
code-reviewer pass (CLAUDE.md rule 4) because it touches process-lifecycle
code. This module has no process-lifecycle risk on its own: importing it
starts nothing, spawns nothing, and reads only `/proc/meminfo` (mockable)
and thermal state (lazily imported, best-effort).

Per the amendment, this gate does NOT enforce a fixed concurrency ceiling
("max N models" / "never both X and Y resident"). It answers two questions:

  1. "Can model X be admitted right now?" — computed from a per-load cost
     estimate (declared model size + n_ctx-driven KV cache size) weighed
     against live, conservatively-defined headroom — not a bare
     headroom-minus-margin check (see NEW-21 in NEW_ISSUES.md, used as this
     module's regression-test case in tests/test_resource_gate.py).
  2. "Given N resident models and C cores, what's a reasonable per-model
     thread allocation?" — the gate owns CPU thread/core allocation as a
     second axis, not a separate mechanism (see `allocate_threads()`).

One admission check is absolute regardless of what else is resident: a
single model that alone exceeds the device's usable physical-RAM ceiling is
never admitted (`compute_device_ceiling_bytes()` / GateDecision.hard_reject).

Residency state (which models are currently resident, and their declared
cost) is stored in a small file-backed store so it can be read/written
across processes (daemon + separate `main.py` CLI invocations), matching
this project's existing convention for cross-process coordination:
`core/loader_v2.py`'s `llama-server-{port}.lock` flock pattern. Unlike that
lock file (which is always empty), this store holds JSON payload, so its
lock file is a *separate*, always-empty sibling file — flock'ing the
payload file itself would require truncating it before the lock is even
held, which is unsafe for a file that holds data (see `_locked_state()`).

Nothing in this module is wired into a live process yet; sub-tasks 2-5
migrate `core/daemon.py`/`core/loader_v2.py`/`core/planner_loader.py`/
`main.py` onto it.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from utils.config import CODEY_STATE_DIR, MODEL_PATH, PLANNER_MODEL_PATH
from utils.logger import warning

# ── Signal source 1: live system RAM/swap headroom, via /proc/meminfo ───────
# device_manager's scan is cached/one-time (not a live signal, per 7.4's
# scoping-correction note), and observability.py's memory figure is
# per-process RSS, not system-wide headroom — neither is usable here. Reading
# /proc/meminfo directly is the standard, dependency-free way to get a live
# system-wide figure, and is implemented as its own function precisely so
# tests can supply a synthetic file instead of depending on the real device
# (per NEW-21's regression case).

_KB = 1024


def read_meminfo(path: str = "/proc/meminfo") -> Dict[str, int]:
    """
    Parse /proc/meminfo into a dict of {field_name: value_in_bytes}.

    Only the fields this module actually uses are guaranteed present in the
    return value (defaulting to 0 if absent from the source so callers don't
    need to guard every lookup): MemTotal, MemFree, MemAvailable, Buffers,
    Cached, SwapTotal, SwapFree. Any other /proc/meminfo field found in the
    file is passed through too (also in bytes), for callers that want it.

    Raises OSError/FileNotFoundError if `path` doesn't exist or isn't
    readable — callers that want "unknown, treat as no live signal" instead
    of a raised exception should catch that explicitly (see
    `can_admit()`'s docstring for how the gate itself handles this).
    """
    result: Dict[str, int] = {}
    with open(path, "r") as f:
        for line in f:
            if ":" not in line:
                continue
            key, _, rest = line.partition(":")
            rest = rest.strip()
            parts = rest.split()
            if not parts:
                continue
            try:
                value_kb = int(parts[0])
            except ValueError:
                continue
            result[key.strip()] = value_kb * _KB

    for required in ("MemTotal", "MemFree", "MemAvailable", "Buffers", "Cached", "SwapTotal", "SwapFree"):
        result.setdefault(required, 0)
    return result


# Conservative multiplier applied to a model's estimated cost before
# comparing it against headroom (see `can_admit()`). This is the mechanism
# the 2026-08-08 amendment asks for explicitly: "the budget computation
# itself needs to stay conservative in practice even though the ceiling is
# no longer a fixed model count." MemAvailable is the kernel's own estimate
# of reclaimable memory, and is a legitimate, standard signal — but it's an
# estimate, not a guarantee: a model load can grow anonymous/mmap'd memory
# fast enough that reclaim (freeing cache, paging out) can't keep up in
# real time, which is consistent with NEW-21's observation (swap climbing
# 1.2Gi -> 5.6Gi in ~10 seconds, i.e. a rate problem, not just a size
# problem). Requiring cost * this factor <= headroom, instead of cost <=
# headroom, is this module's answer to that: pad the *estimate*
# conservatively rather than change what "headroom" means. A first
# attempt at this module used MemFree instead of MemAvailable specifically
# to route around this same concern — that was reverted (advisor review)
# because MemFree is near-zero on a healthy, idle Linux/Termux system by
# design (page cache absorbs it), which made the gate reject every load
# unconditionally, including on an otherwise-idle device with plenty of
# real headroom. See tests/test_resource_gate.py's
# test_primary_model_admitted_under_idle_conditions for the regression
# case that first design broke.
#
# 1.25 is a first, un-calibrated default — reasoned about from NEW-21's
# rate-of-swap-growth observation, not derived from a controlled set of
# real on-device load measurements. Sub-task 3 (migrating core/daemon.py's
# call sites onto this gate, per TODO.md's 7.4 entry) is the point where
# this should be validated/retuned against actual observed load behavior,
# not treated as a settled value from this sub-task's synthetic fixtures.
REQUIRED_HEADROOM_FACTOR = 1.25


def compute_headroom_bytes(meminfo: Dict[str, int], reserved_bytes: int = 0) -> int:
    """
    Compute the "available to spend on a new model load" headroom, in bytes,
    from the kernel's own MemAvailable figure (standard signal for "how much
    could a new allocation actually get without swapping heavily," already
    accounting for reclaimable cache/buffers correctly — unlike a raw
    MemFree-based figure, which is near-zero on a healthy system by design).

    The defense against NEW-21-style over-approval is NOT in this function —
    it's `REQUIRED_HEADROOM_FACTOR`, applied to the model's cost estimate in
    `can_admit()`, not by discounting headroom here. Keeping the discount on
    the estimate side (not the headroom side) keeps this function's meaning
    literal and testable on its own.

    `reserved_bytes` lets a caller subtract the declared cost of other
    slots that are concurrently being admitted/loaded but haven't yet shown
    up in a fresh /proc/meminfo read (e.g. two racing admission checks in
    the cross-process case) — see `total_reserved_bytes()`.
    """
    available = meminfo.get("MemAvailable", 0)
    return max(0, available - max(0, reserved_bytes))


# Fraction of MemTotal a single model may ever claim under the hard ceiling
# check (see compute_device_ceiling_bytes()). 0.85 (a first-draft guess) was
# reviewed and rejected: 0.85 * this device's ~10.8GiB total is ~9.2GiB,
# which the hard "never admissible regardless of anything else" check would
# then never actually refuse for any realistic model on this project (this
# device's own crash history is at 4.4GB model files, and live `free -h`
# during this module's build showed 7.3GiB already used with 5.6GiB already
# in swap at a fairly ordinary moment) — a hard ceiling that never fires
# isn't doing its job. 0.60 is a deliberately more conservative default:
# ~6.5GiB on this device, which still comfortably admits the project's own
# primary 7B model's ~6.4GiB cost estimate (the normal case) while actually
# refusing something meaningfully larger. Like REQUIRED_HEADROOM_FACTOR,
# this is an un-calibrated first default, not a value confirmed against
# real on-device load behavior — sub-task 3's live wiring (per TODO.md's
# 7.4 entry) should validate/retune both knobs against actual observed
# behavior, not just this sub-task's synthetic fixtures.
DEVICE_CEILING_USABLE_FRACTION = 0.60


def compute_device_ceiling_bytes(
    meminfo: Dict[str, int], usable_fraction: float = DEVICE_CEILING_USABLE_FRACTION
) -> int:
    """
    Compute the absolute per-model admission ceiling: the amount of physical
    RAM a single model may ever claim, regardless of current residency or
    headroom. This is what backs the one hard, non-negotiable check the
    2026-08-08 amendment keeps: "a single model must never be admitted if it
    alone exceeds what the device can handle."

    Deliberately derived from MemTotal only (never from live free/available
    figures) so it stays reachable even when the system is otherwise
    completely idle with generous headroom — a model too big for the device
    must be rejected in that case too, not just under memory pressure.

    `usable_fraction` (default DEVICE_CEILING_USABLE_FRACTION) reflects that
    no process can realistically claim all of physical RAM — the OS kernel,
    other running processes, and Termux/Android's own overhead need some of
    it. This is a named, documented knob (see DEVICE_CEILING_USABLE_FRACTION's
    own comment for why 0.60, not a higher/lower value) rather than a
    silently baked-in number, so it can be tuned per-device later (this
    logic is intended to run on higher-RAM hardware too, per Section 7.4's
    original text).
    """
    return int(meminfo.get("MemTotal", 0) * usable_fraction)


# ── Signal source 2: thermal state ───────────────────────────────────────────
# core/thermal.py's monitoring is never started by the daemon (confirmed by
# direct code read during 7.4 scoping) — this module does NOT depend on that
# monitoring loop being active. It only calls the new public
# ThermalManager.get_current_temp_c() accessor (added alongside this module,
# a minimal additive wrapper around the existing private _read_cpu_temp()),
# lazily imported so importing core.resource_gate never pulls in anything
# that could start a background thread or touch process state.


def read_current_temp_c() -> Optional[float]:
    """
    Live current CPU temperature (°C), or None if unreadable/unavailable.
    Lazy-imports core.thermal so this module stays import-safe (and
    side-effect-free at import time) even in contexts where core.thermal
    isn't wanted — matches this file's "no process-lifecycle risk to import"
    design goal.
    """
    try:
        from core.thermal import get_current_temp_c

        return get_current_temp_c()
    except Exception as e:
        # Best-effort signal only: thermal reads have always been optional
        # elsewhere in this codebase (see core/thermal.py's own
        # _check_thermal_status(), which treats a None read as "skip" rather
        # than an error). A failure here (missing /sys/class/thermal on a
        # non-Android host running tests, import error, etc.) must not block
        # admission decisions that don't depend on thermal state being
        # available — this is a signal-sourcing helper, not a safety gate by
        # itself.
        warning(f"resource_gate: thermal read failed, treating as unavailable: {e}")
        return None


# ── Model cost estimation ────────────────────────────────────────────────────
# NEW-21 (NEW_ISSUES.md): a run with baseline 4.3Gi used / 2.2Gi free saw
# swap climb 1.2Gi -> 5.6Gi in ~10s from a single primary-model load, before
# any inference occurred. A bare "headroom minus a safety margin" check would
# have approved that load (2.2Gi free was nonzero). The fix is estimating the
# model's actual cost — base weights + n_ctx-driven KV cache — and comparing
# THAT against headroom, not just checking "is there any headroom at all".


@dataclass(frozen=True)
class ModelArch:
    """
    Minimal transformer architecture parameters needed to estimate KV cache
    size. Values come from each model family's published config (Qwen2.5
    architecture docs), not from parsing the GGUF file — narrowly scoped to
    what this gate needs, not a general GGUF-metadata reader.
    """

    n_layers: int
    n_kv_heads: int
    head_dim: int
    # KV cache element size in bytes. MODEL_CONFIG["kv_type"] = "q4_0" in
    # utils/config.py suggests 4-bit KV, but that key is never actually
    # passed to `llama-server` in core/loader_v2.py's _spawn_locked() command
    # list (checked directly while building this module) — so the server
    # really runs with its default fp16 (2-byte) KV cache. Defaulting to 2
    # here matches real observed behavior, not the aspirational config value;
    # NEW_ISSUES.md gets a separate entry for the dead "kv_type" config key
    # (out of scope for this sub-task — signal sourcing/estimation only).
    kv_bytes_per_element: int = 2


# Qwen2.5-Coder-7B-Instruct: hidden_size=3584, num_hidden_layers=28,
# num_attention_heads=28, num_key_value_heads=4 (GQA), head_dim=128.
QWEN25_7B_ARCH = ModelArch(n_layers=28, n_kv_heads=4, head_dim=128)

# Qwen2.5-Coder-1.5B-Instruct: hidden_size=1536, num_hidden_layers=28,
# num_attention_heads=12, num_key_value_heads=2 (GQA), head_dim=128.
QWEN25_1_5B_ARCH = ModelArch(n_layers=28, n_kv_heads=2, head_dim=128)

# Keyed by the model file path this project already uses as identity
# (utils/config.py's MODEL_PATH / PLANNER_MODEL_PATH), not a free-form name.
KNOWN_MODEL_ARCHS: Dict[str, ModelArch] = {
    str(MODEL_PATH): QWEN25_7B_ARCH,
    str(PLANNER_MODEL_PATH): QWEN25_1_5B_ARCH,
}

# Flat allowance for compute buffers (batch/context scratch space, etc.)
# beyond weights + KV cache. Conservative default; not derived from a
# specific measurement, so it's a named constant rather than buried in the
# formula.
DEFAULT_COMPUTE_OVERHEAD_BYTES = 256 * 1024 * 1024  # 256 MiB


@dataclass(frozen=True)
class ModelSpec:
    """
    Declares what a candidate model load would cost, for `can_admit()`.

    `size_bytes` and `arch` may both be supplied explicitly (this is how
    tests avoid depending on real model files on disk); if `size_bytes` is
    omitted, it's read from `path.stat().st_size` at estimate time. If
    `arch` is omitted and `path` isn't one of `KNOWN_MODEL_ARCHS`, the KV
    cache term is estimated as 0 and a warning is logged — the cost estimate
    degrades to "weights + overhead only", which is a known-incomplete (not
    silently-wrong-in-the-safe-direction) estimate for unknown model
    families; callers passing genuinely unknown models should supply `arch`
    explicitly wherever possible.
    """

    model_id: str
    path: Optional[Path] = None
    size_bytes: Optional[int] = None
    n_ctx: int = 4096
    arch: Optional[ModelArch] = None
    compute_overhead_bytes: int = DEFAULT_COMPUTE_OVERHEAD_BYTES
    # Fraction of the on-disk model file expected to be resident in RAM
    # under load. 1.0 (default) is the conservative assumption — mmap only
    # touches pages as they're used, but llama.cpp's own load path
    # (embedding + first-pass tokenization) plus this project's inference
    # patterns realistically touch most of the file quickly; 1.0 matches
    # NEW-21's observed outcome (see tests/test_resource_gate.py) better
    # than assuming partial residency.
    mmap_resident_fraction: float = 1.0


@dataclass(frozen=True)
class CostEstimate:
    model_bytes: int
    kv_cache_bytes: int
    overhead_bytes: int

    @property
    def total_bytes(self) -> int:
        return self.model_bytes + self.kv_cache_bytes + self.overhead_bytes


def estimate_kv_cache_bytes(arch: ModelArch, n_ctx: int) -> int:
    """
    KV cache size = n_layers * 2 (K and V) * n_kv_heads * head_dim * n_ctx *
    bytes_per_element. Standard formula for GQA/MQA transformer KV cache;
    matches llama.cpp's own KV cache allocation shape.
    """
    return (
        arch.n_layers
        * 2
        * arch.n_kv_heads
        * arch.head_dim
        * n_ctx
        * arch.kv_bytes_per_element
    )


def _resolve_model_arch(spec: ModelSpec) -> Optional[ModelArch]:
    if spec.arch is not None:
        return spec.arch
    if spec.path is not None and str(spec.path) in KNOWN_MODEL_ARCHS:
        return KNOWN_MODEL_ARCHS[str(spec.path)]
    return None


def estimate_model_load_cost(spec: ModelSpec) -> CostEstimate:
    """
    Estimate the real memory cost of loading `spec`, per NEW-21's lesson:
    base model size + n_ctx-driven KV cache, not headroom checked in
    isolation.
    """
    if spec.size_bytes is not None:
        raw_bytes = spec.size_bytes
    elif spec.path is not None:
        raw_bytes = spec.path.stat().st_size
    else:
        raise ValueError(
            f"ModelSpec {spec.model_id!r} has neither size_bytes nor a resolvable path"
        )
    # mmap_resident_fraction applies regardless of whether the raw size came
    # from an explicit size_bytes or a real file stat — it's declaring "how
    # much of this many bytes ends up resident," not "how to derive the byte
    # count," so both sources go through it identically.
    model_bytes = int(raw_bytes * spec.mmap_resident_fraction)

    arch = _resolve_model_arch(spec)
    if arch is not None:
        kv_bytes = estimate_kv_cache_bytes(arch, spec.n_ctx)
    else:
        warning(
            f"resource_gate: no known architecture for model {spec.model_id!r}; "
            "KV cache term omitted from cost estimate (weights + overhead only)"
        )
        kv_bytes = 0

    return CostEstimate(
        model_bytes=model_bytes, kv_cache_bytes=kv_bytes, overhead_bytes=spec.compute_overhead_bytes
    )


# ── Admission decision ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class GateDecision:
    admitted: bool
    hard_reject: bool
    reason: str
    estimated_cost_bytes: int
    headroom_bytes: int
    device_ceiling_bytes: int


def can_admit(
    spec: ModelSpec,
    meminfo: Optional[Dict[str, int]] = None,
    reserved_bytes: int = 0,
    usable_fraction: float = DEVICE_CEILING_USABLE_FRACTION,
    headroom_factor: float = REQUIRED_HEADROOM_FACTOR,
    read_temp_fn=None,
) -> GateDecision:
    """
    Decide whether `spec` can be admitted right now.

    No fixed concurrency ceiling (per the 2026-08-08 amendment): this
    function does not know or care how many other models are resident,
    except via `reserved_bytes` (their already-declared cost, subtracted
    from headroom so concurrent admissions don't double-book the same
    memory — see `total_reserved_bytes()`).

    `meminfo` defaults to a live `/proc/meminfo` read if not supplied
    (tests should always supply a synthetic dict; see NEW-21's regression
    case in tests/test_resource_gate.py).

    `read_temp_fn` defaults to this module's `read_current_temp_c` (a live
    thermal read) if not supplied; tests should always supply a stub
    returning a fixed float or None instead of touching real hardware.

    Three independent checks, any of which can refuse admission:
      1. hard_reject: `spec`'s cost alone exceeds the device's usable
         physical-RAM ceiling — absolute, ignores current headroom/residency
         entirely (2026-08-08 amendment's one remaining non-negotiable rule).
      2. budget check: `spec`'s cost, times `headroom_factor` (a documented
         conservative margin — see REQUIRED_HEADROOM_FACTOR's docstring),
         exceeds currently-computed headroom (live MemAvailable, minus any
         `reserved_bytes`) — this is the live, computed limit that replaces
         the old fixed-count rule.
      3. thermal check: current CPU temperature (if readable) is at or above
         THERMAL_CONFIG["temp_critical"] — the amendment names thermal state
         as one of the live signals the gate arbitrates alongside RAM/swap,
         not just a post-hoc throttle applied after a model is already
         running (see core/thermal.py's existing, separate
         inference-duration-based throttling, which this does not replace).
         An unreadable temperature (None) is treated as "no thermal
         objection" — same fail-open posture core/thermal.py's own
         `_check_thermal_status()` already uses for a None read.
    """
    if meminfo is None:
        meminfo = read_meminfo()
    if read_temp_fn is None:
        read_temp_fn = read_current_temp_c

    cost = estimate_model_load_cost(spec)
    ceiling = compute_device_ceiling_bytes(meminfo, usable_fraction=usable_fraction)
    headroom = compute_headroom_bytes(meminfo, reserved_bytes=reserved_bytes)
    required = int(cost.total_bytes * headroom_factor)

    if cost.total_bytes > ceiling:
        return GateDecision(
            admitted=False,
            hard_reject=True,
            reason=(
                f"model {spec.model_id!r} cost estimate "
                f"({cost.total_bytes / _KB / _KB:.0f}MiB) exceeds device ceiling "
                f"({ceiling / _KB / _KB:.0f}MiB) — never admissible regardless of "
                "current residency"
            ),
            estimated_cost_bytes=cost.total_bytes,
            headroom_bytes=headroom,
            device_ceiling_bytes=ceiling,
        )

    try:
        current_temp = read_temp_fn()
    except Exception as e:
        # Same "best-effort signal, never block on failure to read it"
        # posture as read_current_temp_c() itself — a thermal-read failure
        # must not be indistinguishable from "device is overheating."
        warning(f"resource_gate: thermal read in can_admit() failed, ignoring: {e}")
        current_temp = None

    if current_temp is not None:
        from utils.config import THERMAL_CONFIG

        temp_critical = THERMAL_CONFIG.get("temp_critical", 90)
        if current_temp >= temp_critical:
            return GateDecision(
                admitted=False,
                hard_reject=False,
                reason=(
                    f"current CPU temperature ({current_temp:.1f}°C) at/above "
                    f"critical threshold ({temp_critical}°C) — deferring new "
                    "model admission until thermal state recovers"
                ),
                estimated_cost_bytes=cost.total_bytes,
                headroom_bytes=headroom,
                device_ceiling_bytes=ceiling,
            )

    if required > headroom:
        return GateDecision(
            admitted=False,
            hard_reject=False,
            reason=(
                f"model {spec.model_id!r} cost estimate "
                f"({cost.total_bytes / _KB / _KB:.0f}MiB) x headroom_factor "
                f"({headroom_factor}) = {required / _KB / _KB:.0f}MiB, which exceeds "
                f"current headroom ({headroom / _KB / _KB:.0f}MiB)"
            ),
            estimated_cost_bytes=cost.total_bytes,
            headroom_bytes=headroom,
            device_ceiling_bytes=ceiling,
        )

    return GateDecision(
        admitted=True,
        hard_reject=False,
        reason="within headroom (with margin) and device ceiling",
        estimated_cost_bytes=cost.total_bytes,
        headroom_bytes=headroom,
        device_ceiling_bytes=ceiling,
    )


def would_model_fit(
    spec: ModelSpec,
    meminfo: Optional[Dict[str, int]] = None,
    reserved_bytes: int = 0,
    read_temp_fn=None,
) -> bool:
    """
    Answerable-question hook for the amendment's noted future direction
    (task-appropriate fallback to a smaller model): "would this model fit
    right now", without registering a slot or otherwise having any side
    effect. Deliberately NOT a routing decision — just exposes the same
    admission math `can_admit()` uses so a future routing layer (7.3) can
    query it. Not implementing routing itself is intentional (see this
    module's docstring / TODO.md 7.4).
    """
    return can_admit(
        spec, meminfo=meminfo, reserved_bytes=reserved_bytes, read_temp_fn=read_temp_fn
    ).admitted


# ── CPU thread/core allocation ───────────────────────────────────────────────
# Per the 2026-08-08 amendment, the gate also owns per-model thread/core
# allocation as concurrently-resident model count changes — a second axis it
# arbitrates, not a separate mechanism. This does NOT read or write
# core/thermal.py's existing MODEL_CONFIG["n_threads"] mutation (see
# ThermalManager._reduce_threads()) — that's a second, pre-existing
# authority over thread count for thermal throttling of the (today) single
# resident model. Composing with it is done via the optional `thermal_cap`
# parameter (pass core.thermal.get_current_threads() at the call site once
# this is actually wired in a later sub-task), not by this function reading
# that global itself.


def get_cpu_core_count() -> int:
    """Live core count, with a conservative fallback if undetectable."""
    return os.cpu_count() or 4


def allocate_threads(
    n_models: int,
    total_cores: Optional[int] = None,
    thermal_cap: Optional[int] = None,
    min_threads: int = 1,
) -> List[int]:
    """
    Given `n_models` concurrently-resident models and `total_cores` available
    cores, return a list of length `n_models` with a recommended thread
    count per model, so total compute demand stays within device capacity.

    Not wired into any actual inference call yet (that's a later sub-task,
    once the gate itself is migrated onto by daemon.py/loader_v2.py) — this
    is a pure, independently-testable allocation function.

    Each model gets at least `min_threads` (default 1) even if
    `n_models * min_threads > total_cores` — oversubscription in that case is
    accepted rather than allocating 0 threads to a model, and is visible to
    the caller via the returned list summing to more than `total_cores`.
    Otherwise, cores are divided as evenly as possible (floor division, with
    the remainder distributed one-by-one to the first models in the list) and
    each per-model value is capped at `thermal_cap` if provided (that cap can
    push total allocation below `total_cores`; this function does not try to
    redistribute the slack elsewhere — a later sub-task can revisit that if
    it turns out to matter in practice).
    """
    if n_models <= 0:
        return []
    if total_cores is None:
        total_cores = get_cpu_core_count()
    total_cores = max(1, total_cores)

    if n_models * min_threads >= total_cores:
        allocation = [min_threads] * n_models
    else:
        base, remainder = divmod(total_cores, n_models)
        allocation = [base + (1 if i < remainder else 0) for i in range(n_models)]

    if thermal_cap is not None:
        allocation = [max(min_threads, min(v, thermal_cap)) for v in allocation]

    return allocation


# ── Cross-process residency state store ──────────────────────────────────────
# Small file-backed store so the daemon and separate main.py CLI processes
# can observe/register the same residency state (NEW-69, resolved into scope
# per TODO.md's 7.4 entry — enforcement against the CLI waits for sub-task 4,
# but the state primitive itself is built here so it exists from sub-task 1).
#
# Follows core/loader_v2.py's llama-server-{port}.lock flock convention, but
# with one deliberate difference: that lock file is always empty, so
# `open(path, "w")` immediately before flock'ing is safe there. This store's
# payload file holds JSON data, so the same pattern would truncate it before
# the lock is even held. Instead: a separate, always-empty sibling
# `.lock` file is flock'd, and the payload file itself is only ever replaced
# atomically (write to a temp file in the same directory, then os.replace())
# while that lock is held.
#
# Each slot record carries a `status` lifecycle field — SLOT_STATUS_PENDING
# ("reserved, load not yet confirmed") vs. SLOT_STATUS_RESIDENT ("model
# confirmed actually running") — added specifically so total_reserved_bytes()
# can match compute_headroom_bytes()'s documented contract for its
# `reserved_bytes` parameter: "other slots that are concurrently being
# admitted/loaded but haven't yet shown up in a fresh /proc/meminfo read".
# That description is PENDING-only — once a slot is RESIDENT, its memory
# footprint is already reflected in any subsequent live /proc/meminfo read,
# so continuing to subtract its cost via reserved_bytes would double-count
# it (headroom computed as lower than it actually is, incorrectly refusing
# otherwise-admissible loads). See total_reserved_bytes()'s own docstring.

SLOT_STATUS_PENDING = "pending"
SLOT_STATUS_RESIDENT = "resident"

_STATE_FILENAME = "resource_gate_state.json"
_LOCK_FILENAME = "resource_gate_state.lock"


def _state_paths(state_dir: Optional[Path]) -> tuple[Path, Path]:
    base = Path(state_dir) if state_dir is not None else CODEY_STATE_DIR
    base.mkdir(parents=True, exist_ok=True)
    return base / _STATE_FILENAME, base / _LOCK_FILENAME


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists but we don't own it — still alive, matches
        # core/daemon.py:check_pid_file()'s same os.kill(pid, 0) precedent.
        return True
    except OSError:
        # Unexpected OSError from kill(2) (not ProcessLookupError/
        # PermissionError) — cannot positively confirm liveness or death.
        # Fail closed (treat as "still alive", don't reap): this is
        # accounting state for a resource gate whose whole purpose is
        # avoiding over-admission, so wrongly reaping a live slot (which
        # could let a second load be wrongly admitted on top of it) is the
        # worse failure mode here, not a stale entry lingering a bit longer.
        return True


def _read_state_locked(path: Path) -> List[dict]:
    if not path.exists():
        return []
    try:
        with open(path, "r") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
    except (json.JSONDecodeError, OSError):
        # Corrupt/unreadable state file. Fail closed here would mean
        # refusing to report ANY residency state, which would make every
        # other process blind rather than just this one read stale/empty —
        # worse for the gate's purpose than starting from an empty list and
        # letting registrations rebuild it. Logged, not silent.
        warning(f"resource_gate: state file {path} unreadable/corrupt, treating as empty")
    return []


def _write_state_locked(path: Path, slots: List[dict]) -> None:
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".resource_gate_state_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(slots, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


class _LockedState:
    """Context manager: acquire the sibling lock file, yield the current
    slot list for mutation, write it back atomically on clean exit."""

    def __init__(self, state_dir: Optional[Path]):
        self._state_path, self._lock_path = _state_paths(state_dir)
        self._lock_fd = None

    def __enter__(self) -> List[dict]:
        import fcntl

        self._lock_fd = open(self._lock_path, "w")
        fcntl.flock(self._lock_fd, fcntl.LOCK_EX)  # blocking — short critical section
        self._slots = _read_state_locked(self._state_path)
        return self._slots

    def __exit__(self, exc_type, exc, tb) -> bool:
        import fcntl

        try:
            if exc_type is None:
                _write_state_locked(self._state_path, self._slots)
        finally:
            try:
                fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
            except OSError:
                # Best-effort only — closing the fd (next line) or process
                # exit releases the flock regardless (same reasoning as
                # core/loader_v2.py:LlamaServer.start()'s matching unlock).
                pass
            self._lock_fd.close()
        return False  # never swallow an exception from the `with` body


def register_slot(
    model_id: str,
    cost_bytes: int,
    pid: Optional[int] = None,
    port: Optional[int] = None,
    threads: Optional[int] = None,
    status: str = SLOT_STATUS_PENDING,
    state_dir: Optional[Path] = None,
) -> str:
    """
    Register a slot in the cross-process store, unconditionally (no
    admission check) — for callers that have already decided the slot
    should exist, or that own the admission decision themselves. Callers
    that need "check admission and register atomically, with no TOCTOU
    window between the two" should use `reserve_slot()` instead (see its
    docstring) — that is the safe primitive for the actual "can I load and
    reserve this?" flow when multiple processes may be racing.

    Returns a slot_id for later `release_slot()`/`mark_resident()`.

    `pid` defaults to this process's own PID — the natural owner of a slot
    it's registering — but callers may pass a different PID if the actual
    model server subprocess's PID is known and different from the caller's
    own (e.g. the daemon registering on behalf of a spawned llama-server).

    `status` (default SLOT_STATUS_PENDING) records where in its lifecycle
    the slot is — see this section's header comment and
    `total_reserved_bytes()`'s docstring for why this distinction exists.
    Pass SLOT_STATUS_RESIDENT directly only if the model is already known
    to be fully loaded and running at registration time; otherwise register
    as PENDING and call `mark_resident()` once load is confirmed.
    """
    if pid is None:
        pid = os.getpid()
    slot_id = uuid.uuid4().hex
    entry = {
        "slot_id": slot_id,
        "model_id": model_id,
        "cost_bytes": cost_bytes,
        "pid": pid,
        "port": port,
        "threads": threads,
        "status": status,
        "registered_at": time.time(),
    }
    with _LockedState(state_dir) as slots:
        slots.append(entry)
    return slot_id


def reserve_slot(
    spec: ModelSpec,
    meminfo: Optional[Dict[str, int]] = None,
    usable_fraction: float = DEVICE_CEILING_USABLE_FRACTION,
    headroom_factor: float = REQUIRED_HEADROOM_FACTOR,
    read_temp_fn=None,
    pid: Optional[int] = None,
    port: Optional[int] = None,
    threads: Optional[int] = None,
    reap_dead: bool = True,
    state_dir: Optional[Path] = None,
) -> Tuple[GateDecision, Optional[str]]:
    """
    Atomically decide admission AND register the slot if admitted — the
    single-lock-acquisition replacement for the unsafe pattern of calling
    `total_reserved_bytes()`, then `can_admit()`, then `register_slot()` as
    three separate steps.

    That three-step pattern acquires this store's flock three separate
    times (once inside total_reserved_bytes(), none for can_admit() itself,
    once inside register_slot()), releasing it in between each. That leaves
    a window, between the "is there room" read and the "write my
    reservation" write, where a second concurrent caller (a different
    process or thread) can run the same three steps and also pass its own
    "is there room" check — both then register, and the store ends up
    over-admitted beyond what the budget actually allows. This function
    closes that window by holding the lock for the whole
    read-check-write sequence.

    Live signals that don't belong to the state store (meminfo, thermal) are
    deliberately read BEFORE the lock is acquired, not inside the `with
    _LockedState(...)` block below: `_LockedState` holds a *blocking* flock
    with no timeout (see its own docstring — "short critical section" is a
    documented assumption, not just a comment), and the default
    `read_temp_fn` (`read_current_temp_c`) does a lazy `core.thermal` import
    plus a sysfs read — a slow or hanging sysfs read must not be able to
    stall every other process waiting on this store's lock. Reading the
    temperature once up front and passing a fixed-value closure into
    `can_admit()` keeps the actual critical section to state-read +
    arithmetic + write, matching that assumption.

    Returns `(decision, slot_id)`. `slot_id` is `None` when `decision.admitted`
    is `False` (nothing was registered). The new slot (if any) is created
    with status SLOT_STATUS_PENDING — call `mark_resident()` once the model
    is confirmed actually running.
    """
    if meminfo is None:
        meminfo = read_meminfo()
    if read_temp_fn is None:
        read_temp_fn = read_current_temp_c
    if pid is None:
        pid = os.getpid()

    # Captured once, outside the lock — see docstring above.
    try:
        captured_temp = read_temp_fn()
    except Exception as e:
        # Same best-effort posture as can_admit()'s own try/except around
        # read_temp_fn() — a thermal-read failure must not be
        # indistinguishable from "device is overheating," and must not
        # propagate out of this function either.
        warning(f"resource_gate: thermal read in reserve_slot() failed, ignoring: {e}")
        captured_temp = None

    def _fixed_temp_fn():
        return captured_temp

    with _LockedState(state_dir) as slots:
        if reap_dead:
            slots[:] = [s for s in slots if s.get("pid") is None or _pid_alive(s["pid"])]

        # Only PENDING slots count against reserved_bytes — see this
        # section's header comment / total_reserved_bytes()'s docstring for
        # why RESIDENT slots must not also be subtracted here (their cost is
        # already reflected in `meminfo`).
        reserved = sum(
            s.get("cost_bytes", 0)
            for s in slots
            if s.get("status", SLOT_STATUS_PENDING) == SLOT_STATUS_PENDING
        )

        decision = can_admit(
            spec,
            meminfo=meminfo,
            reserved_bytes=reserved,
            usable_fraction=usable_fraction,
            headroom_factor=headroom_factor,
            read_temp_fn=_fixed_temp_fn,
        )

        if not decision.admitted:
            return decision, None

        slot_id = uuid.uuid4().hex
        slots.append(
            {
                "slot_id": slot_id,
                "model_id": spec.model_id,
                "cost_bytes": decision.estimated_cost_bytes,
                "pid": pid,
                "port": port,
                "threads": threads,
                "status": SLOT_STATUS_PENDING,
                "registered_at": time.time(),
            }
        )
        return decision, slot_id


def mark_resident(slot_id: str, state_dir: Optional[Path] = None) -> bool:
    """
    Transition a slot from SLOT_STATUS_PENDING to SLOT_STATUS_RESIDENT,
    confirming the model actually finished loading (as opposed to merely
    being reserved/in flight). Returns True if a matching slot was found
    and updated, False otherwise.

    Matters for total_reserved_bytes()'s documented contract: see this
    section's header comment and total_reserved_bytes()'s own docstring for
    why only PENDING slots should count against reserved_bytes.

    PRECONDITION callers must respect: only call this once the load is
    genuinely complete AND the model's memory footprint is actually
    reflected in a fresh `/proc/meminfo` read — NOT merely once a health
    endpoint/port starts answering. `ModelSpec.mmap_resident_fraction`'s own
    docstring notes llama.cpp/mmap pages a model's weights in over time
    rather than all at once; a slot marked RESIDENT before its real memory
    use has actually landed would stop counting against reserved_bytes (per
    total_reserved_bytes()'s PENDING-only contract) while MemAvailable still
    hasn't dropped to reflect it — reopening NEW-21's exact "true cost isn't
    visible yet" failure mode through this field instead of through a bare
    headroom check. This is a contract for sub-task 3's future wiring
    (out of scope for this module today), not something this function can
    enforce itself.
    """
    found = False
    with _LockedState(state_dir) as slots:
        for s in slots:
            if s.get("slot_id") == slot_id:
                s["status"] = SLOT_STATUS_RESIDENT
                found = True
                break
    return found


def release_slot(slot_id: str, state_dir: Optional[Path] = None) -> bool:
    """Remove a slot by id. Returns True if a matching slot was found/removed."""
    found = False
    with _LockedState(state_dir) as slots:
        remaining = [s for s in slots if s.get("slot_id") != slot_id]
        found = len(remaining) != len(slots)
        slots[:] = remaining
    return found


def list_slots(state_dir: Optional[Path] = None, reap_dead: bool = True) -> List[dict]:
    """
    Return currently-registered slots. If `reap_dead` (default True), slots
    whose owning PID is no longer alive are dropped from the store as part
    of this read (self-healing — no separate reaper process needed), using
    the same os.kill(pid, 0) liveness precedent as
    core/daemon.py:check_pid_file().
    """
    with _LockedState(state_dir) as slots:
        if reap_dead:
            live = [s for s in slots if s.get("pid") is None or _pid_alive(s["pid"])]
            slots[:] = live
        return list(slots)


def total_reserved_bytes(state_dir: Optional[Path] = None, reap_dead: bool = True) -> int:
    """
    Sum of declared cost_bytes across currently-registered, live,
    SLOT_STATUS_PENDING slots ONLY — the value to pass as `can_admit()`'s
    `reserved_bytes` so a concurrent admission check doesn't double-book
    memory another in-flight (not-yet-confirmed-loaded) slot already
    claimed.

    Deliberately excludes SLOT_STATUS_RESIDENT slots: this matches
    `compute_headroom_bytes()`'s documented contract for `reserved_bytes`
    ("other slots that are concurrently being admitted/loaded but haven't
    yet shown up in a fresh /proc/meminfo read") — a RESIDENT slot's memory
    footprint IS already reflected in any subsequent live meminfo read, so
    also subtracting its cost here would double-count it, making computed
    headroom lower than reality and incorrectly refusing otherwise-
    admissible loads. A slot with no `status` field at all (state written
    before this field existed) is treated as PENDING — the conservative
    default, matching this function's pre-existing "count everything"
    behavior for such legacy entries rather than silently excluding them.
    """
    return sum(
        s.get("cost_bytes", 0)
        for s in list_slots(state_dir=state_dir, reap_dead=reap_dead)
        if s.get("status", SLOT_STATUS_PENDING) == SLOT_STATUS_PENDING
    )
