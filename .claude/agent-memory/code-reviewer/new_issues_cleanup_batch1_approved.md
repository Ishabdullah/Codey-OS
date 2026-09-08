---
name: new-issues-cleanup-batch1-approved
description: Batch 1 of NEW_ISSUES.md ledger closeout (plannd/planner_service/recursive/resource_gate + 5 test files) — APPROVED
metadata:
  type: project
---

2026-09-08: First batch of a project-wide effort to close out
NEW_ISSUES.md via small independent doc/comment/test fixes (no
process-lifecycle touch). Reviewed core/plannd.py, core/planner_service.py,
core/recursive.py, core/resource_gate.py, tests/conftest.py,
tests/test_orchestration.py, tests/test_plannd_telemetry.py,
tests/test_planner_service_daemon_socket_timeout.py,
tests/test_resource_gate.py, tests/test_restoricon_core/test_api.py.
APPROVED — every doc/comment "fix" independently re-verified against
actual source (not taken on the implementer's word), and all held up:

- resource_gate.py's rewritten "wired into daemon.py/loader_v2.py" claim:
  grepped every named function call site directly, all real. Same module
  had a prior *false* "not wired in" claim caught in an earlier round
  ([[daemon_self_pid_check_verified]]-adjacent history), so this class of
  claim gets extra scrutiny every time it recurs — this time it was correct.
- recursive.py's temp_critical/temp_warn fallback drift (80/65 -> 90/75):
  confirmed against utils/config.py's actual THERMAL_CONFIG values.
- test_restoricon_core/test_api.py's monkeypatch scoping fix: confirmed
  make_request() (the test's own HTTP client) hits urlopen directly against
  the live test server, and the real proxy route
  (restoricon_core/api/routes.py:1546->1625) targets a URL containing
  "/v1/chat/completions" — the old unconditional urlopen mock silently
  intercepted the test client's own request too, so the test previously
  never exercised real server code. A neighboring pre-existing test's
  docstring independently corroborated this exact gap.
- test_plannd_telemetry.py's new NEW-344-pinning test: traced plannd.py's
  `if timings:` branch (sets cached_prompt_tokens=None with no `nulls`
  entry) and telemetry/recorders.py's `_emit()` pruning of None body
  fields directly — test's claimed mechanism is accurate, honestly labeled
  as pinning buggy behavior not correctness.

**Why worth remembering:** this is a low-risk-labeled batch (docs/comments/
tests only, explicitly "no process-lifecycle risk") but every single claim
in it was still independently verifiable and worth checking — one of the
docstring rewrites (resource_gate.py) is in a file class that has burned
this project before with a false "not wired in" claim. Don't skip
verification just because a batch is billed as low-risk.

**How to apply:** for future NEW_ISSUES.md ledger-closeout batches, still
grep/read every factual claim in a rewritten docstring or comment against
the actual current call sites — "low risk, no process-lifecycle" scope
does not mean the claims can be trusted without checking.
