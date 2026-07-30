---
name: main-py-new6-keyboardinterrupt-fix-approved
description: NEW-6 fix (args.init/args.tdd/args.fix load_primary() try/except KeyboardInterrupt/SystemExit -> shutdown()) — APPROVED, verified 321/1 live
metadata:
  type: project
---

Round 7, NEW-6 fix in `main.py` `main()` (~lines 1462-1515): wraps
`loader.load_primary()` at the three one-shot CLI sites (`args.init`,
`args.tdd`, `args.fix`) in the identical
`try/except (KeyboardInterrupt, SystemExit): shutdown(); return` block
already approved for `repl()` in [[main_py_new5_keyboardinterrupt_fix_approved]].
Reviewed and **approved**.

Verified, not assumed:
- `git diff` showed exactly 3 hunks, all in `main.py`, all identical in
  shape to the `repl()` fix; `repl()`'s own fix (line ~1269) untouched.
- Each site's early `return` (inside the except) exits `main()` before
  reaching the site's own later call (`run_init()` / `run_tdd_loop()` /
  `fix_file()`) — confirmed by reading the surrounding lines, not just
  the diff hunk. Each block's normal-path `shutdown(); return` at the
  bottom is unreachable once the except's `return` fires, so `shutdown()`
  cannot double-fire for the same invocation. No `atexit`/`signal.signal`
  registration exists anywhere in main.py (grepped) that could trigger a
  second `shutdown()` call independently.
- These three sites never had `repl()`'s `is_remote_backend()` gate
  before this change, and still don't — correctly left as a **pre-existing
  inconsistency**, not silently patched in. (Would be a separate,
  out-of-scope change if ever done.)
- No changes to `shutdown()`, `get_loader()`, `ModelLoader`, or any
  PID/kill logic — diff is purely additive try/except wrapping.
- No name-pattern kills, no new PID-file logic, no exception swallowing
  beyond the existing `shutdown()` internals (pre-existing, already
  reviewed under NEW-5).
- Live test suite run myself: `1 failed, 321 passed` — the 1 failure
  (`ccos/tests/test_ccos.py::test_sandbox`, a sandbox path-allowlist
  assertion) reproduces identically with `git stash` applied (change
  reverted), confirming it's pre-existing and unrelated to this diff.
- `python3 -m py_compile main.py` clean.

Live-verifier note: same caveat as NEW-5 — a true live Ctrl-C-during-load
repro is unreliable through the Bash-tool sandbox
([[termux_signal_delivery_unreliable_in_sandbox]]). Static analysis +
identical-pattern-to-already-approved-code is the basis for this
approval. Recommend one live-verifier pass (manual interactive terminal,
not Bash tool) before considering NEW-6 fully closed, consistent with
NEW-5's precedent — but this is not a blocker for the commit itself.
