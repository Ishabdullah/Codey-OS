---
name: wp0_3_sibling_test_py_regression_changes_requested
description: WP0.3 device-bridge mock removal — round1 CHANGES REQUESTED (real regression in a sibling test.py), round2 APPROVED
metadata:
  type: project
---

2026-10-07, Codey-OS, two-round sequence, now closed.

**Round 1 — CHANGES REQUESTED, Critical.** See full original writeup below.
`ccos/plugins/device/bridge/test.py` (bare `test.py`, not pytest-collected,
but the real mechanism `ccos/core/sandbox.py`'s `run_plugin_test()` invokes
for `agent_orchestrator`'s `PLUGIN_TEST` step) still asserted the old
fabricated-success shape after `_register_default_handlers()` was removed,
and crashed for real when run directly. Root cause of why "116 passed" never
caught it: pytest's default `python_files` pattern (`test_*.py`/`*_test.py`)
never matches a bare `test.py` — **every CCOS plugin has one of these
(`ccos/plugins/*/*/test.py`) and none are covered by any pytest invocation.**
Always check this class of file separately when changing a default behavior
anything in `ccos/plugins/` relies on.

**Round 2 — APPROVED.** Fix rewrote `test_device_bridge_capabilities()` to
assert the fail-loud contract via a new `_assert_not_connected()` helper
(catches only `DeviceBridgeError`, asserts "not connected" in the message,
else raises `AssertionError` — any other exception type propagates
uncaught, so it can't silently mask a wrong-shaped failure). Deliberately
did NOT register fake handlers on the real singleton inside `test.py`
(would have reintroduced the exact hazard, since it runs as production via
the sandbox). Verified independently:
- `python3 ccos/plugins/device/bridge/test.py` passes standalone AND after
  `pytest tests/test_device_bridge_b5b.py -q` ran first in the same shell
  (moot in practice since `test.py` is a fresh subprocess every time, but
  confirmed clean either way).
- Grepped every pytest-collected caller of
  `get_default_device_bridge_server`/`bridge.py`'s module-level `_client`:
  only `tests/test_device_bridge_b5b.py::test_ccos_plugin_capabilities`
  touches the shared singleton — `ccos/tests/test_device_bridge.py` only
  builds local `DeviceBridgeServer()` instances. So the new `try/finally`
  teardown there was fixing a **hygiene** gap, not a demonstrated live
  cross-file bug — there was never more than one pytest-collected caller of
  that singleton to begin with. Don't over-credit a "closes a real risk"
  claim for a teardown fix without checking whether a second caller
  actually existed.
- Read `handle_envelope()`'s full control flow to confirm the new
  `test_genuinely_unknown_action_is_unsupported_not_not_connected` test's
  action type reaches the `ALL_ACTIONS` check (not blocked earlier by the
  telephony/third-party veto or the auth check, since the test server has
  no `auth_token` and the action isn't `send_sms`/`make_call`/
  `third_party_message`) — confirmed the two error strings ("Unsupported
  action type" vs "Device not connected") are genuinely reached by
  different inputs now, closing the round-1 disclosed coverage gap.
- `python3 -m pytest ccos/tests/ tests/test_device_bridge_b5b.py -q` →
  `122 passed in 16.64s` (proxy vars unset first, per
  [[sandbox_http_proxy_urllib_405_env_artifact]]).

**Lesson reinforced: a `try/finally` teardown fix can be correctly
described as "non-blocking hygiene" even in an approved round — verify
whether the risk it closes was ever reachable (grep every caller of the
mutated shared state) before treating "added teardown" as evidence of a
real bug fixed.**

See also [[wp0_2_notification_audit_approved]], [[working_tree_cross_round_bleed]].
