# B1 Census — Codey-Aigentik (the "mouth" limb)

Repo: `/data/data/com.termux/files/home/Codey-Aigentik`
HEAD: `e76f1f0` (2026-09-15). 74 tracked files (41 .js, 19 .md). Tags
v1.0.0/v1.0.1/v1.0.2/v1.1.0. Fork of `Ishabdullah/Aigentik-CLI`
(upstream remote present).

---

## (a) What it is + entry points

`package.json:1-24` — name `aigentik`, `"main": "index.js"`, ESM
(`"type": "module"`), `"start": "node index.js"`. No daemon manager, no
systemd/service file in this repo — it is a single long-running Node
process, presumably started by Codey-OS's own process supervision
(not present in this repo).

**Entry point: `index.js`** (`index.js:1-34`). Comment header
(`index.js:1-8`): "Communication: Gmail + Google Voice ONLY ... No SMS
sending or receiving via Termux ... All routing via Gmail IMAP IDLE."
It imports every other module as a namespace (`logger`, `config.json`,
`telemetry.mjs`, `llama.js`, `gmail.js`, `owner-command.js`,
`contacts.js`, `contacts-sync.js`, `queue.js`, `tone.js`, `sms-rules.js`,
`email-rules.js`, `calendar.js`, `subcontractor-form.js`,
`do-not-contact.js`, `subcontractor-recruiter.js`, `customer-module.js`,
`role-router.js`, `http-server.js`), starts `llama-server`, warms it up,
loads the business profile, kicks off Android contact sync, connects
Gmail IMAP IDLE, and dispatches every inbound email/Google-Voice-text
to the right handler. **Confirmed via `docs/architecture.md:132` (source
table) and cross-checked against actual imports — matches.**

**Runtime model:** single Node.js process with one persistent IMAP IDLE
connection (`email-provider.js`) plus a small pool of extra IMAP
connections for bulk ops. A second, separate **inbound HTTP server**
(`http-server.js:8`, port 8081, `127.0.0.1` only) is started from
`index.js`'s import of `startHttpServer` for Core→Aigentik outbound
notification calls (commit `d6197a8`, "B6.6: Add internal HTTP server
for Core->Aigentik outbound notifications"). Not a CLI tool despite the
upstream product name ("Aigentik-CLI") — Codey's fork runs it as a
service, matching `CODEY_MASTER_PLAN.md`'s "comms/inbox limb" framing.

**Inherited vs Codey-added:** the base email/SMS-via-Google-Voice
engine (`email-provider.js`, `gmail.js`, `calendar.js`, `contacts.js`,
`role-router.js`, rule engines, subcontractor/customer CRM flows) is the
upstream Aigentik-CLI product. Everything Core-API-shaped — the 10
duplicated `coreRequest()` helpers, every `/api/v1/*` call, the
`mapJSToCore`/`mapCoreToJS` layers, `http-server.js`, `telemetry.mjs`,
NEW-### fixes — is Codey-specific (see divergence list below; none of
it exists on `upstream/main`).

---

## (b) Fork divergence vs upstream

```
git log --oneline upstream/main..main   → 0 commits (upstream has nothing Codey lacks)
git log --oneline main..upstream/main   → 29 commits (Codey's additions over the merge base)
```
`upstream/main` tip in the local object store: `0c3eafe`, "chore: ignore
.agents directory", Aug 26 2026. **Not re-fetched from the network for
this task** (instructions prohibit network ops) — this is whatever was
last fetched; `.git/logs/refs/remotes/upstream` shows no fetch activity
in this session, so if upstream has moved since Aug 26 that isn't
visible here. Caveat stated per task instructions.

Given 0 commits unique to upstream relative to the merge base, **there
is no unmerged upstream work to take** — Codey's fork is strictly ahead
on this branch pair; upstream-main..main is empty. All 29 divergent
commits are Codey's own Core-API write-through cutover (Phase B2),
telemetry work (T1/T2/T10), and the recent bug-fix chain:
`4dd1232`→`e76f1f0` (full list captured; highlights: `be242f7`
"Phase B2 100% complete", `2056524` "business profile is Core-first
read", `d6197a8` "internal HTTP server for Core→Aigentik", `8b61916`
"Fix transposed sendCalendarInvite() args", `e76f1f0` "Fix NEW-517").

---

## (c) Integration surface with Codey-OS + auth

