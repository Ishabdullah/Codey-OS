---
name: crm-create-contact-external-id-autoassign-approved
description: CRMService.create_contact auto-assigns contact_NNNN external_id for inbound SMS/email leads — approved
metadata:
  type: project
---

`restoricon_core/services/crm_service.py::create_contact` now auto-assigns
`external_id = f"contact_{id:04d}"` (row id) inside the `with conn:` txn when
caller supplies none, with a collision `while` loop. Approved 2026-09-01.

**Why:** inbound leads (POST /api/v1/contacts from Aigentik contacts.js) left
external_id NULL; Aigentik then addresses Core by a synthesized `contact_%04d`
which Core resolves only by exact external_id match -> 404 -> silent no-op on
every updateContact/applyExtractedDetails.

**How to apply / verification done:**
- Only 2 `INSERT INTO contacts` paths: create_contact + sync_contacts_batch; sync already assigned.
- upsert_contact validates non-empty external_id before calling create_contact, so new branch can't fire there.
- Concurrency safe: txn holds write lock from the INSERT; sqlite timeout=30 serializes writers; WAL. Loop SELECTs a free id before UPDATE so UNIQUE idx_contacts_external_id can't raise.
- sync_contacts_batch recomputes max(contact_ number) every call incl. direct-created rows, so schemes don't diverge into collision; direct loop bounded by row count.
- Negative control: stripping the block makes the new test fail with `assert None == 'contact_0001'` — the real symptom. 211 passed with fix.

**Open caveats at approval:** Aigentik's contacts.js is NOT in this repo
(fork of a standalone product) — the "mapCoreToJS synthesizes contact_%04d
from row id" claim is unverified. If that JS ignores the external_id in the
POST /contacts response and always formats from the numeric id, the collision
`while` loop stores contact_{id+k} while JS addresses contact_{id} -> same
404 no-op it was meant to fix. Rare branch (needs a pre-existing contact_{rowid}
on another row). Comment overclaims that the loop makes this "safe". Also: no
backfill of pre-fix NULL-external_id SMS/email rows — deliberate, owed a
NEW_ISSUES line per rule 8. Only crm_service.py has INSERT INTO contacts
(create_contact + sync_contacts_batch); route POST /api/v1/contacts ->
Contact(**json_body) -> create_contact, explicit external_id honored.

**Negative-control gotcha this round:** first strip attempt used `s.index('self.audit.log(...action="create"')` which matched an EARLIER create_* method (j < i), silently duplicating instead of stripping and giving a false pass. Always anchor the end-marker search with `s.index(marker, start_pos)`.
