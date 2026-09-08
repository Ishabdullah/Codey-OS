---
name: new_issues_cleanup_batch2_changes_requested
description: NEW_ISSUES.md cleanup batch 2 (crm/scheduling/auth/routes/sandbox) — CHANGES REQUESTED, live-reproduced TypeError crash in update_user tuple-return refactor
metadata:
  type: project
---

Batch 2 of the NEW_ISSUES.md ledger closeout (batch 1 = 6617f2a, approved,
see [[new_issues_cleanup_batch1_approved]]). This round: CHANGES REQUESTED.

**Critical (blocking) — auth.py:956-957, NEW-310 tuple-return refactor.**
`AuthService.update_user` signature was changed from `Optional[User]` to
`Tuple[Optional[User], bool]` (returns `(user, role_changed)`), and every
non-error return site was updated to match *except* the missing-row early
return:
```python
user = self.get_user_by_id(user_id)
if not user:
    return None          # <-- still bare None, not (None, False)
```
The one production call site, `restoricon_core/api/routes.py:588`,
unconditionally unpacks: `updated, role_changed = self.auth.update_user(...)`.
For a nonexistent `user_id` this raises
`TypeError: cannot unpack non-iterable NoneType object` *before* the
`if not updated: return 404` guard on the next line ever runs — so
`PUT`/`POST /api/v1/users/{id}` on a bad id now 500s instead of 404ing.
Live-reproduced directly against `AuthService` with an in-memory DB (see
transcript). None of the diff's own tests exercise a nonexistent
`user_id`, and the 1485-test full-suite pass did not catch it — grep
confirmed routes.py is the only call site. **Fix: `return None` ->
`return None, False`** at that line.

**Warning — sandbox.py NEW-42 `_find_disallowed_path_token`.** New
mitigation layer resolves relative tokens containing `../` via
`Path(candidate).resolve()`, which resolves against `os.getcwd()` of the
*reviewing Python process*, not against the `cwd`/`exec_cwd` the command
will actually execute under (the function doesn't even receive that
param). Concretely demonstrated a resolution mismatch (token
`"../../home/Codey-OS/ccos/target"` validates as ALLOWED when resolved
from a repo-root process cwd, but the *actual* subprocess — cwd'd into
`self._tmp_dir` under `tempfile.gettempdir()` — would resolve the same
token to a different, unrelated path). Could not construct an actual
sensitive-file read with this (once a token's `..` count reaches
filesystem root, both bases converge, so absolute-target escapes like
`/etc/passwd` are still caught) — the check is additive/never weaker than
HEAD, and absolute/`~`-prefixed tokens are unaffected since `resolve()`
on those ignores cwd entirely. But the docstring's "known limitations"
list does NOT disclose this mis-resolution, and it means the function
doesn't actually validate what it claims to for the `../`-relative-token
class. Fix is doc-or-code: pass `cwd` into the function and resolve
relative tokens against it (requires hoisting `exec_cwd` computation
above the new check), or add the gap to the docstring's limitations list.

**Confirmed pre-existing, unrelated to this diff (both true, as flagged
by implementer):**
- `Sandbox.cleanup()` calls `shutil.rmtree` with no `import shutil`
  anywhere in the file → silently swallowed by `except Exception: pass`,
  meaning cleanup is a permanent no-op (confirmed leak). Diff adds
  `import shlex` in the same import block — adding `import shutil` there
  too is zero-marginal-cost and should be picked up as a real fix, not
  just logged. The new test file (`ccos/tests/test_sandbox_path_validation.py`)
  calls `sandbox.cleanup()` in `finally` 4x, adding to the tmpdir litter
  problem already confirmed in [[telemetry_t3_prefix_cache_hit_round2_flaky_test_rejected]] (72 live litter dirs).
- `get_customer_by_email` in crm_service.py still has the identical
  over-strict top-level `has_permission(PERM_READ_ALL_CUSTOMERS)` gate
  pattern that NEW-248 just removed from the neighboring
  `get_customer_by_external_id` — confirmed via direct read, correctly
  left unfixed/flagged rather than silently touched (out of this task's
  scope).
- `create_user` (auth.py:720) calls `_parse_custom_permissions` but not
  the new `_validate_custom_permissions` guard that `update_user` and
  `set_user_permissions` now get — confirmed real asymmetry, correctly
  flagged as follow-up not fixed here.

**Verified correct (no issues):**
- NEW-248 delegation: `get_customer_by_external_id` -> `get_customer()`
  -> `can_access_customer()` row-scoped check, confirmed by reading all
  three methods in full.
- NEW-240 (`update_subcontractor_qualification`, `update_subcontractor`,
  `update_appointment_status`): confirmed `get_subcontractor`/
  `get_appointment` do no field redaction beyond the permission gate —
  `_row_to_subcontractor`/`_row_to_appointment` are the same converters
  used by both old getter path and new write-scoped path, so no new
  over-exposure.
- NEW-307 TOCTOU recheck: pre-UPDATE guard (line ~1804) and in-transaction
  recheck (line ~1836) use the *identical* `_PROJECT_REASSIGNMENT_FIELDS &
  set(updates)` condition — recheck is not narrower than the check it
  hardens. None-row guard (concurrent delete) correctly mirrors the
  existing missing-row contract elsewhere in the same method.
- `lib/service_manager.sh` NEW-281 redaction: genuine recursive
  dict/list walk (`_redact`), not shallow; confirmed by reading the
  diff, low-risk CLI-only display path.

**Process gap:** unlike batch 1 (which updated NEW_ISSUES.md +
PROJECT_LOG.md in the same commit, see `git show --stat 6617f2a`), this
batch's diff touches zero lines of NEW_ISSUES.md/PROJECT_LOG.md/
CODEY_MASTER_PLAN.md (`git diff --stat -- NEW_ISSUES.md` empty) despite
closing 8 numbered findings and surfacing 3 new ones. Flagged, not
independently blocking, but should be closed before/with the auth.py fix.

Advisor push-back was correct and load-bearing here: initially framed
the sandbox mis-resolution as a second Critical bypass; advisor's
depth-arithmetic argument (both resolution bases converge once `..`
count reaches root, so absolute-target escapes remain caught) held up
under a second, more careful brute-force search and is why it was
downgraded to Warning. The auth.py tuple-unpack crash was the one the
advisor called correctly as the real, sole blocker, and it live-repro'd
exactly as predicted.
