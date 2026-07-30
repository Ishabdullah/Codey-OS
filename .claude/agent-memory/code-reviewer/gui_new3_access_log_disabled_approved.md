---
name: gui-new3-access-log-disabled-approved
description: NEW-3 fix — gui/server.py run_app() access_log=None to prevent future logging of ?token= session token — APPROVED
metadata:
  type: project
---

Round 4, NEW-3: `gui/server.py`'s `web.run_app()` call now passes
`access_log=None` in addition to the existing `print=lambda *_: None`.
Verified against installed aiohttp (3.14.3) via
`inspect.signature(aiohttp.web.run_app)` that `access_log` is a real
kwarg (default `Logger aiohttp.access`) and `None` is the documented way
to disable it — not a made-up parameter. Confirmed via grep that no
other logger/logging call site in gui/server.py could independently log
the request line or query string, so this one-line change genuinely
closes the token-in-logs path noted as a caveat in
[[gui_c2_session_token_sub3_approved]]. Single-line diff, no scope
bleed, no process-lifecycle/binding/PID change — approved.

This closes out the C-2 remediation follow-up thread
([[gui_c2_remediation_sequence]]); no further sub-tasks expected unless
a new logging configuration is introduced for this process later, in
which case re-verify access_log=None still takes effect (aiohttp lets
a caller override this again from outside run_app if they instantiate
their own AccessLogger — unlikely here but worth a glance if the
logging setup changes).
