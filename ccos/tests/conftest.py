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
def _self_improve_on_for_legacy_tests(monkeypatch, request):
    """Legacy CCOS tests exercise the self-improvement modules directly, so they run with
    CODEY_SELF_IMPROVE=on. Tests that check the OFF default opt out with @pytest.mark.si_default."""
    if "si_default" not in request.keywords:
        monkeypatch.setenv("CODEY_SELF_IMPROVE", "on")
    else:
        monkeypatch.delenv("CODEY_SELF_IMPROVE", raising=False)


def pytest_configure(config):
    config.addinivalue_line("markers", "si_default: run with CODEY_SELF_IMPROVE unset (the OFF default)")
