"""
T7 (docs/telemetry_layer_design.md §2.E) — the `core.agent.get_last_run_stats()`
side-channel that `core/task_executor.py` reads to build category-E
`task_finished` records. Exercises the real `run_agent()` loop (mocked
`infer()` only, per tests/test_new19_patch_failed_repeat_escalation.py's
established pattern — never a real model load, CLAUDE.md rule 2), asserting
the counters mutated in place at existing loop points are actually correct,
not just that task_executor.py plumbs *some* dict through.

Does not duplicate tests/test_task_executor_telemetry.py's coverage of the
task_executor.py wiring itself (kill switch, thread-identity-keyed bucket
lookup [NEW-345], terminal_status mapping) — this file is
agent.py-loop-internals only.
"""
import json

import core.agent as agent


def _tool_block(name, args):
    return "<tool>\n" + json.dumps({"name": name, "args": args}) + "\n</tool>"


def test_get_last_run_stats_empty_before_any_call(monkeypatch):
    # Reset module state so this test doesn't depend on suite ordering.
    monkeypatch.setattr(agent, "_RUN_STATS_BY_THREAD", {})
    assert agent.get_last_run_stats() == {}


def test_successful_run_tracks_step_count_and_tools_called(monkeypatch):
    monkeypatch.setitem(agent.RECURSIVE_CONFIG, "enabled", False)

    responses = [
        _tool_block("read_file", {"path": "core/agent.py"}),
        "All done — file read and verified.",
    ]
    calls = {"n": 0}

    def fake_infer(messages, **kwargs):
        i = calls["n"]
        calls["n"] += 1
        return responses[i]

    monkeypatch.setattr(agent, "infer", fake_infer)
    monkeypatch.setattr(agent, "check_git_and_offer_commit", lambda *a, **kw: None)

    response, history = agent.run_agent(
        "read a file and report", [], _in_subtask=True
    )

    stats = agent.get_last_run_stats()
    assert stats["step_count"] == 2
    assert stats["tools_called"] == {"read_file": 1}
    assert stats["hit_max_steps"] is False
    assert stats["escalated"] is False
    assert stats["auto_retries"] == 0
    assert isinstance(stats["max_steps"], int) and stats["max_steps"] > 0


def test_run_agent_reset_leaks_nothing_from_previous_call(monkeypatch):
    """The very first thing run_agent() does (before any early-return
    branch) is reset the side-channel — a second, unrelated call must not
    see the first call's tools_called/step_count."""
    monkeypatch.setitem(agent.RECURSIVE_CONFIG, "enabled", False)
    monkeypatch.setattr(agent, "check_git_and_offer_commit", lambda *a, **kw: None)

    first_responses = [
        _tool_block("read_file", {"path": "core/agent.py"}),
        "Done.",
    ]
    calls = {"n": 0}

    def fake_infer_first(messages, **kwargs):
        i = calls["n"]
        calls["n"] += 1
        return first_responses[i]

    monkeypatch.setattr(agent, "infer", fake_infer_first)
    agent.run_agent("read a file", [], _in_subtask=True)
    first_stats = agent.get_last_run_stats()
    assert first_stats["tools_called"] == {"read_file": 1}

    # Second call resolves with no tool calls at all.
    calls2 = {"n": 0}

    def fake_infer_second(messages, **kwargs):
        calls2["n"] += 1
        return "Just a plain text answer, no tools needed."

    monkeypatch.setattr(agent, "infer", fake_infer_second)
    agent.run_agent("just answer a question", [], _in_subtask=True)
    second_stats = agent.get_last_run_stats()
    assert second_stats["tools_called"] == {}
    assert second_stats["step_count"] == 1
    assert second_stats["_seq"] != first_stats["_seq"]


def test_hit_max_steps_recorded_when_loop_exhausts(monkeypatch):
    monkeypatch.setitem(agent.RECURSIVE_CONFIG, "enabled", False)
    monkeypatch.setattr(agent, "check_git_and_offer_commit", lambda *a, **kw: None)
    monkeypatch.setitem(agent.AGENT_CONFIG, "max_steps", 1)

    def fake_infer(messages, **kwargs):
        # A tool call every turn (via <tool> markup with no matching
        # terminal text answer) keeps the loop going until max_steps.
        return _tool_block("read_file", {"path": "main.py"})

    monkeypatch.setattr(agent, "infer", fake_infer)

    response, history = agent.run_agent(
        "read a file repeatedly", [], _in_subtask=False
    )

    stats = agent.get_last_run_stats()
    assert stats["hit_max_steps"] is True
    assert stats["step_count"] == stats["max_steps"]
    assert "[INCOMPLETE]" in response


