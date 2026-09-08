---
name: b6-2a-audit-details-round2-approved
description: B6.2a build_audit_details helper + details= on 9 user-mutation audit sites in restoricon_core routes.py — round 1 CHANGES REQUESTED (site 274 wrong enum in append-only ledger)
metadata:
  type: project
---

B6.2a (2026-09-02): module-level `build_audit_details()` + `_AUDITABLE_USER_FIELDS`
frozenset in audit_service.py; `details=` wired into 9 `audit.log()` calls in
api/routes.py. **Round 1: CHANGES REQUESTED. Round 2 (delta): APPROVED.**

Round 2 verified: site 274 now `"all_except_actor" if actor.user_id == user_id else "all"` with test_admin_resets_other_user_password_revokes_all asserting `== {"side_effects": {"sessions_revoked": "all"}}` + no plaintext/hash; docstring "can never reach serialization" now explicitly scoped to changed_fields with a sentence that side_effects/snapshot are verbatim/unfiltered and caller-owned; query_logs `ORDER BY timestamp DESC, id DESC`. B6.2a file 21/21. TOCTOU/site-331 + NEW-### entries owned by coordinator, not blocking.

**Blocker — site 274 (password):** logs fixed literal
`sessions_revoked: "all_except_actor"`. But `change_password`'s SQL is
`WHERE user_id=? AND token != <actor_token>`. When an admin resets ANOTHER
user's password, the actor's token is in a different user_id partition, so
EVERY target session is revoked — true value is "all". `audit_log` is strict
append-only (no UPDATE/DELETE anywhere in audit_service.py; `log()` is the only
writer) so a wrong value is permanent and uncorrectable. Fix:
`"all_except_actor" if actor.user_id == user_id else "all"`. Needs an assertion
covering the admin-resets-other branch — current tests only exercise
admin-changes-own (the correct-value case); the cross-user path runs in the
leak sweep but asserts nothing about sessions_revoked. Tautological-coverage
shape (cf. model_tiers_7_3_subtaskB).

**Blocker — docstring overclaim:** `build_audit_details` docstring says the
`fields` filter means a stray password_hash "can never reach serialization even
if the caller passes a fuller dict." True only for `changed_fields`. `snapshot`
and `side_effects` pass through verbatim, unfiltered. Not a live leak today
(both snapshot callers use `User.to_dict()` default = hash popped) but
`to_dict(include_sensitive=True)` is one kwarg away. Scope the sentence to
`changed_fields` or filter snapshot too. This project blocks on text that
misstates its own mechanism (NEW-212 inaccuracy, task2 migrate).

**Ledger:** TOCTOU finding + site-274 finding each need a NEW-### entry
(rule 8). Check `git diff --stat -- NEW_ISSUES.md` on return (cf. U.31).

**Warning (not blocking) — site 331 TOCTOU:** routes' `before` fetched
separately from update_user's internal re-fetch; concurrent role change by
another actor can make routes log "all"/"none" disagreeing with auth's actual
behavior. SQLite serializes writes; low severity.

**Suggestion:** `query_logs` orders by `timestamp DESC` with no `id` tiebreak —
`_last_details` rows[0] ambiguous on microsecond collision (test_activate logs
2 rows/entity). Implausible given intervening writes.

**Verified sound, keep as-is:** site 331 role-equivalence (echo/absent/real-change/
`if not set_clauses: return user` all match auth's role_changed); site 309
`before is None` unreachable (set_user_permissions raises ValueError->400);
sites 274/337 bool returns never feed `after=`; custom_permissions whole-value
compare (dict == order-independent, both round-trip _parse_custom_permissions);
allow-list correctly guards the post-commit unguarded json.dumps; leak sweep
covers all 9 reachable actions and reads the persisted details_json column.
Full restoricon_core suite 259 passed; new file 20 passed.
