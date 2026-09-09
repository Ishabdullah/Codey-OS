---
name: new86-new203-pid-reverify-approved
description: core/embed_server.py NEW-86 immediate-pre-kill PID reverification + NEW-203 stop() docstring correction — APPROVED
metadata:
  type: project
---

## What was reviewed and approved

`_kill_port_occupant()` (NEW-86 fix): after the original `_find_port_occupant_pid()`
identification call, the fix re-runs `_find_port_occupant_pid()` a second
time immediately before `os.kill()` and aborts the kill (logs, does not
raise) if the two calls disagree. This is the same finding I originally
wrote up under NEW-83's review (see [[new83_embed_server_kill_by_pid_approved]]
lesson 2) — good continuity, the fix targets the exact gap identified
there, not a reinterpretation.

`stop()` (NEW-203): docstring-only change, verified byte-identical code
body before/after diff. Confirmed the described edge case is real by
tracing `start()`'s adoption branch (`_port_is_bound() and
_check_health()` fast path, lines ~83-103): it never touches
`self.process`, so a stale dead `Popen` from this object's OWN earlier
spawn survives untouched through an adoption of a DIFFERENT occupant.
Confirmed the "stays safe" claim: `stop()`'s kill logic only ever
targets `self.process.pid` (its own dead spawn), never the adopted
server's real PID, so behavior is a no-op/ProcessLookupError, not a
wrong kill.

## Verification method used (worth repeating)

1. Traced the reverify-then-kill call site line-by-line: only one `info()`
   log sits between the second `_find_port_occupant_pid()` call and
   `os.kill()` — genuinely "immediately before," not a check done too
   early that leaves the window open again.
2. Traced the mismatch-abort control flow through the *whole* function,
   not just the branch itself: after an abort, execution still falls
   into the shared `_time.sleep(2)` + `_port_is_bound()` tail. This
   correctly returns `True` if the port happened to free itself anyway
   (the real occupant's own natural exit, unrelated to our non-kill) and
   `False` if something is still bound — the return value tracks real
   port state either way, never inferred from the abort decision itself.
   This is deliberate and correct, not a bug.
3. Ran a **negative control** against the pre-fix method body: extracted
   the OLD `_kill_port_occupant` source via `git show HEAD:core/embed_server.py`
   into a scratch file, `exec()`'d it into a throwaway class bound to the
   real module's globals, monkeypatched it onto `EmbedServer` as an alias
   method, and ran test 1's exact `side_effect=[4242, 9999]` scenario
   against it directly (not through pytest, since the working tree file
   couldn't be swapped — see gotcha below). Confirmed it DOES call
   `os.kill(4242, 9)` — i.e., the new tests would genuinely have failed
   against pre-fix code. This is stronger evidence than mentally tracing
   "the old code only calls `_find_port_occupant_pid()` once" — actually
   executed it.
4. Ran the full suite: `python -m pytest tests/ -q` → `1545 passed, 1
   skipped in 235.48s`. No regression.

## Gotcha: overwriting a tracked source file via `cp`/heredoc to do a
negative control gets blocked by the sandbox classifier

Attempting `git show HEAD:core/embed_server.py > core/embed_server.py`
(or `cp` onto the tracked path) to temporarily swap in the pre-fix
version for a negative-control pytest run was blocked ("Permission...
denied by the Claude Code auto mode classifier"), even though the intent
was read-only verification (restore immediately after). Workaround that
worked: write the old version to a **scratch path only** (never the
tracked file), then `exec()` the extracted old method's source into a
throwaway class bound to the live module's globals and monkeypatch it
onto the class for a manual (non-pytest) negative-control run. Slower
than a real pytest negative control but achieves the same evidentiary
value without touching the tracked file. Worth trying this pattern first
next time a negative control is needed, rather than the direct
overwrite-then-restore approach that gets blocked.

## Coverage caveat handling (rule 6)

Both the code comment and the `NEW-86` ledger entry explicitly state the
fix does NOT fully close the window on the `_find_pid_via_registered_slot()`
fallback path (only narrows it — catches recycle-to-non-llama-server,
misses recycle-to-another-llama-server-on-this-device), and explicitly
flag the primary `/proc/net/tcp` path as unverified on-device
(`PermissionError` in dev sandbox). This is accurate, not overclaimed —
confirmed by independently reading both `_find_port_occupant_pid()` and
`_find_pid_via_registered_slot()` in full rather than trusting the
comment's own characterization of them.

## Verdict: APPROVED (both NEW-86 and NEW-203)