**Transport: plain HTTP/JSON to a Core API, not a shared DB, not a
subprocess.** `config.json:60-63` (`.core_api.base_url` =
`http://127.0.0.1:8770`, `.core_api.token` = a static bearer string).
Every data module (`index.js:36-72`, `contacts.js:12-50`,
`calendar.js` top, `customer-module.js:365`, `do-not-contact.js:44`,
`email-rules.js:43`, `sms-rules.js:34`, `llama.js:19`,
`owner-command.js:23`, `subcontractor-recruiter.js:24`,
`email-provider.js:646`) defines **its own copy** of an identical
`coreRequest(method, urlPath, {query, body})` helper — `fetch()` with
`Authorization: Bearer ${CORE_API_TOKEN}`, 15s `AbortSignal.timeout`,
JSON body/response. **11 independent copies of the same ~30-line
function** — see hygiene section (g).

**Auth: a single static bearer token, read from `config.json`, never
rotated in code.** `index.js:36-37` / equivalents in every module:
`const CORE_API_TOKEN = config.core_api?.token;`. No per-request
signing, no token refresh, no handling of 401/403 as "token revoked"
(a 401 is just treated as a generic non-`ok` response and surfaces as a
thrown/logged error like any other failure — confirmed by reading every
`coreRequest` call site; none branch on `status === 401`). The
directive notes the production DB's `api_tokens` table has 96 rows —
this repo's `config.json` holds exactly one of those 96 tokens, loaded
once at process start; this repo gives no visibility into token
issuance/rotation/revocation (that lives in Core, out of this census's
scope).

**Inbound direction (Core → Aigentik):** `http-server.js` (port 8081,
`127.0.0.1`), three unauthenticated POST routes — `/send-email`,
`/send-invite`, `/send-cancellation` (`http-server.js:10,33,59`). **No
token check, no origin/header validation of any kind** on this server —
any local process that can reach `127.0.0.1:8081` can trigger a real
outbound email to an arbitrary address with arbitrary text. Binding to
loopback-only is the only mitigation. Flagged under (f)/(i).

---

## (d) Audit table — every Aigentik→Core HTTP call site

Checked every `coreRequest(...)` call for the known defect class
(argument transposition, stale/leaked keys, silent key mismatches,
missing required fields). Full call-site list obtained via
`grep -n "coreRequest(" *.js` (54 matches across 12 files).

| File:line | Route | Body construction | Verdict |
|---|---|---|---|
| `calendar.js:681,729` | POST `/api/v1/appointments` | `mapJSToCore(jsAppt)` from a **freshly built** object (no spread of a prior mapCoreToJS output) | CORRECT |
| `calendar.js:763` | POST `/api/v1/appointments/{id}/update` | `coreUpdates` built field-by-field from `updates`, manual | CORRECT |
| `contacts.js:264` | POST `/api/v1/contacts` | `mapJSToCore({...fresh literal...})` — not derived from `existing`/`mapCoreToJS` output | CORRECT |
| `contacts.js:348,381` | POST `/api/v1/contacts/{id}/update` | `coreUpdates` built field-by-field | CORRECT |
| `contacts.js:367` | POST `/api/v1/contacts/{id}/delete` | no body | CORRECT |
| `contacts-sync.js:54` | POST `/api/v1/contacts/sync` | `{ contacts: payload }`, payload mapped explicitly (`name`/`phones`/`aliases`/`source`) | CORRECT |
| `customer-module.js:714` | POST `/api/v1/customers/upsert` | `mapJSToCore(record)` — `mapJSToCore` (`customer-module.js:474-549`) builds `coreObj` as a **fresh literal**, not a spread | CORRECT |
| `do-not-contact.js:140` | POST `/api/v1/do-not-contact` | explicit `{identifier, name, reason, source}` | CORRECT |
| `do-not-contact.js:159` | POST `/api/v1/do-not-contact/remove` | explicit `{identifier}` | CORRECT |
| `email-provider.js:777,849` | POST `/api/v1/communications` | explicit `payload`/conditional-spread of named fields only (`logCommunication`, drain loop) | CORRECT |
| `email-rules.js:98` / `sms-rules.js:88` | POST `/api/v1/automation-rules` | explicit `{external_id, channel, description, condition_type, condition_value, action, added_by}` | CORRECT |
| `email-rules.js:124` / `sms-rules.js:114` | POST `/api/v1/automation-rules/{id}/delete` | no body | CORRECT |
| `email-rules.js:179` / `sms-rules.js:144` | POST `/api/v1/automation-rules/{id}/match` | no body | CORRECT |
| `llama.js:208` | POST `/api/v1/ai/chat` | explicit `{model, messages, max_tokens, temperature, enable_thinking}` | CORRECT |
| `owner-command.js:136,278,352` | POST `/api/v1/business-profile` | `{...profile, <overrides>}` — spread of `profile` (an internal, Core-shaped object already round-tripped through `readProfile()`), not of a half-mapped intermediate; overridden fields pinned explicitly after the spread | CORRECT (spread is of the Core-shaped object itself, not a stale pre-map) |
| `subcontractor-recruiter.js:324` | POST `/api/v1/subcontractors/upsert` | `mapJSToCore(record)`, `record = {...data, subcontractor_id: externalId, last_contact: now, ...}` | **CORRECT as of HEAD** — this is exactly the call site NEW-517 fixed (`e76f1f0`): `mapJSToCore` (`subcontractor-recruiter.js:84-103`) now explicitly `delete`s `subcontractor_id`/`last_contact` after copying them to `external_id`/`last_contact_at`. Verified in current source. |
| `subcontractor-recruiter.js:359` | POST `/api/v1/subcontractors/{id}/update` | `mapJSToCore(updates)`, `updates = {...existing, ...updates}` where `existing` came from `mapCoreToJS` (`subcontractor-recruiter.js:64-82`, a **spread-based** reverse-mapper that leaves `external_id`/`last_contact_at` in place alongside the new `subcontractor_id`/`last_contact` keys it adds) | CORRECT **but fragile**: `mapJSToCore` overwrites `coreObj.external_id`/`coreObj.last_contact_at` unconditionally after the spread (not just deletes the JS-side aliases), so the stale Core-side keys get the right value written back over them rather than surviving as duplicates. No bug today, but this call site is one line away from reintroducing NEW-517's exact failure mode if a future edit changes the overwrite order. |
| `http-server.js:50,73` | (local, not Core — outbound to `emailProvider`) | `sendCalendarInvite(data.appointment, data.to, data.text)` / `sendCalendarCancellation(...)` | CORRECT **now** — this is the exact bug `8b61916` fixed ("Fix transposed sendCalendarInvite() args"); verified `email-provider.js:1117` signature `(appointment, toEmail, bodyText)` matches every call site in `gmail.js:97-107`, `index.js:370-766`, `owner-command.js:1178-1244`, and both `http-server.js` routes. |

