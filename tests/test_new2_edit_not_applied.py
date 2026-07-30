"""
NEW-2 regression test: when a file-mutating tool call (patch_file/write_file/
append_file) fails validation, retries and escalation are exhausted, and the
loop falls through to the generic "Tool result: ... Next action or final
answer:" turn, an explicit "[EDIT NOT APPLIED]" marker must be logged and
folded into the transcript sent back to the model — so the eventual plain-text
reply is never indistinguishable from a normal successful-edit answer.

See NEW_ISSUES.md NEW-2 for the confirmed root-cause trace this guards
against.
"""
import core.agent as agent


def _tool_block(name, args):
    import json

    return "<tool>\n" + json.dumps({"name": name, "args": args}) + "\n</tool>"


def test_edit_not_applied_marker_surfaced_after_retry_and_escalation_exhausted(
    monkeypatch, caplog
):
    # Disable recursive inference so the mocked `infer` calls drive the loop
    # directly and deterministically (matches the live-reproduced trace).
    monkeypatch.setitem(agent.RECURSIVE_CONFIG, "enabled", False)

    responses = [
        # Attempt 1: patch_file with empty old_str -> rejected by patch_tools.py
        _tool_block(
            "patch_file",
            {"path": "main.py", "old_str": "", "new_str": "def shutdown():\n    pass\n"},
        ),
        # Attempt 2: model repeats the (still-empty-old_str) failing call, but with
        # slightly different new_str content — as in the live-reproduced trace, the
        # model regenerates a not-quite-identical duplicate body rather than emitting
        # byte-identical args, so this does not hit the separate "duplicate tool call"
        # short-circuit (a different code path from the one under test here).
        _tool_block(
            "patch_file",
            {"path": "main.py", "old_str": "", "new_str": "def shutdown():\n    pass  # v2\n"},
        ),
        # Attempt 3: after the fallthrough, the model gives an ordinary text
        # clarification instead of a tool call.
        "Please provide the correct content for the old_str argument.",
    ]
    calls = {"n": 0}

    def fake_infer(messages, **kwargs):
        i = calls["n"]
        calls["n"] += 1
        return responses[i]

    monkeypatch.setattr(agent, "infer", fake_infer)

    logged = []
    monkeypatch.setattr(agent, "log_error", lambda msg: logged.append(msg))

    # _in_subtask=True skips the peer-CLI escalation call and the
    # check_git_and_offer_commit prompt (both are legitimately out of scope
    # for this test — the [EDIT NOT APPLIED] marker fires on the same
    # fallthrough regardless of whether escalation ran or was skipped, since
    # its condition only checks is_error()+tool name, not how we got there).
    response, history = agent.run_agent(
        "add a docstring to shutdown function in main.py",
        [],
        _in_subtask=True,
    )

    assert calls["n"] == 3, "expected exactly 3 model calls (2 failed attempts + 1 fallback text)"
    assert any("[EDIT NOT APPLIED]" in m for m in logged), (
        "expected an [EDIT NOT APPLIED] marker to be logged once retries/escalation "
        "were exhausted on a failed patch_file call"
    )
    assert "patch_file" in logged[0]
    assert "main.py" in logged[0]
    # The marker must also survive in the transcript actually sent to the
    # model (not just the console/log), otherwise a reviewer scanning
    # `history`/`messages` still can't tell the edit was dropped.
    assert response == responses[2]
