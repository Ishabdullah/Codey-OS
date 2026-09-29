---
name: aigentik-email-signature-crlf-approved
description: buildEmailSignature CR/LF strip round (Codey-Aigentik llama.js) — APPROVED
metadata:
  type: project
---

Round 2 follow-up: `buildEmailSignature` in Codey-Aigentik `llama.js` now
routes dashboard-typed contact values (phone/email/license) through
`clean(v) = (v||'').toString().replace(/[\r\n]+/g,' ').trim()` and
`has(v) = v.length > 0`.

**Why:** pasted multi-line dashboard value could inject fake apparent
signature lines (`\nFake: ...`).

**Verified APPROVED 2026-09-10:**
- `has()` null/''/'   '/newline-only/present cases all identical to old
  `(v||'').toString().trim().length>0`.
- Both text and html branches use the pre-cleaned vars — collapse applies
  to both. html template has no literal `\n` anyway.
- `escapeHtml(str)` calls `str.replace` — `clean()` guaranteeing a string
  actually fixes a latent throw if a non-string ever reached the text
  branch's interpolation. Net improvement.
- New test discriminates in BOTH branches (text `/\nFake:/`, html
  `not.toContain('\n')`) — fails without the `.replace`.
- `npm test`: 286 passed, 20 suites. Matches implementer claim.
