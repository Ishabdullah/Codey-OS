---
name: b9-7-quote-portal-calculator-removal-approved
description: B9.7 D8 removal of public $/sq-ft calculator from render_quote_surface() — APPROVED round 1
metadata:
  type: project
---

B9.7 (decision D8) removed the self-service $/sq-ft price calculator from
`render_quote_surface()` in `restoricon_core/api/web_surfaces.py` and
replaced it with a static "Request a Free Estimate" CTA. Front-end-only,
verified via `git status --short` that only `web_surfaces.py` + the new
test file changed (no API/schema/route diff). APPROVED round 1.

**What held up:** full python-string repo scan (Termux `grep` is broken —
use `python3 -c` scans, per [[frontend_search_must_include_py_files]])
found zero remaining calculator identifiers/CSS/JS anywhere, including no
stale references in docs. CTA is genuinely static (no interpolation, so
no missing-`escapeHtml()` gap), `onclick="focusLeadIntakeForm()"` is a
bare no-arg call (not the NEW-661/664 `onclick='fn(${JSON.stringify(...)})'`
attribute-breakout pattern), and the callee targets the pre-existing
`publicQuoteForm`/`leadName` ids, not a new form. Diffed hunk-by-hunk to
confirm `submitQuoteForm`/`submitBookingForm` genuinely untouched (stronger
than "read it and it looked the same" — no diff hunk overlaps those
functions at all).

**Real finding surfaced and logged as NEW-725 (Confirmed):**
`submitBookingForm()`'s success branch (pre-existing, unrelated to this
diff, confirmed present verbatim at HEAD via `git show HEAD:path`) builds
`alertBox.innerHTML` with `` `...${email || phone}...` `` where
`email`/`phone` come straight from `leadEmail`/`leadPhone` `.value` with
no `escapeHtml()` call — this file's own convention elsewhere
(`render_portal_surface`/`render_admin_surface`/`render_estimates_surface`
all define `escapeHtml()`) is broken here because `render_quote_surface`
and the shared `_get_common_script()` helper never define it. Checked the
severity claim empirically, not just accepted it: searched for
`URLSearchParams`/`location.search`/`location.hash`/`document.referrer`/
any `.value =` prefill into `leadEmail`/`leadPhone` inside
`render_quote_surface` — none found, so this really is self-XSS only
(visitor's own browser reflecting their own typed input), not a
reflected-XSS-via-crafted-link. A "low severity, self-XSS only" claim is
worth this exact check every time before accepting it — a URL-prefilled
field would have made it a real reflected-XSS vector instead.

**Test-count claim didn't reproduce (Warning, non-blocking):** implementer
claimed "targeted: 18 passed" for this round; actual reproducible counts
were 3 (new file alone), 79 (5-file web-surfaces set), 86
(`-k "quote or web_surfaces"` across `tests/test_restoricon_core/`) — none
hit 18. Every test that exists passes, so not a blocker, but per rule 5 an
unverifiable count claim should be corrected in the ledger rather than
left standing (same pattern as NEW-512, see
[[new507_508_509_subcontractor_delete_approved]]).

**Full-suite count DID reproduce exactly, after ruling out a live proxy
artifact:** first full-suite attempt in this session showed
`2786 passed, 1 skipped, 1 error` — the "error" was
`test_api_new529_contacts_malformed_extra_segment_...` failing login with
405 instead of 200. Traced to this specific Bash shell having
`HTTP_PROXY`/`HTTPS_PROXY`/etc. ambient env vars re-injected mid-session
(checked via `env | ...`) despite an earlier `unset` in a *different*
Bash tool call — shell state does not persist between Bash tool calls in
this harness, so `unset ... && pytest ...` must be one single command,
every time, not assumed to carry over. Re-running with unset in the same
command gave a clean `2787 passed, 1 skipped` — reproduced twice more
after that, exact match to the implementer's claim. The 1 skip is
`tests/test_new83_embed_server_kill.py` (`/proc/net/tcp not readable in
this sandbox`) — pre-existing, unrelated to this diff (new test file has
no skip markers).
