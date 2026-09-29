---
name: b8_6d_b_round2_atomicity_fix_approved
description: B8.6d-b round 2 — NEW-593 atomicity fix APPROVED after live crash-injection re-verification; advisor caught 2 new non-blocking issues a diff-only re-review missed
metadata:
  type: project
---

2026-09-22, B8.6d-b round 2 (contract_signers atomicity fix, following
[[b8_6d_b_multi_party_signer_party_role_spoof_changes_requested]]).
**APPROVED** — the round-1 Critical (non-atomic status flip) is
genuinely fixed: both the `contract_signers` UPDATE and the conditional
`contracts.status='signed'` UPDATE now sit in one `with conn:` block,
UPDATE-then-COUNT ordering preserved (not count-then-update, which the
implementer's own draft-history correctly identified as a *different*
race: two concurrent last-signers could each read "1 other pending" and
neither would flip status).

**Verified the SQLite locking claim, not just accepted it.** Confirmed
`DatabaseManager.get_connection` (`database.py:1227`) uses default
`isolation_level` (Python's legacy transaction control — implicit BEGIN
before the first DML statement in a `with conn:` block), WAL journal
mode, `timeout=30.0`. WAL still serializes writers project-wide (single
writer at a time), so the first `UPDATE` inside the block takes the
write lock and holds it until commit, genuinely blocking a concurrent
signer's UPDATE from interleaving before the COUNT — the implementer's
reasoning is real SQLite behavior for this codebase's actual connection
settings, not assumed.

**Independently reproduced the discriminating-test claim, don't just
trust it.** Backed up `crm_service.py`, split the single `with conn:`
block back into the pre-fix two-block structure (update signer row,
commit, THEN count+conditionally update status), ran
`test_sign_contract_final_signer_status_flip_is_atomic` in isolation —
it failed with the exact predicted corruption (signer row committed,
`contracts.status` still unsigned). Restored the fix from backup,
re-ran — passes, diff stat identical to original (314 changed lines),
confirming no residue left in the tree. This is the gold-standard
version of the "verify claims independently" pattern this project's
history keeps demanding (NEW-259 precedent) — don't just read the test,
run it both ways.

**Full suite: 2225 passed, 1 skipped**, matches the implementer's claim
verbatim (`python -m pytest -q` from repo root, proxy vars unset,
305.68s, no hang this round). Sanity-checked arithmetically per the
NEW-512 lesson: round B8.6d-a's own approved baseline was 2214 passed
([[b8_6d_a_contract_pdf_service_approved]]); this round's new test file
adds exactly 11 tests; 2214+11=2225 — rules out a silently
lost/newly-skipped test that a bare "2225 matches" check would not.

**Two new non-blocking findings the advisor caught that a diff-only
re-review missed (logged, not fixed — correctly out of round-2 scope):**
1. The PDF-persistence side effect now runs on every partial multi-party
   signature, not just at completion (`signed_contract_signers is not
   None` branch) — filename includes `int(time.time())`, so a 4-signer
   contract produces 4 PDFs + 4 Document rows with no marker for which
   is authoritative (most-recent by created_at is recoverable, but
   undisclosed doc-store growth). Warning, not blocking.
2. `contract_signers` has no `UNIQUE(contract_id, party_role)` and
   `add_contract_signers` has no idempotency guard — live-reproduced:
   calling `add_contract_signers` twice with the same party_role creates
   duplicate unsigned rows, and the role-derivation path in
   `_resolve_contract_signer_row` then permanently raises "Cannot
   determine which signer role" for that party (neither
   `len(unsigned_candidates)==1` nor `len(candidates)==1` holds with 2
   duplicates). Looks like the round-1 Critical's bug family (new code,
   stuck-contract shape) but is NOT equally severe: recoverable via
   explicit `party_role=` (live-verified: first explicit-party sign
   leaves status draft, second explicit-party sign reaches "signed").
   Warning tier. Fix direction: `UNIQUE(contract_id, party_role)` +
   `INSERT ... ON CONFLICT DO NOTHING`, or an existence check in
   `add_contract_signers`.

**Scope-discipline claim — stated the actual basis, not just "confirmed
via diff":** nothing is committed yet, so there is no git artifact for a
round1→round2 delta; the cumulative diff is the whole B8.6d-b feature.
Basis was (a) re-reading the full cumulative diff against the round-1
memory record's description of every other piece (legacy path,
`_resolve_contract_signer_row`, PDF y-constants, audit `side_effects`)
and confirming byte-for-byte match, plus (b) the revert experiment,
which reconstructed exactly the two-block structure round 1 described
and reproduced exactly the failure round 1 proved.

**Explicitly declined to escalate (per advisor, matches round-1's own
lesson):** the pre-transaction TOCTOU on `row["status"]`/`signer_rows`
reads, and the unconditional `SET status='signed'` with no
current-status guard, are both present verbatim in the pre-existing
legacy single-signer path — carried-over semantics, not a new
regression, same trap round 1's `[[b8_6d_b_multi_party_signer_party_role_spoof_changes_requested]]`
warns about (differential before calling something a regression).

**Technique note:** the crash-injection test technique (poison
`sqlite3.Connection` subclass via `factory=` on a fresh connection
sharing the fixture's `cache=shared` in-memory URI, monkeypatching
`db.get_connection`) is now proven reusable and independently
verified twice (round 1's live manual crash-injection, round 2's
revert-and-rerun of the automated test). One gap noted for future
reuse: the poison connection in the test skips `PRAGMA foreign_keys =
ON` that `db.get_connection` normally applies — harmless for this
test's assertions, but a future FK-dependent reuse of this pattern
would behave differently and should add the pragma.