**Pattern-level finding (new, not previously logged):** `contacts.js`'s
`mapJSToCore` (`contacts.js:76-89`) is **also spread-based**
(`const coreObj = { ...jsObj }`) and sets `coreObj.external_id =
jsObj.id` **without deleting `jsObj.id`** from the spread result — the
exact shape of bug that produced NEW-517. It is currently **not
triggered** because the only call site (`contacts.js:245`) passes a
freshly-built literal that never has an `id` key, and all
`updateContact`/`renameContact` paths build `coreUpdates` manually
rather than routing through `mapJSToCore`. **This is a latent landmine,
not a live bug** — logging to `NEW_ISSUES.md` as Suspected per the
project's finding-logging rule, since this is exactly the defect class
the task asked to audit for and it was found outside the task's literal
scope (watching for recurrence, not confirming an active failure).

---

## (e) Unfinished communications capabilities

No `TODO`/`FIXME`/`XXX`/`NotImplemented`/`stub`/`placeholder` markers
found anywhere in source (`grep -rn` across all `*.js` excluding
`node_modules`/`tests`/`coverage` — zero hits). The project appears to
close out work items via commits/NEW-### fixes rather than leaving
inline markers, so absence of markers is not itself evidence of
completeness — cross-checked against docs instead:

- **`docs/architecture.md`'s own architecture diagram is stale/wrong**
  (`docs/architecture.md:21-59`). It depicts `data/*.json` as the
  storage layer for contacts/rules/queue/calendar/profile/logs, with no
  mention of Core API at all, and lists `http-server.js` nowhere in the
  diagram or the "Source file reference" table (`docs/architecture.md:
  130-150`) — yet by the Phase B2 commits (`be242f7`, `badd556`,
  `3ff9d11`, `777c699`, `4dd1232`, `05160ce`, `70655f9`, `53a08bb`,
  `0398396`) every one of those modules is Core-write-through with **no
  local-JSON fallback**. Status: **DOCS-ONLY / stale** — the diagram
  describes the pre-B2 architecture, not current source. This is
  exactly the class of doc-vs-source mismatch the task instructions
  warned about.
- **`docs/security.md` omits the Core API integration and
  `http-server.js` entirely.** Its claim (`docs/security.md:7`) — "The
  only network traffic Aigentik generates is Gmail IMAP/SMTP and local
  calls to `llama-server` on `127.0.0.1`" — is **false against current
  source**: Aigentik also makes HTTP calls to Core on `127.0.0.1:8770`
  (11 call sites, section c/d above) and **runs its own inbound HTTP
  server on `127.0.0.1:8081`** (`http-server.js:5-6`) with three
  unauthenticated routes that can send real email. Status: **DOCS-ONLY
  / contradicted by source.**
