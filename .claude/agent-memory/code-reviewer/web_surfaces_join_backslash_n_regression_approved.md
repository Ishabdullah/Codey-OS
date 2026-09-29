---
name: web-surfaces-join-backslash-n-regression-approved
description: 2026-09-11 incident — .join('\n') in a non-raw triple-quoted Python string became a real newline in JS output, breaking the whole admin dashboard script block; fix + new node --check regression test, approved
metadata:
  type: project
---

Incident: `restoricon_core/api/web_surfaces.py` (two sites, render_admin_surface,
~lines 4091/4531) had `.join('\n')` written inside JS embedded in a non-raw
Python triple-quoted string. Python's string parser consumed `\n` as an
actual newline character before it ever reached the JS output, landing a
raw newline inside a single-quoted JS string — invalid JS syntax. One
syntax error anywhere in a `<script>` block kills the *entire* script, so
this broke every button/data-load on the live admin page, not just the
delete-confirmation feature that introduced it.

Fix: `.join('\n')` → `.join('\\n')` (2-line diff, confirmed via `git diff
--stat`: 2 insertions/2 deletions). Correctly scoped — did not convert the
whole multi-thousand-line literal to a raw string, which would have been
much riskier.

Verification performed and independently reconfirmed by reviewer:
- Grepped whole file for `.join('` sibling patterns — no other bare-`\n`
  sites found (only the 2 fixed + many `.join('')` empty-string joins,
  which are fine).
- New test file `tests/test_restoricon_core/test_web_surfaces_js_syntax.py`
  extracts every `<script>` block from all 8 `render_*_surface()` functions
  (verified complete via `grep '^def render_'` — exactly 8, matches
  SURFACES dict) and runs `node --check` on each; plus one pinned
  regression test asserting `).join('\\n')` (not a raw newline) appears in
  admin surface HTML.
- **Negative control run live by reviewer** (not just implementer's claim):
  `git stash push -- restoricon_core/api/web_surfaces.py` (reverting only
  the fix file), reran the new test file — both
  `test_rendered_surface_script_is_valid_js[render_admin_surface]` and
  `test_admin_surface_join_backslash_n_regression` failed with the exact
  `node --check` SyntaxError from the incident (`Invalid or unexpected
  token` at the newline-broken line). `git stash pop` restored the fix.
- Full `pytest tests/test_restoricon_core/` = 585 passed (576 prior
  baseline + 9 new), matching the claim exactly.

Approved as-is. One process note, not a fix blocker: working tree at
review time carried unrelated unstaged/untracked files (this reviewer's
own memory-file writes, stray sqlite `file:test_doc_upload_*` temp
artifacts) — implementer should stage only
`restoricon_core/api/web_surfaces.py` and
`tests/test_restoricon_core/test_web_surfaces_js_syntax.py` explicitly
(not `git add -A`), consistent with [[working_tree_cross_round_bleed]].

**New bug-class lesson for future reviews of this repo:** JS-in-Python
triple-quoted (non-raw) string literals are a real injection point for
this exact mistake — any `\n`, `\t`, `\\`, or similar JS escape sequence
written directly (not double-backslashed) inside such a literal will be
silently consumed by Python's own parser before the JS ever sees it. When
reviewing diffs that touch `render_*_surface()` functions or any other
Python-string-embedded JS/HTML, grep for single-backslash escape
sequences (`\n`, `\t`, `\r`, `\0`) inside single/double-quoted JS string
literals specifically — backtick (template literal) JS strings are less
of a risk since real newlines are valid there, but single/double-quoted
JS strings are not. This test file
(`test_web_surfaces_js_syntax.py`) is now a standing regression guard —
confirm it still exists and passes on any future diff touching this file.
