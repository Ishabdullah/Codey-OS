---
name: b8_5b_assessment_photo_round2_approved
description: B8.5b round 2 — document_type CHECK-constraint fix for assessment photo upload, APPROVED after independent differential live repro
metadata:
  type: project
---

Round 2 of [[b8_5b_assessment_photo_checktype_changes_requested]] (round 1
CR: `document_type='assessment_photo'` not in the CHECK constraint, every
photo upload 500s). Fix: send `document_type='photo'` (valid) +
`assessment='true'` form field; `routes.py` turns that into an
`"assessment"` tag on the created `Document`, mirroring the existing
`subcontractor_id` -> tag pattern at the same call site. APPROVED.

**Technique that mattered**: don't just trust the new regression test's
own assertions — wrote a second, independent differential repro script
(own MockRFile/router harness, outside the test file) that POSTs the
*old* broken `document_type` value against the *new* code and confirms it
still 500s, then POSTs the new value and confirms 201, on the same live
server instance. This directly proves the fix closes the exact
previously-found bug, rather than just proving the new test's assertions
are internally consistent (a test can assert the wrong thing and still
pass).

Also verified a specific claim about `create_document()` before trusting
the "test asserts a GET re-read, not just the POST response" reasoning:
read the service method and confirmed it mutates and returns the *same*
`doc` object handed to it (`doc.id = cursor.lastrowid`, no re-select) —
so a POST-response-only assertion genuinely would not prove persistence
in the way a GET-after-POST does. Worth checking this kind of claim
against the actual function body every time it's invoked as the reason a
test is structured a certain way — it's the kind of thing that sounds
right and usually is, but "usually" isn't "always."

Full suite `2154 passed, 1 skipped` reproduced exactly to match the
implementer's claim, run from repo root with proxy vars unset (see
[[sandbox_http_proxy_urllib_405_env_artifact]]). Full suite run took
~312s in background — use `run_in_background: true` + wait for the
task-notification event rather than polling/sleeping; polling loops on a
background task you started are explicitly discouraged by the harness.

Disclosed, accepted scope boundary: `handleAssessmentPhotoUpload`'s
per-file upload loop still has no 401-redirect (unlike every other
handler in this diff), because redirecting on the first file's 401 mid
multi-file-loop would silently abandon the rest of the batch. Reasonable
to defer as its own low-severity `NEW-###` rather than block the round on
it — judged this a genuine scope call, not an omission worth rejecting.
