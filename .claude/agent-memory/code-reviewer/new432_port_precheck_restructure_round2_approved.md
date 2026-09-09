---
name: new432-port-precheck-restructure-round2-approved
description: NEW-432 round2 fix — moved probe_port_health() out of the flock-held reap into a pre-lock precheck, keyed on (pid,port) pairs — approved
metadata:
  type: project
---

core/resource_gate.py + tests/test_resource_gate.py, NEW-432 round 2
(round 1 was rejected for running a blocking 2s HTTP probe inside
_LockedState's flock). Round 2: new `_precheck_port_liveness()` does an
UNLOCKED read of the slot list, probes only PermissionError-ambiguous
port-bearing PIDs, returns a `{(pid,port): bool}` map; both call sites
(`reserve_slot()`, `list_slots()`) build this map BEFORE entering
`_LockedState`, then pass it into `_pid_alive(pid, port, precomputed=...)`.
On a supplied-map miss (pid/port pair not found — slot list changed
between the two reads), fails closed to "alive" rather than probing fresh
under the lock. APPROVED — 1575 passed, 1 skipped, 0 failed (236s).

**Verification techniques that mattered here, reusable for future
lock-restructure reviews:**
- Don't just read the diff hunks — grep for EVERY writer of the state
  file (`_write_state_locked(` call sites) before accepting an "unlocked
  read is safe because writes are atomic" claim. Here it really is the
  single writer, invoked only from `_LockedState.__exit__` — but that has
  to be checked each time a new "safe unlocked read" claim shows up in
  this codebase, not assumed from a prior review of a similar claim.
- The "prove lock-ordering via a mocked probe that itself takes a
  non-blocking flock on the same lock file and expects BlockingIOError"
  test pattern is NOT a tautology if you independently confirm Linux
  flock() semantics are per-open-file-description, not per-process — a
  second `open()` in the SAME process attempting LOCK_EX|LOCK_NB while a
  first fd (also same process) still holds LOCK_EX genuinely raises
  BlockingIOError. Verified this directly with a standalone 15-line
  script (not trusted from memory/manpage-recall) before accepting the
  test as a real regression-catcher. This is a good general pattern:
  when a test's discriminating power rests on a specific OS-level
  syscall semantic, reproduce that semantic directly and cheaply rather
  than reasoning about it in the abstract.
- (pid, port)-pair keying for TOCTOU: construct the actual interleaving
  (precheck sees pid+old_port, locked reap sees pid reused with new_port)
  and confirm the miss path is hit and fails closed, rather than trusting
  the docstring's own description of why the keying is safe.
- Also re-verified the untouched TUI-session call site (`_pid_alive(pid)`,
  no port/precomputed args) and the untouched generic-OSError branch are
  both byte-for-byte unchanged — a restructure that touches a shared
  helper's signature is exactly the kind of change where an unrelated
  call site can silently regress if not explicitly re-checked.
