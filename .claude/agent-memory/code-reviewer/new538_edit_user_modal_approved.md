---
name: new538-edit-user-modal-approved
description: NEW-538 admin Edit User modal (role/profile-field edit) — APPROVED after full independent live+JS verification, 2026-09-16
metadata:
  type: project
---

NEW-538 (`restoricon_core/api/web_surfaces.py` `render_admin_surface()`): new
Edit User modal (role/full_name/email/phone/department) wired to existing
`GET`/`PUT /api/v1/users/{id}` (`AuthService.update_user`), zero backend
changes. APPROVED 2026-09-16 — no Critical/Warning findings after:
- reading `update_user()` + its route directly (active→400, PATCH→404,
  role-change token revocation with no self-exemption all confirmed by
  reading the code, not trusting the implementer's description)
- a real Node `vm` harness executing the actual rendered `<script>` block
  (not grep) — role-changed/no-change/ai_agent-dynamic-option/leftover-option
  cleanup scenarios all behaved correctly
- a real HTTP round-trip against `RestoriconAPIServer(db_path=":memory:")`
  (GET→PUT→active-400→PATCH-404), matching the implementer's live-verify
  claims exactly
- full test suite reproduced verbatim (1932 passed, 1 skipped, 212.85s)

**Why this one's worth remembering:** the advisor flagged a plausible-looking
blocking concern (GET response might omit `phone`/`department`, causing a
silent field wipe on every edit) that turned out to be wrong once checked —
`User.to_dict()` is `asdict(self)` and both fields are real dataclass fields.
Advice from advisor is a hypothesis to check empirically, not a verdict to
adopt — checking it here took one `grep`+one live round-trip and closed it
cleanly rather than either blindly trusting or blindly dismissing it.

**How to apply:** for any admin-surface edit-modal review, (1) verify the
GET-response shape backing the modal's population actually matches what the
JS assumes (read the model's `to_dict()`/serializer, don't assume symmetry
with the create form), (2) build a real vm harness, not string-level
assertions, for any non-trivial modal JS logic — see the harness-in-progress
gotcha below.

See also [[vm_harness_silent_stub_gaps]] for a reusable trap in this
verification technique.
