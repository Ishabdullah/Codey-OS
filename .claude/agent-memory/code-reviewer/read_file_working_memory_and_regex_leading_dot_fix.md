---
name: read-file-working-memory-and-regex-leading-dot-fix
description: agent.py read_file->WorkingMemory registration fix + context.py detect_filenames leading-dot regex fix — APPROVED with one Warning
metadata:
  type: project
---

Reviewed uncommitted (working-tree, not staged) changes to `core/agent.py`
(read_file branch ~line 1715), `core/context.py` (`detect_filenames()` ~line
189), and an append-only `NEW-63` entry in `NEW_ISSUES.md`. Verdict:
**approved, with one non-blocking Warning.**

**Fix A (agent.py):** `not last_tool_result.startswith("[ERROR]")` as a gate
for registering read_file content into `core.memory_v2`'s WorkingMemory. This
looked risky at first glance — the codebase has a dedicated `is_error()` for
exactly this kind of gate, and a raw `startswith("[ERROR]")` check is only as
good as the *dispatch* layer between the tool function and `last_tool_result`,
not just the tool function itself. Traced `execute_tool()` (agent.py:368) end
to end: for `name == "read_file"`, it's a clean passthrough —
`result = TOOLS[name](args)` with no wrapping, no linter/log paths (those only
fire for `_is_write`/`_is_patch`/`shell`), and the only other path back to the
caller is the outer `except Exception as e: return "[ERROR] " + str(e)`. Every
failure `tool_read_file` can produce (`FilesystemAccessError`, invalid-path
checks) is also `[ERROR]`-prefixed. So the gate is correct as written — but
**always verify this by reading `execute_tool`'s actual body for the tool in
question, not just the `TOOLS[name]` registration** — grepping only the
tool-function definition without confirming what the dispatcher does to its
return value is not sufficient.

Warning (not blocking): `_wcontent` in the sibling `write_file`/`patch_file`
branch is model-generated (small, bounded by generation length); the new
`read_file` branch registers content up to `Filesystem.read`'s
`MAX_FILE_SIZE = 10MB` — ~1000x larger. `WorkingMemory._evict_by_tokens` skips
files touched in the current turn and `break`s when no evictable candidates
remain, so a single large read this turn can push total tokens over budget
while evicting *other*, more useful (e.g. `.py`) files that were touched
earlier. Given CLAUDE.md rule 2's documented RAM-crash history, a large read
also now persists in RAM across turns instead of being transient. Suggested
fix (not required for this round): size-cap `_mem.load_file()` registration
for `read_file` (skip or truncate above some KB threshold) — logged as
worth a NEW_ISSUES.md entry if not already tracked.

**Fix B (context.py):** widening `detect_filenames()`'s regex to allow a
leading dot per path segment (`.config/settings.json`) and reordering
`json` before `js` in the extension alternation (fixes a real, independent,
pre-existing prefix-shadow bug: `js` matched before `json` could, truncating
`.json` files to `.js`). Verified independently via `re.findall()` for: dot-
prefixed paths, plain filenames, punctuation-adjacent filenames, absolute
paths, `../` relative paths, filename-free sentences, and a full extension
list shadow-check (`json`/`js`, `css`/`cpp`/`c`, `html`/`h` — all correctly
ordered longer-before-shorter already). No catastrophic-backtracking risk
(`(?:\.?[\w\-]+/)*` timed at ~2ms against a 3000-segment adversarial input).

Checked one thing the task didn't explicitly ask but that mattered: the
widened regex now matches inside hidden directories like `.config/`,
`.docker/`, `.claude/` — exactly where secrets tend to live. Traced the
actual consumer, `auto_load_from_prompt()` (context.py:229), which calls
module-level `load_file()` (context.py:82), which calls `is_ignored()`
*before* reading — `.env`, `*.pem`, `*.key`, `.git` etc. are still blocked
via `_DEFAULT_IGNORE`/`.codeyignore`. So the widened regex does not newly
leak credential files through this path. Always trace the regex's actual
consumer, not just the regex in isolation, when a match-set changes.

`NEW-63`'s claim that old and new patterns "fail identically" on
`/data/data/com.termux/...` was independently re-verified via `re.findall()`
— technically the two truncated outputs differ (`termux/...` vs
`.termux/...`, since NEW-62's fix now also captures the leading dot on that
inner segment) but both are equally wrong/non-existent, so "not a
regression" holds. The doc phrasing "truncate ... to the same" is a very
minor imprecision, not worth blocking on.

`NEW_ISSUES.md` diff confirmed genuinely append-only via `git diff | grep
"^-"` returning only the `--- a/NEW_ISSUES.md` header line.

Test suite: `python3 -m pytest tests/ -q` → `271 passed in 0.97s` (verbatim,
reproduced directly, matches implementer's claim).
