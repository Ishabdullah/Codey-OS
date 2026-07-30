---
name: project_round18_new18_new20_new21
description: Round 18 (NEW-18 live-repro attempt) was inconclusive on its original question but surfaced two new confirmed bugs, NEW-20 and NEW-21
metadata:
  type: project
---

Round 18 tried to isolate whether NEW-18's swap-thrashing is driven by
context SIZE vs. turn COUNT/retries, via a small-file-vs-large-file
harness comparison. The comparison never ran: the harness piped a static
file into `main.py --no-resume`'s stdin, and hit a distinct bug —
`main.py:1337-1359`'s paste-detection `select.select([sys.stdin], ...)`
always reports non-TTY stdin as "readable" even at EOF, so it drained
the whole file into one garbled message then spun indefinitely at ~88%
CPU with zero requests ever reaching llama-server.

Outcomes (docs-only commit `c266e85`, no code changed):
- **NEW-18 corrected** per Ground Rule 6 — original size-vs-count
  question remains open/unanswered, not resolved either way by this
  round. Future attempts need a TTY-backed harness (pty/`script(1)`),
  not stdin piping, and must control for baseline free RAM (varied
  2.2Gi vs 4.9Gi free between the two attempted runs — a likely
  confound).
- **NEW-20 (new, Confirmed):** the stdin spin-loop/garbling bug itself.
  Root cause fully identified (select() unsafe on non-TTY stdin), not
  fixed — flagged as a clean, cheap candidate for a near-future round
  since it also blocks any future automated REPL testing via stdin
  redirection.
- **NEW-21 (new, Confirmed):** model load alone (before any inference)
  drove swap ~1.2Gi -> ~5.6Gi within ~10s this run; severity appears
  baseline-free-RAM-dependent. Same character as NEW-14 (n_ctx=32768
  KV-cache concern), now confirmed on a single lightweight model load,
  not just the full 3-model stack. Observational, no action recommended.

**Why:** live-verifier caught genuine instability (swap to 6.8Gi,
llama-server RSS collapse) and stopped immediately per CLAUDE.md's
instability rule, killing only its own tracked PIDs — clean afterward.

**How to apply:** NEW-20 is a good next-round candidate (root cause
already known, isolated fix). Any future NEW-18/NEW-7-style
reproduction work needs a TTY-backed harness, not stdin piping.
