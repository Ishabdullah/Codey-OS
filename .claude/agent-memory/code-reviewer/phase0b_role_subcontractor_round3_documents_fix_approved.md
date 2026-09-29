---
name: phase0b-role-subcontractor-round3-documents-fix-approved
description: Phase 0b/B8.16 ROLE_SUBCONTRACTOR round 3 (final) — PERM_READ_DOCUMENTS/PERM_WRITE_DOCUMENTS removal verified correct, all citations checked, 1291 passed, APPROVED closing all three rounds
metadata:
  type: project
---

Round 3 (final) of [[phase0b_role_subcontractor_round2_documents_gap_changes_requested]].
Implementer removed `PERM_READ_DOCUMENTS`/`PERM_WRITE_DOCUMENTS` from
`ROLE_PERMISSIONS[ROLE_SUBCONTRACTOR]` in `restoricon_core/auth.py`, same
pattern as the round-2 `PERM_READ_COMPLIANCE` fix. Verified independently,
not by trusting the summary:

- Final permission set is exactly `{PERM_READ_OPERATIONS,
  PERM_WRITE_OPERATIONS, PERM_LOG_COMMUNICATION}` — read the dict literal
  directly.
- `NEW-669`'s line citations all check out on direct read:
  `crm_service.py:6295`/`:6323` are the exact `if not
  actor.has_permission(PERM_READ_DOCUMENTS)` narrowing-skip lines;
  `routes.py:1554`/`:1734` are the exact unfiltered-list and
  raw-bytes-download handlers; `models.py:656` is the `permissions: List[str]`
  field, round-tripped at `crm_service.py:6262`(read)/`6354`(write) but never
  consulted in access-control — dead metadata claim confirmed by grepping
  `permissions` across the whole file.
- `NEW-668`'s entry (from round 2) is untouched/clean this round — no
  corruption from the same-round `NEW-669` edit landing right after it.
- Checked for a regression the implementer didn't flag: whether any UI
  surface reachable by a subcontractor now silently breaks. Traced
  `render_subcontractor_surface()` → `_render_staff_portal_base()`
  (`web_surfaces.py:5344-5481`) — self-contained, only calls
  `GET /api/v1/staff-schedules` and `GET /api/v1/projects`, no document
  upload/read anywhere in it. The `handleAssessmentPhotoUpload`/
  `POST /api/v1/documents` code that does exist in the file (~line 7659)
  lives inside `render_admin_surface()` (starts line 1695), a completely
  separate function — not reachable from the subcontractor portal. No
  silent-403 regression.
- `env -u HTTP_PROXY ... pytest tests/test_restoricon_core/ -q` →
  `1291 passed in 215.57s (0:03:35)`, verbatim, matches round 2's count
  (test file only swapped two assertions, didn't add new tests this round).

**APPROVED** — final verdict across all three rounds (C1 reassignment gate,
C2 compliance over-grant, false NEW-668-precursor comment, and this
documents over-grant) is CHANGES REQUESTED → CHANGES REQUESTED →
APPROVED. Files to stage for commit: `restoricon_core/auth.py`,
`NEW_ISSUES.md`, `tests/test_restoricon_core/test_phase0b_role_subcontractor.py`
(untracked). The other modified files (`routes.py`, `web_surfaces.py`,
`database.py`, `models.py`, `services/operations_service.py`,
`tests/test_restoricon_core/test_database.py`,
`tests/test_restoricon_core/test_web_surfaces_admin_wiring.py`) were
already reviewed/approved in rounds 1-2 as part of the same overall Phase
0b diff and belong to the same commit, not new this round.

Technique reinforced from [[phase0b_role_subcontractor_round2_documents_gap_changes_requested]]:
when checking "does anything assume the removed permission," don't stop at
grepping the permission name in routes/services — also trace the actual
portal-surface call graph (which JS function is nested inside which
`render_*` function) to rule out a silent-403 UI regression. A flat grep
for `PERM_READ_DOCUMENTS`/`PERM_WRITE_DOCUMENTS` usage wouldn't have
surfaced the admin-only assessment-upload feature at all, so the "is it
reachable from the narrowed role" question needed the structural read.
