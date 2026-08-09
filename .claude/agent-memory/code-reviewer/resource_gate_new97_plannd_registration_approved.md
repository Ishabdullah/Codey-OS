---
name: resource-gate-new97-plannd-registration-approved
description: NEW-97/U.28 plannd accounted-but-exempt slot registration in codeydOS — approved w/ comment fix + doc-logging follow-up required
metadata:
  type: project
---

Reviewed `codeydOS`'s `start_plannd()`/`stop_plannd()` fix registering/releasing a
`resource_gate` slot for the bash-spawned `plannd` process (accounting-only,
never gating — `plannd` must keep starting unconditionally). Code itself
approved: env-var-passed Python `-c` snippets (no shell interpolation of
`$MODEL_FILE`/`$PID` into the Python source — safe), `cmd || echo` correctly
neutralizes `set -e` at every call site, PID+model_id double-match in
`_release_plannd_slot()` genuinely guards against PID recycling, real
`register_slot`/`release_slot`/`list_slots` signatures matched by direct read
(not trusted from implementer's report), live round-trip test passed against
real (non-mocked) `core/resource_gate.py`.

Two things worth remembering for next time this store is touched:

1. **`total_reserved_bytes()` deliberately excludes `SLOT_STATUS_RESIDENT`**
   (resource_gate.py ~1109-1133) — RESIDENT memory is already reflected in a
   live `/proc/meminfo` read, so summing it too would double-count and wrongly
   shrink headroom. Any future comment/doc claiming a RESIDENT registration
   "feeds into total_reserved_bytes()/admission bookkeeping" is factually
   wrong — it's visible in `list_slots()` only, contributes zero to admission
   math. Caught an overclaiming comment on this exact point in NEW-97's fix.

2. **Trace every `list_slots()` caller before approving a new slot-store
   writer**, not just the writer/reader you're told about. Only two real
   consumers exist project-wide: `resource_gate.total_reserved_bytes()`
   (RESIDENT-excluded, see above) and `core/embed_server.py:286`
   (`_find_pid_via_registered_slot`, filters by `model_id != "embed"`). Also
   check `core/daemon.py`'s `_handle_release_model_slot` — for
   `model_id="planner"` it never touches the gate store directly, only
   `get_planner_loader()`'s in-process singleton, so it silently reports
   `already_unloaded` while a real RESIDENT `"planner"` slot for `plannd`'s
   separate process persists. This is a *pre-existing, newly-observable*
   contradiction (nothing to contradict before plannd had zero gate
   presence) — accurately self-reported by the implementer, not a new bug
   introduced by the registration fix, and correctly out of scope for it.

Process gotcha: the implementer's review brief described "two findings
logged, not fixed" and cited `TODO.md:678`'s `U.28`/`NEW-97` entry as if it
reflected the fix — but `git diff --stat` showed only `codeydOS` changed;
`NEW_ISSUES.md` and `TODO.md` were untouched, `U.28` was still an open
unchecked item, and neither new finding actually existed anywhere in
`NEW_ISSUES.md` yet. Always run `git diff --stat` across the whole repo (not
just the reviewed file) before accepting a "this was logged" claim at face
value — rule 8/9 doc-logging claims need the same verbatim-evidence standard
as code claims.
