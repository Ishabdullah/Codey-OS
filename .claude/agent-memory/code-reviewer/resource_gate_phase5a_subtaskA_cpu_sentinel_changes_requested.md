---
name: resource-gate-phase5a-subtaskA-cpu-sentinel-changes-requested
description: Phase 5a/7.4 sub-task A (rolling CPU sampler + ResourceSnapshot + --status) — CHANGES REQUESTED on cpu_percent sentinel gap + stale TODO.md line; rule-4 exemption confirmed correct
metadata:
  type: project
---

Track 3 Phase 5a / 7.4 sub-task A (`core/resource_gate.py` rolling CPU%
sampler, `core/sysmon.py` `read_battery_status()`, `core/daemon.py` watchdog
wiring, `main.py --status`) — round 1 verdict: **changes requested**, not a
clean approve, despite the process-lifecycle trace coming back clean.

**Rule 4 exemption — confirmed correct, don't re-litigate lightly next
time.** Traced `get_monitor()` → `SystemMonitor.__init__` → `_seed_cpu_proc()`
(guarded single file read, no thread) — thread only starts in `.start()`,
never called by `read_battery_status()`. `_read_battery()` uses no instance
state. `core/daemon.py`'s new call is `sample_cpu_percent()` (not
`get_current_cpu_percent()`), so no `time.sleep()` lands in the 30s watchdog
tick, and it's wrapped in its own broad try/except that only logs — verified
`_main_loop()` is a single asyncio coroutine (no concurrent writers), so the
sampler's un-locked module globals are safe today. This is a real, useful
"rule 4 doesn't force a whole daemon control review" case — but frame future
verdicts as "this passes rule 4 on the merits," not "rule 4 doesn't apply,"
per CLAUDE.md's own wording.

**Blocking finding 1 — `cpu_percent` sentinel gap.** `ResourceSnapshot`
uses `Optional[float]`/`Optional[int]` (`None` = unavailable) for
`temperature_c` and `battery_percent`, but `cpu_percent: float` has no way
to express "unmeasurable" — `sample_cpu_percent()`/`get_current_cpu_percent()`
both silently return `0.0` on any read failure (confirmed live on-device:
`/proc/stat` is `PermissionError` under non-root Termux on this build, no
`psutil` installed). NEW-108's own wording ("correctly log-and-degrade to
0.0 rather than... a wrong non-zero value") overclaims — 0.0 *is* wrong on
a loaded device, just wrong in the direction that looks like "genuinely
idle." This isn't cosmetic: sub-task C gates queue dispatch and sub-task D
trips an autonomous shutdown at >90% CPU, both directly off this same
float. Fix: make `cpu_percent: Optional[float]` (two existing tests already
assert `== 0.0` for exactly the two "not a measurement" cases — seed call,
unreadable file — and should become `is None` instead, which is the correct
direction, not collateral) — or, if the type stays `float`, NEW-108 must be
corrected under rule 6 to state plainly that 0.0 is indistinguishable from
idle and callers must not treat it as trustworthy.

**Blocking finding 2 — stale TODO.md line shipping alongside its own
implementation.** TODO.md's 4.1 entry says "Sub-task A is ready to hand to
implementer. Zero implementation started" in the *same uncommitted diff*
that contains sub-task A's full implementation + 12 passing tests. This is
the same shape as [[working_tree_cross_round_bleed]] — a scoping round
(TODO.md, WORK_QUEUE.md, project-architect memory) bundled with an
implementation round (code, tests, NEW_ISSUES.md, install.sh) in one working
tree, with the docs never updated to reflect the later round. Ask for
either two commits (scoping, then implementation with TODO.md corrected to
"code complete, pending review" per rule 7), or one commit with the line
fixed.

**Non-blocking, logged to NEW_ISSUES.md by the implementer (not yet, at
review time) — test-suite git-status coupling.** Reproduced empirically:
`tests/test_new19_patch_failed_repeat_escalation.py`'s three
`check_git_and_offer_commit` tests call the **real** `git status`/`git diff`
against the actual working tree (unmocked) and reach a real interactive
`confirm()` prompt whenever the tree has ANY uncommitted changes, hanging
under pytest's captured stdin (`OSError: reading from stdin while output is
captured`). Isolated via bisection: full suite green on clean `main`
(437 passed, 1 skipped); reintroducing only `main.py`'s diff (not
`resource_gate.py`/`daemon.py`/`sysmon.py`) alone reproduces the 3 failures;
reverting only `main.py` from an otherwise-full working tree makes them pass
again. Root cause: pre-existing test design flaw (tests do real git
operations on the live repo), not something this sub-task's logic broke —
but it means the full suite is NOT reliably green while ANY diff sits
uncommitted, independent of what that diff contains. Log under rule 8;
recommend a `git worktree`-based clean-checkout run for a true "does this
commit make the suite pass" verbatim result, since evaluating in the shared
working tree while dirty is inherently unreliable.

**Verified independently, all held up:** `/proc/stat` PermissionError live
(`cat /proc/stat` → Permission denied), `psutil` absent
(`ModuleNotFoundError`), `/sys/class/power_supply/battery/capacity` also
PermissionError (confirms `termux-battery-status` subprocess fallback is
the one actually exercised — matches install.sh's new comment and rule 11's
premise), `python main.py --status` live output structurally matches
NEW-108/NEW-109's pasted claims (`daemon.pid: null` + non-zero
`uptime_seconds` simultaneously; `battery_percent` populated real value;
CPU/temp keys present under `"resources"`). `core/resource_gate.py`'s
`_read_proc_stat_cpu_line()` byte-for-byte matches
`core/sysmon.py::_read_cpu_proc()`'s inner `_stat()` field indexing
(`idle = fields[3] + fields[4]`, `total = sum(fields)`) — the "same fields,
same formula, reused not reinvented" docstring claim is accurate.
