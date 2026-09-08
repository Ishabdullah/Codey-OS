---
name: new413_piece2_aigentik_release_call_approved
description: NEW-413 piece 2 (Aigentik index.js warm-up-failure calls release_model_cli.py) — APPROVED with 2 non-blocking warnings
metadata:
  type: project
---

Reviewed `~/Codey-Aigentik/index.js` diff (piece 2 of [[new68_inference_retry_and_new413_release_cli_approved]] — piece 1, `tools/release_model_cli.py`, already approved in Codey-OS repo). Verdict: **APPROVED**.

What was verified directly (not accepted on the implementer's word):
- Line ordering: new block sits between `warmUp()` failure log and the pre-existing `process.exit(1)` — confirmed via direct read, not dead code.
- Gate parity: `llama.getLlmProvider() === 'local'` used identically at the load site (`main()` line ~1670) and the new release site (~1691); `llama.js`'s `getLlmProvider()` returns `config.llm.provider` filtered through the same `VALID_PROVIDERS` list, defaulting to `'local'` — no enum/string mismatch.
- `execSync`/`child_process` already imported at top of file (line 10) — reused, not newly added.
- try/catch around the new `execSync` call is nested *inside* the `if (local)` block, but `process.exit(1)` is unconditional and sits after both — confirmed non-zero exit from `release_model_cli.py` (exit 1 = daemon unreachable, exit 2 = declined) is caught and logged, never blocks or alters Aigentik's own exit.
- `python3 ...` bare-name invocation (no absolute python3 path) mirrors the existing `ensure_model_cli.py` call in `startLlamaServer()` — pre-existing pattern, not a new risk introduced by this diff.
- `npm test`: 272 passed / 19 suites, verbatim, matches the implementer's claim exactly. Coverage report confirms `index.js` lines 1627-1736 (which include the new block) are uncovered by the existing suite — same lack-of-coverage as `startLlamaServer()` itself (lines 212-286 uncovered) — parity claim holds, this is untested-but-consistent-with-existing-practice, not a regression in test discipline.
- `git status --short` in `~/Codey-Aigentik`: only `index.js` modified (some untracked hash-named test-artifact dirs present but pre-dated this session by days, unrelated).

Two non-blocking findings surfaced independently (worth a NEW_ISSUES.md follow-on if not already logged):
1. **Narrow TOCTOU on `getLlmProvider()` across the startup window.** `startHttpServer()` runs *before* the load-side provider check, and `owner-command.js` has live `setLlmProvider()` call sites reachable via that HTTP surface. If an owner command switches provider between the load-side check and the warm-up-failure release-side check (a window of up to ~30s + warm-up time), the release call could be silently skipped even though a local model was spawned, or fired when none was. Narrow, requires an external command to land during Aigentik's own boot sequence, but structurally the same "state read twice, mutable in between" shape as this project's past self-race bugs — flag, don't block.
2. **Explicitly out of scope, not a regression**: the *other* exit path in `main()` (`if (!llamaOk) { process.exit(1) }`, i.e. `startLlamaServer()` itself returning false after a 30s poll timeout) still has no release call. If `ensure_model_cli.py` actually spawned the server but `isLlamaRunning()`'s health-check polling just hadn't caught up yet, that exit also orphans the model. The NEW-413 ledger entry's own "Fix direction" text scoped the fix to the warm-up-failure path only, so this isn't new-diff scope creep — but it's a real remaining gap worth a fresh ledger line if not already tracked.
