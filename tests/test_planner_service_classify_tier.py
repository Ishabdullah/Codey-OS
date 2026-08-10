"""
Tests for core/planner_service.py's TODO.md 7.3 sub-task C integration —
`get_plan()` now calls `core.model_tiers.classify_tier()` and logs its
decision, but must not let that decision change which model path/port the
existing fallback ladder actually uses.

These tests mock `_request_daemon_plan()` / `core.orchestrator.plan_tasks()`
directly (no daemon process, no model load) and assert `get_plan()`'s
returned value is identical to what it was before sub-task C, across
representative inputs — with the classify_tier call present and, separately,
with classify_tier made to raise, to prove a classification failure can't
break planning either.
"""

import core.planner_service as planner_service


class DummyQueue:
    def __init__(self, descriptions):
        self.tasks = [DummyTask(d) for d in descriptions]


class DummyTask:
    def __init__(self, description):
        self.description = description


class TestNoPlanShortCircuit:
    def test_no_plan_true_returns_none_without_calling_daemon_or_classifier(self, monkeypatch):
        called = {"daemon": False, "classify": False}

        def fake_daemon(prompt):
            called["daemon"] = True
            return None

        def fake_classify(domain, role, message):
            called["classify"] = True
            return "large"

        monkeypatch.setattr(planner_service, "_request_daemon_plan", fake_daemon)
        monkeypatch.setattr("core.model_tiers.classify_tier", fake_classify)

        result = planner_service.get_plan("do something", no_plan=True)

        assert result is None
        assert called["daemon"] is False
        assert called["classify"] is False


class TestGetPlanWithRealClassifyTier:
    """Only `_request_daemon_plan()` is mocked here — `classify_tier()` runs
    for real, exercising its actual lazy `core.orchestrator` import and
    scoring logic on the daemon-success path. This is the test that proves
    "get_plan()'s behavior is unchanged" against the shipped classifier, not
    a stand-in stub."""

    def test_daemon_plan_returned_unchanged_with_real_classify_tier(self, monkeypatch):
        expected_plan = ["step one", "step two"]
        monkeypatch.setattr(planner_service, "_request_daemon_plan", lambda prompt: expected_plan)

        result = planner_service.get_plan("create a module and implement tests")

        assert result == expected_plan

    def test_daemon_plan_returned_unchanged_with_real_classify_tier_short_prompt(self, monkeypatch):
        expected_plan = ["only step"]
        monkeypatch.setattr(planner_service, "_request_daemon_plan", lambda prompt: expected_plan)

        result = planner_service.get_plan("hi")

        assert result == expected_plan


class TestDaemonPlanPathUnaffectedByClassifier:
    def test_daemon_plan_returned_unchanged_regardless_of_classify_tier_result(self, monkeypatch):
        expected_plan = ["step one", "step two"]
        monkeypatch.setattr(planner_service, "_request_daemon_plan", lambda prompt: expected_plan)

        for fake_tier in ("small", "large", "remote"):
            monkeypatch.setattr("core.model_tiers.classify_tier", lambda d, r, m, t=fake_tier: t)
            result = planner_service.get_plan("create a module and implement tests")
            assert result == expected_plan

    def test_daemon_plan_path_unaffected_when_classify_tier_raises(self, monkeypatch):
        expected_plan = ["step one", "step two"]
        monkeypatch.setattr(planner_service, "_request_daemon_plan", lambda prompt: expected_plan)

        def boom(domain, role, message):
            raise RuntimeError("classifier exploded")

        monkeypatch.setattr("core.model_tiers.classify_tier", boom)

        result = planner_service.get_plan("create a module and implement tests")
        assert result == expected_plan


class TestOrchestratorFallbackUnaffectedByClassifier:
    def test_orchestrator_fallback_used_when_daemon_returns_none(self, monkeypatch):
        monkeypatch.setattr(planner_service, "_request_daemon_plan", lambda prompt: None)

        import core.orchestrator as orchestrator

        expected_descriptions = ["orchestrator step 1", "orchestrator step 2"]
        monkeypatch.setattr(
            orchestrator, "plan_tasks", lambda prompt, project_context="": DummyQueue(expected_descriptions)
        )
        monkeypatch.setattr("core.model_tiers.classify_tier", lambda d, r, m: "small")

        result = planner_service.get_plan("create a module and implement tests")
        assert result == expected_descriptions

    def test_returns_none_when_both_daemon_and_orchestrator_have_nothing(self, monkeypatch):
        monkeypatch.setattr(planner_service, "_request_daemon_plan", lambda prompt: None)

        import core.orchestrator as orchestrator

        monkeypatch.setattr(
            orchestrator, "plan_tasks", lambda prompt, project_context="": DummyQueue([])
        )
        monkeypatch.setattr("core.model_tiers.classify_tier", lambda d, r, m: "large")

        result = planner_service.get_plan("hi")
        assert result is None


class TestClassifyTierCallDoesNotChangeControlFlow:
    def test_get_plan_result_identical_with_and_without_classify_tier_available(self, monkeypatch):
        """Simulates sub-task C not existing at all (classify_tier import
        fails) vs. existing normally — get_plan()'s return value must be
        identical either way, proving the classifier call is genuinely
        decorative to control flow."""
        expected_plan = ["a", "b", "c"]
        monkeypatch.setattr(planner_service, "_request_daemon_plan", lambda prompt: expected_plan)

        # With classify_tier working normally.
        monkeypatch.setattr("core.model_tiers.classify_tier", lambda d, r, m: "small")
        with_classifier = planner_service.get_plan("create and build and run tests")

        # With classify_tier's import itself failing (module missing/renamed).
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "core.model_tiers":
                raise ImportError("simulated: core.model_tiers unavailable")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        without_classifier = planner_service.get_plan("create and build and run tests")

        assert with_classifier == without_classifier == expected_plan
