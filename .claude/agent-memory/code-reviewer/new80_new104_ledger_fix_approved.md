---
name: new80-new104-ledger-fix-approved
description: NEW-80 _LockedState fd-leak fix + NEW-104 ledger-correction claim, both verified and approved (2026-09-09)
metadata:
  type: project
---

Scope: `core/resource_gate.py` (`_LockedState.__enter__`) + `tests/test_resource_gate.py`, reviewed in isolation
from a much larger uncommitted parallel-agent working tree (per CLAUDE.md's cross-agent doc-collision warning).

**NEW-80 (code fix) — APPROVED.**
- The `try`/`except BaseException` wraps *only* the `fcntl.flock(...)` call — confirmed by reading the
  surrounding lines directly (not trusting the diff hunk framing alone). `self._slots = _read_state_locked(...)`
  sits *after* the try block, outside it, so a failure there is never caught/masked by this except clause.
- Bare `raise` (no `raise ... from ...`, no wrapping) — preserves the original exception object and traceback
  exactly; `BaseException` catch + bare re-raise is safe for `SystemExit`/`GeneratorExit` too, since nothing about
  either is altered before the re-raise.
- `except BaseException` (not `Exception`) is deliberate and correct given the KeyboardInterrupt-during-blocking-flock
  rationale — verified this doesn't create a swallow risk anywhere, since every path re-raises unconditionally.
- Convention-match claim vs `telemetry/rotate.py`'s `acquire_rotate_lock()` — read that function directly: it's a
  generator-based `@contextmanager`, so its fd-close-on-failure lives in an outer `finally` around the `yield`;
  `_LockedState` is class-based, so the equivalent lives directly in `__enter__`'s except clause. The two shapes are
  different for a structural reason (generator vs class), not a deviation — ledger's own description of this
  distinction is accurate.
- Negative control reproduced myself (not trusting the "verified via git stash" claim as stated): swapped in the
  pre-fix file body (via `git show HEAD:core/resource_gate.py`, since `git stash` failed here due to unrelated
  untracked files elsewhere in a busy multi-agent tree — worth remembering, `git stash` can fail loudly and safely
  when the tree has conflicting untracked adds; it did not silently drop anything). Both new tests failed pre-fix
  with the exact `assert <open TextIOWrapper> is None` failure the ledger entry describes verbatim, and passed
  post-fix (restored file). Confirms real regression coverage, not decorative tests.
- Full suite: `python -m pytest tests/ -q` → 1545 passed, 1 skipped, no regressions.

**NEW-104 (ledger-correction-only claim, zero code diff) — VERIFIED, claim holds.**
Traced every cited call site myself rather than accepting the "already fixed by 1ca97e1" framing:
- `core/loader_v2.py:1410` `rg.reserve_slot(spec, port=PRIMARY_SERVER_PORT, meminfo=gate_meminfo)` — confirmed
  `port=` is passed (matches claim it was `None` at the time the original finding was written).
- `confirm_resident_and_mark_slot()` (loader_v2.py:121-211) genuinely forwards `pid=self._server.process.pid` to
  `rg.mark_resident(slot_id, pid=pid)` at line 211 in the genuine-spawn branch — rebinds slot pid to the real child.
- `_reconcile_adopted_slot()` (loader_v2.py:1586+) resolves the real PID via `rg.resolve_port_owner_pid()` AND
  gates on `rg.pid_cmdline_contains(real_pid, b"llama-server")` before calling `register_slot(pid=real_pid, ...)` —
  genuinely a positive-resolution path, not a name-based guess (CLAUDE.md rule 3 compliant). Bails out (no
  registration) if either check fails, rather than registering an unverified PID.
- `core/embed_server.py` — both `register_slot()` call sites (adoption branch line ~92 using
  `self._find_port_occupant_pid()`, genuine-spawn branch line ~204 using `self.process.pid`) independently use real
  PIDs, confirmed by direct read.
- `codeydOS`'s `start_plannd()` — grepped the file: only a comment mentions the name (`# ... "start_plannd()"/...`),
  no function definition or call exists. Confirms M1-D deletion claim.
This is the kind of "already fixed, ledger correction only" claim this same triage session had gotten wrong 3
times elsewhere per the task brief — this one held up under full independent tracing.

**Verdict: APPROVED**, both NEW-80 and NEW-104.

Reusable notes for future resource_gate.py / lock-logic reviews:
- When `git stash` fails due to unrelated untracked files elsewhere in a busy multi-agent tree, it fails safely
  (no partial stash) — use `git show HEAD:<path>` to get the pre-diff file body for a scoped negative control
  instead of fighting the stash.
- `_LockedState` (class-based ctx mgr in resource_gate.py) and `telemetry/rotate.py`'s `acquire_rotate_lock()`
  (generator-based) are the two flock patterns in this repo — when reviewing either, check the *other* one's
  close-on-failure placement as the cross-check, but expect the placement to differ structurally, not match line-for-line.
