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
import uuid
from dataclasses import dataclass, field
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
    default (`MAX_SWAP_ASSIST_BYTES`, 10GiB as of sub-task F's 2026-08-11
    recalibration — see `can_admit()`'s own swap-assist section below for
    that constant's derivation; `can_dispatch_task()` uses its own,
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
    return int(max(0, min(max_swap_usage_bytes, gated_swap_free)))


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
    Minimal transformer architecture parameters needed to estimate KV cache
    size. Values come from each model family's published config (Qwen2.5
    architecture docs) for QWEN25_7B_ARCH/QWEN25_1_5B_ARCH. QWEN3_4B_ARCH and
    QWEN25_0_5B_PLANNER_ARCH (below) instead come from reading each real
    GGUF file's own header metadata directly on-device, because those two
    are test-only substitute models with no corresponding "published config"
    reference to cite (see each constant's own comment for the exact fields
    read). Neither provenance parses the GGUF file at estimate time — this
    dataclass stays narrowly scoped to what this gate needs, not a general
    GGUF-metadata reader.
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

# Keyed by ModelSpec.model_id, NOT by the model's file path. This dict used
# to be keyed by str(MODEL_PATH)/str(PLANNER_MODEL_PATH) — both bound once
# at this module's import time — which meant a hot-swap to a fine-tuned
# model (core/lora_import.py's swap_to_finetuned_model(), which mutates
# utils.config.MODEL_PATH/PLANNER_MODEL_PATH on the live module object, not
# this frozen import-time snapshot) silently missed the lookup after the
# swap and dropped the KV-cache cost term to 0 in the gate's admission math
# (NEW_ISSUES.md NEW-84 addendum — an admission-safety bug: an
# underestimated cost could let the gate over-admit a load it would
# otherwise correctly reject). core/loader_v2.py and core/planner_loader.py
# both always pass a fixed model_id of "primary"/"planner" respectively
# regardless of which file is actually being loaded (see their
# rg.ModelSpec(...) call sites) — a LoRA-merged model keeps the same
# architecture (n_layers/n_kv_heads/head_dim) as its base, so keying on the
# stable role identifier instead of the mutable path is both correct and
# swap-proof.
KNOWN_MODEL_ARCHS: Dict[str, ModelArch] = {
    "primary": QWEN25_7B_ARCH,
    "planner": QWEN25_1_5B_ARCH,
}

# ── Test-only architecture substitutes (Qwen3-4B / Qwen2.5-0.5B planner) ────
# These two constants exist ONLY to support a documented, deliberate live-test
# session (Ish swapping in smaller models via utils/config.py's existing
# CODEY_MODEL / CODEY_PLANNER_MODEL env-var overrides, for RAM-safe on-device
# gate/loader/daemon verification) — never for any non-test purpose. They are
# NOT added to KNOWN_MODEL_ARCHS's committed default entries, and by
# themselves do nothing: see CODEY_TEST_PRIMARY_ARCH / CODEY_TEST_PLANNER_ARCH
# below for the only mechanism that activates them, and note its own "unset
# means byte-for-byte unchanged" contract.
#
# Values below were read directly from each real GGUF file's own header
# metadata on this device (not published specs, not guessed) — see the task
# that added this section for the exact `gguf`/metadata dump this was
# extracted from.

# Qwen3-4B-Instruct-2507 (~/models/qwen3-4b-instruct/
# Qwen3-4B-Instruct-2507-Q4_K_M.gguf). GGUF header: qwen3.block_count=36,
# qwen3.attention.head_count_kv=8, qwen3.attention.key_length=128.
QWEN3_4B_ARCH = ModelArch(n_layers=36, n_kv_heads=8, head_dim=128)

# 0.5B planner substitute (~/models/qwen2.5-0.5b/planner-codey.gguf, Qwen2
# architecture, general.size_label="494M"). GGUF header: qwen2.block_count=24,
# qwen2.attention.head_count_kv=2; this GGUF has no separate
# qwen2.attention.key_length field, so head_dim is derived the standard way
# for this architecture family: qwen2.embedding_length=896 /
# qwen2.attention.head_count=14 = 64.
QWEN25_0_5B_PLANNER_ARCH = ModelArch(n_layers=24, n_kv_heads=2, head_dim=64)