def test_escalation_reason_and_outcome_recorded_on_patch_failed_repeat(monkeypatch):
    """Mirrors tests/test_new19_patch_failed_repeat_escalation.py's
    peer-CLI-ran scenario, additionally asserting the T7 side-channel."""
    monkeypatch.setitem(agent.RECURSIVE_CONFIG, "enabled", False)
    monkeypatch.setattr(agent, "check_git_and_offer_commit", lambda *a, **kw: None)

    responses = [
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
        "Understood — I'll re-read the file and retry with a corrected old_str.",
    ]
    calls = {"n": 0}

    def fake_infer(messages, **kwargs):
        i = calls["n"]
        calls["n"] += 1
        return responses[i]

    monkeypatch.setattr(agent, "infer", fake_infer)
    monkeypatch.setattr(
        "core.peer_cli.escalate",
        lambda user_message, errors, files: "peer CLI diagnosed the issue.",
    )

    agent.run_agent(
        "add a docstring to shutdown function in main.py", [], _in_subtask=False
    )

    stats = agent.get_last_run_stats()
    assert stats["escalated"] is True
    assert stats["escalation_reason"] == "patch_failure"
    assert stats["escalation_outcome"] == "peer_cli"


def test_escalation_outcome_skipped_when_user_declines(monkeypatch):
    monkeypatch.setitem(agent.RECURSIVE_CONFIG, "enabled", False)
    monkeypatch.setattr(agent, "check_git_and_offer_commit", lambda *a, **kw: None)

    responses = [
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
        "Please clarify the correct old_str.",
    ]
    calls = {"n": 0}

    def fake_infer(messages, **kwargs):
        i = calls["n"]
        calls["n"] += 1
        return responses[i]

    monkeypatch.setattr(agent, "infer", fake_infer)
    monkeypatch.setattr("core.peer_cli.escalate", lambda user_message, errors, files: None)

    agent.run_agent(
        "add a docstring to shutdown function in main.py", [], _in_subtask=False
    )

    stats = agent.get_last_run_stats()
    assert stats["escalated"] is True
    assert stats["escalation_reason"] == "patch_failure"
    assert stats["escalation_outcome"] == "skipped"


def test_escalation_outcome_absent_on_redirect(monkeypatch):
    """The [redirect]: branch (human typed a redirect instruction, no peer
    CLI ran) has no honest fit in the closed {peer_cli, parked, skipped}
    escalation_outcome enum -- it must stay None (left absent by
    task_executor.py's telemetry emission, not written as a reasoned
    null -- see core/agent.py's comment on this branch for why no
    null_reason_codes entry is available either), not the
    false-but-closest-fit "peer_cli" (same class of bug as NEW-341)."""
    monkeypatch.setitem(agent.RECURSIVE_CONFIG, "enabled", False)
    monkeypatch.setattr(agent, "check_git_and_offer_commit", lambda *a, **kw: None)

    responses = [
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
        "Understood — I'll take that different approach and stop here.",
    ]
    calls = {"n": 0}

    def fake_infer(messages, **kwargs):
        i = calls["n"]
        calls["n"] += 1
        return responses[i]

    monkeypatch.setattr(agent, "infer", fake_infer)
    monkeypatch.setattr(
        "core.peer_cli.escalate",
        lambda user_message, errors, files: "[redirect]: try editing the other file instead.",
    )

    agent.run_agent(
        "add a docstring to shutdown function in main.py", [], _in_subtask=False
    )

    stats = agent.get_last_run_stats()
    assert stats["escalated"] is True
    assert stats["escalation_reason"] == "patch_failure"
    assert stats["escalation_outcome"] is None


def test_in_subtask_never_reaches_escalation(monkeypatch):
    """core/task_executor.py always passes in_subtask=True, so escalation
    (and therefore escalated/escalation_reason/escalation_outcome) is
    always False/None on the daemon task-execution path — an accurate
    reflection of the existing `not _in_subtask` guards, not a bug in the
    T7 instrumentation. See the T7 handoff for the full note."""
    monkeypatch.setitem(agent.RECURSIVE_CONFIG, "enabled", False)
    monkeypatch.setattr(agent, "check_git_and_offer_commit", lambda *a, **kw: None)

    responses = [
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
        "Please clarify the correct old_str.",
    ]
    calls = {"n": 0}

    def fake_infer(messages, **kwargs):
        i = calls["n"]
        calls["n"] += 1
        return responses[i]

    monkeypatch.setattr(agent, "infer", fake_infer)

    agent.run_agent(
        "add a docstring to shutdown function in main.py", [], _in_subtask=True
    )

    stats = agent.get_last_run_stats()
    assert stats["escalated"] is False
    assert stats["escalation_reason"] is None
    assert stats["escalation_outcome"] is None
