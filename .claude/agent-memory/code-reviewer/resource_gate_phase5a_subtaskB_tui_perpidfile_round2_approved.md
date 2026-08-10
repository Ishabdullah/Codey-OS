---
name: resource-gate-phase5a-subtaskB-tui-perpidfile-round2-approved
description: Phase 4.1/7.4 sub-task B (TUI interactive-session signal) round 2 — APPROVED, per-PID files + os.replace() close the single-shared-file bug from round 1
metadata:
  type: project
---

Round 2 of [[resource_gate_phase5a_subtaskB_tui_singlefile_rejected]] —
APPROVED. Fix direction from round 1 (per-session files, not one shared
file) was implemented as specified:

- `utils/config.py`: `TUI_PID_FILE` (single path) replaced with
  `TUI_SESSIONS_DIR` (directory). `GUI_CLIENTS_FILE` also added (GUI half,
  unrelated to this round's fix — see below).
- `main.py`: `_write_tui_pid_file()` writes to a **fixed** per-PID temp
  name (`.{pid}.tmp`, not `tempfile.mkstemp()`'s random suffix — verified
  this is safe because there is exactly one caller of this function, one
  `repl(...)` call site inside `main()`, confirmed by grepping both
  `_write_tui_pid_file\|_remove_tui_pid_file` and `repl(` project-wide —
  no re-entrancy, no second interactive entry point that would bypass
  this signal) then `os.replace()`s it to `{pid}.pid` — atomic on POSIX,
  closes the original truncate-before-lock race structurally (a reader
  can never observe a partial/empty file for a given PID; it either
  doesn't exist yet or is fully written). `_remove_tui_pid_file()` only
  ever unlinks its own PID-named path — ownership is now structural
  (path-based), not content-based, so the old read-back-and-compare
  ownership check is correctly gone, not silently dropped.
- `core/resource_gate.py`: `is_tui_session_active()` scans
  `TUI_SESSIONS_DIR`, returns True if any entry names a live PID, reaps
  dead-PID entries per-file (mirrors `daemon.py:check_pid_file()`'s
  self-healing but per-entry). Correctly skips dotfile temp names
  (`entry.name.startswith(".")`) matching the `.{pid}.tmp` naming from
  `_write_tui_pid_file()`. No flock on read — sound, because atomic
  replace means there's nothing to lock against (verified: only the
  writer that owns a given PID ever writes that filename, single-caller
  confirmed above).
- Verified the core regression fix with the project's own fork-based
  test (`tests/test_main_tui_lock.py::test_two_concurrent_sessions_do_not_destroy_each_others_signal`)
  by tracing it by hand: it uses **real `os.fork()`**, the child calls the
  actual `_write_tui_pid_file()`/`_remove_tui_pid_file()` functions (not
  hand-placed files), and assertions check the child's file **content**
  (`int(session_b.read_text().strip()) == child_pid`), not just
  existence — this is what makes a "two real PIDs coexist" claim
  actually load-bearing, versus round 1's flagged flaw (a test that would
  pass even with the old single-shared-file bug because it never
  constructed a genuine second live PID). Full suite: 474 passed / 1
  skipped (verbatim, matches implementer's claim). Isolated
  (`test_resource_gate.py` + `test_main_tui_lock.py` +
  `test_gui_clients_signal.py`): 104 passed (verbatim).

**GUI half (`gui/server.py`) did appear in `git diff` this round** — this
is round-1's already-approved work, never committed
(see [[working_tree_cross_round_bleed]]), not a new change. Verified
feature-for-feature against round-1's approved description
(`_write_gui_clients_count()`, connect/disconnect writes, `on_startup`
zeroing, `on_shutdown` write, GUI-PID cross-check) — matches prose
description; there is no commit anchor to diff against byte-for-byte
(same caveat as [[plannd_iter4_report_gen_deletion_scope_warning]]), so
"unchanged since approval" is a structural/feature-level claim, not a
byte-level one. The eventual commit will also pull in `NEW_ISSUES.md`
(NEW-111, `gui/server.py` sys.argv[1] import-time crash, already
documented and accepted as out-of-scope) and this memory dir's own
files — do not `git add -A`; stage the specific file list.

**Two residual risks found, both accepted (not blocking, not filed as
new NEW_ISSUES entries)**, same shape as the daemon.py PID-liveness
pattern this code deliberately mirrors:
1. TOCTOU in the reap loop: PID checked dead via `_pid_alive()`, then
   `entry.unlink()` — a window exists where the OS could reuse that exact
   PID for a new, legitimately-live TUI session between the check and the
   unlink. Requires PID reuse landing in a multi-microsecond window; same
   residual risk already accepted for `daemon.py:check_pid_file()`.
2. A `.{pid}.tmp` orphan left behind by SIGKILL between temp-write and
   `os.replace()` is never proactively reaped by `is_tui_session_active()`
   (it's skipped, not deleted) — self-corrects only when that same PID is
   reused and writes again. Bounded (one file per PID, not unbounded) per
   the implementer's own claim, verified by reading the fixed (not
   random) temp-name logic.

**Warning (non-blocking): fail-open/fail-closed inconsistency in the scan
loop.** `is_tui_session_active()`'s per-entry loop does
`if not entry.is_file() or entry.name.startswith("."): continue` —
`Path.is_file()` swallows stat-level `OSError` internally and returns
`False`, so an entry that can't even be `stat()`-ed is silently skipped
(counts toward the overall result being `False`, i.e. fail-**open** at
this exact point) — while the very next branch down (`entry.read_text()`
raising `OSError`) is explicit fail-**closed** (`any_live = True`), with
inline comment reasoning that closed is the safe direction for this
signal. These two adjacent failure paths land on opposite defaults for
what is conceptually the same "can't inspect this entry" case. Cheap fix
if ever revisited: replace `entry.is_file()` with an explicit
`try: entry.stat(); except OSError: any_live = True; continue` so a
stat failure gets the same fail-closed treatment as a read failure.

**Process lesson reinforced:** when a fork/subprocess-based test claims
to prove "two real PIDs coexist," check that assertions read back
*content* keyed to each PID, not just file existence — existence-only
checks pass even against a bug that would silently blank an existing
file's content in place (write succeeds structurally, but if two writers
ever did share a path, content would be indistinguishable from a
single-session pass/fail check).
