---
name: escaping-json-examples-in-prompt-strings
description: how to embed literal \n / \" inside JSON tool-call examples that live in non-raw triple-quoted Python prompt strings (system_prompt.py, PLANNER_PROMPT, etc.)
metadata:
  type: feedback
---

When adding a `<tool>{"name": ..., "old_str": "...\n...", ...}</tool>` example
into `_SYSTEM_PROMPT_BODY` (or any other prompt body defined as a normal,
non-raw `"""..."""` Python string), a single backslash (`\n`, `\"`) in the
source is consumed by Python's own string-literal parser at import time and
turns into a real newline / bare quote in the runtime string — which silently
breaks the single-line JSON example (multi-line JSON, or invalid JSON from
unescaped `"""`) with no `SyntaxError` to catch it.

To get the literal two-character sequences `\n` / `\"` in the final prompt
text shown to the model, write `\\n` / `\\"` in the Python source (double
backslash). This is *not* optional stylistic escaping — it's required
whenever a prompt example's JSON string value needs to represent a
multi-line file edit or an embedded quote (e.g. a Python docstring's `"""`
inside `new_str`).

**Why:** found and fixed during [[patch-file-old-str-grounding-fix]] (NEW-7).
The first draft of the `patch_file` old_str-grounding fix used single
backslashes and produced literal multi-line/broken-JSON examples in the
actual prompt text — verified via `od -c` on the raw source line (single `\`
before `n`) and by importing `get_system_prompt()` and observing real
newlines / unescaped `"""` in the output.

**How to apply:** any time a prompt-engineering change adds or edits a
`<tool>{...}</tool>` JSON example containing `\n` or an embedded `"` inside a
Python prompt-string literal, verify with a source-level check
(`sed -n '<line>p' file.py | od -c`) AND a runtime check
(`python3 -c "from ...prompts... import get_...; print(...)"` plus
`json.loads()` on each extracted example line) before considering the edit
done. A prompt file that merely "reads fine" as Python source is not
sufficient verification — the escape-consumption bug produces no import-time
error.
