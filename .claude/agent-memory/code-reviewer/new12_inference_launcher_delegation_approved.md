---
name: new12-inference-launcher-delegation-approved
description: core/inference.py's independent _start_server() Popen launcher removed, delegates to loader_v2.get_loader().ensure_model() — APPROVED with one Warning about orphaned thermal-restart feature
metadata:
  type: project
---

Round (NEW-12): removed the second, uncoordinated `llama-server` launcher in
`core/inference.py` (`_start_server()`'s own `subprocess.Popen`, no
port-in-use check, `stop_server()` never called by anything). New
`_start_server()` delegates to `core.loader_v2.get_loader().ensure_model()`,
the canonical launcher (port check, reuse, os.setsid, SIGINT mask per
NEW-9). Added `PRIMARY_SERVER_PORT` config constant (`CODEY_PRIMARY_PORT`
env var, default 8080), threaded through `loader_v2.SERVER_PORT` and
`inference_hybrid.ChatCompletionBackend`'s default port arg.

Verified independently (not just trusting implementer's summary):
- Zero repo-wide callers of `stop_server`/`_get_env`/`_server_proc`
  before deletion (grep across all .py, not just core/).
- `_server_ready()` left in file but now genuinely dead (only def, no
  callers) — implementer correctly flagged this as intentional, not
  hidden.
- Dropped imports (`os`, `subprocess`, `LLAMA_LIB`, `LLAMA_SERVER_BIN`,
  `MODEL_PATH`) are genuinely unused post-diff — confirmed via AST-walk
  usage-count script, not just eyeballing.
- `ensure_model()` → `load_primary()` return semantics match old
  `_server_ready()` failure shape (bool, `if not X: raise`).
- Ran full test suite live: `1 failed, 321 passed` — confirmed the 1
  failure (`test_sandbox`, sandbox path-allowlist assertion) is
  pre-existing by stashing the diff and re-running; unrelated to this
  change.
- `PRIMARY_SERVER_PORT`/`CODEY_PRIMARY_PORT` naming doesn't collide with
  `EMBED_SERVER_PORT`/`PLANND_SERVER_PORT` siblings.
- docs/configuration.md planner-model default correction matches actual
  `utils/config.py` default.

**Bug pattern for future reviews — silent feature death via removed
"secondary consumer" code:** `core/thermal.py`'s `ThermalManager.
_reduce_threads()` sets `self.restart_recommended = True` specifically so
a caller can restart llama-server with the new thread count (the class's
own docstring/comment says so verbatim: "inference.py checks this and
restarts llama-server with the updated thread count on next call"). The
deleted `_start_server()` block was the *only* reader of
`restart_recommended` anywhere in the repo (verified by grep across all
.py files) — nothing in `loader_v2.py` replaced it. So thermal-based
thread-count restart-on-throttle is now dead: `ThermalManager` still
computes and warns about it, but nothing ever acts on the flag anymore.
This is a real behavior regression (device-heat mitigation), not just a
"different launcher" cleanup, and it wasn't explicitly called out as a
finding in the implementer's summary (they framed it as "not a regression
since loader_v2 never had equivalent logic" — technically true but
misleading, since inference.py *did* have it and now nothing does).

**How to apply:** when a diff deletes a code block that consumed a flag
set by module X, always grep repo-wide for that flag/attribute name to
check if X now has an orphaned producer with no consumer. This class of
bug won't show up in "who calls the deleted function" greps — you have to
grep the *flag itself*, in both directions.
