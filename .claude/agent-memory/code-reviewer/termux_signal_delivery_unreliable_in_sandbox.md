---
name: termux-signal-delivery-unreliable-in-sandbox
description: Bash-tool sandbox can't reliably reproduce real Ctrl+C/SIGINT timing on this device — don't trust a "clean" or "failed" live-repro of KeyboardInterrupt-handling code done this way
metadata:
  type: project
---

Attempted to independently live-verify the [[main_py_new5_keyboardinterrupt_fix_approved]]
Round 6 fix by sending `kill -INT` to a backgrounded `python main.py` from
the Bash tool. Two confounders made this unreliable, discovered the hard
way:

1. **`cmd &` in bash gives the child `SIGINT`/`SIGQUIT` = `SIG_IGN`**
   (POSIX job-control convention for asynchronous commands in a
   non-interactive shell). Once a process starts with that disposition,
   `kill -INT <pid>` is a silent no-op — Python never even sees the
   signal to raise `KeyboardInterrupt`, regardless of how precisely the
   kill is timed. Confirmed with a trivial `time.sleep` loop script:
   ran to full completion twice under `bash -c '... &'`, never caught
   the interrupt.
2. **Even when correctly delivered (e.g. via the Bash tool's own
   `run_in_background`, which doesn't have this job-control quirk),
   signal-handling latency on this device was highly variable** — one
   control test took ~19 seconds to notice a signal sent at the ~1s
   mark, despite the target code being in a plain `time.sleep(0.5)`
   loop with nothing blocking the GIL. This is long enough to blow past
   a model-load window that itself only took a few seconds, making
   "send SIGINT mid-load" essentially unreproducible through this tool
   with any timing precision.

One attempt using this flawed method left a genuinely orphaned
`llama-server` (spawned by a `main.py` I'd sent `kill -TERM` to while it
was blocked on a FIFO stdin) — had to be cleaned up manually by tracked
PID, RAM dropped to 153Mi free / 7Gi swap in use before cleanup, back to
4.3Gi free / 1.2Gi swap after. Not a bug in reviewed code — an artifact
of my own test harness — but a reminder that any live-signal-handling
test in this environment carries real RAM risk if it's not cleaned up
immediately (CLAUDE.md rule 2).

**Takeaway:** don't attempt to live-verify `KeyboardInterrupt`/SIGINT
handling changes via this Bash tool's backgrounding. It cannot stand in
for a real interactive terminal session. Trust static/code-path analysis
for this class of change, and require the live-verifier subagent (or the
user) to confirm via an actual interactive Ctrl+C, with the verbatim
output logged per CLAUDE.md rule 5 — don't accept "I sent kill -INT and
nothing happened" from this sandbox as evidence the fix doesn't work.
