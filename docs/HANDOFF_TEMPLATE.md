# Handoff template

Created 2026-10-27 (WP2.1 closing pass). No handoff template existed before
this; root `HANDOFF.md` is an archived dated snapshot (2026-10-13), not a
template. Copy this file to `docs/<WP>_HANDOFF_<date>.md` and fill it in. A
handoff is a dated snapshot and navigation aid, not an authoritative rules
document or work register.

## 1. Start here
Which docs to read first (`AGENTS.md`, blueprint §1/§21, `CLAUDE.md`,
`CODEY_MASTER_PLAN.md` §2), the exact production HEAD hash and whether
`origin/main` equals it (verify with `git rev-parse HEAD origin/main`), and
what is open or closed.

## 2. Current result, approvals and exact resume points
One table per unit of work: state, counts, and the exact artifact (path + SHA256)
to resume from. Distinguish code-complete / reviewer-approved / live-verified
(rule 7) for every line.

## 3. Committed vs scratch-only
Required section. Three lists, no overlap:

- **Committed:** commit hash and the exact paths (`git show --stat <hash>`).
- **Working tree, uncommitted:** every modified or new path in
  `git status --short`, who owns it (this task or a foreign edit to preserve),
  and whether it has been independently reviewed.
- **Scratch only:** paths outside the repo (for example the `/data/data/com.termux/files/usr/tmp/...`
  work directory), with size, whether they are volatile, which are immutable
  evidence, and which durable copies exist in the repo (with the manifest file
  that pins their hashes). Anything cited by a claim must be in the repo or
  listed here with its SHA256, never assumed to still exist.

## 4. Tests and findings
Raw counts first (`N passed / M failed / K skipped`, verbatim), then effective
counts with the reason for any difference; the list of failing node ids; last
allocated `NEW-###` id; findings opened, with their `trigger:` tags (rule 8).

## 5. Rules in force and operating limits
Concurrency cap, RAM discipline (rule 2), no name-pattern kills (rule 3),
staging by exact path (never `git add -A`), foreign work to preserve.

## 6. Decisions: already made vs pending
Cite the ledger entry for each decision. A decision known only from a coordinator
brief says so. Never re-ask a recorded decision.

## 7. Resume order and resume prompt
Ordered steps; then a short copy-paste prompt that points back at this file.
