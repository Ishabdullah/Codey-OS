---
name: telemetry-batch-new354-360-361-362-stale-ledger-citation
description: Batched low-risk fix round (NEW-354/360/361/362) — CLI JSON-array fix approved, but a user-facing message citing a NEW-## ledger entry as "unresolved" was itself wrong because the ledger entry was stale
metadata:
  type: feedback
---

Round covered 4 deferred findings: docs corrections (NEW-354 meta-vs-device
body fields, NEW-362 stale call_site example), and `telemetry/cli.py`'s
`provenance --all --json` fix (NEW-360/361: array-wrapper output +
docstring). The CLI fix was clean — verified by tracing control flow
(early-return before the old print("") loop, collect=None default keeping
single-run path untouched) and an independently-run new regression test.

The blocking bug was in a message the *coordinator* added post-implementer
to `main.py`'s `--import-lora` success path: it cited `NEW-24` as a "known
unresolved bug" in the `coding.finetune_rollback_backup` capability that
"can leave no working model at all." Grepping the actual current code
(`core/lora_import.py`) showed `load_secondary()` — NEW-24's actual
mechanism — has zero live call sites; the function has its own inline
comment documenting the bug was fixed, later further collapsed by M1-D
(2026-08-23). `NEW_ISSUES.md`'s NEW-24 entry still read "Status: Confirmed,
not fixed" (line 1888), never updated — contradicted by a *later* entry
(NEW-84) that says "NEW-24's own fix... is correct and complete." A
user-facing warning built on a stale ledger citation is a real bug, not a
wording nitpick: it misdirects users into an unnecessarily risky manual
workaround and points suspicion at code that's actually fine.

**Lesson — new pattern to check for:** when a diff has a human-readable
message (log line, CLI output, docstring) that cites a `NEW-##` finding ID
to justify a claim, don't trust the ledger status at face value. Grep the
*actual current code* the citation is about before accepting the claim.
Ledger entries get superseded by later entries/fixes without their own
status line ever being updated back — this project has now hit that
exact staleness class twice at least (NEW-24 here, itself found via NEW-84
also possibly being stale). When you find one, don't just flag the citing
diff — flag correcting the stale ledger entry itself as a required fix in
the same round (CLAUDE.md rule 6), since leaving it stale guarantees the
next writer (human or agent) repeats the same wrong citation.

Also worth the extra step: when a message claims a specific *consequence*
("can leave no working model at all"), trace whether the code's actual
control flow (order of copy/unlink/reload calls) supports that specific
outcome — don't stop at "the cited bug doesn't apply," also check whether
any mechanism at all produces the claimed consequence.

See also [[new189_fix_approved_plus_new194_role_keyed_scoping]] for a
similar pattern of a narrowing/fix leaving a superficially-plausible but
substantively wrong claim standing nearby.
