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
from core.orchestrator import _score_message


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

    def test_planner_role_has_small_and_large_local_tiers(self):
        planner_tiers = model_tiers.tiers_for_role("coding", "planner")
        local_tiers = {tier: e for tier, e in planner_tiers.items() if e.backend == "local"}
        assert local_tiers.keys() == {"small", "large"}

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

    def test_planner_small_tier_matches_config(self):
        entry = model_tiers.get_tier("coding", "planner", "small")
        assert entry.model_ref == str(cfg.PLANNER_MODEL_PATH)
        assert entry.port == cfg.PLANND_SERVER_PORT
        assert entry.backend == "local"

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


class TestClassifyTier:
    """TODO.md 7.3 sub-task C: classify_tier() is a pure, non-LLM decision —
    it never loads a model or dispatches anything, it only returns a tier
    name. These tests check the returned string only."""

    def test_coder_role_always_returns_large_no_small_tier_exists(self):
        """The coder role has no "small" tier (NEW-84) — classify_tier must
        never invent one, regardless of how simple the message is."""
        assert model_tiers.classify_tier("coding", "coder", "hi") == "large"
        assert (
            model_tiers.classify_tier(
                "coding", "coder", "create a new module and implement tests and then run them"
            )
            == "large"
        )

    def test_planner_short_message_no_action_no_signals_is_small(self):
        assert model_tiers.classify_tier("coding", "planner", "hey") == "small"

    def test_planner_action_keyword_is_large(self):
        """A single action keyword (has_action) is enough to route to the
        large tier, even for an otherwise short message."""
        assert model_tiers.classify_tier("coding", "planner", "fix bug") == "large"

    def test_planner_two_complex_signals_is_large(self):
        assert (
            model_tiers.classify_tier("coding", "planner", "create and build something") == "large"
        )

    def test_planner_long_message_with_no_action_or_signal_words_is_large(self):
        """Length alone (>150 chars) routes to large, independent of
        keyword matches."""
        long_message = "x" * 160
        assert model_tiers.classify_tier("coding", "planner", long_message) == "large"

    def test_planner_signal_count_alone_is_large_without_has_action(self):
        """Isolates the `signal_count >= 2` clause specifically: "the api
        module" matches two COMPLEX_SIGNALS entries ("api", "module") but
        zero _action_kws entries, so has_action=False and length<150 — only
        signal_count>=2 can be driving this to "large". Without this test,
        every other "large" case in this class is also covered by
        has_action or length alone, leaving signal_count's own branch
        unverified. (Sub-task D strengthens this with an explicit
        signal_count==2 assertion, since "large" alone doesn't distinguish
        signal_count==2 from signal_count>=3.)"""
        message = "the api module"
        assert _score_message(message).signal_count == 2
        assert _score_message(message).has_action is False
        assert model_tiers.classify_tier("coding", "planner", message) == "large"

    def test_result_is_always_a_valid_key_for_the_role(self):
        available = model_tiers.tiers_for_role("coding", "planner")
        for message in ["hi", "fix bug", "x" * 200, "create and build and run tests"]:
            tier = model_tiers.classify_tier("coding", "planner", message)
            assert tier in available

    def test_unknown_role_raises_keyerror(self):
        """Fail loud on a role/domain with no configured tiers at all,
        matching get_tier()'s existing fail-loud convention."""
        with pytest.raises(KeyError):
            model_tiers.classify_tier("coding", "nonexistent-role", "hi")

    def test_reuses_score_message_not_a_third_keyword_list(self):
        """classify_tier() must not define its own action/signal keyword
        lists — it reuses core.orchestrator's existing ones via
        _score_message(). Confirmed indirectly: a message containing an
        orchestrator action keyword ("refactor") not present in any
        model_tiers-local list still routes to large."""
        assert model_tiers.classify_tier("coding", "planner", "refactor") == "large"

    def test_empty_message_no_action_no_length_no_signal_is_small(self):
        """Empty string has has_action=False, length=0, signal_count=0 —
        none of needs_large's three clauses fire, so this must be "small"."""
        assert model_tiers.classify_tier("coding", "planner", "") == "small"

    def test_unknown_domain_raises_keyerror(self):
        with pytest.raises(KeyError):
            model_tiers.classify_tier("nonexistent-domain", "planner", "hi")

    def test_length_boundary_150_is_not_large_by_length_alone(self):
        """needs_large's length clause is strictly `> 150` — a message of
        exactly 150 chars with no action keyword and fewer than 2
        COMPLEX_SIGNALS hits must NOT be routed to large by length alone."""
        message = "z" * 150
        assert _score_message(message).length == 150
        assert model_tiers.classify_tier("coding", "planner", message) == "small"

    def test_length_boundary_151_is_large_by_length_alone(self):
        """One char past the threshold flips the length clause to True."""
        message = "z" * 151
        assert _score_message(message).length == 151
        assert model_tiers.classify_tier("coding", "planner", message) == "large"

    def test_signal_count_boundary_one_is_not_large_by_signal_alone(self):
        """needs_large's signal clause is `signal_count >= 2` — exactly one
        COMPLEX_SIGNALS hit, no action keyword, short message, must stay
        "small". "module" alone is one COMPLEX_SIGNALS hit and matches no
        _action_kws entry."""
        message = "module"
        score = _score_message(message)
        assert score.signal_count == 1
        assert score.has_action is False
        assert score.length <= 150
        assert model_tiers.classify_tier("coding", "planner", message) == "small"

    # The symmetric signal_count==2 boundary case ("the api module") is
    # covered by TestClassifyTier.test_planner_signal_count_alone_is_large_
    # without_has_action above (strengthened with an explicit
    # signal_count==2 assertion) — not duplicated here.


class TestClassifyTierFullChainIntegration:
    """Confirms the full chain — a message through classify_tier() to a
    valid MODEL_TIERS key through get_tier() — works end to end for every
    currently-configured (domain, role) pair, not just the ones spot-checked
    in TestClassifyTier above. Iterates model_tiers.MODEL_TIERS itself
    rather than a hardcoded pair list, so this stays correct if a future
    round adds a new domain/role without anyone remembering to update this
    test file."""

    def test_classify_tier_then_get_tier_succeeds_for_every_configured_pair(self):
        domain_role_pairs = {(d, r) for d, r, _tier in model_tiers.MODEL_TIERS}
        assert domain_role_pairs, "MODEL_TIERS must have at least one (domain, role) pair to test"
        messages = ["hi", "fix bug", "z" * 200, "create and build and run tests"]
        for domain, role in sorted(domain_role_pairs):
            for message in messages:
                tier = model_tiers.classify_tier(domain, role, message)
                entry = model_tiers.get_tier(domain, role, tier)
                assert isinstance(entry, model_tiers.ModelTierEntry)
