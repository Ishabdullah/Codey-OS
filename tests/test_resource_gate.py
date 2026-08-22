"""
Tests for core/resource_gate.py — Track 3 Phase 5a / CODEY_OS_MASTER_VISION.md
Section 7.4 (2026-08-08 amendment), sub-task 1.

All tests use synthetic /proc/meminfo content, explicit ModelSpec sizes, and
a stubbed thermal reader (`read_temp_fn=lambda: None` unless a test is
specifically exercising the thermal check) — no real model file is read, no
llama-server (or any other) subprocess is spawned, and no test depends on
this device's real live memory/thermal state, matching this project's
history around hidden model loads in the test suite (NEW-1) and this
sub-task's own "no dependency on real live system state" requirement.

Includes the NEW-21 regression case (NEW_ISSUES.md): baseline 4.3Gi used /
2.2Gi free, single primary-model load drove swap from 1.2Gi to 5.6Gi in
~10s. Asserts the gate would reject that load given a correctly-computed
cost estimate (model size + n_ctx-driven KV cache) plus the module's
documented conservative headroom margin — not a bare headroom check.
"""

import os
import subprocess
import tempfile
import threading
import time
from multiprocessing import Process
from pathlib import Path

import pytest

import core.resource_gate as rg

GIB = 1024**3
MIB = 1024**2

NO_THERMAL = lambda: None  # noqa: E731 — stub for read_temp_fn in every test that doesn't test thermal itself


def meminfo_bytes(mem_total_gib, mem_free_gib, mem_available_gib, swap_total_gib=0, swap_free_gib=0):
    """Build a synthetic meminfo dict (already in bytes, matching
    read_meminfo()'s return shape) without touching a real file."""
    return {
        "MemTotal": int(mem_total_gib * GIB),
        "MemFree": int(mem_free_gib * GIB),
        "MemAvailable": int(mem_available_gib * GIB),
        "Buffers": 0,
        "Cached": 0,
        "SwapTotal": int(swap_total_gib * GIB),
        "SwapFree": int(swap_free_gib * GIB),
    }


# ── read_meminfo() parsing ───────────────────────────────────────────────────


def test_read_meminfo_parses_fixture_file(tmp_path):
    fixture = tmp_path / "meminfo"
    fixture.write_text(
        "MemTotal:       11324620 kB\n"
        "MemFree:         2306867 kB\n"
        "MemAvailable:    6979321 kB\n"
        "Buffers:           10240 kB\n"
        "Cached:          4194304 kB\n"
        "SwapTotal:       8388608 kB\n"
        "SwapFree:        7130317 kB\n"
        "SomeOtherField:        1 kB\n"
    )
    result = rg.read_meminfo(str(fixture))
    assert result["MemTotal"] == 11324620 * 1024
    assert result["MemFree"] == 2306867 * 1024
    assert result["MemAvailable"] == 6979321 * 1024
    assert result["SwapFree"] == 7130317 * 1024
    # Pass-through field also present, in bytes.
    assert result["SomeOtherField"] == 1024


def test_read_meminfo_missing_file_raises():
    with pytest.raises(OSError):
        rg.read_meminfo("/nonexistent/path/meminfo")


# ── headroom / ceiling computation ───────────────────────────────────────────


def test_compute_headroom_uses_memavailable():
    # MemAvailable (kernel-computed reclaimable estimate) is the headroom
    # signal, NOT MemFree — MemFree alone runs near-zero on a healthy,
    # idle Linux/Termux system by design (page cache absorbs the rest), so
    # a MemFree-only definition would reject every load unconditionally
    # (see test_primary_model_admitted_under_idle_conditions below, which
    # would fail under a MemFree-only definition).
    mi = meminfo_bytes(mem_total_gib=10.8, mem_free_gib=0.25, mem_available_gib=6.5)
    headroom = rg.compute_headroom_bytes(mi)
    assert headroom == int(6.5 * GIB)


def test_compute_headroom_subtracts_reserved():
    mi = meminfo_bytes(mem_total_gib=10.8, mem_free_gib=0.25, mem_available_gib=6.5)
    headroom = rg.compute_headroom_bytes(mi, reserved_bytes=int(1 * GIB))
    assert headroom == int(5.5 * GIB)


def test_compute_headroom_never_negative():
    mi = meminfo_bytes(mem_total_gib=10.8, mem_free_gib=0.25, mem_available_gib=1.0)
    headroom = rg.compute_headroom_bytes(mi, reserved_bytes=int(5 * GIB))
    assert headroom == 0


def test_compute_device_ceiling_uses_memtotal_only():
    mi = meminfo_bytes(mem_total_gib=10.8, mem_free_gib=0.1, mem_available_gib=0.1)
    ceiling = rg.compute_device_ceiling_bytes(mi, usable_fraction=0.85)
    assert ceiling == int(10.8 * GIB * 0.85)


# ── model cost estimation ────────────────────────────────────────────────────


def test_estimate_kv_cache_bytes_qwen7b():
    # 28 layers * 2 (K+V) * 4 kv_heads * 128 head_dim * 32768 ctx * 2 bytes
    expected = 28 * 2 * 4 * 128 * 32768 * 2
    assert rg.estimate_kv_cache_bytes(rg.QWEN25_7B_ARCH, n_ctx=32768) == expected


def test_estimate_model_load_cost_uses_explicit_size_and_arch():
    spec = rg.ModelSpec(
        model_id="test-7b",
        size_bytes=4_683_073_536,
        n_ctx=32768,
        arch=rg.QWEN25_7B_ARCH,
    )
    cost = rg.estimate_model_load_cost(spec)
    assert cost.model_bytes == 4_683_073_536
    assert cost.kv_cache_bytes == 28 * 2 * 4 * 128 * 32768 * 2
    assert cost.overhead_bytes == rg.DEFAULT_COMPUTE_OVERHEAD_BYTES
    # No recurrent/SSM term for a conventional transformer.
    assert cost.recurrent_state_bytes == 0
    assert cost.total_bytes == (
        cost.model_bytes
        + cost.kv_cache_bytes
        + cost.overhead_bytes
        + cost.recurrent_state_bytes
    )


def test_estimate_model_load_cost_unknown_arch_omits_kv_term():
    spec = rg.ModelSpec(model_id="mystery-model", size_bytes=1_000_000_000, n_ctx=8192)
    cost = rg.estimate_model_load_cost(spec)
    assert cost.kv_cache_bytes == 0
    assert cost.recurrent_state_bytes == 0
    assert cost.model_bytes == 1_000_000_000


def test_qwen35_4b_hybrid_kv_uses_8_attention_layers_not_32():
    # The whole point of M1-A. Qwen3.5-4B declares block_count=32 but
    # full_attention_interval=4, so only 8 layers keep a growing KV cache
    # (CODEY_MASTER_PLAN.md §1.4/§5.1). Using n_layers here would
    # over-estimate by exactly 4x and wrongly refuse an affordable n_ctx.
    assert rg.QWEN35_4B_ARCH.n_layers == 32
    assert rg.QWEN35_4B_ARCH.n_attention_layers == 8
    # 8 layers * 2 (K+V) * 4 kv_heads * 256 head_dim * 2 bytes = 32768/token.
    assert rg.estimate_kv_cache_bytes(rg.QWEN35_4B_ARCH, n_ctx=1) == 32768
    assert rg.estimate_kv_cache_bytes(rg.QWEN35_4B_ARCH, n_ctx=32768) == 8 * 2 * 4 * 256 * 32768 * 2
    # Regression guard against "correcting" n_attention_layers back to 32.
    assert (
        rg.estimate_kv_cache_bytes(rg.QWEN35_4B_ARCH, n_ctx=32768) * 4
        == 32 * 2 * 4 * 256 * 32768 * 2
    )


def test_qwen35_4b_total_cost_reconciles_with_master_plan_table():
    # Single assertion pinning the whole M1-A change against
    # CODEY_MASTER_PLAN.md §5.1's published table (3.852GiB at n_ctx=32768):
    # real on-disk file size + 8-layer KV + the 256MiB overhead constant +
    # the source-derived SSM state. If any one of those four terms drifts,
    # this fails and the plan's table is the thing to reconcile against.
    spec = rg.ModelSpec(model_id="primary", size_bytes=2_740_937_888, n_ctx=32768)
    cost = rg.estimate_model_load_cost(spec)
    assert cost.model_bytes == 2_740_937_888
    assert cost.kv_cache_bytes == 1_073_741_824  # exactly 1.000 GiB
    assert cost.overhead_bytes == rg.DEFAULT_COMPUTE_OVERHEAD_BYTES
    # Mirrors llama.cpp's n_embd_r + n_embd_s at F32, x 24 SSM layers — see
    # QWEN35_4B_ARCH's comment for the source lines. The group_count term
    # (2 * 16 * 128) and the 4-byte element size are both load-bearing: an
    # earlier version dropped the first and used 2 bytes, under-estimating
    # by 26,935,296 bytes.
    assert (
        cost.recurrent_state_bytes
        == ((4 - 1) * (4096 + 2 * 16 * 128) + 128 * 4096) * 4 * 24
        == 52_690_944
    )
    assert cost.total_bytes == 4_135_806_112
    assert abs(cost.total_bytes / (1024 ** 3) - 3.852) < 0.001


def test_estimate_model_load_cost_no_size_or_path_raises():
    spec = rg.ModelSpec(model_id="broken")
    with pytest.raises(ValueError):
        rg.estimate_model_load_cost(spec)


def test_estimate_model_load_cost_applies_mmap_fraction_with_explicit_size():
    # Regression: an earlier version of this module only applied
    # mmap_resident_fraction when size came from path.stat(), silently
    # ignoring it whenever size_bytes was supplied explicitly (which every
    # other test in this file does) — fixed so it applies uniformly.
    spec = rg.ModelSpec(model_id="partial-resident", size_bytes=1_000_000_000, n_ctx=1024, mmap_resident_fraction=0.5)
    cost = rg.estimate_model_load_cost(spec)
    assert cost.model_bytes == 500_000_000


def test_estimate_model_load_cost_applies_mmap_fraction_from_path(tmp_path):
    fake_model = tmp_path / "fake.gguf"
    fake_model.write_bytes(b"\x00" * 1000)
    spec = rg.ModelSpec(model_id="from-path", path=fake_model, n_ctx=1024, mmap_resident_fraction=0.25)
    cost = rg.estimate_model_load_cost(spec)
    assert cost.model_bytes == 250


def test_known_model_archs_resolved_by_path():
    from utils.config import MODEL_PATH, PLANNER_MODEL_PATH

    # Both roles resolve to the one Qwen3.5-4B arch as of the 2026-08-22
    # one-model decision; what this test pins is that resolution happens by
    # model_id and not by the path (NEW-84), not which model is default.
    spec = rg.ModelSpec(model_id="primary", path=MODEL_PATH, size_bytes=1, n_ctx=1024)
    assert rg._resolve_model_arch(spec) is rg.QWEN35_4B_ARCH

    spec2 = rg.ModelSpec(model_id="planner", path=PLANNER_MODEL_PATH, size_bytes=1, n_ctx=1024)
    assert rg._resolve_model_arch(spec2) is rg.QWEN35_4B_ARCH


# ── CODEY_TEST_PRIMARY_ARCH / CODEY_TEST_PLANNER_ARCH override ──────────────
# Env-var-gated architecture substitution for a documented live-test session
# (swapping smaller models in via CODEY_MODEL/CODEY_PLANNER_MODEL for
# RAM-safe on-device gate/loader/daemon verification — see
# core/resource_gate.py's "Test-only architecture substitutes" section).


def test_test_arch_override_unset_matches_current_default_behavior(monkeypatch):
    # Regression: with both env vars unset (the default, normal case),
    # resolution must be byte-for-byte identical to today — including the
    # object identity the pre-existing test above already pins.
    monkeypatch.delenv(rg.CODEY_TEST_PRIMARY_ARCH_ENV, raising=False)
    monkeypatch.delenv(rg.CODEY_TEST_PLANNER_ARCH_ENV, raising=False)

    spec = rg.ModelSpec(model_id="primary", size_bytes=1, n_ctx=1024)
    assert rg._resolve_model_arch(spec) is rg.QWEN35_4B_ARCH

    spec2 = rg.ModelSpec(model_id="planner", size_bytes=1, n_ctx=1024)
    assert rg._resolve_model_arch(spec2) is rg.QWEN35_4B_ARCH

    # KNOWN_MODEL_ARCHS's committed default entries themselves are untouched
    # (this mechanism is a lookup-time override, never a mutation of the dict).
    assert rg.KNOWN_MODEL_ARCHS["primary"] is rg.QWEN35_4B_ARCH
    assert rg.KNOWN_MODEL_ARCHS["planner"] is rg.QWEN35_4B_ARCH


def test_test_arch_override_primary_set_selects_qwen3_4b(monkeypatch):
    # "qwen3-4b" selects the OLDER Qwen3-4B substitute (QWEN3_4B_TEST_ARCH),
    # which is a different architecture from the qwen35 default — see that
    # constant's comment.
    monkeypatch.setenv(rg.CODEY_TEST_PRIMARY_ARCH_ENV, "qwen3-4b")
    monkeypatch.delenv(rg.CODEY_TEST_PLANNER_ARCH_ENV, raising=False)

    spec = rg.ModelSpec(model_id="primary", size_bytes=1, n_ctx=1024)
    assert rg._resolve_model_arch(spec) is rg.QWEN3_4B_TEST_ARCH

    # KNOWN_MODEL_ARCHS's committed default entry is still untouched even
    # while the override is active — this is a lookup-time override, not a
    # mutation, so nothing else reading the dict directly is affected.
    assert rg.KNOWN_MODEL_ARCHS["primary"] is rg.QWEN35_4B_ARCH


def test_test_arch_override_planner_set_selects_qwen25_0_5b(monkeypatch):
    monkeypatch.delenv(rg.CODEY_TEST_PRIMARY_ARCH_ENV, raising=False)
    monkeypatch.setenv(rg.CODEY_TEST_PLANNER_ARCH_ENV, "qwen2.5-0.5b-planner")

    spec = rg.ModelSpec(model_id="planner", size_bytes=1, n_ctx=1024)
    assert rg._resolve_model_arch(spec) is rg.QWEN25_0_5B_PLANNER_ARCH
    assert rg.KNOWN_MODEL_ARCHS["planner"] is rg.QWEN35_4B_ARCH


def test_test_arch_override_does_not_preempt_explicit_spec_arch(monkeypatch):
    # Explicit spec.arch always wins over the env-var test override — an env
    # var silently preempting a caller's explicit, already-correct
    # declaration would itself be a wrong-arch bug.
    monkeypatch.setenv(rg.CODEY_TEST_PRIMARY_ARCH_ENV, "qwen3-4b")
    spec = rg.ModelSpec(model_id="primary", size_bytes=1, n_ctx=1024, arch=rg.QWEN25_7B_ARCH)
    assert rg._resolve_model_arch(spec) is rg.QWEN25_7B_ARCH


def test_test_arch_override_scoped_to_primary_and_planner_only(monkeypatch):
    # Same "primary-7b" model_id used by the NEW-21 regression fixtures below
    # (not the bare "primary"/"planner" role identifiers) must be unaffected
    # by the override, WITHOUT an explicit spec.arch short-circuiting the
    # check (an explicit arch would resolve at the earlier branch in
    # _resolve_model_arch() regardless of scoping, so it wouldn't actually
    # exercise/discriminate this env-var-scoping behavior at all) —
    # otherwise there's no way to distinguish "the override works" from "the
    # override is too broad and catches unrelated ids."
    monkeypatch.setenv(rg.CODEY_TEST_PRIMARY_ARCH_ENV, "qwen3-4b")
    unknown_spec = rg.ModelSpec(model_id="primary-7b", size_bytes=1, n_ctx=1024)
    assert rg._resolve_model_arch(unknown_spec) is None


def test_test_arch_override_invalid_value_raises_valueerror(monkeypatch):
    monkeypatch.setenv(rg.CODEY_TEST_PRIMARY_ARCH_ENV, "not-a-real-arch")
    spec = rg.ModelSpec(model_id="primary", size_bytes=1, n_ctx=1024)
    with pytest.raises(ValueError):
        rg._resolve_model_arch(spec)


def test_test_arch_override_cross_role_value_rejected(monkeypatch):
    # A value that's valid for the OTHER role's env var (e.g. the planner
    # substitute's key used for CODEY_TEST_PRIMARY_ARCH) must be rejected
    # loudly, not silently accepted — a flat, role-agnostic registry would
    # have let this through and produced a WORSE under-estimate (0.5B arch
    # used for the primary/7B slot) than the bug this feature exists to fix.
    monkeypatch.setenv(rg.CODEY_TEST_PRIMARY_ARCH_ENV, "qwen2.5-0.5b-planner")
    spec = rg.ModelSpec(model_id="primary", size_bytes=1, n_ctx=1024)
    with pytest.raises(ValueError):
        rg._resolve_model_arch(spec)

    monkeypatch.delenv(rg.CODEY_TEST_PRIMARY_ARCH_ENV, raising=False)
    monkeypatch.setenv(rg.CODEY_TEST_PLANNER_ARCH_ENV, "qwen3-4b")
    spec2 = rg.ModelSpec(model_id="planner", size_bytes=1, n_ctx=1024)
    with pytest.raises(ValueError):
        rg._resolve_model_arch(spec2)


