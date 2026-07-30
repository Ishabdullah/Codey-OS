---
name: sandbox_new8_gettempdir_fix_approved
description: NEW-8 fix in ccos/core/sandbox.py (ALLOWED_DIRS "/tmp" -> tempfile.gettempdir()) — APPROVED, plus two new latent bugs found in the same file during review
metadata:
  type: project
---

Reviewed and approved the NEW-8 fix: `ccos/core/sandbox.py`'s `ALLOWED_DIRS`
hardcoded `"/tmp"`, but `Sandbox.__init__` creates its working dir via
`tempfile.mkdtemp(prefix="ccos_sandbox_")` (no `dir=`), which resolves
against `tempfile.gettempdir()` — `/data/data/com.termux/files/usr/tmp` on
this Termux device, not `/tmp`. Every sandboxed command failed its own
allowlist check before running. Fix: hardcoded string replaced with a
`tempfile.gettempdir()` call. Diff was a genuinely minimal 1-line-changed,
comment-added change to `ALLOWED_DIRS` only.

**Why this was a clean approve:**
- Empirically confirmed `tempfile.mkdtemp(dir=None)`'s parent dir equals
  `tempfile.gettempdir()` in this environment (not just by reading docs).
- `test_sandbox` (`ccos/tests/test_ccos.py:92`) has a real
  `assert result.success` on `echo hello` — the `PytestReturnNotNoneWarning`
  about its trailing `return True` is cosmetic, not a false-pass risk. Always
  check the test body directly rather than trusting "N passed" when a
  ReturnNotNone warning is present — it can (in other repos) mask a test that
  never asserts. Here it didn't.
- Grepped all `Sandbox(` call sites; the only one passing an explicit
  `allowed_dirs=` (`ccos/tests/test_improvement_loop.py:193`) *extends*
  `ALLOWED_DIRS` rather than replacing it, so it inherits the new
  `gettempdir()` entry — no partial-fix gap in practice.
- Security tradeoff is a non-issue: `_validate_path` only gates `cwd`, not
  what `shell=True` commands can touch elsewhere — see [[sandbox_no_containment_new25]].
  Widening from `/tmp` to `gettempdir()` cannot regress this, and on Termux
  the new path is app-private (narrower than shared `/tmp` on stock Linux).

**Two new bugs found and logged to NEW_ISSUES.md (NEW-24, NEW-25), not
blocking this fix, both pre-existing/out-of-scope:**
- NEW-24: `Sandbox.cleanup()` calls `shutil.rmtree()` but the module never
  `import shutil`s — every `cleanup()` call raises `NameError`, silently
  swallowed by `except Exception: pass`. Leaks a temp dir per `Sandbox()`
  instantiation forever. Pre-existing (blame commit `30e22b2c`), unrelated to
  NEW-8's diff — confirmed via `git blame`, not assumed.
- NEW-25 (see above): the allowlist is cwd-only, not real containment —
  worth a design-review flag if this sandbox is ever relied on as an actual
  security boundary rather than a footgun-prevention convenience.

**Pattern for future sandbox.py reviews:** when `ALLOWED_DIRS` or
`_validate_path` changes again, re-check (a) whether `mkdtemp()`'s actual
resolution still empirically matches the allowlist entry (don't just trust
that they're "obviously" the same string), and (b) all `Sandbox(allowed_dirs=...)`
call sites for whether they extend or replace the default list.
