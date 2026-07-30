---
name: loader-v2-new9-sigmask-approved
description: NEW-9 fix (pthread_sigmask around Popen in LlamaServer.start()) — APPROVED with a Warning about child-process inherited signal mask
metadata:
  type: project
---

Round (NEW-9), `core/loader_v2.py` `LlamaServer.start()`: wraps the
existing `subprocess.Popen(cmd, stdout=log_fd, stderr=subprocess.STDOUT,
preexec_fn=os.setsid...)` call in
`signal.pthread_sigmask(SIG_BLOCK, {SIGINT})` / `finally:
SIG_UNBLOCK`, to close a real race where a SIGINT landing during
Popen()'s internal `os.fork()` gets silently swallowed by CPython's
logging-module atfork callback (never reaches [[main_py_new5_keyboardinterrupt_fix_approved]]
/ [[main_py_new6_keyboardinterrupt_fix_approved]] guards, since those
never got the exception at all). **Approved.**

Verified, not assumed:
- `git diff core/loader_v2.py` showed Popen kwargs byte-for-byte
  unchanged; only the sigmask wrapper added.
- `self.process = subprocess.Popen(...)` is inside the `try`, assigned
  before the `finally`'s unblock — the one way the implementer could
  have made this worse (deferred-signal-fires-before-PID-tracked) does
  not occur.
- `start()` is only ever called from the main thread in this codebase:
  `main.py` CLI/REPL sites (main thread) and `core/daemon.py`'s
  `_main_loop` watchdog (single-threaded asyncio event loop, not a
  worker thread) — grepped all `threading`/`Thread(` usage in the repo,
  none touch loader_v2.py. `pthread_sigmask` masking therefore actually
  takes effect; no non-main-thread silent-no-op risk here.
- The blocked window is narrow — only the Popen() call itself, not the
  120-iteration health-check loop after it.
- `finally` covers all exit paths of the try (any exception type,
  including non-KeyboardInterrupt failures like `FileNotFoundError`) —
  SIGINT cannot be left permanently blocked by a Popen()-side exception.
  (Minor: the initial `SIG_BLOCK` call itself is *before* the try, so a
  hypothetical failure there would leave SIGINT blocked forever — not a
  practical risk since blocking a valid signal essentially never raises,
  Suggestion-level only.)
- Local `import signal` in `start()` doesn't collide with `stop()`'s
  separate local `import signal as _signal` (both function-scoped, no
  module-level `signal` import existed before). Naming inconsistency is
  cosmetic only.
- Live pytest run: `1 failed, 321 passed` — same pre-existing
  `test_sandbox` failure seen and already attributed as unrelated in
  [[main_py_new6_keyboardinterrupt_fix_approved]]. `py_compile` clean.
- `git status` scope matched expectations: only `core/loader_v2.py` +
  `NEW_ISSUES.md` (project-architect's own doc, out of scope per task
  framing) — no cross-round bleed this time, contrast with
  [[working_tree_cross_round_bleed]].

**Warning raised (not blocking, logged for NEW_ISSUES.md):** POSIX
signal masks are inherited across `fork()`, and `exec()` does **not**
reset a blocked-signal mask (only resets handler dispositions). Since
`subprocess.Popen()` forks before exec'ing `llama-server`, the child
inherits the parent's momentarily-blocked SIGINT mask at the instant of
fork — meaning **llama-server itself starts with SIGINT permanently
blocked at the OS level**, and nothing in this diff (or elsewhere in
the codebase) ever unblocks it in the child. This is not currently
exploitable: `os.setsid()` (already present, unchanged) already detaches
the child from the terminal's process group, so it was never going to
receive terminal-driven SIGINT anyway, and `stop()` only ever sends
SIGTERM/SIGKILL to this child, never SIGINT. But it's a real, latent
behavior change worth documenting — if any future code path ever sends
`SIGINT` directly to the llama-server PID expecting graceful shutdown,
it will silently do nothing. Correct long-term fix would be to also
unblock SIGINT inside `preexec_fn` (child-side, post-fork/pre-exec) so
the child's mask matches its pre-diff state.

Live-verifier note: same caveat as NEW-5/NEW-6 —
[[termux_signal_delivery_unreliable_in_sandbox]] means a live SIGINT-during-fork
repro (the original bug had only a ~1-in-4 reproduction rate per
live-verifier) cannot be meaningfully forced through this Bash-tool
sandbox at all, let alone repeatedly. Confidence here rests on static/
logical analysis: blocking SIGINT for the duration of fork() means the
kernel defers delivery until after `pthread_sigmask(SIG_UNBLOCK, ...)`
returns, which is strictly after `self.process` is assigned — this
closes the exact mechanism described (the atfork callback can no longer
receive a KeyboardInterrupt to swallow, because the signal is not
delivered to the thread at all during that window). This is a
sound "no delivery" argument, not a "faster handling" argument, so it
does not depend on scheduling luck the way the original bug's timing
did. Recommend one interactive-terminal live-verifier pass (real Ctrl+C,
not Bash tool) as a final confirmation, but given the deterministic
kernel-level guarantee (vs. the original race's inherent unreliability),
this is lower-priority than prior NEW-5/6 live-verifier follow-ups —
not a blocker for commit.