def test_test_arch_override_invalid_value_propagates_through_can_admit(monkeypatch):
    # A bad override must fail loudly all the way through the real call path
    # a caller actually uses (can_admit()), not just at _resolve_model_arch()
    # directly — this is what makes the failure mode fail-closed (refusing
    # admission) rather than silently admitting on a wrong/omitted estimate.
    monkeypatch.setenv(rg.CODEY_TEST_PRIMARY_ARCH_ENV, "not-a-real-arch")
    spec = rg.ModelSpec(model_id="primary", size_bytes=int(1 * GIB), n_ctx=4096)
    mi = meminfo_bytes(mem_total_gib=10.8, mem_free_gib=8.5, mem_available_gib=9.0)
    with pytest.raises(ValueError):
        rg.can_admit(spec, meminfo=mi, read_temp_fn=NO_THERMAL)


def test_qwen3_4b_test_arch_kv_estimate_is_larger_than_the_default_primary():
    # Pins the arithmetic this override feature exists to fix: if the
    # default primary arch were wrongly used for a resident, substituted
    # Qwen3-4B-Instruct, the KV cache cost would be UNDER-estimated — the
    # dangerous direction for a resource gate. Baseline re-pointed at
    # QWEN35_4B_ARCH (M1-A, 2026-08-22): the retired 7B is no longer any
    # role's default, so comparing against it stopped testing the stated
    # property. The direction still holds and the margin is wider — the
    # hybrid default's per-token factor is 8*4*256 = 8192 against the
    # Qwen3-4B substitute's 36*8*128 = 36864, i.e. ~4.5x, where it used to
    # be ~2.6x against the 7B's 28*4*128 = 14336.
    n_ctx = 4096
    qwen3_4b_kv = rg.estimate_kv_cache_bytes(rg.QWEN3_4B_TEST_ARCH, n_ctx=n_ctx)
    default_primary_kv = rg.estimate_kv_cache_bytes(rg.QWEN35_4B_ARCH, n_ctx=n_ctx)
    assert qwen3_4b_kv > default_primary_kv
    expected = 36 * 2 * 8 * 128 * n_ctx * 2
    assert qwen3_4b_kv == expected


def test_qwen25_0_5b_planner_arch_kv_estimate():
    expected = 24 * 2 * 2 * 64 * 4096 * 2
    assert rg.estimate_kv_cache_bytes(rg.QWEN25_0_5B_PLANNER_ARCH, n_ctx=4096) == expected


# ── NEW-21 regression: real numbers, correctly-computed cost estimate ───────


def _new21_primary_spec():
    # Real on-disk file size, per `ls -la ~/models/qwen2.5-coder-7b/` at the
    # time this module was built: 4683073536 bytes. n_ctx from
    # utils/config.py's MODEL_CONFIG["n_ctx"] (32768) — the same config both
    # the primary and planner llama-server invocations use today (checked in
    # core/loader_v2.py:_spawn_locked()).
    return rg.ModelSpec(
        model_id="primary-7b",
        size_bytes=4_683_073_536,
        n_ctx=32768,
        arch=rg.QWEN25_7B_ARCH,
    )


def _new21_meminfo(mem_available_gib):
    # NEW-21 itself only reports used/free (4.3Gi used / 2.2Gi free), not
    # MemAvailable. Rather than invent one specific MemAvailable value, this
    # is parametrized (see test_new21_regression_rejects_load below) across
    # the full plausible range: MemFree itself (2.2GiB — the floor; what
    # MemAvailable equals if there's no meaningfully reclaimable cache) up
    # through the mathematical UPPER BOUND implied by used/free (`free -h`'s
    # "used" column already excludes reclaimable buffers/cache, so
    # MemAvailable can be at most total - used = 10.8 - 4.3 = 6.5GiB at that
    # moment). Rejection must hold across that entire range for this test to
    # actually validate the gate rather than one convenient number. SwapFree
    # reflects ~1.2Gi already in use before this load, matching NEW-21's
    # "swap climbed from 1.2Gi" starting point.
    return meminfo_bytes(
        mem_total_gib=10.8,
        mem_free_gib=2.2,
        mem_available_gib=mem_available_gib,
        swap_total_gib=8.0,
        swap_free_gib=6.8,
    )


@pytest.mark.parametrize("mem_available_gib", [2.2, 3.5, 5.0, 6.5])
def test_new21_regression_rejects_load_on_ram_margin_alone(mem_available_gib):
    # RAM-margin invariant NEW-21 actually pinned (cost * margin > RAM-only
    # headroom across the full plausible MemAvailable range) — unaffected by
    # TODO.md 7.4a sub-task F's swap-cap recalibration below, verified here
    # with `enable_swap_assist=False` so this stays a pure regression test
    # of REQUIRED_HEADROOM_FACTOR, not entangled with the separate swap-
    # assist mechanism (see test_new21_production_call_shape_swap_assist_may_
    # now_admit below for that mechanism's own, now-different, effect on
    # this exact fixture at the real production call shape).
    spec = _new21_primary_spec()
    mi = _new21_meminfo(mem_available_gib)
    decision = rg.can_admit(spec, meminfo=mi, read_temp_fn=NO_THERMAL, enable_swap_assist=False)
    assert decision.admitted is False
    # Rejected via the live budget check (cost * margin > headroom), not the
    # absolute per-model ceiling — a 7B model is NOT too big for this device
    # outright (it's this project's normal single-model case); it's too big
    # given what's already resident/used at that moment. Confirms the gate
    # is doing the intended "cost vs. live headroom" comparison, not
    # silently rejecting every load via the hard ceiling instead.
    assert decision.hard_reject is False
    assert decision.estimated_cost_bytes * rg.REQUIRED_HEADROOM_FACTOR > decision.headroom_bytes


# TODO.md 7.4a sub-task F (2026-08-11 recalibration) consequence, verified
# directly against this exact NEW-21 fixture, NOT assumed: reserve_slot()'s
# real, production can_admit() call shape leaves `enable_swap_assist` unset,
# resolving to the default-ON swap-assist path (sub-task C2). At this
# fixture's swap terms (SwapTotal=8.0GiB, SwapFree=6.8GiB -> slmk_floor =
# 0.8GiB, gated_swap_free = 6.8 - 2*0.8 = 5.2GiB), the raised 10GiB
# MAX_SWAP_ASSIST_BYTES cap (min(10GiB, 5.2GiB) = 5.2GiB swap contribution)
# now covers the RAM deficit at 3 of the 4 MemAvailable points in NEW-21's
# own plausible range (3.5/5.0/6.5GiB) — only the 2.2GiB floor (MemAvailable
# == MemFree, no reclaimable cache at all) still denies outright: its
# ~5.9GiB deficit (8143MiB required - 2253MiB RAM headroom) exceeds even the
# 5.2GiB gated swap contribution. This is the single-model instance of the
# same "a device state that previously caused real swap distress is now
# admissible" consequence TODO.md 7.4a sub-task F's own write-up already
# flagged for the concurrent 3-model case — NOT previously flagged there for
# the single-model NEW-21 state itself. Logged to NEW_ISSUES.md per rule 8;
# not fixed here (out of scope — see TODO.md 7.4a sub-task F's explicit "do
# not change either ceiling" instruction).
@pytest.mark.parametrize(
    "mem_available_gib,expect_admitted,expect_via_swap",
    [(2.2, False, False), (3.5, True, True), (5.0, True, True), (6.5, True, True)],
)
def test_new21_production_call_shape_swap_assist_may_now_admit(
    mem_available_gib, expect_admitted, expect_via_swap
):
    spec = _new21_primary_spec()
    mi = _new21_meminfo(mem_available_gib)
    decision = rg.can_admit(spec, meminfo=mi, read_temp_fn=NO_THERMAL)
    assert decision.admitted is expect_admitted
    assert decision.admitted_via_swap is expect_via_swap
    assert decision.hard_reject is False
    assert decision.budget_ceiling_exceeded is False


def test_new21_naive_check_without_margin_would_have_admitted():
    """
    Pins the actual bug NEW-21 exposed, at the upper-bound (most favorable)
    endpoint of the plausible MemAvailable range above (6.5GiB): a
    "cost <= headroom" check with NO conservative margin (headroom_factor=1.0)
    would have approved this load. Deliberately only tested at this one
    endpoint (unlike the RAM-margin regression's full range above) — at
    the lower end of the range (2.2-5.0GiB) the raw cost estimate alone
    already exceeds headroom with no margin needed, so headroom_factor's
    effect isn't observable there; 6.5GiB is the only point where the
    naive-vs-real comparison is meaningful. This test fails (loudly) if a
    future change removes/weakens REQUIRED_HEADROOM_FACTOR's effect without
    updating this test to match — that's the intended tripwire.
    """
    spec = _new21_primary_spec()
    mi = _new21_meminfo(mem_available_gib=6.5)
    naive = rg.can_admit(spec, meminfo=mi, headroom_factor=1.0, read_temp_fn=NO_THERMAL)
    assert naive.admitted is True, (
        "fixture no longer demonstrates the NEW-21 naive-check failure mode — "
        "adjust the 6.5GiB endpoint so cost < MemAvailable (no margin) still holds"
    )
    # ...at the real production call shape (enable_swap_assist left unset),
    # the gate's default conservative margin still correctly rejects this
    # load on RAM alone — but, as of TODO.md 7.4a sub-task F's 2026-08-11
    # recalibration, the same call now admits it anyway via the raised
    # 10GiB MAX_SWAP_ASSIST_BYTES cap (see
    # test_new21_production_call_shape_swap_assist_may_now_admit above for
    # the full derivation on this exact fixture) — no longer a bare denial.
    real = rg.can_admit(spec, meminfo=mi, read_temp_fn=NO_THERMAL)
    assert real.admitted is True
    assert real.admitted_via_swap is True
    # ...while the RAM-only path (swap-assist explicitly off) still denies,
    # confirming REQUIRED_HEADROOM_FACTOR's own effect is intact and it is
    # specifically the swap-assist mechanism, not a weakened margin, that
    # changed this outcome:
    real_ram_only = rg.can_admit(
        spec, meminfo=mi, read_temp_fn=NO_THERMAL, enable_swap_assist=False
    )
    assert real_ram_only.admitted is False


def test_new21_reserved_bytes_from_other_slot_also_rejects():
    # Even a smaller candidate model must be rejected if another slot's
    # already-declared cost accounts for most of the live headroom — this is
    # what reserved_bytes/total_reserved_bytes exists for (racing/concurrent
    # admissions in the cross-process case).
    spec = rg.ModelSpec(model_id="small", size_bytes=int(1.5 * GIB), n_ctx=4096)
    mi = meminfo_bytes(mem_total_gib=10.8, mem_free_gib=0.2, mem_available_gib=2.0)
    decision = rg.can_admit(spec, meminfo=mi, reserved_bytes=int(1.8 * GIB), read_temp_fn=NO_THERMAL)
    assert decision.admitted is False


def test_primary_model_admitted_under_idle_conditions():
    # Regression for the reviewed-and-reverted MemFree-only design: on an
    # otherwise-idle device (most of RAM genuinely free), the gate MUST
    # admit the project's own normal single-model case, not reject
    # everything unconditionally.
    spec = _new21_primary_spec()
    mi = meminfo_bytes(mem_total_gib=10.8, mem_free_gib=8.5, mem_available_gib=9.0)
    decision = rg.can_admit(spec, meminfo=mi, read_temp_fn=NO_THERMAL)
    assert decision.admitted is True
    assert decision.hard_reject is False


# ── hard ceiling (absolute, independent of live headroom) ──────────────────


def test_hard_reject_even_with_generous_headroom():
    # System otherwise idle: lots of free RAM — the hard ceiling must still
    # fire for a model too big for the device outright.
    spec = rg.ModelSpec(model_id="too-big", size_bytes=50 * GIB, n_ctx=4096)
    mi = meminfo_bytes(mem_total_gib=10.8, mem_free_gib=8.0, mem_available_gib=9.0)
    decision = rg.can_admit(spec, meminfo=mi, read_temp_fn=NO_THERMAL)
    assert decision.admitted is False
    assert decision.hard_reject is True


def test_hard_ceiling_boundary_flips_hard_reject():
    # Idle device (generous headroom) so only the ceiling check can be
    # responsible for a rejection here — proves the boundary is exactly
    # where compute_device_ceiling_bytes() says it is, and that a model
    # just below it is NOT hard-rejected while one just above it IS.
    mi = meminfo_bytes(mem_total_gib=10.8, mem_free_gib=8.0, mem_available_gib=9.0)
    ceiling = rg.compute_device_ceiling_bytes(mi)
    overhead = rg.DEFAULT_COMPUTE_OVERHEAD_BYTES

    just_under = rg.ModelSpec(model_id="just-under", size_bytes=ceiling - overhead - MIB, n_ctx=1024)
    just_over = rg.ModelSpec(model_id="just-over", size_bytes=ceiling - overhead + MIB, n_ctx=1024)

    under_decision = rg.can_admit(just_under, meminfo=mi, read_temp_fn=NO_THERMAL)
    over_decision = rg.can_admit(just_over, meminfo=mi, read_temp_fn=NO_THERMAL)

    assert under_decision.hard_reject is False
    assert under_decision.admitted is True
    assert over_decision.hard_reject is True
    assert over_decision.admitted is False


def test_would_model_fit_wraps_can_admit():
    spec = rg.ModelSpec(model_id="ok", size_bytes=int(0.5 * GIB), n_ctx=2048)
    mi = meminfo_bytes(mem_total_gib=10.8, mem_free_gib=5.0, mem_available_gib=7.0)
    assert rg.would_model_fit(spec, meminfo=mi, read_temp_fn=NO_THERMAL) is True

    big = rg.ModelSpec(model_id="too-big", size_bytes=50 * GIB, n_ctx=4096)
    assert rg.would_model_fit(big, meminfo=mi, read_temp_fn=NO_THERMAL) is False


# ── thermal signal ────────────────────────────────────────────────────────


def test_can_admit_rejects_when_temperature_critical():
    spec = rg.ModelSpec(model_id="ok", size_bytes=int(0.5 * GIB), n_ctx=2048)
    mi = meminfo_bytes(mem_total_gib=10.8, mem_free_gib=5.0, mem_available_gib=7.0)
    decision = rg.can_admit(spec, meminfo=mi, read_temp_fn=lambda: 95.0)
    assert decision.admitted is False
    assert decision.hard_reject is False
    assert "temperature" in decision.reason.lower()


def test_can_admit_allows_when_temperature_below_critical():
    spec = rg.ModelSpec(model_id="ok", size_bytes=int(0.5 * GIB), n_ctx=2048)
    mi = meminfo_bytes(mem_total_gib=10.8, mem_free_gib=5.0, mem_available_gib=7.0)
    decision = rg.can_admit(spec, meminfo=mi, read_temp_fn=lambda: 40.0)
    assert decision.admitted is True


def test_can_admit_treats_unreadable_temperature_as_no_objection():
    spec = rg.ModelSpec(model_id="ok", size_bytes=int(0.5 * GIB), n_ctx=2048)
    mi = meminfo_bytes(mem_total_gib=10.8, mem_free_gib=5.0, mem_available_gib=7.0)
    decision = rg.can_admit(spec, meminfo=mi, read_temp_fn=lambda: None)
    assert decision.admitted is True


def test_can_admit_treats_temp_read_exception_as_no_objection():
    def _raises():
        raise RuntimeError("thermal zone unreadable")

    spec = rg.ModelSpec(model_id="ok", size_bytes=int(0.5 * GIB), n_ctx=2048)
    mi = meminfo_bytes(mem_total_gib=10.8, mem_free_gib=5.0, mem_available_gib=7.0)
    decision = rg.can_admit(spec, meminfo=mi, read_temp_fn=_raises)
    assert decision.admitted is True


def test_read_current_temp_c_mocked_float_and_none(monkeypatch):
    # Never touches the real device — mocks core.thermal.get_current_temp_c
    # directly, per this module's "no dependency on real live system state"
    # contract.
    import core.thermal as thermal_mod

    monkeypatch.setattr(thermal_mod, "get_current_temp_c", lambda: 42.5)
    assert rg.read_current_temp_c() == 42.5

    monkeypatch.setattr(thermal_mod, "get_current_temp_c", lambda: None)
    assert rg.read_current_temp_c() is None

    def _raises():
        raise RuntimeError("boom")

    monkeypatch.setattr(thermal_mod, "get_current_temp_c", _raises)
    assert rg.read_current_temp_c() is None  # best-effort: exception -> None, never raises


# ── CPU thread/core allocation ───────────────────────────────────────────────


def test_allocate_threads_even_split():
    assert rg.allocate_threads(n_models=2, total_cores=8) == [4, 4]


def test_allocate_threads_uneven_split_gives_remainder_to_first():
    assert rg.allocate_threads(n_models=3, total_cores=8) == [3, 3, 2]


def test_allocate_threads_zero_models():
    assert rg.allocate_threads(n_models=0, total_cores=8) == []


def test_allocate_threads_oversubscribes_rather_than_zero():
    # 5 models, 4 cores, min_threads=1 — each still gets >= 1, even though
    # that sums to more than total_cores.
    allocation = rg.allocate_threads(n_models=5, total_cores=4, min_threads=1)
    assert allocation == [1, 1, 1, 1, 1]
    assert sum(allocation) > 4


def test_allocate_threads_respects_thermal_cap():
    allocation = rg.allocate_threads(n_models=1, total_cores=8, thermal_cap=2)
    assert allocation == [2]