- **SMS-via-Termux is explicitly documented as removed**
  (`docs/architecture.md:65`: "that entire path (`sms-send.js`,
  `sms-inbox.js`, `sms-public.js`, and a first-run setup wizard...) has
  been removed"). Confirmed — none of those files exist in the repo.
  `sms.poll_interval_ms`/`sms.max_sms_fetch` in `config.json` are
  **dead config** — `sms-rules.js` is the Google-Voice-via-Gmail rule
  engine, not a poller; no code reads `config.sms.*` anywhere (checked:
  no hits for `config.sms` outside `config.json` itself). Status:
  **DOCS-ONLY config / DORMANT** — present in config schema, read by
  nothing. Searched: `grep -rn "config.sms\b\|\.sms\." *.js`.
- **`gemini`/`vertex` config blocks** (`config.json`: `.gemini.*`,
  `.vertex.*`) are live code paths (`llama.js`'s `chat()` branches on
  `provider === 'gemini'`/`'vertex'`), but `config.json`'s
  `.llm.provider` is set to `"local"` — so this capability is
  **IMPLEMENTED but DORMANT** in the current runtime config (reachable
  only if an operator changes `.llm.provider`, never exercised in the
  current deployment).
- **`scripts/send_test_sms.py`** — a standalone Python test script,
  outside the Node runtime, no reference to it from any `.js` file.
  **DORMANT** by the task's reachability test (searched: no `import`/
  `require`/`execSync` reference to this path anywhere in `*.js`); it's
  a manual dev tool, not a wired capability.

---

## (f) Production coupling / risk — real-message-sending surface

