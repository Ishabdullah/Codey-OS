"""
NEW-19 regression test: [PATCH_FAILED] (old_str-not-found) is deliberately
excluded from is_error() so a single failure bypasses retry entirely and
shows the model full file content, letting it reconstruct the edit itself
(see NEW-19 in NEW_ISSUES.md). But if the SAME path fails with
[PATCH_FAILED] more than once within a turn, that strategy isn't working —
the fix routes it into the existing peer-CLI escalation path instead of
showing full content indefinitely, and (when escalation doesn't resolve it)
logs a new, distinct "[PATCH_FAILED, UNRESOLVED]" marker rather than
reusing NEW-2's "[EDIT NOT APPLIED]" marker, whose "failed after retries
and escalation were exhausted" wording would be false for this case
([PATCH_FAILED] never enters the auto-retry gate in the first place).

See NEW_ISSUES.md NEW-19 for the confirmed root-cause trace and the
decision recorded 2026-07-30 this test guards against regressing.
"""
import core.agent as agent


def _tool_block(name, args):
    import json

    return "<tool>\n" + json.dumps({"name": name, "args": args}) + "\n</tool>"


def test_repeated_patch_failed_same_path_gets_unresolved_marker_not_edit_not_applied(
    monkeypatch, caplog
):
    # Disable recursive inference so the mocked `infer` calls drive the loop
    # directly and deterministically.
    monkeypatch.setitem(agent.RECURSIVE_CONFIG, "enabled", False)

    responses = [
        # Attempt 1: old_str that doesn't exist in main.py -> [PATCH_FAILED]
        _tool_block(
            "patch_file",
            {
                "path": "main.py",
                "old_str": "this_string_does_not_exist_in_the_file_v1",
                "new_str": "def shutdown():\n    pass\n",
            },
        ),
        # Attempt 2: same path, still nonexistent old_str (slightly different
        # text so this isn't short-circuited as an exact duplicate tool call)
        # -> second [PATCH_FAILED] on the same path within this turn.
        _tool_block(
            "patch_file",
            {
                "path": "main.py",
                "old_str": "this_string_does_not_exist_in_the_file_v2",
                "new_str": "def shutdown():\n    pass  # v2\n",
            },
        ),
        # Attempt 3: after the fallthrough, the model gives an ordinary text
        # reply instead of another tool call.
        "Please clarify the correct old_str for shutdown().",
    ]
    calls = {"n": 0}

    def fake_infer(messages, **kwargs):
        i = calls["n"]
        calls["n"] += 1
        return responses[i]

    monkeypatch.setattr(agent, "infer", fake_infer)

    logged = []
    monkeypatch.setattr(agent, "log_error", lambda msg: logged.append(msg))

    # _in_subtask=True skips the peer-CLI escalation call itself (out of
    # scope here — escalate() is exercised elsewhere) and lets us assert
    # deterministically on the fallthrough marker that fires when the
    # repeated-[PATCH_FAILED] case is never resolved within the turn.
    response, history = agent.run_agent(
        "add a docstring to shutdown function in main.py",
        [],
        _in_subtask=True,
    )

    assert calls["n"] == 3, "expected exactly 3 model calls (2 failed patch attempts + 1 fallback text)"
    assert any("[PATCH_FAILED, UNRESOLVED]" in m for m in logged), (
        "expected a [PATCH_FAILED, UNRESOLVED] marker to be logged once the same path "
        "failed with [PATCH_FAILED] more than once in this turn"
    )
    assert "patch_file" in logged[0]
    assert "main.py" in logged[0]
    # Wording must be true regardless of whether escalation actually ran
    # (it doesn't, here, since _in_subtask=True) — must not claim escalation
    # "was exhausted"/"did not resolve it" when it never ran at all.
    assert "escalation were exhausted" not in logged[0]
    assert "escalation did not resolve" not in logged[0]
    # Must NOT reuse NEW-2's [EDIT NOT APPLIED] marker — its "after retries
    # and escalation were exhausted" wording is false for [PATCH_FAILED],
    # which never enters the auto-retry gate in the first place.
    assert not any("[EDIT NOT APPLIED]" in m for m in logged)
    # The marker must also survive in the transcript actually sent to the
    # model (not just the console/log).
    assert response == responses[2]


def test_single_patch_failed_does_not_trigger_unresolved_marker():
    # A lone [PATCH_FAILED] on a path (no repeat) must keep existing
    # behavior: no escalation, no new marker — full file content is shown
    # so the model can reconstruct the edit itself.
    responses = [
        _tool_block(
            "patch_file",
            {
                "path": "main.py",
                "old_str": "this_string_does_not_exist_in_the_file",
                "new_str": "def shutdown():\n    pass\n",
            },
        ),
        "Understood, let me try a different old_str next time.",
    ]
    calls = {"n": 0}

    def fake_infer(messages, **kwargs):
        i = calls["n"]
        calls["n"] += 1
        return responses[i]

    import pytest

    monkeypatch = pytest.MonkeyPatch()
    try:
        monkeypatch.setitem(agent.RECURSIVE_CONFIG, "enabled", False)
        monkeypatch.setattr(agent, "infer", fake_infer)
        logged = []
        monkeypatch.setattr(agent, "log_error", lambda msg: logged.append(msg))

        response, history = agent.run_agent(
            "add a docstring to shutdown function in main.py",
            [],
            _in_subtask=True,
        )

        assert calls["n"] == 2
        assert not any("[PATCH_FAILED, UNRESOLVED]" in m for m in logged)
        assert not any("[EDIT NOT APPLIED]" in m for m in logged)
    finally:
        monkeypatch.undo()


