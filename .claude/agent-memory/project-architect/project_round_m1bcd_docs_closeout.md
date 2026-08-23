---
name: round-m1bcd-docs-closeout
description: M1-B/C/D (config repoint, spawn flags, planner collapse) doc closeout 2026-08-23 — code-complete + reviewer-approved, NOT committed, no live component
metadata:
  type: project
---

M1-B/M1-C/M1-D (Qwen3.5-4B migration: config repoint, `--jinja`/
`--reasoning-format` spawn flags, planner-server collapse) reached
code-complete + two-pass code-reviewer-approved on 2026-08-23, but was
**deliberately left uncommitted** at the time of this docs-only round —
project-architect updated `CODEY_MASTER_PLAN.md`/`NEW_ISSUES.md`/
`PROJECT_LOG.md` to reflect that exact state without committing anything
or touching any source/test file.

Findings closed this round (all confirmed by direct code read, not by
the model-migration decision alone, per [[project_new56_recursive_hypothesis_refuted]]-style discipline of verifying reachability before closing): `NEW-161`, `NEW-100`,
`NEW-101`, `NEW-124`, `NEW-142`. Partially closed: `NEW-99`/`NEW-103`
(only the 8081 half — `codeydOS`'s 8080-pattern `pkill` sites remain
open). Left explicitly NOT closed despite the temptation to tick them off
on the decision: `NEW-137`, `NEW-140` scenario 3, `NEW-141`, `NEW-143` —
these needed BOTH a code-read (done) AND M1-E's live numbers (not done)
per `NEW-159`'s own disposition note; a prior "closed by retirement" line
in §4.3 for `NEW-137`/`NEW-143` was corrected under rule 6 as
overstated. New finding this round: `NEW-163` (lora_import.py rollback
writes base weights into the fine-tuned file's name) — logged by the
implementer, not this session, already fully written up.

**Why this matters for future rounds:** the ledger's convention for
closing a finding is to append a new `**Status: CLOSED/RESOLVED,
<date>.**` bullet to the END of the existing entry, not to rewrite the
entry's header or its original "Not fixed" line — see `NEW-102`'s
resolution note for the pattern this project already established, which
this round followed for `NEW-161`/`NEW-99`/`NEW-100`/`NEW-101`/`NEW-124`/
`NEW-142`.

**How to apply:** when closing out a code-complete-and-reviewed-but-
uncommitted round, verify test counts and code deletions yourself
(re-ran `pytest tests/` → 647 passed/1 skipped, `pytest ccos/tests/` → 68
passed, both matched the brief exactly) rather than trusting the
handoff's numbers — this is a docs-only round, but rule 5 still applies
to what gets written down.
