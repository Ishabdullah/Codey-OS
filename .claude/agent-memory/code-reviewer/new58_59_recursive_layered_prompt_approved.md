---
name: new58-59-recursive-layered-prompt-approved
description: NEW-58 (refine draft-blindness) / NEW-59 (critique double-truncation) fix in core/recursive.py + prompts/layered_prompt.py — approved with 2 logged warnings
metadata:
  type: project
---

Reviewed core/recursive.py + prompts/layered_prompt.py NEW-58/59 fix (removed
draft[:2000]/prior_draft[:1500] double-truncation, added tool-block-aware
_safe_truncate_draft(), threaded prior_draft into refine). Verified: parse_tool_call's
no-closing-tag tolerance is real (core/agent.py:319, :1490), 8000-char critique
budget and CRITIQUE_CODE (1164 chars) claims check out, LayeredPrompt.build()
never evicts required layers, 5/5 new tests + 339/339 full suite pass (live output).

Two Warnings logged, not blocking:
1. Making refine's new prior_draft layer `required=True` (up to 4000 chars) inside
   a fixed 20000-char budget, stacked on SYSTEM_PROMPT (measured 12942 chars) +
   required critique (800), leaves only ~2258 chars for repo_map/retrieval(NEED_DOCS)/
   files/symbolic_graph combined — down from ~6258 before this diff. NEED_DOCS
   retrieved_context (refine's own reason for existing) can now get silently
   evicted where it previously fit. Check this arithmetic again (measure
   get_system_prompt() length fresh) if refine's layer set changes again.
2. _extract_tool_name() (logging-only attribution helper) only matches
   `<tool>{...}</tool>`, missing parse_tool_call's other two paths
   (ROGUE_TAG_MAP tags, block-style `<write_file path="...">`) — so a turn that
   actually executes a rogue-tag tool call will misleadingly log tool=none.
   Relevant if this round's live-verifier reports confusing attribution lines.

General lesson: when a fix adds a new `required=True` layer to an existing
LayeredPrompt budget, always recompute headroom against the *other* non-required
layers in that same prompt (not just confirm identity/system-prompt survives) —
the squeeze lands on the layer with the lowest priority number among the
non-required ones, which may be exactly the content the fix's own feature needs.
