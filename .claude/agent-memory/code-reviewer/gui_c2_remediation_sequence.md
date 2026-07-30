---
name: gui-c2-remediation-sequence
description: Codey-OS audit finding C-2 (GUI unauthenticated, 0.0.0.0 bind, no Origin check) is being fixed as 3 separate sub-tasks
metadata:
  type: project
---

`Codey-OS-audit.md` finding C-2 covers three distinct gaps in
`gui/server.py`: (1) default bind host `0.0.0.0` with no auth, (2) no
WebSocket Origin allowlist in `handle_ws`, (3) no session token/auth at
all. These are being remediated as three separate sub-tasks, each
reviewed in isolation:

- Sub-task 1 (reviewed 2026-07-29, approved): default `CODEY_GUI_HOST`
  changed from `0.0.0.0` to `127.0.0.1` at `gui/server.py:269`. Confirmed
  no other code/script (`gui/start.sh`, `install.sh`, `README.md`) reads
  `CODEY_GUI_HOST` or assumes LAN/remote reachability — all docs and
  launch scripts only ever reference `http://localhost:8888`, consistent
  with this being a single-device (Samsung S24 Ultra) local-first tool,
  not a LAN service.
- Sub-task 2 (not yet reviewed as of 2026-07-29): WS Origin allowlist.
- Sub-task 3 (not yet reviewed as of 2026-07-29): session token/auth.

**How to apply:** Do not treat sub-task 1's approval as closing C-2 —
`handle_ws` (gui/server.py ~206-238) still has zero auth and zero Origin
check after sub-task 1 alone; a process on the same device (or anything
that reaches 127.0.0.1, e.g. another Termux app or a local proxy) can
still open the websocket and run commands. Full C-2 closure requires all
three sub-tasks landing and being reviewed individually — check whether
sub-tasks 2 and 3 have their own approved commits before considering C-2
resolved in PROJECT_PLAN.md.
