---
name: phase_b2_task4_email_sms_rules_writethrough_approved
description: Phase B2 task 4's second write-through module (email-rules.js/sms-rules.js + new delete_rule/route) — approved, no blocking findings
metadata:
  type: project
---

Reviewed 2026-08-27: Codey-OS `restoricon_core/services/automation_service.py`
(new `delete_rule`), `restoricon_core/api/routes.py` (new
`POST /api/v1/automation-rules/{id}/delete`), new tests in
`test_operations_services.py`/`test_api.py`, `NEW_ISSUES.md` (NEW-231);
Codey-Aigentik `email-rules.js`/`sms-rules.js` (rewritten to Core HTTP,
each with its own `coreRequest()`), `index.js`/`owner-command.js` (await
conversion), new `tests/email-rules.test.js`/`sms-rules.test.js` (28
tests), `docs/data-files.md`/`docs/rules.md`. **Approved.**

Verified directly (not from implementer's summary):
- `delete_rule()`'s RBAC (`PERM_WRITE_AUTOMATION_RULES`) matches
  `create_rule`'s gate exactly (read both side by side). Its
  conditional-audit-log-only-on-actual-deletion behavior matches
  `remove_from_do_not_contact`'s real code (read that method directly,
  not the docstring's claim) — both skip `audit.log()` when
  `cursor.rowcount == 0`.
- Route convention: new route is `POST .../automation-rules/{id}/delete`,
  returns `{"deleted": <bool>}` at 200 always, including on an
  already-gone id (never 404) — confirmed against the sibling
  `POST /api/v1/do-not-contact/remove` route which has the exact same
  shape (`{"removed": <bool>}`, always 200). Grepped the whole file for
  `'PUT'`/`'DELETE'` HTTP verbs — zero matches, confirming the
  action-suffix-on-POST convention is unbroken.
- `list_rules()`'s actual SQL (`ORDER BY id DESC`, `WHERE channel = ?`
  when a channel filter is passed) matches the JS files' claimed
  precedence/channel-isolation contract exactly — read the query
  construction directly, not assumed from the docstring comment.
- `coreRequest()` is byte-identical (modulo the module-name string in
  log calls) across all three copies now: `do-not-contact.js`,
  `email-rules.js`, `sms-rules.js`. No copy-paste divergence on the
  parse-error-as-failure or network-error-rethrow paths.
- All Core-touching call sites in `index.js`/`owner-command.js` converted
  to `await` (grepped every `emailRules.`/`smsRules.` call site
  repo-wide, 11 total) and all enclosing functions confirmed `async`.
  The one unconverted call (`emailRules.isPromotional` passed as a sync
  callback to `gmail.spamMatchingEmails`) is correctly untouched — pure
  function, no Core I/O.
- NEW-228 (dead `message_contains` rule for email) survives unmodified —
  confirmed no case added to `email-rules.js`'s switch, and a dedicated
  test (`'has no message_contains case (NEW-228)'`) asserts it still
  falls through to default with zero `/match` calls.
- NEW-231's claim (no `last_matched` column, but `updated_at` is
  refreshed on every match so the info isn't fully lost) verified
  directly against `record_rule_match()`'s actual `UPDATE ... SET
  match_count = match_count + 1, updated_at = ?` — accurate.
- `config.json`'s `core_api` block confirmed restored/unchanged from the
  prior DNC-pilot round's already-verified value (same `base_url`, same
  token prefix `Jv3LGdCl...`) — not left pointing at a scratch server.
  File is gitignored so `git diff` can't show this; had to read it
  directly and cross-check against the prior round's memory record.
- Zero changes to `~/Aigentik-CLI` (confirmed via `git status --short` /
  `git diff --stat` there — only a pre-existing untracked `.agents/`
  dir).
- Test suites run and pasted verbatim: JS `npm test` → 150/150 passed
  (10 suites, includes the new 28); Python `pytest tests/` → 778 passed,
  1 skipped (includes the new 6).
- Honest scope limitation in the new JS test files: rule-precedence and
  channel-isolation are explicitly *not* asserted via the mocked-fetch
  unit tests (a mock can't prove the real server's `ORDER BY`/`WHERE`
  behavior) — deferred to live-verification, stated plainly in both
  test files' header comments rather than papered over with a
  false-confidence mock assertion.

**Minor, non-blocking:** `NEW-230`'s pre-existing write-up (from the
prior spec-only commit, not touched in this diff) says the new method
would be "audit-logged like `create_rule`" — the actual implementation
is closer to `remove_from_do_not_contact`'s *conditional* audit-log
(only on actual deletion), not `create_rule`'s unconditional one
(`create_rule` always logs, since a create always succeeds). Cosmetic
inaccuracy in an already-committed doc entry, not something this round
introduced or needs to block on.

**No blocking findings.** This is code-complete + tested against the
mocked Core API / a real Core instance for CRUD shape, **not**
live-verified against real `~/Aigentik-CLI` production traffic
end-to-end (matches the DNC pilot precedent's caveat).
