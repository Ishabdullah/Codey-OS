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
    assert cost.total_bytes == cost.model_bytes + cost.kv_cache_bytes + cost.overhead_bytes


def test_estimate_model_load_cost_unknown_arch_omits_kv_term():
    spec = rg.ModelSpec(model_id="mystery-model", size_bytes=1_000_000_000, n_ctx=8192)
    cost = rg.estimate_model_load_cost(spec)
    assert cost.kv_cache_bytes == 0
    assert cost.model_bytes == 1_000_000_000


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

    spec = rg.ModelSpec(model_id="primary", path=MODEL_PATH, size_bytes=1, n_ctx=1024)
    assert rg._resolve_model_arch(spec) is rg.QWEN25_7B_ARCH

    spec2 = rg.ModelSpec(model_id="planner", path=PLANNER_MODEL_PATH, size_bytes=1, n_ctx=1024)
    assert rg._resolve_model_arch(spec2) is rg.QWEN25_1_5B_ARCH


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
    assert rg._resolve_model_arch(spec) is rg.QWEN25_7B_ARCH

    spec2 = rg.ModelSpec(model_id="planner", size_bytes=1, n_ctx=1024)
    assert rg._resolve_model_arch(spec2) is rg.QWEN25_1_5B_ARCH

    # KNOWN_MODEL_ARCHS's committed default entries themselves are untouched
    # (this mechanism is a lookup-time override, never a mutation of the dict).
    assert rg.KNOWN_MODEL_ARCHS["primary"] is rg.QWEN25_7B_ARCH
    assert rg.KNOWN_MODEL_ARCHS["planner"] is rg.QWEN25_1_5B_ARCH


def test_test_arch_override_primary_set_selects_qwen3_4b(monkeypatch):
    monkeypatch.setenv(rg.CODEY_TEST_PRIMARY_ARCH_ENV, "qwen3-4b")
    monkeypatch.delenv(rg.CODEY_TEST_PLANNER_ARCH_ENV, raising=False)

    spec = rg.ModelSpec(model_id="primary", size_bytes=1, n_ctx=1024)
    assert rg._resolve_model_arch(spec) is rg.QWEN3_4B_ARCH

    # KNOWN_MODEL_ARCHS's committed default entry is still untouched even
    # while the override is active — this is a lookup-time override, not a
    # mutation, so nothing else reading the dict directly is affected.
    assert rg.KNOWN_MODEL_ARCHS["primary"] is rg.QWEN25_7B_ARCH


def test_test_arch_override_planner_set_selects_qwen25_0_5b(monkeypatch):
    monkeypatch.delenv(rg.CODEY_TEST_PRIMARY_ARCH_ENV, raising=False)
    monkeypatch.setenv(rg.CODEY_TEST_PLANNER_ARCH_ENV, "qwen2.5-0.5b-planner")

    spec = rg.ModelSpec(model_id="planner", size_bytes=1, n_ctx=1024)
    assert rg._resolve_model_arch(spec) is rg.QWEN25_0_5B_PLANNER_ARCH
    assert rg.KNOWN_MODEL_ARCHS["planner"] is rg.QWEN25_1_5B_ARCH


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


def test_qwen3_4b_arch_kv_estimate_is_larger_than_qwen25_7b():
    # Pins the actual arithmetic this feature exists to fix: if the 7B arch
    # were wrongly used for a resident Qwen3-4B-Instruct model, the KV cache
    # cost would be under-estimated (7B factor: 28*4*128=14336) relative to
    # Qwen3-4B's real factor (36*8*128=36864, ~2.6x larger) — the dangerous
    # direction for a resource gate. Confirms QWEN3_4B_ARCH actually produces
    # the larger, correct estimate once selected via the override.
    n_ctx = 4096
    qwen3_4b_kv = rg.estimate_kv_cache_bytes(rg.QWEN3_4B_ARCH, n_ctx=n_ctx)
    qwen25_7b_kv = rg.estimate_kv_cache_bytes(rg.QWEN25_7B_ARCH, n_ctx=n_ctx)
    assert qwen3_4b_kv > qwen25_7b_kv
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
def test_new21_regression_rejects_load(mem_available_gib):
    spec = _new21_primary_spec()
    mi = _new21_meminfo(mem_available_gib)
    decision = rg.can_admit(spec, meminfo=mi, read_temp_fn=NO_THERMAL)
    assert decision.admitted is False
    # Rejected via the live budget check (cost * margin > headroom), not the
    # absolute per-model ceiling — a 7B model is NOT too big for this device
    # outright (it's this project's normal single-model case); it's too big
    # given what's already resident/used at that moment. Confirms the gate
    # is doing the intended "cost vs. live headroom" comparison, not
    # silently rejecting every load via the hard ceiling instead.
    assert decision.hard_reject is False
    assert decision.estimated_cost_bytes * rg.REQUIRED_HEADROOM_FACTOR > decision.headroom_bytes


def test_new21_naive_check_without_margin_would_have_admitted():
    """
    Pins the actual bug NEW-21 exposed, at the upper-bound (most favorable)
    endpoint of the plausible MemAvailable range above (6.5GiB): a
    "cost <= headroom" check with NO conservative margin (headroom_factor=1.0)
    would have approved this load. Deliberately only tested at this one
    endpoint (unlike test_new21_regression_rejects_load's full range) — at
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
    # ...yet the real gate, with its default conservative margin, correctly
    # rejects the same load:
    real = rg.can_admit(spec, meminfo=mi, read_temp_fn=NO_THERMAL)
    assert real.admitted is False


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
