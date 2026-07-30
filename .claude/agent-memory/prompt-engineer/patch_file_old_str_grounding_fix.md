---
name: patch-file-old-str-grounding-fix
description: NEW-7's root-cause prompt fix (patch_file old_str verbatim-substring rule) — what was added, where, and what's still open
metadata:
  type: project
---

NEW-7 (Codey-OS `NEW_ISSUES.md`) characterized a 67% failure rate on
docstring-insertion-style edit prompts: the local 7B model (Qwen2.5-Coder-7B,
port 8080) either emits `old_str: ""` or a hallucinated `old_str` (e.g.
assuming a real ~15-line function is a one-line `pass` stub) instead of a
real verbatim substring of the target file. Round 14/20 of that
investigation confirmed the root gap: `prompts/system_prompt.py` had no
instruction that `old_str` must be a verbatim substring, and no warning
against an empty `old_str`.

**Fix applied (this round, not yet committed as of writing):**
- `prompts/system_prompt.py` — added a `PATCH_FILE — old_str MUST BE REAL
  FILE CONTENT, NEVER A GUESS` section (after the `AVAILABLE TOOLS` examples,
  before the `RULES:` block) with: old_str-can't-be-empty rule + tool's real
  rejection behavior, a "read_file first if you haven't seen the file yet"
  rule, and 2 wrong / 1 correct `<tool>` JSON examples using `main.py`'s real
  `shutdown()` function (verified unique via `grep -c "def shutdown():"
  main.py` = 1, so the example is actually applicable, not just illustrative).
- `prompts/critique_prompts.py`'s `CRITIQUE_CODE` — added item 8: flag an
  empty `old_str` and rate below 5/10. This only catches the empty-`old_str`
  variant (this project's Round 14 draws a2/b1) — the hallucinated-stub
  variant (a1/b2) is structurally uncatchable by critique because
  `_build_critique_prompt()` (`prompts/layered_prompt.py`) never gives the
  critique model real file ground truth (a pre-existing, separately-logged
  structural gap, not something this fix touches).
- `core/plannd.py`'s `PLANNER_PROMPT` was deliberately left unchanged — it
  only emits step-description prose ("Edit `<file>`: add a docstring to
  ..."), never constructs `old_str`/`new_str` itself, so it isn't part of
  this failure's causal chain.

**Verified before handoff (deterministic, no model load):**
- Each new `<tool>` JSON example round-trips through `json.loads()`
  correctly (see [[escaping-json-examples-in-prompt-strings]] for the escaping
  gotcha this surfaced).
- Confirmed via `git stash` diff-test that the new, longer identity block
  does NOT newly evict the "Loaded Files" background layer in
  `layered_prompt.py`'s draft-phase budget — `main.py` (68KB) was already
  excluded from that layer before this change too (it's far larger than the
  whole 20000-char budget). The `read_file`-first instruction added by this
  fix routes around that layer anyway, since `read_file`'s tool result goes
  directly into conversation history, not through the budget-gated
  `_build_draft_prompt()` layer.

**Still open — explicitly NOT done by this fix:** live confirmation that the
prompt change actually changes the 7B model's behavior. This needs a
live-verifier pass re-running the docstring-insertion prompt
("Add a docstring to the shutdown function in main.py.") against real
`main.py`, both recursive and plain paths (`CODEY_RECURSIVE` unset vs. `=0`),
≥6 draws with `/clear` between draws, compared against the pre-fix 4/6 (67%)
failure baseline. Must include an explicit `y` answer for the `Apply patch?`
confirm in any piped/non-interactive input (a prior round's harness gap —
see NEW-43 addendum), and must watch for `core/agent.py`'s
verbatim-duplicate-tool-call guard short-circuiting a turn into a false
"Done." before any `patch_file` call is even attempted (documented as firing
on `read_file` too, not just `patch_file`, in NEW-7's Round 20 addendum to
that guard's own issue entry).
