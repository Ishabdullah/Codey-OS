---
name: new15-write-file-syntax-guard-approved
description: NEW-15 tool_write_file() syntax guardrail + patch_tools wording fix — APPROVED, live-verified with direct script (not just unit test)
metadata:
  type: project
---

NEW-15 fix (tools/file_tools.py, tools/patch_tools.py) approved after live behavioral
verification, not just static reading. Root problem: `[PATCH_FAILED]` message nudged the
model toward `write_file` whole-file reconstruction while `core/agent.py` truncates the
tool result the model sees, causing corrupted reconstructions placed in wrong locations.

Fix: `tool_write_file()` gained a syntax-check guard (via `core.linter.check_syntax`,
which is `ast.parse`-based, returns `None` on valid syntax / error string on invalid —
confirmed by reading `core/linter.py`), gated on `file_exists and p.suffix == ".py"`,
placed as an independent block *after* the existing 20%-size-shrink guard (both blocks
return early, so they're independent, not mutually exclusive — order matters only in
which message the model sees first if both would trigger).

Key thing worth re-deriving each time rather than trusting the implementer's claim: the
"fail-open matches patch_file's existing behavior" claim. Verified directly —
`tools/patch_tools.py` lines ~78-90 has an identical `except Exception: pass` fail-open
around its own `check_syntax` call. This confirms the new code copies an *already
accepted* pattern rather than introducing a new weaker posture.

Live-verified with a throwaway script (not just trusting the diff or unit tests):
1. Existing .py file + broken-syntax overwrite of similar size → blocked with
   `[ERROR] Refusing to overwrite ... syntax error`.
2. Same file + valid-syntax overwrite of similar size → succeeds.
3. Brand-new .py file (file_exists=False) with broken syntax → NOT blocked (guard
   correctly scoped to overwrites of existing files only).
4. Simulated `ImportError` on `core.linter` via `builtins.__import__` monkeypatch →
   write proceeds (fail-open confirmed empirically, not just by reading the except block).

Caveat noted, not blocking: no unit test in `tests/` exercises `tool_write_file`'s new
syntax path (existing `tests/test_patch.py` only touches `.txt` files and is unaffected
by the `[PATCH_FAILED]` wording change, confirmed by grep). Logged as a Suggestion, not
Critical, since I live-verified the behavior directly.

**Why this pattern matters:** this project's past bugs (blanket pkill, self-referential
PID race) came from safety guardrails whose fail-open/fail-closed direction wasn't
scrutinized against precedent. Always find and diff the *existing* analogous guard
(here: patch_tools's own syntax check) rather than accepting "matches existing behavior"
as an unverified claim.

**How to apply:** for any future guardrail-consistency claim ("matches X's existing
behavior"), locate X in the diff/codebase and read it side-by-side before accepting the
claim.
