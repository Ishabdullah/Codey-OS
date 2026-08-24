"""
Tests for core/model_tiers.py — Track 3 Phase 5b / TODO.md 7.3 sub-task B/D.

Pure data/lookup tests. No model file is read, no server process is
spawned, no loader/classifier/dispatch code is touched — this module is a
config table only, not yet wired into anything that acts on it.
"""

import importlib

import pytest

import core.model_tiers as model_tiers
import utils.config as cfg


class TestTableStructure:
    def test_all_keys_are_coding_domain(self):
        """This first cut is coding-domain only."""
        assert all(domain == "coding" for domain, _role, _tier in model_tiers.MODEL_TIERS)

    def test_only_planner_and_coder_roles(self):
        """embedding is deliberately excluded — not tiered."""
        roles = {role for _domain, role, _tier in model_tiers.MODEL_TIERS}
        assert roles <= {"planner", "coder"}
        assert "embedding" not in roles

    def test_coder_role_has_exactly_one_local_tier(self):
        """NEW-84: SECONDARY_MODEL_PATH is dead config, not a real coder-small
        tier — the coder role must have exactly one local tier ("large"),
        not two."""
        coder_tiers = model_tiers.tiers_for_role("coding", "coder")
        local_tiers = {tier: e for tier, e in coder_tiers.items() if e.backend == "local"}
        assert local_tiers.keys() == {"large"}

    def test_coder_has_no_small_tier(self):
        assert ("coding", "coder", "small") not in model_tiers.MODEL_TIERS

    def test_planner_role_has_exactly_one_local_tier(self):
        """M1-D (2026-08-23): planning collapsed onto the same single primary
        server the coder uses — the planner role's former "small" tier (a
        dedicated 1.5B on its own port) is removed, leaving exactly one
        local tier ("large"), same as the coder role."""
        planner_tiers = model_tiers.tiers_for_role("coding", "planner")
        local_tiers = {tier: e for tier, e in planner_tiers.items() if e.backend == "local"}
        assert local_tiers.keys() == {"large"}

    def test_planner_has_no_small_tier(self):
        assert ("coding", "planner", "small") not in model_tiers.MODEL_TIERS

    def test_entries_are_model_tier_entry_instances(self):
        for entry in model_tiers.MODEL_TIERS.values():
            assert isinstance(entry, model_tiers.ModelTierEntry)

    def test_backend_field_is_a_known_backend(self):
        for entry in model_tiers.MODEL_TIERS.values():
            assert entry.backend in model_tiers.BACKENDS

    def test_local_entries_have_a_port_remote_entries_do_not(self):
        for (_domain, _role, _tier), entry in model_tiers.MODEL_TIERS.items():
            if entry.backend == "local":
                assert entry.port is not None
            else:
                assert entry.port is None


class TestValuesSourcedFromConfig:
    """Table values must come from utils/config.py, not be re-hardcoded."""

    def test_coder_large_tier_matches_config(self):
        entry = model_tiers.get_tier("coding", "coder", "large")
        assert entry.model_ref == str(cfg.MODEL_PATH)
        assert entry.port == cfg.PRIMARY_SERVER_PORT
        assert entry.backend == "local"

    def test_planner_large_tier_matches_config(self):
        entry = model_tiers.get_tier("coding", "planner", "large")
        assert entry.model_ref == str(cfg.MODEL_PATH)
        assert entry.port == cfg.PRIMARY_SERVER_PORT
        assert entry.backend == "local"


class TestNew125SameModelOverlap:
    """NEW-125: planner's "large" tier and coder's "large" tier are the same
    physical model today — the table must represent that literally."""

    def test_planner_large_and_coder_large_are_the_same_model_ref(self):
        planner_large = model_tiers.get_tier("coding", "planner", "large")
        coder_large = model_tiers.get_tier("coding", "coder", "large")
        assert planner_large.model_ref == coder_large.model_ref
        assert planner_large.port == coder_large.port
        assert planner_large.backend == coder_large.backend


class TestLookupHelpers:
    def test_get_tier_returns_entry(self):
        entry = model_tiers.get_tier("coding", "coder", "large")
        assert isinstance(entry, model_tiers.ModelTierEntry)

    def test_get_tier_raises_keyerror_on_unknown_tier(self):
        """Fail loud on a typo'd tier name, matching this project's
        fail-loud-on-bad-config convention (e.g. utils/config.py's
        CODEY_N_CTX validation) rather than silently returning None."""
        with pytest.raises(KeyError):
            model_tiers.get_tier("coding", "coder", "nonexistent-tier")

    def test_get_tier_raises_keyerror_on_unknown_role(self):
        with pytest.raises(KeyError):
            model_tiers.get_tier("coding", "nonexistent-role", "large")

    def test_get_tier_raises_keyerror_on_unknown_domain(self):
        with pytest.raises(KeyError):
            model_tiers.get_tier("nonexistent-domain", "coder", "large")

    def test_tiers_for_role_coder(self):
        tiers = model_tiers.tiers_for_role("coding", "coder")
        assert "large" in tiers
        assert all(isinstance(e, model_tiers.ModelTierEntry) for e in tiers.values())

    def test_tiers_for_role_unknown_returns_empty(self):
        assert model_tiers.tiers_for_role("coding", "nonexistent-role") == {}


class TestRemoteTierPresenceReflectsCurrentBackend:
    """The "remote" tier is only present when CODEY_BACKEND(_P) actually
    selects a remote backend today — this table formalizes today's existing
    fixed assignments, it doesn't invent a phantom remote entry for a
    backend nothing is currently pointed at."""

    def test_remote_tier_presence_matches_is_remote_backend(self):
        has_coder_remote = ("coding", "coder", "remote") in model_tiers.MODEL_TIERS
        assert has_coder_remote == cfg.is_remote_backend()

    def test_remote_tier_presence_matches_is_remote_planner_backend(self):
        has_planner_remote = ("coding", "planner", "remote") in model_tiers.MODEL_TIERS
        assert has_planner_remote == cfg.is_remote_planner_backend()

    @pytest.mark.parametrize(
        "env_var,role,backend,model_ref_attr",
        [
            ("CODEY_BACKEND", "coder", "openrouter", "OPENROUTER_MODEL"),
            ("CODEY_BACKEND", "coder", "unlimitedclaude", "UNLIMITEDCLAUDE_MODEL"),
            ("CODEY_BACKEND_P", "planner", "openrouter", "OPENROUTER_PLANNER_MODEL"),
            ("CODEY_BACKEND_P", "planner", "unlimitedclaude", "UNLIMITEDCLAUDE_PLANNER_MODEL"),
        ],
    )
    def test_module_reimport_with_remote_backend_adds_remote_tier(
        self, monkeypatch, env_var, role, backend, model_ref_attr
    ):
        """Simulate each remote-backend env var setting at import time and
        confirm the table would include a "remote" tier for the
        corresponding role, with the matching backend name, no port, and a
        model_ref sourced from the matching utils.config constant. Reloads
        both utils.config and core.model_tiers under the patched env, then
        restores the real modules afterward so this test doesn't leak state
        into any other test in the suite."""
        monkeypatch.setenv(env_var, backend)
        try:
            reloaded_cfg = importlib.reload(cfg)
            reloaded_tiers = importlib.reload(model_tiers)
            entry = reloaded_tiers.get_tier("coding", role, "remote")
            assert entry.backend == backend
            assert entry.port is None
            assert entry.model_ref == getattr(reloaded_cfg, model_ref_attr)
        finally:
            monkeypatch.undo()
            importlib.reload(cfg)
            importlib.reload(model_tiers)
