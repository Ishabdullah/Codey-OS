"""
TODO.md 7.4b sub-task C — coder interactive-vs-background context branching.

Sub-task C: the coder gets the full MODEL_CONFIG["n_ctx"] ceiling when
core.resource_gate.is_interactive_session_active() is True, else the
smaller utils.config.get_coder_background_n_ctx() (16384 by default) —
wired through core/loader_v2.py's ModelLoader.load_primary().

Also covers utils/config.py's get_coder_background_n_ctx() CODEY_N_CTX
clamping (a smaller substitute-model override must bind downward on it
too), and — NEW-102/bug_002 (2026-08-13) — that it's a LIVE read of
MODEL_CONFIG["n_ctx"], not a constant frozen at import time, so a runtime
--ctx override (main.py's apply_overrides()) actually reaches the
background coder ceiling, not just the interactive coder path.

M1-D (2026-08-23): this file used to ALSO cover TODO.md 7.4b sub-task B —
the dedicated 1.5B planner's own fixed context ceiling
(utils.config.get_planner_n_ctx(), 8192 by default), wired through
core/planner_loader.py's PlannerLoader.load(). Both that function and that
module are deleted — planning now shares the coder's single Qwen3.5-4B
server/context, so a separate planner-only ceiling is no longer an
expressible concept, not merely unused (see utils/config.py's own comment
on the removal). TestPlannerNCtx and every get_planner_n_ctx() reference in
this file's remaining classes are removed accordingly, not adapted.
"""
import importlib
import os
from unittest.mock import MagicMock, patch

import pytest

import core.loader_v2 as lv
import core.resource_gate as rg
import utils.config as cfg


def _meminfo_with_drop_after(n_before: int, high: int = 10**10, low: int = 0):
    calls = {"n": 0}

    def _fake(*a, **k):
        calls["n"] += 1
        return {"MemAvailable": high if calls["n"] <= n_before else low}

    return _fake


class FakeServerSpawned:
    """Stand-in LlamaServer that records the n_ctx it was constructed with
    (matching this project's real LlamaServer.__init__ signature) and
    "spawns" successfully. Mirrors tests/test_loader_resource_gate.py's
    own FakeServerSpawned, but also captures n_ctx for this sub-task's
    assertions."""

    last_n_ctx = None
    last_port = None

    def __init__(self, model_path=None, port=None, n_ctx=None):
        FakeServerSpawned.last_n_ctx = n_ctx
        FakeServerSpawned.last_port = port
        self.process = MagicMock(pid=os.getpid())
        self._started = True

    def start(self):
        return True

    def stop(self):
        self.process = None
        self._started = False

    def is_running(self):
        return self._started


class TestCoderInteractiveVsBackgroundNCtx:
    def teardown_method(self):
        FakeServerSpawned.last_n_ctx = None
        FakeServerSpawned.last_port = None

    def _run_load_primary(self, monkeypatch, interactive: bool):
        fake_decision = MagicMock(admitted=True, estimated_cost_bytes=1024, reason="ok")
        reserve_calls = []
        monkeypatch.setattr(
            rg,
            "reserve_slot",
            lambda spec, **k: (reserve_calls.append(spec) or fake_decision, "slot-primary"),
        )
        monkeypatch.setattr(rg, "mark_resident", lambda *a, **k: True)
        monkeypatch.setattr(rg, "release_slot", lambda *a, **k: True)
        monkeypatch.setattr(rg, "read_meminfo", _meminfo_with_drop_after(1))
        monkeypatch.setattr(rg, "is_interactive_session_active", lambda *a, **k: interactive)

        with patch.object(lv, "LlamaServer", FakeServerSpawned), patch(
            "pathlib.Path.exists", return_value=True
        ):
            loader = lv.ModelLoader()
            assert loader.load_primary() is True

        return reserve_calls

    def test_interactive_session_active_uses_full_n_ctx(self, monkeypatch):
        reserve_calls = self._run_load_primary(monkeypatch, interactive=True)
        assert reserve_calls[0].n_ctx == cfg.MODEL_CONFIG["n_ctx"]
        assert FakeServerSpawned.last_n_ctx == cfg.MODEL_CONFIG["n_ctx"]

    def test_no_interactive_session_uses_background_n_ctx(self, monkeypatch):
        reserve_calls = self._run_load_primary(monkeypatch, interactive=False)
        assert reserve_calls[0].n_ctx == cfg.get_coder_background_n_ctx()
        assert FakeServerSpawned.last_n_ctx == cfg.get_coder_background_n_ctx()

    def test_gate_spec_and_real_spawn_always_agree(self, monkeypatch):
        """The ModelSpec passed to the gate and the LlamaServer actually
        spawned must never disagree on n_ctx (the NEW-84 desync class) —
        check both interactive states, not just one."""
        for interactive in (True, False):
            FakeServerSpawned.last_n_ctx = None
            reserve_calls = self._run_load_primary(monkeypatch, interactive)
            assert reserve_calls[0].n_ctx == FakeServerSpawned.last_n_ctx


