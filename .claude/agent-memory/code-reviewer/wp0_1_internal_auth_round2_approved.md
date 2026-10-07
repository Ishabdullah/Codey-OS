---
name: wp0_1_internal_auth_round2_approved
description: WP0.1 (NEW-764) Aigentik internal-auth round2 — all 3 round-1 CR findings fixed and independently reverified — APPROVED
metadata:
  type: project
---

Round1 CR found 3 issues in `Codey-Aigentik/internal-auth.js` + `http-server.js` + `Codey-OS/install.sh`
(the shared-secret gate for Aigentik's loopback HTTP server, `/send-email`,
`/send-invite`, `/send-cancellation`). Round2 fixed all three; re-verified
each independently rather than trusting the fix description:

1. **Cache-poisons-on-ENOENT fix** (`readTokenFile()` only caches a
   successful non-empty read) — verified via `node --experimental-vm-modules
   jest` on `tests/internal-auth.test.js` (2/2 pass: miss-then-appears,
   and cache-sticks-after-found).
2. **`install.sh`'s `-f`→`-s` + umask-scoping fix** — verified live by
   sourcing just the function in an isolated `HOME` via
   `sed -n '/^setup_aigentik_internal_token()/,/^}/p' install.sh`: confirmed
   `umask` unchanged before/after the call (0022→0022, the `( umask 077; ... )`
   subshell doesn't leak), 600-mode/65-byte token produced, idempotent on
   rerun (byte-identical), and zero-byte-file recovery (removes it, warns,
   doesn't claim success).
3. **Auth-before-body-read fix** (`checkAuth()` split out, called before
   `readJsonBody()` in all three routes) — verified by reading
   `http-server.js` in full (not just the diff) and running
   `tests/http-server.test.js` (10/10 pass incl. malformed-body-gets-401-not-500).

**Advisor caught two gaps round2 almost missed by trusting `git diff`
output over the full file:**
- `git diff` truncates at the end of the `createServer` handler —
  `server.listen(PORT, HOST, ...)` (the actual bind-address line, this
  project's known C-2 risk class) was never in the diff and had to be
  read directly from the file to confirm it binds `127.0.0.1` not `0.0.0.0`.
- The `isBlocked()`-throws path (do-not-contact.js throws rather than
  degrades when Core is unreachable — NEW-311 decision) had zero test
  coverage; all 10 existing tests only used `mockResolvedValue`. Wrote an
  ad-hoc throw-mock test confirming the throw lands in the same `try` as
  `readJsonBody`/`checkNotBlocked` → 500, `sendEmail` never called — no
  fall-through-to-send on Core-down. This is the one failure mode where a
  bug would mean actually re-contacting a suppressed person, so it's the
  single most important path to check by execution, not by reading the
  nesting.

**Lesson:** reading only the hunks `git diff` shows is not "reading the
file in full" — a diff can truncate exactly at the security-relevant line
(the bind call) that sits just past the last changed hunk. When a task
says "read in full," actually open the file, especially near rule-4/C-2
territory (binding, auth, kill logic).

See also [[wp2_3a_sandbox_ccos_allowed_dirs_removal_approved]] for the
broader WP0/WP1/WP2 census-roadmap batch this sits in.
