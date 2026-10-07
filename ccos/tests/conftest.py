"""
CCOS test-suite fixtures/hooks.

AGI_AUDIT_PLAN.md item 1.1. Most tests in this directory end in
`return True`, because each file also has a script-mode `main()` that
counts a test as passed only when it returns truthy (`python
ccos/tests/test_x.py`). Under pytest, a non-None return value emits
PytestReturnNotNoneWarning (69 of them) and, if any test ever returned
False, pytest would silently ignore it and report a pass.

This hook keeps the `return True` convention (so the script-mode runners
keep working) but makes pytest honor it: a test that returns False now
FAILS, and returning True/None no longer warns. Assertions inside the
tests are unaffected and still fail as usual.
"""

import inspect

import pytest


@pytest.hookimpl(tryfirst=True)
def pytest_pyfunc_call(pyfuncitem):
    testfunction = pyfuncitem.obj
    # Leave async tests to whichever plugin awaits them; calling them here
    # would create a coroutine that is never awaited and pass silently.
    if inspect.iscoroutinefunction(testfunction):
        return None
    argnames = pyfuncitem._fixtureinfo.argnames
    testargs = {arg: pyfuncitem.funcargs[arg] for arg in argnames}
    result = testfunction(**testargs)
    if result is False:
        pytest.fail(f"{pyfuncitem.name} returned False", pytrace=False)
    return True


@pytest.fixture(autouse=True)
def _isolate_performance_and_reflection_singletons(tmp_path, monkeypatch):
    """WP0.6 (CODEY_OS_MASTER_BLUEPRINT.md §21): get_performance_tracker()
    and get_reflection_engine() are process-wide singletons that fall back
    to the REAL on-device ccos/data/ccos_memory.db and reflections.jsonl
    whenever a caller doesn't inject its own instance -- and none of
    AgentOrchestrator, AutoImprovementLoop, GoalEngine, CapabilityOptimizer,
    LifecycleManager, or SkillRecombiner accept one via their constructors
    (confirmed by reading all six __init__ methods). Every CCOS test run
    constructing any of those classes with defaults was silently writing
    real rows into those two files -- confirmed live: cap_metrics grew from
    454 rows (the 2026-10-06 census count) to 467 between then and this fix,
    purely from this session's own earlier test runs. This is the root
    cause of the "unsourced metrics" WP0.6 quarantines; without this fix,
    running the test suite again would immediately repopulate what the
    quarantine just cleared.

    Resetting the module-global singleton to None (not just redirecting the
    path) matters: get_performance_tracker()/get_reflection_engine() only
    construct a NEW instance when the singleton is None, so a prior test in
    the same process that already populated the real singleton would keep
    returning it regardless of what DB_PATH/REFLECTIONS_PATH says now.
    """
    import ccos.core.performance_tracker as pt
    import ccos.core.reflection_engine as refl

    monkeypatch.setattr(pt, "_tracker", None)
    monkeypatch.setattr(pt, "DB_PATH", str(tmp_path / "ccos_memory_test.db"))
    monkeypatch.setattr(refl, "_engine", None)
    monkeypatch.setattr(refl, "REFLECTIONS_PATH", str(tmp_path / "reflections_test.jsonl"))


@pytest.fixture(autouse=True)
def _self_improve_on_for_legacy_tests(monkeypatch, request):
    """Legacy CCOS tests exercise the self-improvement modules directly, so they run with
    CODEY_SELF_IMPROVE=on. Tests that check the OFF default opt out with @pytest.mark.si_default."""
    if "si_default" not in request.keywords:
        monkeypatch.setenv("CODEY_SELF_IMPROVE", "on")
    else:
        monkeypatch.delenv("CODEY_SELF_IMPROVE", raising=False)


def pytest_configure(config):
    config.addinivalue_line("markers", "si_default: run with CODEY_SELF_IMPROVE unset (the OFF default)")
