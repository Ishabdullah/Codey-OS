"""
NEW-169 fix coverage — core/planner_service.py's _request_daemon_plan().

NEW-164/NEW-165/NEW-167 rebuilt the server-side timeout chain
(core/plannd.py's urlopen() -> core/daemon.py's asyncio.wait_for) to be
formula-based rather than a stale flat constant, but a code-reviewer
sanity check found this module's own client-side socket timeout
(send_command(..., timeout=185)) was never touched — an outermost,
shorter timeout that made the whole server-side rebuild moot for its one
real caller. This file confirms the fix: the socket timeout passed to
send_command() is now derived from the same compute_planner_timeout()
formula/inputs core/daemon.py uses for its own outer wait_for, plus extra
buffer, so it is never the shortest timeout in the chain.

No real daemon socket or model load — core.daemon.send_command is mocked
directly, matching this project's convention for these unit tests
(tests/test_plannd_timeout.py mocks urllib.request.urlopen the same way).
"""
import core.planner_service as planner_service
from core.plannd import (
    PLANNER_PROMPT,
    PLANNER_TIMEOUT_OUTER_BUFFER,
    compute_planner_timeout,
)
from core.tokens import estimate_tokens
from utils.config import PLANNER_MAX_TOKENS


def _expected_socket_timeout(prompt: str) -> float:
    prompt_tokens_estimate = estimate_tokens(PLANNER_PROMPT) + estimate_tokens(prompt)
    daemon_outer_timeout = compute_planner_timeout(prompt_tokens_estimate, PLANNER_MAX_TOKENS) + PLANNER_TIMEOUT_OUTER_BUFFER
    return daemon_outer_timeout + 10.0


def test_request_daemon_plan_derives_timeout_from_formula_not_flat_185(monkeypatch):
    captured = {}

    def fake_send_command(cmd, data, timeout=60.0):
        captured["timeout"] = timeout
        return {"plan": ["step one", "step two"]}

    monkeypatch.setattr("core.daemon.is_daemon_running", lambda: True)
    monkeypatch.setattr("core.daemon.send_command", fake_send_command)

    prompt = "fix the bug in core/legacy_calc.py"
    result = planner_service._request_daemon_plan(prompt)

    assert result == ["step one", "step two"]
    expected = _expected_socket_timeout(prompt)
    assert captured["timeout"] == expected
    # The old flat constant this replaced — must not survive under any input.
    assert captured["timeout"] != 185


def test_request_daemon_plan_socket_timeout_exceeds_daemon_outer_timeout(monkeypatch):
    """
    The whole point of NEW-169: this client-side timeout must always be
    strictly greater than core/daemon.py's own outer wait_for timeout for
    the same prompt, or the client is still the first thing to give up.
    """
    captured = {}
    monkeypatch.setattr("core.daemon.is_daemon_running", lambda: True)
    monkeypatch.setattr(
        "core.daemon.send_command",
        lambda cmd, data, timeout=60.0: captured.setdefault("timeout", timeout) or {"plan": None},
    )

    prompt = "a considerably longer prompt to check the formula scales " * 5
    planner_service._request_daemon_plan(prompt)

    prompt_tokens_estimate = estimate_tokens(PLANNER_PROMPT) + estimate_tokens(prompt)
    daemon_outer_timeout = compute_planner_timeout(prompt_tokens_estimate, PLANNER_MAX_TOKENS) + PLANNER_TIMEOUT_OUTER_BUFFER

    assert captured["timeout"] > daemon_outer_timeout


def test_request_daemon_plan_timeout_falls_back_to_flat_value_on_broken_import(monkeypatch):
    """
    Matches this function's own degrade-gracefully convention: a broken
    utils.config/core.* import must not crash planning — it should fall
    back to a safe, generous flat timeout instead.
    """
    captured = {}
    monkeypatch.setattr("core.daemon.is_daemon_running", lambda: True)
    monkeypatch.setattr(
        "core.daemon.send_command",
        lambda cmd, data, timeout=60.0: captured.setdefault("timeout", timeout) or {"plan": None},
    )

    import builtins

    real_import = builtins.__import__

    def broken_import(name, *args, **kwargs):
        if name == "core.plannd":
            raise ImportError("simulated broken import")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", broken_import)

    planner_service._request_daemon_plan("do something")

    assert captured["timeout"] == 1400.0