def test_allocate_threads_thermal_cap_never_below_min():
    allocation = rg.allocate_threads(n_models=4, total_cores=4, min_threads=1, thermal_cap=0)
    assert allocation == [1, 1, 1, 1]


def test_get_cpu_core_count_positive():
    assert rg.get_cpu_core_count() >= 1


# ── cross-process residency state store ──────────────────────────────────────


def test_register_list_release_slot_roundtrip(tmp_path):
    slot_id = rg.register_slot("primary-7b", cost_bytes=6 * GIB, port=8080, state_dir=tmp_path)
    slots = rg.list_slots(state_dir=tmp_path)
    assert len(slots) == 1
    assert slots[0]["slot_id"] == slot_id
    assert slots[0]["model_id"] == "primary-7b"
    assert slots[0]["cost_bytes"] == 6 * GIB
    assert slots[0]["pid"] == os.getpid()

    assert rg.total_reserved_bytes(state_dir=tmp_path) == 6 * GIB

    removed = rg.release_slot(slot_id, state_dir=tmp_path)
    assert removed is True
    assert rg.list_slots(state_dir=tmp_path) == []


def test_release_unknown_slot_returns_false(tmp_path):
    assert rg.release_slot("does-not-exist", state_dir=tmp_path) is False


def test_list_slots_reaps_dead_pid(tmp_path):
    # Spawn and immediately finish a real subprocess so its PID is
    # guaranteed to be a real-but-now-dead PID, not a guessed number.
    proc = subprocess.Popen(["true"])
    dead_pid = proc.pid
    proc.wait()

    rg.register_slot("stale", cost_bytes=1 * GIB, pid=dead_pid, state_dir=tmp_path)
    slots = rg.list_slots(state_dir=tmp_path, reap_dead=True)
    assert slots == []


def test_list_slots_reap_dead_false_keeps_stale_entry(tmp_path):
    proc = subprocess.Popen(["true"])
    dead_pid = proc.pid
    proc.wait()

    rg.register_slot("stale", cost_bytes=1 * GIB, pid=dead_pid, state_dir=tmp_path)
    slots = rg.list_slots(state_dir=tmp_path, reap_dead=False)
    assert len(slots) == 1


def _cross_process_writer(state_dir_str, done_flag_path):
    import core.resource_gate as rg_child

    rg_child.register_slot("from-child", cost_bytes=2 * GIB, port=9999, state_dir=Path(state_dir_str))
    Path(done_flag_path).write_text("done")


def test_cross_process_write_visible_to_reader(tmp_path):
    """
    Write from one process, read from another (this test process), confirm
    consistency — per this sub-task's requirement that the residency-state
    primitive be usable across processes (daemon + main.py CLI), not just
    threads within one process.
    """
    done_flag = tmp_path / "done_flag"
    p = Process(target=_cross_process_writer, args=(str(tmp_path), str(done_flag)))
    p.start()
    p.join(timeout=10)
    assert p.exitcode == 0
    assert p.is_alive() is False

    # The child process has already exited by the time we read here (its own
    # PID was the slot's registered owner) — reap_dead=False first, to prove
    # the write really landed on disk and is visible to this separate
    # process's read, independent of liveness reaping.
    slots = rg.list_slots(state_dir=tmp_path, reap_dead=False)
    assert len(slots) == 1
    assert slots[0]["model_id"] == "from-child"
    assert slots[0]["cost_bytes"] == 2 * GIB

    # Now confirm reaping also works correctly across the pid boundary in
    # the cross-process case: since the registering (child) process is gone,
    # a reap pass removes it.
    reaped = rg.list_slots(state_dir=tmp_path, reap_dead=True)
    assert reaped == []


# ── slot lifecycle status (PENDING vs RESIDENT) ──────────────────────────────


def test_register_slot_defaults_to_pending_status(tmp_path):
    slot_id = rg.register_slot("m", cost_bytes=1 * GIB, state_dir=tmp_path)
    slots = rg.list_slots(state_dir=tmp_path)
    assert slots[0]["slot_id"] == slot_id
    assert slots[0]["status"] == rg.SLOT_STATUS_PENDING


def test_mark_resident_transitions_status(tmp_path):
    slot_id = rg.register_slot("m", cost_bytes=1 * GIB, state_dir=tmp_path)
    assert rg.mark_resident(slot_id, state_dir=tmp_path) is True
    slots = rg.list_slots(state_dir=tmp_path)
    assert slots[0]["status"] == rg.SLOT_STATUS_RESIDENT


def test_mark_resident_unknown_slot_returns_false(tmp_path):
    assert rg.mark_resident("does-not-exist", state_dir=tmp_path) is False


def test_mark_resident_pid_arg_rebinds_slot_pid(tmp_path):
    # NEW-81 fix: reserve_slot()/register_slot() register a slot under the
    # CALLING process's own PID (there's no real model subprocess yet at
    # admission time) -- mark_resident()'s optional `pid` lets a caller that
    # later learns the real spawned subprocess's PID rebind the slot to it,
    # so PID-liveness reaping tracks the process that should actually free
    # the slot, not the (possibly long-lived) caller.
    slot_id = rg.register_slot("m", cost_bytes=1 * GIB, pid=os.getpid(), state_dir=tmp_path)
    assert rg.list_slots(state_dir=tmp_path)[0]["pid"] == os.getpid()

    real_child_pid = 999999  # doesn't need to be alive for this assertion
    assert rg.mark_resident(slot_id, state_dir=tmp_path, pid=real_child_pid) is True

    slots = rg.list_slots(state_dir=tmp_path, reap_dead=False)
    assert slots[0]["pid"] == real_child_pid
    assert slots[0]["status"] == rg.SLOT_STATUS_RESIDENT


def test_mark_resident_without_pid_arg_leaves_pid_unchanged(tmp_path):
    # Default (pid=None) must be a no-op on the pid field -- existing
    # callers that don't pass it keep today's behavior exactly.
    slot_id = rg.register_slot("m", cost_bytes=1 * GIB, pid=12345, state_dir=tmp_path)
    assert rg.mark_resident(slot_id, state_dir=tmp_path) is True
    slots = rg.list_slots(state_dir=tmp_path, reap_dead=False)
    assert slots[0]["pid"] == 12345


def test_total_reserved_bytes_excludes_resident_slots(tmp_path):
    # Contract fix (code-reviewer finding): total_reserved_bytes() must
    # match compute_headroom_bytes()'s documented meaning of reserved_bytes
    # ("concurrently being admitted/loaded but haven't yet shown up in a
    # fresh /proc/meminfo read") — a RESIDENT slot's memory is already
    # reflected in a fresh meminfo read, so it must NOT also be counted
    # here, or headroom gets double-counted/undercounted.
    pending_id = rg.register_slot("pending-model", cost_bytes=2 * GIB, state_dir=tmp_path)
    resident_id = rg.register_slot("resident-model", cost_bytes=3 * GIB, state_dir=tmp_path)
    rg.mark_resident(resident_id, state_dir=tmp_path)

    assert rg.total_reserved_bytes(state_dir=tmp_path) == 2 * GIB

    rg.release_slot(pending_id, state_dir=tmp_path)
    rg.release_slot(resident_id, state_dir=tmp_path)


def test_total_reserved_bytes_treats_missing_status_as_pending(tmp_path):
    # Legacy/pre-status-field entries (or any entry missing the key) must
    # still be counted — conservative default, not silently excluded.
    state_path = tmp_path / "resource_gate_state.json"
    import json as _json

    state_path.write_text(
        _json.dumps(
            [
                {
                    "slot_id": "legacy",
                    "model_id": "legacy-model",
                    "cost_bytes": 1 * GIB,
                    "pid": None,
                    "port": None,
                    "threads": None,
                    "registered_at": 0.0,
                    # deliberately no "status" key
                }
            ]
        )
    )
    assert rg.total_reserved_bytes(state_dir=tmp_path) == 1 * GIB


# ── reserve_slot(): atomic check-and-register (TOCTOU fix) ──────────────────


def test_reserve_slot_admits_and_registers_when_room(tmp_path):
    spec = rg.ModelSpec(model_id="ok", size_bytes=int(0.5 * GIB), n_ctx=2048, compute_overhead_bytes=0)
    mi = meminfo_bytes(mem_total_gib=10.8, mem_free_gib=5.0, mem_available_gib=5.0)
    decision, slot_id = rg.reserve_slot(spec, meminfo=mi, read_temp_fn=NO_THERMAL, state_dir=tmp_path)
    assert decision.admitted is True
    assert slot_id is not None
    slots = rg.list_slots(state_dir=tmp_path)
    assert len(slots) == 1
    assert slots[0]["slot_id"] == slot_id
    assert slots[0]["status"] == rg.SLOT_STATUS_PENDING
    assert slots[0]["cost_bytes"] == decision.estimated_cost_bytes


def test_reserve_slot_refuses_and_does_not_register_when_no_room(tmp_path):
    spec = rg.ModelSpec(model_id="too-big", size_bytes=50 * GIB, n_ctx=4096)
    mi = meminfo_bytes(mem_total_gib=10.8, mem_free_gib=8.0, mem_available_gib=9.0)
    decision, slot_id = rg.reserve_slot(spec, meminfo=mi, read_temp_fn=NO_THERMAL, state_dir=tmp_path)
    assert decision.admitted is False
    assert slot_id is None
    assert rg.list_slots(state_dir=tmp_path) == []


def test_reserve_slot_bad_test_arch_override_raises_and_registers_nothing(monkeypatch, tmp_path):
    # The ValueError from a bad CODEY_TEST_*_ARCH override is raised from
    # inside can_admit(), which reserve_slot() calls WHILE holding
    # _LockedState's flock (see reserve_slot()'s docstring on why live
    # signals are read before the lock, but can_admit() itself runs inside
    # it). Confirms the exception still propagates cleanly out of
    # reserve_slot() with no slot registered and no leaked/held lock — the
    # one path in this module where the new raise crosses a flock, which
    # matters given this module's history of process-lifecycle bugs.
    monkeypatch.setenv(rg.CODEY_TEST_PRIMARY_ARCH_ENV, "not-a-real-arch")
    spec = rg.ModelSpec(model_id="primary", size_bytes=int(0.5 * GIB), n_ctx=2048)
    mi = meminfo_bytes(mem_total_gib=10.8, mem_free_gib=5.0, mem_available_gib=5.0)
    with pytest.raises(ValueError):
        rg.reserve_slot(spec, meminfo=mi, read_temp_fn=NO_THERMAL, state_dir=tmp_path)
    assert rg.list_slots(state_dir=tmp_path) == []
    # Lock released cleanly despite the exception: a second, unrelated call
    # against the same state_dir must not hang/deadlock on a stuck flock.
    ok_spec = rg.ModelSpec(model_id="ok", size_bytes=int(0.1 * GIB), n_ctx=1024, compute_overhead_bytes=0)
    decision, slot_id = rg.reserve_slot(ok_spec, meminfo=mi, read_temp_fn=NO_THERMAL, state_dir=tmp_path)
    assert decision.admitted is True
    assert slot_id is not None


def test_reserve_slot_accounts_for_prior_pending_reservation(tmp_path):
    # A second call must see the first call's reservation via the store
    # itself (not require the caller to separately track/pass
    # reserved_bytes) — this is the whole point of folding the read into
    # the same locked operation as the check.
    mi = meminfo_bytes(mem_total_gib=10.8, mem_free_gib=2.5, mem_available_gib=2.5)
    spec = rg.ModelSpec(model_id="m", size_bytes=int(1.5 * GIB), n_ctx=1024, compute_overhead_bytes=0)

    first = rg.reserve_slot(spec, meminfo=mi, read_temp_fn=NO_THERMAL, state_dir=tmp_path)
    assert first[0].admitted is True  # cost*1.25 = 1.875GiB <= 2.5GiB headroom

    second = rg.reserve_slot(spec, meminfo=mi, read_temp_fn=NO_THERMAL, state_dir=tmp_path)
    # headroom for the second call = 2.5GiB - 1.5GiB reserved = 1.0GiB,
    # required = 1.875GiB > 1.0GiB -> refused.
    assert second[0].admitted is False
    assert second[1] is None
    assert rg.total_reserved_bytes(state_dir=tmp_path) == int(1.5 * GIB)


# Budget shared by both the real test and its negative control below.
# cost * REQUIRED_HEADROOM_FACTOR(1.25) = 2.25GiB required per admission.
# Deterministic arithmetic (every candidate has identical cost/threshold):
#   1st: headroom=5.0GiB, required=2.25GiB -> admit, reserved=1.8GiB
#   2nd: headroom=5.0-1.8=3.2GiB, required=2.25GiB -> admit, reserved=3.6GiB
#   3rd+: headroom=5.0-3.6=1.4GiB, required=2.25GiB -> refuse
# So a correct, single-lock-acquisition implementation admits exactly 2, no
# matter how many callers race or in what order they acquire the lock.
_RACE_COST = int(1.8 * GIB)
_RACE_MEMINFO = meminfo_bytes(mem_total_gib=10.8, mem_free_gib=5.0, mem_available_gib=5.0)
_RACE_N_THREADS = 12


def _reserve_unsafe(model_id, state_dir):
    """
    The exact three-separate-flock-acquisitions pattern `reserve_slot()`
    replaces (read reserved total, check admission, register) — used ONLY
    as a negative control in test_reserve_unsafe_pattern_over_admits below,
    to prove the concurrency test actually discriminates safe from unsafe
    behavior. Deliberately NOT added to core/resource_gate.py itself — it's
    a known-bad pattern, not a primitive worth offering callers.
    """
    spec = rg.ModelSpec(model_id=model_id, size_bytes=_RACE_COST, n_ctx=1024, compute_overhead_bytes=0)
    reserved = rg.total_reserved_bytes(state_dir=state_dir)
    decision = rg.can_admit(spec, meminfo=_RACE_MEMINFO, reserved_bytes=reserved, read_temp_fn=NO_THERMAL)
    if not decision.admitted:
        return decision, None
    # Widens the window that already exists between the read above and the
    # write below (three separate flock acquisitions with no lock held
    # across them) — does not create a race that wasn't already there.
    time.sleep(0.01)
    slot_id = rg.register_slot(model_id, cost_bytes=decision.estimated_cost_bytes, state_dir=state_dir)
    return decision, slot_id


