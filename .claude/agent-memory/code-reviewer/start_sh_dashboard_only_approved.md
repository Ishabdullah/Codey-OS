---
name: start-sh-dashboard-only-approved
description: gui/start.sh --dashboard-only opt-in mode (NEW-4 fix) reviewed and approved — reference for re-checking start.sh arg parsing or trap changes later
metadata:
  type: project
---

Round 3 addressed NEW-4 (`gui/start.sh` forcing a full 7B load just to view
the dashboard) by adding `--dashboard-only` / `CODEY_GUI_DASHBOARD_ONLY=1`.
When set, the script skips `python main.py` and instead does
`wait "$GUI_PID"` in the foreground, letting the existing single
`trap ... INT TERM EXIT` (which kills the tracked `$GUI_PID`) handle
teardown identically in both branches. No new kill path, no PID-file
involvement, default path byte-for-byte unchanged. Approved.

**Latent (non-blocking) gotcha found:** the arg-parsing was changed from
`PORT="${1:-8888}"` to a `for arg in "$@"` loop where any non-flag arg sets
`PORT`. This means with multiple positional args the **last** one wins
instead of the first (previously only `$1` was ever read). No current
caller (`install.sh`, README, master vision doc) passes more than one
positional arg, so it's not an active regression — but if `gui/start.sh`'s
call sites are extended later (e.g. a wrapper passing extra flags), recheck
this loop's arg-precedence behavior.

**Why relevant to future reviews:** if `gui/start.sh` gets more flags added
later, verify the loop still correctly separates flags from the single
PORT positional — this is the kind of "small" arg-parsing change CLAUDE.md
rule 4 does NOT technically require code-reviewer sign-off for (it's not
process-lifecycle/kill/PID/auth), but it sits right next to the trap/kill
logic in the same file, so review it together anyway.

**How to apply:** when reviewing further `gui/start.sh` changes, always
grep repo-wide for callers before approving any change to positional-arg
semantics, and re-verify the trap still references the same single tracked
`$GUI_PID` in every branch (including any new mode branches).
