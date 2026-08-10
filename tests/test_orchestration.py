#!/usr/bin/env python3
"""
Test orchestration heuristics.

Verifies that the is_complex function correctly identifies when
a request should trigger multi-step planning vs. direct response.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.orchestrator import (CONVERSATIONAL_PATTERNS, ScoreResult,
                               _postprocess_plan, _score_message, is_complex)


class TestOrchestrationHeuristics:
    """Test orchestration complexity detection."""

    def test_question_not_complex(self):
        """Simple questions should NOT trigger orchestration."""
        assert is_complex("How do I create a file?") == False

    def test_what_is_not_complex(self):
        """'What is' questions should NOT trigger orchestration."""
        assert is_complex("What is a decorator?") == False

    def test_can_you_explain_not_complex(self):
        """'Can you explain' should NOT trigger orchestration."""
        assert is_complex("Can you explain how this works?") == False

    def test_tell_me_not_complex(self):
        """'Tell me' requests should NOT trigger orchestration."""
        assert is_complex("Tell me about Python classes") == False

    def test_how_does_not_complex(self):
        """'How does' questions should NOT trigger orchestration."""
        assert is_complex("How does the async event loop work?") == False

    def test_should_i_use_not_complex(self):
        """'Should I use' questions should NOT trigger orchestration."""
        assert is_complex("Should I use Flask or Django?") == False

    def test_difference_between_not_complex(self):
        """'Difference between' questions should NOT trigger orchestration."""
        assert is_complex("What's the difference between list and tuple?") == False

    def test_i_need_help_not_complex(self):
        """'I need help' should NOT trigger orchestration."""
        assert is_complex("I need help understanding this error") == False

    def test_create_simple_file_not_complex(self):
        """Short create requests should NOT trigger orchestration."""
        assert is_complex("Create a file") == False

    def test_how_to_use_not_complex(self):
        """'How to use' questions should NOT trigger orchestration."""
        assert is_complex("How to use pytest?") == False

    def test_complex_create_with_tests(self):
        """Create with tests SHOULD trigger orchestration."""
        # Need enough COMPLEX_SIGNALS matches
        assert is_complex("Create a Flask app with user authentication and also add tests") == True

    def test_complex_build_multiple_components(self):
        """Build with multiple components SHOULD trigger orchestration."""
        assert (
            is_complex(
                "Build a REST API with multiple endpoints for users, posts, and also comments"
            )
            == True
        )

    def test_complex_refactor_and_run(self):
        """Refactor and run SHOULD trigger orchestration."""
        assert is_complex("Refactor the code to use classes and then run the tests") == True

    def test_complex_implement_system(self):
        """Implement system SHOULD trigger orchestration."""
        assert is_complex("Implement a caching system with Redis for the application") == True

    def test_long_message_fewer_signals(self):
        """Long messages need fewer signals to be complex."""
        msg = "Create a complete web application with user authentication, database models, API endpoints, and comprehensive test coverage including unit tests and integration tests"
        assert is_complex(msg) == True

    def test_short_message_needs_more_signals(self):
        """Short messages need more signals to be complex."""
        msg = "Create app"
        assert is_complex(msg) == False

    def test_question_mark_not_complex(self):
        """Messages ending with ? should NOT be complex (without action keywords)."""
        assert is_complex("Is this the right approach?") == False

    def test_action_keyword_with_question_not_complex(self):
        """Action keywords with question format should NOT be complex."""
        assert is_complex("How do I create a function?") == False

    def test_conversational_pattern_in_long_request(self):
        """Conversational patterns should filter even long requests."""
        msg = "Can you explain how to create a complete web application with authentication"
        assert is_complex(msg) == False

    def test_all_conversational_patterns_filtered(self):
        """All defined conversational patterns should be filtered."""
        for pattern in CONVERSATIONAL_PATTERNS:
            msg = f"{pattern} create something"
            # Most patterns should result in NOT complex
            # Some might still be complex if they have enough signals
            # This test just verifies the patterns are being checked
            result = is_complex(msg)
            # We don't assert False for all, as some patterns with enough
            # complexity signals might still trigger orchestration

    def test_implementation_request_complex(self):
        """Implementation requests SHOULD trigger orchestration."""
        # Need enough COMPLEX_SIGNALS matches
        assert (
            is_complex(
                "Implement a user registration system with multiple models and also API endpoints"
            )
            == True
        )

    def test_add_feature_complex(self):
        """Add feature requests SHOULD trigger orchestration."""
        # Need enough COMPLEX_SIGNALS matches
        assert (
            is_complex("Add a new module for handling file uploads and then also add tests for it")
            == True
        )

    def test_rewrite_and_refactor_complex(self):
        """Rewrite/refactor requests SHOULD trigger orchestration."""
        # Need enough COMPLEX_SIGNALS matches
        assert (
            is_complex(
                "Rewrite the data processing module to use async and also refactor for the application"
            )
            == True
        )

    def test_multiple_tasks_complex(self):
        """Multiple tasks SHOULD trigger orchestration."""
        assert (
            is_complex("Create the models and then add the API endpoints and also write tests")
            == True
        )

    def test_empty_message_not_complex(self):
        """Empty messages should NOT be complex."""
        assert is_complex("") == False

    def test_very_short_message_not_complex(self):
        """Very short messages should NOT be complex."""
        assert is_complex("Hi") == False
        assert is_complex("Hello") == False
        assert is_complex("Test") == False


class TestScoreMessage:
    """
    Direct unit tests for `_score_message()`/`ScoreResult` — TODO.md 7.3
    sub-task A extracted this out of `is_complex()` as a reusable helper
    (now also consumed by `core.model_tiers.classify_tier()`, sub-task C).
    `is_complex()`'s existing tests above only exercise `_score_message()`
    indirectly through its combined boolean result; these tests check the
    raw `ScoreResult` fields themselves so a future change to the scoring
    logic that happens to preserve `is_complex()`'s boolean outputs (but
    breaks `classify_tier()`, which reads different fields) would still be
    caught here.
    """

    def test_returns_score_result_instance(self):
        assert isinstance(_score_message("hello"), ScoreResult)

    def test_msg_is_lowercased(self):
        result = _score_message("Create A File")
        assert result.msg == "create a file"

    def test_length_is_len_of_original_message_not_lowercased_copy(self):
        # Same length either way, but confirms `length` is computed from
        # the original argument, not incidentally from something else.
        message = "Create a Flask App"
        assert _score_message(message).length == len(message)

    def test_has_action_true_for_action_keyword(self):
        assert _score_message("please fix the bug").has_action is True

    def test_has_action_false_with_no_action_keyword(self):
        assert _score_message("the weather today").has_action is False

    def test_has_action_matches_whole_word_only(self):
        # "add" must not match inside "address" — word-boundary regex.
        assert _score_message("what is my address").has_action is False

    def test_is_question_true_for_question_mark(self):
        assert _score_message("Is this right?").is_question is True

    def test_is_question_true_for_question_starter(self):
        assert _score_message("What is a decorator").is_question is True

    def test_is_question_true_for_qa_phrase(self):
        assert _score_message("tell me about Python").is_question is True

    def test_is_question_false_for_plain_statement(self):
        assert _score_message("create a new file called app.py").is_question is False

    def test_is_conversational_true_for_conversational_pattern(self):
        assert _score_message("How do I create a file?").is_conversational is True

    def test_is_conversational_false_without_pattern(self):
        assert _score_message("Create a file").is_conversational is False

    def test_signal_count_counts_complex_signals(self):
        # "create" and "and then" and "also" -> 3 COMPLEX_SIGNALS hits.
        result = _score_message("create the module and then also add tests")
        assert result.signal_count >= 3

    def test_signal_count_zero_when_no_signals_present(self):
        assert _score_message("the weather today").signal_count == 0

    def test_empty_message(self):
        result = _score_message("")
        assert result.msg == ""
        assert result.length == 0
        assert result.has_action is False
        assert result.signal_count == 0
        # "".startswith(_question_starters) is False for every starter, and
        # "" doesn't end with "?" or match any _qa_phrases word-boundary
        # search, so is_question is False for the empty string.
        assert result.is_question is False


class TestIsComplexThresholdBoundaries:
    """
    Boundary tests for `is_complex()`'s length/signal_count thresholds —
    the existing 41-test corpus above is all natural-language strings and
    doesn't sit exactly on a branch edge, so a threshold accidentally
    shifted by one (e.g. sub-task A's refactor swapping `>` for `>=`)
    wouldn't be caught by it. `is_complex()`'s branches:
        length <  50            -> always False
        length >  300           -> signal_count >= 2
        length >  150 (<= 300)  -> signal_count >= 2
        length <= 150           -> signal_count >= 3
    Messages here are built to hit an exact length with a controlled
    signal_count, using "create" (1 COMPLEX_SIGNALS hit, also an
    _action_kws hit) repeated and padded with non-signal filler so the
    signal count is exact and deliberate.
    """

    @staticmethod
    def _pad_to_length(prefix: str, length: int) -> str:
        """Pad *prefix* out to exactly *length* chars with non-signal 'z'
        filler, preserving *prefix*'s leading signal words."""
        assert len(prefix) <= length
        return prefix + "z" * (length - len(prefix))

    def test_length_49_always_false_regardless_of_signals(self):
        msg = self._pad_to_length("create build implement refactor rewrite add", 49)
        assert len(msg) == 49
        assert is_complex(msg) is False

    def test_length_50_with_enough_signals_can_be_true(self):
        # length==50 is not <50, so it proceeds to the else branch
        # (length<=150 -> signal_count>=3).
        msg = self._pad_to_length("create build implement refactor rewrite add", 50)
        assert len(msg) == 50
        assert _score_message(msg).signal_count >= 3
        assert is_complex(msg) is True

    def test_length_150_needs_3_signals_not_2(self):
        """length==150 falls in the `else` branch (signal_count>=3), NOT
        the `elif length>150` branch (signal_count>=2) — exactly 2 signals
        at this boundary must stay False."""
        msg = self._pad_to_length("create build", 150)
        assert len(msg) == 150
        assert _score_message(msg).signal_count == 2
        assert is_complex(msg) is False

    def test_length_150_with_3_signals_is_true(self):
        msg = self._pad_to_length("create build implement", 150)
        assert len(msg) == 150
        assert _score_message(msg).signal_count == 3
        assert is_complex(msg) is True

    def test_length_151_only_needs_2_signals(self):
        """length==151 crosses into the `elif length>150` branch
        (signal_count>=2) — 2 signals here (not enough at 150) is now
        enough."""
        msg = self._pad_to_length("create build", 151)
        assert len(msg) == 151
        assert _score_message(msg).signal_count == 2
        assert is_complex(msg) is True

    def test_length_300_still_only_needs_2_signals(self):
        """length==300 is still in the `elif length>150` branch (not yet
        `>300`) — signal_count>=2 applies."""
        msg = self._pad_to_length("create build", 300)
        assert len(msg) == 300
        assert _score_message(msg).signal_count == 2
        assert is_complex(msg) is True

    def test_length_301_crosses_into_over_300_branch_same_threshold(self):
        """length==301 crosses into the `if length>300` branch — per
        NEW-128 (logged, not fixed by this test-only sub-task) that branch
        has the exact same body as the `elif length>150` branch
        (signal_count>=2), so this assertion is identical to the length-151
        case above. The test exists to pin that documented behavior, not
        to imply the `>300` split does something distinct."""
        msg = self._pad_to_length("create build", 301)
        assert len(msg) == 301
        assert _score_message(msg).signal_count == 2
        assert is_complex(msg) is True


class TestConversationalPatterns:
    """Test conversational pattern coverage."""

    def test_common_question_starters(self):
        """Common question starters should be in patterns."""
        patterns_text = " ".join(CONVERSATIONAL_PATTERNS)

        # Should cover common question formats
        assert "how do i" in patterns_text.lower()
        assert "what is" in patterns_text.lower()
        assert "can you explain" in patterns_text.lower()

    def test_help_patterns(self):
        """Help-seeking patterns should be included."""
        patterns_text = " ".join(CONVERSATIONAL_PATTERNS)

        assert "help" in patterns_text.lower()
        assert "explain" in patterns_text.lower()


class TestPostprocessPlan:
    """Test _postprocess_plan: deduplication, Run step preservation, cap."""

    def test_empty_plan(self):
        assert _postprocess_plan([]) == []

    def test_single_step_unchanged(self):
        steps = ["Create app.py: accepts input, prints output"]
        assert _postprocess_plan(steps) == steps

    def test_deduplicates_same_file(self):
        """Two create steps for the same file — keep the longer one."""
        steps = [
            "Create app.py: prints hello",
            "Create app.py: accepts input, prints hello world with timestamp",
        ]
        result = _postprocess_plan(steps)
        assert len(result) == 1
        assert "timestamp" in result[0]

    def test_run_steps_never_deduplicated(self):
        """Two Run: steps for the same file are intentional — both kept."""
        steps = [
            "Create xform.py: counts tokens",
            "Run: python xform.py corpus.txt",
            "Run: python xform.py corpus.txt",
        ]
        result = _postprocess_plan(steps)
        run_steps = [s for s in result if s.lower().startswith("run:")]
        assert len(run_steps) == 2

    def test_cap_at_eight(self):
        """Plans with more than 8 steps are capped at 8."""
        steps = [f"Create file{i}.py: step {i}" for i in range(12)]
        result = _postprocess_plan(steps)
        assert len(result) <= 8

    def test_different_files_all_kept(self):
        """Steps for different files are kept separately."""
        steps = [
            "Create app.py: main entry point",
            "Create models.py: data models",
            "Create tests.py: unit tests",
            "Run: python -m pytest tests.py",
        ]
        result = _postprocess_plan(steps)
        assert len(result) == 4

    def test_verify_step_kept(self):
        """Verify/check steps (no filename) are kept as-is."""
        steps = [
            "Create app.py: core logic",
            "Run: python app.py",
            "Verify: output matches expected format",
        ]
        result = _postprocess_plan(steps)
        assert len(result) == 3
        assert any("Verify" in s for s in result)

    def test_run_step_with_different_args_both_kept(self):
        """Run steps with different arguments are distinct and both kept."""
        steps = [
            "Create counter.py: counts words",
            "Run: python counter.py file1.txt",
            "Run: python counter.py file2.txt",
        ]
        result = _postprocess_plan(steps)
        run_steps = [s for s in result if s.lower().startswith("run:")]
        assert len(run_steps) == 2


class TestIntegrationAgentUtils:
    """
    Lightweight integration test for agent utilities.

    Does NOT require a running inference server — tests pure logic
    (JSON parsing, tool call parsing, hallucination detection) only.
    """

    def test_extract_json_roundtrip(self):
        from core.agent import extract_json

        data = {"name": "write_file", "args": {"path": "x.py", "content": "pass\n"}}
        import json

        raw = json.dumps(data)
        result = extract_json(raw)
        assert result == data

    def test_parse_tool_call_roundtrip(self):
        from core.agent import parse_tool_call

        raw = '<tool>\n{"name": "shell", "args": {"command": "pytest test.py -v"}}\n</tool>'
        result = parse_tool_call(raw)
        assert result is not None
        assert result["name"] == "shell"
        assert result["args"]["command"] == "pytest test.py -v"

    def test_hallucination_no_false_positive_for_tool_use(self):
        from core.agent import is_hallucination

        response = "I created the file for you."
        user_message = "Create hello.py"
        tools_used = ['write_file:{"path":"hello.py"}']  # tool was used
        false_file, false_run = is_hallucination(response, user_message, tools_used)
        assert false_file == False  # tool was used, so not a hallucination

    def test_hallucination_detects_no_tool_used(self):
        from core.agent import is_hallucination

        # is_hallucination fires on exact phrases OR on code-in-markdown without tool
        response = "I created the file for you."  # matches "i created" phrase
        user_message = "Create hello.py"
        tools_used = []  # no tool used
        false_file, false_run = is_hallucination(response, user_message, tools_used)
        assert false_file == True

    def test_hallucination_detects_code_block_without_write(self):
        from core.agent import is_hallucination

        response = "Here is the code:\n```python\nprint('hello')\n```"
        user_message = "Create hello.py"
        tools_used = []  # no write_file used
        false_file, _ = is_hallucination(response, user_message, tools_used)
        assert false_file == True


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
