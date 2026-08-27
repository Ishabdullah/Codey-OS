---
name: new145_149_155_option_c_3warnings_closed
description: Follow-up confirmation pass closing all 3 warnings from new145_149_155_option_c_approved — comment fix + 2 negative-control-verified tests
metadata:
  type: project
---

Follow-up to [[new145_149_155_option_c_approved]] (2026-08-27). Implementer
patched all 3 previously-logged warnings; re-verified each independently
rather than trusting the "verified via negative control" claim:

1. **`core/daemon.py` comment fix (warning 1) — confirmed accurate.**
   Corrected comment states `_handle_health()` hardcodes literal `1800`
   rather than reading `task_timeout` from config (tracked as NEW-256,
   out of scope here). Independently grepped `core/daemon.py` for `1800`
   and confirmed line 374 (`_handle_health()`) really is a bare literal —
   comment's factual claim holds.

2. **New test `test_handle_status_running_active_reads_configured_non_default_timeout`
   (warning 3) — genuinely load-bearing.** Hand-hardcoded `task_timeout =
   1800` in `_handle_status()` (deleting the `self._config.get(...)`
   read) and reran just this test: failed (`assert 1 == 0`). Restored,
   reran full file: 28/28 green again.

3. **New test `test_start_allow_upgrade_true_daemon_idle_releases_old_slot_on_upgrade`
   (warning 2) — genuinely load-bearing.** Commented out the
   `rg.release_slot(existing_slot["slot_id"])` call inside
   `_upgrade_resident_if_safe()` and reran just this test: failed
   ("Expected 'mock' to be called once. Called 0 times."). Restored,
   reran full file: 28/28 green again.

4. **`core/loader_v2.py` diff content unchanged from the prior round** —
   confirmed via `diff <(git show HEAD:core/loader_v2.py) <working-tree>`
   showing the same single-line addition set as before my two probes
   (no accidental leftover edit from the negative-control test).

Full suite: `862 passed, 1 skipped` (matches implementer's reported
count exactly — this repo currently has a second, unrelated concurrent
round's changes to `restoricon_core/*` and its own tests live in the
same working tree, contributing to that total; scoped `git diff --stat`
on `core/daemon.py`/`core/loader_v2.py`/the new test file confirms no
bleed either direction, consistent with [[working_tree_cross_round_bleed]]).

**APPROVED — closes the NEW-145/149/155 chain's mandatory rule-4 review.**
Ready for commit; still needs the live-verification step per rule 2/7
(unit tests can't observe a real port-in-use race or TERM-then-KILL
cycle against a live daemon — same live-verifier flag as the prior
round: daemon-only harness per the NEW-14 swap-pressure precedent).

**Reusable technique note:** when a reviewer needs to hand-revert a
tracked, unstaged file to run a negative control, `git diff <(git show
HEAD:path) path` after restoring is a cheap way to confirm the restore
landed byte-for-byte, cheaper than `git diff --stat` alone (stat only
proves *a* diff exists, not that it's the *right* diff).
