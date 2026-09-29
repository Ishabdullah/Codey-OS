---
name: b9_2_round2_branch_divergence_approved
description: Phase B9.2 round2 (lock-on-accept, cost-gate, NEW-707 correction, estimates rename migration) — APPROVED, but surfaced a serious branch-divergence hazard behind Fix 4
metadata:
  type: project
---

Round 2 of [[b9_2_estimate_service_changes_requested]] (branch
`feat/estimator-phase3-schema`, 2026-09-29). All 4 fixes verified clean:
Critical lock-on-accept fix (conditional `_lock_version_write()` call is
correct, not a loophole — an unconditional call would ValueError-abort the
whole decision transaction against the DB trigger), line-cost gating (13
fields correctly gated, `price_override_cents`/`line_total_cents` correctly
left visible so customer still sees a coherent charge), NEW-707 correction
(mostly accurate, one wording overclaim I caught by re-running the isolated
test and getting the opposite result from round 1 — see
[[sandbox_proxy_test_artifact]]/[[b9_2_estimate_service_changes_requested]]
for the sibling flake classes), and a live-production migration fix
(`_migrate_estimates_table_v2()`'s `assigned_user_id` -> `assigned_to_user_id`
rename).

**New pattern worth remembering: verify a migration docstring's own cited
git commit, don't just trust that the cited commit shows what it claims.**
The implementer's docstring said "confirmed by reading `git show 1ac1e25^`'s
pre-migration schema" — I checked, and that commit's `estimates` table
does NOT have `assigned_user_id` at all. The real source was a *different*,
unrelated-looking commit (`a2c88d6`, an ALTER TABLE ADD COLUMN from a much
earlier B8.6a round) that happens to be on `main` but not on this feature
branch. Following the citation literally would have produced a false
"doesn't check out" result; the actual truth required tracing the column
across the WHOLE git history (`git log -S`), not just the one commit named.

**Bigger finding, from just checking "is this citation accurate": this
feature branch is ~30 commits behind `main`**, missing entire features
(ROLE_SUBCONTRACTOR, package_options pricing, invoice line items,
customer_credits ledger, multi-party contract signing, comms RBAC
narrowing) that are already live in the production DB (built by `main`'s
migration chain). This is NOT something the task asked me to check — it
surfaced purely from tracing one column-rename claim. Confirms CLAUDE.md's
"working alongside another agent" doc-collision warning applies to whole
BRANCHES too, not just the three tracking docs: two agents/sessions can
develop against divergent bases against the SAME live production DB.

**Checked whether this branch's OTHER full-table-rebuild migration
(`_migrate_users_role_constraint()`, same hazard class: DROP+recreate
gated on CHECK-constraint text) would silently narrow the live `users.role`
CHECK by dropping `'subcontractor'` (added on `main` post-divergence, not
known to this branch). It does NOT fire — the gate is keyed on `'sales_manager'`
already being present in the live schema's stored SQL, which it is (added
earlier on `main`), so the branch's rebuild is a permanent no-op against
the real DB. Safe by gate-text-ordering coincidence, not by design
foresight. Lesson: when a branch is stale relative to what's actually
deployed, EVERY full-table-rebuild migration (not just the one the task
names) is a candidate for silent narrowing and needs its gate condition
traced against the real live schema text, not assumed safe by analogy to
a sibling fix that already checked out.

**Verdict:** approved the 4 fixes on their own merits (each independently
verified live/empirically), but explicitly told the coordinator not to
treat this as "safe to run `codey start`" — recommended escalating the
branch-divergence to Ish as a product-direction question, and a
live-verifier pass against a DB COPY exercising the FULL `init_schema()`
chain (not just the one migration function the task named) before any
real restart attempt.