def _run_race(reserve_fn, tmp_path):
    """Fire _RACE_N_THREADS threads at `reserve_fn` simultaneously (via a
    Barrier, so we have actual evidence they overlapped rather than just
    hoping thread scheduling interleaved them) and return the list of
    (admitted, slot_id) results."""
    barrier = threading.Barrier(_RACE_N_THREADS)
    results = []
    results_lock = threading.Lock()

    def worker(i):
        barrier.wait(timeout=10)  # all threads hit the check together
        decision, slot_id = reserve_fn(f"race-{i}", tmp_path)
        with results_lock:
            results.append((decision.admitted, slot_id))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(_RACE_N_THREADS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    for t in threads:
        assert not t.is_alive(), "worker thread failed to complete — possible deadlock"
    assert len(results) == _RACE_N_THREADS
    return results


def test_reserve_unsafe_pattern_over_admits(tmp_path):
    """
    Negative control: proves the concurrency test below actually
    discriminates safe from unsafe behavior, rather than passing
    unconditionally because a tiny critical section never gets interleaved
    in practice. Drives the exact three-separate-flock-acquisitions pattern
    `reserve_slot()` replaces through the same racing-threads harness and
    asserts it DOES over-admit beyond the fixed budget (more than the 2
    slots the budget arithmetic allows).
    """
    results = _run_race(lambda model_id, sd: _reserve_unsafe(model_id, sd), tmp_path)
    admitted = [r for r in results if r[0]]
    assert len(admitted) > 2, (
        "expected the known-unsafe three-lock-acquisition pattern to over-admit "
        f"beyond the 2-slot budget under contention, but only {len(admitted)} were "
        "admitted — this harness may not actually be exercising the race; "
        "re-check timing/Barrier before trusting the real reserve_slot() test above"
    )


def test_reserve_slot_concurrent_does_not_over_admit(tmp_path):
    """
    Regression for the TOCTOU race a code-reviewer pass found in the
    reserve-then-register flow (three separate flock acquisitions, with a
    window between the admission check and the write where two racing
    callers could both pass the check). Spawns many threads all trying to
    reserve a slot against a fixed, tight memory budget simultaneously
    (synchronized via a Barrier so they're proven to overlap — see
    test_reserve_unsafe_pattern_over_admits above for confirmation this
    harness actually catches the race it's designed to catch), and asserts
    the store never ends up holding more reservations than the budget
    arithmetic allows for a single-lock-acquisition, non-racing sequence of
    the same calls.
    """

    def reserve_fn(model_id, sd):
        spec = rg.ModelSpec(model_id=model_id, size_bytes=_RACE_COST, n_ctx=1024, compute_overhead_bytes=0)
        return rg.reserve_slot(spec, meminfo=_RACE_MEMINFO, read_temp_fn=NO_THERMAL, state_dir=sd)

    results = _run_race(reserve_fn, tmp_path)
    admitted = [r for r in results if r[0]]
    assert len(admitted) == 2, (
        f"expected exactly 2 admissions given the fixed budget, got {len(admitted)} — "
        "over-admission indicates the check-then-write race reopened"
    )
    # Cross-check against the actual store contents, not just the in-memory
    # decisions collected above — confirms the persisted state itself never
    # exceeds the budget, which is the property that actually matters.
    stored = rg.list_slots(state_dir=tmp_path)
    assert len(stored) == 2
    assert rg.total_reserved_bytes(state_dir=tmp_path) == 2 * _RACE_COST


def test_state_dir_defaults_to_codey_state_dir(monkeypatch):
    # Confirm the default path resolution uses CODEY_STATE_DIR without
    # actually touching it — redirect CODEY_STATE_DIR itself to a temp dir
    # for the duration of this one test.
    with tempfile.TemporaryDirectory() as d:
        monkeypatch.setattr(rg, "CODEY_STATE_DIR", Path(d))
        slot_id = rg.register_slot("x", cost_bytes=1, state_dir=None)
        assert (Path(d) / "resource_gate_state.json").exists()
        rg.release_slot(slot_id, state_dir=None)


# ── Rolling CPU% sampler (Track 3 Phase 5a / 7.4 sub-task A) ────────────────


@pytest.fixture(autouse=False)
def _clean_cpu_sampler():
    """Reset the module-global rolling CPU sampler before and after each
    test that uses it, so ordered test runs can't leak history/seed state
    between tests (same precedent as core/thermal.py's reset_thermal())."""
    rg.reset_cpu_sampler()
    yield
    rg.reset_cpu_sampler()


def _write_stat_line(path: Path, idle: int, total_minus_idle: int):
    """Write a synthetic /proc/stat first line with a controlled
    idle/non-idle split. Field order: user nice system idle iowait ...
    Only `idle` (index 3) and the sum of all fields matter to
    _read_proc_stat_cpu_line(), so the other non-idle time is dumped into
    the first field."""
    path.write_text(f"cpu  {total_minus_idle} 0 0 {idle} 0 0 0 0 0 0\n")


def test_sample_cpu_percent_first_call_seeds_and_returns_none(tmp_path, _clean_cpu_sampler):
    stat = tmp_path / "stat"
    _write_stat_line(stat, idle=1000, total_minus_idle=1000)
    # None (not 0.0): the seed call has nothing to diff against yet, so it
    # hasn't actually measured anything — 0.0 would be indistinguishable
    # from a genuinely idle reading.
    assert rg.sample_cpu_percent(str(stat)) is None
    assert rg.get_cpu_history() == []  # seed call records no history entry


def test_sample_cpu_percent_computes_delta_and_records_history(tmp_path, _clean_cpu_sampler):
    stat = tmp_path / "stat"
    _write_stat_line(stat, idle=1000, total_minus_idle=1000)
    rg.sample_cpu_percent(str(stat))  # seed

    # Second sample: total ticks advance by 200 (100 idle, 100 busy) -> 50% busy
    _write_stat_line(stat, idle=1100, total_minus_idle=1100)
    pct = rg.sample_cpu_percent(str(stat))
    assert pct == pytest.approx(50.0)

    history = rg.get_cpu_history()
    assert len(history) == 1
    ts, recorded_pct = history[0]
    assert recorded_pct == pytest.approx(50.0)
    assert ts <= time.time()


def test_sample_cpu_percent_fully_idle_delta_is_zero(tmp_path, _clean_cpu_sampler):
    stat = tmp_path / "stat"
    _write_stat_line(stat, idle=1000, total_minus_idle=1000)
    rg.sample_cpu_percent(str(stat))
    _write_stat_line(stat, idle=1100, total_minus_idle=1000)  # only idle advances
    assert rg.sample_cpu_percent(str(stat)) == pytest.approx(0.0)


def test_sample_cpu_percent_unreadable_file_returns_none_and_no_history(_clean_cpu_sampler):
    # None (not 0.0): a read failure must not be indistinguishable from a
    # genuinely idle reading — see sample_cpu_percent()'s docstring.
    assert rg.sample_cpu_percent("/nonexistent/proc/stat") is None
    assert rg.get_cpu_history() == []


def test_get_cpu_history_filters_by_max_age(tmp_path, _clean_cpu_sampler):
    stat = tmp_path / "stat"
    _write_stat_line(stat, idle=0, total_minus_idle=0)
    rg.sample_cpu_percent(str(stat))
    _write_stat_line(stat, idle=100, total_minus_idle=100)
    rg.sample_cpu_percent(str(stat))
    # Backdate the one recorded sample beyond any reasonable max_age filter.
    rg._cpu_history[:] = [(time.time() - 3600, p) for _, p in rg._cpu_history]
    assert rg.get_cpu_history(max_age_sec=60) == []
    assert len(rg.get_cpu_history()) == 1  # unfiltered call still sees it


def test_get_current_cpu_percent_uses_last_history_sample_when_available(tmp_path, _clean_cpu_sampler):
    stat = tmp_path / "stat"
    _write_stat_line(stat, idle=0, total_minus_idle=0)
    rg.sample_cpu_percent(str(stat))
    _write_stat_line(stat, idle=0, total_minus_idle=100)  # 100% busy delta
    rg.sample_cpu_percent(str(stat))
    assert rg.get_current_cpu_percent() == pytest.approx(100.0)


def test_get_current_cpu_percent_cold_start_falls_back_to_fresh_sample(_clean_cpu_sampler):
    # No prior sample_cpu_percent() call in this process (history empty) —
    # must fall back to a real (mocked, no real sleep) cold-start read
    # instead of silently returning a meaningless 0.0.
    calls = iter([(1000, 2000), (1050, 2100)])  # (idle, total) pairs

    def fake_stat_line(path="/proc/stat"):
        idle_total = next(calls)
        return idle_total

    import core.resource_gate as _rg

    orig = _rg._read_proc_stat_cpu_line
    _rg._read_proc_stat_cpu_line = fake_stat_line
    try:
        pct = rg.get_current_cpu_percent(cold_start_sample_sec=0.0)
    finally:
        _rg._read_proc_stat_cpu_line = orig
    # d_idle=50, d_total=100 -> 50% busy
    assert pct == pytest.approx(50.0)


def test_reset_cpu_sampler_clears_seed_and_history(tmp_path, _clean_cpu_sampler):
    stat = tmp_path / "stat"
    _write_stat_line(stat, idle=0, total_minus_idle=0)
    rg.sample_cpu_percent(str(stat))
    _write_stat_line(stat, idle=0, total_minus_idle=100)
    rg.sample_cpu_percent(str(stat))
    assert rg.get_cpu_history() != []

    rg.reset_cpu_sampler()
    assert rg.get_cpu_history() == []
    # After reset, the next call re-seeds (returns None, no history entry)
    # exactly like a fresh process would.
    assert rg.sample_cpu_percent(str(stat)) is None
    assert rg.get_cpu_history() == []


# ── Snapshot composer (get_resource_snapshot) ────────────────────────────────


class _FakeStateStore:
    def __init__(self, pending=0, running=0):
        self._pending = pending
        self._running = running

    def get_tasks_by_status(self, status):
        if status == "pending":
            return list(range(self._pending))
        if status == "running":
            return list(range(self._running))
        return []


class _RaisingStateStore:
    def get_tasks_by_status(self, status):
        raise RuntimeError("db unavailable")


def test_get_resource_snapshot_composes_all_injected_signals():
    meminfo = meminfo_bytes(mem_total_gib=11, mem_free_gib=2, mem_available_gib=6)
    snap = rg.get_resource_snapshot(
        meminfo=meminfo,
        read_temp_fn=lambda: 42.5,
        read_battery_fn=lambda: (77, True),
        state_store=_FakeStateStore(pending=3, running=1),
        cpu_percent=12.5,
    )
    assert snap.cpu_percent == 12.5
    assert snap.ram_headroom_bytes == rg.compute_headroom_bytes(meminfo)
    assert snap.ram_total_bytes == meminfo["MemTotal"]
    assert snap.temperature_c == 42.5
    assert snap.queue_pending == 3
    assert snap.queue_running == 1
    assert snap.battery_percent == 77
    assert snap.battery_charging is True
    assert snap.timestamp <= time.time()


def test_get_resource_snapshot_thermal_failure_does_not_blank_other_signals():
    meminfo = meminfo_bytes(mem_total_gib=11, mem_free_gib=2, mem_available_gib=6)

    def raising_temp():
        raise RuntimeError("no sensor")

    snap = rg.get_resource_snapshot(
        meminfo=meminfo,
        read_temp_fn=raising_temp,
        read_battery_fn=lambda: (50, False),
        state_store=_FakeStateStore(pending=1, running=0),
        cpu_percent=5.0,
    )
    assert snap.temperature_c is None
    assert snap.battery_percent == 50
    assert snap.queue_pending == 1


def test_get_resource_snapshot_battery_failure_does_not_blank_other_signals():
    meminfo = meminfo_bytes(mem_total_gib=11, mem_free_gib=2, mem_available_gib=6)

    def raising_battery():
        raise RuntimeError("termux-battery-status unavailable")

    snap = rg.get_resource_snapshot(
        meminfo=meminfo,
        read_temp_fn=lambda: 30.0,
        read_battery_fn=raising_battery,
        state_store=_FakeStateStore(pending=0, running=0),
        cpu_percent=5.0,
    )
    assert snap.battery_percent is None
    assert snap.battery_charging is False
    assert snap.temperature_c == 30.0


def test_get_resource_snapshot_queue_read_failure_does_not_blank_other_signals():
    meminfo = meminfo_bytes(mem_total_gib=11, mem_free_gib=2, mem_available_gib=6)
    snap = rg.get_resource_snapshot(
        meminfo=meminfo,
        read_temp_fn=lambda: 30.0,
        read_battery_fn=lambda: (99, False),
        state_store=_RaisingStateStore(),
        cpu_percent=5.0,
    )
    assert snap.queue_pending == 0
    assert snap.queue_running == 0
    assert snap.temperature_c == 30.0
    assert snap.battery_percent == 99


# ── is_tui_session_active / is_gui_client_connected / is_interactive_session_active ──
# Track 3 Phase 5a / 7.4 sub-task B. Synthetic fixtures throughout (tmp_path
# directories/files, subprocess.Popen(["true"]) for a real-but-dead PID) —
# no dependency on a real running main.py/gui/server.py instance, matching
# this module's existing test convention. TUI sessions live one-per-file
# under a directory (TUI_SESSIONS_DIR / f"{pid}.pid"), not a single shared
# file, so two concurrent sessions can never overwrite each other's entry.


def test_is_tui_session_active_missing_dir_is_false(tmp_path):
    assert rg.is_tui_session_active(sessions_dir=tmp_path / "tui-sessions") is False


def test_is_tui_session_active_empty_dir_is_false(tmp_path):
    sessions_dir = tmp_path / "tui-sessions"
    sessions_dir.mkdir()
    assert rg.is_tui_session_active(sessions_dir=sessions_dir) is False


def test_is_tui_session_active_live_pid_is_true(tmp_path):
    sessions_dir = tmp_path / "tui-sessions"
    sessions_dir.mkdir()
    pid = os.getpid()
    (sessions_dir / f"{pid}.pid").write_text(str(pid))
    assert rg.is_tui_session_active(sessions_dir=sessions_dir) is True


def test_is_tui_session_active_stale_pid_is_false_and_self_heals(tmp_path):
    proc = subprocess.Popen(["true"])
    dead_pid = proc.pid
    proc.wait()

    sessions_dir = tmp_path / "tui-sessions"
    sessions_dir.mkdir()
    session_file = sessions_dir / f"{dead_pid}.pid"
    session_file.write_text(str(dead_pid))

    assert rg.is_tui_session_active(sessions_dir=sessions_dir) is False
    # Self-healing: the stale entry is removed as a side effect of the
    # check, matching core/daemon.py:check_pid_file()'s same behavior.
    assert not session_file.exists()


def test_is_tui_session_active_unreadable_file_fails_closed_to_true(tmp_path):
    # A permission-denied (existing but unopenable) entry must fail closed
    # toward "treat as active" — the safe direction for a caller deciding
    # whether to defer background work — rather than being silently
    # indistinguishable from "no session". See is_tui_session_active()'s
    # own comment on this branch for why this is transient in practice,
    # not a permanent wedge.
    sessions_dir = tmp_path / "tui-sessions"
    sessions_dir.mkdir()
    session_file = sessions_dir / f"{os.getpid()}.pid"
    session_file.write_text(str(os.getpid()))
    session_file.chmod(0o000)
    try:
        assert rg.is_tui_session_active(sessions_dir=sessions_dir) is True
    finally:
        session_file.chmod(0o644)


def test_is_tui_session_active_corrupt_pid_file_is_false_and_removed(tmp_path):
    sessions_dir = tmp_path / "tui-sessions"
    sessions_dir.mkdir()
    session_file = sessions_dir / "not-a-pid.pid"
    session_file.write_text("not-a-pid")
    assert rg.is_tui_session_active(sessions_dir=sessions_dir) is False
    assert not session_file.exists()


def test_is_tui_session_active_two_concurrent_sessions_survive_one_exiting(tmp_path):
    # The regression this fix is for: a second session's write/removal
    # must not destroy a first, still-live session's entry, and the
    # composed signal must correctly track each session independently.
    sessions_dir = tmp_path / "tui-sessions"
    sessions_dir.mkdir()
    pid_a = os.getpid()
    proc_b = subprocess.Popen(["sleep", "30"])
    pid_b = proc_b.pid
    try:
        session_a = sessions_dir / f"{pid_a}.pid"
        session_b = sessions_dir / f"{pid_b}.pid"
        session_a.write_text(str(pid_a))
        session_b.write_text(str(pid_b))

        assert rg.is_tui_session_active(sessions_dir=sessions_dir) is True

        # B exits and removes its own entry — A's presence must still be
        # correctly reported.
        session_b.unlink()
        assert session_a.exists()
        assert rg.is_tui_session_active(sessions_dir=sessions_dir) is True

        # A exits too — now nothing is left.
        session_a.unlink()
        assert rg.is_tui_session_active(sessions_dir=sessions_dir) is False
    finally:
        proc_b.kill()
        proc_b.wait()


def test_is_tui_session_active_crashed_session_is_reaped_without_hiding_live_one(tmp_path):
    # B is SIGKILL'd (crash, not a clean exit) — its dead PID is left
    # behind in its OWN file. Self-healing must reap only B's entry, and
    # must not touch A's still-live entry in the process.
    sessions_dir = tmp_path / "tui-sessions"
    sessions_dir.mkdir()
    pid_a = os.getpid()

    proc_b = subprocess.Popen(["true"])
    dead_pid_b = proc_b.pid
    proc_b.wait()

    session_a = sessions_dir / f"{pid_a}.pid"
    session_b = sessions_dir / f"{dead_pid_b}.pid"
    session_a.write_text(str(pid_a))
    session_b.write_text(str(dead_pid_b))

    assert rg.is_tui_session_active(sessions_dir=sessions_dir) is True
    assert not session_b.exists()
    assert session_a.exists()


def test_is_gui_client_connected_missing_file_is_false(tmp_path):
    assert (
        rg.is_gui_client_connected(
            clients_file=tmp_path / "gui-clients.count",
            gui_pid_file=tmp_path / "gui-server.pid",
        )
        is False
    )


def test_is_gui_client_connected_zero_count_is_false(tmp_path):
    clients_file = tmp_path / "gui-clients.count"
    clients_file.write_text("0")
    assert (
        rg.is_gui_client_connected(
            clients_file=clients_file, gui_pid_file=tmp_path / "gui-server.pid"
        )
        is False
    )


def test_is_gui_client_connected_positive_count_no_pid_file_is_true(tmp_path):
    # No GUI PID file to cross-check against at all — nothing to invalidate
    # the count with, so it's trusted as-is.
    clients_file = tmp_path / "gui-clients.count"
    clients_file.write_text("2")
    assert (
        rg.is_gui_client_connected(
            clients_file=clients_file, gui_pid_file=tmp_path / "gui-server.pid"
        )
        is True
    )


def test_is_gui_client_connected_positive_count_live_gui_pid_is_true(tmp_path):
    clients_file = tmp_path / "gui-clients.count"
    clients_file.write_text("1")
    gui_pid_file = tmp_path / "gui-server.pid"
    gui_pid_file.write_text(str(os.getpid()))
    assert (
        rg.is_gui_client_connected(clients_file=clients_file, gui_pid_file=gui_pid_file) is True
    )


def test_is_gui_client_connected_positive_count_dead_gui_pid_is_stale(tmp_path):
    # A GUI server that crashed while clients were connected must not leave
    # a false-positive "someone's watching" signal behind forever.
    proc = subprocess.Popen(["true"])
    dead_pid = proc.pid
    proc.wait()

    clients_file = tmp_path / "gui-clients.count"
    clients_file.write_text("3")
    gui_pid_file = tmp_path / "gui-server.pid"
    gui_pid_file.write_text(str(dead_pid))

    assert (
        rg.is_gui_client_connected(clients_file=clients_file, gui_pid_file=gui_pid_file) is False
    )


def test_is_gui_client_connected_corrupt_count_file_is_false(tmp_path):
    clients_file = tmp_path / "gui-clients.count"
    clients_file.write_text("not-a-count")
    assert (
        rg.is_gui_client_connected(
            clients_file=clients_file, gui_pid_file=tmp_path / "gui-server.pid"
        )
        is False
    )


def test_is_interactive_session_active_false_when_neither_active(tmp_path):
    assert (
        rg.is_interactive_session_active(
            tui_sessions_dir=tmp_path / "tui-sessions",
            gui_clients_file=tmp_path / "gui-clients.count",
            gui_pid_file=tmp_path / "gui-server.pid",
        )
        is False
    )


def test_is_interactive_session_active_true_when_only_tui_active(tmp_path):
    tui_sessions_dir = tmp_path / "tui-sessions"
    tui_sessions_dir.mkdir()
    (tui_sessions_dir / f"{os.getpid()}.pid").write_text(str(os.getpid()))
    assert (
        rg.is_interactive_session_active(
            tui_sessions_dir=tui_sessions_dir,
            gui_clients_file=tmp_path / "gui-clients.count",
            gui_pid_file=tmp_path / "gui-server.pid",
        )
        is True
    )


def test_is_interactive_session_active_true_when_only_gui_active(tmp_path):
    clients_file = tmp_path / "gui-clients.count"
    clients_file.write_text("1")
    gui_pid_file = tmp_path / "gui-server.pid"
    gui_pid_file.write_text(str(os.getpid()))
    assert (
        rg.is_interactive_session_active(
            tui_sessions_dir=tmp_path / "tui-sessions",
            gui_clients_file=clients_file,
            gui_pid_file=gui_pid_file,
        )
        is True
    )


# ── can_dispatch_task() (7.4 sub-task C) ─────────────────────────────────────
# Every check below uses a synthetic ResourceSnapshot built directly — no real
# hardware/model reads, matching this module's existing test convention.


def _snapshot(
    cpu_percent=10.0,
    ram_headroom_bytes=4 * GIB,
    temperature_c=40.0,
    battery_percent=80,
    battery_charging=False,
    queue_pending=0,
    queue_running=0,
):
    return rg.ResourceSnapshot(
        cpu_percent=cpu_percent,
        ram_headroom_bytes=ram_headroom_bytes,
        ram_total_bytes=12 * GIB,
        temperature_c=temperature_c,
        queue_pending=queue_pending,
        queue_running=queue_running,
        battery_percent=battery_percent,
        battery_charging=battery_charging,
        timestamp=time.time(),
    )


def test_can_dispatch_task_allows_within_all_limits():
    decision = rg.can_dispatch_task(_snapshot(), interactive_active=False)
    assert decision.allowed is True


def test_can_dispatch_task_refuses_when_interactive_active():
    # Interactive-lock check takes priority over everything else — even a
    # snapshot that would otherwise be fully fine.
    decision = rg.can_dispatch_task(_snapshot(), interactive_active=True)
    assert decision.allowed is False
    assert "interactive" in decision.reason.lower()


def test_can_dispatch_task_refuses_at_critical_temperature():
    snap = _snapshot(temperature_c=91.0)  # THERMAL_CONFIG["temp_critical"] == 90
    decision = rg.can_dispatch_task(snap, interactive_active=False)
    assert decision.allowed is False
    assert "temperature" in decision.reason.lower()


def test_can_dispatch_task_allows_below_critical_temperature():
    snap = _snapshot(temperature_c=89.0)
    decision = rg.can_dispatch_task(snap, interactive_active=False)
    assert decision.allowed is True


def test_can_dispatch_task_treats_unreadable_temperature_as_no_objection():
    snap = _snapshot(temperature_c=None)
    decision = rg.can_dispatch_task(snap, interactive_active=False)
    assert decision.allowed is True


def test_can_dispatch_task_refuses_on_critical_battery_not_charging():
    snap = _snapshot(battery_percent=5, battery_charging=False)  # batt_critical == 5
    decision = rg.can_dispatch_task(snap, interactive_active=False)
    assert decision.allowed is False
    assert "battery" in decision.reason.lower()


def test_can_dispatch_task_allows_critical_battery_while_charging():
    # Mirrors core/recursive.py:get_adaptive_depth()'s "not charging AND
    # critical" convention — charging exempts the battery check entirely.
    snap = _snapshot(battery_percent=5, battery_charging=True)
    decision = rg.can_dispatch_task(snap, interactive_active=False)
    assert decision.allowed is True


def test_can_dispatch_task_allows_low_but_not_critical_battery_not_charging():
    snap = _snapshot(battery_percent=6, battery_charging=False)
    decision = rg.can_dispatch_task(snap, interactive_active=False)
    assert decision.allowed is True


def test_can_dispatch_task_refuses_below_ram_headroom_floor():
    snap = _snapshot(ram_headroom_bytes=rg.DISPATCH_MIN_HEADROOM_BYTES - MIB)
    decision = rg.can_dispatch_task(snap, interactive_active=False)
    assert decision.allowed is False
    assert "ram" in decision.reason.lower() or "headroom" in decision.reason.lower()


def test_can_dispatch_task_allows_at_ram_headroom_floor_boundary():
    snap = _snapshot(ram_headroom_bytes=rg.DISPATCH_MIN_HEADROOM_BYTES)
    decision = rg.can_dispatch_task(snap, interactive_active=False)
    assert decision.allowed is True


def test_can_dispatch_task_allows_but_flags_unmeasured_cpu():
    # NEW-108: cpu_percent is always None on this device (/proc/stat
    # permission-denied). This must not refuse dispatch, but the reason
    # string must say the CPU leg was unmeasured — otherwise a
    # live-verifier reading logs could mistake "gate open" for "CPU
    # confirmed low."
    snap = _snapshot(cpu_percent=None)
    decision = rg.can_dispatch_task(snap, interactive_active=False)
    assert decision.allowed is True
    assert "cpu" in decision.reason.lower()
    assert "unmeasur" in decision.reason.lower()


def test_can_dispatch_task_priority_interactive_over_thermal():
    # Interactive lock refuses even when thermal is also critical — priority
    # order matters for which reason string callers see.
    snap = _snapshot(temperature_c=95.0)
    decision = rg.can_dispatch_task(snap, interactive_active=True)
    assert decision.allowed is False
    assert "interactive" in decision.reason.lower()


# ── Rolling thermal sampler (7.4 sub-task D) ─────────────────────────────────
# Mirrors the CPU sampler tests above exactly — see that section's own
# comments for the reasoning; this one differs only in that a real
# read_temp_fn stub (not a synthetic /proc/stat file) is injected, matching
# sample_temperature_c()'s own read_temp_fn parameter.


@pytest.fixture(autouse=False)
def _clean_temp_sampler():
    rg.reset_temp_sampler()
    yield
    rg.reset_temp_sampler()


def test_sample_temperature_c_records_history_and_returns_value(_clean_temp_sampler):
    pct = rg.sample_temperature_c(read_temp_fn=lambda: 42.5)
    assert pct == pytest.approx(42.5)
    history = rg.get_temp_history()
    assert len(history) == 1
    ts, recorded = history[0]
    assert recorded == pytest.approx(42.5)
    assert ts <= time.time()


def test_sample_temperature_c_unreadable_returns_none_and_no_history(_clean_temp_sampler):
    # None (not a fabricated "cool" value): a failed/unavailable read must
    # not be indistinguishable from a genuinely cool reading — same
    # sentinel contract as sample_cpu_percent().
    assert rg.sample_temperature_c(read_temp_fn=lambda: None) is None
    assert rg.get_temp_history() == []


def test_sample_temperature_c_raising_read_fn_returns_none_and_no_history(_clean_temp_sampler):
    def _raise():
        raise OSError("no thermal zone")

    assert rg.sample_temperature_c(read_temp_fn=_raise) is None
    assert rg.get_temp_history() == []


def test_get_temp_history_filters_by_max_age(_clean_temp_sampler):
    rg.sample_temperature_c(read_temp_fn=lambda: 50.0)
    # Backdate the one recorded sample beyond any reasonable max_age filter.
    rg._temp_history[:] = [(time.time() - 3600, v) for _, v in rg._temp_history]
    assert rg.get_temp_history(max_age_sec=60) == []
    assert len(rg.get_temp_history()) == 1  # unfiltered call still sees it


def test_reset_temp_sampler_clears_history(_clean_temp_sampler):
    rg.sample_temperature_c(read_temp_fn=lambda: 60.0)
    assert rg.get_temp_history() != []
    rg.reset_temp_sampler()
    assert rg.get_temp_history() == []


# ── should_trip_shutdown() (7.4 sub-task D) ──────────────────────────────────
# Every test builds synthetic (timestamp, value) histories directly and
# passes them via temp_history=/cpu_history= — matching this module's
# "inject everything" test convention (see can_dispatch_task()'s own tests
# above) — no real thermal/CPU state or reset-sampler fixtures needed here.

_TEMP_CRITICAL = 90  # THERMAL_CONFIG["temp_critical"], unmodified
_DURATION_SEC = 1200  # THERMAL_CONFIG["shutdown_trip_after_sec"] default
_CPU_THRESHOLD = 90  # THERMAL_CONFIG["shutdown_cpu_pct"] default


def _synthetic_history(values, interval_sec=30.0, end_ts=None):
    """Build an ascending (timestamp, value) history, `interval_sec` apart,
    ending at `end_ts` (default: now) — values[-1] is the most recent
    sample."""
    if end_ts is None:
        end_ts = time.time()
    n = len(values)
    return [(end_ts - (n - 1 - i) * interval_sec, values[i]) for i in range(n)]


def test_should_trip_shutdown_no_trip_on_short_insufficient_run():
    # All samples above threshold, but the run doesn't span the required
    # duration — a freshly-started daemon with only a few hot ticks must
    # not trivially trip this.
    history = _synthetic_history([95.0] * 10, interval_sec=30.0)  # spans 270s < 1200s
    decision = rg.should_trip_shutdown(temp_history=history, cpu_history=[])
    assert decision.should_trip is False
    assert "insufficient" in decision.reason.lower() or "spans" in decision.reason.lower()


def test_should_trip_shutdown_trips_on_genuinely_sustained_run():
    # 41 samples 30s apart spans exactly 1200s (~20 minutes at the daemon's
    # 30s tick rate) — the minimum genuinely-sustained case.
    history = _synthetic_history([95.0] * 41, interval_sec=30.0)
    decision = rg.should_trip_shutdown(temp_history=history, cpu_history=[])
    assert decision.should_trip is True
    assert "thermal" in decision.reason.lower()


def test_should_trip_shutdown_no_trip_if_most_recent_sample_has_cooled():
    # Hot for the whole window except the very latest tick — by the time
    # this is evaluated, the condition has already passed; must not still
    # read as "currently sustained."
    values = [95.0] * 40 + [50.0]
    history = _synthetic_history(values, interval_sec=30.0)
    decision = rg.should_trip_shutdown(temp_history=history, cpu_history=[])
    assert decision.should_trip is False


def test_should_trip_shutdown_single_cool_blip_does_not_reset_window():
    # One cool sample in the middle of an otherwise-sustained run must not
    # reset the whole window to zero (naive "must be unbroken" check).
    values = [95.0] * 41
    values[20] = 50.0  # one blip well inside the window, not the latest sample
    history = _synthetic_history(values, interval_sec=30.0)
    decision = rg.should_trip_shutdown(temp_history=history, cpu_history=[])
    assert decision.should_trip is True


def test_should_trip_shutdown_too_many_cool_samples_breaks_qualifying_fraction():
    # Half the window below threshold — fraction (~50%) is well under the
    # 80% qualifying floor, even though the most recent sample is hot.
    values = [95.0 if i % 2 == 0 else 50.0 for i in range(41)]
    values[-1] = 95.0  # ensure the most-recent-sample check isn't what fails this
    history = _synthetic_history(values, interval_sec=30.0)
    decision = rg.should_trip_shutdown(temp_history=history, cpu_history=[])
    assert decision.should_trip is False


def test_should_trip_shutdown_cpu_none_means_thermal_alone_suffices():
    # cpu_history=[] mirrors get_cpu_history()'s real, always-empty return
    # on this device (NEW-108: sample_cpu_percent() never appends when
    # unmeasurable) — thermal-alone must be sufficient per Ish's
    # 2026-08-10 option-3 decision.
    history = _synthetic_history([95.0] * 41, interval_sec=30.0)
    decision = rg.should_trip_shutdown(temp_history=history, cpu_history=[])
    assert decision.should_trip is True
    assert "unmeasurable" in decision.reason.lower() or "unmeasured" in decision.reason.lower()


def test_should_trip_shutdown_cpu_measurable_and_genuinely_enforced():
    # Synthetic case where CPU IS measurable (non-empty cpu_history) — the
    # AND must be genuinely enforced: thermal alone is no longer enough.
    temp_history = _synthetic_history([95.0] * 41, interval_sec=30.0)
    cpu_history_low = _synthetic_history([10.0] * 41, interval_sec=30.0)  # well under 90%
    decision = rg.should_trip_shutdown(temp_history=temp_history, cpu_history=cpu_history_low)
    assert decision.should_trip is False
    assert "cpu" in decision.reason.lower()

    cpu_history_high = _synthetic_history([95.0] * 41, interval_sec=30.0)  # sustained >90%
    decision2 = rg.should_trip_shutdown(temp_history=temp_history, cpu_history=cpu_history_high)
    assert decision2.should_trip is True
    assert "cpu" in decision2.reason.lower()


def test_should_trip_shutdown_trips_with_jittered_real_tick_spacing():
    # Regression case for a bug caught in review: an earlier implementation
    # pre-filtered history to a `duration_sec`-wide window and then required
    # THAT window's own span to be >= duration_sec — which, at a real
    # 30s-ish tick rate, made the check unsatisfiable outside an exact,
    # hand-placed synthetic boundary sample (span is bounded above by the
    # filter itself). 45 samples at a jittered 30.4s interval span ~1338s
    # (comfortably past the 1200s duration, the way real ticks with loop
    # overhead actually would) — this must still trip.
    history = _synthetic_history([95.0] * 45, interval_sec=30.4)
    decision = rg.should_trip_shutdown(temp_history=history, cpu_history=[])
    assert decision.should_trip is True


def test_should_trip_shutdown_no_trip_on_sparse_history_false_trip():
    # Regression case (code-reviewer, reproduced live): two samples 25
    # minutes apart, both above threshold, satisfy the naive span +
    # fraction-above-threshold checks (2/2 = 100% qualifying, span = 1500s
    # >= 1200s) despite reflecting almost no actual sustained observation.
    # Reachable in production via a run of failed thermal reads (each of
    # which appends nothing, per sample_temperature_c()'s sentinel
    # contract) followed by one hot sample after the gap. Must NOT trip.
    now = time.time()
    history = [(now - 1500, 95.0), (now, 95.0)]
    decision = rg.should_trip_shutdown(temp_history=history, cpu_history=[])
    assert decision.should_trip is False


def test_should_trip_shutdown_trips_at_half_density_boundary():
    # Pins MIN_QUALIFYING_DENSITY_FRACTION's own boundary: a 1200s window
    # with every-other-30s-tick read dropped (60s effective spacing, ~50%
    # of the ~40 samples a fully-populated window would have) is the
    # accepted tradeoff this constant deliberately allows through — a
    # plausible real-world case (intermittent thermal-read failures during
    # a genuinely hot period, e.g. Android doze or thermal-driver
    # contention) must still trip, not silently stop working. If this test
    # starts failing after a change to MIN_QUALIFYING_DENSITY_FRACTION,
    # that's a deliberate tradeoff to re-justify, not a regression to
    # silently "fix" by loosening the assertion. The boundary itself is
    # `density < min_density_fraction` (strict) in
    # _sustained_trailing_run() — exactly 50% density trips, it does not
    # fail; the precondition assert below pins that against the real
    # constant rather than a hardcoded 0.5 literal, so a future change to
    # MIN_QUALIFYING_DENSITY_FRACTION produces a failure that names the
    # constant instead of a mysterious sample-count mismatch.
    expected_count = 1200.0 / rg.EXPECTED_SAMPLE_INTERVAL_SEC  # 40
    assert 21 / expected_count >= rg.MIN_QUALIFYING_DENSITY_FRACTION
    history = _synthetic_history([95.0] * 21, interval_sec=60.0)  # spans 1200s, 21 samples
    decision = rg.should_trip_shutdown(temp_history=history, cpu_history=[])
    assert decision.should_trip is True


def test_should_trip_shutdown_no_trip_just_below_density_boundary():
    # Two fewer samples than the half-density case above, spanning the same
    # 1200s window — must NOT trip. Paired with the test above to pin both
    # sides of the boundary; see that test's docstring for the strict `<`
    # boundary semantics this precondition assert pins against the real
    # constant.
    expected_count = 1200.0 / rg.EXPECTED_SAMPLE_INTERVAL_SEC  # 40
    n = 19
    assert n / expected_count < rg.MIN_QUALIFYING_DENSITY_FRACTION
    now = time.time()
    history = [(now - (n - 1 - i) * (1200.0 / (n - 1)), 95.0) for i in range(n)]
    decision = rg.should_trip_shutdown(temp_history=history, cpu_history=[])
    assert decision.should_trip is False
    assert "sparse" in decision.reason.lower() or "density" in decision.reason.lower()


def test_should_trip_shutdown_no_trip_on_empty_temp_history():
    decision = rg.should_trip_shutdown(temp_history=[], cpu_history=[])
    assert decision.should_trip is False


def test_should_trip_shutdown_default_args_read_live_module_state(monkeypatch):
    # Confirm the None-default path actually reads get_temp_history()/
    # get_cpu_history() rather than only ever being exercised via explicit
    # injection in the tests above.
    history = _synthetic_history([95.0] * 41, interval_sec=30.0)
    monkeypatch.setattr(rg, "get_temp_history", lambda: list(history))
    monkeypatch.setattr(rg, "get_cpu_history", lambda: [])
    decision = rg.should_trip_shutdown()
    assert decision.should_trip is True


# ── TODO.md 7.4a sub-task A: read_zram_stats() / ResourceSnapshot fields ────


def test_read_zram_stats_parses_fixture_files(tmp_path):
    disksize = tmp_path / "disksize"
    disksize.write_text("12884901888\n")
    mm_stat = tmp_path / "mm_stat"
    # Real on-device sample shape (2026-08-11 live read, 9 whitespace-
    # separated fields): orig_data_size, compr_data_size, mem_used_total,
    # mem_limit, mem_used_max, same_pages, pages_compacted, huge_pages,
    # huge_pages_since.
    mm_stat.write_text(
        "2989174784 794678314 835547136        0 1057902592    88831   216694    23428   108007\n"
    )
    stats = rg.read_zram_stats(disksize_path=str(disksize), mm_stat_path=str(mm_stat))
    assert stats["disksize_bytes"] == 12884901888
    assert stats["orig_data_size_bytes"] == 2989174784
    assert stats["compr_data_size_bytes"] == 794678314
    assert stats["mem_used_total_bytes"] == 835547136


def test_read_zram_stats_missing_files_returns_none():
    # Non-Android host / no zram device: fail-soft (None), never raise —
    # unlike read_meminfo()'s fail-loud posture (this signal is additive/
    # optional, no existing check depends on it).
    stats = rg.read_zram_stats(
        disksize_path="/nonexistent/disksize", mm_stat_path="/nonexistent/mm_stat"
    )
    assert stats is None


def test_compute_zram_compression_ratio_none_input():
    assert rg.compute_zram_compression_ratio(None) is None


def test_compute_zram_compression_ratio_zero_compressed_bytes_is_none():
    # Idle/unused zram device: compr_data_size == 0 must not raise
    # ZeroDivisionError, and must not be misread as "infinite compression."
    stats = {"orig_data_size_bytes": 0, "compr_data_size_bytes": 0}
    assert rg.compute_zram_compression_ratio(stats) is None


def test_compute_zram_compression_ratio_computed_from_live_sample_shape():
    stats = {"orig_data_size_bytes": 2989174784, "compr_data_size_bytes": 794678314}
    ratio = rg.compute_zram_compression_ratio(stats)
    assert ratio == pytest.approx(2989174784 / 794678314)
    assert ratio == pytest.approx(3.76, abs=0.01)


def test_resource_snapshot_defaults_swap_fields_to_zero_and_none():
    # Every existing keyword-only ResourceSnapshot construction elsewhere in
    # this test module (e.g. _snapshot() below) must keep working unchanged
    # — confirms the new fields are safely defaulted.
    snap = rg.ResourceSnapshot(
        cpu_percent=10.0,
        ram_headroom_bytes=1 * GIB,
        ram_total_bytes=10 * GIB,
        temperature_c=40.0,
        queue_pending=0,
        queue_running=0,
        battery_percent=80,
        battery_charging=False,
        timestamp=time.time(),
    )
    assert snap.swap_total_bytes == 0
    assert snap.swap_free_bytes == 0
    assert snap.zram_compression_ratio is None


def test_get_resource_snapshot_composes_swap_and_zram_signals():
    mi = meminfo_bytes(
        mem_total_gib=10.8, mem_free_gib=0.25, mem_available_gib=2.2,
        swap_total_gib=12.0, swap_free_gib=1.2,
    )
    zram_stats = {"orig_data_size_bytes": 4000, "compr_data_size_bytes": 1000}
    snap = rg.get_resource_snapshot(
        meminfo=mi,
        read_temp_fn=NO_THERMAL,
        read_battery_fn=lambda: (80, False),
        state_store=_FakeStateStore(pending=0, running=0),
        cpu_percent=10.0,
        read_zram_fn=lambda: zram_stats,
    )
    assert snap.swap_total_bytes == int(12.0 * GIB)
    assert snap.swap_free_bytes == int(1.2 * GIB)
    assert snap.zram_compression_ratio == pytest.approx(4.0)


def test_get_resource_snapshot_zram_read_failure_does_not_blank_other_signals():
    mi = meminfo_bytes(mem_total_gib=10.8, mem_free_gib=0.25, mem_available_gib=2.2)

    def _raising_zram():
        raise OSError("boom")

    snap = rg.get_resource_snapshot(
        meminfo=mi,
        read_temp_fn=NO_THERMAL,
        read_battery_fn=lambda: (80, False),
        state_store=_FakeStateStore(pending=0, running=0),
        cpu_percent=10.0,
        read_zram_fn=_raising_zram,
    )
    assert snap.zram_compression_ratio is None
    assert snap.battery_percent == 80
    assert snap.cpu_percent == 10.0


def test_get_resource_snapshot_default_read_zram_fn_is_read_zram_stats(monkeypatch):
    # Confirms the None-default path actually wires up read_zram_stats(),
    # not just the injectable path exercised by every other test above.
    mi = meminfo_bytes(mem_total_gib=10.8, mem_free_gib=0.25, mem_available_gib=2.2)
    monkeypatch.setattr(rg, "read_zram_stats", lambda: None)
    snap = rg.get_resource_snapshot(
        meminfo=mi,
        read_temp_fn=NO_THERMAL,
        read_battery_fn=lambda: (80, False),
        state_store=_FakeStateStore(pending=0, running=0),
        cpu_percent=10.0,
    )
    assert snap.zram_compression_ratio is None


# ── TODO.md 7.4a sub-task B: compute_swap_assisted_headroom_bytes() ─────────


def test_compute_swap_assisted_headroom_new21_fixture_pre_registered_case():
    # Pre-registered per TODO.md 7.4a's own scoping call: NEW-21's baseline
    # (SwapTotal~12GiB, SwapFree consistent with ~1.2GiB already used, i.e.
    # SwapFree~10.8GiB), K=2.0, cap=768MiB -> min(768MiB, 10.8 - 2*1.2) =
    # min(768MiB, 8.4GiB) = 768MiB. Written BEFORE any tuning, per sub-task
    # B's own "expected value in the test first" rule.
    mi = meminfo_bytes(
        mem_total_gib=10.8, mem_free_gib=2.2, mem_available_gib=2.2,
        swap_total_gib=12.0, swap_free_gib=10.8,
    )
    result = rg.compute_swap_assisted_headroom_bytes(
        mi, max_swap_usage_bytes=768 * MIB, slmk_floor_gate_multiplier=2.0
    )
    assert result == 768 * MIB


def test_compute_swap_assisted_headroom_capped_by_gated_swap_free_not_just_cap():
    # A generous cap (larger than what the gated SwapFree actually allows)
    # must not authorize more than the gated figure — the cap and the
    # gated-SwapFree term are independently binding (min of both).
    mi = meminfo_bytes(
        mem_total_gib=10.8, mem_free_gib=2.2, mem_available_gib=2.2,
        swap_total_gib=12.0, swap_free_gib=10.8,
    )
    result = rg.compute_swap_assisted_headroom_bytes(
        mi, max_swap_usage_bytes=100 * GIB, slmk_floor_gate_multiplier=2.0
    )
    # gated = 10.8GiB - 2*1.2GiB = 8.4GiB
    assert result == pytest.approx(int(8.4 * GIB), abs=MIB)


def test_compute_swap_assisted_headroom_clamps_to_zero_near_slmk_floor():
    # SwapFree sitting right at (or below) the gated floor must clamp to 0,
    # never go negative.
    mi = meminfo_bytes(
        mem_total_gib=10.8, mem_free_gib=0.1, mem_available_gib=0.1,
        swap_total_gib=12.0, swap_free_gib=1.0,
    )
    # slmk_floor = 12.0 * 0.10 = 1.2GiB; gate = 2 * 1.2 = 2.4GiB > 1.0GiB SwapFree.
    result = rg.compute_swap_assisted_headroom_bytes(
        mi, max_swap_usage_bytes=768 * MIB, slmk_floor_gate_multiplier=2.0
    )
    assert result == 0


def test_compute_swap_assisted_headroom_zero_max_swap_usage_is_zero():
    mi = meminfo_bytes(
        mem_total_gib=10.8, mem_free_gib=2.2, mem_available_gib=2.2,
        swap_total_gib=12.0, swap_free_gib=10.8,
    )
    result = rg.compute_swap_assisted_headroom_bytes(mi, max_swap_usage_bytes=0)
    assert result == 0


def test_compute_swap_assisted_headroom_no_swap_configured_is_zero():
    mi = meminfo_bytes(mem_total_gib=10.8, mem_free_gib=2.2, mem_available_gib=2.2)
    result = rg.compute_swap_assisted_headroom_bytes(mi, max_swap_usage_bytes=768 * MIB)
    assert result == 0


def test_compute_swap_assisted_headroom_is_pure_no_side_effects():
    mi = meminfo_bytes(
        mem_total_gib=10.8, mem_free_gib=2.2, mem_available_gib=2.2,
        swap_total_gib=12.0, swap_free_gib=10.8,
    )
    mi_copy = dict(mi)
    rg.compute_swap_assisted_headroom_bytes(mi, max_swap_usage_bytes=768 * MIB)
    assert mi == mi_copy


def test_compute_swap_assisted_headroom_now_wired_into_can_admit():
    # Superseded by sub-task C2: at sub-task B's own point in this project's
    # history, can_admit() did not reference swap at all — this test used to
    # pin that. C2 wires compute_swap_assisted_headroom_bytes() in as a
    # genuine secondary check (see tests below for the full behavioral
    # coverage), so the source now DOES reference it; this positive
    # assertion replaces the old negative one rather than silently deleting
    # it.
    import inspect

    src = inspect.getsource(rg.can_admit)
    assert "compute_swap_assisted_headroom_bytes" in src


# ── TODO.md 7.4a sub-task C1: MAX_CONCURRENT_MODEL_BUDGET_BYTES ─────────────

# Real, exact bytes from TODO.md 7.4a's own derivation — used directly
# (not re-derived here) so these tests pin the actual documented numbers.
_SEVENB_COST_BYTES = 6_830_557_184
_ONE_POINT_FIVEB_COST_BYTES = 2_325_280_320
_EMBED_COST_BYTES = 352_563_303


def test_max_concurrent_model_budget_bytes_value():
    assert rg.MAX_CONCURRENT_MODEL_BUDGET_BYTES == 9_556_302_233


def test_three_model_concurrent_case_is_admissible_new133_regression(tmp_path):
    # NEW-133's exact regression case: the full 3-model-concurrent scenario
    # this ceiling was derived from must itself be ADMISSIBLE, not refused
    # by a rounding error (the failure mode the 8.80GiB->8.90GiB correction
    # fixed). Two slots pre-registered (7B + 1.5B), candidate is the embed
    # model — sum of all three equals the raw 9,508,400,807-byte sum, well
    # under the 9,556,302,233-byte ceiling.
    rg.register_slot("primary", cost_bytes=_SEVENB_COST_BYTES, state_dir=tmp_path, status=rg.SLOT_STATUS_RESIDENT)
    rg.register_slot("planner", cost_bytes=_ONE_POINT_FIVEB_COST_BYTES, state_dir=tmp_path, status=rg.SLOT_STATUS_RESIDENT)

    embed_spec = rg.ModelSpec(model_id="embed", size_bytes=_EMBED_COST_BYTES, n_ctx=2048, compute_overhead_bytes=0)
    mi = meminfo_bytes(mem_total_gib=10.8, mem_free_gib=5.0, mem_available_gib=5.0)
    decision, slot_id = rg.reserve_slot(embed_spec, meminfo=mi, read_temp_fn=NO_THERMAL, state_dir=tmp_path)
    assert decision.admitted is True
    assert decision.budget_ceiling_exceeded is False
    assert slot_id is not None


def test_can_admit_denies_over_ceiling_with_retryable_not_hard_reject():
    spec = rg.ModelSpec(model_id="x", size_bytes=1 * GIB, n_ctx=1024, compute_overhead_bytes=0)
    mi = meminfo_bytes(mem_total_gib=10.8, mem_free_gib=8.0, mem_available_gib=8.0)
    already_committed = rg.MAX_CONCURRENT_MODEL_BUDGET_BYTES - int(0.5 * GIB)
    decision = rg.can_admit(
        spec, meminfo=mi, read_temp_fn=NO_THERMAL, concurrent_committed_bytes=already_committed
    )
    assert decision.admitted is False
    assert decision.hard_reject is False
    assert decision.budget_ceiling_exceeded is True
    assert "budget" in decision.reason.lower()


def test_can_admit_exactly_at_ceiling_admits():
    # Boundary: committed + cost == ceiling exactly must ADMIT (the check is
    # a strict `>`, not `>=`).
    spec = rg.ModelSpec(model_id="x", size_bytes=1 * GIB, n_ctx=1024, compute_overhead_bytes=0)
    mi = meminfo_bytes(mem_total_gib=10.8, mem_free_gib=8.0, mem_available_gib=8.0)
    already_committed = rg.MAX_CONCURRENT_MODEL_BUDGET_BYTES - int(1 * GIB)
    decision = rg.can_admit(
        spec, meminfo=mi, read_temp_fn=NO_THERMAL, concurrent_committed_bytes=already_committed
    )
    assert decision.admitted is True
    assert decision.budget_ceiling_exceeded is False


def test_can_admit_one_byte_over_ceiling_denies():
    spec = rg.ModelSpec(model_id="x", size_bytes=1 * GIB, n_ctx=1024, compute_overhead_bytes=0)
    mi = meminfo_bytes(mem_total_gib=10.8, mem_free_gib=8.0, mem_available_gib=8.0)
    already_committed = rg.MAX_CONCURRENT_MODEL_BUDGET_BYTES - int(1 * GIB) + 1
    decision = rg.can_admit(
        spec, meminfo=mi, read_temp_fn=NO_THERMAL, concurrent_committed_bytes=already_committed
    )
    assert decision.admitted is False
    assert decision.budget_ceiling_exceeded is True


def test_can_admit_budget_ceiling_checked_before_headroom_and_thermal():
    # A load that would ALSO fail the headroom check (tiny MemAvailable)
    # must still report the budget-ceiling reason, not the headroom reason,
    # confirming the new check runs before the pre-existing ones (per
    # TODO.md 7.4a's explicit scoped ordering).
    spec = rg.ModelSpec(model_id="x", size_bytes=1 * GIB, n_ctx=1024, compute_overhead_bytes=0)
    mi = meminfo_bytes(mem_total_gib=10.8, mem_free_gib=0.01, mem_available_gib=0.01)
    already_committed = rg.MAX_CONCURRENT_MODEL_BUDGET_BYTES
    decision = rg.can_admit(
        spec, meminfo=mi, read_temp_fn=NO_THERMAL, concurrent_committed_bytes=already_committed
    )
    assert decision.admitted is False
    assert decision.budget_ceiling_exceeded is True
    assert "budget" in decision.reason.lower()


def test_can_admit_hard_reject_still_takes_priority_over_budget_ceiling():
    # A model whose own cost alone exceeds the device ceiling must still
    # report hard_reject=True (unaffected by this new check, which is only
    # evaluated once hard_reject has already been ruled out).
    spec = rg.ModelSpec(model_id="huge", size_bytes=50 * GIB, n_ctx=4096)
    mi = meminfo_bytes(mem_total_gib=10.8, mem_free_gib=8.0, mem_available_gib=8.0)
    decision = rg.can_admit(spec, meminfo=mi, read_temp_fn=NO_THERMAL, concurrent_committed_bytes=0)
    assert decision.admitted is False
    assert decision.hard_reject is True
    assert decision.budget_ceiling_exceeded is False


def test_can_admit_default_concurrent_committed_bytes_is_zero_unaffected():
    # Every unmodified call site (not passing concurrent_committed_bytes at
    # all) must be byte-for-byte unaffected — a real budget of 0 never
    # trips this check.
    spec = rg.ModelSpec(model_id="x", size_bytes=1 * GIB, n_ctx=1024, compute_overhead_bytes=0)
    mi = meminfo_bytes(mem_total_gib=10.8, mem_free_gib=8.0, mem_available_gib=8.0)
    decision = rg.can_admit(spec, meminfo=mi, read_temp_fn=NO_THERMAL)
    assert decision.admitted is True
    assert decision.budget_ceiling_exceeded is False


def test_sum_committed_bytes_includes_pending_and_resident():
    slots = [
        {"cost_bytes": 1 * GIB, "status": rg.SLOT_STATUS_PENDING},
        {"cost_bytes": 2 * GIB, "status": rg.SLOT_STATUS_RESIDENT},
        {"cost_bytes": 3 * GIB},  # missing status entirely — still counted
    ]
    assert rg._sum_committed_bytes(slots) == 6 * GIB


def test_total_committed_bytes_includes_both_pending_and_resident(tmp_path):
    pending_id = rg.register_slot("pending-model", cost_bytes=2 * GIB, state_dir=tmp_path)
    resident_id = rg.register_slot("resident-model", cost_bytes=3 * GIB, state_dir=tmp_path)
    rg.mark_resident(resident_id, state_dir=tmp_path)

    # Deliberately the OPPOSITE of total_reserved_bytes()'s PENDING-only
    # result for the same two slots (see
    # test_total_reserved_bytes_excludes_resident_slots above): this sums
    # both.
    assert rg.total_committed_bytes(state_dir=tmp_path) == 5 * GIB
    assert rg.total_reserved_bytes(state_dir=tmp_path) == 2 * GIB

    rg.release_slot(pending_id, state_dir=tmp_path)
    rg.release_slot(resident_id, state_dir=tmp_path)


def test_reserve_slot_uses_real_committed_sum_from_state_store_two_prior_slots(tmp_path):
    # Exercises the locking-correctness claim in reserve_slot()'s own
    # docstring: two slots already registered (one PENDING, one RESIDENT)
    # directly through reserve_slot()/register_slot(), then a third
    # reserve_slot() call that should be denied purely because the
    # cumulative sum (computed INSIDE reserve_slot()'s own lock, not a
    # hand-fed can_admit() parameter) now exceeds the ceiling.
    slot_a_cost = rg.MAX_CONCURRENT_MODEL_BUDGET_BYTES - int(1.5 * GIB)
    slot_b_cost = int(1 * GIB)
    rg.register_slot("a", cost_bytes=slot_a_cost, state_dir=tmp_path, status=rg.SLOT_STATUS_RESIDENT)
    rg.register_slot("b", cost_bytes=slot_b_cost, state_dir=tmp_path, status=rg.SLOT_STATUS_PENDING)
    # Committed so far: ceiling - 0.5GiB. A candidate costing 1GiB pushes
    # the sum 0.5GiB over the ceiling.
    candidate = rg.ModelSpec(model_id="c", size_bytes=1 * GIB, n_ctx=1024, compute_overhead_bytes=0)
    mi = meminfo_bytes(mem_total_gib=10.8, mem_free_gib=8.0, mem_available_gib=8.0)
    decision, slot_id = rg.reserve_slot(candidate, meminfo=mi, read_temp_fn=NO_THERMAL, state_dir=tmp_path)
    assert decision.admitted is False
    assert decision.budget_ceiling_exceeded is True
    assert slot_id is None
    assert rg.list_slots(state_dir=tmp_path) == [
        s for s in rg.list_slots(state_dir=tmp_path) if s["model_id"] in ("a", "b")
    ]


def test_reserve_slot_admits_when_committed_sum_stays_under_ceiling(tmp_path):
    slot_a_cost = rg.MAX_CONCURRENT_MODEL_BUDGET_BYTES - int(2 * GIB)
    rg.register_slot("a", cost_bytes=slot_a_cost, state_dir=tmp_path, status=rg.SLOT_STATUS_RESIDENT)
    candidate = rg.ModelSpec(model_id="c", size_bytes=1 * GIB, n_ctx=1024, compute_overhead_bytes=0)
    mi = meminfo_bytes(mem_total_gib=10.8, mem_free_gib=8.0, mem_available_gib=8.0)
    decision, slot_id = rg.reserve_slot(candidate, meminfo=mi, read_temp_fn=NO_THERMAL, state_dir=tmp_path)
    assert decision.admitted is True
    assert decision.budget_ceiling_exceeded is False
    assert slot_id is not None


# ── TODO.md 7.4a sub-task C2: swap-assisted secondary check wired into
#    can_admit() ───────────────────────────────────────────────────────────
#
# All fixtures here use headroom_factor=1.0 (rather than the module default
# 1.25) so `required` equals `cost.total_bytes` exactly and every boundary
# below can be pinned to exact byte counts — matching sub-task C1's own
# `== admits` / `+1 denies` boundary-test pattern (see
# test_can_admit_exactly_at_ceiling_admits / _one_byte_over_ceiling_denies
# above), applied here to the RAM+swap combined figure instead of the
# budget ceiling.


def test_max_swap_assist_bytes_value():
    # TODO.md 7.4a sub-task F (2026-08-11 recalibration): can_admit()'s own
    # cap was raised to 10GiB; see DISPATCH_MAX_SWAP_ASSIST_BYTES below for
    # the deliberately-unchanged, decoupled can_dispatch_task() cap.
    assert rg.MAX_SWAP_ASSIST_BYTES == 10_737_418_240


def test_dispatch_max_swap_assist_bytes_value():
    # TODO.md 7.4a sub-task F: can_dispatch_task()'s own cap stays at the
    # original 768MiB value, deliberately decoupled from the can_admit()-
    # only 10GiB raise above.
    assert rg.DISPATCH_MAX_SWAP_ASSIST_BYTES == 805_306_368


# Realistic fixture for the exact-byte boundary tests below: SwapTotal=12GiB,
# SwapFree=5GiB, mem_available=1GiB. Deliberately NOT a `SwapTotal: 0` /
# `SwapFree: 5GiB` fixture (that combination is a physically impossible
# memory state — SwapFree can never exceed SwapTotal on any real device) —
# with the default `SLMK_FLOOR_GATE_MULTIPLIER=2.0`,
# `slmk_floor_bytes = 12.0 * 0.10 = 1.2GiB`, `gated = 5.0 - 2*1.2 = 2.6GiB`,
# so `min(500MiB, 2.6GiB) = 500MiB` exactly — the same exact-byte arithmetic
# the isolated-arithmetic version would have given, on a realistic fixture.
_BOUNDARY_MEMINFO = meminfo_bytes(
    mem_total_gib=10.0, mem_free_gib=1.0, mem_available_gib=1.0,
    swap_total_gib=12.0, swap_free_gib=5.0,
)


def test_swap_assist_admits_when_ram_alone_would_deny():
    # NEW-21-shaped fixture (real numbers, not the isolated-arithmetic
    # fixture above): baseline 2.2GiB MemAvailable, ~10.8GiB SwapFree.
    # required=2.5GiB > headroom=2.2GiB (RAM alone denies), but
    # combined = 2.2GiB + min(10GiB, 8.4GiB gated SwapFree) (the default
    # MAX_SWAP_ASSIST_BYTES cap as of TODO.md 7.4a sub-task F's 2026-08-11
    # recalibration; the 8.4GiB gated SwapFree term binds here, not the
    # 10GiB cap itself) = 10.6GiB >= 2.5GiB.
    spec = rg.ModelSpec(model_id="x", size_bytes=2 * GIB, n_ctx=1024, compute_overhead_bytes=0)
    mi = meminfo_bytes(
        mem_total_gib=10.8, mem_free_gib=2.2, mem_available_gib=2.2,
        swap_total_gib=12.0, swap_free_gib=10.8,
    )
    ram_only = rg.can_admit(spec, meminfo=mi, read_temp_fn=NO_THERMAL, enable_swap_assist=False)
    assert ram_only.admitted is False
    assert ram_only.admitted_via_swap is False

    decision = rg.can_admit(spec, meminfo=mi, read_temp_fn=NO_THERMAL)
    assert decision.admitted is True
    assert decision.admitted_via_swap is True
    assert decision.hard_reject is False
    assert decision.budget_ceiling_exceeded is False
    assert "swap" in decision.reason.lower()


def test_swap_assist_exact_combined_headroom_boundary_admits():
    # combined = 1GiB (RAM, headroom_factor=1.0) + 500MiB (explicit cap,
    # well under the 2.6GiB gated SwapFree this fixture allows — see
    # _BOUNDARY_MEMINFO's own comment).
    required_target = 1 * GIB + 500 * MIB
    spec = rg.ModelSpec(
        model_id="x", size_bytes=required_target, n_ctx=1024, compute_overhead_bytes=0
    )
    decision = rg.can_admit(
        spec, meminfo=_BOUNDARY_MEMINFO, read_temp_fn=NO_THERMAL, headroom_factor=1.0,
        max_swap_usage_bytes=500 * MIB,
    )
    assert decision.admitted is True
    assert decision.admitted_via_swap is True


def test_swap_assist_one_byte_over_combined_headroom_boundary_denies():
    required_target = 1 * GIB + 500 * MIB + 1
    spec = rg.ModelSpec(
        model_id="x", size_bytes=required_target, n_ctx=1024, compute_overhead_bytes=0
    )
    decision = rg.can_admit(
        spec, meminfo=_BOUNDARY_MEMINFO, read_temp_fn=NO_THERMAL, headroom_factor=1.0,
        max_swap_usage_bytes=500 * MIB,
    )
    assert decision.admitted is False
    assert decision.admitted_via_swap is False
    assert decision.hard_reject is False
    assert decision.budget_ceiling_exceeded is False


def test_swap_assist_disabled_via_parameter_keeps_ram_only_denial():
    spec = rg.ModelSpec(model_id="x", size_bytes=2 * GIB, n_ctx=1024, compute_overhead_bytes=0)
    mi = meminfo_bytes(
        mem_total_gib=10.8, mem_free_gib=2.2, mem_available_gib=2.2,
        swap_total_gib=12.0, swap_free_gib=10.8,
    )
    decision = rg.can_admit(spec, meminfo=mi, read_temp_fn=NO_THERMAL, enable_swap_assist=False)
    assert decision.admitted is False
    assert decision.admitted_via_swap is False


def test_swap_assist_disabled_via_env_var_keeps_ram_only_denial(monkeypatch):
    monkeypatch.setenv(rg.CODEY_SWAP_ASSIST_ADMISSION_ENV, "0")
    spec = rg.ModelSpec(model_id="x", size_bytes=2 * GIB, n_ctx=1024, compute_overhead_bytes=0)
    mi = meminfo_bytes(
        mem_total_gib=10.8, mem_free_gib=2.2, mem_available_gib=2.2,
        swap_total_gib=12.0, swap_free_gib=10.8,
    )
    decision = rg.can_admit(spec, meminfo=mi, read_temp_fn=NO_THERMAL)
    assert decision.admitted is False
    assert decision.admitted_via_swap is False


def test_swap_assist_env_var_unset_matches_default_enabled(monkeypatch):
    monkeypatch.delenv(rg.CODEY_SWAP_ASSIST_ADMISSION_ENV, raising=False)
    assert rg._resolve_swap_assist_enabled_default() is True


def test_swap_assist_env_var_explicit_one_enables(monkeypatch):
    monkeypatch.setenv(rg.CODEY_SWAP_ASSIST_ADMISSION_ENV, "1")
    assert rg._resolve_swap_assist_enabled_default() is True


def test_swap_assist_env_var_invalid_value_raises_loudly(monkeypatch):
    # Deliberately NOT a bare truthiness check (`!= "0"`) — see
    # CODEY_SWAP_ASSIST_ADMISSION_ENV's own comment for why a value like
    # "false"/"off"/"no" must fail loudly rather than being silently
    # (and wrong-directionally) treated as enabled.
    monkeypatch.setenv(rg.CODEY_SWAP_ASSIST_ADMISSION_ENV, "false")
    with pytest.raises(ValueError):
        rg._resolve_swap_assist_enabled_default()


def test_swap_assist_never_overrides_budget_ceiling_denial():
    # Hard invariant (TODO.md 7.4a, must not be relaxed): swap-assisted
    # admission may only ever override the plain-RAM headroom denial, never
    # C1's cumulative-budget denial. Tiny MemAvailable AND generous SwapFree
    # (would easily cover `required` via swap alone) AND
    # concurrent_committed_bytes already at the ceiling — must stay denied
    # via budget_ceiling_exceeded, not flip to admitted_via_swap.
    spec = rg.ModelSpec(model_id="x", size_bytes=1 * GIB, n_ctx=1024, compute_overhead_bytes=0)
    mi = meminfo_bytes(
        mem_total_gib=10.8, mem_free_gib=0.01, mem_available_gib=0.01,
        swap_total_gib=12.0, swap_free_gib=10.8,
    )
    decision = rg.can_admit(
        spec, meminfo=mi, read_temp_fn=NO_THERMAL,
        concurrent_committed_bytes=rg.MAX_CONCURRENT_MODEL_BUDGET_BYTES,
    )
    assert decision.admitted is False
    assert decision.budget_ceiling_exceeded is True
    assert decision.admitted_via_swap is False


def test_swap_assist_never_overrides_budget_ceiling_denial_via_reserve_slot(tmp_path):
    # Same invariant, exercised through the real reserve_slot()/
    # _sum_committed_bytes() path (not a hand-fed concurrent_committed_bytes
    # parameter) — two RESIDENT slots whose real declared-cost sum already
    # exceeds MAX_CONCURRENT_MODEL_BUDGET_BYTES, tiny MemAvailable, generous
    # SwapFree. Must still deny via budget_ceiling_exceeded.
    slot_a_cost = rg.MAX_CONCURRENT_MODEL_BUDGET_BYTES // 2 + 1 * GIB
    slot_b_cost = rg.MAX_CONCURRENT_MODEL_BUDGET_BYTES // 2 + 1 * GIB
    rg.register_slot("a", cost_bytes=slot_a_cost, state_dir=tmp_path, status=rg.SLOT_STATUS_RESIDENT)
    rg.register_slot("b", cost_bytes=slot_b_cost, state_dir=tmp_path, status=rg.SLOT_STATUS_RESIDENT)

    candidate = rg.ModelSpec(model_id="c", size_bytes=1 * GIB, n_ctx=1024, compute_overhead_bytes=0)
    mi = meminfo_bytes(
        mem_total_gib=10.8, mem_free_gib=0.01, mem_available_gib=0.01,
        swap_total_gib=12.0, swap_free_gib=10.8,
    )
    decision, slot_id = rg.reserve_slot(candidate, meminfo=mi, read_temp_fn=NO_THERMAL, state_dir=tmp_path)
    assert decision.admitted is False
    assert decision.budget_ceiling_exceeded is True
    assert decision.admitted_via_swap is False
    assert slot_id is None


def test_swap_assist_ram_only_pass_is_byte_for_byte_unchanged(monkeypatch):
    # A load that already passes on MemAvailable alone must be completely
    # unaffected by SwapFree or enable_swap_assist — every GateDecision
    # field identical across all combinations below, INCLUDING the real
    # production call shape (enable_swap_assist left unset -> resolved from
    # CODEY_SWAP_ASSIST_ADMISSION, exactly how reserve_slot() calls
    # can_admit() today).
    monkeypatch.delenv(rg.CODEY_SWAP_ASSIST_ADMISSION_ENV, raising=False)
    spec = rg.ModelSpec(model_id="x", size_bytes=1 * GIB, n_ctx=1024, compute_overhead_bytes=0)
    decisions = []
    for swap_free_gib in (0.0, 10.8):
        for enable_swap_assist in (True, False, None):
            mi = meminfo_bytes(
                mem_total_gib=10.8, mem_free_gib=8.0, mem_available_gib=8.0,
                swap_total_gib=12.0, swap_free_gib=swap_free_gib,
            )
            kwargs = {} if enable_swap_assist is None else {"enable_swap_assist": enable_swap_assist}
            decisions.append(rg.can_admit(spec, meminfo=mi, read_temp_fn=NO_THERMAL, **kwargs))
    first = decisions[0]
    assert first.admitted is True
    assert first.admitted_via_swap is False
    for other in decisions[1:]:
        assert other == first


def test_would_model_fit_does_not_use_swap_assist():
    # TODO.md 7.4a sub-task C's own pre-declared default: swap-assisted
    # admission must NOT count for would_model_fit()'s routing use unless a
    # caller explicitly opts in (no opt-in mechanism exists yet — that's
    # sub-task D). A load only admissible via swap assist must still report
    # False here, even though the equivalent can_admit() call admits it.
    spec = rg.ModelSpec(model_id="x", size_bytes=2 * GIB, n_ctx=1024, compute_overhead_bytes=0)
    mi = meminfo_bytes(
        mem_total_gib=10.8, mem_free_gib=2.2, mem_available_gib=2.2,
        swap_total_gib=12.0, swap_free_gib=10.8,
    )
    assert rg.can_admit(spec, meminfo=mi, read_temp_fn=NO_THERMAL).admitted is True
    assert rg.would_model_fit(spec, meminfo=mi, read_temp_fn=NO_THERMAL) is False


def test_reserve_slot_bad_swap_assist_env_var_raises_and_registers_nothing(monkeypatch, tmp_path):
    # Mirrors test_reserve_slot_bad_test_arch_override_raises_and_registers_nothing
    # above: the ValueError from a bad CODEY_SWAP_ASSIST_ADMISSION value is
    # raised from inside can_admit(), which reserve_slot() calls WHILE
    # holding _LockedState's flock. Confirms the exception still propagates
    # cleanly out of reserve_slot() with no slot registered and no leaked/
    # held lock. Requires a load that would otherwise hit the swap-assist
    # branch at all (RAM alone denying) — a load that already passes on RAM
    # never evaluates enable_swap_assist/the env var, so never reaches this
    # raise (see the byte-for-byte test above).
    monkeypatch.setenv(rg.CODEY_SWAP_ASSIST_ADMISSION_ENV, "false")
    spec = rg.ModelSpec(model_id="x", size_bytes=2 * GIB, n_ctx=1024, compute_overhead_bytes=0)
    mi = meminfo_bytes(
        mem_total_gib=10.8, mem_free_gib=2.2, mem_available_gib=2.2,
        swap_total_gib=12.0, swap_free_gib=10.8,
    )
    with pytest.raises(ValueError):
        rg.reserve_slot(spec, meminfo=mi, read_temp_fn=NO_THERMAL, state_dir=tmp_path)
    assert rg.list_slots(state_dir=tmp_path) == []
    # Lock released cleanly despite the exception: a second, unrelated call
    # against the same state_dir must not hang/deadlock on a stuck flock.
    monkeypatch.delenv(rg.CODEY_SWAP_ASSIST_ADMISSION_ENV, raising=False)
    ok_spec = rg.ModelSpec(model_id="ok", size_bytes=int(0.1 * GIB), n_ctx=1024, compute_overhead_bytes=0)
    decision, slot_id = rg.reserve_slot(ok_spec, meminfo=mi, read_temp_fn=NO_THERMAL, state_dir=tmp_path)
    assert decision.admitted is True
    assert slot_id is not None


# ── TODO.md 7.4a sub-task D1: would_model_fit_decision() ────────────────────


def test_would_model_fit_still_returns_a_bare_bool():
    # Non-breaking guarantee: would_model_fit() itself must still return a
    # plain bool (not a GateDecision, which is always truthy) — a
    # GateDecision return here would silently turn any existing/future
    # `if would_model_fit(...):` check into an always-True bug.
    spec = rg.ModelSpec(model_id="ok", size_bytes=int(0.5 * GIB), n_ctx=2048)
    mi = meminfo_bytes(mem_total_gib=10.8, mem_free_gib=5.0, mem_available_gib=7.0)
    result = rg.would_model_fit(spec, meminfo=mi, read_temp_fn=NO_THERMAL)
    assert result is True
    assert type(result) is bool


def test_would_model_fit_decision_returns_full_gate_decision():
    spec = rg.ModelSpec(model_id="ok", size_bytes=int(0.5 * GIB), n_ctx=2048)
    mi = meminfo_bytes(mem_total_gib=10.8, mem_free_gib=5.0, mem_available_gib=7.0)
    decision = rg.would_model_fit_decision(spec, meminfo=mi, read_temp_fn=NO_THERMAL)
    assert isinstance(decision, rg.GateDecision)
    assert decision.admitted is True
    assert decision.hard_reject is False
    assert decision.budget_ceiling_exceeded is False
    assert decision.admitted_via_swap is False


def test_would_model_fit_decision_distinguishes_hard_reject_from_headroom_no():
    # A candidate whose own cost alone exceeds the device ceiling must
    # report hard_reject=True — a router should treat this candidate as
    # unsuitable full stop, never retryable.
    huge = rg.ModelSpec(model_id="huge", size_bytes=50 * GIB, n_ctx=4096)
    mi = meminfo_bytes(mem_total_gib=10.8, mem_free_gib=5.0, mem_available_gib=7.0)
    decision = rg.would_model_fit_decision(huge, meminfo=mi, read_temp_fn=NO_THERMAL)
    assert decision.admitted is False
    assert decision.hard_reject is True
    assert decision.budget_ceiling_exceeded is False

    # A candidate refused purely on live RAM headroom (not the ceiling) must
    # report hard_reject=False — this is the RECOVERABLE-by-waiting case a
    # router might reasonably retry later, distinct from the case above.
    modest = rg.ModelSpec(model_id="modest", size_bytes=int(2 * GIB), n_ctx=1024, compute_overhead_bytes=0)
    tight_mi = meminfo_bytes(mem_total_gib=10.8, mem_free_gib=0.5, mem_available_gib=0.5)
    tight_decision = rg.would_model_fit_decision(modest, meminfo=tight_mi, read_temp_fn=NO_THERMAL)
    assert tight_decision.admitted is False
    assert tight_decision.hard_reject is False
    assert tight_decision.budget_ceiling_exceeded is False


def test_would_model_fit_decision_distinguishes_budget_ceiling_no_from_headroom_no():
    # A "no" caused specifically by C1's fixed cumulative-model budget
    # (recoverable by releasing another resident model) must be
    # distinguishable from a "no" caused by live RAM headroom alone.
    spec = rg.ModelSpec(model_id="c", size_bytes=1 * GIB, n_ctx=1024, compute_overhead_bytes=0)
    mi = meminfo_bytes(mem_total_gib=10.8, mem_free_gib=8.0, mem_available_gib=8.0)
    decision = rg.would_model_fit_decision(
        spec, meminfo=mi, read_temp_fn=NO_THERMAL,
        concurrent_committed_bytes=rg.MAX_CONCURRENT_MODEL_BUDGET_BYTES,
    )
    assert decision.admitted is False
    assert decision.hard_reject is False
    assert decision.budget_ceiling_exceeded is True


def test_would_model_fit_decision_default_concurrent_committed_bytes_unaffected():
    # Unmodified call sites (concurrent_committed_bytes left at its default
    # of 0) must be byte-for-byte unaffected by C1's check, same convention
    # as can_admit()'s own default.
    spec = rg.ModelSpec(model_id="c", size_bytes=1 * GIB, n_ctx=1024, compute_overhead_bytes=0)
    mi = meminfo_bytes(mem_total_gib=10.8, mem_free_gib=8.0, mem_available_gib=8.0)
    decision = rg.would_model_fit_decision(spec, meminfo=mi, read_temp_fn=NO_THERMAL)
    assert decision.admitted is True
    assert decision.budget_ceiling_exceeded is False


def test_would_model_fit_decision_swap_assisted_yes_distinguishable_from_ram_comfortable_yes():
    # A "yes" reached only via swap assist (allow_swap_assist=True, opt-in)
    # must be distinguishable from a RAM-comfortable "yes" via
    # admitted_via_swap — the whole point of D1's return-shape work.
    spec = rg.ModelSpec(model_id="x", size_bytes=2 * GIB, n_ctx=1024, compute_overhead_bytes=0)
    mi = meminfo_bytes(
        mem_total_gib=10.8, mem_free_gib=2.2, mem_available_gib=2.2,
        swap_total_gib=12.0, swap_free_gib=10.8,
    )
    # Default (allow_swap_assist=False, unchanged pre-D1 behavior): refused.
    default_decision = rg.would_model_fit_decision(spec, meminfo=mi, read_temp_fn=NO_THERMAL)
    assert default_decision.admitted is False
    assert default_decision.admitted_via_swap is False

    # Explicit opt-in: admitted, and distinguishably via swap.
    opted_in = rg.would_model_fit_decision(
        spec, meminfo=mi, read_temp_fn=NO_THERMAL, allow_swap_assist=True
    )
    assert opted_in.admitted is True
    assert opted_in.admitted_via_swap is True

    # A RAM-comfortable "yes" (no swap needed at all) stays admitted_via_swap
    # False even with allow_swap_assist=True — the swap branch is only
    # reached when RAM alone would already refuse.
    comfy_mi = meminfo_bytes(mem_total_gib=10.8, mem_free_gib=8.0, mem_available_gib=8.0)
    comfy = rg.would_model_fit_decision(
        spec, meminfo=comfy_mi, read_temp_fn=NO_THERMAL, allow_swap_assist=True
    )
    assert comfy.admitted is True
    assert comfy.admitted_via_swap is False


def test_would_model_fit_default_still_matches_pre_d1_behavior():
    # would_model_fit()'s own bool return, with no new params supplied, must
    # match its pre-D1 behavior exactly: swap-assisted admission does not
    # count as "fits" by default.
    spec = rg.ModelSpec(model_id="x", size_bytes=2 * GIB, n_ctx=1024, compute_overhead_bytes=0)
    mi = meminfo_bytes(
        mem_total_gib=10.8, mem_free_gib=2.2, mem_available_gib=2.2,
        swap_total_gib=12.0, swap_free_gib=10.8,
    )
    assert rg.can_admit(spec, meminfo=mi, read_temp_fn=NO_THERMAL).admitted is True
    assert rg.would_model_fit(spec, meminfo=mi, read_temp_fn=NO_THERMAL) is False
    # Opting in via the new parameter flips it, proving the parameter is
    # actually wired through (not just would_model_fit_decision()).
    assert rg.would_model_fit(
        spec, meminfo=mi, read_temp_fn=NO_THERMAL, allow_swap_assist=True
    ) is True


# ── TODO.md 7.4a sub-task D2: can_dispatch_task()'s swap-aware dispatch
#    floor ───────────────────────────────────────────────────────────────────
#
# Mirrors sub-task C2's own invariant-testing rigor: swap-assist must be able
# to cover the RAM-headroom gap, must never be able to bypass any
# higher-priority refusal (interactive/thermal/battery), must respect the
# same on/off-switch and cap as can_admit()'s own swap-assist branch, and a
# snapshot that already passes on RAM alone must be byte-for-byte unaffected.


def _swap_snapshot(
    ram_headroom_bytes,
    swap_total_bytes=12 * GIB,
    swap_free_bytes=10 * GIB,
    temperature_c=40.0,
    battery_percent=80,
    battery_charging=False,
    cpu_percent=10.0,
):
    return rg.ResourceSnapshot(
        cpu_percent=cpu_percent,
        ram_headroom_bytes=ram_headroom_bytes,
        ram_total_bytes=12 * GIB,
        temperature_c=temperature_c,
        queue_pending=0,
        queue_running=0,
        battery_percent=battery_percent,
        battery_charging=battery_charging,
        timestamp=time.time(),
        swap_total_bytes=swap_total_bytes,
        swap_free_bytes=swap_free_bytes,
    )


def test_can_dispatch_task_swap_assist_admits_when_ram_alone_would_refuse():
    # RAM headroom just under the 1GiB floor; generous SwapFree comfortably
    # covers the gap via the default DISPATCH_MAX_SWAP_ASSIST_BYTES cap
    # (768MiB — can_dispatch_task()'s own, decoupled from can_admit()'s
    # MAX_SWAP_ASSIST_BYTES per TODO.md 7.4a sub-task F).
    snap = _swap_snapshot(ram_headroom_bytes=rg.DISPATCH_MIN_HEADROOM_BYTES - MIB)
    ram_only = rg.can_dispatch_task(snap, interactive_active=False, enable_swap_assist=False)
    assert ram_only.allowed is False
    assert ram_only.dispatched_via_swap is False

    decision = rg.can_dispatch_task(snap, interactive_active=False)
    assert decision.allowed is True
    assert decision.dispatched_via_swap is True
    assert "swap" in decision.reason.lower()


def test_can_dispatch_task_swap_assist_capped_still_refuses_when_gap_too_large():
    # Proves swap-assist can't buy arbitrary headroom: RAM headroom 2GiB
    # below the floor, but DISPATCH_MAX_SWAP_ASSIST_BYTES (768MiB default,
    # unchanged by TODO.md 7.4a sub-task F) can't cover a gap that large
    # even with enormous SwapFree available.
    snap = _swap_snapshot(
        ram_headroom_bytes=rg.DISPATCH_MIN_HEADROOM_BYTES - 2 * GIB,
        swap_total_bytes=100 * GIB,
        swap_free_bytes=90 * GIB,
    )
    decision = rg.can_dispatch_task(snap, interactive_active=False)
    assert decision.allowed is False
    assert decision.dispatched_via_swap is False


def test_can_dispatch_task_swap_assist_gated_near_slmk_floor_still_refuses():
    # SwapFree at/below the slmk-gated floor (2 x 10% of SwapTotal) means
    # compute_swap_assisted_headroom_bytes() authorizes 0 bytes — dispatch
    # must stay refused even though SwapTotal itself is large. Asserted
    # directly against the underlying mechanism (not just the decision) so
    # this test can't pass "by accident" on a tiny nonzero swap_headroom
    # that happens to still be smaller than the RAM gap.
    swap_total = 12 * GIB
    slmk_floor_bytes = swap_total * rg.SLMK_SWAP_FREE_LOW_FRACTION

    for swap_free_bytes in (int(2 * slmk_floor_bytes), int(slmk_floor_bytes)):
        snap = _swap_snapshot(
            ram_headroom_bytes=rg.DISPATCH_MIN_HEADROOM_BYTES - MIB,
            swap_total_bytes=swap_total,
            swap_free_bytes=swap_free_bytes,
        )
        assert (
            rg.compute_swap_assisted_headroom_bytes(
                {"SwapFree": snap.swap_free_bytes, "SwapTotal": snap.swap_total_bytes},
                rg.DISPATCH_MAX_SWAP_ASSIST_BYTES,
            )
            == 0
        )
        decision = rg.can_dispatch_task(snap, interactive_active=False)
        assert decision.allowed is False
        assert decision.dispatched_via_swap is False


def test_can_dispatch_task_swap_assist_never_overrides_interactive_refusal():
    # Interactive-lock priority (check 1) must win even when swap-assist
    # would otherwise cover the RAM gap — swap-assist can only ever cover
    # ITS OWN check's denial, never checks 1-3's.
    snap = _swap_snapshot(ram_headroom_bytes=rg.DISPATCH_MIN_HEADROOM_BYTES - MIB)
    decision = rg.can_dispatch_task(snap, interactive_active=True)
    assert decision.allowed is False
    assert decision.dispatched_via_swap is False
    assert "interactive" in decision.reason.lower()


def test_can_dispatch_task_swap_assist_never_overrides_thermal_refusal():
    snap = _swap_snapshot(
        ram_headroom_bytes=rg.DISPATCH_MIN_HEADROOM_BYTES - MIB, temperature_c=95.0,
    )
    decision = rg.can_dispatch_task(snap, interactive_active=False)
    assert decision.allowed is False
    assert decision.dispatched_via_swap is False
    assert "temperature" in decision.reason.lower()


def test_can_dispatch_task_swap_assist_never_overrides_battery_refusal():
    snap = _swap_snapshot(
        ram_headroom_bytes=rg.DISPATCH_MIN_HEADROOM_BYTES - MIB,
        battery_percent=5, battery_charging=False,
    )
    decision = rg.can_dispatch_task(snap, interactive_active=False)
    assert decision.allowed is False
    assert decision.dispatched_via_swap is False
    assert "battery" in decision.reason.lower()


def test_can_dispatch_task_swap_assist_disabled_via_parameter_keeps_ram_only_refusal():
    snap = _swap_snapshot(ram_headroom_bytes=rg.DISPATCH_MIN_HEADROOM_BYTES - MIB)
    decision = rg.can_dispatch_task(snap, interactive_active=False, enable_swap_assist=False)
    assert decision.allowed is False
    assert decision.dispatched_via_swap is False


def test_can_dispatch_task_swap_assist_disabled_via_env_var_keeps_ram_only_refusal(monkeypatch):
    monkeypatch.setenv(rg.CODEY_SWAP_ASSIST_ADMISSION_ENV, "0")
    snap = _swap_snapshot(ram_headroom_bytes=rg.DISPATCH_MIN_HEADROOM_BYTES - MIB)
    decision = rg.can_dispatch_task(snap, interactive_active=False)
    assert decision.allowed is False
    assert decision.dispatched_via_swap is False


def test_can_dispatch_task_bad_swap_assist_env_var_disables_rather_than_raises(monkeypatch):
    # Deliberately different posture from can_admit(): can_dispatch_task()
    # runs unguarded on every daemon dispatch-loop tick, so a malformed env
    # var must not raise here — it's caught and treated as disabled
    # (fail-safe direction: pre-D2 RAM-only behavior), not propagated.
    monkeypatch.setenv(rg.CODEY_SWAP_ASSIST_ADMISSION_ENV, "false")
    snap = _swap_snapshot(ram_headroom_bytes=rg.DISPATCH_MIN_HEADROOM_BYTES - MIB)
    decision = rg.can_dispatch_task(snap, interactive_active=False)
    assert decision.allowed is False
    assert decision.dispatched_via_swap is False


def test_can_dispatch_task_swap_assist_ram_only_pass_is_byte_for_byte_unchanged(monkeypatch):
    # A snapshot that already passes on ram_headroom_bytes alone must be
    # completely unaffected by SwapFree or enable_swap_assist.
    monkeypatch.delenv(rg.CODEY_SWAP_ASSIST_ADMISSION_ENV, raising=False)
    decisions = []
    for swap_free_bytes in (0, 10 * GIB):
        for enable_swap_assist in (True, False, None):
            snap = _swap_snapshot(
                ram_headroom_bytes=rg.DISPATCH_MIN_HEADROOM_BYTES + GIB,
                swap_free_bytes=swap_free_bytes,
            )
            kwargs = {} if enable_swap_assist is None else {"enable_swap_assist": enable_swap_assist}
            decisions.append(rg.can_dispatch_task(snap, interactive_active=False, **kwargs))
    first = decisions[0]
    assert first.allowed is True
    assert first.dispatched_via_swap is False
    for other in decisions[1:]:
        assert other == first


def test_can_dispatch_task_swap_assist_exact_combined_headroom_boundary_admits():
    # Exact-byte boundary, mirroring can_admit()'s own boundary-test pattern:
    # combined = ram_headroom_bytes + swap_headroom exactly equals the floor.
    max_swap_usage = 500 * MIB
    ram_headroom = rg.DISPATCH_MIN_HEADROOM_BYTES - max_swap_usage
    snap = _swap_snapshot(
        ram_headroom_bytes=ram_headroom, swap_total_bytes=12 * GIB, swap_free_bytes=10 * GIB,
    )
    decision = rg.can_dispatch_task(snap, interactive_active=False, max_swap_usage_bytes=max_swap_usage)
    assert decision.allowed is True
    assert decision.dispatched_via_swap is True


def test_can_dispatch_task_swap_assist_one_byte_under_combined_headroom_boundary_refuses():
    max_swap_usage = 500 * MIB
    ram_headroom = rg.DISPATCH_MIN_HEADROOM_BYTES - max_swap_usage - 1
    snap = _swap_snapshot(
        ram_headroom_bytes=ram_headroom, swap_total_bytes=12 * GIB, swap_free_bytes=10 * GIB,
    )
    decision = rg.can_dispatch_task(snap, interactive_active=False, max_swap_usage_bytes=max_swap_usage)
    assert decision.allowed is False
    assert decision.dispatched_via_swap is False
