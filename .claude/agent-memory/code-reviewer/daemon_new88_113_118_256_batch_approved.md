---
name: daemon-new88-113-118-256-batch-approved
description: 4-finding core/daemon.py batch (NEW-88 embed watchdog logging, NEW-113 dead server.planner removal, NEW-118 shutdown-tripwire continue, NEW-256 task_timeout config unification) — all 4 approved
metadata:
  type: project
---

Reviewed uncommitted `core/daemon.py` diff (scoped review — repo had
substantial other parallel-agent uncommitted work outside these 4 files,
correctly excluded per task scope) plus 3 new test files
(`tests/test_new88_embed_watchdog_logs.py`,
`tests/test_new118_shutdown_short_circuit.py`,
`tests/test_new256_handle_health_task_timeout.py`).

**NEW-256** (hardcoded `1800` → `get_config().get("tasks", "task_timeout",
default=1800)` in `_handle_health()`): verified both call sites
(`_handle_status()` line 352, `_handle_health()` line 396) now read the
identical expression, using the module-level `get_config` import (line
26) — not `self._config`, which post-[[new259_daemon_config_and_loader_port_fix_approved]]
is the correct pattern for this file (that earlier round found
`self._config` doesn't exist on `DaemonServer`).

**NEW-113** (removed dead `self.server.planner = self.planner`):
repo-wide grep for `server\.planner` across `core/`, `tools/`, `ccos/`,
`tests/`, `main.py` found zero reads anywhere — only test files setting
`d.planner` directly on `Daemon` (different attribute/class). Confirmed
safe independently, not just trusting the ledger's own grep claim.

**NEW-118** (added `continue` after `_trigger_shutdown()` fires inside
the watchdog tripwire check, so the same tick doesn't fall through to
the model-load/embed-server watchdogs): verified via literal
column-indentation dump that `continue` (col 28) sits inside
`while self.running:` (col 12, wrapped by try col 8/finally col 8) —
correctly re-evaluates the loop condition, which is now False, and
falls into the `finally:` unload block. `_trigger_shutdown()`'s own
docstring explicitly documents this exact mechanism as intended design,
not a new invention. Confirmed nothing between the tripwire check and
the watchdogs (background cleanup, `_process_planner_tasks()`) is
skipped by the early `continue` — those run earlier in the same tick,
before the watchdog block.

**NEW-88** (bare `except Exception: pass` in embed-server watchdog →
`except Exception as e: warning(...)`): confirmed `warning` is imported
at line 30-31 (`from utils.logger import (error, info, ...,
warning)`). Pure logging addition — exception still caught, no new
re-raise, same swallow-at-control-flow-level.

**Negative-controlled all 3 new tests** (not just run against the fixed
code): copied fixed `daemon.py` to scratchpad, restored pre-fix version
via `git show HEAD:core/daemon.py`, reran the 3 new test files — all 3
new/rewritten tests failed exactly as their own docstrings predicted
(embed-watchdog logging test: mock not called; shutdown short-circuit
test: embed watchdog's `is_running()` mock called once, proving
fall-through; task_timeout non-default test: `[] == [1]`). Restored
fixed file from scratchpad copy afterward (not `git checkout`, per
[[git_checkout_path_wipes_uncommitted_diff]] — confirmed restore via
`git diff --stat` matching original 31/5 line counts before proceeding).

Full suite: `python -m pytest tests/ -q` → **1545 passed, 1 skipped**,
0 failures, no daemon-related regressions (227.49s).

Verdict: **APPROVED** — all 4 findings (NEW-88, NEW-113, NEW-118,
NEW-256) independently verified against current code, not just trusted
from the diff's own inline comments.
