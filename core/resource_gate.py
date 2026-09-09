#!/usr/bin/env python3
"""
Resource gate — Track 3 Phase 5a / CODEY_OS_MASTER_VISION.md Section 7.4
(2026-08-08 amendment). Originally built as sub-task 1 of 5 of the
model-load-admission migration; see below for the now-completed wiring
into the real call sites.

This module is the "single authority" for model-load admission decisions
described in 7.4, built as a standalone, unit-testable component. It IS
wired live into `core/daemon.py` and `core/loader_v2.py`: `loader_v2.py`
calls `reserve_slot()`, `mark_resident()`, and `find_resident_slot()` on
the actual coder-server load/upgrade/adopt path, and `daemon.py` lazily
imports `sample_cpu_percent()`, `sample_temperature_c()`,
`should_trip_shutdown()`, `is_interactive_session_active()`,
`compute_zram_compression_ratio()`, `can_dispatch_task()`, and
`get_resource_snapshot()` for its monitoring/dispatch loop. `main.py`
also imports `get_resource_snapshot()` for CLI status reporting.
`core/planner_loader.py` no longer exists — it was retired in M1-D
(2026-08-23, see `core/planner_service.py`'s docstring) when the planner
model was upgraded to a dedicated 1.5B, so there is nothing left to wire
this module into there. This module still has no process-lifecycle risk
on its own: importing it starts nothing and spawns nothing, and its
sampling functions read only `/proc/meminfo` (mockable) and thermal
state (lazily imported, best-effort) — the process-lifecycle risk lives
in the callers (`daemon.py`, `loader_v2.py`), not in this module.

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

TODO.md 7.4a sub-task C1 adds a second, independent, NAMED ceiling:
`MAX_CONCURRENT_MODEL_BUDGET_BYTES` caps the SUM of every concurrently-
declared model's cost (see `total_committed_bytes()`), checked before any
live-memory/thermal signal. This is deliberately NOT the "max N models"
fixed concurrency ceiling the 2026-08-08 amendment rejects above — it bounds
total declared bytes, not model count, and (unlike hard_reject) is
recoverable: releasing/unloading a resident model can bring a later load
back under budget (see `GateDecision.budget_ceiling_exceeded`).

TODO.md 7.4a sub-task C2 adds a SECONDARY check on top of the existing
`MemAvailable`-based headroom check, evaluated only when that plain-RAM
check would otherwise refuse admission: swap-assisted headroom
(`compute_swap_assisted_headroom_bytes()`, ON by default per Ish's
2026-08-11 direct decision, `CODEY_SWAP_ASSIST_ADMISSION=0` to disable).
Reported via `GateDecision.admitted_via_swap` so a caller/log can
distinguish "admitted on RAM" from "admitted on swap budget." This check
may only ever override the plain-RAM headroom denial — it can never
override C1's `MAX_CONCURRENT_MODEL_BUDGET_BYTES` denial (see
`can_admit()`'s own docstring for why that's structurally guaranteed, not
just a documented intent).

TODO.md 7.4a sub-task D is a consistency pass on what C1/C2 each left
unreconciled elsewhere: (D1) `would_model_fit()` gained a
`would_model_fit_decision()` sibling returning the full `GateDecision`
(instead of changing `would_model_fit()`'s own bool return type, which
would silently break any bool-checking caller — see that function's own
docstring) so a future routing caller can distinguish a budget-ceiling
"no" from a headroom "no", and a RAM-comfortable "yes" from a
swap-assisted one. (D2, Ish's direct 2026-08-11 decision)
`can_dispatch_task()`'s `DISPATCH_MIN_HEADROOM_BYTES` floor is now
swap-aware too, via the same `compute_swap_assisted_headroom_bytes()`
mechanism and `CODEY_SWAP_ASSIST_ADMISSION` on/off convention C2
established (its own swap-usage cap, `DISPATCH_MAX_SWAP_ASSIST_BYTES`, was
deliberately decoupled from `can_admit()`'s `MAX_SWAP_ASSIST_BYTES` by
sub-task F's 2026-08-11 recalibration — see that constant's own comment),
reported via
`DispatchDecision.dispatched_via_swap` — see `can_dispatch_task()`'s own
docstring for the full wiring and its one deliberate difference from
`can_admit()`'s swap-assist error handling (a malformed
`CODEY_SWAP_ASSIST_ADMISSION` value is caught and treated as "disabled"
here, not left to propagate, because this function runs unguarded on
every tick of the daemon's autonomous dispatch loop).

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
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from utils.config import CODEY_STATE_DIR
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


# ── Signal source 1b: zram state, via /sys/block/zram0 ──────────────────────
# TODO.md 7.4a sub-task A. `read_meminfo()` above already surfaces
# SwapTotal/SwapFree (this device's ~12GiB zram-backed swap device shows up
# there as ordinary swap, no extra plumbing needed) — what's missing is the
# zram device's OWN accounting: how much of that swap is actually in use
# right now, and at what compression ratio, which /proc/meminfo cannot say.
# Live-read on this device, 2026-08-11 (values used only to confirm field
# names/shape, not hardcoded anywhere below):
#   /sys/block/zram0/disksize   -> "12884901888" (bytes, single integer)
#   /sys/block/zram0/mm_stat    -> 9 whitespace-separated integers, in this
#     fixed kernel-documented order: orig_data_size, compr_data_size,
#     mem_used_total, mem_limit, mem_used_max, same_pages, pages_compacted,
#     huge_pages, huge_pages_since. Only the first three are used here — the
#     rest aren't needed by anything this sub-task builds.
#
# zram is a compressed block device living INSIDE MemTotal, not extra
# capacity outside it (see TODO.md 7.4a's own "zram-specific risk" note) —
# this function only sources the signal; it does not itself claim any
# particular compression ratio carries over to model-weight pages (already
# high-entropy, likely closer to 1:1 than the ~4:1 ratio observed on
# ordinary idle app pages — unverified until sub-task E's live pass).


def read_zram_stats(
    disksize_path: str = "/sys/block/zram0/disksize",
    mm_stat_path: str = "/sys/block/zram0/mm_stat",
) -> Optional[Dict[str, int]]:
    """
    Read live zram device accounting, or None if unavailable (non-Android
    host, no zram device configured, permission denied, etc.) — mirrors
    `read_current_temp_c()`'s fail-soft posture (never raises), NOT
    `read_meminfo()`'s fail-loud posture. The difference is deliberate:
    `read_meminfo()` raising on a missing /proc/meminfo signals a genuinely
    broken environment for a function every admission decision depends on;
    a missing zram device is an expected, unremarkable case (this signal is
    additive/optional — no existing check in this module depends on it) on
    any non-Android host running this test suite, so callers must be able
    to treat "no zram" as a normal, common return value rather than an
    exception to catch everywhere this is called.

    Returns a dict with keys `disksize_bytes`, `orig_data_size_bytes`,
    `compr_data_size_bytes`, `mem_used_total_bytes` (all raw bytes, straight
    from the kernel's own accounting, no derived ratio) — the ratio itself
    is computed by `compute_zram_compression_ratio()` below, kept separate
    so a caller that only wants the raw counters isn't forced through a
    division.
    """
    try:
        with open(disksize_path, "r") as f:
            disksize_bytes = int(f.read().strip())
        with open(mm_stat_path, "r") as f:
            fields = f.read().split()
        orig_data_size = int(fields[0])
        compr_data_size = int(fields[1])
        mem_used_total = int(fields[2])
    except Exception as e:
        # Best-effort signal only, same posture as read_current_temp_c():
        # a missing/unreadable zram device must not block anything that
        # calls this, and this module has no admission logic depending on
        # it yet (sub-task A is signal-sourcing only).
        warning(f"resource_gate: zram stats read failed, treating as unavailable: {e}")
        return None
    return {
        "disksize_bytes": disksize_bytes,
        "orig_data_size_bytes": orig_data_size,
        "compr_data_size_bytes": compr_data_size,
        "mem_used_total_bytes": mem_used_total,
    }


def compute_zram_compression_ratio(zram_stats: Optional[Dict[str, int]]) -> Optional[float]:
    """
    logical-bytes-stored / physical-bytes-used-to-store-them, i.e.
    `orig_data_size / compr_data_size` — the ratio a caller would read as
    "how much headroom is compression buying." Uses `compr_data_size`
    (compressed payload size only) as the denominator rather than
    `mem_used_total` (compressed payload + zram's own per-page bookkeeping
    overhead) so the ratio reflects compression efficiency itself, not
    allocator overhead; on this device's own live sample the two
    denominators give ~3.76 vs ~3.58 respectively — a real but secondary
    difference, not a bug in either choice, and not investigated further
    here since this sub-task only sources the signal (no admission math
    consumes it yet).

    Returns None if `zram_stats` is None, or if `compr_data_size_bytes` is 0
    (an idle/unused zram device — dividing by zero would be wrong, and 0
    compressed bytes doesn't mean "infinite compression," it means "nothing
    has been swapped yet").
    """
    if zram_stats is None:
        return None
    compr = zram_stats.get("compr_data_size_bytes", 0)
    if compr <= 0:
        return None
    return zram_stats.get("orig_data_size_bytes", 0) / compr


# ── Sub-task B: pure swap-assisted headroom function ─────────────────────────
# TODO.md 7.4a sub-task B. Pure, standalone, independently unit-testable:
# takes `meminfo` and an explicit `max_swap_usage_bytes` cap as parameters,
# never reads real system state itself, and (as built by sub-task B) blesses
# no default cap value of its own. TODO.md 7.4a sub-task C2 (below, in the
# admission-decision section) is the caller that wires this function into
# `can_admit()` and supplies the real default (`MAX_SWAP_ASSIST_BYTES`) — see
# that section for the wiring itself.

# Device-grounded floor this function's formula is anchored to, per Ish's
# 2026-08-11 direction (TODO.md 7.4a): `getprop
# ro.slmk.swap_free_low_percentage` reads 10 on this device — Samsung's own
# low-memory-killer (slmk) starts killing processes once SwapFree drops
# below this fraction of SwapTotal. Computed live from SwapTotal (not
# hardcoded to a fixed byte value) so it tracks whatever SwapTotal this
# device (or a future different device) actually reports, matching this
# module's existing "derive from live meminfo, not a baked-in number"
# convention (compute_device_ceiling_bytes()'s own usable_fraction pattern).
SLMK_SWAP_FREE_LOW_FRACTION = 0.10

# Gate term that zeroes the swap assist as SwapFree approaches the slmk kill
# floor above — staying two full slmk floors above the point Samsung's own
# low-memory-killer starts acting, per TODO.md 7.4a's own derivation. Named
# and pulled out to module level (rather than left as a bare `2.0` default
# inline on each function that uses it) specifically so
# `compute_swap_assisted_headroom_bytes()` and `can_admit()` (sub-task C2)
# can't drift into two different numbers meaning the same thing — the exact
# "second number to keep in sync" problem MAX_CONCURRENT_MODEL_BUDGET_BYTES's
# own comment already warns against for a different pair of constants. An
# un-calibrated first default, same status as REQUIRED_HEADROOM_FACTOR/
# DEVICE_CEILING_USABLE_FRACTION — sub-task E's live pass is what actually
# calibrates it, not this module's synthetic fixtures.
SLMK_FLOOR_GATE_MULTIPLIER = 2.0


def compute_swap_assisted_headroom_bytes(
    meminfo: Dict[str, int],
    max_swap_usage_bytes: int,
    slmk_floor_gate_multiplier: float = SLMK_FLOOR_GATE_MULTIPLIER,
    reserved_swap_bytes: int = 0,
) -> int:
    """
    Additional headroom (in bytes) a swap-assisted admission check would
    allow BEYOND `compute_headroom_bytes()`'s existing MemAvailable-only
    figure — i.e. `compute_headroom_bytes(meminfo) +
    compute_swap_assisted_headroom_bytes(meminfo, max_swap_usage_bytes)` is
    the swap-assisted total a future caller (sub-task C2) would compare
    against a candidate load's required cost. This function itself performs
    no such comparison and has no admission side effects — it only computes
    the additive figure.

    `reserved_swap_bytes` (default 0, `NEW-135`'s fix): the swap-assist
    already authorized to OTHER concurrently-PENDING admissions, so a second
    admission racing the first doesn't see the full `max_swap_usage_bytes`
    cap as still-available. Mirrors `compute_headroom_bytes()`'s existing
    `reserved_bytes` parameter, but is subtracted from the POLICY CAP
    (`max_swap_usage_bytes`), not from the live `SwapFree` signal itself —
    unlike RAM, swap authorized-but-not-yet-consumed by a still-loading
    PENDING slot has not actually reduced `SwapFree` yet (the model hasn't
    started paging in), so the live gated-SwapFree term below is computed
    exactly as before; only the shared authorization ceiling shrinks by
    however much of it other in-flight admissions have already claimed. See
    `reserve_slot()` for the one caller that computes and passes a real,
    lock-consistent value here (the RAM-side `reserved_bytes` precedent for
    why this must be computed inside that same lock, not via a separate
    call).

    Formula (TODO.md 7.4a's own scoping call, not guessed):
        permitted = min(
            max_swap_usage_bytes,
            max(0, SwapFree - slmk_floor_gate_multiplier * slmk_floor_bytes),
        )
    where `slmk_floor_bytes = SwapTotal * SLMK_SWAP_FREE_LOW_FRACTION` (the
    device-grounded slmk kill floor, computed live above, NOT hardcoded).
    `slmk_floor_gate_multiplier` (default SLMK_FLOOR_GATE_MULTIPLIER, 2.0) is
    a gate term that zeroes the assist as SwapFree approaches that floor —
    staying two full slmk floors above the point Samsung's own
    low-memory-killer starts acting, per TODO.md 7.4a's own derivation, an
    un-calibrated first default in the same spirit as
    REQUIRED_HEADROOM_FACTOR/DEVICE_CEILING_USABLE_FRACTION (sub-task E's
    live pass is what actually calibrates it, not this sub-task's synthetic
    fixtures).

    `max_swap_usage_bytes` is NOT capped by this function to any built-in
    default — sub-task B (this function) deliberately took it as a required
    parameter (see this section's header comment) rather than blessing a
    module-level constant; sub-task C2 is the caller that supplies the real
    default (`MAX_SWAP_ASSIST_BYTES`, 6.50GiB as of M1-F's 2026-08-24
    re-derivation, superseding sub-task F's 2026-08-11 10.00GiB — see
    `can_admit()`'s own swap-assist section below for that constant's
    derivation; `can_dispatch_task()` uses its own,
    deliberately unchanged, `DISPATCH_MAX_SWAP_ASSIST_BYTES`, 768MiB).

    Callers must NOT treat the returned bytes as 1:1 usable headroom in the
    same sense as real free RAM: zram is a compressed block device living
    INSIDE MemTotal, not extra capacity outside it, and quantized model
    weights (already high-entropy) may compress far less favorably than the
    ~4:1 ratio observed on ordinary idle app pages (see
    `read_zram_stats()`'s own header comment) — this is authorized swap
    USAGE, not a claim about how much real headroom that usage actually
    buys under a real model load. Unverified until sub-task E's live pass.
    """
    swap_free = meminfo.get("SwapFree", 0)
    swap_total = meminfo.get("SwapTotal", 0)
    slmk_floor_bytes = swap_total * SLMK_SWAP_FREE_LOW_FRACTION
    gated_swap_free = max(0, swap_free - slmk_floor_gate_multiplier * slmk_floor_bytes)
    # NEW-135: the shared authorization ceiling shrinks by whatever other
    # in-flight PENDING admissions have already claimed against it — see
    # this parameter's own docstring for why this is subtracted from the
    # cap rather than from `gated_swap_free`.
    remaining_cap = max(0, max_swap_usage_bytes - reserved_swap_bytes)
    return int(max(0, min(remaining_cap, gated_swap_free)))


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
# ~6.5GiB on this device, which comfortably admits the project's new
# primary Qwen3.5-4B model's ~3.2GiB cost estimate (the normal case) while actually
# refusing something meaningfully larger. Like REQUIRED_HEADROOM_FACTOR,
# this fraction is retained un-retuned for the 4B era because 0.60 remains
# a demonstrably safe structural ceiling, even if the margin is wider now.
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


# ── Signal source 3: rolling system-wide CPU% ────────────────────────────────
# Track 3 Phase 5a / 7.4 sub-task A. Reuses core/sysmon.py's own /proc/stat
# delta math (same fields, same formula) rather than reinventing it, but as
# a ROLLING sampler fed by the daemon's existing 30s watchdog tick
# (core/daemon.py's `_main_loop()`), not a one-shot cold-read helper: 7.4
# sub-task D (later, out of scope here) needs CPU *history* for a 20-minute
# sustained-threshold tripwire check, so this module keeps enough history
# now for D to consume without redesigning the sampler.
#
# core/sysmon.py's own SystemMonitor is NOT used as the sampling engine
# here — confirmed by reading every call site (core/daemon.py never imports
# core.sysmon at all; only main.py's TUI, core/recursive.py, and the CCOS
# thermal_monitor plugin do, each starting/using their own instance) that
# its background thread has never been started by the daemon (matching
# 7.4's own scoping note that it historically was dead code from the
# daemon's perspective). Starting a new persistent thread inside the daemon
# process to fix that would be a process-lifecycle change requiring a
# mandatory code-reviewer pass under CLAUDE.md rule 4; calling a plain
# function directly from the watchdog tick that already exists (and already
# runs every 30s) avoids that question entirely, so that's what this does.
#
# Module-level (not a class instance) to match this module's existing
# process-global posture (residency state store, KNOWN_MODEL_ARCHS, etc.) —
# there is exactly one daemon process per device, and /status (a separate,
# short-lived CLI process) never shares this history with it (see
# `get_current_cpu_percent()`'s cold-start fallback for that case).

_cpu_prev_idle: int = 0
_cpu_prev_total: int = 0
_cpu_seeded: bool = False
_cpu_history: List[Tuple[float, float]] = []

# How long a sample stays in _cpu_history before being pruned. 30 minutes
# comfortably covers 7.4 sub-task D's stated 20-minute sustained-CPU
# tripwire window with margin, without keeping this list growing forever
# (60 samples/hour at the daemon's 30s tick rate).
CPU_HISTORY_MAX_AGE_SEC = 30 * 60


def _read_proc_stat_cpu_line(path: str = "/proc/stat") -> Tuple[int, int]:
    """
    Read the aggregate `cpu` line of `/proc/stat` and return (idle, total)
    tick counts — the same two fields core/sysmon.py's `_read_cpu_proc()`
    computes deltas from. Kept as its own function (mockable via `path`)
    for the same reason `read_meminfo()` takes a `path` argument.
    """
    with open(path, "r") as f:
        fields = list(map(int, f.readline().split()[1:]))
    idle = fields[3] + (fields[4] if len(fields) > 4 else 0)
    total = sum(fields)
    return idle, total


def sample_cpu_percent(path: str = "/proc/stat") -> Optional[float]:
    """
    Take one rolling CPU% sample and append it to `_cpu_history`, returning
    the sampled value, or None if unmeasurable (unreadable `/proc/stat`, or
    this is the very first call in the process — see below). Meant to be
    called once per daemon watchdog tick (~30s apart) — at that interval the
    delta is always large enough that core/sysmon.py's own "delta too small,
    do a mini 250ms re-sample" correction isn't needed here (unlike sysmon's
    2s-interval background thread, which does need it).

    None (not 0.0) is returned both when the read itself fails AND on the
    very first call in a process, which only seeds the previous-tick
    idle/total counters (nothing to diff against yet) — no history entry is
    recorded for either case. 0.0 would be wrong in the dangerous direction
    here: it's indistinguishable from a genuinely idle reading, but actually
    means "couldn't measure" — a caller (e.g. a future >90%-CPU shutdown
    tripwire) must not read either case as "device is idle."
    """
    global _cpu_prev_idle, _cpu_prev_total, _cpu_seeded
    try:
        idle, total = _read_proc_stat_cpu_line(path)
    except Exception as e:
        warning(f"resource_gate: CPU sample read failed, treating as unavailable: {e}")
        return None

    if not _cpu_seeded:
        _cpu_prev_idle, _cpu_prev_total = idle, total
        _cpu_seeded = True
        return None

    d_idle = idle - _cpu_prev_idle
    d_total = total - _cpu_prev_total
    _cpu_prev_idle, _cpu_prev_total = idle, total

    pct = 0.0 if d_total <= 0 else max(0.0, min(100.0, 100.0 * (1.0 - d_idle / d_total)))
    _cpu_history.append((time.time(), pct))
    cutoff = time.time() - CPU_HISTORY_MAX_AGE_SEC
    _cpu_history[:] = [(t, p) for t, p in _cpu_history if t >= cutoff]
    return pct


def get_cpu_history(max_age_sec: Optional[float] = None) -> List[Tuple[float, float]]:
    """
    Return `(timestamp, cpu_percent)` samples recorded by `sample_cpu_percent()`,
    most-recent last. Timestamps are kept (not just the values) so a future
    consumer (7.4 sub-task D) can check that a run of high readings actually
    *spans* its required duration, rather than just counting samples — a
    freshly-started daemon with only one or two ticks under a high-CPU
    reading must not look identical to a genuinely sustained condition.

    `max_age_sec`, if given, filters to samples newer than `now - max_age_sec`
    (in addition to the unconditional `CPU_HISTORY_MAX_AGE_SEC` pruning
    `sample_cpu_percent()` already applies on every call).
    """
    if max_age_sec is None:
        return list(_cpu_history)
    cutoff = time.time() - max_age_sec
    return [(t, p) for t, p in _cpu_history if t >= cutoff]


def get_current_cpu_percent(cold_start_sample_sec: float = 0.25) -> Optional[float]:
    """
    Best available "current" CPU% reading: the most recent rolling-sampler
    value if this process has already been ticking `sample_cpu_percent()`
    (true for the daemon, which calls it every 30s watchdog tick), otherwise
    a self-contained cold-start sample. Returns None if unmeasurable
    (unreadable `/proc/stat`) — see `sample_cpu_percent()`'s docstring for
    why None, not 0.0, is the correct "couldn't measure" sentinel here.

    This distinction matters because `_cpu_history`/`_cpu_prev_*` are
    process-global: a short-lived process that never called
    `sample_cpu_percent()` before (e.g. the `--status` CLI command, which
    runs in its own separate process from the daemon) would otherwise only
    ever see an empty history or a meaningless first-call reading. The
    cold-start path mirrors core/sysmon.py's own `_read_cpu_proc()`
    "delta too small -> take a fresh mini-sleep sample" trick so a one-shot
    caller still gets a real reading instead of a fabricated default.
    """
    history = get_cpu_history()
    if history:
        return history[-1][1]
    try:
        idle1, total1 = _read_proc_stat_cpu_line()
        time.sleep(cold_start_sample_sec)
        idle2, total2 = _read_proc_stat_cpu_line()
    except Exception as e:
        warning(f"resource_gate: cold-start CPU sample failed, treating as unavailable: {e}")
        return None
    d_idle = idle2 - idle1
    d_total = total2 - total1
    return 0.0 if d_total <= 0 else max(0.0, min(100.0, 100.0 * (1.0 - d_idle / d_total)))


def reset_cpu_sampler() -> None:
    """
    Reset the rolling CPU sampler's process-global state (seed flag,
    previous-tick counters, and history). Test-only convenience, same
    precedent as `core/thermal.py`'s `reset_thermal()` /
    `core/state.py`'s `reset_state_store()` — without this, ordered test
    runs would leak sampler state (in particular, prior history entries and
    the seeded previous-tick counters) between tests that otherwise use
    disjoint fixtures.
    """
    global _cpu_prev_idle, _cpu_prev_total, _cpu_seeded
    _cpu_prev_idle = 0
    _cpu_prev_total = 0
    _cpu_seeded = False
    _cpu_history.clear()


# ── Signal source 4: rolling thermal history (7.4 sub-task D) ───────────────
# Mirrors the CPU sampler immediately above exactly (module-level rolling
# history, "None on read failure, never a fabricated cool value" sentinel
# contract) — built for should_trip_shutdown()'s sustained-window check,
# same reason get_cpu_history() carries timestamps rather than just values.
#
# UNLIKE _cpu_history (which, per NEW-108, stays permanently EMPTY on this
# device because /proc/stat is permission-denied here — see
# sample_cpu_percent()'s docstring), read_current_temp_c() is already a
# live, working signal on this device today. This history WILL actually
# accumulate real samples here. State this explicitly so a future reader
# does not conclude the CPU leg of should_trip_shutdown() "just hasn't
# tripped yet" the way this thermal history has — it structurally cannot
# populate on this hardware, full stop, not a timing accident.

_temp_history: List[Tuple[float, float]] = []


def _temp_history_max_age_sec() -> float:
    """
    How long a sample stays in `_temp_history` before being pruned by
    `sample_temperature_c()`. Deliberately NOT a fixed module constant like
    CPU_HISTORY_MAX_AGE_SEC — it's derived from
    THERMAL_CONFIG["shutdown_trip_after_sec"] (read lazily, so it always
    reflects any live CODEY_SHUTDOWN_TRIP_AFTER_SEC override) so this
    pruning window can never be shorter than the tripwire's own configured
    duration. Without this, an env-var override that RAISES the duration
    (or a future committed default increase) could silently prune away the
    exact history should_trip_shutdown()'s sustained-window check needs,
    turning the tripwire into a permanent no-op with no error anywhere.
    Floors at 30 minutes (matching CPU_HISTORY_MAX_AGE_SEC's own margin
    reasoning) so a drastically-shortened live-test duration doesn't shrink
    the retained history to something impractically small either.
    """
    from utils.config import THERMAL_CONFIG

    duration = THERMAL_CONFIG.get("shutdown_trip_after_sec", 1200)
    return max(CPU_HISTORY_MAX_AGE_SEC, duration * 1.5)


def sample_temperature_c(read_temp_fn=None) -> Optional[float]:
    """
    Take one rolling temperature sample and append it to `_temp_history`,
    returning the sampled value, or None if unreadable. Meant to be called
    once per daemon watchdog tick (~30s apart), same cadence as
    `sample_cpu_percent()`.

    `read_temp_fn` defaults to this module's `read_current_temp_c` (a live
    thermal read) if not supplied — same injectable-callable convention as
    `get_resource_snapshot()`'s own `read_temp_fn` parameter, so tests never
    need to touch real hardware or monkeypatch a module-level name.

    None (not some fabricated "cool" value like 0.0) is returned on a read
    failure, and no history entry is recorded for it — same sentinel
    contract as `sample_cpu_percent()`'s own docstring explains: a caller
    (`should_trip_shutdown()`) must not read a failed read as "confirmed
    cool" any more than a failed CPU read should look like "confirmed
    idle."
    """
    if read_temp_fn is None:
        read_temp_fn = read_current_temp_c
    try:
        temp = read_temp_fn()
    except Exception as e:
        warning(f"resource_gate: temperature sample read failed, treating as unavailable: {e}")
        return None
    if temp is None:
        return None
    _temp_history.append((time.time(), temp))
    cutoff = time.time() - _temp_history_max_age_sec()
    _temp_history[:] = [(t, v) for t, v in _temp_history if t >= cutoff]
    return temp


def get_temp_history(max_age_sec: Optional[float] = None) -> List[Tuple[float, float]]:
    """
    Return `(timestamp, temperature_c)` samples recorded by
    `sample_temperature_c()`, most-recent last. Mirrors `get_cpu_history()`
    exactly — see its docstring for why timestamps (not just values) are
    kept.

    `max_age_sec`, if given, filters to samples newer than `now - max_age_sec`
    (in addition to the unconditional pruning `sample_temperature_c()`
    already applies on every call, via `_temp_history_max_age_sec()`).
    """
    if max_age_sec is None:
        return list(_temp_history)
    cutoff = time.time() - max_age_sec
    return [(t, v) for t, v in _temp_history if t >= cutoff]


def reset_temp_sampler() -> None:
    """
    Reset the rolling thermal sampler's process-global history. Test-only
    convenience, same precedent as `reset_cpu_sampler()` immediately above.
    """
    _temp_history.clear()


# ── Snapshot composer ────────────────────────────────────────────────────────
# "Single resource-gate authority" (per this module's own module docstring
# and WORK_QUEUE.md's Phase 1 framing): composes every live signal this
# sub-task adds (rolling CPU%, RAM headroom, temperature, queue depth,
# battery) into one object, here rather than duplicated into
# core/observability.py. Not wired into any admission/gating decision by
# this sub-task — that's 7.4 sub-task C's job; this is signal-sourcing only.


@dataclass(frozen=True)
class ResourceSnapshot:
    cpu_percent: Optional[float]
    ram_headroom_bytes: int
    ram_total_bytes: int
    temperature_c: Optional[float]
    queue_pending: int
    queue_running: int
    battery_percent: Optional[int]
    battery_charging: bool
    timestamp: float
    # TODO.md 7.4a sub-task A — swap-awareness signal fields, additive only.
    # swap_total_bytes/swap_free_bytes come straight from read_meminfo()'s
    # existing SwapTotal/SwapFree parsing (already present, zero new
    # plumbing); zram_compression_ratio comes from read_zram_stats() +
    # compute_zram_compression_ratio() (None if unavailable — see those
    # functions' own docstrings for why). Defaulted so every existing
    # keyword-constructed ResourceSnapshot in this module/its tests stays
    # valid unchanged. No admission/dispatch logic reads these yet (that's
    # 7.4a sub-task C2, out of scope here) — this sub-task only makes the
    # signal visible on the snapshot.
    swap_total_bytes: int = 0
    swap_free_bytes: int = 0
    zram_compression_ratio: Optional[float] = None


def _default_read_battery_fn() -> Tuple[Optional[int], bool]:
    """
    Lazy-imports core.sysmon so importing core.resource_gate never pulls in
    `rich` (core/sysmon.py's only import-time dependency beyond the
    standard library) — matches this module's existing "import-safe, no
    surprise dependencies" posture for `read_current_temp_c()`.
    """
    from core.sysmon import read_battery_status

    return read_battery_status()


def get_resource_snapshot(
    meminfo: Optional[Dict[str, int]] = None,
    read_temp_fn=None,
    read_battery_fn=None,
    state_store=None,
    cpu_percent: Optional[float] = None,
    read_zram_fn=None,
) -> ResourceSnapshot:
    """
    Compose the current CPU%, RAM headroom, temperature, queue depth,
    battery state, and swap/zram state into one `ResourceSnapshot`.

    Every signal is independently injectable/overridable so tests never
    need to depend on this device's real live state (matching this module's
    existing test convention — see tests/test_resource_gate.py's module
    docstring): `meminfo` a synthetic dict, `read_temp_fn`/`read_battery_fn`/
    `read_zram_fn` stub callables, `state_store` a fake object exposing
    `get_tasks_by_status(status) -> list`, `cpu_percent` a fixed float (or
    None, matching `get_current_cpu_percent()`'s own "unmeasurable" case —
    see its docstring for why None, not 0.0, is used).

    `read_battery_fn` defaults to `core.sysmon.read_battery_status()`, whose
    fallback path (confirmed live on this device — the
    `/sys/class/power_supply/battery/` sysfs path is permission-denied
    under Termux without root) shells out to `termux-battery-status` with a
    2s timeout. That's fine for this sub-task's own use (a one-shot
    `--status` CLI read), but a future caller invoking this composer from a
    hot, frequently-ticking loop (e.g. 7.4 sub-task C's per-task-dispatch
    check, which runs far more often than this module's own 30s CPU tick)
    should pass a `read_battery_fn` that reads a value cached/refreshed on
    a slower cadence instead of taking the default here directly — this
    function does not itself add any such caching.

    Each signal's read is independently wrapped so one failing signal
    (e.g. no thermal zone on a non-Android host, a corrupt state DB) can't
    blank out the others — same best-effort posture as this module's
    existing `can_admit()`/`reserve_slot()` thermal-read handling.
    """
    if meminfo is None:
        meminfo = read_meminfo()
    if read_temp_fn is None:
        read_temp_fn = read_current_temp_c
    if read_battery_fn is None:
        read_battery_fn = _default_read_battery_fn
    if read_zram_fn is None:
        read_zram_fn = read_zram_stats
    if state_store is None:
        from core.state import get_state_store

        state_store = get_state_store()
    if cpu_percent is None:
        cpu_percent = get_current_cpu_percent()

    try:
        temperature_c = read_temp_fn()
    except Exception as e:
        warning(f"resource_gate: snapshot thermal read failed, treating as unavailable: {e}")
        temperature_c = None

    try:
        battery_percent, battery_charging = read_battery_fn()
    except Exception as e:
        warning(f"resource_gate: snapshot battery read failed, treating as unavailable: {e}")
        battery_percent, battery_charging = None, False

    try:
        queue_pending = len(state_store.get_tasks_by_status("pending"))
        queue_running = len(state_store.get_tasks_by_status("running"))
    except Exception as e:
        warning(f"resource_gate: snapshot queue-depth read failed, treating as unavailable: {e}")
        queue_pending, queue_running = 0, 0

    try:
        zram_stats = read_zram_fn()
    except Exception as e:
        # Same best-effort posture as the thermal/battery/queue reads just
        # above — read_zram_stats() itself already fails soft (returns None
        # rather than raising), but an injected read_zram_fn in a test could
        # still raise, so this stays consistent with every other signal in
        # this composer.
        warning(f"resource_gate: snapshot zram read failed, treating as unavailable: {e}")
        zram_stats = None

    return ResourceSnapshot(
        cpu_percent=cpu_percent,
        ram_headroom_bytes=compute_headroom_bytes(meminfo),
        ram_total_bytes=meminfo.get("MemTotal", 0),
        temperature_c=temperature_c,
        queue_pending=queue_pending,
        queue_running=queue_running,
        battery_percent=battery_percent,
        battery_charging=battery_charging,
        timestamp=time.time(),
        swap_total_bytes=meminfo.get("SwapTotal", 0),
        swap_free_bytes=meminfo.get("SwapFree", 0),
        zram_compression_ratio=compute_zram_compression_ratio(zram_stats),
    )


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
    Minimal architecture parameters needed to estimate a model's resident
    memory cost. Values come from each model family's published config
    (Qwen2.5 architecture docs) for QWEN25_7B_ARCH/QWEN25_1_5B_ARCH.
    QWEN35_4B_ARCH and QWEN3_4B_TEST_ARCH (below) instead come from
    reading each real GGUF file's own header metadata
    directly on-device (see each constant's own comment for the exact fields
    read). No provenance parses the GGUF file at estimate time — this
    dataclass stays narrowly scoped to what this gate needs, not a general
    GGUF-metadata reader.

    Not every model is a uniform stack of attention layers. Qwen3.5-4B is a
    hybrid Transformer-SSM model: only some of its blocks keep a KV cache
    that grows with context, and the rest carry a fixed-size recurrent
    state. `n_attention_layers` and `recurrent_state_bytes` exist for that
    case and default to "conventional model" values, so every previously
    declared arch keeps its exact prior cost.

    One limitation worth knowing: `head_dim` is a single number, so this
    dataclass silently assumes a model's key and value dimensions are
    equal. That holds for every arch declared below, but the evidence
    differs by family and it is worth knowing which you have: the qwen3
    and qwen35 GGUFs declare `attention.key_length` and
    `attention.value_length` explicitly, and both were checked equal. The
    three qwen2 GGUFs (7B, 1.5B, and the 0.5B planner substitute) carry
    neither key — llama.cpp derives head_dim there as
    `embedding_length / attention.head_count`, one value used for both, so
    they are symmetric by construction rather than by inspection. Nothing
    here would catch an asymmetric model: before adding one, check
    `<arch>.attention.key_length` against `value_length` if it declares
    them, and read the family's head_dim derivation if it does not.
    """

    n_layers: int
    n_kv_heads: int
    head_dim: int
    # Number of layers that actually keep a growing KV cache. None (the
    # default) means "all of them", i.e. n_layers — the conventional case.
    # Set explicitly only for hybrid models where the two differ; see
    # QWEN35_4B_ARCH.
    n_attention_layers: Optional[int] = None
    # Context-INDEPENDENT recurrent/SSM state, in bytes, for models that
    # carry one. 0 for a conventional transformer. Deliberately a flat byte
    # count rather than a formula: it does not scale with n_ctx, so there is
    # nothing for this gate to compute per admission.
    recurrent_state_bytes: int = 0
    # KV cache element size in bytes. MODEL_CONFIG["kv_type"] = "q4_0" in
    # utils/config.py suggests 4-bit KV, but that key is never actually
    # passed to `llama-server` in core/loader_v2.py's _spawn_locked() command
    # list (checked directly while building this module) — so the server
    # really runs with its default fp16 (2-byte) KV cache. Defaulting to 2
    # here matches real observed behavior, not the aspirational config value;
    # NEW_ISSUES.md gets a separate entry for the dead "kv_type" config key
    # (out of scope for this sub-task — signal sourcing/estimation only).
    kv_bytes_per_element: int = 2


# The two retired models (CODEY_MASTER_PLAN.md §1.4, 2026-08-22). No entry
# in KNOWN_MODEL_ARCHS points at either one any more; they are kept as
# declared constants because the NEW-84 regression tests and this module's
# own derivation comments reference them by name, and because M1-D has not
# yet removed the last of the retired-model code paths. Do not re-point a
# role at them.

# Qwen2.5-Coder-7B-Instruct: hidden_size=3584, num_hidden_layers=28,
# num_attention_heads=28, num_key_value_heads=4 (GQA), head_dim=128.
QWEN25_7B_ARCH = ModelArch(n_layers=28, n_kv_heads=4, head_dim=128)

# Qwen2.5-Coder-1.5B-Instruct: hidden_size=1536, num_hidden_layers=28,
# num_attention_heads=12, num_key_value_heads=2 (GQA), head_dim=128.
QWEN25_1_5B_ARCH = ModelArch(n_layers=28, n_kv_heads=2, head_dim=128)

# Qwen3.5-4B-Instruct (~/models/qwen3.5-4b-instruct/Qwen3.5-4B-Q4_K_M.gguf,
# 2,740,937,888 bytes) — the single default model for every role as of the
# 2026-08-22 one-model decision (CODEY_MASTER_PLAN.md §1.4).
#
# THIS IS A HYBRID TRANSFORMER-SSM MODEL, NOT A CONVENTIONAL ONE. Read
# directly from the GGUF header on-device (full 46-key dump, not a filtered
# grep — rule 14): general.architecture=qwen35, qwen35.block_count=32,
# qwen35.full_attention_interval=4. 32/4 = 8 full-attention layers; the
# other 24 are SSM/linear layers whose state does NOT grow with context. So
# n_attention_layers=8 while n_layers stays 32 — the numbers disagree on
# purpose, and "correcting" n_attention_layers to 32 would over-estimate
# this model's KV cache by 4x and wrongly refuse an n_ctx the device can
# actually afford (NEW-157).
#
# The attention fields are qwen35.attention.head_count_kv=4 and
# qwen35.attention.key_length=256. head_dim=256 is only valid here because
# qwen35.attention.value_length is ALSO 256 — ModelArch has one head_dim
# field and would not catch a model where they differ.
#
# recurrent_state_bytes is the 24 SSM layers' fixed state. It is derived
# from llama.cpp's own allocation code, read on-device at ~/llama.cpp
# (commit 91d2fc38) — NOT from the GGUF's ssm.* fields interpreted by
# analogy with Mamba, which is how an earlier version of this constant got
# it wrong in both of the ways its own comment warned about:
#
#   llama-hparams.cpp:204 (n_embd_r, the conv state) —
#       (ssm_d_conv - 1) * (ssm_d_inner + 2 * ssm_n_group * ssm_d_state)
#     = 3 * (4096 + 2 * 16 * 128) = 24,576 per layer.
#     Note ssm_n_group: qwen35.ssm.group_count=16 enters here. Omitting it
#     halves this term, which is the mistake that was caught in review.
#   llama-hparams.cpp:220 (n_embd_s, the SSM state) —
#       ssm_d_state * ssm_d_inner = 128 * 4096 = 524,288 per layer.
#   llama-model.cpp:2153-2155 — qwen35 passes recurrent_type_k and
#     recurrent_type_v as GGML_TYPE_F32. The elements are 4 bytes, NOT the
#     2-byte fp16 the KV cache uses. Do not assume this follows
#     kv_bytes_per_element; it does not.
#
# So: ((4 - 1) * (4096 + 2 * 16 * 128) + 128 * 4096) * 4 * 24
#   = 52,690,944 bytes (50.25MiB).
#
# This is now SOURCE-DERIVED BUT STILL NOT MEASURED. Reading the allocator
# is stronger evidence than the formula it replaced, but M1-E keeps its
# measurement task — real resident cost is what settles it.
#
# One caveat that is NOT obvious: llama.cpp allocates recurrent state PER
# SEQUENCE SLOT (llama-memory-recurrent.cpp:100-101, n_rows =
# max(1, n_seq_max)), so this figure is for a single slot — llama-server's
# default. It scales with n_seq_max / --parallel: negligible at one slot,
# not negligible at eight, and the concurrency work in §6.2 is about to
# start setting that flag.
QWEN35_4B_ARCH = ModelArch(
    n_layers=32,
    n_kv_heads=4,
    head_dim=256,
    n_attention_layers=8,
    recurrent_state_bytes=((4 - 1) * (4096 + 2 * 16 * 128) + 128 * 4096) * 4 * 24,
)

# Keyed by ModelSpec.model_id, NOT by the model's file path. This dict used
# to be keyed by str(MODEL_PATH)/str(PLANNER_MODEL_PATH) — both bound once
# at this module's import time — which meant a hot-swap to a fine-tuned
# model (core/lora_import.py's swap_to_finetuned_model(), which mutates
# utils.config.MODEL_PATH/PLANNER_MODEL_PATH on the live module object, not
# this frozen import-time snapshot) silently missed the lookup after the
# swap and dropped the KV-cache cost term to 0 in the gate's admission math
# (NEW_ISSUES.md NEW-84 addendum — an admission-safety bug: an
# underestimated cost could let the gate over-admit a load it would
# otherwise correctly reject). core/loader_v2.py always passes a fixed
# model_id of "primary" regardless of which file is actually being loaded
# (see its rg.ModelSpec(...) call site) — a LoRA-merged model keeps the same
# architecture (n_layers/n_kv_heads/head_dim) as its base, so keying on the
# stable role identifier instead of the mutable path is both correct and
# swap-proof.
#
# M1-D (2026-08-23): a "planner" entry used to sit here too, for
# core/planner_loader.py's ModelSpec(model_id="planner", ...) reservations.
# That module (and the dedicated planner process it managed) is deleted —
# nothing in this codebase calls reserve_slot()/estimate_model_load_cost()
# with model_id="planner" anymore, so the entry is removed, not left as
# dead-but-harmless data. "primary" is the only role this gate resolves an
# architecture for today.
KNOWN_MODEL_ARCHS: Dict[str, ModelArch] = {
    "primary": QWEN35_4B_ARCH,
}

# ── Test-only architecture substitute (Qwen3-4B) ────────────────────────────
# This constant exists ONLY to support a documented, deliberate live-test
# session (Ish swapping in a smaller model via utils/config.py's existing
# CODEY_MODEL env-var override, for RAM-safe on-device gate/loader/daemon
# verification) — never for any non-test purpose. It is NOT added to
# KNOWN_MODEL_ARCHS's committed default entries, and by itself does nothing:
# see CODEY_TEST_PRIMARY_ARCH below for the only mechanism that activates
# it, and note its own "unset means byte-for-byte unchanged" contract.
#
# M1-D (2026-08-23): a matching QWEN25_0_5B_PLANNER_ARCH / "planner"-role
# entry in the registry below (and the CODEY_TEST_PLANNER_ARCH env var that
# activated it) is removed along with core/planner_loader.py — nothing ever
# reserves a slot with model_id="planner" anymore, so that whole per-role
# substitution path is dead, not just unused. Only the "primary" role
# remains, so the per-role registry below is retained for its
# typo-safety/enumerable-error property (see its own comment), not because
# a second role still exists.
#
# Value below was read directly from the real GGUF file's own header
# metadata on this device (not published specs, not guessed) — see the task
# that added this section for the exact `gguf`/metadata dump this was
# extracted from.

# Qwen3-4B-Instruct-2507 (~/models/qwen3-4b-instruct/
# Qwen3-4B-Instruct-2507-Q4_K_M.gguf). GGUF header: qwen3.block_count=36,
# qwen3.attention.head_count_kv=8, qwen3.attention.key_length=128.
#
# NAMED *_TEST_ARCH ON PURPOSE (renamed from QWEN3_4B_ARCH, 2026-08-22).
# This is the OLDER Qwen3-4B — general.architecture=qwen3, 36 conventional
# all-attention layers — and is NOT the qwen35 default above. The two names
# were one character apart while describing different architectures, which
# is exactly the confusable-name trap rule 14 exists for. Kept rather than
# deleted because it is still wired into _TEST_ARCH_REGISTRY_BY_ROLE, still
# load-bearing for the CODEY_TEST_PRIMARY_ARCH live-test contract, and the
# model file is still on disk.
QWEN3_4B_TEST_ARCH = ModelArch(n_layers=36, n_kv_heads=8, head_dim=128)

# String keys accepted by CODEY_TEST_PRIMARY_ARCH below, mapped to the
# constant above. A small registry (rather than accepting a raw
# "n_layers,n_kv_heads,head_dim" triple) so a typo produces a loud,
# enumerable error instead of a silently-plausible wrong triple — see
# _resolve_model_arch()'s use of this dict.
#
# Deliberately PER-ROLE (a registry keyed by model_id) even though only one
# role remains post-M1-D — see this dict's own comment before M1-D removed
# the "planner" entry for the cross-role-substitution risk this structure
# was built to close, which still applies to any future second role added
# here.
_TEST_ARCH_REGISTRY_BY_ROLE: Dict[str, Dict[str, ModelArch]] = {
    "primary": {"qwen3-4b": QWEN3_4B_TEST_ARCH},
}

# Env var read LAZILY (inside _resolve_model_arch(), not at module import)
# so: (1) a test process can set/unset it per-test without needing
# importlib.reload (which would rebind this module's ModelArch constants and
# break identity checks elsewhere, e.g.
# tests/test_resource_gate.py::test_known_model_archs_resolved_by_path's `is`
# assertion); (2) the override can never outlive the env var — unset always
# means immediately, byte-for-byte back to today's KNOWN_MODEL_ARCHS lookup,
# with no risk of a stale in-process cache silently persisting an override
# into what's meant to be a normal production run.
#
# Scoped to model_id "primary" ONLY, and only consulted AFTER the existing
# `spec.arch is not None` explicit-override check in _resolve_model_arch() —
# a caller (or test) that explicitly passes `arch=` always wins; this env
# var must never silently preempt an explicit, already-correct caller
# declaration. Precedence, in order: explicit `spec.arch` > this env-var
# test override > KNOWN_MODEL_ARCHS default.
CODEY_TEST_PRIMARY_ARCH_ENV = "CODEY_TEST_PRIMARY_ARCH"

_TEST_ARCH_ENV_BY_MODEL_ID = {
    "primary": CODEY_TEST_PRIMARY_ARCH_ENV,
}


def _resolve_test_arch_override(model_id: str) -> Optional[ModelArch]:
    """
    Return the env-var-selected test-only architecture override for
    `model_id` ("primary" only), or None if no applicable env var is set or
    the env var is set to the empty string (treated as unset, matching this
    project's `os.environ.get(NAME, default)` convention elsewhere — e.g.
    utils/config.py's CODEY_MODEL override — where an empty value is not a
    meaningful distinct case worth its own error). Raises ValueError (loud,
    not a silent bad fallback) if the env var is set to a non-empty value
    not present in that role's entry in _TEST_ARCH_REGISTRY_BY_ROLE — this
    gate's entire purpose is preventing an under-estimated cost from
    silently admitting a load it shouldn't, so a typo'd override value must
    fail admission outright rather than quietly falling back to the wrong
    architecture (or to "no architecture", which would silently zero the KV
    term — see estimate_model_load_cost()'s unknown-arch branch).
    """
    env_name = _TEST_ARCH_ENV_BY_MODEL_ID.get(model_id)
    if env_name is None:
        return None
    raw = os.environ.get(env_name)
    if not raw:
        return None
    role_registry = _TEST_ARCH_REGISTRY_BY_ROLE.get(model_id, {})
    try:
        return role_registry[raw]
    except KeyError:
        raise ValueError(
            f"{env_name}={raw!r} is not a recognized test architecture override "
            f"for model_id {model_id!r}; valid values: {sorted(role_registry)}"
        ) from None


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
    omitted, it's read from `path.stat().st_size` at estimate time. Arch
    resolution (see `_resolve_model_arch()`) checks, in order: explicit
    `arch` on this spec, then (for `model_id` "primary" only) the
    CODEY_TEST_PRIMARY_ARCH test-only env-var
    override (see that section's header comment in this module — unset by
    default, never active in a normal run), then `KNOWN_MODEL_ARCHS`. If none
    of those resolve, the KV cache term is estimated as 0 and a warning is
    logged — the cost estimate degrades to "weights + overhead only", which
    is a known-incomplete (not silently-wrong-in-the-safe-direction) estimate
    for unknown model families; callers passing genuinely unknown models
    should supply `arch` explicitly wherever possible.
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
    """
    The breakdown behind one admission decision, kept as separate terms so
    a total that looks wrong can be audited against the model's own
    arithmetic rather than re-derived. `recurrent_state_bytes` defaults to 0
    and is non-zero only for hybrid/SSM models (see ModelArch); it is
    context-independent, unlike kv_cache_bytes.
    """

    model_bytes: int
    kv_cache_bytes: int
    overhead_bytes: int
    recurrent_state_bytes: int = 0

    @property
    def total_bytes(self) -> int:
        return (
            self.model_bytes
            + self.kv_cache_bytes
            + self.overhead_bytes
            + self.recurrent_state_bytes
        )


def estimate_kv_cache_bytes(arch: ModelArch, n_ctx: int) -> int:
    """
    KV cache size = attention_layers * 2 (K and V) * n_kv_heads * head_dim *
    n_ctx * bytes_per_element. Standard formula for GQA/MQA transformer KV
    cache; matches llama.cpp's own KV cache allocation shape.

    `attention_layers` is arch.n_attention_layers when set, else n_layers.
    Only layers that actually attend keep a growing cache — on a hybrid
    model like Qwen3.5-4B (8 of 32) using n_layers here would over-estimate
    by 4x (NEW-157). The `is not None` test is deliberate: `or` would treat
    a legitimate 0 as unset. Layers that don't attend are not free, but
    their cost is fixed rather than context-scaled and is carried by
    arch.recurrent_state_bytes instead, in estimate_model_load_cost().
    """
    attention_layers = (
        arch.n_attention_layers if arch.n_attention_layers is not None else arch.n_layers
    )
    return (
        attention_layers
        * 2
        * arch.n_kv_heads
        * arch.head_dim
        * n_ctx
        * arch.kv_bytes_per_element
    )


def _resolve_model_arch(spec: ModelSpec) -> Optional[ModelArch]:
    """
    Precedence, in order: explicit `spec.arch` > CODEY_TEST_PRIMARY_ARCH
    env-var test override (see that section's header comment above) >
    KNOWN_MODEL_ARCHS default. The env-var check can raise
    ValueError if set to an unrecognized value — deliberately not caught
    here; see _resolve_test_arch_override()'s docstring for why a bad
    override must fail loudly rather than silently falling back.
    """
    if spec.arch is not None:
        return spec.arch
    override = _resolve_test_arch_override(spec.model_id)
    if override is not None:
        return override
    if spec.model_id in KNOWN_MODEL_ARCHS:
        return KNOWN_MODEL_ARCHS[spec.model_id]
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
        # Context-independent, and 0 for every conventional model — see
        # ModelArch.recurrent_state_bytes. Kept as its own term rather than
        # folded into the KV or overhead terms so the KV number stays
        # directly auditable against CODEY_MASTER_PLAN.md §5.1's table.
        recurrent_bytes = arch.recurrent_state_bytes
    else:
        warning(
            f"resource_gate: no known architecture for model {spec.model_id!r}; "
            "KV cache term omitted from cost estimate (weights + overhead only)"
        )
        kv_bytes = 0
        recurrent_bytes = 0

    return CostEstimate(
        model_bytes=model_bytes,
        kv_cache_bytes=kv_bytes,
        overhead_bytes=spec.compute_overhead_bytes,
        recurrent_state_bytes=recurrent_bytes,
    )


# ── Admission decision ───────────────────────────────────────────────────────

# TODO.md 7.4a sub-task C1 (Ish's direct decision, 2026-08-11). A new,
# additional, NAMED ceiling — distinct from both the per-model hard-reject
# ceiling (compute_device_ceiling_bytes(), MemTotal-only, unchanged/untouched
# by this constant) and the live MemAvailable-based headroom check
# (compute_headroom_bytes()/REQUIRED_HEADROOM_FACTOR): a fixed cap on the
# SUM of every concurrently-declared model cost this gate's own state store
# knows about (see total_committed_bytes() below), checked unconditionally
# BEFORE any live-memory read is even consulted — Ish's own framing: "make
# sure the device's own policy is shown to Codey so it never even tries to
# load a model above that number." This is NOT the "fixed concurrency
# ceiling" the 2026-08-08 amendment explicitly rejects (a "max N models"
# rule) — it caps total declared BYTES, not model count, and coexists with
# the amendment's live-headroom-based admission math rather than replacing
# it.
#
# Derivation (real numbers, computed live via this project's own
# estimate_model_load_cost() against the real on-disk 7B/1.5B/embed model
# files at n_ctx=32768, on this device's ~10.8GiB MemTotal — NOT a guess):
#   7B (primary) at n_ctx=32768:    model=4.361GiB + kv=1.750GiB +
#                                    overhead=0.250GiB = 6.361GiB
#                                    (6,830,557,184 bytes exact)
#   1.5B (planner) at n_ctx=32768:  model=1.041GiB + kv=0.875GiB +
#                                    overhead=0.250GiB = 2.166GiB
#                                    (2,325,280,320 bytes exact)
#   embed model:                    file=0.078GiB, NO KV-cache term
#                                    computable (the embed model_id has no
#                                    entry in KNOWN_MODEL_ARCHS —
#                                    estimate_model_load_cost() cannot
#                                    compute a KV term for it) -> FLOOR
#                                    ESTIMATE only, ~0.328GiB
#                                    (352,563,303 bytes exact) = file +
#                                    DEFAULT_COMPUTE_OVERHEAD_BYTES. Also:
#                                    the embed server is hardcoded to
#                                    launch at -c 2048 in
#                                    core/embed_server.py, NOT n_ctx=32768
#                                    — the "embed at 32768" premise below
#                                    does not reflect what the code
#                                    actually does today; used anyway since
#                                    the embed model's contribution to the
#                                    total is small regardless. KNOWN,
#                                    ACCEPTED UNDERCOUNT — if a future
#                                    estimate_model_load_cost() change (or
#                                    sub-task E's live pass) measures the
#                                    embed model's real resident cost above
#                                    this floor by more than this
#                                    constant's ~45.7MiB margin (see below),
#                                    the three-model-concurrent case this
#                                    ceiling was built to admit could become
#                                    inadmissible again (NEW-133's exact
#                                    failure mode) — re-check this constant
#                                    against the real embed cost at that
#                                    point, don't assume the margin holds.
#   Raw sum: 6,830,557,184 + 2,325,280,320 + 352,563,303 = 9,508,400,807
#            bytes (~8.855GiB).
#
# NEW-133 (NEW_ISSUES.md): Ish's original session figure, 8.80GiB, was
# described as "raw sum minus ~0.06GiB, for a slight safety margin" but was
# arithmetically BELOW the 8.855GiB raw sum by ~0.055GiB — meaning the exact
# 3-model-concurrent case this ceiling was computed from would itself have
# been refused by a few tens of MiB, defeating the stated "never even tries
# to load a model above that number" intent (which reads as "the full
# 3-model case should be admissible," not "should be refused by design").
# Ish's direct answer, 2026-08-11: round UP instead, so the full 3-model
# case stays admissible, with any remaining margin-wanting applied
# elsewhere (sub-task C2's independently-derived, separately-calibrated
# MAX_SWAP_ASSIST_BYTES) rather than as a deduction on this ceiling — this
# is a declared-cost POLICY sum, not a live-RAM safety check (that's what
# compute_headroom_bytes() x REQUIRED_HEADROOM_FACTOR already does), so no
# deduction margin belongs on it at all.
#
# Corrected value: raw sum rounded UP to the next 0.05GiB = 8.90GiB
# (9,556,302,233 bytes), a positive margin of 47,901,426 bytes (~45.7MiB)
# ABOVE the raw sum, not a deduction below it.
#
# 8.90GiB / 10.8GiB (this device's MemTotal) ~= 0.82, well above
# DEVICE_CEILING_USABLE_FRACTION (0.60) — this is INTENTIONAL and must NOT
# be "reconciled" toward that other constant: they are two different
# concepts. compute_device_ceiling_bytes()/DEVICE_CEILING_USABLE_FRACTION
# answers "how much RAM may ONE model ever claim, absolute, regardless of
# anything else" (a per-model physical ceiling). This constant answers "what
# is the fixed cap on the SUM of ALL concurrently-declared model costs" (a
# multi-model budget). A single model's cost can legally be well under 0.60
# * MemTotal while the SUM of several concurrently-declared models
# approaches 0.82 * MemTotal — both checks are meant to bind independently.
#
# Device-derived from THIS device's real on-disk model files at n_ctx=32768
# on ~10.8GiB MemTotal — MUST BE RECOMPUTED (via estimate_model_load_cost()
# against the real files on that device), not linearly scaled, if this code
# ever runs on different hardware.
#
# ── TODO.md 7.4b sub-task D revisit, 2026-08-11 (docs-only, VALUE UNCHANGED) ─
# Ish's 7.4b decision shrinks two of the three operands above: the planner's
# ceiling was utils.config.get_planner_n_ctx() (8192 by default, not
# 32768 — sub-task B; a function, not a constant, as of the NEW-102/bug_002
# fix — see utils/config.py). M1-D (2026-08-23, VALUE STILL UNCHANGED here,
# same as this whole section's own heading — re-deriving
# MAX_CONCURRENT_MODEL_BUDGET_BYTES itself is explicitly out of scope for
# that round, deferred to M1-F pending M1-E's real measurements) removed
# get_planner_n_ctx() along with the dedicated planner process it ceilinged
# — flagged here as a now-stale input to this historical derivation, not
# silently left implying the function still exists. And the coder's ceiling drops to
# utils.config.get_coder_background_n_ctx() (16384 by default, not 32768)
# for daemon-dispatched BACKGROUND tasks specifically —
# sub-task C — while staying at the full 32768 whenever a human is actively
# using it interactively (core.resource_gate.is_interactive_session_active()
# True). Always-on embed does NOT invalidate the derivation above: it
# already summed embed's cost as always-present, this decision just makes
# that assumption REALIZED in practice (see TODO.md 7.4b's own scoping).
#
# Recomputed (real numbers, via this project's own estimate_model_load_cost()
# against the real on-disk 7B/1.5B/embed files, same device):
#   Planner @ PLANNER_N_CTX=8192:        model=1.041GiB + kv=0.219GiB +
#                                         overhead=0.250GiB = 1.509GiB
#                                         (1,620,637,248 bytes exact)
#   Embed (unchanged, still -c 2048,
#          same KNOWN, ACCEPTED UNDERCOUNT
#          as above):                    0.328GiB (352,542,080 bytes exact)
#   Coder @ CODER_BACKGROUND_N_CTX=16384
#          (no interactive session):     model=4.361GiB + kv=0.875GiB +
#                                         overhead=0.250GiB = 5.486GiB
#                                         (5,891,033,088 bytes exact)
#   Coder @ full n_ctx=32768
#          (interactive session active): model=4.361GiB + kv=1.750GiB +
#                                         overhead=0.250GiB = 6.361GiB
#                                         (6,830,557,184 bytes exact,
#                                         identical to the original
#                                         derivation above — unchanged by
#                                         this decision)
#
#   New raw sum, BACKGROUND coder + planner + embed:
#     5,891,033,088 + 1,620,637,248 + 352,542,080 = 7,864,212,416 bytes
#     (~7.324GiB) — the realistic case any daemon-dispatched background
#     task now produces.
#   New raw sum, INTERACTIVE coder + planner + embed (the coder's ceiling
#     this decision does NOT shrink, so this is the larger of the two new
#     cases, and the one that must be checked against the existing
#     8.90GiB ceiling):
#     6,830,557,184 + 1,620,637,248 + 352,542,080 = 8,803,736,512 bytes
#     (~8.199GiB).
#
# Both new sums (7.324GiB background, 8.199GiB interactive) are BELOW the
# original 8.855GiB raw sum this constant's 8.90GiB was rounded up from,
# and both stay comfortably below 8.90GiB itself (margins of ~1.576GiB and
# ~0.701GiB respectively — MORE margin than before this decision, not
# less). **Conclusion at the time of this 2026-08-11 revisit:
# MAX_CONCURRENT_MODEL_BUDGET_BYTES stays 8.90GiB — no value change from
# this revisit.** That conclusion is now superseded by the M1-F
# re-derivation directly below, once the planner process itself was
# retired (§1.4/M1-D) rather than merely re-ceilinged.
#
# ── M1-F (2026-08-24): re-derived for the single-model architecture
# (`NEW-156`) ──────────────────────────────────────────────────────────────
# §1.4/M1-D retired the dedicated planner process entirely — Qwen3.5-4B is
# now the only local generation model, running in thinking mode instead of
# handing off to a second server. This constant's basis (3 concurrently-
# declared models: 7B + 1.5B + embed, then coder + planner + embed above)
# no longer exists; M1-E (2026-08-23) supplied the first real measured RSS
# for the new single model, which is what this re-derivation waited on
# (`NEW-133`'s lesson: never re-derive an admission ceiling from arithmetic
# alone before real measurement exists).
#
# Real numbers, computed live via estimate_model_load_cost() against the
# real on-disk primary/embed files on this device (2026-08-24 session):
#   Primary @ full n_ctx=65536 (interactive session active — the coder's
#   ceiling MODEL_CONFIG["n_ctx"] is NOT shrunk by an interactive session,
#   only a background-dispatched one is, per get_coder_background_n_ctx()):
#     model=2,740,937,888 + kv=2,147,483,648 (32,768 bytes/token x 65536,
#     the hybrid 8-attention-layer term, §5.1) + overhead=268,435,456 +
#     recurrent=52,690,944 (context-independent SSM state, one sequence
#     slot) = 5,209,547,936 bytes (4.8518GiB) — matches §5.1's table and
#     M1-A's own pinned unit-test total for this model exactly.
#   Primary @ CODER_BACKGROUND_N_CTX=16384 (no interactive session):
#     model=2,740,937,888 + kv=536,870,912 + overhead=268,435,456 +
#     recurrent=52,690,944 = 3,598,935,200 bytes (3.3518GiB).
#   Embed: UNCHANGED, same KNOWN, ACCEPTED UNDERCOUNT as every prior
#     derivation in this section — 352,542,080 bytes (0.328GiB), a floor
#     estimate (file size + DEFAULT_COMPUTE_OVERHEAD_BYTES only; the embed
#     model_id has no KNOWN_MODEL_ARCHS entry, so no KV term is computed for
#     it, and it still launches at -c 2048 per core/embed_server.py, not
#     whatever n_ctx this table's other rows use). **M1-E did not measure
#     real embed RSS** — checked this round, no such figure exists in this
#     project's live-test history yet — so this floor is still the only
#     available number; logged as a still-open gap below, same as every
#     prior revisit of this constant.
#
#   New raw sum, BACKGROUND primary + embed:
#     3,598,935,200 + 352,542,080 = 3,951,477,280 bytes (~3.680GiB).
#   New raw sum, INTERACTIVE primary + embed (the larger of the two cases,
#     per this constant's own established precedent of checking against
#     whichever is bigger — see the sub-task-D-revisit block above):
#     5,209,547,936 + 352,542,080 = 5,562,090,016 bytes (~5.1801GiB).
#
# **This constant has a SECOND floor, independent of the concurrent raw
# sum above, that this section's own prior revisits stated but never
# enforced with a test: MAX_CONCURRENT_MODEL_BUDGET_BYTES must stay >=
# compute_device_ceiling_bytes()`, or the budget check can refuse a SINGLE
# model that `hard_reject` would otherwise admit — inverting rule 12's
# "hard_reject is the absolute per-model bound" into "budget is the real
# bound, tighter than the documented physical one." The original 8.90GiB
# value's own comment observed it sat at ~0.82 of MemTotal, "well above
# DEVICE_CEILING_USABLE_FRACTION (0.60)," and called that "INTENTIONAL" —
# that observation was the invariant, not incidental color. This round is
# what first wrote the invariant down as a requirement and pinned it with
# `test_max_concurrent_budget_at_least_device_ceiling` in
# tests/test_resource_gate.py, because M1-F's first-pass value (5.25GiB,
# rounded up from the interactive raw sum alone) violated it and was
# caught by the project's own existing single-model tests
# (`test_hard_ceiling_boundary_flips_hard_reject` et al.) refusing a
# model just under compute_device_ceiling_bytes() with
# budget_ceiling_exceeded instead of admitting it. Logged as `NEW-179`
# (see NEW_ISSUES.md): this ordering requirement existed the whole time
# this constant has had a documented derivation and was never itself
# documented or tested before M1-F's own mistake surfaced it.
#
# Live `compute_device_ceiling_bytes()` called directly against this
# device's real `read_meminfo()` (MemTotal 11,623,120,896 bytes, 2026-08-24
# session) = 6,973,872,537 bytes (~6.4949GiB) — the actual device figure,
# not a fixture. The historical 10.8GiB-MemTotal fixture used throughout
# this module's tests gives a very close but NOT identical 6,957,847,019
# bytes (~6.4800GiB), since 10.8GiB is a slightly-rounded stand-in for the
# real, slightly-higher MemTotal (`DEVICE_CEILING_USABLE_FRACTION`, 0.60,
# applied to a MemTotal that drifts only slightly sample to sample —
# unlike SwapFree, MemTotal is a fixed hardware property, so this floor is
# far more stable than the swap-side numbers in this file).
#
# Final value: **7.00GiB (7,516,192,768 bytes)**, chosen to clear BOTH
# floors with a real margin, not sit at either one:
#   - clears the real live device ceiling (~6.4949GiB) by ~0.505GiB — wide
#     enough that a MemTotal re-read on this same device, or a modest
#     difference on a similar device, does not flip the invariant back the
#     wrong way (6.50GiB, an earlier candidate, cleared it by only ~6MiB —
#     too thin to trust against sample-to-sample drift).
#   - clears the interactive concurrent raw sum (5,562,090,016 bytes,
#     ~5.1801GiB) by ~1.4GiB — which also retires the embed-RSS-undercount
#     margin concern from the 5.20-vs-5.25GiB rounding question earlier
#     revisits of this constant wrestled with: even a large future
#     correction to the embed floor estimate has ample room here.
#   - still correctly REFUSES both two-concurrent-primary cases (an
#     unreachable state today per the structural check below, but the
#     ceiling should not accidentally admit either shape of it):
#     two INTERACTIVE primaries + embed = 2 x 5,209,547,936 + 352,542,080 =
#     10,771,637,952 bytes (~10.03GiB), comfortably above 7.00GiB; two
#     BACKGROUND primaries + embed = 2 x 3,598,935,200 + 352,542,080 =
#     7,550,412,480 bytes (~7.033GiB) — refused, but only by 34,219,712
#     bytes (~32.6MiB), NOT comfortably. If a genuine two-background-primary
#     concurrent case is ever intentionally introduced (it is not today —
#     see the structural check below), re-check this margin specifically;
#     it is the tightest case this ceiling is asked to refuse.
#
# One structural check this round confirmed, not merely assumed (rule 12):
# core/loader_v2.py's LlamaServer/ModelLoader never register a second
# "primary" slot before releasing the first — ensure_model()'s thermal-
# restart branch calls self.unload() (which calls rg.release_slot() on the
# existing slot) BEFORE calling load_primary() (which calls rg.reserve_slot()
# again), all inside a single SWAP_GUARD-held critical section. There is no
# spawn-then-kill handoff window in this codebase where two "primary"
# reservations exist concurrently, so this ceiling's reduction from 8.90GiB
# does not newly refuse an in-flight restart/reload transient that used to
# be admissible — verified by reading ensure_model()'s and
# LlamaServer.unload()'s bodies directly, not assumed from the old
# 3-model-derivation's shape.
#
# 7.00GiB / ~10.82GiB (this device's MemTotal, §5) ~= 0.647 — back above
# DEVICE_CEILING_USABLE_FRACTION (0.60), preserving the same qualitative
# relationship the retired 8.90GiB/0.82 value had (budget ceiling
# meaningfully above the single-model physical ceiling), just at a smaller
# absolute margin appropriate to a system with one generation model
# instead of three.
#
# Device-derived from THIS device's real on-disk model files at the n_ctx
# values above, on ~10.82GiB MemTotal — MUST BE RECOMPUTED (via
# estimate_model_load_cost() against the real files on that device), not
# linearly scaled, if this code ever runs on different hardware. Any future
# re-derivation MUST check the result against compute_device_ceiling_bytes()
# on the target device, not just against the concurrent raw sum — see the
# invariant note above.
MAX_CONCURRENT_MODEL_BUDGET_BYTES = int(7.00 * (1024 ** 3))  # 7,516,192,768 bytes


# TODO.md 7.4a sub-task C2 (project-architect scoping call per Ish's
# 2026-08-11 direction — Ish gave the ceiling number/"on by default" intent
# above; this constant's exact value is wiring-mechanics detail resolved
# without a further Ish round-trip, per this task's own instructions).
#
# `max_swap_usage_bytes` for `compute_swap_assisted_headroom_bytes()` (sub-
# task B) — the real default sub-task B's own docstring deferred to this
# sub-task. NOT derived from a bare `SwapFree - K * slmk_floor` formula on
# its own: checked against this item's own pre-registered NEW-21 fixture
# (SwapTotal~12GiB, SwapFree~10.8GiB, slmk_floor_bytes~1.2GiB), K=2.0 alone
# authorizes `10.8 - 2*1.2 = 8.4GiB` of swap-assist — enough to admit nearly
# any load at near-zero MemAvailable, contradicting this feature's own
# "capped well under the ~1.2GiB slmk floor, not up against it" framing.
# 768MiB was this constant's original, un-calibrated first default — well
# under the ~1.2GiB slmk floor per the same asymmetry REQUIRED_HEADROOM_
# FACTOR/DEVICE_CEILING_USABLE_FRACTION already document (under-estimating
# just reproduces today's status quo; over-estimating risks slmk killing
# something unrelated). Verified against the NEW-21 fixture BEFORE being
# written here, per sub-task B's own "expected value in the test first"
# rule: min(768MiB, 8.4GiB) = 768MiB (see
# tests/test_resource_gate.py::test_compute_swap_assisted_headroom_new21_fixture_pre_registered_case,
# already pinning this exact number from sub-task B).
#
# TODO.md 7.4a sub-task F (2026-08-11 recalibration, Ish's explicit direct
# decision, NOT an implementation-mechanics call like the paragraph above):
# sub-task E's live pass proved the swap-assisted mechanism genuinely works
# end-to-end at n_ctx=16384, but found the real production default,
# n_ctx=32768, refused — its deficit (~1356-1382MiB that session) exceeded
# the 768MiB cap by ~600-650MiB (NEW-137). Separately, Ish increased this
# device's real swap capacity — SwapTotal is now ~16.0GiB zram (confirmed
# `/sys/block/zram0/disksize` = 17,179,869,184 bytes), not the ~12GiB the
# 768MiB derivation above assumed. Ish's explicit instruction: raise this
# cap close to the formula's own live-computed ceiling on this device, not
# just far enough to patch the one known 32768 gap (a more conservative
# ~2GiB alternative was offered and explicitly declined) — use most of the
# real capacity the swap increase provides. Live arithmetic backing the new
# value (2026-08-11 session, drifts sample to sample — re-verify live
# before relying on it):
#   SwapTotal = 16,777,212 kB (~16.00GiB); SwapFree = 14,562,300 kB (~13.89GiB)
#   slmk_floor_bytes = SwapTotal * 0.10 = 1,717,986,508.8 B (~1.60GiB)
#   gated_swap_free  = SwapFree - 2.0 * slmk_floor_bytes
#                    = 14,911,795,200 - 3,435,973,017.6 = 11,475,822,182.4 B
#                    ≈ 10.69GiB (the formula's own uncapped ceiling —
#                      compute_swap_assisted_headroom_bytes()'s own
#                      min(max_swap_usage_bytes, gated_swap_free) term,
#                      right operand)
# New value: 10 * 1024**3 = 10,737,418,240 bytes (10.00GiB) — for
# can_admit() only (see DISPATCH_MAX_SWAP_ASSIST_BYTES below for the
# decoupled, unchanged dispatch-side cap). Deliberately NOT set to exactly
# the live-computed ceiling (~10.69GiB) — kept ~0.69GiB below it as a real,
# binding outer sanity ceiling (larger than the ~500-900MiB sample-to-
# sample SwapFree drift observed in this same session) rather than a cap
# that would never actually bind. This does make can_admit()'s plain-
# MemAvailable-only check effectively non-binding for any single
# admissible model whenever gated_swap_free >= 10GiB (true at every sample
# taken 2026-08-11): hard_reject bounds any single model's cost at
# compute_device_ceiling_bytes() (~6.49GiB), so the largest possible
# `required` after REQUIRED_HEADROOM_FACTOR (1.25) is ~8.11GiB — below the
# 10GiB cap regardless of live MemAvailable, including at MemAvailable=0.
# This is a deliberate, accepted consequence of Ish's "trust swap as real,
# usable capacity" direction, not an oversight — see TODO.md 7.4a sub-task
# F's own write-up for the full reasoning, including the known,
# accepted-for-now concurrent-admission consequence (combined with the
# existing MAX_CONCURRENT_MODEL_BUDGET_BYTES ceiling, this can admit up to
# ~8.9GiB of declared model cost at arbitrarily low live MemAvailable —
# flagged there for a separate live-verification pass, not addressed by
# changing either ceiling). **This 10.00GiB figure and the reasoning above
# it are historical — sub-task F calibrated them specifically to make the
# now-retired 7B-at-32768 case reachable through swap assist. That target
# is gone (§1.4). Superseded by the M1-F re-derivation directly below.**
#
# ── M1-F (2026-08-24): re-derived for the single-model architecture
# (`NEW-156`) ──────────────────────────────────────────────────────────────
# Same live formula sub-task F used (`compute_swap_assisted_headroom_bytes()`
# itself, called with the real max_swap_usage_bytes uncapped to read its own
# unclamped `gated_swap_free` term), but with a FRESH live read of
# `/proc/meminfo` on this device today, per rule 5 — the old 2026-08-11
# sample is not reused:
#   SwapTotal = 16,777,212 kB (~16.00GiB, unchanged — Ish's zram increase);
#   SwapFree (two reads taken seconds apart this session, confirming the
#   "drifts sample to sample" warning above is not theoretical):
#     read 1: SwapFree = 10,937,764 kB -> gated_swap_free (hand arithmetic,
#             slmk_floor_bytes = SwapTotal x 0.10, gated = SwapFree -
#             2.0 x slmk_floor_bytes) = 7,764,297,318 bytes (~7.231GiB)
#     read 2: SwapFree = 10,838,696 kB (a few seconds later) ->
#             compute_swap_assisted_headroom_bytes() called directly against
#             a fresh read_meminfo(), uncapped, returned 7,662,847,590 bytes
#             (~7.137GiB) — the module's own arithmetic, not a hand
#             re-derivation, confirming the formula and the hand math agree.
#   This device's real swap headroom moved ~94MiB in the time it took to run
#   two commands — smaller than the ~500-900MiB single-session drift sub-
#   task F observed, but the SAME property: this is a live, moving number,
#   never a constant to be trusted verbatim from a prior session.
#
# Target worst case, from §5.1's own table: primary alone (no embed — swap
# assist gates ONE model's admission at a time, not the concurrent-budget
# sum MAX_CONCURRENT_MODEL_BUDGET_BYTES above governs) at full interactive
# n_ctx=65536: model+kv+overhead+recurrent = 5,209,547,936 bytes
# (4.8518GiB), x REQUIRED_HEADROOM_FACTOR (1.25) = 6,511,934,920 bytes
# (~6.065GiB required) — matches §5.1's table exactly.
#
# New value: 6.50GiB (6,979,321,856 bytes). Chosen the same way sub-task F
# chose 10.00GiB — a real, binding margin below the live-computed ceiling,
# not exactly at it, and comfortably above the worst case this cap exists
# to admit:
#   - ~0.435GiB above the 6.065GiB required worst case (a real margin, not
#     a knife's edge — comparable in spirit, though smaller in absolute
#     terms, to the ~2.5GiB of slack the 131072/262144 rows of §5.1's table
#     show between the admissible 65536 case and the next hard-reject
#     tier).
#   - ~0.6-0.7GiB below both live gated_swap_free reads above (~7.14-7.23GiB
#     today) — a real ceiling that would actually bind if SwapFree drops
#     further, not a number set so high it never does.
#
# **Stated plainly, per rule 6/7 (do not let a smaller number imply a
# qualitative change that didn't happen): 6.50GiB does NOT make the plain-
# MemAvailable-only check binding again for the interactive worst case.**
# hard_reject bounds any single model's cost at compute_device_ceiling_bytes()
# (~6.49GiB per §5, itself close to the 65536 case's own 4.8518GiB raw
# cost), and the largest possible `required` after REQUIRED_HEADROOM_FACTOR
# for that same case is ~6.065GiB — below 6.50GiB regardless of live
# MemAvailable, including at MemAvailable=0. §4.3's original "this makes
# the plain-MemAvailable check effectively non-binding" observation still
# applies at 6.50GiB, in the same direction, just at a smaller magnitude
# than 10.00GiB produced. This is accepted, not an oversight — the
# alternative (a cap below 6.065GiB) would defeat swap-assist's entire
# purpose for the one case §8 Q1 explicitly decided should be admissible at
# this device's real headroom.
#
# **Also worth recording plainly: the live term, not this cap, is what
# actually binds today.** Both live gated_swap_free reads above
# (~7.14-7.23GiB) are only ~1.1-1.2GiB above the 6.065GiB requirement — if
# SwapFree drops by roughly that much on a future session (well within the
# ~3.46GiB swing observed between this session's read and the 2026-08-11
# sub-task F session's 10.43GiB-vs-13.89GiB SwapFree), the interactive
# 65536 worst case stops being admissible through swap assist regardless of
# what this constant is set to — the formula's own min(max_swap_usage_bytes,
# gated_swap_free) would clamp on the smaller, live-drifting operand, not
# this cap. Re-verify this margin live before relying on it, same as every
# other number in this section.
#
# This cap silently couples to n_ctx — worth stating for whoever next
# revisits §8 Q1's "65536" answer upward. Working backward from 6.50GiB:
# max admissible cost via swap assist alone = 6,979,321,856 / 1.25
# (REQUIRED_HEADROOM_FACTOR) = 5,583,457,484.8 bytes; subtracting the
# fixed, n_ctx-independent terms (model 2,740,937,888 + overhead
# 268,435,456 + recurrent 52,690,944 = 3,062,064,288) leaves a KV budget
# of 2,521,393,196.8 bytes; at 32,768 bytes/token that's n_ctx ≈ 76,947 —
# ~17.4% above today's 65536 default. THIS constant (via swap assist) is
# what binds FIRST if n_ctx is ever raised past ~77k on this device —
# compute_device_ceiling_bytes() (~6.4949GiB, no REQUIRED_HEADROOM_FACTOR
# applied to hard_reject's raw-cost comparison, by the same arithmetic
# good to ~n_ctx≈119,379) does not become the binding constraint until
# well past that. Re-derive both before raising n_ctx, not just the one
# that happens to be checked first.
#
# Real numbers, computed live via this project's own
# estimate_model_load_cost() and compute_swap_assisted_headroom_bytes()
# against the real on-disk primary model file and real /proc/meminfo, on
# this device's ~10.82GiB MemTotal / ~16.00GiB SwapTotal — MUST BE
# RECOMPUTED (not linearly scaled) if this code ever runs on different
# hardware.
#
# `NEW-135` fix, 2026-08-25 — this constant's MEANING, not just its value:
# every derivation above (E, F) computed this as a single number without
# considering more than one admission decision in flight at once, and
# `NEW-135` found `can_admit()` correspondingly treated it as if each
# concurrently-PENDING admission got its own independent 6.50GiB allowance
# against the same live `SwapFree` — never the actual intent (nothing in
# either derivation session argues for authorizing N x 6.50GiB of aggregate
# swap use just because N loads happen to race). The fix
# (`reserved_swap_bytes` on `compute_swap_assisted_headroom_bytes()`/
# `can_admit()`, wired through `reserve_slot()`) makes this constant behave
# as it was always meant to: a single shared ceiling on the TOTAL swap
# authorized across every concurrently-PENDING admission, not a per-load
# allowance each one gets independently. No change to the 6.50GiB VALUE
# itself was needed or made — only to how multiple concurrent claims
# against it are accounted for.
MAX_SWAP_ASSIST_BYTES = int(6.50 * 1024 ** 3)  # 6,979,321,856 bytes (6.50GiB)

# TODO.md 7.4a sub-task F: `can_dispatch_task()`'s own default cap,
# deliberately DECOUPLED from `MAX_SWAP_ASSIST_BYTES` above (raised to
# 10.00GiB by sub-task F, since re-derived to 6.50GiB by M1-F — see that
# constant's own comment above; both values are/were `can_admit()`-only —
# one-shot, explicit, human/loader-initiated model loads). `can_dispatch_
# task()` runs unguarded on EVERY tick of the daemon's autonomous,
# unattended dispatch loop, gating
# `DISPATCH_MIN_HEADROOM_BYTES` (1GiB, chosen specifically as an
# early-warning floor "well before can_admit()'s own...check would run,"
# per that constant's own comment). Raising the shared constant to 10GiB
# would have made that RAM-headroom check ALSO effectively non-binding
# whenever swap is healthy (10GiB swap contribution vastly exceeds the
# 1GiB dispatch floor), collapsing the deliberate early-warning gap between
# "dispatch refuses" and "admission refuses" that DISPATCH_MIN_HEADROOM_
# BYTES's own comment describes as the point of a flat, lower,
# task-agnostic floor. Ish's 2026-08-11 direction was given in the context
# of the 32768 model-load gap (NEW-137) — nothing in it addresses the
# autonomous per-tick dispatch loop's own, separate risk profile, so this
# constant stays at 768MiB, exactly `can_dispatch_task()`'s value before
# this recalibration (sub-task D2's own original derivation, unchanged). If
# Ish later wants the dispatch floor raised too, that is a separate,
# explicit decision — not a side effect of this recalibration.
DISPATCH_MAX_SWAP_ASSIST_BYTES = 805_306_368  # 768MiB, unchanged from pre-F

# Env var to DISABLE swap-assisted admission (C2) — the shipped default is
# ON with no opt-in required, per Ish's explicit 2026-08-11 decision (TODO.md
# 7.4a: "This reverses this entry's own earlier 'opt-in is the more
# conservative starting posture' suggestion — Ish's explicit call overrides
# that suggestion"). Kept as an off switch (not removed) because sub-task E's
# live pass needs a non-swapped baseline latency run through the same
# reserve_slot()/can_admit() path the swapped run uses, not a separate code
# path.
#
# Read LAZILY (inside _resolve_swap_assist_enabled_default(), not at module
# import time) for the same reason CODEY_TEST_PRIMARY_ARCH is read lazily
# above: a test process can flip it
# per-test without importlib.reload, and it can never outlive the env var.
#
# Only "1" (enabled) or "0" (disabled) are accepted, and anything else raises
# loudly rather than silently falling back — deliberately NOT a bare
# `!= "0"` truthiness check. That looser form would silently treat
# CODEY_SWAP_ASSIST_ADMISSION=false/off/no (an operator's evident intent to
# disable) as ENABLED instead, the exact wrong-direction failure this
# module's own _resolve_test_arch_override() docstring already warns against
# ("a typo'd override value must fail admission outright rather than quietly
# falling back") — here a wrong-direction failure is worse than a typo'd
# arch override, since it silently keeps admitting swap-assisted loads an
# operator explicitly tried to turn off.
CODEY_SWAP_ASSIST_ADMISSION_ENV = "CODEY_SWAP_ASSIST_ADMISSION"


def _resolve_swap_assist_enabled_default() -> bool:
    """
    Whether swap-assisted admission (C2) is active when `can_admit()`'s
    `enable_swap_assist` parameter is left at its default (`None`) — see
    that parameter's own docstring. Reads `CODEY_SWAP_ASSIST_ADMISSION`
    lazily at call time (see this section's header comment for why).
    """
    raw = os.environ.get(CODEY_SWAP_ASSIST_ADMISSION_ENV)
    if raw is None:
        return True
    if raw == "1":
        return True
    if raw == "0":
        return False
    raise ValueError(
        f"{CODEY_SWAP_ASSIST_ADMISSION_ENV}={raw!r} is not a valid value; "
        "use '1' (enabled, the default) or '0' (disabled). Unset it to use "
        "the default."
    )


@dataclass(frozen=True)
class GateDecision:
    admitted: bool
    hard_reject: bool
    reason: str
    estimated_cost_bytes: int
    headroom_bytes: int
    device_ceiling_bytes: int
    # TODO.md 7.4a sub-task C1. True only when admission was refused
    # specifically by the new MAX_CONCURRENT_MODEL_BUDGET_BYTES cumulative
    # check below — distinct from `hard_reject` because, unlike the
    # permanent single-model ceiling (can never be satisfied by any device
    # state change), a cumulative-budget denial is RECOVERABLE: release/
    # unload another resident model and the same load then passes.
    # Confirmed by direct code read (core/loader_v2.py:563-564,640): the
    # retryable-vs-permanent split is driven entirely by
    # GateDecision.hard_reject (LOAD_OUTCOME_GATE_DENIED_HARD if
    # decision.hard_reject else LOAD_OUTCOME_GATE_DENIED) — this new field
    # always ships with hard_reject=False, so a budget-ceiling denial maps
    # to the existing retryable LOAD_OUTCOME_GATE_DENIED path automatically,
    # with no core/loader_v2.py change needed.
    budget_ceiling_exceeded: bool = False
    # TODO.md 7.4a sub-task C2. True only on an admission that would have
    # been REFUSED on `MemAvailable` alone (i.e. `required > headroom` was
    # true) but was admitted anyway because
    # `headroom + compute_swap_assisted_headroom_bytes(...)` covered
    # `required`. False on every other admitted decision (RAM alone was
    # already sufficient) and on every refused decision (hard_reject,
    # budget_ceiling_exceeded, thermal, or swap-assist still insufficient).
    # Deliberately a separate field, not folded into `admitted` — a
    # caller/log needs to distinguish "admitted on RAM" from "admitted on
    # swap budget" (TODO.md 7.4a's own explicit requirement), since the two
    # carry different risk profiles (see `can_admit()`'s swap-assist section
    # below).
    admitted_via_swap: bool = False
    # NEW-135/NEW-136 fix: the actual swap bytes THIS decision would need to
    # authorize to cover the gap between `required` and RAM-only `headroom`
    # — 0 whenever `admitted_via_swap` is False. Recorded as a magnitude
    # (not just the `admitted_via_swap` boolean) specifically so a caller
    # persisting this into the slot store (`reserve_slot()`) can later sum
    # PENDING slots' real swap claims and pass that sum back in as
    # `reserved_swap_bytes`, closing NEW-135's double-claim race — a bare
    # boolean has no magnitude to sum. See `reserve_slot()`'s docstring for
    # the full accounting loop this field feeds.
    swap_bytes_claimed: int = 0


def can_admit(
    spec: ModelSpec,
    meminfo: Optional[Dict[str, int]] = None,
    reserved_bytes: int = 0,
    usable_fraction: float = DEVICE_CEILING_USABLE_FRACTION,
    headroom_factor: float = REQUIRED_HEADROOM_FACTOR,
    read_temp_fn=None,
    concurrent_committed_bytes: int = 0,
    max_concurrent_budget_bytes: int = MAX_CONCURRENT_MODEL_BUDGET_BYTES,
    enable_swap_assist: Optional[bool] = None,
    max_swap_usage_bytes: int = MAX_SWAP_ASSIST_BYTES,
    slmk_floor_gate_multiplier: float = SLMK_FLOOR_GATE_MULTIPLIER,
    reserved_swap_bytes: int = 0,
) -> GateDecision:
    """
    Decide whether `spec` can be admitted right now.

    No fixed concurrency ceiling (per the 2026-08-08 amendment): this
    function does not know or care how many other models are resident,
    except via `reserved_bytes` (their already-declared cost, subtracted
    from headroom so concurrent admissions don't double-book the same
    memory — see `total_reserved_bytes()`) and `concurrent_committed_bytes`
    (the declared-cost SUM check below — a fixed byte budget, not a "max N
    models" count rule; see MAX_CONCURRENT_MODEL_BUDGET_BYTES's own comment
    for why this is not the concurrency ceiling the amendment rejects).

    `meminfo` defaults to a live `/proc/meminfo` read if not supplied
    (tests should always supply a synthetic dict; see NEW-21's regression
    case in tests/test_resource_gate.py).

    `read_temp_fn` defaults to this module's `read_current_temp_c` (a live
    thermal read) if not supplied; tests should always supply a stub
    returning a fixed float or None instead of touching real hardware.

    `concurrent_committed_bytes` (default 0 — see TODO.md 7.4a sub-task C1
    item 4: every call site this sub-task doesn't touch stays unaffected by
    construction, since a real budget of 0 never trips this check) is a
    CALLER-PRECOMPUTED sum of every currently-tracked slot's declared cost
    (PENDING + RESIDENT — see `total_committed_bytes()`). This function
    stays free of any direct state-store I/O and fully synthetic-testable —
    it does not compute this sum itself. `reserve_slot()` is the one call
    site that computes and passes the real sum, inside its own existing
    lock (see its docstring for why that matters — computing this sum
    outside that lock would reopen the exact TOCTOU race `reserve_slot()`
    exists to prevent). Any other direct `can_admit()` caller that wants
    this check enforced is responsible for computing its own consistent
    snapshot the same way.

    `enable_swap_assist` (default `None`, resolving lazily to
    `_resolve_swap_assist_enabled_default()` — see
    `CODEY_SWAP_ASSIST_ADMISSION`'s own comment) controls TODO.md 7.4a
    sub-task C2, ON by default per Ish's 2026-08-11 direct decision.
    `max_swap_usage_bytes` (default `MAX_SWAP_ASSIST_BYTES`, 6.50GiB as of
    M1-F's 2026-08-24 re-derivation) and
    `slmk_floor_gate_multiplier` (default `SLMK_FLOOR_GATE_MULTIPLIER`, 2.0)
    are passed straight through to `compute_swap_assisted_headroom_bytes()`
    — see that function's own docstring and `MAX_SWAP_ASSIST_BYTES`'s own
    comment for the full derivation of both.

    `reserved_swap_bytes` (default 0, `NEW-135`'s fix): passed straight
    through to `compute_swap_assisted_headroom_bytes()`'s own parameter of
    the same name — the swap-assist already claimed by other concurrently-
    PENDING admissions. `reserve_slot()` is the one call site that computes
    a real, lock-consistent value (summing PENDING slots'
    `swap_bytes_claimed`, mirroring how it already computes `reserved_bytes`
    for the RAM side) — any other direct caller wanting this race closed is
    responsible for computing its own consistent snapshot the same way.

    Four independent checks, any of which can refuse admission:
      1. hard_reject: `spec`'s cost alone exceeds the device's usable
         physical-RAM ceiling — absolute, ignores current headroom/residency
         entirely (2026-08-08 amendment's one remaining non-negotiable rule).
      2. budget-ceiling check (TODO.md 7.4a sub-task C1): `spec`'s cost,
         ADDED to `concurrent_committed_bytes`, exceeds
         `max_concurrent_budget_bytes` (default
         MAX_CONCURRENT_MODEL_BUDGET_BYTES — see its own comment for the
         full derivation). Unlike hard_reject, this denial is RECOVERABLE
         (release/unload another resident model and the same load then
         passes) — reported via `GateDecision.budget_ceiling_exceeded`, not
         `hard_reject`, so callers can tell the two apart.
      3. budget check: `spec`'s cost, times `headroom_factor` (a documented
         conservative margin — see REQUIRED_HEADROOM_FACTOR's docstring),
         exceeds currently-computed headroom (live MemAvailable, minus any
         `reserved_bytes`) — this is the live, computed limit that replaces
         the old fixed-count rule. TODO.md 7.4a sub-task C2: ONLY when this
         check would otherwise refuse admission, a second, swap-assisted
         comparison runs — `required` against `headroom +
         compute_swap_assisted_headroom_bytes(meminfo, max_swap_usage_bytes,
         slmk_floor_gate_multiplier)`. If that combined figure covers
         `required`, the load is admitted with
         `GateDecision.admitted_via_swap=True` instead of being refused. A
         load that already passes on `headroom` alone never reaches this
         swap comparison at all — its outcome (and every field on the
         returned `GateDecision`) is byte-for-byte unchanged by
         `enable_swap_assist`/`max_swap_usage_bytes`/
         `slmk_floor_gate_multiplier` in that case. Checks 1 and 2 above
         both `return` before this point in the function body, so a
         hard_reject or budget_ceiling_exceeded denial is structurally
         unreachable by this swap-assisted comparison — it can only ever
         override THIS check's own denial, never checks 1 or 2's (TODO.md
         7.4a's own hard invariant for C2, "must never be allowed to
         override C1's cumulative-budget denial").
      4. thermal check: current CPU temperature (if readable) is at or above
         THERMAL_CONFIG["temp_critical"] — the amendment names thermal state
         as one of the live signals the gate arbitrates alongside RAM/swap,
         not just a post-hoc throttle applied after a model is already
         running (see core/thermal.py's existing, separate
         inference-duration-based throttling, which this does not replace).
         An unreadable temperature (None) is treated as "no thermal
         objection" — same fail-open posture core/thermal.py's own
         `_check_thermal_status()` already uses for a None read.

    Checks 3 and 4 (headroom, thermal) are evaluated in the same relative
    order they always were; check 2 (budget-ceiling) is evaluated
    immediately after check 1 (hard_reject) and before either of them, per
    TODO.md 7.4a sub-task C1's explicit scoped ordering — the point being
    that this device-policy ceiling is checked before any live-memory/
    thermal signal is even consulted.

    Caveats carried forward from sub-task B:
      - The swap-assist figure is authorized swap USAGE, not a claim about
        real usable headroom under an actual model load — quantized model
        weight pages may compress far less favorably than the ~4:1 ratio
        `compute_zram_compression_ratio()` observes on ordinary idle app
        pages. Unverified until sub-task E's live pass. Still open.
      - **`NEW-135` fixed for the `reserve_slot()` call path (this round,
        not C2):** `compute_swap_assisted_headroom_bytes()` now accepts
        `reserved_swap_bytes` (see this function's own `reserved_swap_bytes`
        parameter above) and `reserve_slot()` computes and passes a real,
        lock-consistent value — two concurrently-pending swap-assisted
        `reserve_slot()` admissions can no longer each independently claim
        the full `MAX_SWAP_ASSIST_BYTES` cap against the same live
        `SwapFree` figure. **NOT fixed for `can_dispatch_task()`'s separate
        swap-assist consumer** (see its own docstring's carried-forward
        caveat) — that path never registers a slot, so there is nothing for
        this accounting mechanism to sum on that side; a `can_admit()`
        admission and a `can_dispatch_task()` dispatch decision can still
        each independently claim swap headroom with no cross-awareness of
        each other. Any *direct* caller of `can_admit()` other than
        `reserve_slot()` (there are none in this codebase today, per the
        docstring above) would also need to compute its own consistent
        `reserved_swap_bytes` snapshot the same way to get this protection.
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

    prospective_committed = concurrent_committed_bytes + cost.total_bytes
    if prospective_committed > max_concurrent_budget_bytes:
        return GateDecision(
            admitted=False,
            hard_reject=False,
            budget_ceiling_exceeded=True,
            reason=(
                f"model {spec.model_id!r} cost estimate "
                f"({cost.total_bytes / _KB / _KB:.0f}MiB) added to already-committed "
                f"({concurrent_committed_bytes / _KB / _KB:.0f}MiB) = "
                f"{prospective_committed / _KB / _KB:.0f}MiB, which exceeds the "
                f"device's fixed concurrent-model budget "
                f"({max_concurrent_budget_bytes / _KB / _KB:.0f}MiB) — recoverable "
                "by releasing/unloading another resident model"
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
        # TODO.md 7.4a sub-task C2. Reached ONLY when the plain-RAM check
        # just above would already refuse admission — this branch never
        # runs at all for a load that passes on `headroom` alone (see
        # `can_admit()`'s own docstring for the byte-for-byte-unchanged
        # guarantee that follows from that). Checks 1 (hard_reject) and 2
        # (budget_ceiling_exceeded) above both `return` before this point in
        # the function body, so this swap-assisted comparison is
        # structurally unreachable on either of those paths — it can only
        # ever override THIS check's own denial, never theirs (the hard
        # invariant TODO.md 7.4a states explicitly for C2).
        swap_assist_enabled = enable_swap_assist
        if swap_assist_enabled is None:
            swap_assist_enabled = _resolve_swap_assist_enabled_default()

        if swap_assist_enabled:
            swap_headroom = compute_swap_assisted_headroom_bytes(
                meminfo,
                max_swap_usage_bytes,
                slmk_floor_gate_multiplier,
                reserved_swap_bytes=reserved_swap_bytes,
            )
            combined_headroom = headroom + swap_headroom
            if required <= combined_headroom:
                # The actual swap this decision needs to authorize is just
                # the gap RAM-only headroom didn't cover — not the whole
                # `swap_headroom` capacity, which may be larger than what
                # this particular load actually uses. `required > headroom`
                # is guaranteed true in this branch (the `if` above this
                # swap-assist block), so this gap is always > 0.
                swap_claim = required - headroom
                return GateDecision(
                    admitted=True,
                    hard_reject=False,
                    admitted_via_swap=True,
                    swap_bytes_claimed=swap_claim,
                    reason=(
                        f"model {spec.model_id!r} cost estimate "
                        f"({cost.total_bytes / _KB / _KB:.0f}MiB) x headroom_factor "
                        f"({headroom_factor}) = {required / _KB / _KB:.0f}MiB exceeds "
                        f"RAM-only headroom ({headroom / _KB / _KB:.0f}MiB), but is "
                        f"covered by RAM + swap-assisted headroom "
                        f"({combined_headroom / _KB / _KB:.0f}MiB, of which "
                        f"{swap_headroom / _KB / _KB:.0f}MiB is swap-assisted) — "
                        "admitted via swap assist"
                    ),
                    estimated_cost_bytes=cost.total_bytes,
                    headroom_bytes=headroom,
                    device_ceiling_bytes=ceiling,
                )

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


def would_model_fit_decision(
    spec: ModelSpec,
    meminfo: Optional[Dict[str, int]] = None,
    reserved_bytes: int = 0,
    read_temp_fn=None,
    concurrent_committed_bytes: int = 0,
    allow_swap_assist: bool = False,
) -> GateDecision:
    """
    TODO.md 7.4a sub-task D1. Full-`GateDecision` sibling of
    `would_model_fit()`, added because a bare bool answer to "would this
    fit" became ambiguous once C1 (a recoverable budget-ceiling "no",
    distinct from a headroom "no") and C2 (a swap-assisted "yes", distinct
    from a RAM-comfortable "yes") both landed — a future routing caller
    (7.3, `core/model_tiers.py`) may need to tell these apart (e.g. retry a
    budget-ceiling denial later once another model unloads, but treat a
    headroom/hard_reject denial as this candidate being unsuitable full
    stop; or decline to route onto a swap-assisted "fits").

    `would_model_fit()` itself is now a thin `.admitted` wrapper over this
    function — deliberately NOT replaced/repointed to return a
    `GateDecision` directly. A `GateDecision` instance is always truthy, so
    silently changing `would_model_fit()`'s own return type would turn any
    existing/future `if would_model_fit(...):` bool check into an
    always-True bug with no error anywhere it would surface — this module
    has no live caller of `would_model_fit()` yet (grepped), but
    `core/model_tiers.py` is this function's intended, concurrently-
    developed consumer, so "no caller today" doesn't mean "safe to change
    the return type out from under it." Callers that want the fuller shape
    should call `would_model_fit_decision()` directly instead.

    `concurrent_committed_bytes` (default 0, matching `can_admit()`'s own
    default): forwarded straight through so a caller CAN get a real
    `budget_ceiling_exceeded` answer if it supplies its own sum — but
    unlike `reserve_slot()`, this function (like `would_model_fit()`
    before it) holds no lock and registers/reserves nothing, so any
    caller-supplied value here is inherently a stale snapshot by the time
    it's read. That staleness is acceptable specifically BECAUSE this is
    an advisory, side-effect-free query — there is no TOCTOU window to
    protect the way there is for `reserve_slot()`'s own write (see
    `can_admit()`'s docstring on why `reserve_slot()` must compute this
    sum inside its own lock). A caller wanting this check enforced with
    reservation-time consistency should go through `reserve_slot()`/
    `can_admit()` directly, not this function.

    `allow_swap_assist` (default `False`) is the opt-in TODO.md 7.4a
    sub-task C's own pre-declared default asked for: swap-assisted
    admission does NOT count as "fits" for routing purposes unless a
    caller explicitly opts in (routing a smaller-model fallback decision
    onto a thrash-risk load is a different risk profile than the gate's
    own explicit, single-load admission decision). Forwarded as
    `can_admit()`'s own `enable_swap_assist` parameter — `False` here
    means "swap-assist off for this query" regardless of
    `CODEY_SWAP_ASSIST_ADMISSION`'s own default-on setting, exactly the
    override `would_model_fit()` already applied unconditionally before
    this sub-task.
    """
    return can_admit(
        spec,
        meminfo=meminfo,
        reserved_bytes=reserved_bytes,
        read_temp_fn=read_temp_fn,
        concurrent_committed_bytes=concurrent_committed_bytes,
        enable_swap_assist=allow_swap_assist,
    )


def would_model_fit(
    spec: ModelSpec,
    meminfo: Optional[Dict[str, int]] = None,
    reserved_bytes: int = 0,
    read_temp_fn=None,
    concurrent_committed_bytes: int = 0,
    allow_swap_assist: bool = False,
) -> bool:
    """
    Answerable-question hook for the amendment's noted future direction
    (task-appropriate fallback to a smaller model): "would this model fit
    right now", without registering a slot or otherwise having any side
    effect. Deliberately NOT a routing decision — just exposes the same
    admission math `can_admit()` uses so a future routing layer (7.3) can
    query it. Not implementing routing itself is intentional (see this
    module's docstring / TODO.md 7.4).

    Returns only `.admitted` from `would_model_fit_decision()` (TODO.md
    7.4a sub-task D1 added that function) — a plain bool, same shape this
    function has always had, for any caller that only needs a yes/no
    answer. See `would_model_fit_decision()`'s own docstring for the full
    case shape (`hard_reject`, `budget_ceiling_exceeded`,
    `admitted_via_swap`) a caller needing more detail should use instead,
    and for `concurrent_committed_bytes`/`allow_swap_assist`'s own
    semantics (both default to the same pre-D1 behavior — a real budget of
    0 and swap-assist off — so an unmodified call site is unaffected by
    this sub-task).
    """
    return would_model_fit_decision(
        spec,
        meminfo=meminfo,
        reserved_bytes=reserved_bytes,
        read_temp_fn=read_temp_fn,
        concurrent_committed_bytes=concurrent_committed_bytes,
        allow_swap_assist=allow_swap_assist,
    ).admitted


# ── Task-dispatch gate (7.4 sub-task C) ──────────────────────────────────────
# `can_dispatch_task()` is a coarse pre-check for `core/daemon.py`'s
# `_process_planner_tasks()` loop, deciding whether to claim (via
# `state.try_claim_task()`) and dispatch the next queued task at all — NOT a
# model-admission re-check. `_execute_task()` (core/task_executor.py:96)
# already runs through `run_agent()` -> the model-loading path, which already
# calls `can_admit()` with a real ModelSpec before any model loads.
# `can_dispatch_task()` must not re-simulate that decision; its only job is to
# avoid claiming a task the executor would immediately fail on for a resource
# reason, and to enforce the interactive-lock rule `can_admit()` knows nothing
# about (never do daemon-initiated background work while a human is watching
# the TUI — see `is_interactive_session_active()` above).
#
# Both inputs (`snapshot`, `interactive_active`) are passed in rather than
# read internally, matching `can_admit()`'s own inject-everything test
# convention, so this function stays synchronous and trivially testable with
# synthetic ResourceSnapshots.

# RAM headroom floor below which task dispatch is refused outright, regardless
# of what a model's own admission check would later say. This is the one leg
# of can_dispatch_task() with no existing project constant to reuse (unlike
# the thermal/battery legs below, which reuse THERMAL_CONFIG). Grounded in
# this project's own swap-pressure evidence rather than picked arbitrarily:
# NEW-14/NEW-18/NEW-21 (NEW_ISSUES.md) all observed swap onset with as little
# as ~1.2GiB of free RAM before a model load, with severe swap pressure
# (1.2Gi -> 5.6Gi in ~10s) within seconds once it started under a full
# 3-model stack. 1GiB sits just below that observed onset point, so it acts
# as an early-warning floor for *dispatching new work* — well before
# `can_admit()`'s own, separately-computed per-model headroom_factor check
# would run against a real ModelSpec at load time. It is deliberately not
# "0 bytes" (any headroom at all): NEW-21's whole lesson is that a bare
# "nonzero headroom" check is not conservative enough on this device.
#
# TODO.md 7.4a sub-task D2 (Ish's direct decision, 2026-08-11): this floor
# is now swap-aware, matching can_admit()'s own C2 posture, rather than
# leaving dispatch RAM-only while admission can lean on swap — see
# can_dispatch_task()'s own docstring for the wiring. Note this floor is
# still a flat, task-agnostic threshold, not a per-candidate cost estimate
# scaled by REQUIRED_HEADROOM_FACTOR the way can_admit()'s check is — the
# flat floor itself IS this check's conservatism (dispatch has no specific
# model/cost to weigh yet, just "is it even worth attempting"), so there is
# deliberately no headroom_factor-equivalent multiplier here; that is not
# an oversight relative to can_admit()'s shape, it is a different kind of
# check by design (see this section's own header comment).
DISPATCH_MIN_HEADROOM_BYTES = 1 * 1024 * 1024 * 1024  # 1 GiB


@dataclass(frozen=True)
class DispatchDecision:
    allowed: bool
    reason: str
    # TODO.md 7.4a sub-task D2. True only when `allowed=True` was reached
    # via the swap-assisted branch of the RAM-headroom check below (i.e.
    # `ram_headroom_bytes` alone was below DISPATCH_MIN_HEADROOM_BYTES, but
    # `ram_headroom_bytes + compute_swap_assisted_headroom_bytes(...)`
    # covered it) — mirrors GateDecision.admitted_via_swap so a later
    # reader of dispatch-decision logs can distinguish "dispatched on RAM"
    # from "dispatched on swap budget", the same distinction C2 required
    # for admission. False on every other decision (RAM alone was already
    # sufficient, or dispatch was refused for any reason).
    dispatched_via_swap: bool = False


def can_dispatch_task(
    snapshot: "ResourceSnapshot",
    interactive_active: bool,
    enable_swap_assist: Optional[bool] = None,
    max_swap_usage_bytes: int = DISPATCH_MAX_SWAP_ASSIST_BYTES,
    slmk_floor_gate_multiplier: float = SLMK_FLOOR_GATE_MULTIPLIER,
) -> DispatchDecision:
    """
    Decide whether `_process_planner_tasks()` should claim and dispatch the
    next queued task right now, given a pre-composed `snapshot` (see
    `get_resource_snapshot()`) and `interactive_active` (see
    `is_interactive_session_active()`).

    Checks, in this exact priority order (first match wins):
      1. `interactive_active` True -> refuse. The rule `can_admit()` has no
         equivalent of: never do daemon-initiated background work while a
         human is watching the TUI.
      2. `temperature_c is not None and temperature_c >=
         THERMAL_CONFIG["temp_critical"]` -> refuse. Same threshold
         `can_admit()` already uses — one authority, not a second number to
         keep in sync.
      3. `battery_percent is not None and not battery_charging and
         battery_percent <= THERMAL_CONFIG["batt_critical"]` -> refuse.
         Mirrors `core/recursive.py:get_adaptive_depth()`'s existing
         "not charging AND at/below batt_critical -> treat as most
         restrictive" convention exactly (same config keys, same
         not-charging gate).
      4. `ram_headroom_bytes < DISPATCH_MIN_HEADROOM_BYTES` -> refuse,
         UNLESS TODO.md 7.4a sub-task D2's swap-assisted branch covers the
         gap (see below) — in which case dispatch is allowed with
         `DispatchDecision.dispatched_via_swap=True` instead.
      5. `cpu_percent is None` -> this signal is IGNORED, not a refusal
         reason (NEW-108 confirms `/proc/stat` is permission-denied on this
         device, so `cpu_percent` reads `None` unconditionally, regardless
         of actual load — treating `None` as "fail closed" would
         permanently wedge dispatch on this exact device, mirroring
         `can_admit()`'s own existing precedent for an unreadable
         temperature: "An unreadable temperature (None) is treated as 'no
         thermal objection'"). When every other check passes and
         `cpu_percent is None`, the returned `reason` says so explicitly so
         a live-verifier reading dispatch-decision logs can't mistake "gate
         open" for "CPU confirmed low."

    A real, measured `cpu_percent` value is not itself gated on by this
    sub-task (see WORK_QUEUE.md's note on this leg) — it is read into the
    snapshot but not compared against a threshold here.

    **TODO.md 7.4a sub-task D2 (Ish's direct decision, 2026-08-11)**: check
    4's RAM-headroom floor is now swap-aware, using the exact same
    `compute_swap_assisted_headroom_bytes()` mechanism and
    `CODEY_SWAP_ASSIST_ADMISSION` on/off-switch convention `can_admit()`'s
    own C2 swap-assist branch already established — not a second, parallel
    swap-assist mechanism with different defaults. Only evaluated when
    `ram_headroom_bytes` alone is already below `DISPATCH_MIN_HEADROOM_
    BYTES`; a snapshot that already passes on RAM alone never reaches this
    branch and its `DispatchDecision` is byte-for-byte unchanged by this
    sub-task. `enable_swap_assist` (default `None`, resolving lazily to
    `_resolve_swap_assist_enabled_default()`, same as `can_admit()`) and
    `slmk_floor_gate_multiplier` (default `SLMK_FLOOR_GATE_MULTIPLIER`) are
    the same shared parameters `can_admit()` exposes. `max_swap_usage_bytes`
    is the one deliberate exception, per TODO.md 7.4a sub-task F's
    2026-08-11 recalibration: this function's own default is
    `DISPATCH_MAX_SWAP_ASSIST_BYTES` (768MiB, unchanged), NOT
    `MAX_SWAP_ASSIST_BYTES` (6.50GiB as of M1-F's 2026-08-24 re-derivation,
    `can_admit()`-only) — see `DISPATCH_MAX_SWAP_ASSIST_BYTES`'s own
    comment for why the two caps were deliberately decoupled. Both are
    passed straight through to `compute_swap_assisted_headroom_bytes()` —
    see that function's own comments for the full derivation.
    `ResourceSnapshot.swap_free_bytes`/`swap_total_bytes` (sub-task A) are
    synthesized into a small meminfo-shaped dict here rather than
    re-plumbing sub-task B's own `compute_swap_assisted_headroom_bytes()`
    signature (which takes a full meminfo dict by contract) — out of scope
    for this sub-task.

    Checks 1-3 above still take priority over this branch exactly as before
    (unchanged code, unchanged order) — interactive/thermal/battery
    refusals `return` before this RAM-headroom check ever runs, so
    swap-assist here can only ever cover THIS check's own gap, never
    override checks 1-3, matching the same structural (not just
    conventional) guarantee `can_admit()`'s own swap-assist branch gives
    for `hard_reject`/`budget_ceiling_exceeded`.

    **`NEW-187` fix (2026-08-26), partially closing the `NEW-135` gap this
    function widened**: this branch now passes `total_reserved_swap_bytes()`
    — the exact ledger `reserve_slot()`'s own `NEW-135` fix populates,
    already documented on that function as "for any direct caller that
    isn't `reserve_slot()`" — into `compute_swap_assisted_headroom_bytes()`'s
    `reserved_swap_bytes` parameter below, so a dispatch decision no longer
    treats the full `DISPATCH_MAX_SWAP_ASSIST_BYTES` cap as untouched
    when a concurrently-PENDING `reserve_slot()` admission has already
    claimed swap-assist headroom against the shared live `SwapFree` figure.
    This is a ONE-DIRECTIONAL fix, not a full close of `NEW-135`'s "widened
    blast radius": `can_dispatch_task()` never registers a slot and commits
    no durable claim of its own (a dispatch decision has no persisted
    record for a racing `reserve_slot()` call to sum against, unlike two
    `reserve_slot()` callers racing each other) — so `reserve_slot()`
    remains, structurally, unable to see a concurrent dispatch decision's
    swap usage. That residual direction is not a symmetric race the way
    `NEW-135`'s original finding was; it is dispatch (which runs already-
    resident models, not a new model load) reading the swap ledger, never
    registering a durable claim of its own onto it. (Note: the read call,
    `total_reserved_swap_bytes()`, does call `list_slots(reap_dead=True)`
    by default, which DOES mutate the shared slot store under lock —
    dropping dead-PID entries. So this function is not literally
    read-only against the shared state file; it just never adds a
    PENDING claim a racing `reserve_slot()` call would sum against, and
    it does so at daemon-tick frequency, not just at load-admission time
    like `reserve_slot()`'s own reaping.) See `NEW-187`'s own
    `NEW_ISSUES.md` entry for the full reasoning on why this asymmetry is
    accepted as the closing state, not deferred further. A read failure
    on this ledger fails toward disabling swap-assist for the tick
    (`swap_assist_enabled = False`), matching the sibling
    `CODEY_SWAP_ASSIST_ADMISSION` handler's fail-safe direction just
    above in this function — not toward the more permissive "treat as no
    other claims" reading (code-reviewer finding, NEW-187 review round).
    """
    if interactive_active:
        return DispatchDecision(
            allowed=False,
            reason="interactive TUI session active — deferring background dispatch",
        )

    from utils.config import THERMAL_CONFIG

    temp_critical = THERMAL_CONFIG.get("temp_critical", 90)
    if snapshot.temperature_c is not None and snapshot.temperature_c >= temp_critical:
        return DispatchDecision(
            allowed=False,
            reason=(
                f"current CPU temperature ({snapshot.temperature_c:.1f}°C) at/above "
                f"critical threshold ({temp_critical}°C) — deferring dispatch"
            ),
        )

    batt_critical = THERMAL_CONFIG.get("batt_critical", 5)
    if (
        snapshot.battery_percent is not None
        and not snapshot.battery_charging
        and snapshot.battery_percent <= batt_critical
    ):
        return DispatchDecision(
            allowed=False,
            reason=(
                f"battery critical ({snapshot.battery_percent}%, not charging) — "
                "deferring dispatch"
            ),
        )

    if snapshot.ram_headroom_bytes < DISPATCH_MIN_HEADROOM_BYTES:
        # TODO.md 7.4a sub-task D2. Only reached when the plain-RAM check
        # just above would already refuse dispatch — a snapshot that passes
        # on ram_headroom_bytes alone never reaches this branch, so its
        # DispatchDecision is byte-for-byte unchanged by this sub-task (see
        # this function's own docstring).
        swap_assist_enabled = enable_swap_assist
        if swap_assist_enabled is None:
            try:
                swap_assist_enabled = _resolve_swap_assist_enabled_default()
            except ValueError as e:
                # Safety-relevant exception handling (CLAUDE.md's rule):
                # _resolve_swap_assist_enabled_default() raises loudly BY
                # DESIGN on a malformed CODEY_SWAP_ASSIST_ADMISSION value
                # (see its own comment — silently falling back there would
                # risk the wrong-direction failure of quietly keeping
                # swap-assist ON when an operator explicitly tried to turn
                # it off). can_admit()'s own callers can safely let that
                # exception propagate — they are explicit, single-load
                # requests. can_dispatch_task() is different: it runs on
                # EVERY tick of the daemon's autonomous, unattended dispatch
                # loop (core/daemon.py's _process_planner_tasks(), called
                # with no surrounding try/except around this check), which
                # could not raise at all before this sub-task. Letting a
                # malformed env var wedge/crash that loop is a worse failure
                # than this one check quietly falling back — so here (and
                # only here, not in can_admit()) the fail-safe direction is
                # DISABLED (byte-for-byte the pre-D2, RAM-only behavior),
                # logged at warning so the fallback isn't silent.
                warning(
                    "resource_gate: can_dispatch_task() failed to resolve "
                    f"CODEY_SWAP_ASSIST_ADMISSION default ({e}) — treating "
                    "swap-assist as disabled for this dispatch check"
                )
                swap_assist_enabled = False

        if swap_assist_enabled:
            # NEW-187 fix: same ledger reserve_slot() populates via its own
            # NEW-135 fix, read here (see this function's own docstring
            # "NEW-187 fix" section for the one-directional design). A read
            # failure (e.g. a corrupt/unreadable state file) must not crash
            # the daemon's autonomous dispatch loop, but per code-reviewer
            # findings (NEW-187 review round) a read failure must NOT fail
            # toward the MORE permissive "treat as 0 in-flight claims"
            # reading — that is exactly backwards for a gate, and reads on
            # the same ledger elsewhere in this file (reserve_slot()'s own
            # inline sum) fail closed, not open. Matching the sibling
            # CODEY_SWAP_ASSIST_ADMISSION handler just above this block:
            # fail-safe direction is DISABLED (skip the swap branch for this
            # tick, byte-for-byte the pre-D2 RAM-only behavior), logged at
            # warning so the fallback isn't silent.
            try:
                reserved_swap_for_dispatch = total_reserved_swap_bytes()
            except Exception as e:
                warning(
                    "resource_gate: can_dispatch_task() failed to read "
                    f"total_reserved_swap_bytes() ({e}) — treating "
                    "swap-assist as disabled for this dispatch check"
                )
                swap_assist_enabled = False

        if swap_assist_enabled:
            swap_headroom = compute_swap_assisted_headroom_bytes(
                # compute_swap_assisted_headroom_bytes() takes a meminfo-
                # shaped dict by contract (sub-task B); ResourceSnapshot
                # already carries the same two fields under different names
                # (sub-task A), so a two-key dict is synthesized here rather
                # than re-plumbing sub-task B's own signature — out of scope
                # for this sub-task.
                {"SwapFree": snapshot.swap_free_bytes, "SwapTotal": snapshot.swap_total_bytes},
                max_swap_usage_bytes,
                slmk_floor_gate_multiplier,
                reserved_swap_bytes=reserved_swap_for_dispatch,
            )
            combined_headroom = snapshot.ram_headroom_bytes + swap_headroom
            if combined_headroom >= DISPATCH_MIN_HEADROOM_BYTES:
                return DispatchDecision(
                    allowed=True,
                    dispatched_via_swap=True,
                    reason=(
                        f"RAM headroom ({snapshot.ram_headroom_bytes / _KB / _KB:.0f}MiB) "
                        f"below dispatch floor "
                        f"({DISPATCH_MIN_HEADROOM_BYTES / _KB / _KB:.0f}MiB), but covered "
                        f"by RAM + swap-assisted headroom "
                        f"({combined_headroom / _KB / _KB:.0f}MiB, of which "
                        f"{swap_headroom / _KB / _KB:.0f}MiB is swap-assisted) — "
                        "dispatching via swap assist"
                    ),
                )

        return DispatchDecision(
            allowed=False,
            reason=(
                f"RAM headroom ({snapshot.ram_headroom_bytes / _KB / _KB:.0f}MiB) below "
                f"dispatch floor ({DISPATCH_MIN_HEADROOM_BYTES / _KB / _KB:.0f}MiB) — "
                "deferring dispatch"
            ),
        )

    if snapshot.cpu_percent is None:
        return DispatchDecision(
            allowed=True,
            reason="within resource limits (CPU unmeasurable on this device, NEW-108 — not evaluated)",
        )

    return DispatchDecision(allowed=True, reason="within resource limits")


# ── Autonomous shutdown tripwire (7.4 sub-task D) ────────────────────────────
# `should_trip_shutdown()` decides whether core/daemon.py's `_main_loop()`
# watchdog tick should call `_trigger_shutdown()` — a fully autonomous,
# process-internal decision with no socket-triggerable equivalent (the old
# `shutdown` socket command / `daemon_shutdown()` helper were retired in this
# same sub-task; see core/daemon.py). Implements Ish's 2026-08-10 decision on
# PENDING_ISH_DECISIONS.md item 2 (option 3, "CPU-as-veto-only-when-
# measurable" — see WORK_QUEUE.md Track 3 item 2 sub-task D for the full
# three-option writeup this resolves; options 1 "thermal-only-permanent" and
# 2 "strict AND, unlive-verifiable-forever-on-this-device" were both
# explicitly NOT chosen).

DEFAULT_MIN_QUALIFYING_FRACTION = 0.8

# Expected spacing between samples under normal operation — matches the
# daemon's own 30s watchdog tick (core/daemon.py's `_main_loop()`, which
# calls `sample_temperature_c()`/`sample_cpu_percent()` once per tick; see
# that module's own `_watchdog_ticks >= 60` comment at a 0.5s per-tick
# sleep). Used only to compute how many samples a genuinely-sustained
# trailing window *should* contain, for `_sustained_trailing_run()`'s
# density check below — not to reject any individual sample's timing.
EXPECTED_SAMPLE_INTERVAL_SEC = 30.0

# Minimum fraction of the *expected* tick count for a trailing window's span
# that must actually be present, in addition to (not instead of) the
# existing "fraction of present samples above threshold" check. Guards
# against a sparse-history false-trip: e.g. two samples 25 minutes apart
# (a real reachable case — a run of failed thermal reads, per
# `sample_temperature_c()`'s "append nothing on a None read" contract,
# followed by one hot sample after the gap) satisfies the span check and a
# 100%-qualifying-fraction check with only 2 of the ~50 samples a genuinely
# 25-minute-sustained run at the normal 30s tick rate would contain. 0.5 is
# a deliberately generous floor (comfortably tolerant of missed/failed
# reads and real tick jitter) that still rejects a history this sparse by
# roughly an order of magnitude.
#
# Live-verification caveat: with `duration_sec` shortened to something on
# the order of `EXPECTED_SAMPLE_INTERVAL_SEC` (30s) or less — e.g. a
# live-verification session using `CODEY_SHUTDOWN_TRIP_AFTER_SEC=20` to
# observe a real trip without a multi-hour session — the backward walk in
# `_sustained_trailing_run()` below always stops at the FIRST window whose
# span first reaches `duration_sec`, which at the daemon's normal ~30s tick
# cadence is a 2-sample, ~30s-span window. At that span, `expected_count =
# max(1.0, span / EXPECTED_SAMPLE_INTERVAL_SEC)` floors at 1.0, so density
# is always >= 1.0 there and this branch never rejects. (The floor does NOT
# make the guard vacuous in general — e.g. 2 samples 25 minutes apart still
# computes density ~0.04 and correctly rejects; it only fails to bind at
# the specific short spans a shortened live-test duration produces.) A
# live-verification session run this way will therefore NOT exercise this
# rejecting branch at all — only the unit tests do. Do not treat "sub-task
# D was live-verified" as evidence this density-guard fix specifically was
# live-verified; those are separate claims.
MIN_QUALIFYING_DENSITY_FRACTION = 0.5


def _sustained_trailing_run(
    history: List[Tuple[float, float]],
    threshold: float,
    duration_sec: float,
    min_fraction: float = DEFAULT_MIN_QUALIFYING_FRACTION,
    min_density_fraction: float = MIN_QUALIFYING_DENSITY_FRACTION,
) -> Tuple[bool, str]:
    """
    Shared "is this signal sustained above threshold" check for
    `should_trip_shutdown()`'s thermal (and, when measurable, CPU) legs.
    `history` must be the FULL retained history (e.g. `get_temp_history()`/
    `get_cpu_history()` called with no `max_age_sec`, or an equivalent
    synthetic list in tests) — NOT pre-filtered to `duration_sec`, since
    filtering first would make the span check below trivially always pass
    or always fail regardless of the real data (the filtered window's own
    span is bounded above by the filter itself).

    Two independently-required conditions, not one "N samples above
    threshold" check:
      (a) the MOST RECENT sample must itself be at/above `threshold` — a run
          that was hot for most of the window but has already cooled off by
          the latest tick must not still read as "currently sustained": by
          the time this is evaluated, that condition has already passed.
      (b) walking back from the most recent sample to the oldest sample
          within `duration_sec` of it (the "trailing window"), that window
          must (b1) actually *span* `duration_sec` (oldest-to-newest gap in
          the trailing window, not just "some samples exist somewhere in
          history") — a freshly-restarted daemon (history starts empty on
          every restart — see `should_trip_shutdown()`'s own docstring) with
          only a couple of hot ticks must not trivially satisfy this — and
          (b2) at least `min_fraction` of samples within that window must be
          at/above `threshold` — guards against one cool blip inside an
          otherwise-sustained run resetting a naive "must be unbroken" check
          to zero, and (b3) the window must actually be DENSELY sampled —
          at least `min_density_fraction` of the sample count a genuinely
          continuous run at `EXPECTED_SAMPLE_INTERVAL_SEC` spacing would
          have produced over that span must actually be present. Without
          this, a sparse history (e.g. two samples 25 minutes apart, both
          above threshold — reachable via a run of failed reads that append
          nothing, per `sample_temperature_c()`'s sentinel contract,
          followed by one hot sample after the gap) would satisfy both the
          span check (b1) and a 100%-qualifying-fraction check (b2) despite
          reflecting almost no actual sustained observation.

    Returns `(satisfied, detail)`; `detail` explains the verdict either way,
    for `should_trip_shutdown()`'s own `reason` string.
    """
    if not history:
        return False, "no samples recorded yet"

    newest_ts, newest_val = history[-1]
    if newest_val < threshold:
        return False, (
            f"most recent sample ({newest_val:.1f}) is below threshold "
            f"({threshold}) — not currently sustained regardless of earlier history"
        )

    # Walk backward from the most recent sample, accumulating the qualifying
    # count as we go, and stop at the FIRST (i.e. smallest, most-recent-
    # weighted) window whose span reaches `duration_sec`. This is
    # deliberately NOT "pre-filter to samples newer than `now - duration_sec`,
    # then check that slice's own span" — at a jittery real tick rate
    # (30s +/- loop overhead), a duration-bounded filter's own span can only
    # ever be <= duration_sec, so a `span >= duration_sec` check against it
    # can (almost) never pass in production, only in a hand-placed test with
    # samples at an exact synthetic interval landing precisely on the
    # boundary. Walking the full, unfiltered history and stopping once the
    # accumulated span first reaches `duration_sec` (which, with real
    # jittery ticks, will be slightly ABOVE duration_sec, not exactly equal
    # to it) is what makes this actually satisfiable outside a contrived
    # exact-interval test.
    qualifying = 0
    for offset, (ts, val) in enumerate(reversed(history)):
        if val >= threshold:
            qualifying += 1
        span = newest_ts - ts
        count = offset + 1
        if span >= duration_sec:
            expected_count = max(1.0, span / EXPECTED_SAMPLE_INTERVAL_SEC)
            density = count / expected_count
            if density < min_density_fraction:
                return False, (
                    f"only {count} sample(s) present in the {span:.0f}s trailing "
                    f"window (expected ~{expected_count:.0f} at "
                    f"{EXPECTED_SAMPLE_INTERVAL_SEC:.0f}s spacing, density "
                    f"{density:.0%} < required {min_density_fraction:.0%}) — too "
                    "sparse to conclude sustained"
                )
            fraction = qualifying / count
            if fraction < min_fraction:
                return False, (
                    f"only {fraction:.0%} of samples in the {span:.0f}s trailing "
                    f"window are at/above {threshold} (need >= {min_fraction:.0%})"
                )
            return True, (
                f"{fraction:.0%} of samples over a {span:.0f}s trailing window "
                f"at/above {threshold} (most recent sample {newest_val:.1f})"
            )

    # Exhausted the full retained history without ever reaching the required
    # span — insufficient history to conclude sustained (expected for the
    # first ~duration_sec after any daemon restart, since history is
    # process-global and starts empty; see should_trip_shutdown()'s
    # docstring).
    span = newest_ts - history[0][0]
    return False, (
        f"trailing window only spans {span:.0f}s of the required "
        f"{duration_sec:.0f}s — insufficient history to conclude sustained "
        "(expected for the first ~duration after any daemon restart, since "
        "history is process-global and starts empty)"
    )


@dataclass(frozen=True)
class TripDecision:
    should_trip: bool
    reason: str


def should_trip_shutdown(
    temp_history: Optional[List[Tuple[float, float]]] = None,
    cpu_history: Optional[List[Tuple[float, float]]] = None,
) -> TripDecision:
    """
    Decide whether the daemon should autonomously trigger its own shutdown.

    Thermal leg (always evaluated): a sustained run of temperature samples
    at/above `THERMAL_CONFIG["temp_critical"]` (90°C — the same threshold
    `can_admit()`/`can_dispatch_task()` already use, not a new number)
    spanning at least `THERMAL_CONFIG["shutdown_trip_after_sec"]` (default
    1200s/20min, env-overridable via CODEY_SHUTDOWN_TRIP_AFTER_SEC — see
    utils/config.py). See `_sustained_trailing_run()`'s own docstring for
    exactly what "sustained" requires here.

    CPU leg (conditionally evaluated — Ish's option 3, decided 2026-08-10):
    on THIS device, `get_cpu_history()` is confirmed (NEW-108) to NEVER
    accumulate any samples — `/proc/stat` is permission-denied under
    Termux, and `sample_cpu_percent()` only ever appends a value when it
    actually measured one (see its own docstring), so an EMPTY
    `cpu_history` reliably means "CPU unmeasurable here," not "hasn't
    tripped yet." Whenever `cpu_history` is empty, the thermal leg alone is
    sufficient to trip. This is Ish's explicit, direct decision, not a
    default implementer chose by analogy: the opposite fail-open direction
    (refusing to ever trip because CPU can't be confirmed) would mean a
    genuinely overheating, unsupervised device keeps running hot for
    longer — the exact failure mode this tripwire exists to catch — whereas
    `can_dispatch_task()`'s own CPU-None fail-open (a different function,
    a different consequence direction) only ever makes an "allow new work"
    decision more permissive on a missing signal. On hardware/environment
    where CPU IS actually measurable (`cpu_history` non-empty), the same
    sustained-run check is ALSO required against
    `THERMAL_CONFIG["shutdown_cpu_pct"]` (default 90, env-overridable via
    CODEY_SHUTDOWN_CPU_PCT) as a genuine second leg of the AND — this
    predicate degrades gracefully rather than being permanently
    thermal-only by construction.

    Both `_temp_history` and `_cpu_history` are process-global module state
    (see `sample_temperature_c()`/`sample_cpu_percent()`) — a daemon
    restart clears both, so no trip is possible for at least
    `shutdown_trip_after_sec` after any daemon restart. This is intended,
    not a gap: there is no history persisted across restarts to trip on,
    and a freshly-restarted daemon has no basis for concluding "sustained."

    `temp_history`/`cpu_history` default to reading live module state
    (`get_temp_history()`/`get_cpu_history()`, with no `max_age_sec` filter
    — see `_sustained_trailing_run()`'s docstring for why the FULL history
    must be passed in, not a pre-filtered slice) but are independently
    injectable, matching `can_dispatch_task()`'s own "inject everything"
    test convention — tests should always pass synthetic histories rather
    than depending on this process's real accumulated state. Passing
    `cpu_history=[]` explicitly (as opposed to leaving it `None`, which
    reads live module state) is how a test deterministically exercises the
    "CPU unmeasurable" branch regardless of what this process has actually
    sampled.
    """
    from utils.config import THERMAL_CONFIG

    temp_critical = THERMAL_CONFIG.get("temp_critical", 90)
    duration_sec = THERMAL_CONFIG.get("shutdown_trip_after_sec", 1200)
    cpu_pct_threshold = THERMAL_CONFIG.get("shutdown_cpu_pct", 90)

    if temp_history is None:
        temp_history = get_temp_history()
    if cpu_history is None:
        cpu_history = get_cpu_history()

    thermal_ok, thermal_detail = _sustained_trailing_run(temp_history, temp_critical, duration_sec)
    if not thermal_ok:
        return TripDecision(should_trip=False, reason=f"thermal leg not satisfied: {thermal_detail}")

    if not cpu_history:
        return TripDecision(
            should_trip=True,
            reason=(
                f"sustained thermal trip ({thermal_detail}); CPU unmeasurable on "
                "this device (NEW-108) — thermal alone sufficient per Ish's "
                "2026-08-10 option-3 decision"
            ),
        )

    cpu_ok, cpu_detail = _sustained_trailing_run(cpu_history, cpu_pct_threshold, duration_sec)
    if not cpu_ok:
        return TripDecision(
            should_trip=False,
            reason=(
                f"thermal leg satisfied ({thermal_detail}) but CPU leg not satisfied: "
                f"{cpu_detail} — CPU is measurable here, so both legs of the AND are "
                "required"
            ),
        )

    return TripDecision(
        should_trip=True,
        reason=f"sustained thermal+CPU trip — thermal: {thermal_detail}; CPU: {cpu_detail}",
    )


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


def _state_paths(
    state_dir: Optional[Path],
    state_filename: str = _STATE_FILENAME,
    lock_filename: str = _LOCK_FILENAME,
) -> tuple[Path, Path]:
    """
    `state_filename`/`lock_filename` (§8 Q11, 2026-08-26): overridable so
    `_LockedState` can back a SECOND, independent file-locked store (the
    context-budget reservation ledger below) using the exact same
    lock-then-read-then-write mechanism, rather than inventing a second
    primitive — see `_LockedState`'s own docstring. Defaults are unchanged
    so every existing caller (the model-residency slot store) is
    unaffected.
    """
    base = Path(state_dir) if state_dir is not None else CODEY_STATE_DIR
    base.mkdir(parents=True, exist_ok=True)
    return base / state_filename, base / lock_filename


def _pid_alive(
    pid: int,
    port: Optional[int] = None,
    precomputed: Optional[Dict[Tuple[int, int], bool]] = None,
) -> bool:
    """
    `port` (NEW-432, 2026-09-09): PermissionError from `os.kill(pid, 0)` was
    previously treated as unconditionally "alive" (see that branch's own
    comment). That's right for a genuinely foreign process (we don't own
    it, so we have no stronger signal), but wrong for a resource-gate slot
    whose PID got reused by an unrelated process after the model server we
    registered actually died — the reused PID can legitimately return
    PermissionError too (e.g. owned by a different uid), and we'd wrongly
    keep counting a dead slot as live forever, permanently over-counting
    reserved memory. When a port is available for that slot, use it as a
    second, independent liveness signal via a cross-process HTTP health
    probe (`core/loader_v2.probe_port_health()`) before falling back to the
    old fail-closed behavior. `port=None` (default) callers — the
    TUI-session PID-file check at the bottom of this file has no port
    concept — get byte-for-byte the old behavior.

    `precomputed` (NEW-432 restructure, 2026-09-09, code-reviewer round 2):
    an optional `{(pid, port): is_alive}` map of PermissionError-ambiguous,
    port-bearing PIDs whose port probe was ALREADY DONE, before this call,
    outside of any lock — see `_precheck_port_liveness()`. Keyed on the
    `(pid, port)` PAIR, not bare `pid`: the unlocked precheck read and this
    function's later locked read can observe different slot lists (a slot
    released and a new one registered reusing the same pid with a
    DIFFERENT port between the two reads) — keying on the pair means a
    stale probe result for the old `(pid, old_port)` combination can never
    be mistakenly applied to a new slot that happens to share the same pid
    but a different port.

    `reserve_slot()` and `list_slots()` build this map before acquiring
    `_LockedState`'s flock and pass it in here specifically so the blocking
    HTTP probe never executes while that flock is held (matches this
    file's own documented invariant — see `reserve_slot()`'s and
    `total_reserved_swap_bytes()`'s docstrings on reading slow/uncertain
    signals before the lock).

    Callers that pass a `precomputed` map (i.e. every call made from inside
    a `_LockedState` block) are signalling "we are under the lock — do not
    probe here." If `(pid, port)` isn't in that map (not registered yet at
    pre-check time, or its port changed between the two reads), this does
    NOT fall back to probing fresh — that would reintroduce the exact
    blocking-under-lock latency this restructure exists to eliminate.
    Instead it fails closed to "alive" (skip reaping this pass): the slot
    simply isn't reaped this cycle, but it IS covered by the *next*
    `reserve_slot()`/`list_slots()` call's own pre-lock precheck, so
    nothing is permanently lost, only deferred one cycle. `precomputed=None`
    (the default; this function's own direct unit-test callers, and any
    future non-locked caller) still probes fresh here exactly as before —
    that path never runs under a lock, so it never introduces the guarded
    latency at all.
    """
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists but we don't own it — still alive, matches
        # core/daemon.py:check_pid_file()'s same os.kill(pid, 0) precedent.
        # See docstring above for why `port` can override this to a "dead"
        # verdict when it's available.
        if port is not None:
            if precomputed is not None:
                key = (pid, port)
                if key in precomputed:
                    alive = precomputed[key]
                    if not alive:
                        warning(
                            f"resource_gate: pid {pid} PermissionError and "
                            f"port {port} unreachable (precomputed) — "
                            "treating as dead, reaping"
                        )
                    return alive
                # `precomputed` was supplied (we're inside a locked reap)
                # but this exact (pid, port) pair wasn't precomputed —
                # probing here would block while the flock is held, which
                # is the exact NEW-432 round-2 finding. Fail closed to
                # "alive" this pass instead of probing; the next call's own
                # pre-lock precheck will cover this pair.
                warning(
                    f"resource_gate: pid {pid} PermissionError, port {port} "
                    "not in pre-lock liveness map — treating as alive this "
                    "pass, will be probed on the next pre-lock precheck"
                )
                return True
            # No precomputed map at all — this call isn't under the lock
            # (e.g. a direct/unit-test caller), so probing fresh here is
            # safe.
            # Deferred import: core/loader_v2.py imports core.resource_gate
            # at module top (`import core.resource_gate as rg`), so a
            # top-level import here would be circular.
            from core.loader_v2 import probe_port_health

            if probe_port_health(port):
                return True
            warning(
                f"resource_gate: pid {pid} PermissionError and port {port} "
                "unreachable — treating as dead, reaping"
            )
            return False
        # No port to cross-check against — fail closed exactly as before.
        # This branch is reached routinely and correctly by non-slot
        # callers with no port concept at all (e.g. the TUI-session
        # PID-file check below, checking a genuinely foreign process's
        # PID) — it is NOT itself evidence of a problem. It only becomes
        # the NEW-432 residual gap (a resource-gate slot's dead-PID entry
        # that can never be reaped because it has no recorded port) for
        # `reserve_slot()`/`list_slots()` callers specifically; this log
        # line can't tell those two cases apart, so it's necessarily
        # best-effort noise for the TUI case in exchange for visibility
        # on the slot case (this is the coordinator's known follow-up, not
        # closed by this fix).
        warning(
            f"resource_gate: pid {pid} PermissionError, no port recorded — "
            "cannot cross-check liveness, treating as alive (old behavior)"
        )
        return True
    except OSError:
        # Unexpected OSError from kill(2) (not ProcessLookupError/
        # PermissionError) — cannot positively confirm liveness or death.
        # Fail closed (treat as "still alive", don't reap): this is
        # accounting state for a resource gate whose whole purpose is
        # avoiding over-admission, so wrongly reaping a live slot (which
        # could let a second load be wrongly admitted on top of it) is the
        # worse failure mode here, not a stale entry lingering a bit longer.
        # Deliberately NOT extended with the port-probe tie-break above:
        # this branch is for genuinely unexpected kill(2) failures, not the
        # specific reused-PID/foreign-process ambiguity PermissionError
        # represents — scoped decision, not an oversight.
        return True


def _precheck_port_liveness(state_dir: Optional[Path] = None) -> Dict[Tuple[int, int], bool]:
    """
    NEW-432 restructure (2026-09-09, code-reviewer round 2): the pre-lock
    half of `_pid_alive()`'s port-health tie-break. `probe_port_health()` is
    a blocking HTTP GET (2s timeout) and must never run while
    `_LockedState`'s flock is held — this file already documents that exact
    invariant for other slow/uncertain signals (see `reserve_slot()`'s
    docstring on reading meminfo/thermal before the lock, and
    `total_reserved_swap_bytes()`'s docstring). Probing from inside
    `_pid_alive()` while the lock was held (the original NEW-432 fix) broke
    that invariant: a stale slot with an unreachable port would stall every
    other `reserve_slot()`/`list_slots()`/admission caller for up to 2s per
    dead slot in the reap pass.

    This function takes an UNLOCKED read of the current slot list (via
    `_read_state_locked()`, which despite its name is just a plain
    open+json.load — no flock involved; only `_LockedState` itself takes
    the flock; safe against a torn read because `_write_state_locked()`
    always writes via `mkstemp()` + `os.replace()`, so an unlocked reader
    only ever sees a complete old or complete new file, never a partial
    write), identifies slots whose PID is PermissionError-ambiguous
    (`os.kill(pid, 0)` raises `PermissionError` — a foreign or reused PID,
    not confirmed dead) AND has a recorded port, and probes those ports
    OUTSIDE any lock. Returns a `{(pid, port): is_alive}` map covering only
    those ambiguous, port-bearing pairs — everything else (confirmed-alive,
    confirmed-dead, or no-port PIDs) doesn't need a probe at all and is
    left for the plain `os.kill()` path inside the later locked reap.

    Keyed on the `(pid, port)` PAIR, not bare `pid`: the slot list can
    change between this unlocked read and the later locked read (a slot
    released and a different slot registered reusing the same pid under a
    DIFFERENT port). Keying on the pair means a stale probe result can
    never be misapplied to an unrelated slot that happens to share a pid —
    see `_pid_alive()`'s own docstring for how a pair not found in this map
    is handled (fails closed to "alive this pass", NOT a fresh in-lock
    probe).

    Callers (`reserve_slot()`, `list_slots()`) call this BEFORE entering
    `with _LockedState(...)`, then pass the resulting map into
    `_pid_alive()`'s `precomputed` parameter during the actual locked reap.
    This is intentionally read-only and never mutates or writes the state
    file. Cost: one extra unlocked JSON read plus one `os.kill()` call per
    port-bearing slot on every `reserve_slot()`/`list_slots()` call (the
    latter also reached indirectly via `find_resident_slot()`) —
    microseconds, negligible next to the up-to-2s lock-hold latency this
    exists to avoid.
    """
    state_path, _ = _state_paths(state_dir)
    slots = _read_state_locked(state_path)
    result: Dict[Tuple[int, int], bool] = {}
    for s in slots:
        pid = s.get("pid")
        port = s.get("port")
        if pid is None or port is None:
            continue
        try:
            os.kill(pid, 0)
            continue  # confirmed alive — no probe needed, plain os.kill suffices later
        except ProcessLookupError:
            continue  # confirmed dead — no probe needed either
        except PermissionError:
            pass  # ambiguous — this is the case the probe below resolves
        except OSError:
            # Unexpected kill(2) failure — not the PermissionError ambiguity
            # this helper exists to resolve; leave it to _pid_alive()'s own
            # fail-closed OSError branch inside the lock.
            continue
        # Deferred import: core/loader_v2.py imports core.resource_gate at
        # module top, so a top-level import here would be circular.
        from core.loader_v2 import probe_port_health

        result[(pid, port)] = probe_port_health(port)
    return result


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

    def __init__(
        self,
        state_dir: Optional[Path],
        state_filename: str = _STATE_FILENAME,
        lock_filename: str = _LOCK_FILENAME,
    ):
        self._state_path, self._lock_path = _state_paths(state_dir, state_filename, lock_filename)
        self._lock_fd = None

    def __enter__(self) -> List[dict]:
        import fcntl

        self._lock_fd = open(self._lock_path, "w")
        try:
            fcntl.flock(self._lock_fd, fcntl.LOCK_EX)  # blocking — short critical section
        except BaseException:
            # NEW-80: if flock() raises after the fd is already open, __exit__
            # never runs (the `with` statement's context-manager protocol only
            # calls __exit__ after a successful __enter__), so the opened fd
            # would otherwise leak on every failed lock acquisition. Close it
            # here before re-raising so the caller still sees the original
            # failure. `BaseException` (not `Exception`) deliberately: this is
            # a blocking, no-timeout flock — a short-lived CLI process blocked
            # here can be interrupted by Ctrl-C (`KeyboardInterrupt`, which
            # does not inherit from `Exception`), and that must also close the
            # fd rather than leak it.
            self._lock_fd.close()
            self._lock_fd = None
            raise
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
    swap_bytes_claimed: int = 0,
    n_ctx: Optional[int] = None,
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

    `swap_bytes_claimed` (default 0, `NEW-135`/`NEW-136`): the
    `GateDecision.swap_bytes_claimed` value from whatever admission decision
    justified this slot, if any (0 for a RAM-only admission). Persisted so
    `total_reserved_swap_bytes()`/`reserve_slot()`'s own inline sum can
    later account for it, and so a later reader (a status command, a
    future thermal/swap-pressure responder) can tell which resident slots
    got here via swap assist and by how much — this is `NEW-136`'s own
    fix-direction note acted on directly, as a magnitude rather than a bare
    boolean (see `GateDecision.swap_bytes_claimed`'s own comment for why a
    magnitude, not a bool, is what NEW-135's accounting actually needs).
    Direct callers that don't pass this get 0, i.e. "no swap claimed" —
    existing callers are unaffected.

    `n_ctx` (default None, lease/registry item, 2026-08-26): the context
    size the running (or about-to-run) server was/will be spawned with.
    Existing callers that don't pass it get `None`, matching prior
    behavior exactly. This is the datum `NEW-149`/`NEW-155` needed to be
    detectable at all — before this, a slot recorded `port` but not
    `n_ctx`, so nothing reading the store could tell whether a resident
    server was spawned at the caller's own required ceiling or a smaller
    one a different, earlier caller happened to pick. See
    `find_resident_slot()` below, the query helper this enables.
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
        "swap_bytes_claimed": swap_bytes_claimed,
        "n_ctx": n_ctx,
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
    max_concurrent_budget_bytes: int = MAX_CONCURRENT_MODEL_BUDGET_BYTES,
) -> Tuple[GateDecision, Optional[str]]:
    """
    Atomically decide admission AND register the slot if admitted — the
    single-lock-acquisition replacement for the unsafe pattern of calling
    `total_reserved_bytes()`, then `can_admit()`, then `register_slot()` as
    three separate steps.

    TODO.md 7.4a sub-task C1: this is the one call site that computes the
    real cumulative committed-bytes sum (PENDING + RESIDENT, see
    `_sum_committed_bytes()`) and passes it into `can_admit()`'s
    `concurrent_committed_bytes` — computed INSIDE this function's own lock
    below, on the same already-reaped slot list `reserved` is computed from,
    not via a separate `total_committed_bytes()` call (which would both
    self-deadlock against the lock already held here and reopen the exact
    TOCTOU window this function exists to close — see its own docstring
    just below).

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

    `NEW-135` fix: this is also the one call site that computes the real
    cumulative swap-claim sum (PENDING slots' `swap_bytes_claimed`, mirroring
    `reserved`/`committed` immediately above) and passes it into
    `can_admit()`'s `reserved_swap_bytes` — computed inside this same lock,
    on the same already-reaped slot list, for exactly the TOCTOU reasons
    this function's own docstring already gives for `reserved`/`committed`.
    The admitted decision's own `swap_bytes_claimed` (0 if not
    `admitted_via_swap`) is then persisted onto the new slot record, closing
    the loop for the next racing caller. See `can_admit()`'s
    `reserved_swap_bytes` docstring for the one thing this does NOT fix —
    `can_dispatch_task()`'s separate swap-assist consumer, which registers
    no slot and so has nothing for this mechanism to sum on that side.
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

    # NEW-432 restructure (2026-09-09): pre-lock port-liveness probe pass —
    # see `_precheck_port_liveness()`'s own docstring for why this must
    # happen BEFORE `_LockedState` is entered, not inside it. Skipped
    # entirely when reap_dead is False since nothing below will consult it.
    _port_liveness = _precheck_port_liveness(state_dir) if reap_dead else {}

    with _LockedState(state_dir) as slots:
        if reap_dead:
            slots[:] = [
                s
                for s in slots
                if s.get("pid") is None
                or _pid_alive(s["pid"], port=s.get("port"), precomputed=_port_liveness)
            ]

        # Only PENDING slots count against reserved_bytes — see this
        # section's header comment / total_reserved_bytes()'s docstring for
        # why RESIDENT slots must not also be subtracted here (their cost is
        # already reflected in `meminfo`).
        reserved = sum(
            s.get("cost_bytes", 0)
            for s in slots
            if s.get("status", SLOT_STATUS_PENDING) == SLOT_STATUS_PENDING
        )

        # TODO.md 7.4a sub-task C1 item 3: computed HERE, inside this same
        # lock, on the already-reaped `slots` list — NOT via a separate
        # total_committed_bytes() call (which acquires its own lock and
        # would both self-deadlock against the lock already held here and
        # reopen the exact TOCTOU window this function exists to close).
        #
        # NEW-261 (found during Option C live-verification, 2026-08-27):
        # If this reservation specifies a port, an existing slot on that exact
        # same port cannot run concurrently with this reservation (the port
        # is exclusive, and will either be reused or killed+replaced on upgrade).
        # Exclude same-port slots from the concurrent sum so an upgrade from
        # a smaller resident model to a larger model isn't falsely rejected
        # as a concurrent dual-model load exceeding MAX_CONCURRENT_MODEL_BUDGET_BYTES.
        concurrent_slots = [s for s in slots if s.get("port") != port] if port is not None else slots
        committed = _sum_committed_bytes(concurrent_slots)

        # NEW-135 fix: same PENDING-only filter as `reserved` above, summing
        # `swap_bytes_claimed` instead of `cost_bytes` — the swap-assist
        # capacity other in-flight admissions have already claimed. See
        # `total_reserved_swap_bytes()` for the equivalent computed outside
        # this lock, for direct `can_admit()` callers other than this one.
        reserved_swap = sum(
            s.get("swap_bytes_claimed", 0)
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
            concurrent_committed_bytes=committed,
            max_concurrent_budget_bytes=max_concurrent_budget_bytes,
            reserved_swap_bytes=reserved_swap,
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
                # NEW-135/NEW-136: persist the magnitude this admission
                # actually claimed (0 if not admitted_via_swap) so the next
                # racing reserve_slot() call's `reserved_swap` sum above sees
                # it, and so a later reader can tell which resident slots
                # got here via swap and by how much.
                "swap_bytes_claimed": decision.swap_bytes_claimed,
                # Lease/registry item, 2026-08-26 (NEW-149/NEW-155): persist
                # the n_ctx this admission was computed against, so a later
                # caller can detect (via find_resident_slot()) that a
                # resident server was sized for a smaller ceiling than it
                # itself needs, instead of silently reusing it with no way
                # to tell.
                "n_ctx": spec.n_ctx,
            }
        )
        return decision, slot_id


def mark_resident(
    slot_id: str, state_dir: Optional[Path] = None, pid: Optional[int] = None
) -> bool:
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

    `pid` (optional): rebind the slot's `pid` field at the same time,
    atomically, inside the same lock. Fixes NEW-81 — `reserve_slot()` is
    always called BEFORE the real model subprocess is spawned (the gate has
    to admit the load before anything is started), so the slot is initially
    registered under the *caller's own* PID (`reserve_slot()`'s
    `if pid is None: pid = os.getpid()` default), e.g. the long-lived daemon
    process, not the short-lived `llama-server` child it's about to spawn.
    `_pid_alive()`-based reaping (`reserve_slot()`, `release_slot()`,
    `list_slots()`) therefore keeps checking the daemon's own (still-alive)
    PID forever, even after the actual model process crashes — the slot's
    declared cost is never reaped. Callers that know the real subprocess PID
    by the time the load is confirmed (i.e. every real caller —
    `core/loader_v2.py`'s `confirm_resident_and_mark_slot()`, formerly
    shared with `core/planner_loader.py` before that module was deleted in
    M1-D, 2026-08-23) should pass it here so PID-liveness
    reaping actually tracks the process whose death should free the slot.
    Omitting `pid` (the default) leaves whatever PID the slot was registered
    under untouched — existing callers that don't pass it keep today's
    behavior exactly.
    """
    found = False
    with _LockedState(state_dir) as slots:
        for s in slots:
            if s.get("slot_id") == slot_id:
                s["status"] = SLOT_STATUS_RESIDENT
                if pid is not None:
                    s["pid"] = pid
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
    # NEW-432 restructure (2026-09-09): pre-lock port-liveness probe pass —
    # see `_precheck_port_liveness()`'s own docstring for why this must
    # happen BEFORE `_LockedState` is entered, not inside it. Skipped
    # entirely when reap_dead is False since nothing below will consult it.
    _port_liveness = _precheck_port_liveness(state_dir) if reap_dead else {}

    with _LockedState(state_dir) as slots:
        if reap_dead:
            live = [
                s
                for s in slots
                if s.get("pid") is None
                or _pid_alive(s["pid"], port=s.get("port"), precomputed=_port_liveness)
            ]
            slots[:] = live
        return list(slots)


def find_resident_slot(
    model_id: str,
    port: Optional[int] = None,
    state_dir: Optional[Path] = None,
    reap_dead: bool = True,
) -> Optional[dict]:
    """
    Lease/registry item (2026-08-26, absorbs `NEW-104`/`NEW-144`/`NEW-146`/
    `NEW-149` per `CODEY_MASTER_PLAN.md` §6.2's Appendix A entry): the query
    half of "is a specific model already resident, and if so, at what
    `n_ctx`/`pid`/`port`?" — the question every port-probe adoption branch
    in this codebase (`core/loader_v2.py:LlamaServer.start()`'s reuse
    branch, `core/embed_server.py:EmbedServer.start()`'s kill-and-replace
    branch) was previously answering with a raw TCP/HTTP probe instead of
    this store, the store already being the single source of truth for
    everything else about slot ownership. Deliberately reuses the existing
    slot store/lock rather than inventing a second lease-file format — see
    this section's header comment for why RESIDENT is the right status to
    filter on here (a PENDING slot is an in-flight reservation, not yet a
    real running server to adopt).

    Returns the first matching RESIDENT slot dict (or `None` if none
    found), matched on `model_id` and, if given, `port` too — callers that
    know the exact port they're about to bind to (the normal case: a fixed
    per-role port like `PRIMARY_SERVER_PORT`/`EMBED_SERVER_PORT`) should
    pass it, since `model_id` alone is not guaranteed unique if a future
    caller ever registers more than one slot for the same role.

    `reap_dead` (default True, explicit rather than a bare default per
    NEW-187's review-pass precedent on this section's other read helpers):
    forwarded to the same PID-liveness reap `list_slots()` already does,
    so a slot whose owning PID has since died is never returned as a live
    adoption target.
    """
    for slot in list_slots(state_dir=state_dir, reap_dead=reap_dead):
        if slot.get("status") != SLOT_STATUS_RESIDENT:
            continue
        if slot.get("model_id") != model_id:
            continue
        if port is not None and slot.get("port") != port:
            continue
        return slot
    return None


# TCP state 0A = LISTEN, per /proc/net/tcp's documented state codes.
_TCP_STATE_LISTEN = "0A"


def resolve_port_owner_pid(port: int) -> Optional[int]:
    """
    Resolve the exact PID bound to `port` via a `/proc/net/tcp[6]` +
    `/proc/*/fd` scan. Generalized (2026-08-26, lease/registry item) from
    `core/embed_server.py:_find_port_occupant_pid()`'s original
    embed-server-only implementation, so `core/loader_v2.py`'s coder
    adoption path can identify a genuinely-adopted (never-registered-by-
    this-process) server's real PID the same positively-identified way
    `embed_server.py`'s kill path already does, rather than each caller
    growing its own copy of this scan. Returns `None` if no owning PID
    could be positively identified — callers must never fall back to a
    name-based anything in that case (CLAUDE.md rule 3).

    **Confirmed platform limitation (2026-08-26, `NEW-200`, read directly
    against this actual device per rule 12 — not assumed from `embed_
    server.py`'s own pre-existing "can be unreadable on some Termux/Android
    configurations" comment):** on this project's real target device,
    `/proc/net/tcp`/`/proc/net/tcp6` are `PermissionError` — not merely
    absent — for EVERY caller, including a process reading about its own
    sockets. This degrades safely (returns `None`, exactly as designed)
    rather than crashing, but it means this function's PRIMARY path
    (finding a truly-foreign PID with no pre-existing resource-gate slot
    to fall back to) will essentially never succeed in production on this
    device — only a caller with a real fallback path independent of this
    scan (`embed_server.py`'s `_find_pid_via_registered_slot()`, or this
    module's own `find_resident_slot()`, both of which read the
    resource-gate's own slot store instead of the OS) can positively
    identify a port's occupant here. Kept as the primary path anyway for
    portability to a rooted device or a non-Android deployment where
    `/proc/net/tcp` IS readable — but a caller relying on this function
    ALONE to resolve a genuinely-unregistered foreign process on THIS
    device should not expect it to succeed. See `NEW-200` for the full
    finding and its practical consequence for `NEW-104`'s original
    "true foreign adoption, no lease at all" case.
    """
    try:
        port_hex = f"{port:04X}"
        candidates: List[Tuple[str, str]] = []  # (state, inode), LISTEN first
        for proc_file in ("/proc/net/tcp", "/proc/net/tcp6"):
            try:
                with open(proc_file) as f:
                    lines = f.readlines()
            except (FileNotFoundError, PermissionError):
                continue
            for line in lines[1:]:  # skip header
                parts = line.split()
                if len(parts) < 10:
                    continue
                local_addr, state, inode = parts[1], parts[3], parts[9]
                if local_addr.endswith(f":{port_hex}"):
                    candidates.append((state, inode))
        candidates.sort(key=lambda c: 0 if c[0] == _TCP_STATE_LISTEN else 1)

        for _state, inode in candidates:
            pid = _pid_owning_inode(inode)
            if pid is not None:
                return pid
    except Exception as e:
        warning(f"resource_gate: /proc scan for port {port} occupant failed: {e}")
    return None


def _pid_owning_inode(inode: str) -> Optional[int]:
    """Scan /proc/*/fd for the PID holding a socket inode."""
    try:
        for pid_dir in Path("/proc").iterdir():
            if not pid_dir.name.isdigit():
                continue
            try:
                for fd in (pid_dir / "fd").iterdir():
                    link = os.readlink(str(fd))
                    if f"socket:[{inode}]" in link:
                        return int(pid_dir.name)
            except (PermissionError, OSError):
                continue
    except Exception:
        pass
    return None


def pid_cmdline_contains(pid: int, needle: bytes) -> bool:
    """
    True if `/proc/<pid>/cmdline` contains `needle`. Used to positively
    confirm an unfamiliar PID is actually a `llama-server` process before
    treating it as an adoption target (mirrors
    `embed_server.py:_cmdline_is_llama_server()`, generalized here so
    `loader_v2.py`'s coder-adoption path can use the identical check
    rather than a second copy of it).
    """
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            cmdline = f.read()
        return needle in cmdline
    except Exception:
        return False


def resolve_spawned_n_ctx(pid: int) -> Optional[int]:
    """
    Best-effort: parse the `-c <n_ctx>` argument out of `/proc/<pid>/cmdline`
    for a process this project itself spawned via `LlamaServer._spawn_locked()`
    (see `core/loader_v2.py`, which always passes `["-c", str(self.n_ctx)]`
    verbatim on that binary's command line — confirmed live-readable this
    way in the 7.4b live-verification pass, `~/.codeyOS/llama-server.log:1`'s
    spawn line, per CLAUDE.md rule 12's "read the artifact" bar). Returns
    `None` if the cmdline can't be read, has no `-c` argument, or the
    following argument isn't an integer — callers must treat `None` as
    "unknown," never as "0" or any other assumed value.

    `/proc/<pid>/cmdline` is NUL-separated argv, not shell-quoted text —
    parsed accordingly (split on `\\x00`, look for the exact `-c` token,
    read the next token) rather than with a text/regex parse that would
    mis-split on embedded spaces in another argument.
    """
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            raw = f.read()
    except Exception:
        return None
    args = [a.decode("utf-8", errors="replace") for a in raw.split(b"\x00") if a]
    for i, arg in enumerate(args):
        if arg == "-c" and i + 1 < len(args):
            try:
                return int(args[i + 1])
            except ValueError:
                return None
    return None


# ── Signal source 5: interactive-session activity (TUI) ─────────────────────
# Track 3 Phase 5a / 7.4 sub-task B. "Is a human actively watching a TUI
# session right now." The GUI half of this signal was removed 2026-09-02
# with the GUI itself — see is_interactive_session_active() for why it was
# removed outright rather than left as a dead always-False branch.
#
# Only the signal/predicate itself is built here — NOT wired into any
# daemon dispatch decision (that's 7.4 sub-task C, out of scope for this
# sub-task, mirroring how get_resource_snapshot() above was built without
# being wired into admission/gating).


def is_tui_session_active(sessions_dir: Optional[Path] = None) -> bool:
    """
    True if any per-session file under main.py's interactive-session
    directory (utils.config.TUI_SESSIONS_DIR — one file per PID, written
    as `_write_tui_pid_file()`'s `TUI_SESSIONS_DIR / f"{pid}.pid"`, called
    around `main()`'s `repl(...)` call site, and removed by that same PID's
    `_remove_tui_pid_file()` in that call site's `finally`) currently names
    a still-live PID.

    One file per session, not one shared file, is deliberate: two
    concurrent interactive sessions are a normal, supported case here
    (e.g. two terminals — see `_write_tui_pid_file()`'s docstring), and a
    single shared file cannot hold two sessions' presence at once —
    whichever session wrote (or crashed, or was reaped as stale) last
    would silently erase the other session's still-live signal. Per-PID
    filenames make ownership structural instead: a session can only ever
    write/remove its own path, so no read-back-and-compare ownership check
    is needed anywhere in this signal.

    Reaping still mirrors core/daemon.py:check_pid_file()'s staleness-check
    intent (os.kill(pid, 0) liveness check, self-healing removal of a
    stale/corrupt entry) — just applied per-entry across every file in the
    directory instead of a single path. One difference from
    check_pid_file(): there is no "this is my own PID, that's expected"
    special case, because this function's only real caller (the daemon, in
    a later sub-task) is always a different process than the TUI
    session(s) it's checking on. No flock is taken on read here (unlike
    check_pid_file()'s shared-lock read): `_write_tui_pid_file()` writes
    each entry via a temp file + os.replace() in the same directory, which
    is atomic, so a reader here can never observe a partially-written
    entry to lock against in the first place — an entry either doesn't
    exist yet, or is fully written.
    """
    if sessions_dir is None:
        from utils.config import TUI_SESSIONS_DIR

        sessions_dir = TUI_SESSIONS_DIR

    if not sessions_dir.exists():
        return False

    try:
        entries = list(sessions_dir.iterdir())
    except OSError:
        # Could not even list the directory — fail closed toward "treat as
        # active" (the safe direction for a caller deciding whether to
        # defer background work), same fail-closed posture as the
        # per-entry read-failure branch below.
        return True

    any_live = False
    for entry in entries:
        # Skip _write_tui_pid_file()'s own in-progress/orphaned temp files
        # (".{pid}.tmp") — either not yet renamed into place via
        # os.replace(), or an orphan left behind by a SIGKILL between the
        # temp write and that rename (see _write_tui_pid_file()'s
        # docstring for why that's bounded to one file per PID and
        # self-corrects on that PID's next write, rather than something
        # this function needs to reap). Either way, not yet a real entry.
        if not entry.is_file() or entry.name.startswith("."):
            continue
        try:
            raw = entry.read_text().strip()
        except OSError:
            # Could not even open this entry to check it — fail closed
            # toward "treat as active" for this entry, the safe direction
            # for a caller deciding whether to defer background work.
            # Note this is a weaker guarantee than "transient" for a lone
            # orphaned entry (e.g. permissions changed on a dead session's
            # file after the fact, with no writer left to ever fix it):
            # such an entry can never be reaped via this branch, since
            # reaping requires a successful read. In practice this signal
            # is only ever consulted live rather than cached, so a wedged
            # entry here means one specific stale file is over-counted as
            # active, not that the whole signal is stuck — other entries
            # are still evaluated normally, and a genuinely dead PID with
            # a readable entry is still reaped below.
            any_live = True
            continue

        try:
            pid = int(raw)
        except ValueError:
            warning(f"resource_gate: TUI session file {entry} unreadable, treating as stale")
            entry.unlink(missing_ok=True)
            continue

        if _pid_alive(pid):
            any_live = True
        else:
            warning(f"resource_gate: removing stale TUI session file {entry}")
            entry.unlink(missing_ok=True)

    return any_live


def is_interactive_session_active(
    tui_sessions_dir: Optional[Path] = None,
) -> bool:
    """
    "Is a human actively using Codey-OS's TUI right now" signal. Consumed
    by 7.4 sub-task C to decide whether the daemon should defer background
    work while a user is actively watching.

    **The GUI half of this signal was removed 2026-09-02** along with the
    GUI itself (Ish's decision; the web dashboard replaces it). This was
    deliberately a removal rather than a vestigial always-False branch,
    because the old `is_gui_client_connected()` had a live trap: with a
    stale `gui-clients.count` holding a nonzero value and no
    `gui-server.pid` to cross-check against, it returned True
    unconditionally — which would have deferred ALL background dispatch
    forever. With no process left to write that count file, keeping the
    read path would have been a permanent, silent hazard. If a GUI is ever
    reintroduced, restore the signal WITH a freshness/liveness guard that
    does not fail open.
    """
    return is_tui_session_active(tui_sessions_dir)


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


def total_reserved_swap_bytes(state_dir: Optional[Path] = None, reap_dead: bool = True) -> int:
    """
    `NEW-135` fix: sum of `swap_bytes_claimed` across currently-registered,
    live, SLOT_STATUS_PENDING slots ONLY — the value to pass as
    `can_admit()`'s `reserved_swap_bytes` for any direct caller that isn't
    `reserve_slot()` (which computes this same sum itself, inside its own
    lock — see its docstring for why that matters and why this function
    must NOT be called from inside that lock). Mirrors
    `total_reserved_bytes()` exactly, summing `swap_bytes_claimed` instead
    of `cost_bytes`; same PENDING-only filter, on the same INHERITED
    assumption `total_reserved_bytes()`'s own RAM-side filter rests on (a
    RESIDENT slot's swap usage, if any, is already reflected in a
    subsequent live `SwapFree` read) — not independently measured for the
    swap case specifically. This holds only if callers respect
    `mark_resident()`'s own documented precondition (only mark RESIDENT
    once the load's real memory footprint has actually landed) — the same
    class of "believed true, not measured" claim `NEW-180` (embed model's
    real resident RSS still unmeasured) is already open on for the RAM
    side. A slot with no `swap_bytes_claimed` field at all (state written
    before this field existed, or a RAM-only admission) is treated as 0.
    """
    return sum(
        s.get("swap_bytes_claimed", 0)
        for s in list_slots(state_dir=state_dir, reap_dead=reap_dead)
        if s.get("status", SLOT_STATUS_PENDING) == SLOT_STATUS_PENDING
    )


def _sum_committed_bytes(slots: List[dict]) -> int:
    """
    Pure sum of `cost_bytes` across EVERY entry in `slots` (already reaped
    of dead-PID entries by the caller, if desired) — deliberately the
    OPPOSITE filter from `total_reserved_bytes()`/the `reserved` computation
    above: this sums PENDING AND RESIDENT slots together, not PENDING only.

    This is a declared-cost POLICY sum against a fixed named ceiling
    (MAX_CONCURRENT_MODEL_BUDGET_BYTES), not a live-`MemAvailable`-
    double-counting guard — `total_reserved_bytes()`'s PENDING-only filter
    exists specifically to avoid double-counting a RESIDENT slot's cost
    against a fresh meminfo read (that slot's memory footprint is already
    reflected there); this sum never touches meminfo at all, so that
    concern doesn't apply here — a RESIDENT slot's declared cost is exactly
    as real a claim against the fixed device-wide budget as a PENDING one.

    Takes a plain in-memory list, not `state_dir`/a lock — kept separate
    from `total_committed_bytes()` (below) specifically so `reserve_slot()`
    can call this directly on the slot list it already holds inside its own
    `_LockedState` block, without acquiring a second, nested lock on the
    same non-reentrant flock (which would self-deadlock).

    Assumes every slot in the store carries a real `cost_bytes` — true for
    every write this module itself makes (`reserve_slot()`'s own append,
    `core/resource_gate.py`, always populates `cost_bytes:
    decision.estimated_cost_bytes`) and positionally required (no default)
    by `register_slot()`'s own signature — but if some future caller ever
    calls `register_slot()` with `cost_bytes=0`, this sum silently
    undercounts and the ceiling fails open. Documented here rather than
    defended against with new code this sub-task didn't ask for.
    """
    return sum(s.get("cost_bytes", 0) for s in slots)


def total_committed_bytes(state_dir: Optional[Path] = None, reap_dead: bool = True) -> int:
    """
    Sum of declared `cost_bytes` across every currently-registered, live
    slot — PENDING and RESIDENT together (see `_sum_committed_bytes()`'s
    docstring for why this is the opposite filter from
    `total_reserved_bytes()`). This is the value to pass as `can_admit()`'s
    `concurrent_committed_bytes` for any direct caller that isn't
    `reserve_slot()` (which computes this same sum itself, inside its own
    lock — see its docstring for why that matters and why this function
    must NOT be called from inside that lock).
    """
    return _sum_committed_bytes(list_slots(state_dir=state_dir, reap_dead=reap_dead))


# ── Context-budget admission (§8 Q11 / NEW-206 fix, 2026-08-26) ─────────────
# Ish's decision (CODEY_MASTER_PLAN.md §8 Q11, ANSWERED 2026-08-26): the real
# shared `llama-server` (kv_unified=true, n_parallel=4) fails EVERY in-flight
# request hard — not gracefully — when two concurrent requests' combined
# context oversubscribes its shared KV pool (NEW-206, live-reproduced). Fix
# direction: (c) the resource gate refuses admission once combined estimated
# context would approach the shared pool, with (b) wired directly behind it
# so a refusal becomes a serialization wait, not an outright rejection — one
# mechanism, two behaviors (`reserve_context_budget()` is (c);
# `wait_and_reserve_context_budget()` layers (b) on top of it).
#
# This is a SECOND, independent file-locked store (`_CONTEXT_STATE_FILENAME`/
# `_CONTEXT_LOCK_FILENAME`), not a new coordination primitive: it reuses
# `_LockedState` exactly as-is (see that class's own docstring and
# `_state_paths()`'s `state_filename`/`lock_filename` overrides added
# above), the same way the model-residency slot store already keeps its
# lock file as a separate, always-empty sibling of its payload file. Kept
# as a separate JSON file from the model-slot store (not additional entries
# tagged onto the same list) so the byte-accounting sums this file already
# relies on (`total_reserved_bytes()`, `_sum_committed_bytes()`, etc.) can
# never accidentally sum a context-token reservation's fields as if they
# were another model-load's `cost_bytes` — the two domains (bytes of RAM,
# tokens of KV-pool context) must never mix in one arithmetic sum.
#
# The reservation ledger this section builds is deliberately NOT the sole
# source of truth on real KV-pool occupancy — a second design-review pass
# (source-checked against `~/llama.cpp/tools/server/server-context.cpp`)
# found that a normal request's cached prompt tokens stay resident after
# the HTTP call returns (`slot::release()`'s `reset()` does not clear them,
# for prefix-cache reuse), so a per-call reservation that is the only signal
# would under-count real occupancy for the dominant multi-turn case. Instead:
# the server's own `/slots` endpoint (already enabled by default —
# `params.endpoint_slots = true`, never disabled by this project's spawn
# command in `core/loader_v2.py`) is polled fresh at each admission check and
# its `n_prompt_tokens` field summed across slots (confirmed real, from
# `slot::to_json()`) as the AUTHORITATIVE occupancy signal. This ledger's
# only job is to close the TOCTOU window between one caller's admission
# check and that caller's request actually reaching the server — i.e. the
# gap /slots cannot see into because the request hasn't been sent yet — not
# to track occupancy for a request's entire lifetime. That is also why
# releasing a reservation once its own HTTP call returns is correct here
# (see `release_context_budget()`'s own docstring), unlike
# the design round's original, rejected "release on HTTP-return" idea, which
# was wrong for a different reason (using per-call release as the ONLY
# accounting signal, with no live /slots check backing it up for the time
# the call is actually in flight).

# Fraction of n_ctx witheld as a fragmentation-safe margin: an admission is
# refused once combined estimated context (server-reported /slots occupancy
# + this process's own in-flight-but-not-yet-dispatched reservations + the
# candidate request's own prompt+generation estimate) would exceed
# `n_ctx * (1 - CONTEXT_BUDGET_SAFETY_MARGIN_FRACTION)`. 0.15 (not something
# razor-thin like 0.02-0.05) is deliberate: NEW-206's own source-reading of
# the real allocator (`llama-kv-cache.cpp:894-1084`) found the failure mode
# is KV-cache FRAGMENTATION (a contiguous-allocation requirement can fail
# even when the total free-cell count elsewhere would suffice), not a bare
# linear sum-vs-total check — so a margin that only just clears 100% of
# nominal capacity would still leave the exact non-contiguous-free-space
# scenario NEW-206 flagged as untested (and which Ish explicitly declined to
# spend a live 65536 re-run confirming, see §8 Q11's own entry) free to
# still trigger the cascade this fix exists to prevent. 15% is a first-pass,
# UN-CALIBRATED default reasoned from that risk, in the same voice as this
# module's other first-pass constants (REQUIRED_HEADROOM_FACTOR,
# DEVICE_CEILING_USABLE_FRACTION) — not derived from a controlled set of
# real on-device fragmentation measurements, which the design round noted
# were never run. A future live pass that actually measures how much
# contiguous headroom `find_slot()` needs in practice should retune this,
# not treat it as settled.
CONTEXT_BUDGET_SAFETY_MARGIN_FRACTION = 0.15

# How often wait_and_reserve_context_budget() retries after a refusal.
# 2.0s matches this module's own existing short-HTTP-probe timeout
# (check_health()-style precedent) — frequent enough that a typical
# request's ~8-9% pool footprint (§8 Q11's own typical-footprint check)
# clears within a few retries once the blocking occupant's turn ends,
# without hammering the server with continuous /slots polls. Deliberately
# NOT FIFO-fair (documented, accepted tradeoff from the design round): two
# waiters race on each retry tick, and whichever's reserve_context_budget()
# call wins the lock first is admitted first — not a bug to fix here.
CONTEXT_QUEUE_POLL_INTERVAL_SECONDS = 2.0

# Hard cap on wait_and_reserve_context_budget()'s own timeout, regardless of
# what compute_context_queue_timeout_seconds()'s formula would otherwise
# compute (which can reach ~110 minutes at production's real n_ctx=65536 —
# see that function's own docstring). The cap exists because both real call
# sites this queue wraps are themselves bounded by an ENCLOSING timeout that
# a full formula-sized wait would blow through before the admitted request
# even got a chance to run:
#   - core/task_executor.py's background-dispatch path (inference_hybrid.py)
#     is wrapped in a 1800s asyncio.wait_for() around the ENTIRE task
#     (core/daemon.py's dispatch loop, core/daemon_config.py's
#     DEFAULT_CONFIG["tasks"]["task_timeout"]) — a queue wait plus the
#     actual inference call both have to fit inside that one 1800s budget.
#   - core/plannd.py's plan_only RPC path is wrapped in
#     core/daemon.py's own asyncio.wait_for(inner_timeout + 30.0) around the
#     HTTP call (compute_planner_timeout()'s own docstring) — this task's
#     wiring extends that outer_timeout to also cover a pre-request queue
#     wait (see core/plannd.py's own get_plan() wiring comment), so the cap
#     here keeps that extension bounded too.
# 600.0s (10 minutes) leaves >= 1200s (20 minutes) of the 1800s task-timeout
# budget for the actual admitted call afterward on the background-dispatch
# path — generous margin, not razor-thin — while still being long enough
# that a typical (~8-9% pool footprint) request queued behind one or two
# similarly-typical in-flight requests should clear well before the cap in
# practice. Like CONTEXT_BUDGET_SAFETY_MARGIN_FRACTION, this is a first-pass,
# un-calibrated value reasoned from the enclosing timeouts' own numbers, not
# from a real measured queue-clearing time — a future live pass should
# retune it against actual observed wait durations, not treat it as settled.
CONTEXT_QUEUE_TIMEOUT_CAP_SECONDS = 600.0

# How long a context-budget reservation record is honored before this
# module's own reaping treats it as stale and drops it, REGARDLESS of
# whether its owning PID is still alive — a defense-in-depth backstop for a
# reservation whose owning process is alive but which itself leaked (crashed
# out of its own try/finally before calling release_context_budget(), a bug
# in a future caller, etc.), since `_pid_alive()`-based reaping alone cannot
# catch that case (the daemon process itself stays alive for the record's
# entire life; only the one in-flight HTTP call the reservation was for
# would have died). 1800s matches core/daemon_config.py's own
# DEFAULT_CONFIG["tasks"]["task_timeout"] — the longest any single real
# request this ledger tracks is itself allowed to run before the daemon's
# own watchdog would have killed it, so a reservation older than that is
# never a legitimately-still-running request, only a leak.
CONTEXT_RESERVATION_MAX_AGE_SECONDS = 1800.0

# Timeout for the two short, best-effort HTTP calls this section makes
# against the live server (/slots, /tokenize). 2.0s for /slots matches this
# module's own check_health()-equivalent precedent elsewhere in this
# codebase (core/inference_hybrid.py:ChatCompletionBackend.check_health());
# /tokenize gets a slightly longer budget (5.0s) since it does real
# tokenization work proportional to prompt length, not a fixed-cost health
# ping.
SLOTS_ENDPOINT_TIMEOUT_SECONDS = 2.0
TOKENIZE_ENDPOINT_TIMEOUT_SECONDS = 5.0

# core/tokens.py's estimate_tokens()/estimate_messages_tokens() are used here
# ONLY as the fallback when the server's own /tokenize endpoint is
# unreachable — see estimate_prompt_tokens()'s own docstring for why. Called
# with no `path` argument (this call site has no file path to give it), that
# heuristic always uses the ~4-chars/token prose ratio, never the
# ~3-chars/token code ratio the same function uses when it DOES get a path —
# under-counting a code-heavy prompt (the common case here: agent prompts
# are full of source code) by roughly a third. That is the DANGEROUS
# direction for a safety check whose whole purpose is not under-admitting
# combined demand, so the heuristic estimate (never the /tokenize-endpoint
# one, which needs no such correction) is padded before use — the same
# "pad the estimate conservatively, not the signal" pattern
# REQUIRED_HEADROOM_FACTOR already established in this module. An
# un-calibrated first default, not measured against real code-vs-prose
# prompt mixes.
CONTEXT_HEURISTIC_FALLBACK_PADDING_FACTOR = 1.35

_CONTEXT_STATE_FILENAME = "resource_gate_context_budget.json"
_CONTEXT_LOCK_FILENAME = "resource_gate_context_budget.lock"


def resolve_effective_n_ctx(
    model_id: str, port: int, state_dir: Optional[Path] = None
) -> Optional[int]:
    """
    Resolve the shared server's REAL, currently-spawned `n_ctx` — never a
    config default — for a context-budget admission check to divide against.

    This function exists because of a concrete failure mode a reviewer
    identified directly against this fix's own regression case: `NEW-206`'s
    own live test ran with `CODEY_N_CTX=8192` while a fresh process's
    `MODEL_CONFIG["n_ctx"]` import would read production's real default,
    65536 — an admission check that budgeted against `MODEL_CONFIG["n_ctx"]`
    directly would silently no-op on exactly the override path the finding
    was reproduced on. `find_resident_slot()`'s persisted `n_ctx` field
    (populated at real spawn time by `core/loader_v2.py`'s
    `rg.reserve_slot(spec)`/`rg.register_slot(..., n_ctx=...)` calls,
    NEW-149/NEW-155's own lease/registry item) is the one value in this
    codebase that reflects what a server was ACTUALLY spawned with,
    regardless of what any later reader's own config import says — so it is
    tried first, ahead of a live `/proc/<pid>/cmdline` re-derivation
    (`resolve_spawned_n_ctx()`, kept as a secondary path for the case where
    no slot is registered at all, though `resolve_port_owner_pid()`'s own
    docstring notes this device's `/proc/net/tcp` is permission-denied for
    every caller, so that secondary path will rarely resolve anything here
    in practice — kept anyway for portability to a device where it can).

    Returns `None` if neither source can resolve a real value —
    `reserve_context_budget()`'s caller-facing contract for that case is to
    REFUSE admission rather than silently fall back to `MODEL_CONFIG["n_ctx"]`
    (CLAUDE.md rule 12: never guess at an external artifact's real state from
    a value that could disagree with it) — see that function's own docstring.
    """
    slot = find_resident_slot(model_id=model_id, port=port, state_dir=state_dir)
    if slot is not None:
        n_ctx = slot.get("n_ctx")
        if n_ctx:
            return int(n_ctx)
    pid = resolve_port_owner_pid(port)
    if pid is not None:
        n_ctx = resolve_spawned_n_ctx(pid)
        if n_ctx is not None:
            return n_ctx
    return None


# NEW-431: number of attempts _fetch_slots_prompt_tokens() makes before
# giving up and returning None — a single transient blip (a GC pause, a
# momentarily-busy event loop on the server side) must not immediately
# force reserve_context_budget()'s fail-closed refusal path; a second,
# quick retry absorbs that without meaningfully widening the TOCTOU window
# this whole admission check exists to close.
SLOTS_ENDPOINT_MAX_ATTEMPTS = 2
# Gap between the two attempts above. Deliberately short — this whole poll
# already happens outside the ledger's lock (see reserve_context_budget()'s
# own docstring) specifically so it can't stall other callers, and a slow
# retry gap would erode that.
SLOTS_ENDPOINT_RETRY_GAP_SECONDS = 0.5


def _fetch_slots_prompt_tokens(
    host: str,
    port: int,
    timeout: float = SLOTS_ENDPOINT_TIMEOUT_SECONDS,
    max_attempts: int = SLOTS_ENDPOINT_MAX_ATTEMPTS,
    retry_gap_seconds: float = SLOTS_ENDPOINT_RETRY_GAP_SECONDS,
    sleep_fn=time.sleep,
) -> Optional[int]:
    """
    Poll the live server's `/slots` endpoint and sum `n_prompt_tokens`
    across every slot that is actively `is_processing` — the
    AUTHORITATIVE, freshly-measured occupancy signal this section's header
    comment describes (candidate 1 from §8 Q11's design round, confirmed
    viable there: `slot::to_json()`'s real fields, the endpoint enabled by
    this project's own default spawn command).

    NEW-435: `n_prompt_tokens` is NOT cleared when a slot is released — the
    real server (confirmed against llama.cpp's tools/server/server-context.cpp)
    keeps reporting the last-served request's token count on an idle slot
    indefinitely, until that slot serves its next request. Summing
    `n_prompt_tokens` unconditionally therefore overcounts occupancy by
    whatever every idle-but-previously-used slot last served. `is_processing`
    (present on every slot, always) is the field that actually reflects true
    occupancy, with no meaningful lag — it's updated synchronously in the
    same single-threaded inference loop that serves `/slots` itself. Only
    slots with `is_processing is True` contribute their `n_prompt_tokens`;
    a slot whose `is_processing` is missing or not a real bool is treated
    as schema drift and counted anyway (fails closed, warns) rather than
    silently assumed idle — see this function's safety-relevant-code note
    below.

    Makes up to `max_attempts` tries (NEW-431), each with its own
    `timeout`-second budget and a short `retry_gap_seconds` sleep between
    attempts, before giving up — a bounded retry against one transient
    blip, not a long/unbounded backoff.

    Returns `0` whenever every attempt succeeds and no slot is actively
    processing — a genuinely idle pool (or no slots at all) is the normal,
    expected case post-NEW-435, not a suspicious value. Returns `None`
    only when every attempt fails outright — timeout, connection refused,
    malformed JSON, the endpoint disabled — so a caller can tell
    "genuinely zero resident context" (0) apart from "couldn't ask the
    server at all" (None), and degrade accordingly. See
    `reserve_context_budget()`'s own docstring for why failing closed
    (refusing admission, NEW-431 — never "the pool must be empty," which
    is what this used to silently do) is the safe failure mode for this
    admission check specifically — this is safety-relevant code (CLAUDE.md's
    exception-handling rule), and treating an unreachable `/slots` as "the
    pool must be empty" would reopen exactly the over-admission NEW-206
    itself is about.
    """
    last_error: Optional[Exception] = None
    for attempt in range(max_attempts):
        try:
            url = f"http://{host}:{port}/slots"
            with urllib.request.urlopen(url, timeout=timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
            if not isinstance(data, list):
                last_error = ValueError(f"/slots returned non-list payload: {type(data)}")
            else:
                total = 0
                for s in data:
                    processing = s.get("is_processing")
                    if processing is not True and processing is not False:
                        # Schema drift (NEW-431's own rule applied here too):
                        # an unrecognized/missing occupancy field must not be
                        # silently treated as "safe to ignore" (that's the
                        # opposite mistake NEW-431 already caught this module
                        # making) — fail closed by counting the slot as
                        # occupied, and warn so the drift gets noticed.
                        warning(
                            f"resource_gate: /slots entry missing/invalid "
                            f"'is_processing' ({processing!r}), counting it as "
                            f"occupied (fail-closed): {s.get('id')}"
                        )
                        total += int(s.get("n_prompt_tokens", 0) or 0)
                    elif processing:
                        total += int(s.get("n_prompt_tokens", 0) or 0)
                return total
        except Exception as e:
            last_error = e
        if attempt < max_attempts - 1:
            sleep_fn(retry_gap_seconds)
    warning(
        f"resource_gate: /slots poll failed for {host}:{port} after "
        f"{max_attempts} attempts, degrading: {last_error}"
    )
    return None


def _tokenize_via_server(
    host: str, port: int, text: str, timeout: float = TOKENIZE_ENDPOINT_TIMEOUT_SECONDS
) -> Optional[int]:
    """
    Ask the live server's own `/tokenize` endpoint for the real token count
    of `text` — the same approach `NEW-206`'s own live test used to measure
    its two prompts, more precise than any local heuristic since it uses the
    model's actual tokenizer. Returns `None` (never a guessed count) on any
    failure so `estimate_prompt_tokens()` can fall back to the heuristic
    explicitly, rather than silently substituting a wrong number.
    """
    try:
        url = f"http://{host}:{port}/tokenize"
        payload = json.dumps({"content": text}).encode("utf-8")
        req = urllib.request.Request(
            url, data=payload, headers={"Content-Type": "application/json"}, method="POST"
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
        tokens = data.get("tokens")
        if isinstance(tokens, list):
            return len(tokens)
        return None
    except Exception as e:
        warning(f"resource_gate: /tokenize call failed for {host}:{port}, falling back to heuristic: {e}")
        return None


def estimate_prompt_tokens(
    host: str, port: int, messages: List[dict], tokenize_fn=None
) -> Tuple[int, str]:
    """
    Estimate the prompt-token cost of `messages` for a context-budget
    admission check, preferring the live server's own `/tokenize` endpoint
    for precision and falling back to `core/tokens.py`'s existing
    `estimate_tokens()`/`estimate_messages_tokens()` heuristic (padded, see
    `CONTEXT_HEURISTIC_FALLBACK_PADDING_FACTOR`'s own comment) if `/tokenize`
    fails or times out.

    Centralized here (§8 Q11's design round explicitly called this out,
    "now that it's safety-relevant, not just a UX computation") rather than
    duplicated at each of the two live call sites (`core/inference_hybrid.py`,
    `core/plannd.py`) — both call sites now go through
    `reserve_context_budget()` (which calls this), so there is exactly one
    place this estimation logic can drift, not two independently-maintained
    copies.

    Returns `(estimated_tokens, source)` where `source` is `"tokenize"` or
    `"heuristic"` — persisted onto the reservation record so a later reader
    can tell which was used for a given admission decision.

    `tokenize_fn` (test seam): defaults to a real `/tokenize` HTTP call
    against `host`/`port`; tests pass a stub returning an int or `None`.
    """
    text = "\n".join(str(m.get("content", "")) for m in messages)
    if tokenize_fn is None:
        tokenize_fn = lambda t: _tokenize_via_server(host, port, t)
    tokens = tokenize_fn(text)
    if tokens is not None:
        return int(tokens), "tokenize"

    from core.tokens import estimate_messages_tokens

    heuristic = estimate_messages_tokens(messages)
    return int(heuristic * CONTEXT_HEURISTIC_FALLBACK_PADDING_FACTOR), "heuristic"


def compute_context_queue_timeout_seconds(n_ctx: int, max_tokens: int) -> float:
    """
    Formula-based timeout for `wait_and_reserve_context_budget()`'s own
    retry loop — matching this codebase's own established precedent
    (`core/plannd.py::compute_planner_timeout()`, which this project chose
    over a flat constant specifically because a flat constant already
    caused one incident, `NEW-165`, the moment the thing it was sized
    against changed) rather than a single hardcoded number.

    Modeled as the worst-case wall-clock time for ONE full-context occupant
    (prefill across the whole shared pool, then a full generation budget) to
    finish and free the capacity a queued caller is waiting on — the
    genuine upper bound on how long a well-behaved queued wait might
    legitimately need, using this project's own conservative device-rate
    floors (`PLANNER_MIN_PREFILL_TPS`/`PLANNER_MIN_GEN_TPS`/
    `PLANNER_TIMEOUT_MARGIN_SECONDS`, `utils/config.py` — the same floors
    `compute_planner_timeout()` already uses, not a second, independently-
    guessed set of rates), then capped at `CONTEXT_QUEUE_TIMEOUT_CAP_SECONDS`
    — see that constant's own comment for why the uncapped formula (which
    reaches ~110 minutes at production's real n_ctx=65536) would exceed both
    real call sites' own enclosing timeouts.
    """
    from utils.config import (PLANNER_MIN_GEN_TPS, PLANNER_MIN_PREFILL_TPS,
                               PLANNER_TIMEOUT_MARGIN_SECONDS)

    worst_case = (
        (n_ctx / PLANNER_MIN_PREFILL_TPS)
        + (max_tokens / PLANNER_MIN_GEN_TPS)
        + PLANNER_TIMEOUT_MARGIN_SECONDS
    )
    return min(worst_case, CONTEXT_QUEUE_TIMEOUT_CAP_SECONDS)


@dataclass(frozen=True)
class ContextBudgetDecision:
    """
    Result of `reserve_context_budget()`/`wait_and_reserve_context_budget()`.

    `admitted`: whether this request may proceed now.
    `reservation_id`: the ledger record's id if admitted (pass to
        `release_context_budget()` once the HTTP call this reservation was
        for returns, success or failure) — `None` if not admitted.
    `reserved_tokens`: this request's own `prompt_tokens + max_tokens`
        estimate (the figure actually reserved on admission).
    `effective_n_ctx`: the real spawned `n_ctx` this decision was computed
        against (`resolve_effective_n_ctx()`), or `None` if it could not be
        resolved (in which case `admitted` is always `False` — see
        `reserve_context_budget()`'s own docstring for why that's a refusal,
        not a guess).
    `ceiling_tokens`: `effective_n_ctx * (1 - safety_margin_fraction)`, the
        combined-demand ceiling this decision was checked against (0 if
        `effective_n_ctx` is `None`).
    `slots_occupied_tokens`: the live `/slots`-reported sum at check time (0
        if `/slots` was unreachable — see `reason` for whether that
        degraded-signal case applies to this particular decision).
    `other_reserved_tokens`: sum of every OTHER live reservation record's
        `reserved_tokens` in the ledger at check time (this decision's own
        request is not included in this figure).
    `estimate_source`: `"tokenize"`, `"heuristic"`, or `"none"` (the
        `effective_n_ctx`-unresolvable refusal case, where no estimate was
        computed at all).
    `reason`: human-readable explanation, always populated (not just on
        refusal) so a caller/log can show why an admission succeeded too.
    `timed_out`: `True` only when `wait_and_reserve_context_budget()`'s own
        retry loop hit its timeout without ever getting admitted — `False`
        for every decision `reserve_context_budget()` itself returns
        directly (single-shot calls have no notion of "timed out").
    """

    admitted: bool
    reservation_id: Optional[str]
    reserved_tokens: int
    effective_n_ctx: Optional[int]
    ceiling_tokens: int
    slots_occupied_tokens: int
    other_reserved_tokens: int
    estimate_source: str
    reason: str
    timed_out: bool = False


def reserve_context_budget(
    port: int,
    messages: List[dict],
    max_tokens: int,
    model_id: str = "primary",
    host: str = "127.0.0.1",
    n_ctx: Optional[int] = None,
    safety_margin_fraction: float = CONTEXT_BUDGET_SAFETY_MARGIN_FRACTION,
    state_dir: Optional[Path] = None,
    pid: Optional[int] = None,
    reap_dead: bool = True,
    fetch_slots_fn=None,
    tokenize_fn=None,
) -> ContextBudgetDecision:
    """
    Single-shot admission check + atomic reservation against the shared
    server's KV-pool context budget — the (c) half of §8 Q11's fix. Reserves
    `estimate_prompt_tokens(...) + max_tokens` (prompt AND generation
    together, deliberately conservative: the design round's own source-read
    confirmed the during-generation collision surface is untested, so this
    does not assume it is safe to release the generation-budget portion
    early).

    Admission combines THREE figures against the ceiling, not just this
    request's own estimate: (a) the live `/slots`-reported sum (the
    authoritative real-occupancy signal — see this section's header
    comment), (b) every other live reservation this or another process has
    admitted but not yet released (closes the TOCTOU window between an
    admission check and that request actually reaching the server — the
    ledger's only job, see the header comment for why it does NOT try to be
    the sole source of truth on real, ongoing occupancy), and (c) this
    request's own estimate. Refuses if the combined total would exceed
    `effective_n_ctx * (1 - safety_margin_fraction)`.

    `n_ctx`, if given, skips `resolve_effective_n_ctx()`'s own store/proc
    lookup — `wait_and_reserve_context_budget()`'s own retry loop passes it
    explicitly so every retry checks against the same resolved value instead
    of re-resolving (and potentially re-querying `/proc`) on every tick.
    Direct callers should normally leave this `None` and let it resolve.

    **If `effective_n_ctx` cannot be resolved at all (neither the slot
    store nor a live `/proc` re-derivation has it), this function REFUSES
    admission** rather than falling back to `MODEL_CONFIG["n_ctx"]` — see
    `resolve_effective_n_ctx()`'s own docstring for the concrete bug this
    avoids (a config value that can silently disagree with what the server
    was actually spawned with, exactly `NEW-206`'s own `CODEY_N_CTX=8192`-
    override scenario). This is a deliberate fail-closed choice for
    safety-relevant admission logic (CLAUDE.md's exception-handling rule):
    in normal operation `core/loader_v2.py` always registers the primary
    server's real `n_ctx` at spawn time, so this branch should essentially
    never fire when the server was started through this project's own
    normal path; if it ever does fire, refusing one request that can't be
    safety-checked is a far smaller failure than silently admitting against
    a possibly-wrong ceiling and reopening NEW-206's cascade.

    `/slots` is polled BEFORE the ledger's lock is acquired, not inside it —
    matching `reserve_slot()`'s own documented reason for reading live
    signals (meminfo, thermal) outside `_LockedState`'s blocking, no-timeout
    flock: a slow or unreachable `/slots` call must not stall every other
    process waiting on this ledger's lock. `_fetch_slots_prompt_tokens()`
    itself retries once (NEW-431) before giving up; if the poll still
    fails after that, this function fails CLOSED — refuses admission
    outright, without ever calling `acquire_context_lease()` — rather than
    degrading to "the local reservation ledger alone" (that older behavior
    was NEW-431: the local ledger cannot see occupancy from requests that
    bypassed it, so treating an unreachable `/slots` as "the pool must be
    empty" reopened exactly NEW-206's own over-admission window). See
    `_fetch_slots_prompt_tokens()`'s own docstring for why "treat as
    unlimited" was never on the table either.
    """
    if pid is None:
        pid = os.getpid()

    if n_ctx is None:
        n_ctx = resolve_effective_n_ctx(model_id, port, state_dir=state_dir)
    if not n_ctx or n_ctx <= 0:
        return ContextBudgetDecision(
            admitted=False,
            reservation_id=None,
            reserved_tokens=0,
            effective_n_ctx=None,
            ceiling_tokens=0,
            slots_occupied_tokens=0,
            other_reserved_tokens=0,
            estimate_source="none",
            reason=(
                "cannot resolve the shared server's real n_ctx from the slot "
                "store or /proc — refusing this admission rather than "
                "guessing (CLAUDE.md rule 12)"
            ),
        )

    ceiling_tokens = int(n_ctx * (1.0 - safety_margin_fraction))

    prompt_tokens, estimate_source = estimate_prompt_tokens(
        host, port, messages, tokenize_fn=tokenize_fn
    )
    reserved_tokens = prompt_tokens + max_tokens

    if fetch_slots_fn is None:
        fetch_slots_fn = lambda: _fetch_slots_prompt_tokens(host, port)
    try:
        slots_tokens = fetch_slots_fn()
    except Exception as e:
        # Best-effort signal only — see _fetch_slots_prompt_tokens()'s own
        # docstring for why an injected fetch_slots_fn raising is handled
        # the same degrade-not-crash way a real HTTP failure already is.
        warning(f"resource_gate: fetch_slots_fn raised, degrading: {e}")
        slots_tokens = None

    if slots_tokens is None:
        # NEW-431: fail CLOSED, not open. `/slots` is the one AUTHORITATIVE,
        # freshly-measured real-occupancy signal this admission check has
        # (see this section's own header comment) — silently treating
        # "couldn't ask the server" as "the pool must be genuinely empty"
        # (the old behavior: degrading slots_tokens to 0 and proceeding)
        # reopens exactly the over-admission window NEW-206 itself is
        # about, since the local reservation ledger alone cannot see
        # occupancy from requests that bypassed this ledger entirely. Skip
        # acquire_context_lease() entirely rather than admitting against an
        # unverifiable ceiling. effective_n_ctx is set to the real resolved
        # n_ctx (NOT None) so wait_and_reserve_context_budget()'s
        # early-return-on-None-means-hard-fail check does not fire — this
        # must be retryable as a transient blip, not treated as an
        # immediate hard failure.
        return ContextBudgetDecision(
            admitted=False,
            reservation_id=None,
            reserved_tokens=reserved_tokens,
            effective_n_ctx=n_ctx,
            ceiling_tokens=ceiling_tokens,
            slots_occupied_tokens=0,
            other_reserved_tokens=0,
            estimate_source=estimate_source,
            reason=(
                "refusing: /slots endpoint unreachable — cannot verify real "
                "KV-pool occupancy safely (fail-closed, NEW-431)"
            ),
        )

    from core.resource_bus import acquire_context_lease

    admitted, reservation_id, other_reserved_tokens, ceiling_tokens, bus_reason = acquire_context_lease(
        port=port,
        reserved_tokens=reserved_tokens,
        effective_n_ctx=n_ctx,
        safety_margin_fraction=safety_margin_fraction,
        slots_tokens=slots_tokens,
        pid=pid,
        state_dir=state_dir,
        # NEW-430: this reservation must live for the whole in-flight HTTP
        # call it guards (up to CONTEXT_QUEUE_TIMEOUT_CAP_SECONDS's own
        # enclosing timeout), not resource_bus.py's DEFAULT_LEASE_DURATION_SEC
        # (60.0, tuned for the OTHER, short-lived lease domains — CPU
        # threads, model slots, memory — sharing that same default). Without
        # this, a real request running longer than 60s would have its own
        # still-in-flight reservation silently reaped out from under it by
        # _reap_stale_records_locked(), reopening exactly the over-admission
        # window NEW-206 is about.
        lease_duration=CONTEXT_RESERVATION_MAX_AGE_SECONDS,
        metadata={
            "prompt_tokens": prompt_tokens,
            "max_tokens": max_tokens,
            "estimate_source": estimate_source,
        },
    )

    if not admitted:
        # NEW-431: slots_tokens is a real, successfully-fetched value here
        # -- the /slots-unreachable case now returns above, before this
        # point, so bus_reason needs no "degraded" annotation.
        return ContextBudgetDecision(
            admitted=False,
            reservation_id=None,
            reserved_tokens=reserved_tokens,
            effective_n_ctx=n_ctx,
            ceiling_tokens=ceiling_tokens,
            slots_occupied_tokens=slots_tokens,
            other_reserved_tokens=other_reserved_tokens,
            estimate_source=estimate_source,
            reason=bus_reason,
        )

    return ContextBudgetDecision(
        admitted=True,
        reservation_id=reservation_id,
        reserved_tokens=reserved_tokens,
        effective_n_ctx=n_ctx,
        ceiling_tokens=ceiling_tokens,
        slots_occupied_tokens=slots_tokens,
        other_reserved_tokens=other_reserved_tokens,
        estimate_source=estimate_source,
        reason="admitted",
    )


def release_context_budget(reservation_id: str, state_dir: Optional[Path] = None) -> bool:
    """
    Remove a context-budget reservation by id once the HTTP call it was
    reserved for has returned — success OR failure, always, from a
    `finally` block at the call site (matching this module's own
    `release_slot()` precedent).

    Delegates to core/resource_bus.py's release_context_lease().
    """
    from core.resource_bus import release_context_lease
    return release_context_lease(reservation_id, state_dir=state_dir)


def wait_and_reserve_context_budget(
    port: int,
    messages: List[dict],
    max_tokens: int,
    model_id: str = "primary",
    host: str = "127.0.0.1",
    safety_margin_fraction: float = CONTEXT_BUDGET_SAFETY_MARGIN_FRACTION,
    timeout_seconds: Optional[float] = None,
    poll_interval_seconds: float = CONTEXT_QUEUE_POLL_INTERVAL_SECONDS,
    state_dir: Optional[Path] = None,
    pid: Optional[int] = None,
    fetch_slots_fn=None,
    tokenize_fn=None,
    sleep_fn=time.sleep,
) -> ContextBudgetDecision:
    """
    The (b)-as-backstop-behind-(c) half of §8 Q11's fix: retries
    `reserve_context_budget()` in a plain acquire-check-release-sleep-retry
    loop until either admitted or `timeout_seconds` elapses, turning a
    would-be refusal into a serialization WAIT instead of an outright
    rejection — one mechanism, two behaviors, matching Ish's own "(b) as a
    safety AFTER (c)" framing (§8 Q11), not two separate circuit breakers.

    Each retry is a full, independent `reserve_context_budget()` call —
    `_LockedState`'s blocking flock is acquired and released within that
    call, never held across `sleep_fn()` (the design round's own explicit
    requirement: a caller sleeping while holding this cross-process lock
    would stall every OTHER process's admission checks and slot operations
    for the sleep's whole duration).

    Deliberately NOT FIFO-fair (design round's own accepted tradeoff, not a
    bug): every waiter's next retry races every other waiter's next retry
    with no ordering token between them — whichever call happens to reach
    `reserve_context_budget()`'s lock first on a given tick wins that tick,
    which can (rarely, in principle) let a later-arriving waiter jump ahead
    of an earlier one.

    `n_ctx` is resolved ONCE up front (not re-resolved on every retry) so
    every retry in one wait checks against the same value and so
    `timeout_seconds`'s default can be computed from it before the loop
    starts. If it cannot be resolved at all, returns immediately (the
    first `reserve_context_budget()` call's own refusal) rather than
    retrying pointlessly — a request that can never be resolved once won't
    resolve on a later tick either.

    `timeout_seconds`, if `None` (the normal case), defaults to
    `compute_context_queue_timeout_seconds(n_ctx, max_tokens)` — see that
    function's own docstring for the formula and its
    `CONTEXT_QUEUE_TIMEOUT_CAP_SECONDS` cap.

    On timeout, returns the LAST refusal `ContextBudgetDecision` with
    `timed_out=True` set — callers (`core/inference_hybrid.py`,
    `core/plannd.py`) treat this the same as any other admission refusal
    (log and surface a failure to their own caller, exactly like every
    other error path those two functions already have), just with a more
    specific reason string available for the log line.
    """
    n_ctx = resolve_effective_n_ctx(model_id, port, state_dir=state_dir)

    decision = reserve_context_budget(
        port,
        messages,
        max_tokens,
        model_id=model_id,
        host=host,
        n_ctx=n_ctx,
        safety_margin_fraction=safety_margin_fraction,
        state_dir=state_dir,
        pid=pid,
        fetch_slots_fn=fetch_slots_fn,
        tokenize_fn=tokenize_fn,
    )
    if decision.admitted or decision.effective_n_ctx is None:
        return decision

    if timeout_seconds is None:
        timeout_seconds = compute_context_queue_timeout_seconds(n_ctx, max_tokens)
    deadline = time.time() + timeout_seconds

    while True:
        if time.time() >= deadline:
            return ContextBudgetDecision(
                admitted=False,
                reservation_id=None,
                reserved_tokens=decision.reserved_tokens,
                effective_n_ctx=decision.effective_n_ctx,
                ceiling_tokens=decision.ceiling_tokens,
                slots_occupied_tokens=decision.slots_occupied_tokens,
                other_reserved_tokens=decision.other_reserved_tokens,
                estimate_source=decision.estimate_source,
                reason=(
                    f"timed out after {timeout_seconds:.0f}s waiting for context "
                    f"budget to free up — last refusal: {decision.reason}"
                ),
                timed_out=True,
            )
        sleep_fn(poll_interval_seconds)
        decision = reserve_context_budget(
            port,
            messages,
            max_tokens,
            model_id=model_id,
            host=host,
            n_ctx=n_ctx,
            safety_margin_fraction=safety_margin_fraction,
            state_dir=state_dir,
            pid=pid,
            fetch_slots_fn=fetch_slots_fn,
            tokenize_fn=tokenize_fn,
        )
        if decision.admitted:
            return decision
