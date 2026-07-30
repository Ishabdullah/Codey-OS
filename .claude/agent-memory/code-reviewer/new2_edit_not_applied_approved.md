---
name: new2-edit-not-applied-approved
description: NEW-2 fix (core/agent.py else-fallthrough EDIT NOT APPLIED marker) — APPROVED, verified live
metadata:
  type: project
---

NEW-2 fix approved for commit: in the `run_agent()` else-fallthrough branch
(core/agent.py ~1831-1869), a new `[EDIT NOT APPLIED] <tool> on <path> ...`
marker is logged via `log_error` (aliased from `utils.logger.error`, no
collision — `error` was genuinely absent from the pre-existing
`info/separator/success/warning` import) and prepended into the
`messages.append(...)` content whenever `name in
("write_file","patch_file","append_file")` and `is_error(last_tool_result,
name)` is True at that point.

**Why this held up under scrutiny:** traced that `last_tool_result` is
reassigned unconditionally every loop iteration (core/agent.py:1670) before
any check runs, so there's no staleness risk from an earlier/unrelated tool
call. Enumerated every route into the fallthrough with `is_error==True` for a
mutating tool: (a) escalation offered+declined, (b) `_in_subtask=True` so
escalation is skipped and retries alone exhaust, (c) `max_retries==0` edge
case. All three are legitimately "exhausted" states — no false-positive
route found.

**Test verified genuinely exercises the real path** (not a repeat of the
NEW-1 "patched the wrong import" bug): `core/agent.py:9` imports `infer` at
module level (`from core.inference_v2 import infer`), so
`monkeypatch.setattr(agent, "infer", fake_infer)` in
`tests/test_new2_edit_not_applied.py` actually intercepts the call site used
by the retry loop. Confirmed by literally running the test:
`python -m pytest tests/test_new2_edit_not_applied.py -v` → `1 passed in
0.19s`.

**Full suite verified live**, not just trusted from the handoff:
`python -m pytest -q` → `1 failed, 321 passed, 67 warnings in 4.81s`, the one
failure being `ccos/tests/test_ccos.py::test_sandbox` (echo-should-succeed
assertion), a file untouched by this diff — consistent with a pre-existing,
unrelated environment issue.

**How to apply:** if NEW-2's marker logic is touched again, re-verify the
same three things: (1) `last_tool_result` reassignment timing relative to
the check, (2) all reachable routes into the fallthrough given `is_error`
True for a mutating tool name, (3) that `infer` (or any other mocked call)
is patched at its real module-level import site, not a local/deferred one —
this project has been bitten by patch-target mismatches before (NEW-1,
[[working_tree_cross_round_bleed]] adjacent pattern).
