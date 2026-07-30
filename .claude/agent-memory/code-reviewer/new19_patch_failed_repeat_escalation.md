---
name: new19-patch-failed-repeat-escalation
description: core/agent.py NEW-19 (repeated [PATCH_FAILED] escalation) — approved with two logged non-blocking gaps
metadata:
  type: project
---

Reviewed 2026-07-30. `core/agent.py`'s new `patch_failed_counts` tracking +
peer-CLI escalation on repeated same-path `[PATCH_FAILED]` (old_str-not-found)
matched the exact decision Ish recorded in `WORK_QUEUE.md`. Verified live:
- `patch_failed_counts` initialized once per `run_agent()` call, before the
  `while step < max_steps` loop — correctly per-turn scoped, not leaking.
- `fpath_touched = args.get("path", "")` can't collide/empty-key for
  `patch_file` since `TOOLS["patch_file"]` dispatch requires `args["path"]`
  to exist (KeyError otherwise) — no silent single-key collision risk.
- `is_error()` never matches a string starting with `[PATCH_FAILED]` (only
  `[ERROR]` prefix, or shell-specific signals gated on `tool_name=="shell"`),
  so the new `elif _patch_failed_repeat` branches are provably mutually
  exclusive with the pre-existing `is_error()`-gated branches — no double-
  escalation, no marker collision with NEW-2's `[EDIT NOT APPLIED]`.
- Local `from core.peer_cli import escalate` inside the branch body means
  `monkeypatch.setattr("core.peer_cli.escalate", ...)` in tests really
  intercepts the live call site (not mock theater) — verified by running
  the 5 new tests for real (`pytest tests/test_new19_*.py -v`, all passed)
  and the full suite (263 passed, matches implementer's claim verbatim).

Two gaps surfaced by advisor and confirmed real, logged to NEW_ISSUES
rather than blocking (matches the CLAUDE.md rule 8 pattern — out-of-scope
findings get logged, not silently fixed or dropped):
1. **Verbatim-duplicate blind spot.** The pre-existing `duplicate_count`
   guard (`core/agent.py` ~line 1645-1667, untouched by this diff) fires
   BEFORE `execute_tool()` runs on a byte-identical repeated tool call
   (same name+args JSON). On the 2nd identical repeat it returns early
   with a "Done. <stale last_tool_result>" summary — misrepresenting a
   still-failed `[PATCH_FAILED]` result as success — and NEW-19's new
   counting/escalation logic never even executes, since `execute_tool()`
   is never re-invoked for that path. NEW-19's escalation only fires when
   the model varies its `old_str` between attempts (which is the
   documented expected remediation per the `[PATCH_FAILED]` message
   itself), not when it blindly resends the same broken call — a likely
   more common LLM failure mode. Pre-existing bug, not introduced by this
   diff, but it materially limits the new fix's real-world reach.
2. **error_log content now flows into `detect_task_type()`'s keyword
   matching.** `error_log.append(last_tool_result[:300])` for
   `[PATCH_FAILED]` results injects up to 300 chars of arbitrary file
   content (the `[PATCH_FAILED]` message embeds current file content) into
   a list previously reserved for `is_error()`-matched error text only.
   `peer_cli.py`'s `detect_task_type()` joins `errors` and keyword-matches
   as a fallback (after user_message checks) — worst case is a suboptimal
   peer-CLI selection, not a safety issue (matching is bounded/truncated,
   and `build_prompt()` also truncates to last-3/300-chars each). Also:
   `build_prompt()`'s fixed wording "exhausted its retry budget" is
   technically false for the `[PATCH_FAILED]`-repeat case (retries were
   never entered) — inherited as-is from reusing the shared `escalate()`
   path, which was the explicit, recorded design choice.

**Verdict: APPROVED.** Core logic (scoping, key population, elif exclusivity,
marker distinction, test fidelity) all verified correct and non-regressing.
The two gaps above are Warning/Suggestion-level, not Critical — recommend
implementer log them to `NEW_ISSUES.md` per rule 8 rather than silently
fixing, since both are adjacent-but-outside this task's exact scope.

See also [[new2_edit_not_applied_approved]] for the marker precedent this
extends, and [[new16_show_patch_write_error_display_approved]] for the
`[PATCH_FAILED]` display-only precedent this design question originated from.
