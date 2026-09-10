---
name: new441-dead-json-context-store-removal-approved
description: NEW-441 removed the dead legacy_reserved JSON context-budget store path from resource_bus.acquire/release_context_lease + orphan constants — approved
metadata:
  type: project
---

Reviewed uncommitted diff: core/resource_bus.py, core/resource_gate.py,
tests/test_context_budget.py (commit 1 of 2; test_api.py is commit 2 / NEW-443, out of scope).
APPROVED.

**Verified:**
- No writer anywhere to `resource_gate_context_budget.json` /
  `_CONTEXT_STATE_FILENAME`. `_LockedState` / `_write_state_locked` are
  used ONLY with slot-store defaults now — no `state_filename=` override
  caller remains. So `legacy_reserved` was provably always 0; removal inert.
- `total_other_reserved = other_reserved`; SQLite sum, ceiling check,
  INSERT byte-identical. `now` still used (INSERT granted_at/expires_at).
- `release_context_lease`: `found=False` + UPDATE→`found=True` on
  rowcount>0; JSON-only-match path can't have mattered (nothing ever wrote
  JSON records).
- `grep _CONTEXT_STATE_FILENAME|_CONTEXT_LOCK_FILENAME core/` → nothing.
- Converted reap test is a real discriminator: negative control
  (monkeypatch `_reap_stale_records_locked` to no-op) → test FAILS
  (`admitted=False`, other_reservations=5000). New `status==EXPIRED`
  assertion pins the expires_at reap branch specifically (seeded pid is
  alive). `_reap_stale_records_locked` sets EXPIRED via UPDATE, matches.
- Full run: tests/test_context_budget.py + test_resource_bus.py +
  test_new430_431_context_lease.py + test_resource_gate.py = 259 passed.

**Two out-of-scope stale-prose / latent issues confirmed real for
coordinator to ledger (non-blocking commit 1):**
- `restoricon_core/api/routes.py:~1686`: `release_context_budget(reservation_id)`
  is inside `try/except Exception as e: logger.warning(...)` — a wrong-arity
  TypeError would be swallowed and the AI-chat request still returns 200.
- `core/resource_gate.py:~3016-3019`: `_state_paths` docstring still says
  the overridable `state_filename`/`lock_filename` exist "to back a SECOND,
  independent file-locked store (the context-budget reservation ledger
  below)". That store is gone; those override params + `_LockedState`'s
  `state_filename`/`lock_filename` kwargs are now entirely dead (no caller
  passes them). NEW-441 rewrote the ~4108 sibling comment for exactly this
  reason but left this one.

**Follow-up 2026-09-10 (NEW-440 + NEW-445, commit 1 of 2) — APPROVED.**
Removed `reap_dead` from `reserve_context_budget()` sig (verified absent
from full body 4547-4750; reaping lives in acquire_context_lease); both
internal call sites + all test call sites use kwargs, never pass it.
Removed `state_filename`/`lock_filename` overrides from `_state_paths()`
and `_LockedState.__init__`, hardcoded `_STATE_FILENAME`/`_LOCK_FILENAME`;
repo-wide grep for `state_filename=`/`lock_filename=` = zero, all
`_LockedState(`/`_state_paths(` calls single positional. Bodies otherwise
byte-identical. Docstrings rewritten, accurate, no overclaim. 259+23
tests pass. Other `reap_dead`-bearing fns (list_slots etc.) untouched.
