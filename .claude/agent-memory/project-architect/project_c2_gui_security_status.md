---
name: project-c2-gui-security-status
description: Audit finding C-2 (GUI server security) is FULLY LIVE-VERIFIED as of 2026-07-29 — all 3 sub-tasks + a live-verifier pass through the real gui/start.sh launch path. Round 2 is closed.
metadata:
  type: project
---

As of 2026-07-29, `Codey-OS-audit.md`'s [C-2] (GUI server: unauthenticated
command execution, `0.0.0.0` default bind, no WS Origin check) is
**fully live-verified**, not just code-complete. All three remediation
sub-tasks are committed and code-reviewer-approved: `d29468f` (loopback
default bind), `ca94ab5` (WS Origin allowlist), `1198ba1` (per-process
session token + timing-safe check on `/ws`).

Two verification passes exist:
1. code-reviewer ran a real `gui/server.py` on a scratch port, curl-tested
   all 4 token/Origin combinations (no-token 403, wrong-token 403,
   correct+correct 101, correct-token+bad-Origin 403), clean PID-tracked
   teardown.
2. **live-verifier then ran a second, stronger pass through the actual
   `gui/start.sh` launch path** (real daemon startup, not scratch):
   confirmed loopback-only bind via direct connectivity (LAN IP refused),
   re-checked WS auth against the real served token fetched live, 7B
   model load confirmed via `/health` 200, teardown of all 5 real
   processes by tracked PID, `free -h` healthier after teardown
   (3.4Gi used) than before launch (4.0Gi used).

`PROJECT_PLAN.md`'s Round 2 section is now marked **"FULLY
LIVE-VERIFIED"** — Round 2 (C-2) is closed, no open items remain.

**How to apply:** if asked about GUI security status, this can now be
described as fully done/verified without qualification. Two follow-ups
remain logged (not fixed, not blocking): [NEW-3] (Suspected) — GUI
session token could leak into access logs if a future change ever
configures a `logging` handler for `gui/server.py` (dormant today, no
exploit path currently); [NEW-4] (Confirmed) — `gui/start.sh`
unconditionally chains into `main.py`, forcing a full 7B model load with
zero user interaction just to view the dashboard (a resource-cost/UX
issue, not security).