# String keys accepted by CODEY_TEST_PRIMARY_ARCH / CODEY_TEST_PLANNER_ARCH
# below, mapped to the constants above. A small registry (rather than
# accepting a raw "n_layers,n_kv_heads,head_dim" triple) so a typo produces a
# loud, enumerable error instead of a silently-plausible wrong triple — see
# _resolve_model_arch()'s use of this dict.
#
# Deliberately PER-ROLE (a registry keyed by model_id, not one flat registry
# shared across both env vars): if a single flat registry accepted either key
# from either env var, e.g. `CODEY_TEST_PRIMARY_ARCH=qwen2.5-0.5b-planner`
# would be silently accepted and would set the *primary* role's KV factor to
# 24*2*64=3072 against the real 7B's 14336 — a ~4.7x under-estimate, worse
# than the 2.6x under-estimate this whole feature exists to fix, and with no
# loud failure at all. Splitting the registry by role means the wrong-role
# value simply isn't a recognized key for that role's env var, so it hits the
# same loud ValueError path as any other typo. Cross-role substitution
# (deliberately putting the 0.5B arch in the primary slot, or vice versa) is
# NOT supported by this mechanism — if a future live test genuinely needs
# that, it should be a documented, explicit extension, not a side effect of
# a shared flat registry.
_TEST_ARCH_REGISTRY_BY_ROLE: Dict[str, Dict[str, ModelArch]] = {
    "primary": {"qwen3-4b": QWEN3_4B_ARCH},
    "planner": {"qwen2.5-0.5b-planner": QWEN25_0_5B_PLANNER_ARCH},
}

# Env vars read LAZILY (inside _resolve_model_arch(), not at module import)
# so: (1) a test process can set/unset them per-test without needing
# importlib.reload (which would rebind this module's ModelArch constants and
# break identity checks elsewhere, e.g.
# tests/test_resource_gate.py::test_known_model_archs_resolved_by_path's `is`
# assertion); (2) the override can never outlive the env var — unset always
# means immediately, byte-for-byte back to today's KNOWN_MODEL_ARCHS lookup,
# with no risk of a stale in-process cache silently persisting an override
# into what's meant to be a normal production run.
#
# Scoped to model_id "primary"/"planner" ONLY, and only consulted AFTER the
# existing `spec.arch is not None` explicit-override check in
# _resolve_model_arch() — a caller (or test) that explicitly passes `arch=`
# always wins; these env vars must never silently preempt an explicit,
# already-correct caller declaration. Precedence, in order: explicit
# `spec.arch` > this env-var test override > KNOWN_MODEL_ARCHS default.
CODEY_TEST_PRIMARY_ARCH_ENV = "CODEY_TEST_PRIMARY_ARCH"
CODEY_TEST_PLANNER_ARCH_ENV = "CODEY_TEST_PLANNER_ARCH"

_TEST_ARCH_ENV_BY_MODEL_ID = {
    "primary": CODEY_TEST_PRIMARY_ARCH_ENV,
    "planner": CODEY_TEST_PLANNER_ARCH_ENV,
}


def _resolve_test_arch_override(model_id: str) -> Optional[ModelArch]:
    """
    Return the env-var-selected test-only architecture override for
    `model_id` ("primary"/"planner" only), or None if no applicable env var
    is set or the env var is set to the empty string (treated as unset,
    matching this project's `os.environ.get(NAME, default)` convention
    elsewhere — e.g. utils/config.py's CODEY_MODEL override — where an empty
    value is not a meaningful distinct case worth its own error). Raises
    ValueError (loud, not a silent bad fallback) if the env var is set to a
    non-empty value not present in that role's entry in
    _TEST_ARCH_REGISTRY_BY_ROLE — this gate's entire purpose is preventing an
    under-estimated cost from silently admitting a load it shouldn't, so a
    typo'd override value (INCLUDING a value valid for the *other* role, per
    the per-role registry split above) must fail admission outright rather
    than quietly falling back to the wrong architecture (or to "no
    architecture", which would silently zero the KV term — see
    estimate_model_load_cost()'s unknown-arch branch).
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
    `arch` on this spec, then (for `model_id` "primary"/"planner" only) the
    CODEY_TEST_PRIMARY_ARCH/CODEY_TEST_PLANNER_ARCH test-only env-var
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
    """
    Precedence, in order: explicit `spec.arch` > CODEY_TEST_PRIMARY_ARCH /
    CODEY_TEST_PLANNER_ARCH env-var test override (see that section's header
    comment above) > KNOWN_MODEL_ARCHS default. The env-var check can raise
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
# ceiling is now utils.config.get_planner_n_ctx() (8192 by default, not
# 32768 — sub-task B; a function, not a constant, as of the NEW-102/bug_002
# fix — see utils/config.py), and the coder's ceiling drops to
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
# less). **Conclusion: MAX_CONCURRENT_MODEL_BUDGET_BYTES stays 8.90GiB —
# no value change from this revisit.** The larger (interactive-coder)
# recomputed sum is the one this ceiling must be checked against going
# forward, since sub-task C's decision does not shrink the coder's
# interactive ceiling — only its background-dispatch one.
MAX_CONCURRENT_MODEL_BUDGET_BYTES = int(8.90 * (1024 ** 3))  # 9,556,302,233 bytes


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
# changing either ceiling).
MAX_SWAP_ASSIST_BYTES = 10 * 1024 ** 3  # 10,737,418,240 bytes (10.00GiB)