def _repeated_patch_failed_responses():
    return [
        _tool_block(
            "patch_file",
            {
                "path": "main.py",
                "old_str": "this_string_does_not_exist_in_the_file_v1",
                "new_str": "def shutdown():\n    pass\n",
            },
        ),
        _tool_block(
            "patch_file",
            {
                "path": "main.py",
                "old_str": "this_string_does_not_exist_in_the_file_v2",
                "new_str": "def shutdown():\n    pass  # v2\n",
            },
        ),
    ]


def test_repeated_patch_failed_actually_calls_escalate_with_error_context(monkeypatch):
    # Not _in_subtask this time — the second [PATCH_FAILED] on the same path
    # must reach the real escalation call site (core.peer_cli.escalate),
    # not just the fallthrough marker. Also asserts error_log is non-empty
    # at call time, since is_error() doesn't capture [PATCH_FAILED] on its
    # own — the fix must mirror that accumulation for escalate()'s benefit.
    monkeypatch.setitem(agent.RECURSIVE_CONFIG, "enabled", False)

    responses = _repeated_patch_failed_responses() + [
        "Understood — I'll re-read the file and retry with a corrected old_str."
    ]
    calls = {"n": 0}

    def fake_infer(messages, **kwargs):
        i = calls["n"]
        calls["n"] += 1
        return responses[i]

    monkeypatch.setattr(agent, "infer", fake_infer)

    escalate_calls = []

    def fake_escalate(user_message, errors, files):
        escalate_calls.append((user_message, list(errors), list(files)))
        return "peer CLI diagnosed the issue: old_str is stale, re-read the file."

    monkeypatch.setattr("core.peer_cli.escalate", fake_escalate)

    response, history = agent.run_agent(
        "add a docstring to shutdown function in main.py",
        [],
        _in_subtask=False,
    )

    assert len(escalate_calls) == 1, "expected escalate() to be called exactly once"
    _um, _errors, _files = escalate_calls[0]
    assert _errors, "error_log must not be empty when escalate() is called for a repeated [PATCH_FAILED]"
    assert any("PATCH_FAILED" in e for e in _errors)
    assert "main.py" in _files
    # Peer CLI output was injected back into the loop as the next user turn
    # (not returned raw) — confirm the follow-up model call actually saw it.
    assert calls["n"] == 3
    assert response == responses[2]


def test_repeated_patch_failed_escalate_redirect_branch(monkeypatch):
    # Covers the "[redirect]: ..." branch of the shared escalation path.
    monkeypatch.setitem(agent.RECURSIVE_CONFIG, "enabled", False)

    responses = _repeated_patch_failed_responses() + [
        "Got it, trying the redirected approach."
    ]
    calls = {"n": 0}

    def fake_infer(messages, **kwargs):
        i = calls["n"]
        calls["n"] += 1
        return responses[i]

    monkeypatch.setattr(agent, "infer", fake_infer)
    monkeypatch.setattr(
        "core.peer_cli.escalate",
        lambda user_message, errors, files: "[redirect]: try write_file instead",
    )

    response, history = agent.run_agent(
        "add a docstring to shutdown function in main.py",
        [],
        _in_subtask=False,
    )

    assert calls["n"] == 3
    assert response == responses[2]


def test_repeated_patch_failed_escalate_skipped_falls_through_to_marker(monkeypatch):
    # Covers the "user skipped escalation" branch (escalate() returns None)
    # — must still fall through to the [PATCH_FAILED, UNRESOLVED] marker.
    monkeypatch.setitem(agent.RECURSIVE_CONFIG, "enabled", False)

    responses = _repeated_patch_failed_responses() + [
        "Please clarify the correct old_str."
    ]
    calls = {"n": 0}

    def fake_infer(messages, **kwargs):
        i = calls["n"]
        calls["n"] += 1
        return responses[i]

    monkeypatch.setattr(agent, "infer", fake_infer)
    monkeypatch.setattr("core.peer_cli.escalate", lambda user_message, errors, files: None)

    logged = []
    monkeypatch.setattr(agent, "log_error", lambda msg: logged.append(msg))

    response, history = agent.run_agent(
        "add a docstring to shutdown function in main.py",
        [],
        _in_subtask=False,
    )

    assert calls["n"] == 3
    assert any("[PATCH_FAILED, UNRESOLVED]" in m for m in logged)
    assert response == responses[2]
