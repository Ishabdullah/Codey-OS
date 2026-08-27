---
name: phase_b2_task4_dnc_writethrough_approved
description: Phase B2 task 4 do-not-contact.js Core write-through pilot (Codey-Aigentik) + provision_ai_agent_auth.py — approved, no blocking findings
metadata:
  type: project
---

Reviewed 2026-08-27: `~/Codey-Aigentik/do-not-contact.js` (rewritten to
async Core HTTP calls), `index.js`/`owner-command.js` (call sites converted
to `await`), `install.sh`/`docs/configuration.md` (`core_api` config block),
`tests/do-not-contact.test.js` (new, 18 tests); Codey-OS side:
`tools/provision_ai_agent_auth.py` (new) + `tests/test_provision_ai_agent_auth.py`
(new, 4 tests). **Approved.**

Verified directly (not from implementer's summary):
- The `.forEach()`/`.filter()` → `for...of` conversion in `owner-command.js`
  (`handleBlockContact`/`handleUnblockContact`) is correct: sequential
  `await` inside the loop, no async-in-sync-callback survivors. Grepped
  every `doNotContact.` call site across `index.js`/`owner-command.js`/
  `role-router.js` (14 total) — all awaited, all inside `async function`
  scopes (checked the enclosing function signatures, not just the call
  site).
- `coreRequest()`'s parse-error handling is correct: a 2xx with an
  unparseable JSON body sets `data: null, parseError: e` and folds into
  `ok: response.ok && !parseError`, so every caller's `if (!ok) throw`
  catches it. Covered by a real test
  (`'throws ... on a 200 with an unparseable body'`) that mocks
  `json: async () => { throw new SyntaxError(...) }` — not just asserted
  in a comment.
- Core-only/no-fallback: all 4 exported functions throw on non-2xx/network
  failure (traced `isBlocked`/`addToDoNotContact`/`removeFromDoNotContact`/
  `loadEntries`, each has its own `if (!ok) throw new Error(...)`). The one
  intentional non-throw is `addToDoNotContact`'s `status === 400` ->
  `return null`, which I verified against `restoricon_core`'s actual route
  (`routes.py`) and service (`automation_service.py`'s
  `add_to_do_not_contact`) — 400 on that route is emitted *only* for
  "identifier could not be classified" (no other `ValueError` path exists
  in that method), so the special-case doesn't mask any other failure mode.
- `classifyIdentifier()` gate applied consistently before every one of the
  4 Core-calling functions (checked each function body directly) — no
  code path reaches `coreRequest` with an unclassified identifier.
- Config/secret hygiene: `~/Codey-Aigentik/config.json` is gitignored by
  a literal `config.json` line (not the broader `*token*` pattern) —
  confirmed via `git check-ignore -v`; real local token
  (`Jv3LGdCl...`) exists on disk but is untracked/ignored, not in any
  diff. `provision_ai_agent_auth.py`'s deliberate non-"token" filename
  correctly avoids the Codey-OS repo's `*token*` gitignore pattern —
  confirmed via `git check-ignore -v` on both new files (exit 1, not
  ignored, will actually get committed as intended).
- `provision_ai_agent_auth.py` matches `restoricon_core/auth.py`'s real
  `create_user`/`create_token` signatures (read the file directly, not
  assumed). Idempotency: re-running with the same `--username` reuses the
  existing user (SELECT-before-create, single row on repeat), and
  correctly raises on a username collision with the wrong role — both
  behaviors have dedicated tests. The one non-idempotent aspect (each
  rerun issues a *new*, never-revoked token, so old tokens accumulate) is
  honestly documented in the script's own docstring and
  `docs/configuration.md`, not hidden — acceptable, not a defect, since
  nothing revokes-on-provision was ever claimed.
- Zero changes to `~/Aigentik-CLI` (the live original) — confirmed via
  `git status --short` / `git diff --stat` there (only an unrelated
  pre-existing untracked `.agents/` dir).
- Doc hygiene (rule 7): `CODEY_MASTER_PLAN.md`/`PROJECT_LOG.md` diffs
  correctly say "code-complete + tested against a locally-started Core
  instance, NOT live-verified against real `~/Aigentik-CLI` production
  traffic" — no overclaim.
- Test suites run and pasted verbatim: JS `npm test` → 122/122 passed (8
  suites, including the new 18); Python `pytest tests/` → 774 passed, 1
  skipped (includes the new 4 in `test_provision_ai_agent_auth.py`,
  confirmed running via a scoped `-v` invocation too).

**No blocking findings.** The task's own out-of-scope logging (NEW-224:
subcontractors rejected as pilot module for lacking a general-update Core
route; NEW-225: Core API never yet run against its real persistent DB/a
separate OS process) is honest and correctly filed as context, not hidden.

**Reusable technique:** when a diff adds a status-code special-case
(`if (status === 400) return null` before the generic `!ok` throw), don't
just trust the comment saying "matches pre-existing behavior" — grep the
*actual server-side route handler* for every code path that can produce
that status code, to confirm the special-case doesn't inadvertently
swallow an unrelated failure mode alongside the intended one.