class TestNCtxFunctionsClampToCodeyNCtxOverride:
    """CODEY_N_CTX seeds MODEL_CONFIG["n_ctx"] at import time (utils/config.py's
    `_n_ctx`), so these still need importlib.reload() to exercise the
    env-var path specifically — that part of config.py's import-time
    behavior is unchanged by the NEW-102/bug_002 fix below. What changed:
    get_coder_background_n_ctx() is now a function, called after reload
    rather than read as a frozen attribute. (This class used to also cover
    get_planner_n_ctx() — removed in M1-D, 2026-08-23, see module
    docstring.)"""

    @pytest.fixture(autouse=True)
    def restore_config_module(self):
        yield
        os.environ.pop("CODEY_N_CTX", None)
        importlib.reload(cfg)

    def test_coder_background_n_ctx_defaults_below_full_n_ctx(self):
        os.environ.pop("CODEY_N_CTX", None)
        reloaded = importlib.reload(cfg)
        assert reloaded.get_coder_background_n_ctx() == 16384

    def test_coder_background_n_ctx_clamps_to_smaller_override(self):
        os.environ["CODEY_N_CTX"] = "4096"
        reloaded = importlib.reload(cfg)
        assert reloaded.MODEL_CONFIG["n_ctx"] == 4096
        # A substitute-model override smaller than 16384 must bind
        # downward on the derived value too — it must never sit above
        # the override CODEY_N_CTX exists to enforce.
        assert reloaded.get_coder_background_n_ctx() == 4096

    def test_larger_override_does_not_raise_ceiling_above_its_own_default(self):
        os.environ["CODEY_N_CTX"] = "65536"
        reloaded = importlib.reload(cfg)
        assert reloaded.MODEL_CONFIG["n_ctx"] == 65536
        # An override LARGER than 16384 must not raise the background
        # coder's own fixed ceiling above its intended value — min()
        # clamps only downward.
        assert reloaded.get_coder_background_n_ctx() == 16384


class TestNCtxFunctionsFollowRuntimeMutation:
    """NEW-102/bug_002 (2026-08-13): get_coder_background_n_ctx() must be a
    LIVE read of MODEL_CONFIG["n_ctx"], not a value frozen at import time —
    this is what makes a runtime mutation of MODEL_CONFIG["n_ctx"] (e.g.
    main.py's apply_overrides() applying --ctx) actually reach it, unlike
    the old CODER_BACKGROUND_N_CTX module-level constant this round
    replaced. No importlib.reload() here on purpose — that would re-derive
    from the CODEY_N_CTX env var and re-mask the exact bug this covers."""

    def teardown_method(self):
        cfg.MODEL_CONFIG["n_ctx"] = 32768

    def test_get_coder_background_n_ctx_follows_runtime_model_config_mutation(self):
        cfg.MODEL_CONFIG["n_ctx"] = 4096
        assert cfg.get_coder_background_n_ctx() == 4096

    def test_get_coder_background_n_ctx_still_clamps_when_model_config_raised(self):
        cfg.MODEL_CONFIG["n_ctx"] = 65536
        assert cfg.get_coder_background_n_ctx() == 16384


class TestCliCtxFlagReachesBackgroundCoder:
    """The regression this round fixes, exercised through the real CLI
    entry point rather than just the config function directly: main.py's
    apply_overrides() applying --ctx must be visible to
    get_coder_background_n_ctx() afterward. Pre-fix, this was frozen at
    utils.config import time and never saw this mutation (only the
    interactive coder's MODEL_CONFIG.get("n_ctx", ...) read did)."""

    def teardown_method(self):
        cfg.MODEL_CONFIG["n_ctx"] = 32768

    def test_apply_overrides_ctx_flag_reaches_background_ceiling(self):
        import argparse

        from main import apply_overrides

        args = argparse.Namespace(
            yolo=False, allow_self_mod=False, threads=None, ctx=4096
        )
        apply_overrides(args)

        assert cfg.MODEL_CONFIG["n_ctx"] == 4096
        assert cfg.get_coder_background_n_ctx() == 4096

    def test_apply_overrides_rejects_non_positive_ctx(self):
        import argparse

        from main import apply_overrides

        args = argparse.Namespace(
            yolo=False, allow_self_mod=False, threads=None, ctx=0
        )
        with pytest.raises(ValueError):
            apply_overrides(args)

        args_negative = argparse.Namespace(
            yolo=False, allow_self_mod=False, threads=None, ctx=-1
        )
        with pytest.raises(ValueError):
            apply_overrides(args_negative)
