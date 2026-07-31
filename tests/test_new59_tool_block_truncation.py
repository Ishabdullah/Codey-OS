"""
NEW-59 regression test: a real patch_file tool call's <tool>{...}</tool>
JSON (old_str/new_str embedding verbatim file excerpts) can easily exceed a
plain char-count truncation cap, and a raw `text[:limit]` slice can land
mid-JSON, making a legitimately correct, complete tool call look
syntactically broken to the critique/refine model. This guards
prompts.layered_prompt._safe_truncate_draft(), the single truncation point
that replaced the old double-truncation (core/recursive.py's `draft[:2000]`
stacked on layered_prompt.py's `prior_draft[:1500]`).

Also guards the specific, non-obvious data shape this bug actually occurs
on: core/recursive.py's draft infer() call stops on "</tool>" (the default
extra_stop), and llama.cpp elides the stop string from returned text — so a
real draft containing a tool call routinely has NO closing "</tool>" tag at
all. core/agent.py's own parse_tool_call() confirms this (it matches
`<tool>\\s*(\\{.*)` with no closing-tag requirement). A truncation helper
that only recognizes a *terminated* <tool>...</tool> block would silently
miss this common case and fall through to the naive cut it exists to avoid.

See NEW_ISSUES.md NEW-59 for the finding this fixes.
"""
from prompts.layered_prompt import _safe_truncate_draft


def _tool_json(old_str_len=3000, terminated=True):
    body = (
        '<tool>\n{"name": "patch_file", "args": {"path": "x.py", '
        '"old_str": "' + ("A" * old_str_len) + '", "new_str": "B"}}'
    )
    if terminated:
        body += "\n</tool>"
    return body


def test_terminated_tool_block_preserved_whole_when_it_alone_exceeds_limit():
    tool_json = _tool_json(terminated=True)
    text = "reasoning " * 50 + tool_json + " trailing prose " * 20
    out = _safe_truncate_draft(text, 1500)
    assert tool_json in out
    assert out.count("<tool>") == 1
    assert out.count("</tool>") == 1


def test_unterminated_tool_block_preserved_whole_when_it_alone_exceeds_limit():
    # The realistic case: no closing </tool> tag (elided stop sequence).
    tool_json = _tool_json(terminated=False)
    text = "reasoning " * 50 + tool_json
    out = _safe_truncate_draft(text, 1500)
    assert tool_json in out
    assert out.endswith(tool_json)


def test_no_tool_block_falls_back_to_plain_char_truncation():
    text = "x" * 3000
    out = _safe_truncate_draft(text, 1500)
    assert out.startswith("x" * 1500)
    assert len(out) < len(text)


def test_tool_block_larger_than_limit_returned_intact_not_split():
    tool_json = _tool_json(old_str_len=5000, terminated=False)
    out = _safe_truncate_draft(tool_json, 100)
    assert out == tool_json


def test_short_text_under_limit_returned_unchanged():
    text = "short draft, no truncation needed"
    assert _safe_truncate_draft(text, 1500) == text
