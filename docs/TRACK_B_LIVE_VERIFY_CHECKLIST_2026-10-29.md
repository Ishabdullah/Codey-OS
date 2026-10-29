# Track B — Ish-attended live-verification checklist (B6 / B8 / B9 + B7 status)

Written 2026-10-29 by project-architect. Scratch file, not a tracked repo doc.
Derived only from `CODEY_MASTER_PLAN.md` §4.5 "Track B tier table", `PROJECT_LOG.md`,
`NEW_ISSUES.md`. Nothing here was run. Rule 7: "live-verified" = real server /
real HTTP / real DB (or a copy), verbatim output captured. Reviewer-run repros do
not count.

## Ground rules for every item

- **Where it runs.** Default is a **disposable world** made with `tools/world.py`
  (`docs/worlds.md`): `RESTORICON_DB_PATH` points at a copy, ports 18770-18999,
  and the live store is refused without `--world production`. Items marked
  **[PROD]** are the only ones that need an Ish-chosen `--world production`
  pass, because they ask about the real store itself; every [PROD] item is
  read-only unless it says otherwise. Back up `restoricon.db`, `-wal`, `-shm`
  first (as done 2026-10-28 into `~/restoricon-prestart-backup/`) and record the
  live files' size/mtime/inode before and after.
- **Model loads.** Only B8.11 (AI copilot) and nothing else here loads a model.
  If you run it, rule 2: `free -h` first, one model-load cycle, confirm
  llama-server gone after. Everything below is model-free.
- **Evidence form.** Verbatim command + output pasted into `PROJECT_LOG.md`
  (rule 5); a paraphrase or "tests pass" does not flip a tier.
- **Negative control.** For every isolation/denial claim, show the *allowed*
  request succeeding right next to the denied one (otherwise a broken server
  also "passes").

---

## P0 — customer isolation and portals (highest consequence: a bug here is a
## data breach between real customers; §7 risk 3)

**P0-1. Customer-to-customer isolation over real HTTP (B1, B4 portal API, B6.3).**
Tier today: CC+RA, no LV recorded. World: **world copy**, server started the
normal managed way, requests from a *separate OS process* (curl or a second
python), two customer logins (customer A, customer B) each with at least one
project, invoice, contract, document, estimate.
Flips to LV when the transcript shows, verbatim: A's token gets 200 for A's ids
and 403/404 for each of B's project / invoice / contract / document / estimate /
message ids on `/api/v1/portal/*` and on the direct `/api/v1/...` equivalents;
list endpoints for A contain none of B's rows; A's responses contain no
cost/margin/internal-note fields; `GET` with no token and with a garbage token
are 401; the audit log has rows for the denied attempts if the design logs them.

**P0-2. B1 exit criterion (separate process, human + agent audit records).**
Tier: B1 LV "unclear". World: **world copy** via the real `codey-start`/managed
start. Flips to LV when: a second process gets role-filtered data for at least
two roles (e.g. admin vs technician vs customer), and the audit log and
communication history show one row caused by a human-session action and one
caused by an `ai_agent` actor, both with actor + timestamp, listed with a
`SELECT` against the world DB.

**P0-3. Rendered customer portal in a real browser (B6.3).**
Tier: CC+RA. World: world copy, behind the tunnel if it is up, otherwise
`127.0.0.1`. Flips to LV when: customer login lands on `/portal`, the page shows
that customer's real timeline/invoices/contracts/PM chat (no demo text), the
browser network log (or server access log) shows the page actually calling the
`/api/v1/portal/*` routes, and a second customer's login shows different data.
Same session, also the open sessionStorage item from 2026-09-02: quit the browser
fully, reopen, confirm login is required again (§4.1 "session persistence",
currently "NOT browser-verified").

**P0-4. Public share-link surface (B9.4) — first unauthenticated surface.**
Tier: CC+RA, no LV. World: world copy with one sent estimate. Flips to LV when:
the share link opens the customer view with no login; the response contains no
cost/margin/internal fields (customer allow-list serializer, F1 fix); a wrong,
expired and revoked token each return the same uninformative denial; the token is
accepted only in the path (not the `?token=` session fallback at the routes the
spec names); and the stored value is a SHA-256 hash (read the row, show it is not
the URL token); repeated bad tokens hit the rate limiter.

