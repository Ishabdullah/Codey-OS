---
name: new16-show-patch-write-error-display-approved
description: NEW-16 core/agent.py + core/display.py error= threading for show_patch/show_file_write — APPROVED
metadata:
  type: project
---

NEW-16 fix threads `error=` through `show_patch()`/`show_file_write()` (core/display.py)
so failed patches/writes render a red "PATCH FAILED"/"WRITE FAILED" panel instead of a
success-colored one. Call site in core/agent.py's `execute_tool()` computes `_is_err` via
`is_error(result, name)`, with an extra inline `result.startswith("[PATCH_FAILED]")` check
added ONLY at the `show_patch()` call site (not `show_file_write()`), because
`tools/patch_tools.py`'s `[PATCH_FAILED]` prefix (old_str-not-found path, line ~49) is
deliberately excluded from the shared `is_error()` so it bypasses retry/escalation and
instead returns full file content to the model.

Verified this round:
- `is_error()` (core/agent.py:492) and all 4 retry/escalation call sites (~1706, 1712,
  1773, 1854) are byte-for-byte untouched — diff only touches lines 407-421.
- `[PATCH_FAILED]` appears at exactly one return site in patch_tools.py (line 49), literally
  at index 0, no leading whitespace — the `.startswith()` check is valid against the real
  string. The ambiguous-match (`count > 1`) failure path returns `[ERROR]`-prefixed (line 60),
  already caught by base `is_error()` — no second special-case needed.
- `core/agent.py` is the sole caller of both display functions (repo-wide grep) — signature
  changes with defaults are safe.
- The `isinstance(result, str)` guard before `.startswith()` is NOT just cosmetic: this whole
  block sits inside `try: ... except Exception: pass` (agent.py:408-431). Without the guard,
  a non-str `result` would raise AttributeError, get swallowed by the bare except, and
  **skip the display panel entirely** for that turn — worse than a wrong color. Confirmed by
  reading the surrounding try/except directly.
- `error=False` branches in display.py reproduce the exact pre-diff title strings/border
  colors ("Editing"/"Creating"/"Patching", yellow/green/yellow) — happy path unchanged.
- Ran `python -m pytest -q`: 325 passed, 1 pre-existing unrelated failure
  (`ccos/tests/test_ccos.py::test_sandbox`, a sandbox-path-allowlist issue) — confirmed
  pre-existing by stashing the diff and re-running the same test in isolation (same failure
  with diff stashed out).
- Manually exercised the exact `_is_err` boolean expressions from both call sites against
  5 representative result strings (old_str-absent, ambiguous-match, successful-patch,
  write-error, successful-write) — all 5 matched expected error/non-error classification.

Verdict: APPROVED. No live-verifier session needed for this class of change (pure display/
trust-signal logic, no process lifecycle, no daemon, no GUI binding/auth) — direct
`execute_tool()`-level + is_error()-level verification is sufficient. Only a Suggestion:
no dedicated unit test exists for `show_patch`/`show_file_write` error-path titles/colors;
future regression here would only surface via visual inspection or grep of retry-site
behavior, not a red pytest failure.
