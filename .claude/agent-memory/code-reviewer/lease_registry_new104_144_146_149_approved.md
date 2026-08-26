---
name: lease-registry-new104-144-146-149-approved
description: Lease/registry adoption-registry commit (1ca97e1) review — APPROVED with 2 latent findings logged, not blocking
metadata:
  type: project
---

Reviewed commit `1ca97e1` (find_resident_slot/resolve_port_owner_pid
toolkit in resource_gate.py, loader_v2.py's _reconcile_adopted_slot(),
embed_server.py's adopt-instead-of-kill start() branch + stop() leak fix).
**Verdict: APPROVED.**

Verified clean: `stop()`'s release-outside-`if self.process:` control flow
(traced line by line — no double-release, correct order vs the `finally:
self.process = None` above it); `_reconcile_adopted_slot()`'s try/except
wraps the entire method body (only `return`s inside, no raise can escape
into `load_primary()`); `_port_is_bound()` before `_check_health()`
ordering in the adoption branch; every PID-resolution helper
(`resolve_port_owner_pid`, `_pid_owning_inode`, `pid_cmdline_contains`)
degrades to `None`/`False` on failure with zero name-based fallback (rule
3); NEW-200's `PermissionError` claim reproduced live in-session
(`open("/proc/net/tcp")` → `PermissionError: [Errno 13]`); the rewritten
`test_resolve_port_owner_pid_finds_real_listening_process` genuinely
exercises the real `_pid_owning_inode()` fd-scan — proved via negative
control (hand-patched `_pid_owning_inode` to `return None`, re-ran, test
failed as expected, reverted); `test_embed_server_still_kills_unhealthy_occupant`
still passes (adoption branch doesn't swallow the original NEW-144 kill
path); full suite `692 passed, 1 skipped` re-run matches the claim
exactly; docs (CODEY_MASTER_PLAN.md §4/Appendix A) correctly say "NOT yet
reviewed" with no overclaim.

**Two latent (non-blocking) findings surfaced, must be logged to
NEW_ISSUES.md before/alongside closing this item:**

1. **TOCTOU double-registration**: `find_resident_slot()` (read, one
   `_LockedState` lock) followed by `register_slot()` (write, a SEPARATE
   lock acquisition) in both `loader_v2._reconcile_adopted_slot()` and
   `embed_server.py:start()`'s adoption branch (embed_server.py:88-98) is
   the exact anti-pattern `reserve_slot()`'s own docstring (resource_gate.py
   ~3201) documents and was written specifically to avoid ("acquires this
   store's flock three separate times... both then register, and the
   store ends up over-admitted"). Two concurrent adopters (e.g. a CLI
   process's `ModelLoader` and the daemon's watchdog, both racing to
   adopt the same genuinely-unregistered resident server) could both see
   `existing is None` and both `register_slot()`, double-counting the
   same real PID's cost_bytes. **Confirmed NOT currently reachable**:
   loader_v2's register branch requires `resolve_port_owner_pid()` to
   resolve a PID, which requires `/proc/net/tcp` — confirmed
   `PermissionError` on this device (NEW-200), and `_reconcile_adopted_slot()`
   has no registered-slot fallback (unlike embed_server's
   `_find_pid_via_registered_slot()`) — so this branch is dead code on
   this device today. embed_server's `start()` is only ever called from
   the daemon's single `async def _main_loop` (sequential ticks in one
   coroutine, not threads) via the `get_embed_server()` singleton;
   `inference.py` doesn't call `start()` per NEW-144's own precedent — so
   no real cross-process race exists for embed either, today. **Fix
   direction if/when this becomes reachable** (rooted device, or a future
   caller): an atomic `register_slot_if_absent()` doing the find-and-append
   inside one `_LockedState` acquisition, mirroring `reserve_slot()`'s own
   pattern.

2. **Status-filter divergence** (embed_server.py): `find_resident_slot()`
   filters `status == RESIDENT` (resource_gate.py:3458), but
   `_find_port_occupant_pid()`'s fallback `_find_pid_via_registered_slot()`
   (embed_server.py:365-366) filters only `model_id`+`port`, no status
   check — so a PENDING (or missing-status) `model_id="embed"` slot would
   be invisible to the adoption-branch's "already registered" check but
   visible to the fallback PID lookup, causing the same double-registration
   with NO concurrency required. **Confirmed empty today**: grepped every
   `model_id="embed"` write site (embed_server.py:93, :205) — both pass
   `status=rg.SLOT_STATUS_RESIDENT` explicitly; embed is deliberately
   exempt from `reserve_slot()` (the only PENDING producer) per the
   module's own design. Latent only — would activate if a future writer
   ever registers an embed slot at a status other than RESIDENT.

**Also verified, not a defect**: `stop()`'s docstring asserts an adopted
server always has `self.process is None` — traced a real edge case where
that's false (this object's OWN earlier spawn died — `self.process`
truthy but `poll() is not None` — then adoption picks up a DIFFERENT
process on the same port before `self.process` is ever cleared).
Behavior stays safe (killpg targets the stale, already-dead PID →
`ProcessLookupError` → caught; the real adopted PID is never touched) —
but the stated invariant is inaccurate. Worth a docstring correction, not
blocking.

**`is_running()` re-entry check** (advisor-prompted): for an adopted
server, `self._started` is set `True` in the adoption branch, so
`is_running()` falls through to `self._check_health()` and correctly
returns `True` — the daemon watchdog's `if not is_running(): start()`
does NOT re-enter `start()`'s registration branch every 30s tick. Clean.

**Process lesson**: when a check-then-act race is flagged as a review
target (per instructions), don't stop at "the anti-pattern exists" — walk
every caller's actual reachability on THIS device/architecture before
deciding severity. A textbook TOCTOU that's provably dead code today
(blocked by an already-documented platform limitation, or a
single-coroutine call pattern) is a Warning + NEW_ISSUES entry, not a
blocker — but only after that reachability check, not instead of it.