# TODO.md 7.4a sub-task F: `can_dispatch_task()`'s own default cap,
# deliberately DECOUPLED from `MAX_SWAP_ASSIST_BYTES` above (which sub-task
# F raised to 10GiB for `can_admit()` — one-shot, explicit, human/loader-
# initiated model loads). `can_dispatch_task()` runs unguarded on EVERY
# tick of the daemon's autonomous, unattended dispatch loop, gating
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
# import time) for the same reason CODEY_TEST_PRIMARY_ARCH/
# CODEY_TEST_PLANNER_ARCH are read lazily above: a test process can flip it
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
    `max_swap_usage_bytes` (default `MAX_SWAP_ASSIST_BYTES`, 10GiB as of
    sub-task F's 2026-08-11 recalibration) and
    `slmk_floor_gate_multiplier` (default `SLMK_FLOOR_GATE_MULTIPLIER`, 2.0)
    are passed straight through to `compute_swap_assisted_headroom_bytes()`
    — see that function's own docstring and `MAX_SWAP_ASSIST_BYTES`'s own
    comment for the full derivation of both.

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

    Caveats carried forward from sub-task B, both still unaddressed by C2
    (out of scope here; flagged for sub-task D/E):
      - The swap-assist figure is authorized swap USAGE, not a claim about
        real usable headroom under an actual model load — quantized model
        weight pages may compress far less favorably than the ~4:1 ratio
        `compute_zram_compression_ratio()` observes on ordinary idle app
        pages. Unverified until sub-task E's live pass.
      - `compute_swap_assisted_headroom_bytes()` reads raw `SwapFree` with
        no `reserved_bytes`-style deduction for other in-flight admissions
        (unlike `compute_headroom_bytes()`, which does subtract
        `reserved_bytes`) — two concurrently-pending swap-assisted
        admissions can each independently lean on the same live `SwapFree`
        figure and the same `MAX_SWAP_ASSIST_BYTES` cap (10GiB as of
        sub-task F), rather than the second one seeing the first one's
        claim already spent. Not fixed here (would change
        sub-task B's own function signature, out of scope for C2's mandate
        of wiring, not redesigning, that function) — flagged for whichever
        later sub-task revisits concurrent-admission accounting for the
        swap-assist path specifically.
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
                meminfo, max_swap_usage_bytes, slmk_floor_gate_multiplier
            )
            combined_headroom = headroom + swap_headroom
            if required <= combined_headroom:
                return GateDecision(
                    admitted=True,
                    hard_reject=False,
                    admitted_via_swap=True,
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
# the TUI/GUI — see `is_interactive_session_active()` above).
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
         human is watching the TUI/GUI.
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
    `MAX_SWAP_ASSIST_BYTES` (raised to 10GiB, `can_admit()`-only by that
    same recalibration) — see `DISPATCH_MAX_SWAP_ASSIST_BYTES`'s own
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

    **Deliberately unfixed, carried-forward caveat (`NEW-135`)**: like
    `can_admit()`'s own swap-assist branch,
    `compute_swap_assisted_headroom_bytes()` reads raw `SwapFree` with no
    `reserved_bytes`-style deduction for other in-flight consumers of the
    same swap budget. This sub-task adds a SECOND independent consumer of
    the same live `SwapFree` figure (a dispatch decision, alongside
    `can_admit()`'s own model-admission decision) — widening `NEW-135`'s
    blast radius rather than introducing a new gap: a concurrently
    in-flight swap-assisted admission and a concurrently swap-assisted
    dispatch decision can each independently claim the same live
    `SwapFree` figure, neither aware of the other's claim. As of TODO.md
    7.4a sub-task F's 2026-08-11 recalibration, the two consumers no
    longer share the SAME numeric cap (`can_admit()` now defaults to
    `MAX_SWAP_ASSIST_BYTES`, 10GiB; this function still defaults to the
    unchanged `DISPATCH_MAX_SWAP_ASSIST_BYTES`, 768MiB) — `NEW-135`'s core
    gap (no cross-consumer accounting of the shared `SwapFree` pool) is
    unaffected by that split and remains exactly as unfixed as before. Not
    fixed here (fixing it means changing sub-task B's own function
    signature, out of scope for this sub-task's mandate of wiring, not
    redesigning, that function — same reasoning C2 used to decline the
    same fix).
    """
    if interactive_active:
        return DispatchDecision(
            allowed=False,
            reason="interactive TUI/GUI session active — deferring background dispatch",
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

        # TODO.md 7.4a sub-task C1 item 3: computed HERE, inside this same
        # lock, on the already-reaped `slots` list — NOT via a separate
        # total_committed_bytes() call (which acquires its own lock and
        # would both self-deadlock against the lock already held here and
        # reopen the exact TOCTOU window this function exists to close).
        committed = _sum_committed_bytes(slots)

        decision = can_admit(
            spec,
            meminfo=meminfo,
            reserved_bytes=reserved,
            usable_fraction=usable_fraction,
            headroom_factor=headroom_factor,
            read_temp_fn=_fixed_temp_fn,
            concurrent_committed_bytes=committed,
            max_concurrent_budget_bytes=max_concurrent_budget_bytes,
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
    `core/loader_v2.py`/`core/planner_loader.py`'s shared
    `confirm_resident_and_mark_slot()`) should pass it here so PID-liveness
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
    with _LockedState(state_dir) as slots:
        if reap_dead:
            live = [s for s in slots if s.get("pid") is None or _pid_alive(s["pid"])]
            slots[:] = live
        return list(slots)


# ── Signal source 5: interactive-session activity (TUI + GUI) ───────────────
# Track 3 Phase 5a / 7.4 sub-task B. "Is a human actively watching a TUI or
# GUI session right now" — a distinct question from "is the GUI SERVER
# PROCESS alive": the GUI server can run for an entire codey-start session
# with no browser tab ever opened (or since closed), and treating server-
# liveness as this signal would leave the daemon silently blocked from any
# background work for the whole session regardless of whether anyone's
# actually watching (explicitly flagged as the wrong substitution in
# WORK_QUEUE.md's 7.4 sub-task B scoping).
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


def is_gui_client_connected(
    clients_file: Optional[Path] = None, gui_pid_file: Optional[Path] = None
) -> bool:
    """
    True if gui/server.py's live client-count file (written by
    gui/server.py's `_write_gui_clients_count()` whenever its `clients`
    websocket set changes) currently records at least one connected
    browser session.

    Also cross-checks the GUI server's own PID file (existing convention,
    `lib/gui_launch.sh`'s `gui-server.pid` / `utils.config.GUI_PID_FILE`):
    if that PID is no longer alive, a nonzero count is treated as stale
    (0) rather than trusted, because a crashed/killed GUI server process
    has no further opportunity to write a fresh "0" itself — without this
    check, a crash while clients were connected would leave the count file
    reporting a false-positive "someone's watching" forever. This mirrors
    this module's existing self-healing posture (`list_slots()`'s
    PID-liveness reaping) rather than inventing new machinery.
    """
    if clients_file is None:
        from utils.config import GUI_CLIENTS_FILE

        clients_file = GUI_CLIENTS_FILE
    if gui_pid_file is None:
        from utils.config import GUI_PID_FILE

        gui_pid_file = GUI_PID_FILE

    if not clients_file.exists():
        return False
    try:
        with open(clients_file, "r") as f:
            count = int(f.read().strip())
    except (OSError, ValueError):
        # Unreadable/corrupt count file — fail closed toward "don't block
        # background work on a signal that isn't legible", matching this
        # module's existing best-effort posture for auxiliary signals
        # (get_resource_snapshot()'s thermal/battery/queue-depth reads).
        return False
    if count <= 0:
        return False

    if gui_pid_file.exists():
        try:
            with open(gui_pid_file, "r") as f:
                gui_pid = int(f.read().strip())
        except (OSError, ValueError):
            # Can't confirm the GUI server's PID either — fail open toward
            # trusting the count file rather than discarding a real signal
            # over an unrelated read failure.
            return True
        return _pid_alive(gui_pid)

    # No GUI PID file at all: nothing to cross-check against, so trust the
    # count file as-is rather than assuming stale.
    return True


def is_interactive_session_active(
    tui_sessions_dir: Optional[Path] = None,
    gui_clients_file: Optional[Path] = None,
    gui_pid_file: Optional[Path] = None,
) -> bool:
    """
    Composed "is a human actively using Codey-OS's TUI or GUI right now"
    signal: any TUI session active OR at least one connected GUI client.
    Consumed by 7.4 sub-task C (not built here — see this section's header
    comment) to decide whether the daemon should defer background work
    while a user is actively watching.
    """
    return is_tui_session_active(tui_sessions_dir) or is_gui_client_connected(
        gui_clients_file, gui_pid_file
    )


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
