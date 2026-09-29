---
name: new481-textnode-escaping-second-half-approved
description: NEW-481 remaining text-node innerHTML XSS half (4 sinks in web_surfaces.py) — APPROVED after independent negative-control repro
metadata:
  type: project
---

Round: fixed the second half of `NEW-481` (the inline-handler half was
already closed under `NEW-496`) — 4 sinks in `restoricon_core/api/web_surfaces.py`
wrapped in the file's existing `escapeHtml()`: `loadCrmList()` customer
block, `loadCrmList()` project block, `populateCustomerDropdown()`
(`<option>` text), `loadUsersList()`. **Verdict: APPROVED.**

## What I verified independently (not taken from the brief)

- **Diff is exactly the 4 sinks**, 9 line-pairs / 18 changed lines, no
  scope creep. `NEW-489` (`loadSubcontractors`) and `NEW-496`
  (`openPermModal`/`deleteUser`/`deleteAppointmentType`
  `escapeHtml(JSON.stringify(...))` handler sites) untouched — confirmed
  by direct grep at each line number.
- **Tier1/Tier2 test-tier claim reproduced via my own negative control**:
  saved the diff to scratchpad, `git checkout --` the fixed file (test
  file itself untouched), reran the 24-test file → exactly the claimed 3
  Tier-1 wiring tests failed, all 21 Tier-2 mechanism tests still passed.
  Confirms Tier-2 genuinely proves nothing about the deployed source; only
  Tier-1 is the real regression guard. Restored the diff via `git apply`
  afterward and confirmed `git diff --stat` matched pre-revert exactly.
- **`<option>` sink text-content-equality reasoning holds up under the
  real WHATWG HTML5 "in select" insertion mode**: character tokens are
  inserted as text regardless of mode, but disallowed start tags
  (`<img>`, `<svg>`, etc.) are tokenized-and-dropped as a whole unit —
  meaning an element-absence check would pass identically whether or not
  escaping happened (false confidence), while a raw (unescaped) payload
  containing `<`/`>` either gets consumed whole by a dropped tag token or
  otherwise breaks the literal-text run, so text-content-equality
  correctly diverges between escaped/unescaped. Confirmed the sink is a
  real `<select id="projCustomer">` (4 occurrences), so the reasoning's
  premise applies. No jsdom/headless browser available in this
  environment to empirically double-check (repo genuinely has neither,
  matching the test file's own comment) — this part rests on spec
  knowledge, flagged here in case a future reviewer has jsdom access and
  wants to confirm harder.
- **Completeness**: read `loadUsersList`/`loadCrmList`(both blocks)/
  `populateCustomerDropdown` in full from HEAD. `u.id`/`u.active` are
  `int` in `models.py`'s `User` dataclass (not user-controlled strings) —
  correctly left unescaped. `Customer`/`Project` fields all `str`/
  `Optional[str]`, all covered.
- **escapeHtml null-safety**: `(unsafe || '').toString()` (2 of the 3
  definitions in this file) / `if (!unsafe) return ''` (3rd) — both
  null-safe, so `escapeHtml(c.email || '')` (coalesce-then-escape) and a
  hypothetical `escapeHtml(c.email)` alone would behave identically for
  `None`; no "null"-string regression either way. All 4 fixed sinks live
  in the same `<script>` block (2723-4860) as the `escapeHtml` at line
  3204 (verified via `<script>` tag line boundaries) — the test helper's
  regex grabs the file's *first* `escapeHtml` definition (line 1558) by
  accident but it's byte-identical to the in-scope one, so this doesn't
  matter in practice.
- **`loadAuditLogs()` "latent, not live" claim verified independently**:
  `routes.py:1323` returns `{"audit_logs": [...]}`; the frontend guard at
  the call site checks `data.entries` (never `data.audit_logs`) — the
  render branch genuinely never executes today. Confirmed this is a real
  gap in the same unescaped-interpolation pattern (`e.action`, `e.details`)
  that would need the same fix if `NEW-449`/whatever renames the key
  later — this file's not yet logged in `NEW_ISSUES.md` (`git status`
  confirmed no NEW_ISSUES.md changes in this round) — coordinator needs
  to log it per rule 8 before/with this commit, not a code-reviewer
  blocker but a required follow-up.
- `pytest tests/test_restoricon_core/ tests/test_user_management.py -q`
  → 689 passed in 111.60s (matches claim exactly).
  `test_web_surfaces_js_syntax.py` → 9 passed (NEW-503 class of bug not
  reintroduced).

## Lesson

When a test suite claims a "mechanism-only" tier that doesn't read live
source, don't just read the docstring — actually revert the fix in a
scratch copy and rerun to see which tests fail. This is cheap (a
`cp`+`git checkout --`+`git apply` round-trip) and is the only way to
falsify a claimed negative control rather than trust the implementer's
report of having run it. See also
[[cloud_ultrareview_f1_f8_inline_handler_json_stringify_changes_requested]]
for the JSON.stringify-in-attribute half of this same `NEW-481` bug.
