---
name: wp0_2_notification_audit_approved
description: WP0.2 notification_service audit-gap closure (crm_service.py PM-assignment + routes.py compose-email) — APPROVED
metadata:
  type: project
---

Closed the audit gap at `notification_service.py`'s two real call sites
(confirmed via grep — only `crm_service.py:3188` PM-assignment email and
`routes.py:2852` B8.10c compose-email route actually call it). Both already
had adequate RBAC on *triggering* the send; the gap was that the send
itself (success or failure) left no record. Added `notify_email_sent`/
`notify_email_failed` audit.log calls at both sites, `bool(...)`-wrapped
the `send_email` return to avoid a MagicMock-not-serializable bug caught
in testing. 25/25 tests pass verbatim.

Two checks worth remembering for next time this shape of finding recurs:

1. **`build_audit_details(after={...})` with no `before=`/`fields=` is not
   an empty-envelope bug** — it populates `{"old": None, "new": <value>}`
   per key, confirmed empirically:
   `build_audit_details(after={'to':'a@b.c','sent':True})` →
   `{'changed_fields': {'sent': {'old': None, 'new': True}, 'to': {...}}}`.
   This is also the dominant existing pattern in `crm_service.py` (25+
   other `after=`-only call sites, e.g. `pdf_generation_failed`). Don't
   assume an unguarded single-site read of the signature tells you the
   runtime behavior — advisor correctly pushed on this even though it came
   back clean; it was a one-line check worth doing every time this pattern
   shows up, not just this once.
2. **Rule-6 "downgrade a stale claim" needs to land in the *authoritative
   doc*, not just NEW_ISSUES.md.** This round's `pdf_service` claim (that
   it has an audit gap) was false — both its success and failure paths
   were already audited — but `CODEY_OS_MASTER_BLUEPRINT.md` §21 (the
   live roadmap, lines ~1751-1752, ~2125-2129) still asserts the gap.
   Flagged this as a commit-blocking follow-up: the correction belongs in
   the blueprint text itself.

See also [[working_tree_cross_round_bleed]] — this round's `git status`
had WP0.1's already-approved-but-uncommitted internal-auth changes
(`notification_service.py` itself, `utils/config.py`, `install.sh`) sitting
in the same tree as WP0.2's edits. Confirmed via the untracked
`wp0_1_internal_auth_round2_approved.md` memory file that WP0.1 was a
separate, already-reviewed round — told the coordinator to stage the two
rounds as separate commits rather than risk `git add -A` conflating them.