**P0-5. Staff portals and subcontractor narrowing (B6.8, B8.12a).**
Tier: CC (B6.8) / CC+RA (B8.12a), no LV. World: world copy with one PM, one sales
rep, one technician, one subcontractor, one project each assigned differently.
Flips to LV when: each role's portal opens on "where am I assigned" plus own
calendar; sales rep sees only own/sold projects; the subcontractor sees only
its assigned project(s) and *no* customer financials/contact details (it is the
first surface exposing project data outside the company); a request for an
unassigned project id returns denial for each role.

**P0-6. Document upload and download (B6.5, rule-4).**
Tier: CC, reviewer unclear, no LV. World: world copy, via the tunnel if up.
Flips to LV when: a 25MB+1 upload is rejected; a `../` / absolute-path /
symlink filename lands inside the documents dir or is rejected (show the
resulting path); a disallowed content-type is rejected; customer A cannot
download customer B's document id; the file lands in the configured store
(`~/.codeyOS/restoricon_documents` for the live config, a world path in a world).

---

## P1 — production-DB passes for B9 and the rest of B9/B8 not yet LV

**P1-1. [PROD, read-only] Does the live store carry the B9.x/B9.8 schema?**
Tier: B9.x/B9.8 are LV only on a *copy of the production DB, 2026-10-01*; whether
the real store was migrated is not recorded (the 2026-10-28 `--world production`
start ran the app against it, but no PROJECT_LOG line says `init_schema` migrated
and what it found). Do not assume. Flips (for "migrated in production") when,
with the server stopped and a backup taken, a read-only `sqlite3` session
shows: table count 70 (copy result was 54->70), the 12 pricing/retailer tables
present, `estimates.property_id` and the four `estimate_line_items` pricing-id
FKs present, the three locked-immutability triggers by name,
`PRAGMA integrity_check` = ok, `PRAGMA foreign_key_check` = empty, and row
counts of customers/contacts/audit_log/estimates unchanged against the backup.

**P1-2. B9.8 `EstimateService.convert()` — close the two stated caveats.**
World: **world copy of production** (never the live store for the write). Already
LV on a copy 2026-10-01; what is missing is priority branches 1 and 2 (estimate
already has `project_id`; opportunity already has `project_id`) never forced
against real data. Flips the caveats when: two scratch estimates are driven so
each branch is taken, each producing no duplicate Project and no duplicate audit
row (exactly the audit entries the code defines), idempotent on re-call. If Ish
wants a true production conversion, that is an explicit **[PROD]** write and
needs Ish's go-ahead on a specific real estimate; the real `estimates` table was
empty on 2026-10-01, so check its row count first.

**P1-3. B9.x guard that was synthetic-only.** The orphaned-`property_id`
commit-before-raise guard needs a non-empty `estimates` table with a dangling
`property_id`. World: world copy with one deliberately dangling row inserted.
Flips when: opening the DB raises and the transaction rolls back (row count and
`sqlite_master` unchanged), and a second open still raises (does not
self-silence — the round-1 bug).

**P1-4. B9.2-B9.7 end-to-end estimating flow (service, routes, builder UI, admin
tab, quote portal).** Tier: CC+RA, no LV recorded. World: world copy, browser.
Flips to LV when one estimate goes draft -> priced (server-side totals, a client
attempt to send its own totals/estimate_number ignored) -> internal review as the
state machine requires -> sent -> customer decision (accept) -> contract created,
each step shown in the audit log; `/quote` shows the request-an-estimate CTA and
no $/sq-ft calculator (B9.7); the claim/unclaim/reassign actions respect
ownership narrowing for a sales role and `ai_agent` cannot send.

**P1-5. B9.y browser pass.** Tier: CC+RA, NOT LV (no browser last time). World:
world copy. Flips when: admin creates a customer login via the Add User modal
(customer picker), the new customer can log in and sees only own data; admin
"Reset Password" resets without revealing the old one; switching a role in the
modal does not carry the previous customer's email (the round-1 leak,
differential check).

**P1-6. B8 sales portal pass (B8.2-B8.15).** Tier: CC+RA, no phase-level LV
(B8.1/1a, B8.11, B8.16 are already LV). World: world copy, mobile-size browser.
Flips per sub-area when its main flow works from the browser with a real sales
login: lead claim (atomic, two sessions racing one unclaimed lead — one wins),
estimate -> proposal -> signature (multi-party PDF), commission ledger entries and
dashboards, insurance/financing records, communications center send, sold-project
handoff checklist. Capture one transcript per sub-area; the tier table lists
which rows then move.

