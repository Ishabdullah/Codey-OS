---
name: new14-swap-pressure-finding
description: Full `codeydOS start` (7B + 1.5B plannd + embed, all concurrent) drives this ~10.8GB device to 7.5-8.5Gi swap within ~40s — not a bug, a real capacity limit
metadata:
  type: project
---

The full `codeydOS start` wrapper launches the daemon plus three
concurrent models: the 7B primary, the separate 1.5B "plannd" planner
process, and the embed server. On this device (~10.8GB RAM), that
combination pushes swap usage from a ~1Gi baseline to 7.5-8.5Gi within
about 40 seconds of steady-state startup — well before any actual test
workload runs. This was directly observed during Round 13 (NEW-11)
live-verification: two attempts using the full stack crashed Termux
outright at 7B model-load time, and a third self-aborted proactively
after the swap-climb pattern was recognized. Logged as `NEW_ISSUES.md`
[NEW-14], Confirmed, observational only — not scoped as a fix.

**Why:** no code bug was found causing this; it appears to be the
genuine resource cost of three concurrent llama-server-family processes
on this device spec. A lighter harness (`python3 main.py --daemon`
directly, skipping the plannd process) peaked at only ~1.9Gi swap for
the equivalent test, strongly suggesting the plannd process (or the
3-way concurrency itself) is the dominant contributor, not the
daemon/watchdog code being tested.

**How to apply:** when scoping any future live-verification task that
would use the full `codeydOS start` wrapper, prefer the lighter
`python3 main.py --daemon` harness (bypasses plannd) unless the test
specifically needs the planner process. Always run `free -h` and watch
swap trend, not just a single before/after snapshot — the danger here
is a fast climb mid-startup, not a static high number. See
[[project_round13_new11_closed]] for the verbatim swap-climb numbers and
crash history that produced this finding.