**Aigentik writes to live Restoricon Core data, via HTTP, not
directly to the SQLite file** (the task's `~/.codeyOS/restoricon.db`
was not opened — correctly, per instructions — all access goes through
Core's `127.0.0.1:8770` API). Based on route names and the explicit
"no local-JSON fallback" commit messages, the write-through mapping is:

| Core route Aigentik calls | Likely production table (by name match; Core's own handler not in this repo, not verified at that layer) |
|---|---|
| `/api/v1/contacts*` | `contacts` (249 rows) |
| `/api/v1/do-not-contact*` | `do_not_contact` (4 rows) |
| `/api/v1/automation-rules*` | `automation_rules` (2 rows) |
| `/api/v1/communications` | `communication_history` (309 rows) |

**This inference is based on route-name correspondence only** — the
Core-side route handlers live outside this repo (not found under
`~/restoricon`, which turned out to be the marketing-site repo, not the
Core API backend) and verifying the actual column-level mapping was out
of this census's scope (Codey-Aigentik only).

**Real-message-sending surface (the thing the directive human-gates):**
- `gmail.sendReply`/`sendEmail`/`sendOwnerNotification`/
  `replyToGoogleVoiceText` (`gmail.js:73-89,229`) are the only functions
  that put a message on the wire to a real person. All are gated
  upstream by `do-not-contact.js`'s `isBlocked()` check
  (`docs/architecture.md:99,112` confirms step ordering; code-verified at
  `do-not-contact.js:111-130` the check exists and is called from
  `index.js` before reply generation) and by `email-rules.js`/
  `sms-rules.js` rule matching.
- **`http-server.js`'s three routes are a second, unguarded path to the
  same send functions** — `/send-email` (`http-server.js:10-32`) calls
  `emailProvider.sendEmail(data.to, data.subject, data.text, data.html)`
  with **no do-not-contact check, no rule-engine check, and no auth** —
  any payload Core (or anything else reachable on loopback) sends here
  goes straight to SMTP. This bypasses every safety gate the main
  email-processing pipeline applies to outbound replies. **This is the
  highest-risk finding in this census** — it is the one place a
  malformed or compromised caller could send a real message to a real
  person with zero guard rails, and it has no token, no origin check,
  no allowlist.

---

## (g) Tests & CI

**No CI.** `/data/data/com.termux/files/home/Codey-Aigentik/.github`
does not exist — searched via `find .github` (no output) — confirmed
no GitHub Actions workflow in this repo. Whatever tests exist run only
when a human/agent invokes `npm test` locally.

**Test suite:** `tests/` has 20 files covering 15 of 21 source modules
(Jest, `jest.config.mjs`, `--experimental-vm-modules`, `--coverage`).
Source files with **no test file**: `http-server.js`, `index.js`,
`logger.js`, `owner-command.js`, `tone.js`, `trades.js`. Of these,
**`http-server.js` (the unauthenticated send-trigger server) and
`owner-command.js` (parses every admin command) having zero test
coverage is notable** given (f) above — the highest-risk file in the
repo is also untested.

Tests are mock-based (per `tests/*.test.js` naming and the NEW-517 fix
commit's own description: "New test calls `mapJSToCore()` directly (no
fetch mocking) and asserts the stale keys are absent — the assertion
class the prior mocked-fetch-only test suite couldn't provide" —
`e76f1f0` commit message, confirms the suite was previously
mock-fetch-only and missed this exact defect class until this round).
Did not execute the suite (read-only census; running Jest wasn't
required to assess coverage shape and risks touching nothing material).

---

## (h) Dependencies & hygiene

`package.json:1-24` — 4 runtime deps (`chrono-node`, `imapflow`,
`mailparser`, `nodemailer`), 1 dev dep (`jest`). All 4 runtime deps are
actually imported and used (verified: `calendar.js:12`,
`email-provider.js:8-10`). `package-lock.json` present
(152KB, committed). No `yarn.lock` conflict. No obviously unused or
duplicate dependencies.

**Hygiene issue (new finding): 11 duplicate copies of `coreRequest()`.**
Byte-for-byte (or near-identical) copies of the same ~15-30 line HTTP
helper exist in `index.js`, `contacts.js`, `calendar.js`,
`customer-module.js`, `do-not-contact.js`, `email-rules.js`,
`sms-rules.js`, `llama.js`, `owner-command.js`,
`subcontractor-recruiter.js`, plus a near-twin method on a class in
`email-provider.js:646`. `email-rules.js:38` and `sms-rules.js:31` even
have comments acknowledging the duplication ("matching
do-not-contact.js's coreRequest() exactly (single choke point...)" /
"matching do-not-contact.js's/email-rules.js's coreRequest() exactly.
Duplicated..."). This is a maintained, deliberate duplication (commented
as intentional), not an oversight, but it means **any future auth or
retry-logic change has to be made correctly in 11 places**, which is
exactly the kind of surface area that produces the recurring
NEW-51x-class bugs this census was asked to audit for. Logging as a
Suspected hygiene finding — a shared `core-client.js` module would
remove this risk class at the root.

---

## (i) DORMANT findings (reachability-checked)

- `config.sms.poll_interval_ms`/`max_sms_fetch` — DORMANT. Searched
  `grep -rn "config\.sms\." *.js` (excluding `config.json`) — zero
  reads. Config key exists, nothing consumes it.
- Gemini/Vertex LLM providers (`llama.js` `chat()` branches) —
  IMPLEMENTED but DORMANT under current `config.json` (`.llm.provider`
  = `"local"`); code path exists and would run if the config flag
  changed, not exercised today.
- `scripts/send_test_sms.py` — DORMANT. No `.js` file references this
  path (searched for the filename and for `execSync`/`spawn` calls
  naming it — none found). Manual/dev-only script.
- Upstream Aigentik-CLI features beyond the merge base — **not
  determinable** from the local object store; `main..upstream/main` is
  empty, so by this repo's own git history there's nothing upstream has
  that Codey lacks, but this is caveatted on staleness of the `upstream`
  remote ref (see section b).

---

## (j) Open questions

1. Is `~/.codeyOS/restoricon.db`'s Core API server (port 8770) actually
   the backend Aigentik's `config.core_api.base_url` points at in
   production, or is that only true in this dev checkout? (Not
   verified — would need to inspect Core's own route handlers, which
   live outside this repo; `~/restoricon` turned out to be the
   marketing site, not the Core backend.)
2. Does Core's `/api/v1/*` route layer actually reject unknown keys
   uniformly (the NEW-517 fix commit asserts Core's subcontractor
   upsert route does, post-NEW-515), or only on some routes? If
   enforcement is inconsistent, other latent spread-leak sites (like
   `contacts.js`'s, section d) could silently succeed with garbage
   extra keys instead of failing loudly, which is a worse failure mode
   than an outright rejection.
3. Who/what actually calls `http-server.js`'s three routes in
   production, and with what trust boundary? The commit message says
   "Core→Aigentik outbound notifications" but nothing in this repo
   proves only Core calls it — worth confirming from the Core side
   whether anything else on-device could reach `127.0.0.1:8081`.
4. Is the 96-row `api_tokens` table in production actually used for
   anything beyond handing Aigentik this one static token, or is there
   a rotation/expiry mechanism on the Core side that this config's
   never-refreshed token would silently fail against?