**P1-7. NEW-540 and B7 currency (see status block at the end).**
World: **[PROD]**, because the replica belongs to the live store. Do *not* start
anything new that writes. Flips NEW-540 to resolved when all three are shown:
(1) a litestream process with a pidfile that matches `ps` (and its log mtime is
recent); (2) a GCS generation/snapshot newer than 2026-09-16 (and ideally newer
than the last recorded live write, 2026-10-28); (3) a **scratch restore** of
that replica (`litestream restore -o <scratch>/restored.db`) opened read-only
shows the `users` table DDL containing `sales_manager` in its role CHECK and an
AUTOINCREMENT high-water mark >= 6, plus row counts matching the live DB for
customers/contacts/audit_log/users. If the restore is stale, NEW-540 stays open
and the finding becomes "litestream is not running as a persistent service" (the
entry's own fix-direction fork).

---

## P2 — remaining "unclear/none" cells worth a pass before Jan 1

- **P2-1 B2 write-through (Aigentik jest was the bar):** world copy + a running
  Aigentik fork pointed at the world API; one DNC change, one rule change, one
  contact sync, one inbound/outbound email logged; rows in the world DB and in
  `audit_log`. Flip: row present with expected `external_id`, idempotent on retry.
- **P2-2 B5b Core-to-device dispatch (§8 Q2, now "resolved/built"):** needs the
  Android app on the phone. Flip: a scheduled command created in the Core reaches
  the device over `ws://127.0.0.1:8088/ws/device`, executes, and writes a
  `communication_history` + `audit_log` row; the emergency-shortcode veto refuses
  911/112/999 on-device. Also settles the Suspected inconsistency (device_bridge
  "write-only" in the 12.x scoping note) logged under NEW-1118.
- **P2-3 B4 hosting split (§8 Q4 decision):** `restoricon.com` served from GitHub
  Pages (repo settings + HTTP response headers), `api.restoricon.com` reaches the
  phone through the tunnel with an auth layer in front, a public intake form
  submission arrives as a lead in the world/prod DB. Flip: those three captured.
- **P2-4 B6.6/B6.7 ICS invites:** staff-schedule create/update sends an invite via
  Aigentik (`ics_sequence` increments on update); `NEW-506` (no cancel to a
  previous assignee) is known-open.
- **P2-5 B6.2 audit completeness:** one create/update/delete per service shows the
  canonical `before`/`after` envelope; B6.2c audit-search screen restricted to the
  audit-reading role.
- **P2-6 B3 / B5a engines (CRM scoring, finance P&L/AR aging, compliance expiry
  scan, HR timesheets, procurement):** one scripted scenario each against a world
  copy, compare to hand-computed figures.
- **P2-7 B6.4 post-program batch (`2b2c2a3`, CC+RA only):** the XSS escaping of the
  two new Delete buttons and `openPermModal` in a browser (payload name such as
  `"');alert(1);//` does not execute).

---

## NEW-540 — current status (as of 2026-10-29)

- **Status: OPEN, Confirmed** (live-verifier, 2026-09-16). Sole later mention in
  the plan is `CODEY_MASTER_PLAN.md` Appendix A (B8.1a entry, "still open").
  No closure entry in `PROJECT_LOG.md` or `NEW_ISSUES.md` after 2026-09-16
  (searched all four docs). An update line was appended to the NEW-540 entry on
  2026-10-29.
- **What it actually is — not "data loss":** the ledger entry is a *stale
  off-device replica*. litestream was not running during the D2 `users`-table
  rebuild (log last written 2026-09-15 22:02), so the GCS replica holds the
  pre-migration schema (old role CHECK, AUTOINCREMENT mark 5 vs live 6). The
  entry itself says "not itself data loss" — the live DB was intact. The label
  "replica data loss" overstates it; the real risk is that a restore *today*
  would bring back a pre-2026-09-16 schema and lose everything written since if
  litestream has not run since.
- **Newer evidence that bears on it (not closure):** the 2026-10-28 attended
  `--world production` start/stop wrote to the live store and recorded "no
  restoricon/litestream process" afterwards. So there is no record that any
  replication happened after that write.
- **Adjacent unchanged facts:** B7's Core-DB restore drill and the DR-key chain
  were live-verified 2026-09-10 (exact row parity), `NEW-458` escrow closed
  2026-09-15 on Ish's attestation, doc-store drill byte-identical. All of that
  predates NEW-540 and the WP2.2 world-enforcement change, and none has been
  re-run since. See item P1-7 for the evidence that would close it.
