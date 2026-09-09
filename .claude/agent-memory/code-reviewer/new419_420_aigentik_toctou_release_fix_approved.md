---
name: new419_420_aigentik_toctou_release_fix_approved
description: NEW-419 (getLlmProvider TOCTOU) + NEW-420 (missing release on !llamaOk timeout path) fix in Codey-Aigentik/index.js — APPROVED
metadata:
  type: project
---

Reviewed `~/Codey-Aigentik/index.js` diff closing [[new413_piece2_aigentik_release_call_approved]]'s two follow-on findings (NEW-419, NEW-420, logged in Codey-OS's `NEW_ISSUES.md`). Verdict: **APPROVED**.

What the fix does: captures `llama.getLlmProvider()` once into `const llmProvider` right after `await loadProfile()` (line 1675), reused at both the load-side check (`if (llmProvider === 'local')`, line 1694) and both release-side checks (the new `!llamaOk` branch and the existing warm-up-failure branch). Extracts the release `execSync` + try/catch into a named `releaseLocalModelServer()` function (defined once, line 1684, takes no args) called from both early-exit paths.

Verified directly, not accepted on the implementer's word:
- **NEW-419 fix is complete as scoped.** The bug was two live reads of `getLlmProvider()` at two different points in time potentially disagreeing, causing an inconsistent spawn/skip-release outcome. A single snapshot read before both checks makes them agree by construction — no residual inconsistency possible between the load-side and release-side checks. There *is* a still-earlier window (`startHttpServer()` at line 1664 runs before `loadProfile()` and before the `llmProvider` capture at 1675, so an owner-command provider switch in that window is still possible) — but since `llmProvider` is captured only once and used everywhere after, any such switch is already "baked in" consistently to both checks; it can't produce the orphan-by-disagreement failure mode NEW-419 was about. Confirmed this is a full close of NEW-419 as scoped, not a partial fix.
- **`releaseLocalModelServer()` scoping**: defined at line 1684, both call sites (1702, 1717) are textually after it. Takes zero arguments, references nothing but `execSync`/`log` (both stable, no staleness risk) — does NOT reference `llmProvider` internally, confirmed by direct read.
- **NEW-420 gate verified by reading actual indentation**: the new `releaseLocalModelServer()` call (line 1702) sits inside `if (!llamaOk)` (1696), which sits inside `if (llmProvider === 'local')` (1694). A Gemini-only setup (`llmProvider !== 'local'`) never even calls `startLlamaServer()`, so the whole nested block — including the new release call — is structurally unreachable for non-local providers. Confirmed, not just trusted.
- **Warm-up-failure branch gate unchanged**: still `if (llmProvider === 'local') { releaseLocalModelServer(); }` (1716-1718), same shape as before NEW-413's original fix, just using the captured var.
- **`execSync`/`spawn` import unchanged** (line 10, `child_process`) — confirmed via grep, not newly added or removed.
- **`npm test`: 272 passed, 19 suites, verbatim** — matches prior approved baseline exactly, no regression. Coverage: `index.js` lines 1627-1757 still uncovered (includes the new block) — same pre-existing gap as before, not a new regression in test discipline.
- **`git status --short` in `~/Codey-Aigentik`**: only `index.js` modified (pre-existing untracked hash-named test-artifact dirs, unrelated, noted in a prior review too).
- **Codey-OS repo untouched**: `git status --short` there returned nothing.

No new findings. This closes the loop opened in [[new413_piece2_aigentik_release_call_approved]] cleanly.
