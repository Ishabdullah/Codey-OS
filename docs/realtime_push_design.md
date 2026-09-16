# Restoricon Core — Real-Time Push Layer — Design (D3)

**Status: design only. No code written.** This is a `project-architect`
scoping pass, not a build spec. It reverses a standing, system-wide
architectural decision (`CODEY_MASTER_PLAN.md` §6.9 decision 8, "No
realtime push layer — not needed, not built") on Ish's explicit
2026-09-16 instruction (`sales_rep_portal.md` §4 D3) — Ish already chose
to build this; this document is the *how*, not a re-litigation of
*whether*. Per `CLAUDE.md`'s "when to stop and escalate" (this touches
`CODEY_MASTER_PLAN.md`'s own architecture), **this document should be
reviewed by Ish directly before an `implementer` round is scoped from
it** — the normal architect → implementer → code-reviewer pipeline
alone is not sufficient sign-off for a decision reversal at this level.

**Date:** 2026-09-16.
**Motivating case:** `sales_rep_portal.md` §4a item 3 / D3 — a rep
should learn about a new lead promptly, not only on next page load.
**Scope note:** this document designs the *general* push layer (it is
system-wide per D3's own framing, not sales-portal-scoped), but sizes
its "first cut" event list to the sales-portal motivating case, since
that's the only concrete requirement on record today.

Every factual claim below about the existing codebase was verified by
reading the file directly this session (`CLAUDE.md` rule 12), not
assumed from the file's name or a similar system. See §0.

---

## 0. Verified facts this design rests on

| # | Fact | Where verified |
|---|---|---|
| 0.1 | The API server is a plain stdlib `ThreadingHTTPServer` + `BaseHTTPRequestHandler` (`restoricon_core/api/server.py:185`) — no `asyncio`, no `aiohttp`, no Flask/FastAPI in the serving path. `aiohttp` appears in `requirements.txt:72` but only as a transitive pipeline dependency (`fsspec[http]/datasets`), unrelated to the API server. | `api/server.py:1-40,143-240`; `requirements.txt:45,72` |
| 0.2 | No WebSocket/SSE library or `EventSource` reference exists anywhere in `restoricon_core` today. | `grep -rn websocket\|WebSocket\|EventSource\|aiohttp` across `restoricon_core/` — zero hits outside the unrelated pipeline dependency above |
| 0.3 | The API server runs as **exactly one OS process**, started via `nohup python3 -m restoricon_core.api.server ...` (`lib/service_manager.sh:247`), one `ThreadingHTTPServer` instance, one `serve_forever()` call (`api/server.py:185,235-238`). No worker-process pool, no multiprocessing. | `lib/service_manager.sh:238-247`; `api/server.py:185,235-238` |
| 0.4 | `DatabaseManager.get_connection()` (`restoricon_core/database.py:1051-1067`) caches a `sqlite3.Connection` **per thread**, keyed in `threading.local()` (`database.py:1008`), created lazily on first use and reused for the thread's lifetime. `close()` (`database.py:1420-1426`) releases the thread-local connection but nothing calls it automatically. | `database.py:1008,1051-1067,1420-1426` |
| 0.5 | `RestoriconRequestHandler` never sets `protocol_version`; it inherits `BaseHTTPRequestHandler`'s default, **`HTTP/1.0`**. | `grep -n protocol_version api/server.py` — zero hits |
| 0.6 | `AuditService.log()` (`services/audit_service.py:238-278`) does its own `INSERT` inside `with conn:` (commits on exit) and returns. In `CRMService.create_lead` (`services/crm_service.py:553-...`), the entity `INSERT` is its own separate `with conn:` block that commits *before* `audit.log()` is called afterward as a distinct statement — confirmed for this call site by reading it directly. `audit.log()` is called from ~10+ sites in `crm_service.py` alone (`grep -n audit.log crm_service.py` → lines 167, 434, 597, 748, 823, 1079, 1212, 1260, 1362, 1525) and from other services too — it is a generic, fire-on-every-mutation choke point, not scoped to notification-worthy events. | `services/audit_service.py:238-278`; `services/crm_service.py:553-597` (create_lead) |
| 0.7 | `NotificationService` (`services/notification_service.py`, 57 lines) today only does two things: `send_email` and `send_calendar_invite`/`send_calendar_cancellation`, both by POSTing to Aigentik's HTTP API (`http://127.0.0.1:8081/send-email` etc.) via `urllib.request`. It has no in-process pub/sub, no subscriber list, nothing resembling a broadcaster today. | `services/notification_service.py:1-57` |
| 0.8 | `CRMService._scoped_assignee_filter` / `PERM_READ_TEAM_SALES_DATA` (`services/crm_service.py:626-641`, `auth.py:86`) is the live narrowing mechanism (`NEW-533`'s fix): holders of the permission see every rep's records; everyone else is forced to `actor.user_id` regardless of what they requested. `CRMService.get_lead` (`crm_service.py:607-624`) additionally treats a lead assigned to a *different* specific rep as not-found for a non-privileged actor, **but an unassigned lead (`assigned_user_id is None`) is not hidden** — the `if lead.assigned_user_id is not None and lead.assigned_user_id != actor.user_id` guard only fires when there *is* an assignee. This matches the `NEW-534` claim-workflow premise that the unclaimed pool is visible to all sales reps. | `services/crm_service.py:607-624,626-641` |
| 0.9 | No cookies are set anywhere in the serving path (`grep -n "Set-Cookie\|session_id\|cookie"` across `api/web_surfaces.py`, `api/server.py`, `auth.py` — zero hits). Every staff surface authenticates purely via `getAuthToken()` + `Authorization: Bearer <token>` on each `fetch()` (`sales_rep_portal.md:150-153`, confirmed convention). | grep above; `sales_rep_portal.md:150-153` |
| 0.10 | The service is exposed publicly via a **Cloudflare Tunnel** (`cloudflared tunnel run --token ...`, `lib/service_manager.sh:733`, with its own pid/log files at `lib/service_manager.sh:22-23`), not bound directly to a public IP — `DEFAULT_HOST` is `127.0.0.1` (`api/server.py:34`). Traffic to `*.restoricon.com` passes through this tunnel before reaching the local `ThreadingHTTPServer`. | `lib/service_manager.sh:22-23,238,733`; `api/server.py:34`; `tests/test_subdomain_and_web_surfaces.py:12-30` (confirms subdomain routing — `quote.`/`admin.`/`portal.restoricon.com` — is live routing logic, not just local dev) |

---

## 1. Transport: recommendation and reasoning

**Recommendation: Server-Sent Events (SSE) semantics (`text/event-stream`), consumed via `fetch()` + a streaming `ReadableStream` reader — not the native `EventSource` API.**

Two decisions bundled here; taking them separately:

**(a) SSE over WebSocket.** Confirmed via §0.1/§0.2: this system needs
only server→client push — every client *write* already goes through
ordinary authenticated `POST`/`PUT`/`PATCH` to the existing REST API,
and nothing in this design changes that. WebSocket would require either
a new dependency (violating rule 11 unless justified) or hand-rolling
the RFC 6455 handshake/framing over `BaseHTTPRequestHandler`'s raw
socket — real, avoidable complexity for a channel that only ever needs
to say "go refetch." SSE is plain HTTP: a normal `GET`, a
`Content-Type: text/event-stream` response that's simply never closed,
with `data: ...\n\n` chunks written as events occur. It fits
`ThreadingHTTPServer`'s existing one-thread-per-connection model with
no new library (§8 confirms this against rule 11).

**(b) `fetch()` + `ReadableStream`, not `EventSource`.** The browser's
native `EventSource` constructor (`new EventSource(url)`) cannot set
custom request headers — it cannot carry `Authorization: Bearer
<token>` the way every other call in this codebase does
(`sales_rep_portal.md:150-153`). The standard workaround is a
token-in-query-string (`?token=...`), which was my starting-bias
recommendation in the task framing — **but on reflection I don't
recommend it**, because §0.9 shows there's a strictly better option:
since auth here is bearer-token-only (no cookies to fall back to,
`EventSource`'s `withCredentials` flag would buy nothing), the stream
can instead be opened with `fetch(url, {headers: {Authorization:
'Bearer '+token}})` and consumed via `response.body.getReader()`,
decoding chunks as they arrive — this receives the identical
`text/event-stream` wire format, requires no new client-side
dependency, and matches this repo's existing `getAuthToken()` +
`Authorization: Bearer` convention **verbatim**, rather than
introducing a second, weaker auth mechanism (token-in-URL) alongside
the existing one. The one real cost: `EventSource` auto-reconnects on
disconnect; a `fetch` reader does not, so the client needs an explicit
reconnect loop (open → read loop → on error/close, backoff and reopen).
Per §6 below, reconnection needs no event replay (push is a pure
refetch trigger, never a data source), so this loop is simple: catch
the stream ending, wait with backoff, reopen, and — as a safety net —
trigger one refetch of the currently-open panel immediately on
reconnect, in case anything was missed while disconnected.

**(c) Is polling-interval reduction sufficient instead?** Flagging
explicitly per the task's ask, not deciding unilaterally: whether "new
lead within 10-15 seconds" (a shortened poll) is good enough versus
Ish's actual expectation of "instantly" is not something I have
Ish's answer to. My recommendation defaults to building real push
(SSE) rather than a shortened poll, because (1) Ish already explicitly
chose to override B6.9 decision 8 knowing the cost/tradeoff framing
that was presented to him (per the task description), which reads as
him wanting genuine push, not a faster poll dressed up as one; and (2)
the concrete SSE design below is not meaningfully more complex to
*operate* than a poll once built (§7's heartbeat mechanism is the only
real addition), so there's little to be saved by under-building here.
**This should still be confirmed with Ish before implementation
starts** — if "within ~10s" genuinely satisfies him, a poll-interval
change is a same-day fix with zero new architecture, versus this
design's multi-day build.

---

## 2. Push vs. refetch — confirming the framing, with reasoning

**Agreed: push is a refetch trigger, never a data-carrying channel.**
The server tells the client "something changed, go refetch"; the client
performs a normal authenticated `GET` through the existing
narrowed/permissioned endpoint (`list_leads`, etc.), exactly as it does
today on page load. Reasoning, stated rather than silently adopted:

- §0.8 shows narrowing (`_scoped_assignee_filter`,
  `PERM_READ_TEAM_SALES_DATA`) is real, tested, permission-keyed logic
  living in one place (`CRMService`). A push channel that carried actual
  record data would need to **re-derive that same narrowing** inside a
  second code path (the publish side) to avoid leaking a hidden
  record's contents to a subscriber who shouldn't see it. Two
  implementations of the same permission rule drift over time — this is
  exactly the kind of duplication `CLAUDE.md`'s "don't add abstractions
  that weren't asked for" / "follow existing conventions" guidance
  argues against, and it is also a security-correctness risk category
  (rule 5/CLAUDE.md's verification standard) this project should not
  create casually.
- It also matches §3.5's design (`CODEY_MASTER_PLAN.md`, "one API, one
  auth, no local store") in spirit: every surface still gets its data
  from one place, the REST API, under the one set of permission checks
  that already exist there. Push only changes *when* the client asks,
  never *what* it's allowed to see or *how* it's allowed to see it.
- Cost of this choice: an extra request round-trip per event (refetch
  after being told to). At this scale (§7's headcount reasoning) this
  is negligible — not a reason to reconsider.

---

## 3. Which events to push — first-cut recommendation

Full candidate list from the task, evaluated:

| Candidate event | First cut? | Reasoning |
|---|---|---|
| **New lead created** | **Yes** | The concrete motivating case (`sales_rep_portal.md` §4a item 3). Also the simplest recipient computation (§4): per §0.8, unassigned leads are visible to *every* sales rep today, so this event's recipient set is "every connected actor holding `PERM_READ_LEADS`/`PERM_READ_CRM`" — no per-record narrowing decision needed for the unassigned case, which is the common case for a brand-new lead. |
| **A lead/opportunity/task assigned to me** | **Yes** | Directly relevant post-`NEW-534` (claim workflow) and post-D2 (`sales_manager` role) — a rep should know the moment something lands in their queue, whether by manager assignment or the new claim mechanism. Recipient set is exactly one user id (`assigned_user_id`), the simplest possible narrowing case (§4). |
| **Someone else claims a lead I'm viewing** | **Yes, and specifically because it's a direct UX fix, not just nice-to-have** | Today's `NEW-534` claim flow, per the task framing, produces a stale-button 409 if two reps look at the same unclaimed lead and one claims it first. A push event here removes the stale "Claim" button live instead of surfacing a confusing failure on click. Recipient set: every connected actor currently viewing the unclaimed pool (in practice, same broadcast group as "new lead created" — actors with read access to unassigned leads), so this reuses the exact same publish call as the first event, differentiated only by event name (`lead.claimed` vs `lead.created`), not new recipient-resolution logic. |
| Admin/manager broadcast-style events | **Deferred** | No concrete first-cut use case stated yet; adding a generic "broadcast to a role" mechanism before there's a real consumer risks over-building. The broadcaster design in §5 supports it later with no rework (broadcast is just "recipient set = everyone connected", already a degenerate case of the per-event recipient computation). |
| Appointment reminders | **Deferred** | This is a *scheduled*, time-based notification (surface at T-minus-N), not an event reacting to a mutation — it needs a scheduler/cron-like trigger, not a `publish()` call at a write site. Different mechanism, genuinely separate scope; do not conflate with this event-driven design. `NotificationService`'s existing calendar-invite path already covers the email side of this. |

**First cut: exactly these three events** — `lead.created`,
`assignment.created` (generalizes to opportunities/tasks, same shape),
`lead.claimed` — chosen because (a) they cover the concrete motivating
case plus the two next-most-obviously-valuable ones, (b) between them
they exercise both recipient-computation shapes this design needs
(broadcast-to-permission-holders and single-user), so the mechanism is
proven for the general case without building every event up front, and
(c) explicitly deferring the rest keeps this a scoped first round per
this session's established pattern (every other B8 follow-on task was
sized the same way).

---

## 4. Recipient computation and narrowing — the exact rule

**Rule: a push event's recipient list is derived using the same
permission logic as the corresponding read path, computed once at
publish time — never "broadcast to everyone connected, let the
client's refetch sort it out."**

Concretely, for the three first-cut events:

- **`lead.created`** (unassigned lead — the common case per §0.8):
  recipients = every currently-connected actor for whom
  `actor.has_permission(PERM_READ_LEADS) or
  actor.has_permission(PERM_READ_CRM)` is true (the same check
  `list_leads`/`get_lead` already perform). No per-actor narrowing
  needed beyond that, because an unassigned lead has no
  `assigned_user_id` to narrow against — confirmed by §0.8, so this is
  not a hypothetical simplification, it's the actual current visibility
  rule. If a lead is ever created *pre-assigned* (bypassing the
  unclaimed pool), this event's recipient computation must instead use
  the same rule as `assignment.created` below — flag this as an
  implementation-time branch, not an unhandled case.
- **`assignment.created`** (lead/opportunity/task assigned to a
  specific rep): recipients = exactly the one user id in
  `assigned_user_id`, plus every actor holding
  `PERM_READ_TEAM_SALES_DATA` (managers/`sales_manager`/`ai_agent` per
  §0.8's precedent, since they can already see any rep's assigned
  records and arguably want the same live update a manager dashboard
  would show). This mirrors `_scoped_assignee_filter`'s exact logic —
  same permission check, same "team-wide or forced-to-self" shape.
- **`lead.claimed`**: recipients = same set as `lead.created`
  (everyone with unclaimed-pool read access) — this event is
  specifically about removing a stale UI affordance for anyone who
  might currently be looking at that now-claimed lead, not about
  narrowing to the claimant.

**On the existence-leak question** (does firing a trigger for an actor
who can't see the underlying record leak the record's *existence*, even
if their subsequent refetch returns nothing): for these three specific
first-cut events, this does not arise, because in every case the
recipient computation above already restricts the trigger to actors who
*can* see the record — the recipient list **is** the permission check,
not a broadcast followed by a client-side filter. This principle
generalizes: **any future event added to this system must compute its
recipient list from the same permission/narrowing logic its
corresponding read endpoint uses, before publish**, precisely so this
question never needs a case-by-case leak judgment call later. State this
as a standing rule for whoever adds the next event, not just a fact
about these three.

---

## 5. Where `publish()` is called from

**Recommendation: explicit `publish()` calls at the specific mutation
call sites for these three events, not a generic hook on
`AuditService.log()`.**

The audit-log-as-seam idea (a single choke point every relevant write
already passes through, per the task's own framing) is worth stating
why it's *not* the right seam for this first cut, since it's the
obvious-looking alternative:

- **Frequency mismatch.** `audit.log()` fires on essentially every
  mutation across every service (§0.6 — ~10+ sites in `crm_service.py`
  alone, and it's a generic append-only audit mechanism used
  project-wide, not scoped to sales or to notification-worthy actions).
  Hooking `publish()` into it directly would require an
  `(action, entity_type)` → "is this notify-worthy" allowlist living
  *inside* the generic audit path, mixing a cross-cutting audit
  concern with a feature-specific notification concern. That allowlist
  would need to be kept in sync by hand as new audit call sites are
  added elsewhere in the codebase for entirely unrelated reasons —
  exactly the kind of hidden coupling `CLAUDE.md`'s "follow existing
  conventions" / "don't add abstractions that weren't asked for"
  guidance argues against introducing casually.
- **Transaction-ordering is actually fine, but doesn't change the
  call**. §0.6 confirms, for `create_lead` specifically, that the
  entity's own `INSERT` commits in its own `with conn:` block *before*
  `audit.log()` is invoked as a separate statement — so by the time
  `audit.log()` runs, the write has already durably happened, and there
  is no rollback-after-publish risk for that call site. That removes
  one argument against the seam, but doesn't resolve the frequency-
  mismatch problem above, and this ordering was only verified for one
  call site — it would need re-verification per site before ever being
  relied on generally.
- Per `CLAUDE.md`: "Three similar lines beat a premature abstraction."
  Three explicit `publish("lead.created", ...)` /
  `publish("assignment.created", ...)` / `publish("lead.claimed", ...)`
  calls, placed directly in `CRMService.create_lead`,
  `CRMService.update_lead`/`update_opportunity`/`update_task` (wherever
  `assigned_user_id` transitions from `None`→a value or from one rep to
  another), and the new `claim_lead`/`claim_opportunity`/`claim_task`
  methods (`NEW-534`, already shipped) is small, explicit, and easy to
  audit for correctness — exactly the three call sites this feature
  actually needs, no more.

**Revisit later, not now:** if a fourth or fifth event is added and the
call-site count starts to sprawl, that's the point to reconsider a
structured hook (e.g., a small decorator, or a scoped subset of audit
actions that *do* opt into notification) — not before there's evidence
of the sprawl actually happening.

**Publish must not block the calling (DB-writing) thread on any
network/socket I/O.** `publish()` itself should do only in-memory work:
look up the broadcaster's current subscriber list, compute the
recipient set (§4), and enqueue the event onto each matching
subscriber's own outbound queue (§7's bounded, non-blocking queue) —
never write to a client socket directly from the thread that just
committed a database write. This is what prevents a slow or stuck SSE
client from ever stalling a CRM mutation.

---

## 6. Reconnection / missed-event handling

**Recommendation: no event replay or backlog — confirmed, for the
reason stated in the task framing.** Because push is purely a refetch
*trigger* (§2), the client was never relying on the stream itself as a
data source; the actual state always comes from the next `GET`. A
dropped connection (laptop sleep, wifi blip, backgrounded tab)
therefore needs exactly one thing on reconnect: **the client should
perform one refetch of whatever panel(s) are currently open/visible
immediately upon reconnecting**, as a safety net in case something
happened while disconnected — not because the stream needs to replay
missed events, but because the client has no other way to know
whether it missed one. This is strictly simpler than backlog/replay
(no server-side per-client event history to retain, no sequence
numbers, no "catch-up" protocol) and is consistent with §3.5's
zero-local-store design: the client already refetches on every page
load and every action; reconnect is just one more trigger for the same
existing refetch path.

---

## 7. Resource / lifecycle safety

This is the section rule 2/3 exist for — a new class of long-lived
server-side resource per client, on a device with a documented crash
history from resource contention.

**Realistic scale, stated explicitly:** Restoricon is a single small
business; per `sales_rep_portal.md`'s own framing there is a small sales
team (single-digit to low-double-digit reps) plus a handful of
manager/admin/PM/tech accounts. Concurrent open SSE connections at any
moment will realistically be a handful, not dozens. This is not a
web-scale concurrency problem — but it is still a *new* long-lived
resource type this server has never held before, so the following
guardrails are concrete requirements, not speculative hardening:

- **DB connection must not be pinned for the stream's lifetime.** §0.4
  confirms `get_connection()` caches one `sqlite3.Connection` per
  thread indefinitely. An SSE handler thread that lives for hours must
  **not** hold a DB connection open while idle in its write loop — it
  should resolve `actor`/subscriber identity (a normal, brief DB read
  through the existing auth path) once at connection start, then call
  `DatabaseManager.close()` (or equivalent) to release that thread's
  connection before entering the long-lived write loop, since the
  stream loop itself does no further DB work (it only writes
  pre-computed event payloads to the socket). This must be stated as an
  explicit implementation requirement, not left implicit, given §0.4's
  "nothing calls `close()` automatically" finding.
- **A heartbeat is required, not optional**, and for a specific reason:
  the stream only ever *writes* to the client; TCP gives the server no
  signal that a peer vanished (closed laptop, dead wifi) until the
  server itself attempts a write and the OS reports the failure.
  Mechanism: write an SSE comment line (`: keepalive\n\n` — a line
  starting with `:` is valid SSE and ignored by the client's parser)
  every 15-30 seconds from that connection's own thread. A dead peer
  causes that write to raise `BrokenPipeError`/`ConnectionResetError`;
  the handler catches it, removes itself from the broadcaster's
  subscriber list, and returns (ending the thread). This is the
  connection-cleanup mechanism — no separate reaper/sweep process is
  needed if every subscriber thread detects its own death via a failed
  write.
- **Per-subscriber outbound queue must be bounded and non-blocking.**
  Each subscriber is represented by a small, bounded `queue.Queue`
  (e.g. capacity ~50 events) that `publish()` (§5) enqueues onto with
  `put_nowait()`, never blocking `put()` — if a queue is full (a client
  reading unusually slowly), the oldest or newest event is dropped
  (drop policy: fine either way, since events are pure triggers, not
  data — a dropped `lead.created` trigger just means that client's next
  independent action/reconnect refetch catches it late, not that data
  is lost) rather than ever blocking the publishing thread. This is
  what guarantees §5's "publish never blocks the DB-writing thread"
  property even under an unusually slow subscriber.
- **An explicit max-concurrent-streams cap.** `ThreadingHTTPServer` has
  no built-in connection limit at all (confirmed by its stdlib
  contract — it spawns a thread per accepted connection unconditionally).
  Given the realistic headcount above, a cap around 32 concurrent SSE
  connections is generous relative to actual usage and turns "could
  this run the phone out of resources" into simple, checkable
  arithmetic (32 threads × one bounded in-memory queue each) rather
  than an open-ended question. A connection beyond the cap should
  receive `503 Service Unavailable` immediately rather than being
  silently accepted and contending for resources.
- **`protocol_version` / keep-alive.** §0.5 confirms the handler
  defaults to HTTP/1.0, which does not natively support the
  "write chunks, never close" streaming pattern SSE relies on without
  explicit handling — `BaseHTTPRequestHandler` in HTTP/1.0 mode closes
  the connection after each response unless the handler manages
  keep-alive itself. The SSE handler needs to either set
  `protocol_version = "HTTP/1.1"` on the connection (enabling
  persistent connections) or explicitly manage `self.close_connection =
  False` and flush (`self.wfile.flush()`) after each written chunk, so
  events are actually delivered incrementally rather than buffered
  until the (never-arriving) response end. **This must be verified live**
  (does a chunk actually arrive at the browser before the connection
  is closed?) — it is exactly the class of thing this project's own
  history (`NEW-259`) shows review alone won't catch.
- **Cloudflare Tunnel path (§0.10).** Traffic reaching this server for
  any `*.restoricon.com` request passes through `cloudflared`, not a
  direct socket. Cloudflare Tunnel does support long-lived streaming
  HTTP responses in general, but **this must be live-verified against
  the actual deployed tunnel**, not assumed from Cloudflare's general
  product docs (rule 12) — specifically checking for (a) response
  buffering that would delay event delivery, and (b) an idle-connection
  timeout that would kill the stream faster than this design's
  heartbeat interval, which would mean shortening the heartbeat, not a
  redesign. This is exactly the kind of thing that needs a
  `live-verifier` pass before this is called done, not just
  code-review.

---

## 8. `install.sh` / rule 11

**No new dependency is needed.** SSE over the existing stdlib
`ThreadingHTTPServer` requires nothing beyond what's already imported
(`http.server`, `threading`, `queue` — all stdlib). The client side
needs nothing beyond `fetch()` and `ReadableStream`, both already
available in any browser this portal already targets (no new `<script
src>`, no new npm/pip package). **`install.sh` needs no change for this
design** — stated explicitly per rule 11 rather than left unaddressed.
If a future event needs anything beyond stdlib (unlikely for this
design), that would need its own `install.sh` update at that time.

---

## 9. Concrete "first cut" recommendation (implementer-ready summary)

For a future, separate `implementer` task (not this one) to pick up,
once Ish has reviewed this design directly:

1. **Transport:** SSE (`text/event-stream`) over the existing
   `ThreadingHTTPServer`, one new route (e.g.
   `GET /api/v1/sales/stream` or a more general `/api/v1/stream` if
   other roles get events in a later round — recommend the general path
   name now even though only sales-relevant events ship first, to avoid
   a rename later).
2. **Client:** `fetch()` + `response.body.getReader()`, `Authorization:
   Bearer <token>` header (existing convention, §1(b)) — not native
   `EventSource`. Explicit reconnect loop with backoff; on every
   (re)connect, trigger one refetch of the currently-open panel (§6).
3. **First 3 events:** `lead.created`, `assignment.created` (leads/
   opportunities/tasks), `lead.claimed`. Recipient computation per §4,
   reusing `_scoped_assignee_filter`'s exact permission logic — not a
   parallel implementation of it.
4. **Publish seam:** explicit `publish()` calls at the ~3-5 specific
   `CRMService` mutation methods involved (`create_lead`,
   assignment-changing paths in `update_lead`/`update_opportunity`/
   `update_task`, and the `NEW-534` claim methods) — not a generic
   `AuditService.log()` hook (§5). `publish()` does only in-memory
   enqueue work, never blocking network I/O, never called from inside
   an open DB transaction's critical section.
5. **Broadcaster:** one in-process singleton (safe per §0.3 — single
   process, no external broker needed) holding a thread-safe map of
   subscriber id → bounded `queue.Queue`. Each SSE handler thread reads
   its own queue in a loop, writes `data: ...\n\n` per event, and a
   `: keepalive\n\n` comment every 15-30s (§7).
6. **Auth:** existing bearer-token `Authorization` header, unchanged —
   no new stream-specific token type, since §1(b)'s `fetch`-based
   approach removes the reason a separate short-lived token would have
   been needed (no token-in-URL, so no browser-history/access-log
   exposure tradeoff to accept).
7. **Cleanup:** heartbeat-write-failure detection (§7), no separate
   reaper needed. Cap at 32 concurrent streams, `503` beyond that.
   Release the handler thread's DB connection before entering the
   write loop (§0.4/§7).
8. **`install.sh`:** no change (§8).
9. **Before implementation starts:** (a) Ish reviews this document
   directly given the architecture-reversal stakes; (b) confirm with
   Ish whether "within ~10-15s" (a much cheaper poll-interval shortening)
   would actually satisfy the real need, since that changes the
   cost/benefit materially (§1(c)); (c) live-verify the Cloudflare
   Tunnel streaming behavior (§7) and the HTTP/1.0-default keep-alive
   handling (§7) early in the implementation round, since both are
   exactly the class of assumption this project's history shows
   code-review alone won't catch (`NEW-259`).

---

## 10. What this document deliberately does not do

- Does not write any code — this is a scoping/design pass only, per the
  task's explicit framing.
- Does not update `CODEY_MASTER_PLAN.md` §4/Appendix A status markers —
  nothing here is code-complete, approved, or live-verified; the
  existing unchecked Appendix A line ("Real-time push layer (new,
  system-wide, not B8-scoped)") already reflects "not yet built"
  accurately and should simply gain a pointer to this document, not a
  status change.
- Does not design the appointment-reminder scheduler (§3, deferred) or
  the admin/manager broadcast mechanism (§3, deferred) — both are real
  future extensions of this same broadcaster, not designed further
  here because neither has a concrete first-cut requirement yet.
- Does not decide the D3 poll-vs-push tradeoff finally (§1(c)) — flags
  it for Ish's confirmation rather than assuming the more expensive
  answer is definitely wanted at the "instant" granularity.
