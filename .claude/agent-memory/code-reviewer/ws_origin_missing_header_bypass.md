---
name: ws-origin-missing-header-bypass
description: WS Origin allowlist checks must reject a missing Origin header, not just a mismatched one — this project's GUI has no other auth layer yet. RESOLVED in gui/server.py as of Round 2 sub-task 2, re-submission.
metadata:
  type: project
---

**Status: fixed and approved.** The re-submitted diff changed the guard from
`if origin is not None and origin not in ALLOWED_ORIGINS:` to
`if origin not in ALLOWED_ORIGINS:`, so a missing Origin header (`None`) now
falls into the reject branch same as a mismatched one. Comment was updated to
match (no more "non-browser caller" exemption claim). Confirmed via literal
`git diff` output, only `gui/server.py` touched, PORT/HOST hoisting and
ALLOWED_ORIGINS construction unchanged from the previously-reviewed version.

The original finding below still documents *why* this mattered — keep it for
context when sub-task 3 (session token) lands, per
[[gui_c2_remediation_sequence]], in case the token changes the tradeoff.

Round 2 sub-task 2 (C-2 remediation, WS Origin allowlist in `gui/server.py`
`handle_ws`) initially allowed the WebSocket handshake through when the
`Origin` header was *absent*, only rejecting when it was *present and not in
`ALLOWED_ORIGINS`*. Justification given was "browsers always send Origin, so
missing Origin implies a non-browser caller, e.g. a bundled CLI test client."

That caller does not exist anywhere in the repo (verified via grep for
`ws_connect|handle_ws|/ws|websocket` — only `gui/server.py` itself matches,
and no test file references `handle_ws` or `gui/server` at all). The only
real launcher is `gui/start.sh`, which just execs the server for a human to
open in a browser.

**Why this matters:** per [[gui_c2_remediation_sequence]], sub-task 1 (bind
to 127.0.0.1) and sub-task 2 (Origin allowlist) both land before sub-task 3
(session token). Until the token lands, the Origin check is the *only*
access control on the WS endpoint. "Bound to loopback" does not mean "only
the browser can reach it" on Android/Termux — any other local process,
app, or `curl`/`websockets`-based script can hit `127.0.0.1:PORT/ws`
directly, and most non-browser WS client libraries don't set `Origin` by
default. Allowing missing-Origin through means the control is bypassed by
exactly the threat class it exists to stop, and the bypass requires zero
effort (just don't set the header).

**How to apply:** when reviewing any Origin/Referer-based access control on
a loopback-bound service that doesn't yet have a separate auth token, require
reject-by-default on missing header, not just on mismatch — unless a real,
already-existing caller in the repo needs to omit it (verify by grep before
accepting the justification, don't take "there might be a caller" at face
value). Re-check this same file when sub-task 3 (session token) lands: once
a token exists, missing-Origin-but-valid-token might become an acceptable
combined design — re-evaluate the tradeoff at that point, don't assume this
verdict carries forward unchanged.
