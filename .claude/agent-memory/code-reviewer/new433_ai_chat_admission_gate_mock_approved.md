---
name: new433-ai-chat-admission-gate-mock-approved
description: NEW-433 test_api.py fix mocking wait_and_reserve_context_budget/release_context_budget in test_api_ai_chat_auth_and_validation case 3 — approved
metadata:
  type: project
---

Reviewed 2026-09-09. Diff was test-only, single file
(tests/test_restoricon_core/test_api.py), additive ~10 lines inserted
between case 2 (400 missing-messages) and case 3 (successful proxy) of
`test_api_ai_chat_auth_and_validation`. Confirmed real bug being fixed:
this test previously depended on ambient device state (a real
llama-server on port 8080, which genuinely was running during this
review — `ps aux` showed it) rather than controlling admission
deterministically.

What was verified directly, not taken on the implementer's word:
- Patch-target strings (`core.resource_gate.wait_and_reserve_context_budget`,
  `core.resource_gate.release_context_budget`) match verbatim across all
  5 usages in the file (4 pre-existing T3 tests + this new one) — grepped
  the whole file, not just the diff hunk.
- Insertion point is provably safe: read restoricon_core/api/routes.py's
  `/api/v1/ai/chat` handler directly. The 401 (auth) check happens at
  line ~427 in a shared pre-dispatch block, and the 400 (missing
  messages) check at line ~1556 is *before* the `wait_and_reserve_context_budget`
  import/call at line ~1588-1594. So cases 1 and 2 return before ever
  reaching the admission gate — the mock genuinely cannot affect them.
- Server threading model: `RestoriconAPIServer` (restoricon_core/api/server.py)
  uses `http.server.ThreadingHTTPServer` + `threading.Thread`, not a
  subprocess — confirmed by reading imports/instantiation directly. This
  makes monkeypatch-in-test-process a valid mechanism for affecting
  server-side behavior (same process, same `core.resource_gate` module
  object), not a coincidence.
- Live-ran: single test (pass, 0.88s), full test_api.py file (20 passed,
  27.33s — all 4 pre-existing T3 tests still pass, confirming no
  regression to them), and full suite (`python3 -m pytest -q`, backgrounded
  because it exceeds the 120s foreground tool timeout — 1689 passed, 1
  skipped, 69 warnings in 280.38s).
- No live model load was needed for this review (no `free -h` gating
  required per rule 2) — an ambient llama-server was already running the
  whole time and untouched by the fix (which is the point of the fix).

Pattern for future reviews of this file: this test file's admission-gate
mocking pattern is now applied 5 times identically. If a 6th ai/chat-style
test is added without this mock, that's a regression of the same root
cause NEW-433 fixed — flag it on sight.
