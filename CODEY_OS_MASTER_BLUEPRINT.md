# CODEY-OS MASTER BLUEPRINT

**Status:** COMPLETE DRAFT — awaiting Ish's review (2026-10-06)
Census: 8 parallel read-only agents + coordinator. All 22 directive §16 sections
written. Per-task census reports retained in the session scratchpad; their findings
are folded in below with `file:line` citations.
**Nothing was implemented, moved, deleted, or archived this round** (directive §17).
**Authority:** This document does **not** yet supersede `CODEY_MASTER_PLAN.md`.
It becomes the primary execution document only on Ish's explicit approval.
Until then `CODEY_MASTER_PLAN.md` remains authoritative.

**Source directive:** `CODEY_OS_OPUS_BLUEPRINT_DIRECTIVE.docx` (Downloads,
2026-10-06, 45,662 bytes). Full extracted text archived at
`docs/directives/OPUS_BLUEPRINT_DIRECTIVE.txt` (to be added).

**Method rules in force for this census (directive §3, §5, CLAUDE.md r5/r12):**
- Every status label cites `file:line`. No claim from README text or prior plans.
- Status is decided by **reachability from a real entry point**, not by how
  finished the code reads. No caller path ⇒ `DORMANT`.
- Restoricon production store is **read-only**; copy before any inspection.
- This round **proposes**; it does not move, delete, or archive anything.

---

## Pre-census facts captured (verified 2026-10-06)

| Fact | Evidence |
|---|---|
| Codey-OS HEAD | `405d9cf` 2026-10-06 "NEW-754 ledger: live model-load verification confirmed" |
| Codey-OS branches | `main`, `codey-os-dev-v2` (+ same on origin) |
| **Stranded Stage-0 work** | `codey-os-dev-v2` holds 2 commits not on main: `97ad62d` "S0.1: full-fidelity trajectories, export hygiene, bench grade() fix", `8d1c37e` "Stage 0 kickoff". `main` is 4 ahead. |
| Rollback tags | `rollback/2026-09-30-pre-agi-audit-fixes`, `rollback/2026-09-30-pre-agi-merge`, `rollback/2026-09-30-pre-dev-v2` |
| Codey-OS size | 946 tracked files — 502 `.py`, **389 `.md`** |
| Codey-Aigentik | HEAD `e76f1f0` 2026-09-15; 74 files (41 `.js`); tags v1.0.0–v1.1.0; has `upstream/` remote (fork) |
| **Private-Codey-Agent vs private-agent** | Two near-duplicate Flutter trees: 196 vs 192 tracked files. `Private-Codey-Agent` HEAD `efe9a1c` 2026-08-30 (has `upstream/`); `private-agent` HEAD `9dc89cf` 2026-08-27. Canonical not yet determined. |
| Codey-Estimator-reference | HEAD `df0730f` 2026-09-27; **no `main` branch** — `origin/HEAD` → `claude/epic-archimedes-z3luuu`; 58 files (46 `.py`) |
| OpenCL-S24-Ultra | HEAD `6f766c0` 2026-10-05 "Record October 5 performance checkpoint and three matched OpenCL tests"; 360 files; tag `v0.1.0`; 8 `.patch` files, 14 `.cpp`, 19 `.csv` |
| `restoricon/` repo | HEAD `73eee40` 2026-09-20; 105 files, mostly `.jpg`/`.html` — a **static marketing site**, not the business data system |
| **Live Restoricon data store** | `~/.codeyOS/restoricon.db` — 4,018,176 bytes, mtime 2026-09-30 17:50, with live `-wal` (1,058,872 b) and `-shm`. Plus 4 dated backups and `~/.codey_restoricon/core.db*` (pre-B2 era). |
| Live processes at census start | **None** except `python battery-watch.py` (PID 31924). No listening TCP ports. Codey-OS and Restoricon services are *not* currently running — this is a finding, not an all-clear. |
| Memory at census start | `free -h`: 10Gi total, 6.3Gi used, 686Mi free, 4.2Gi buff/cache, 4.6Gi available; swap 15Gi total / 3.3Gi used |
| Repos named in directive §3 but absent locally | `Codey`, `Codey-v2` (lineage ancestors), `Aigentik-CLI` (ancestor of Codey-Aigentik) |
| Uncommitted at census start | 12 files, all `.claude/agent-memory/code-reviewer/*` — reviewer notes, out of census scope |

---

## 1. Executive architecture and research objective

### 1.1 The objective (directive §2)

Codey-OS is a **persistent developmental AI architecture** — not an LLM wrapper,
and not a claim that AGI has been designed. It should accumulate verified
experience, memory, skills and developmental history; become progressively less
teacher-dependent; generate bounded practice and curiosity; safely test its own
improvements; and replace or enlarge its underlying model without losing
accumulated development.

The neural model is a replaceable brain, not Codey's identity. The whole system is
the research object. Learning requires measurable evidence.

### 1.2 What the census found

The working parts are real. The coding agent, the Core API, the resource gate, and
the Aigentik communications pipeline are genuinely implemented, and the Restoricon
business system holds live production data (249 contacts, 309 communications, 783
audit records). Rule 3 compliance is clean, the promotion gate is conservative and
fail-closed, and the resource gate's hard-won fixes are present and correct.

**But the developmental architecture is not yet started, and the gap is different
from what prior plans assumed.** Three findings define this blueprint:

**1. There is currently no mechanism by which experience changes future behavior.**
Of five documented memory tiers, **one** reaches a prompt — and it silently stops
at 50% context fill. Tier 2 stores an md5 hash, not content. Tier 3 is a dead
parallel retrieval stack. RAG is wired end-to-end with **no corpus** and no
ingestion path. Trajectories **truncate at record time**. Directive §14's first
principle — *"experience is not learning until it measurably changes future
behavior"* — is not yet satisfiable.

**2. The evaluator is contaminated, and the contamination is prescribed by the
project's own documentation.** A verified three-hop path feeds the 8 frozen
benchmark tasks into the fine-tuning corpus, after which the gate grades candidates
on those same 8 tasks. `AGI_AUDIT_LOG.md`'s documented Phase 3 step is the thing
that triggers it. Latent today; fires on the first prescribed run. Scores would go
**up**. Separately, **rollback does not exist** — CLAUDE.md rule 1 is 3-of-4 in
code — and the AGI scorecard's 18/100 baseline has **no rubric in the repo**, so it
is unreproducible.

**3. The documented OS shell is largely not wired.** CCOS has no runtime; its live
surface is **5 of ~25 modules**, with ~8,000 lines dormant. The system's only
safety validator **has never run**. The sandbox never runs. There is **no Action
Gateway** — irreversible actions pass through three disjoint surfaces, one with no
safety checks at all. And there are **two unauthenticated paths to sending real
email to real people**, neither audited.

### 1.3 The recurring pattern — and why older plans missed it

Three failure shapes, none of which announce themselves:

- **Complete code with no caller** — the sandbox, the safety veto, memory tier 3,
  `recovery.py`, two shell validators, `telemetry_engine`, 10 estimator modules.
  Reads as finished; moves nothing.
- **Plumbing without content** — RAG with no corpus, a ledger with no entries, a
  pricing job with no worker, 161 registry entries that are never enforced.
- **Confident falsehood** — a device mock returning `"sent": True`, a "Project
  Memory" prompt block sourced from an unrelated module, a green security suite over
  a function production never calls, OpenCL reporting 29/29 offload while running
  on CPU.

None are visible in a TODO scan: the repo is nearly free of `FIXME` and
`NotImplementedError`. They are only visible by **tracing reachability from a real
entry point**, which is why that was this census's load-bearing method and why §11
recommends making it a standing pipeline question. The third shape is the most
dangerous, because it would poison the experience store the whole research
programme is built on.

### 1.4 What this changes about the plan

**Directive §6 makes NPU integration the first technical priority. The census
supports the ordering but reframes the first step:** both deployed models are
**ineligible** for both NPU handoff prototypes — the primary is `qwen35`, a hybrid
SSM/attention architecture, and the embed model is `nomic-bert` with no KV cache at
all; neither is in either patch allowlist. So the directive's own precondition
("benchmark the exact deployed models first") is not satisfiable on the current
path. The **backend-independent BrainManager boundary comes first** — it is
independently valuable, it fixes the real operational risk (a second, unmanaged
model-load owner bypassing the daemon), and it does not wait on the model decision
that NPU does.

**S0 is bigger than the old plan assumed.** It is not a preliminary step before the
interesting work; it *is* the work for now. Measurement fidelity, a clean
evaluator, rollback, and an action gateway are the prerequisites that every later
stage silently assumed were already there.

**One piece of good news:** a brain swap today would lose almost nothing, because
almost nothing model-independent has accumulated yet. The architecture can be
fixed before there is anything to lose.

### 1.5 How to read the roadmap

§21 orders work by what makes later work *safe* or *meaningful*, not by ambition:

- **P0** — live ungated paths to real people, and mechanisms that would silently
  corrupt the research data. No dependencies; start immediately.
- **P1** — make measurement trustworthy: CI (2,854 tests currently never run),
  trajectory fidelity, rollback, a real rubric.
- **P2** — the Action Gateway and the production firewall. **Must precede any CCOS
  wiring**, because connecting CCOS activates latent defects and a sandbox that can
  write to its own source.
- **P3** — brain abstraction, then NPU.
- **P4** — make memory actually read back.
- **P5** — cleanup, continuous and in parallel (directive §9), not deferred.
- **P6** — S2–S6, **deliberately not detailed yet**; re-planned when P4 lands.

Eight decisions were raised for Ish; they are tabulated at the end of §21.
**One is already resolved:** Restoricon is **manually started and not yet in full
operational use** (Ish, 2026-10-06), so **data integrity — not availability — is
the binding constraint**. That materially de-risks the roadmap: services may be
stopped and restarted during development under a check-before-acting rule, and no
zero-downtime migration machinery is needed. What does *not* relax: never writing
to the live store from development work, and the two unauthenticated email paths,
which stay the highest-severity findings regardless (`contacts` holds 249 real
people). See §9.4. **Seven decisions remain open.**

### 1.6 Restoricon safety statement

Nothing was started, stopped, migrated, reconfigured, or written during this
census. The live store was inspected **only as a copy**, with original mtimes
confirmed unchanged afterward. The production surface turns out to be **narrower
than the schema implies** — 31 of 70 tables hold data, and every estimator and
pricing table is empty — which means those subsystems are code-complete but
**never exercised in production**, and any plan line calling them "done" is
claiming code completion, not production validation (CLAUDE.md rule 7).

## 2. Verified current-state architecture and runtime flow

Every claim here is traced to `file:line` by census A1. Where this contradicts
`docs/architecture.md` (2026-07-29) or `CODEY_MASTER_PLAN.md` §3, **this section
is the verified one** and those are stale (§8.3).

### 2.1 Actual process topology when "fully up"

```
codey  (superset entry point)
  └─ codey-start → lib/service_manager.sh:start_all_services (:891-899)
       ├─ 1. daemon            core/daemon.py        PID file, socket
       ├─ 2. Core API          restoricon_core.api.server   127.0.0.1:8770
       ├─ 3. Aigentik worker   ~/Codey-Aigentik/index.js    (NOT a server)
       └─ 4. embed server      embed_server.py        port 8082, NO PID file

   ccos/  ── started by nothing. In-process import only.
```

**Three findings embedded in that diagram:**

1. **CCOS has no runtime.** `start_all_services` (`service_manager.sh:891-899`)
   starts nothing from `ccos/`. CCOS is an in-process import, reached only from
   `main.py:561` and `restoricon_core/api/routes.py:533`. The documented "OS shell
   that discovers, routes, monitors, and eventually self-improves capabilities" is
   a **library loaded by two other processes**. Combined with §16.2 (only 2 of ~25
   ccos modules imported; ~8,000 lines dormant), this is the **largest
   architectural divergence in the system** between documented and actual design.
2. **Aigentik is not a server.** `index.js` contains no `listen(`. Its `a_port`
   config is parsed at `service_manager.sh:285,436,496` and **never used again** —
   dead twice over.
3. **`codey` is the superset, `codey-start` a thin subset** — the inverse of
   CLAUDE.md's claim that `codey-start`/`codey-stop` are "the unified entry
   points". `codey` and `codey-metrics` are omitted from the map entirely.

### 2.2 The model-load path has a second, unmanaged owner — top operational risk

The daemon is supposed to own model loading. It does not, exclusively:

| Path | Mechanism |
|---|---|
| Daemon (intended) | socket protocol |
| **Aigentik (actual, parallel)** | `~/Codey-Aigentik/index.js:228` → `execSync("python3 .../tools/ensure_model_cli.py")` → `tools/ensure_model_cli.py:92` calls `core.loader_v2.get_loader()` **directly** |
| Release side | *does* go through the daemon socket (`tools/release_model_cli.py:73,77`) |

So a **2.7 GB model load happens inside a short-lived, Node-spawned Python
process**, bypassing the daemon, reached from `start_all_services` step 3. Both
calls run `stdio:'ignore'` — **every failure is silent to Aigentik**.

This sits directly in CLAUDE.md rule 2 (RAM discipline; this device has crashed
from concurrent model loads). What currently makes it safe is the per-port lock
(`loader_v2.py:564-600`) and slot reservation (`:1450`). **Whether those suffice
under real concurrent load is not statically verifiable** — this needs
live-verifier time, and it is the single most important runtime risk found.

### 2.3 The model, verified from the artifact (CLAUDE.md rule 12)

Full 46-key GGUF dump — not a filtered grep, not inferred from the name:

| Key | Value |
|---|---|
| `general.architecture` | **`qwen35`** |
| topology | **hybrid SSM/attention** — `ssm.conv_kernel`, `ssm.state_size`, `ssm.group_count`, `ssm.inner_size` present |
| `full_attention_interval` | **4** → only ~8 of 32 blocks hold a KV cache |
| `context_length` (native) | **262,144** |
| configured `n_ctx` | 65,536 |
| `head_count` / `head_count_kv` | 16 / 4 |
| `key_length` / `value_length` | 256 / 256 |

This vindicates CLAUDE.md rule 12's specific warning: Qwen3.5 is **not** Qwen3
with a bigger number. It is a hybrid SSM/attention model where most blocks carry
no KV cache at all.

**Consequence — open risk:** `core/resource_gate.py`'s KV cost model **may
overestimate memory by ~4×** if it assumes 32 uniform attention layers. A1 did not
audit those 4,911 lines. This is a **high-value follow-up**: a 4× overestimate
would make the resource gate refuse loads it could safely admit, and it directly
affects every NPU/CPU scheduling decision in §10/§19.

### 2.4 Spawn-path divergence

The exact `llama-server` argv is recorded in A1's report, including the NEW-754
`--load-mode mmap` default (commit `b5b805a`). But the **embed server's argv
(`embed_server.py:139-158`) passes no `--load-mode` at all** — two spawn sites
using the same binary with divergent flag sets. A BrainManager boundary (§10)
must unify these rather than inherit both.

### 2.5 A dashboard-only user is invisible to the interactivity signal

`is_interactive_session_active()` (`core/resource_gate.py:3961-3981`) resolves to
**TUI-PID-file scanning alone**, and the only writer is `main.py:401-447`.
**Nothing in `restoricon_core/` writes a session marker.**

So a person working entirely through `/admin` registers as *"no human present"*,
which changes:
- background-dispatch deferral (`daemon.py:1288,1488`)
- interactive-vs-background `n_ctx` selection (`loader_v2.py:1363-1372`)
- context-budget admission at three sites

`resource_gate.py:3977-3980` explicitly anticipates this — *"if a GUI is ever
reintroduced, restore the signal WITH a freshness/liveness guard."* **The web
dashboard is that reintroduction, and the signal was never restored.**

This also collides with the standing "dashboard = single control surface"
direction (Ish, 2026-09-10).

### 2.6 No readiness gating anywhere in startup

Every service starts as `nohup ... &` + `sleep 0.5` + `kill -0`
(e.g. `service_manager.sh:250-258`). That proves **a fork, not a port bind**.

The Core API constructs ~15 services and binds in `__init__`
(`restoricon_core/api/server.py:158-238`), so a port-in-use failure raises
**after** the PID file is written — the exact self-race shape CLAUDE.md rule 4
warns about. Any startup change here needs code-reviewer approval.

### 2.7 What is genuinely healthy

Worth stating plainly, since most of this section is problems:

- **The resource gate is live, not shelfware.** `rg.reserve_slot(spec,
  port=PRIMARY_SERVER_PORT, meminfo=...)` at `loader_v2.py:1450` — the NEW-259
  `port=` fix is present and correct. Context budget is live at three real call
  sites. `~/.codeyOS/resource_bus.db` has a 2026-10-06 mtime.
- **CLAUDE.md rule 3 compliance is clean.** No `pkill -f` anywhere in the service
  scripts; all kills are tracked-PID or two-factor cwd+cmdline-token
  (`service_manager.sh:145-195`).
- **No code stubs in A1 scope** — zero `NotImplementedError`/`FIXME`/`HACK`.

## 3. Repo-by-repo responsibility and integration contracts

Directive §4's default — **coordinated multi-repo, do not merge to simplify the
tree** — is upheld. The census found no case where merging helps; it did find that
one repo is redundant and one boundary is misplaced.

### 3.1 Dispositions

| Repo | Directive default | Census verdict |
|---|---|---|
| **Codey-OS** | core | **Confirmed.** But it currently also *contains* the production business system (`restoricon_core/`) — see §3.3. |
| **Codey-Aigentik** | separate integrated capability | **Confirmed.** Distinct deps (Node), distinct failure boundary, genuinely working. |
| **Private-Codey-Agent** | separate strongly-permissioned capability | **Confirmed in principle, absent in practice.** The security boundary is currently a fail-open auth check plus a veto on the wrong side (§12.4). |
| **Codey-Estimator-reference** | separate canonical until proven | **Reframed.** Not a standalone app — a stdlib-only library, already vendored verbatim (§14.1). Keep as the upstream vendoring source; add a drift check. |
| **OpenCL-S24-Ultra** | separate research backend | **Confirmed, emphatically.** §10's patch-pinning and llama.cpp churn is exactly the instability that must not reach cognitive code. |
| **restoricon** | separate production repo | **Confirmed, but it is not what the directive meant** — a static marketing site, no production coupling (§9.1). |
| **private-agent** | — | **Redundant.** Pure ancestor, zero unique content (§4.2). Propose retirement. |

### 3.2 Integration contracts as they actually exist

| Link | Transport | State |
|---|---|---|
| Aigentik → Core | HTTP/JSON `127.0.0.1:8770`, static bearer | **working**, 54 audited sites |
| Core → Aigentik | HTTP `127.0.0.1:8081` | **working but unauthenticated** (§13.4) |
| Aigentik → model | `execSync` → `ensure_model_cli.py`, **bypasses the daemon** | **risk** (§2.2) |
| Private-Codey-Agent → Core | REST, expects **:8765** | **broken** — Core is on :8770 (§12.2) |
| Private-Codey-Agent ↔ device bridge | socket, expects **:8088** | **broken** — nothing binds it |
| CCOS → device bridge | in-process mock | **fabricates results** (§12.3) |
| Codey-OS → estimator | direct import of vendored copy | working for `calc`; 10 modules unreachable |
| Codey-OS → NPU | — | **none** (§10.4) |

So: **one link works, one works unsafely, three are broken, one is actively
misleading, one does not exist.**

### 3.3 The boundary that is misplaced

`restoricon_core/` — the live production business system, holding most of the
destructive surface and all the RBAC — lives **inside** the Codey-OS repo, while
directive §4 puts production on an independent release lifecycle, and §5 requires
development to fail *around* Restoricon.

Today a single commit to Codey-OS can change both the research system and the
production business system, and they share a release. That is the structural
reason §9's firewall has to be enforced by convention (`RESTORICON_DB_PATH`)
rather than by boundary.

### 3.5 DECIDED — `restoricon_core/` splits into its own repo (Ish, 2026-10-06)

The census recommended keeping it in place with the boundary enforced at the
env-var seam. **Ish decided to split it now**, matching directive §4's reasoning
literally: production gets a genuinely independent release lifecycle, and the
system holding all the RBAC and most of the destructive surface stops sharing a
commit history with the research system.

**This is the decision of record and the roadmap implements it** (WP5.1). The
honest trade-offs, kept visible rather than buried:

| Cost | Mitigation |
|---|---|
| High churn — ~29 `.py` files plus the API surface | `git mv`/`git filter-repo` to preserve history; one bounded batch |
| A new cross-repo contract to maintain | §3.4's hardening applies — one endpoint source of truth, versioned API |
| Competes for time with P0's security fixes | **Sequenced after P0** — see below |

**Sequencing constraint (the one thing that must not be got wrong):**
`restoricon_core/notification_service.py` is the file holding one of the two
unauthenticated email paths (`NEW-765`). Splitting the repo while that fix is
pending would mean landing a live security fix across a repo move. **So: P0's
security fixes land first, in one repo; the split happens after.** WP5.1 is
positioned accordingly.

**Second constraint:** the split must not happen before the §16 Action Gateway
(P2), because the gateway is what makes the production boundary explicit *in code*
— it turns the split from a file move into a real architectural boundary. Doing
the move first would just relocate the three-disjoint-surfaces problem into two
repos.

**Interim control until the split lands:** §9.3's `RESTORICON_DB_PATH` seam,
unchanged.

### 3.4 Contract hardening required

1. **One endpoint source of truth** — host/port injected, not hardcoded in three
   clients at three different values (§12.7).
2. **Authenticate every inbound surface** — `/send-email` (§13.4), the device
   bridge's fail-open auth (§16.5).
3. **No fabricating mocks across a repo boundary.** An unconnected limb returns a
   hard error (§12.3).
4. **Backends declare where work ran**, not merely that it succeeded (§10.3).
5. **Vendoring drift check** for `codey_estimator/` (§14.6).

## 4. Branch / tag / current-work reconciliation

### 4.1 Codey-OS

| Ref | State |
|---|---|
| `main` | `405d9cf` (2026-10-06) — active line |
| `codey-os-dev-v2` | `97ad62d` — **diverged**: main +4, dev-v2 +2 |
| `rollback/2026-09-30-pre-agi-audit-fixes` | rollback tag |
| `rollback/2026-09-30-pre-agi-merge` | rollback tag |
| `rollback/2026-09-30-pre-dev-v2` | rollback tag |

**Stranded work on `codey-os-dev-v2` (not on main):**
- `8d1c37e` Stage 0 kickoff: commit handoff + approved execution plan (docs only)
- `97ad62d` S0.1: full-fidelity trajectories, export hygiene, bench `grade()` fix

`97ad62d` is substantive S0 measurement work — trajectory fidelity plus a
benchmark `grade()` correction. Directive §13's S0 ("Measurement, trajectory
fidelity, benchmark/gates") depends on exactly this. **Decision required:**
cherry-pick, re-implement, or supersede. See §17 for the recommendation once the
`bench/` diff is in.

### 4.2 Private-Codey-Agent vs private-agent — RESOLVED

**`Private-Codey-Agent` is canonical. `private-agent` is a pure ancestor with
zero unique content.** Retirement of `private-agent` is *proposed*, not executed.

Evidence: shared root commits (`7f02f8d`, `cf0b8b8`, `5564cba`); commit counts
66 vs 63; fork direction private-agent → Private-Codey-Agent via its `upstream`
remote; `git log main..upstream/main` **empty**; `comm -13` on tracked-file sets
**empty** — strict superset, no divergence, no merge needed.

The 3 unique commits are precisely the Codey integration ("hands") layer:

| Commit | Content |
|---|---|
| `d24df11` | loopback `DeviceBridgeClientService` + `ThirdPartyAppAutomationService` |
| `907e5a3` | business dashboard screen + `RestoriconApiClient` (Phase B4) |
| `efe9a1c` | wire Business Dashboard into AppBar/drawer navigation |

Integration surface = 4 files: `lib/services/device_bridge_client_service.dart`,
`lib/services/third_party_app_automation_service.dart`,
`lib/services/restoricon_api_client.dart`,
`lib/screens/business_dashboard_screen.dart`. Last touched 2026-08-30 — ~5 weeks
behind Codey-OS main, so the consumed API contract needs re-verification (§12).

### 4.3 Other repos

| Repo | Branches / tags | Note |
|---|---|---|
| Codey-Aigentik | `main` only; tags v1.0.0–v1.1.0; has `upstream/main` | fork of Aigentik-CLI per §3 |
| Codey-Estimator-reference | **no `main`** — `origin/HEAD` → `claude/epic-archimedes-z3luuu` | dir name also differs from directive's `Codey-Estimator` |
| OpenCL-S24-Ultra | `main`, tag `v0.1.0` | most recently active repo after Codey-OS (2026-10-05) |
| restoricon | `main`, no tags | static marketing site (54 `.jpg`, 16 `.html`) — **not** the business data system |

### 4.4 Lineage repos named in directive §3 but absent locally

`Codey`, `Codey-v2`, `Aigentik-CLI`. Recorded as absent; not reconstructed.
`Codey-Aigentik`'s `upstream` remote makes its ancestry recoverable if needed.

## 5. Feature & capability census

Status assigned by **reachability from a real entry point**, not by code
completeness. Detail and `file:line` citations in §2, §10, §12–§20.

### 5.1 Codey-OS core

| Subsystem | Status | Note |
|---|---|---|
| Coding agent main loop (`core/agent.py`) | IMPLEMENTED | the primary working capability |
| Daemon + PID/socket lifecycle | IMPLEMENTED | no readiness gating (§2.6) |
| Core API (`restoricon_core/`, :8770) | IMPLEMENTED | RBAC + audit; most of the destructive surface |
| Model loading (`loader_v2.py`) | IMPLEMENTED | but **two owners** (§2.2) |
| Resource gate + context budget | IMPLEMENTED | KV cost model possibly ~4× wrong (§2.3) |
| Per-port lock / slot reservation | IMPLEMENTED | NEW-259 fix present |
| `telemetry/` (top-level) | IMPLEMENTED | 9 production callers |
| Production planner (`core/planner_v2.py`) | IMPLEMENTED | canonical; `ccos/core/planner.py` is not |
| Tool system (`tools/`) | IMPLEMENTED | but unsandboxed (§16.2) |
| `bench/` harness + gate | PARTIAL | gate is sound; **leakage** (§17.1), ledger empty |
| Memory tier 1 (working) | PARTIAL | silent 50% cliff (`agent.py:1641`) |
| Memory tier 2 (project) | PARTIAL | **write-only; stores an md5 hash** |
| RAG / `kb_semantic` | PARTIAL | wired end-to-end, **no corpus** (§15.2) |
| Trajectory store | PARTIAL | **truncates** at record (`_MAX_RESULT=1000`) |
| Thermal management | PARTIAL | daemon-only; no cooldown trigger |
| `resource_bus` generic half | DORMANT | zero callers |
| Memory tier 3 (embeddings) | DORMANT | dead parallel retrieval stack |
| Memory tiers 4/5 (symbolic) | DORMANT | `CODEY_SYMBOLIC=0` |
| Memory tier 6 (`_summary`) | DORMANT | undocumented; superseded |
| `core/recovery.py` | DORMANT | 521 lines, zero core callers |
| `checkpoint.rollback/list/prune` | DORMANT | created, never read or pruned |
| `core/voice.py` | DORMANT | documented broken; reachability unverified |
| Promotion-gate **rollback** | **MISSING** | rule 1 is 3-of-4 (§17.2) |
| Model/adapter registry | **MISSING** | §17.2 |
| AGI scorecard rubric | **MISSING** | 18/100 unreproducible (§17.3) |
| CI | **MISSING** | no `workflows/` dir; 2,854 tests never run (§20.1) |
| Knowledge-corpus ingestion | **MISSING** | no programmatic path (§15.2) |
| Action Gateway | **MISSING** | §16.1 |
| Worlds / staging isolation | **MISSING** | §16.9 |
| Backend abstraction (BrainManager) | **MISSING** | §10.4 |

### 5.2 CCOS layer

**The headline:** CCOS has **no runtime** (§2.1) and the live surface is **5 of ~25
modules**. ~6,500–8,000 lines are dormant. The documented "OS shell that
discovers, routes, monitors, and eventually self-improves" is, in live-path terms,
a library imported by two processes.

| Module | Status |
|---|---|
| `plugin_manager`, `capability_registry`, `manifest_schema_v2`, `task_context`, `task_blackboard` | IMPLEMENTED (the live 5) |
| `sandbox` | DORMANT — **never runs**; shell tool doesn't use it |
| `tool_router` (+ `validate_tool_safety`) | DORMANT — **the safety veto has never run** |
| `agent_orchestrator` (+ `execute_plan`) | DORMANT — unreachable |
| `planner`, `domain_router`, `lifecycle_manager`, `device_manager`, `ccos_memory` | DORMANT |
| `telemetry_engine` (728 ln) | DORMANT — zero callers at all |
| `reflection_engine`, `performance_tracker` | DORMANT |
| `goal_engine`, `auto_improvement_loop`, `capability_optimizer`, `skill_recombiner` | DORMANT **by design** (§15.4) |

Capability registry: **161 capabilities, all `active`, only 8 ever used**; 3 leaked
test fixtures; 4 orphan `speech.*` rows whose module **exists nowhere**. Manifest
`permissions`/`resource_limits`/`restart_policy`/`inputs_schema` are validated and
**never enforced**.

### 5.3 Companion repos

| Capability | Status |
|---|---|
| Codey-Aigentik pipeline | IMPLEMENTED — in production, 309 comms rows |
| Aigentik↔Core integration (54 sites) | IMPLEMENTED — all correct; 1 latent landmine (§13.3) |
| Aigentik `/send-email` route | **IMPLEMENTED BUT UNSAFE** — no auth, no DNC, no gating |
| Aigentik CI | MISSING |
| Private-Codey-Agent app core | IMPLEMENTED — **but does not compile at HEAD** (§12.1) |
| Private-Codey-Agent ↔ Codey-OS | **MISSING** — 3 incompatible ports, none real |
| Device-bridge capability | **ACTIVELY MISLEADING** — mock fabricates successes (§12.3) |
| Private-Codey-Agent auth | MISSING |
| Estimator `calc` path | IMPLEMENTED — reachable, 7 of 21 modules |
| Estimator `catalog` + `retailers` | DORMANT — 10 modules, zero callers |
| Pricing worker | **MISSING** — job shell exists, worker never written (§14.2) |
| NPU path (research) | PARTIAL — capability validated; **deployed models ineligible** (§10.1) |
| NPU consumable by Codey-OS | MISSING — `llama-server` an unbuilt target (§10.5) |
| OpenCL GPU | RESEARCH-ONLY — negative in every matched comparison |

### 5.4 The pattern

Three failure shapes recur, and they are what older plans missed:

1. **Complete code with no caller** — the sandbox, the safety veto, memory tier 3,
   `recovery.py`, two shell validators, `telemetry_engine`, 10 estimator modules.
   Reads as finished; moves nothing.
2. **Plumbing without content** — RAG with no corpus, a ledger with no entries, a
   pricing job with no worker, a registry with 161 unenforced entries.
3. **Confident falsehood** — a mock returning `"sent": True`, a "Project Memory"
   block sourced from elsewhere, a green test over dead code, OpenCL reporting
   29/29 offload while running on CPU. **This shape is the most dangerous**,
   because it would poison the experience store the developmental architecture is
   built on.

## 6. Dead / duplicate / legacy code cleanup inventory

Per directive §9: evidence before deletion, and a stated replacement before
removal. **Nothing below has been deleted** — this is the proposal.

### 6.1 Duplicate implementations needing one canonical path

| Duplicate | Canonical | Action |
|---|---|---|
| `core/` vs `ccos/` cognition stacks | **`core/`** (§15.3) | retire or wire the ccos stack; decide per module |
| Two planners: `core/planner_v2.py` vs `ccos/core/planner.py` | **`core/planner_v2.py`** (`daemon.py:889`) | delete the dormant one |
| Two telemetry systems: `telemetry/` vs `ccos/core/telemetry_engine.py` | **`telemetry/`** (§20.4) | delete 728 dormant lines; fix CLAUDE.md |
| Two retrieval stacks: `core/embeddings` vs `tools/kb_semantic.py` | **`kb_semantic`** (§15.1) | delete the dead embedding store |
| Two shell validators, both dormant | neither | §16.3 — make one live or delete both |
| **11 copies** of `coreRequest()` in Aigentik | one shared module | §13.5 |
| `codey_estimator/` vendored vs reference repo | vendored copy + drift check | §14.1 — **not** a conflict |
| `private-agent` vs `Private-Codey-Agent` | **`Private-Codey-Agent`** | §4.2 — retire the ancestor |

### 6.2 Dead / dormant code (with replacement stated)

- `ccos/core/telemetry_engine.py` (728 ln) → replaced by `telemetry/`
- `ccos/core/planner.py` → replaced by `core/planner_v2.py`
- `core/embeddings` store path + `store_in_longterm` + `Memory.search()` → replaced by `tools/kb_semantic.py`
- `Memory._summary` (tier 6) → replaced by `core/summarizer.py`
- `core/recovery.py` (521 ln) → **no replacement**; decide keep-and-wire vs delete
- `resource_bus` generic half (`request_resource`/`release_lease`/`poll_queue`) → no replacement; delete
- `checkpoint.rollback/list/prune` → **do not delete**; §17.2 needs rollback — wire these instead
- `tools/shell_tools.py:38-83,162` `_validate_command` + 54-entry allowlist → §16.3 decision
- Estimator `catalog/*` + `retailers/*` (10 modules) → **do not delete**; §14.6 needs them — write the worker
- `getCustomers()` / `getArAging()` (Private-Codey-Agent) → dead client code; delete
- `ccos/plugins/device/private_agent/manifest.json` (port 8766, nonexistent `agent.py`) + stale `.pid` → fiction; delete or implement
- 4 orphan `speech.*` registry rows (`tts_speech` **exists nowhere**) + 3 leaked test fixtures → purge
- `config.json` `gui`/8888 block → leftover from the GUI deleted in `65c9f10`; that round's own review called for sweeping the `8888` constants and `config.json` was the site missed
- Aigentik `a_port` (`service_manager.sh:285,436,496`) → dead twice over (parsed, unused; and Aigentik isn't a server)
- `utils/config.py:101` `"n_gpu_layers": 0` → dead config; subsume into §10's adapter

### 6.3 Working-tree and data noise

- **254 leaked 32-hex dirs, 7.9 MB — root cause identified.** Each holds exactly
  `resource_bus.db` (28,672 B) + `resource_bus.lock`, i.e. what
  `core/resource_bus.py:112-121` creates under a caller-supplied `state_dir`:
  `_get_db_path()`/`_get_lock_path()` call `base.mkdir(parents=True,
  exist_ok=True)` on `Path(state_dir)`. **Something called it 254 times with a
  `uuid4().hex` directory resolved against `cwd`** (the repo root) instead of a
  tmpdir. mtimes span 2026-09-03 → 2026-10-06, so it is still accumulating. The
  unit tests are *not* the culprit — `tests/test_resource_gate.py:651+` correctly
  passes pytest's `tmp_path`; the remaining caller is unidentified and is the one
  thing to find before fixing.
  *Fix:* make `state_dir` resolution reject bare relative paths (or anchor to
  `CODEY_STATE_DIR`), locate and fix the caller, then **remove the `.gitignore:46`
  mask** — a literal 32-char `[0-9a-f]` glob added to hide the symptom rather than
  fix the leak — so the problem cannot silently return. Same test-isolation class
  as the recombiner/optimizer/sandbox bugs fixed in `dd49c1d`, which this instance
  escaped.
- `cap_metrics` (454 rows) + `reflections.jsonl` (235 KB) — **no reachable writer**; purge or quarantine **before** any gate exists (§15.4)
- `.claude/agent-memory/` — 337 files, 87% of all `.md`; retention policy (§8.4)
- 5 orphaned declared dependencies (§20.3)

### 6.4 Misleading names, comments, and docstrings (rule 6 corrections)

- `core/memory_v2.py:5-22` — asserts five working tiers as present-tense fact
- `core/resource_gate.py:1076` — claims nothing calls `reserve_slot()`; `loader_v2.py:1450` does
- `core/trajectory.py:108` — "the only eligible fine-tune/eval data" **is the §17.1 leak**
- `ThermalManager.reset()` docstring — names a cooldown period absent from all nine `THERMAL_CONFIG` keys
- `Codey-Estimator-reference` — directory name differs from the directive's `Codey-Estimator`
- **15 live source comments cite the archived `docs/archive/TODO.md`**, and one cites the archived `CODEY_OS_MASTER_VISION.md` — anyone following those pointers lands in an archive they're told never to plan from
- `docs/importantdoc.md` — the name conveys nothing

### 6.5 Sequencing (directive §9)

Bounded batches, tests and rollback commits, behavioural changes separated from
file moves, `git mv` to preserve history. **Order matters:**

1. **Safety and correctness first** — §13.8/§16.9 security fixes, §17.5 leakage,
   §12.1 compile break, §12.3 fabricating mock. Never behind cleanup.
2. **Then cheap high-value hygiene** — CI (§20.6), the resource_bus leak, the
   `python-multipart` rule-11 fix, the rule-6 comment corrections (§6.4).
3. **Then duplicate consolidation** (§6.1), one pair per batch.
4. **Then dead-code deletion** (§6.2), each with its replacement argument stated.
5. **Directory restructuring last** (§7) — the highest-churn, lowest-urgency work.

**Do not delete anything in §6.2 before checking dynamic imports, plugin
manifests, shell entry points, and external callers** (directive §9). The
`capabilities.json` registry and `ccos/plugins/*/manifest.json` files reference
modules by string name — a Python-only grep will miss them, which is exactly how
the 4 orphan `speech.*` rows survived.

## 7. Proposed target directory tree and staged refactor

### 7.1 Assessment: the tree is mostly honest; the map is not

Directive §10 asks whether the structure still represents the architecture.
Largely **yes** — `core/`, `tools/`, `prompts/`, `pipeline/`, `bench/`,
`telemetry/`, `restoricon_core/` are coherently named and own what they claim.

**The real problem is not placement — it is `ccos/`.** It is laid out as a peer
subsystem to `core/`, which implies a live OS shell. In reality it is 5 live
modules and ~20 dormant ones (§5.2). The tree advertises an architecture that the
imports do not support.

**So: no large migration is proposed.** A big move now would churn 500+ Python
files while the §6.1 duplication questions are still open, and directive §9
explicitly warns against mixing large behavioural changes with massive file moves.
Restructuring is the **last** cleanup phase (§6.5), not the first.

### 7.2 Minimal, justified changes

1. **Split `ccos/` by liveness** — the honest, low-churn change:
   ```
   ccos/
     core/        ← the live 5: plugin_manager, capability_registry,
                    manifest_schema_v2, task_context, task_blackboard
     dormant/     ← explicitly marked, with a README stating status and
                    the §6.2 decision pending for each
   ```
   Makes §5.2's finding structural instead of tribal, and stops new code importing
   dormant modules by accident.
2. **`restoricon_core/` stays put** (§3.3), with the firewall at the env-var seam.
3. **Regenerate CLAUDE.md's map from `git ls-files`** and add a test that fails
   when a tracked top-level dir is missing from it (§8.4). **This is worth more
   than any file move** — the map being wrong is what made four subsystems
   invisible.
4. **Do not adopt the directive's illustrative tree** (`cognition/ agents/
   memory/ learning/ policy/ evaluation/ inference/ …`). The directive says not
   to adopt it blindly, and the census gives no evidence that this layout solves a
   real problem here. Revisit only if §10's BrainManager and §16's gateway grow
   large enough to warrant `inference/` and `policy/` of their own — a genuine
   possibility, but after they exist, not before.

### 7.3 Staging

Only after §6.5 steps 1–4. Each move: `git mv` to preserve history, imports and
manifests updated in the same commit, tests green before and after, one bounded
batch per commit, rollback tag before the batch.

## 8. Documentation archive & index plan

### 8.1 The 389 `.md` files are not 389 documents

| Location | Count | Nature |
|---|---|---|
| `.claude/agent-memory/code-reviewer/` | 280 | agent scratch notes |
| `.claude/agent-memory/project-architect/` | 49 | agent scratch notes |
| `.claude/agent-memory/prompt-engineer/` | 5 | agent scratch notes |
| `.claude/agent-memory/code-hygiene-auditor/` | 3 | agent scratch notes |
| `.claude/agents/` | 7 | subagent definitions (live config) |
| `docs/` | 16 | project documentation |
| `docs/archive/` | 8 | already-archived (superseded 2026-08-21) |
| top-level | ~18 | project documentation + ledgers |
| in-tree (`bench/`, `ccos/plugins/...`) | 2 | local READMEs |

**So the real documentation surface is ~52 files, not 389** — and **337 files
(87%) are agent memory**, which is tooling state, not project history.

`.claude/agent-memory/code-reviewer/` at 280 files is itself a finding: one file
per review round, unbounded, never consolidated. It is not harmful, but it makes
`git ls-files '*.md' | wc -l` a meaningless metric and buries the real docs.

### 8.2 Staleness, measured by last commit touching the file

**Current (2026-09-30 → 2026-10-06) — authoritative:**
`NEW_ISSUES.md` (20,138 lines), `PROJECT_LOG.md` (18,871),
`CODEY_MASTER_PLAN.md` (9,850), `LIVE_TEST_QUEUE.md` (210), `CLAUDE.md` (302),
`AGI_AUDIT_PLAN.md` (77), `AGI_AUDIT_LOG.md` (78).

**Recent (2026-09) — probably current, spot-check needed:**
`codey_estimator_schema.md` (527 — **known drifted**, see §14.3),
`codey_estimator_service.md` (984), `sales_rep_portal.md` (727),
`docs/realtime_push_design.md` (473), `docs/telemetry_layer_design.md` (1,310),
`README.md` (225), `docs/commands.md` (164), `docs/security.md` (214),
`AGENTS.md` (54), `ANTIGRAVITY.md` (31).

**Stale (2026-07-29/30, ~10 weeks) — suspect by default:**
`CHANGELOG.md` (1,028), `docs/tools-embedding-pipeline.md` (1,288),
`Codey-OS-audit.md` (673), `docs/importantdoc.md` (377),
`docs/pipeline.md` (287), `MODEL_COMPARISON.md` (277),
**`docs/architecture.md` (243)**, `docs/fine-tuning-kaggle.md` (209),
`docs/installation.md` (168), `docs/knowledge-base.md` (144),
`docs/troubleshooting.md` (115), `docs/fine-tuning.md` (100),
`PRIVACY.md` (87), `docs/configuration.md` (163).
**Oldest:** `docs/version-history.md` (145, 2026-06-13).

### 8.3 The most consequential drift

**`docs/architecture.md` — last touched 2026-07-29.** It is the architecture
document, and it is ~10 weeks old across a period in which the architecture
changed substantially. Given §16.2's finding that ~8,000 lines of CCOS are
dormant and only 2 of ~25 modules are imported by production, this document
almost certainly describes the *aspirational* OS shell as though it were live.
Treat as **DOCS-ONLY until re-verified line by line.**

**`CLAUDE.md`'s repo map omits four tracked subsystems** — `bench/` (44 files),
`restoricon_core/` (29), `codey_estimator/` (21), `telemetry/` (11): **93 tracked
`.py` files, ~19% of the repo's 502.** Independently flagged by census A3, which
noted `restoricon_core/` holds most of the destructive surface and all the RBAC —
the single most important directory to not be missing from the map.

This is worse than ordinary drift because CLAUDE.md is the first file every new
agent context reads, and the map is explicitly the project's defence against the
repeat-finding problem (`NEW-26`/`NEW-27`). An agent trusting it would not know
`restoricon_core/` exists.

**`codey_estimator_schema.md`** — two confirmed mismatches (§14.3).

### 8.4 Plan

**Index.** One `docs/INDEX.md` naming, for each live document, its scope and its
authority tier:

| Tier | Documents |
|---|---|
| Authoritative plan | `CODEY_OS_MASTER_BLUEPRINT.md` (this file, on approval) |
| Authoritative ledgers | `NEW_ISSUES.md`, `PROJECT_LOG.md`, `LIVE_TEST_QUEUE.md` |
| Authoritative rules | `CLAUDE.md`, `AGENTS.md`, `ANTIGRAVITY.md` |
| Reference (implementation) | `docs/*` — each marked verified or suspect |
| Historical | `docs/archive/*` |

**Archive — APPROVED by Ish 2026-10-06 (execute in P5).** Move to `docs/archive/` with a
`> **SUPERSEDED** — historical evidence only, do not execute` banner:
`Codey-OS-audit.md` (superseded by this blueprint's census),
`docs/importantdoc.md` (name conveys nothing; content to be triaged),
`MODEL_COMPARISON.md` (predates the current single-model decision),
`docs/version-history.md`, and `docs/fine-tuning*.md` if S4 supersedes them.
**Keep `CHANGELOG.md`** — stale but legitimately historical by nature.

**`CODEY_MASTER_PLAN.md`.** Do **not** archive on approval of this blueprint. It
holds §2's numbered rules and a large current-state record that CLAUDE.md
references directly. Proposal: keep it as the rules-and-history document, move the
*outstanding-work register* (§6 / Appendix A) into §21 here, and have each file
point at the other for its half. One register, two documents, no competing plans.

**Repairs, not archiving:**
1. Regenerate `CLAUDE.md`'s repo map from `git ls-files` — and add a test that
   fails when a tracked top-level dir is missing from it, so this cannot recur.
2. Re-verify `docs/architecture.md` against §2's verified runtime flow, or mark it
   superseded by §2 outright.
3. Fix `codey_estimator_schema.md`'s two mismatches (§14.3).
4. Mark `docs/telemetry_layer_design.md` and `docs/realtime_push_design.md`
   design-intent vs as-built once A1/A4 report.

**Agent memory.** Out of project-doc scope, but propose a retention policy
(consolidate per-round reviewer notes into one rolling file, cap the directory)
so `.claude/agent-memory/` stops dominating the file count. Not urgent; no
behavioural effect.

## 9. Restoricon production dependency & firewall map

### 9.1 What "Restoricon production" actually is

Not the `restoricon/` repo (that is a static marketing site). The production
system is:

| Component | Location |
|---|---|
| Business data store | `~/.codeyOS/restoricon.db` — 4,018,176 b, mtime 2026-09-30 17:50, live `-wal` (1,058,872 b) + `-shm` |
| Serving code | `restoricon_core/` (29 `.py`) inside Codey-OS |
| API | Core API on **127.0.0.1:8770** (loopback only) |
| Path seam | `RESTORICON_DB_PATH` env var — `restoricon_core/database.py:18` |

Path resolution sites: `restoricon_core/database.py:18`, `utils/config.py:717`,
`utils/config.py:689` (documents host/port/db defaults), `config.json:8`,
`lib/service_manager.sh:238,244`.

Four dated production backups exist in `~/.codeyOS/` (pre-b9.1,
pre-b816phase5, pre-bounce-loop-fix, pre_d2_role_migration), confirming an
established backup-before-migration convention.

### 9.2 Verified production contents (read-only, on a copy)

Method: copied `.db` + `-wal` + `-shm` to scratchpad, inspected **only the copy**;
original mtimes confirmed unchanged. No process was writing. (No `sqlite3` CLI on
device — used Python's `sqlite3`.)

**70 tables; 31 populated, 39 empty.** The empty set is the finding.

Populated — the real production surface:

| Rows | Table |
|---|---|
| 783 | `audit_log` |
| 309 | `communication_history` |
| 249 | `contacts` |
| 96 | `api_tokens` |
| 23 | `customers` |
| 9 | `tasks` |
| 6 | `users` |
| 5 | `leads` |
| 4 | `appointment_types`, `contract_signers`, `do_not_contact` |
| 2 | `automation_rules`, `contracts`, `documents`, `opportunities`, `production_handoff_checklists`, `projects` |
| 1 | `appointments`, `assessment_records`, `business_profile`, `commission_ledger_entries`, `commission_plan_config`, `invoices`, `properties`, `schedule_config`, `subcontractors`, `work_orders` |

Empty (39), clustered meaningfully:

- **All 6 estimator tables** — `estimates`, `estimate_line_items`,
  `estimate_versions`, `estimate_decisions`, `estimate_number_sequences`,
  `estimate_share_links`. Corroborated independently by
  `Codey-Estimator-reference` HEAD `df0730f` (2026-09-27): "estimates table is
  empty, no migration needed". ⇒ estimator is **schema-only, never exercised in
  production**.
- **All 12+ pricing/retailer tables** — `canonical_materials`, `labor_rates`,
  `labor_rate_history`, `price_book_items`, `price_observations`, `pricing_jobs`,
  `material_matches`, `retailers`, `retailer_products`, `retailer_stores`,
  `package_options`, `search_cache`, `product_search_fts*`. ⇒ the B9.x pricing
  work is **code/schema-complete with zero production data**; it has not been
  validated against real use.
- Remaining: `employees`, `equipment`, `equipment_deployments`, `timesheets`,
  `staff_schedules`, `staff_schedules_archive`, `territories`, `vendors`,
  `purchase_orders`, `project_milestones`, `compliance_items`,
  `customer_credits`, `financial_transactions`, `financing_records`,
  `homecare_subscriptions`, `marketing_campaigns`, `review_requests`.

`_litestream_seq` has 1 row, `_litestream_lock` is empty ⇒ Litestream
replication is configured (`core/setup_litestream.py`) but was **not running** at
census start.

### 9.3 The firewall consequence

The protected surface is **much narrower than the schema suggests**. Real
production dependency concentrates in four clusters:

1. **CRM/comms** — `contacts`, `communication_history`, `customers`, `leads`, `opportunities`, `do_not_contact`
2. **Auth** — `users`, `api_tokens`
3. **Audit** — `audit_log`
4. **Thin job layer** — `projects`, `work_orders`, `invoices`, `contracts`, `appointments`

Those get full §5 protection. The ~39 empty tables are build-out ahead of use:
safe to refactor, and — importantly — **not evidence of working features**. Any
plan line claiming the estimator or pricing subsystems are "done" is claiming
code completion, not production validation (CLAUDE.md rule 7).

**Firewall design:** `RESTORICON_DB_PATH` (`restoricon_core/database.py:18`) is
the clean seam. All development and all Playground/world work points at a copy
via that variable; the live path is never the default in any dev or test
configuration. Detailed controls in §16 once the destructive-action inventory
lands.

### 9.4 Open item requiring Ish — the Core API is not a persistent service

Verified, and more specific than "it's down":

| Check | Result |
|---|---|
| Listening ports at census start | **none** (`ss -tlnp`) — Core API on 8770 not bound |
| Processes | only `python battery-watch.py` (PID 31924) |
| **On-demand / lazy start path** | **none exists.** `start_restoricon()` is defined at `lib/service_manager.sh:226` and called from exactly one place — `start_all_services` at `:894`. Nothing auto-starts it on an API call. |
| Last production write | `~/.codeyOS/restoricon.db` mtime **2026-09-30 17:50 — 6 days before this census** |
| Activity today | a model *was* loaded at 08:34 (`llama-server.log` 08:35, `resource_gate_state.json` 08:34) — i.e. interactive use, not Restoricon serving |

**Conclusion:** the Core API requires an explicit `codey-start`; it is not a
persistent or on-demand service, and no production write has occurred in 6 days.

So "Restoricon must remain operational" (directive §5) currently describes a
**manually-started service over a 6-day-stale datastore**, not a running
production system. This materially changes what the firewall must protect:
continuous-availability protection is not the live constraint — **data integrity
is**. The 249 contacts / 309 communications / 783 audit records are the asset;
uptime is not presently a property the system has.

**ANSWERED — Ish, 2026-10-06:** *"its manuelly started but still not fully in use
as we develope this."*

So Restoricon is **manually started and not yet in full operational use** while
development proceeds. This is now a settled premise, not an open question.

#### What this changes — availability is not the binding constraint

Directive §5's prohibitions ("do not stop, restart, disable, reconfigure live
Restoricon processes") were written against a worst case — a continuously-serving
production system. That worst case does not hold. The binding constraint is
**data integrity**, and the asset is the data itself:

| Protected | Why |
|---|---|
| **The data** — 249 contacts, 309 communications, 23 customers, 5 leads, 6 users, 96 api_tokens, 783 audit records | real business records; irreplaceable; the actual asset |
| **The audit trail** | 783 rows; compliance value; append-only semantics must hold |
| **`do_not_contact`** (4 rows) | real compliance obligation to real people |
| **Service uptime** | **not** a property the system currently has or needs |

#### What this unblocks

Several roadmap constraints relax, and the blueprint is adjusted accordingly:

1. **Services may be stopped and restarted during development.** This was the
   single heaviest constraint on §19's work (readiness gating, PID lifecycle,
   single model-load owner) and on §10's BrainManager work, all of which touch
   process lifecycle. Rule 4's code-reviewer requirement still applies — that is
   about *bug risk*, not availability — but there is no longer a
   "production is serving, don't touch it" blocker.
2. **No zero-downtime migration machinery is needed.** Schema changes can take the
   service down. The existing backup-before-migration convention (4 dated backups
   in `~/.codeyOS/`) is the right and sufficient control.
3. **Restart coordination replaces restart prohibition.** Because Ish starts it
   manually, a process could be running at any time. The operative rule becomes:
   **check before acting** (`ps`/`ss` for a live Core API and a resident model)
   rather than never acting. This is also rule 2's existing discipline.

#### What does NOT relax

- **Never write to the live store from development work.** `RESTORICON_DB_PATH`
  points at a copy in every dev/test/Playground configuration (§9.3). Unchanged.
- **Never use live data as developmental Playground data** (directive §5).
  Unchanged — and now easier to honour, since nothing depends on the live copy
  being warm.
- **Back up before any schema change**, per the established convention.
- **Production secrets stay out of prompts, logs, and training data.** Unchanged.
- **The §13.4 / §16.4 email paths remain the highest-severity finding** — "not
  fully in use" does **not** make an unauthenticated send-to-real-people route
  safe. `contacts` holds 249 real people and `communication_history` shows 309
  real messages already sent. This is the one place where the relaxed premise
  changes nothing at all.

#### Residual risk worth naming

"Not fully in use" is a *current* state, and the roadmap runs for months. The
firewall should be built for the system becoming live during the programme, not
only for today — i.e. design the `RESTORICON_DB_PATH` seam and the §16 gateway
now, while it is cheap, rather than retrofitting them under production pressure
later.

### 9.5 New finding — stale `llama-server` PID file

`~/.codeyOS/llama-server-8080.pid` contains PID **10370**, written 2026-10-06
08:34. `kill -0 10370` fails — **the process is dead and the PID file was left
behind.**

This is adjacent to the self-race class CLAUDE.md rule 4 was written for (a daemon
reading a stale/preemptive PID as evidence a duplicate is running). The resource
gate does reap dead PIDs (`list_slots(..., reap_dead=True)`), so this is likely
handled on the slot path — but the bare PID file is not self-cleaning, and
`codeydOS` cleans only port 8080's. Logged rather than assumed benign; needs a
`NEW-###` and a check of every reader of that file.

## 10. NPU-first inference integration (CPU fallback, benchmark gates)

Directive §6 makes this the first major technical priority. The census supports
that ordering — but **reframes what the first step is**, because the directive's
own precondition ("benchmark exact deployed Codey models before changing
production defaults") turns out not to be satisfiable on the current path.

### 10.1 The blocking finding: both deployed models are ineligible for both NPU handoff prototypes

Both GGUF headers read in full (CLAUDE.md rule 12), not inferred from names:

| Model | Architecture | Disqualifier |
|---|---|---|
| Primary default | **`qwen35`** — hybrid SSM+attention (`ssm.*` keys, `full_attention_interval=4`, `key/value_length=256`, tagged `image-text-to-text`); `llm_arch_is_hybrid()==true` (`llama-arch.cpp:1091-1114`) | not in either allowlist |
| Embed model | **`nomic-bert`**, `attention.causal=False` — **no KV cache at all** | not in either allowlist |

Patch allowlists, both opened directly:
- Patch #5: `QWEN2 || QWEN3`
- Patch #7: `QWEN2 || QWEN3 || (LLAMA && !is_swa_any())`

**Neither deployed model qualifies.** The prefill→decode handoff works by
migrating a KV cache between backends; `qwen35` is hybrid (most blocks hold no KV
cache, and SSM state would also need migrating), and `nomic-bert` has no KV cache
whatsoever.

So directive §6's "benchmark the exact deployed models first" is **not satisfiable
on this path** without new SSM-state-migration work. That is a research task, not
an integration task (§22).

*Methodological note worth preserving:* the census initially identified the embed
server as the obvious first NPU candidate and **retracted it** after reading the
header — `nomic-bert`'s non-causal attention rules it out. Exactly the rule-12
trap, caught by reading the artifact.

### 10.2 Evidence grading — three tiers, deliberately not merged

**Tier 1 — validated and reproducible (one result only):**
Mistral-7B NPU-hybrid, **n=3 rotated order with standard deviations**:
**29.17 s vs CPU 116.13 s — 74.9% faster.**

This number must **always** travel with its four qualifiers:
- **prefill-only win** — NPU *decode* (3.79 / 5.85 tok/s) is **slower** than CPU (6.26)
- **first-response-only** — the handoff is one-way; a second call **throws**
- **warm-only**
- **and the model is Mistral-7B, which Codey-OS does not deploy** (§10.1)

**Tier 2 — capability validated, performance explicitly not:**
NPU clean-room validation is reproducible for *capability* (8/8 DSP gates, 29/29
offload). The repo itself labels its 95.22 / 29.22 tok/s figures *"not matched
performance benchmark results."* Honest labelling by the research repo — the
blueprint preserves that honesty rather than promoting the numbers.

**Tier 3 — not supported:**
All OpenCL performance is **n=1 with non-matched start temperatures**, and
**negative in every matched comparison.** OpenCL stays research-only (directive §6
already says experimental); it is not a fallback tier.

### 10.3 Hard ceilings that constrain the design

| Ceiling | Value | Consequence |
|---|---|---|
| NPU sessions | **1 only** (`0x200` AEE_ERPC; cause unidentified) | Codey-OS runs **three** servers (primary, embed, Aigentik's). NPU cannot serve them all. |
| Context | **2,560** max NPU-benchmarked vs **65,536** production | **25.6× gap**, entirely unmeasured |
| OpenCL correctness | silently runs attention on **CPU** despite reporting 29/29 offload | **the exact failure mode that would make a BrainManager record a false capability** |

That last one is the most important design input in this section: a backend that
reports success while silently falling back is worse than one that fails. The
adapter contract must verify *where work actually ran*, not trust a backend's
self-report.

### 10.4 Codey-OS side: zero backend abstraction

`utils/config.py:101` `"n_gpu_layers": 0` is the **only** accelerator token in the
codebase, and it is **dead config**. There is no adapter boundary of any kind.
Plus the §2.4 divergence: two spawn sites, two different flag sets.

### 10.5 Three decisions the blueprint must surface (not discoveries — choices)

**1. Pin llama.cpp back, or forward-port 8 patches.**
Both patch sets pin upstream `e358d591`; accelerator builds ship
`libllama.so.0.5.0`. But `b5b805a` rebuilt `~/llama.cpp` to 0.6.0-dev /
`4f540676` **yesterday**, and `utils/config.py:40-49` now prefers it.
`install.sh:219-220` clones `--depth 1` **unpinned** (NEW-757) — structurally
incompatible with a commit-pinned patch set. **This decision gates the
`install.sh` rule-11 change**, so it is flagged rather than guessed at.

**2. Which model.** Given §10.1, the options are: (a) deploy a Qwen2/Qwen3 model
to match the existing patch allowlists, (b) do the SSM-state-migration research to
support `qwen35`, or (c) defer NPU until a model decision is made on other grounds.
**This is Ish's call** — it trades the current single-model architecture against
NPU eligibility.

**3. `llama-server` is an unbuilt target, not missing software.**
`tools/server/` exists in both patched trees; `scripts/build.sh:58` and
`build-npu.sh:66` both set `-DLLAMA_BUILD_SERVER=OFF`, building only
`llama-completion llama-bench test-backend-ops`. A materially smaller prerequisite
than it first appears — but MISSING today and never attempted.

### 10.6 Plan — revised ordering

The directive's intent (backend-independent boundary first, NPU as a *selectable*
backend, CPU preserved) is correct and achievable. What changes is that **the
abstraction comes before the accelerator**, because the accelerator is blocked on a
model decision that the abstraction does not depend on.

**Phase N0 — cheapest decisive step, static, no model load.**
Check `ggml-hexagon`'s `supports_op` for `qwen35` SSM ops and `nomic-bert`
non-causal attention. **This gates every remaining question** and costs nothing.
Do this first.

**Phase N1 — BrainManager boundary (no accelerator yet).**
Define the adapter contract and move the llama-server-specific assumptions behind
it (the Tier A–E relocation sweep in the census report is the worklist). The
contract must abstract: process model, lifecycle, memory accounting, context
handling, tokenizer, streaming, and failure modes — and must **verify where work
actually ran** (§10.3). CPU llama-server becomes the first adapter and the
baseline. **Unify the two divergent spawn sites** (§2.4) here.

*This phase is independently valuable:* it fixes §2.2's dual-ownership risk and
§2.4's flag divergence regardless of whether NPU ever lands.

**Phase N2 — resolve §10.5's three decisions with Ish.** N1 does not block on them.

**Phase N3 — fix the KV cost model first.** §2.3 flags that
`core/resource_gate.py` may overestimate KV memory by **~4×** by assuming 32
uniform attention layers when `full_attention_interval=4` means only ~8 carry a KV
cache. Every scheduling decision in §19 and every NPU admission check depends on
this being right. Audit the 4,911 lines.

**Phase N4 — NPU as a selectable adapter**, gated on N2's model decision, with:
CPU preserved as default until a matched benchmark on a *deployed* model beats it;
per-model/per-context/per-workload compatibility **recorded, not assumed**
(directive §6); the single-session ceiling expressed as a hard constraint in the
resource gate; and phase-aware prefill→decode only where validated.

**Phase N5 — OpenCL stays research-only.** Not a fallback tier. Re-evaluate only
if a matched comparison ever turns positive.

**Benchmark gate:** no production default changes without a matched, n≥3,
temperature-controlled comparison on an **actually deployed** model, recorded in
the §17 ledger. Tier 1's single Mistral-7B result does **not** meet this bar for
production purposes — it is encouraging evidence about the hardware, not about
Codey's workload.

### 10.7 Cross-repo ledger item (CLAUDE.md rule 8)

The OpenCL repo's 2026-10-05 preservation audit asserts `~/llama.cpp` HEAD
unchanged. **`b5b805a` invalidated that premise the next day.** Unlogged
cross-repo finding — needs a `NEW-###`.

## 11. Agent-pipeline execution strategy

### 11.1 The pipeline exists and was used for this census

Per directive §7, no competing orchestration layer was invented. CLAUDE.md's
hub-and-spoke pipeline (`project-architect` → `implementer` → `code-reviewer` →
`live-verifier` → coordinator ledger update) and the 7 agents in `.claude/agents/`
are the development pipeline.

This census ran 8 parallel read-only agents under the coordinator, each required
to cite `file:line` and to decide status by reachability. **That worked** — the
three highest-value findings (§17.1 leakage, §12.1 compile break, §12.3 fabricating
mock) each came from a different agent and would not have surfaced from a single
sequential pass.

**What I'd change:** I over-provisioned, running 5 of 8 on Opus. The census tasks
were mechanical grep-and-cite work; Sonnet handled the three it was given at equal
quality. Future census-type fan-out should default to Sonnet, reserving Opus for
synthesis and for genuinely ambiguous analysis.

### 11.2 How the pipeline executes this roadmap

| Work type | Route |
|---|---|
| Any process-lifecycle change (§19.3 readiness gating, §2.2 model-load ownership) | **`code-reviewer` approval mandatory** — CLAUDE.md rule 4 |
| Security fixes (§13.4, §16.4, §16.5) | architect → implementer → **code-reviewer** → live-verifier |
| §17 gate/rollback/leakage | architect → implementer → **code-reviewer** → live-verifier; the leakage test is the acceptance criterion |
| NPU work (§10) | architect → implementer → code-reviewer → **live-verifier** (only agent that runs model loads, rule 2) |
| Cleanup batches (§6) | `code-hygiene-auditor` proposes → implementer → code-reviewer |
| Doc work (§8) | project-architect, with the §8.4 index as the deliverable |

### 11.3 Changes the census justifies

1. **A reachability check belongs in the pipeline, not just in censuses.** The
   recurring failure is complete code with no caller (§5.4). `code-reviewer` should
   be asked, for any new module, "what reaches this from an entry point?" — the
   single cheapest defence against repeating this entire class.
2. **`live-verifier` is load-bearing and under-used.** CLAUDE.md already records
   that two code-reviewer passes approved a change whose real bugs only surfaced on
   attempted live verification (NEW-259). §12.1's compile break and §15.2's missing
   corpus are both "would have been caught by trying to run it" findings.
3. **No new agent types needed** (rule 10). The 7 existing ones cover this roadmap;
   `code-hygiene-auditor` in particular is well-matched to §6 and was not used this
   round only because I kept Wave C in-session to limit cost.
4. **Autonomy boundary (directive §15):** the pipeline may advance through
   engineering gates without a human stop per phase. It may **not** self-authorize
   anything in §16.9's human-gated set — autonomy ceilings, Restoricon production
   access, destructive production actions, new real-person communication
   permissions. §13.4's unauthenticated `/send-email` is precisely the kind of
   capability that must never be reachable by an agent acting on its own authority.

## 12. Private-Codey-Agent completion & integration

The directive expected staleness drift here. The reality is worse: **the
integration is non-functional on both ends**, and the app does not compile at HEAD.

### 12.1 HEAD does not compile — verified independently

`lib/screens/business_dashboard_screen.dart:6,9-13` declares:

```dart
final RestoriconApiClient apiClient;
const BusinessDashboardScreen({ super.key, required this.apiClient, this.thirdPartyService });
```

Both navigation call sites construct it with **zero arguments**:
```
lib/screens/home_screen.dart:637:   MaterialPageRoute(builder: (_) => const BusinessDashboardScreen()),
lib/screens/home_screen.dart:1054:  MaterialPageRoute(builder: (_) => const BusinessDashboardScreen()),
```

A missing `required` argument is a hard Dart compile error. **The most recent
commit in the repo — `efe9a1c`, whose entire purpose was "wire Business Dashboard
into AppBar and drawer navigation" — does not compile as committed.**

`.github/workflows/android-release.yml:61,67` runs `flutter build apk --release`
on push. So either CI has been red since 2026-08-30, or it has not run. **Action:
check the CI logs** — this was verified statically, not by building (no Flutter
toolchain run, per census constraints).

### 12.2 Three mutually incompatible port guesses for one link — none of them real

| Client | Port it expects | Reality |
|---|---|---|
| `restoricon_api_client.dart:14` | `127.0.0.1:8765` | Core API is on **8770** (`utils/config.py:689,707,712`) — hardcoded mismatch, **no override path in the app** |
| `device_bridge_client_service.dart:25` | `8088` | **Nothing in Codey-OS ever binds 8088.** `DeviceBridgeServer.start()` — the only method that opens a real socket — is called in exactly one test file, with an ephemeral port, never in production |
| `ccos/plugins/device/private_agent/manifest.json` | `8766` | References a `python3 agent.py` start command **that does not exist anywhere in the repo**; not registered in any capability listing; has a stale leftover `.pid` file beside it |

Three integration points, three different ports, zero working connections. The
third is not dormant code — it is fiction with a `.pid` file next to it.

### 12.3 The capability CCOS exposes to its planner fabricates every result

`get_default_device_bridge_client()` wires to an **in-process mock server** whose
default handlers return hardcoded values — `"screen_width": 1080`,
`"sent": True` with no actual SMS send. It never touches a socket.

This is the most dangerous shape of all: the planner can call a device capability,
receive a confident success envelope, and record a trajectory in which an action
"succeeded" that never happened. Under directive §14 ("experience is not learning
until it measurably changes future behavior"), this would poison the experience
store with fabricated successes. **It must be fixed before any trajectory-driven
learning is switched on** — this is an S0 blocker, not an S1 integration task.

**Salvageable:** the wire protocol / envelope schema is well-designed and matches
on both sides. The contract is sound; only the transport and the honesty of the
mock are broken.

### 12.4 Safety-veto asymmetry

Codey-OS's `validate_telephony_safety` runs **only on the mock-dispatch path** —
the one that does nothing real. The Flutter app's own `handleRequestEnvelope`,
which is the side that would actually dial or text, has **no equivalent veto**.
Compounding §16.5's finding that the device bridge's auth **fails open** and its
telephony veto blocks only emergency numbers.

So: the guard is on the harmless path, absent from the harmful one.

### 12.5 Contract mismatches (lower severity)

- `/finance/summary` — client expects `gross_margin_percent`; server returns
  `net_margin_percent`. The dashboard renders only because of an incidental
  fallback to the executive-report endpoint.
- `/api/v1/projects` — **silently ignores** the client's `status` and `limit`
  filters.
- `getCustomers()` / `getArAging()` — dead client code, no callers.

### 12.6 Auth: absent

**No auth/login flow exists anywhere in the app.** No hardcoded credential was
found (good), but there is also no token acquisition, storage, or presentation —
while the production store holds 96 `api_tokens` rows and `restoricon_core/`
enforces RBAC. The app could not authenticate even if the ports were right.

### 12.7 Plan — ordered

1. **Fix the compile break** (`home_screen.dart:637,1054`) and check CI history.
   Nothing else can be verified until the app builds.
2. **Replace the fabricating mock with explicit failure.** An unconnected device
   bridge must return a hard error, never a synthetic success. Highest priority
   item in this section — it is a data-integrity issue for the learning system
   (§12.3), not an app bug.
3. **Single source of truth for the endpoint.** Core API port/host comes from one
   place, injected, not hardcoded in three. Delete the fictional
   `private_agent/manifest.json` (port 8766, nonexistent `agent.py`) and its
   stale `.pid`, or implement it — state which.
4. **Decide the transport.** REST (8770) *or* the socket bridge, not both. The
   envelope schema survives either way.
5. **Implement auth** against the existing `api_tokens` + RBAC model.
6. **Move the telephony veto to the acting side** and fix the fail-open auth
   (§16.5) — before the bridge is ever connected to a real socket.
7. **Fix the contract mismatches** (§12.5); delete the dead client methods.
8. **Then** integration tests against a *copy* of the production DB (§9.3).

**Status:** app core IMPLEMENTED but **does not build**; Codey-OS integration
MISSING (no working transport, no auth); device-bridge capability **actively
misleading** (mock presented as real); envelope schema IMPLEMENTED and sound.

**Security boundary note:** directive §4 keeps this repo separate precisely
because device actuation deserves a boundary. That boundary currently consists of
a fail-open auth check and a veto on the wrong side of the call. Re-establishing
it is a precondition for connecting the limb at all, not a later hardening step.

## 13. Codey-Aigentik completion & integration

**The one limb that genuinely works.** Unlike Private-Codey-Agent (§12), this
integration is live, correct, and carrying real production traffic — 309
`communication_history` rows.

### 13.1 What it is

A single long-running Node process (`index.js`), fork of upstream `Aigentik-CLI`.
It starts `llama-server`, warms it, connects Gmail IMAP IDLE, and routes every
inbound email / Google-Voice text through rule engines, a role router, and
customer/subcontractor CRM flows. A second small HTTP server
(`http-server.js`, port **8081**, loopback) handles Core→Aigentik inbound calls.

Note this makes Aigentik the **second** `llama-server` owner — see §2.2, where its
`ensure_model_cli.py` bypass is the top operational risk.

### 13.2 Fork divergence

`upstream/main..main` is **empty** — upstream has nothing Codey lacks (caveat: not
re-fetched, so this is last-known state as of 2026-08-26). `main..upstream/main`
has **29 commits**, all Codey's own: the Phase B2 Core-API write-through cutover,
telemetry work, and the recent bug-fix chain ending at HEAD.

### 13.3 The Aigentik→Core audit — the requested deliverable

**All ~54 call sites across 12 files audited. All currently correct.** Both
previously-fixed bugs verified fixed in current source with call-site citations:
NEW-517's spread-leak in `subcontractor-recruiter.js`, and the
`sendCalendarInvite()` argument transposition from `8b61916`.

**One new Suspected finding — a latent landmine.** `contacts.js:76-89`'s
`mapJSToCore` has the **identical spread-based shape** that caused NEW-517:
`coreObj.external_id = jsObj.id` **without deleting `jsObj.id`**. Not
live-triggered today only because its sole call site happens to pass a fresh
object with no `id` key. One new caller passing an object that has an `id`
reopens NEW-517 exactly.

This vindicates the standing memory note to keep watching this class. Recommend
fixing the shape now rather than relying on caller discipline.

### 13.4 Highest-risk finding: an unauthenticated real-email endpoint

`http-server.js`'s **`/send-email` route has zero auth, zero do-not-contact check,
and zero rule-engine gating.** Any local caller reaching `127.0.0.1:8081` can send
a real outbound email to an arbitrary address, **bypassing every safety gate the
main pipeline applies**. The file also has **zero test coverage**.

Combined with §16.4 (`restoricon_core/notification_service.py` POSTs to
Aigentik→Gmail with no RBAC and no audit), there are **two independent
unauthenticated paths to sending real email to real people**, neither audited.
Directive §15 human-gates "new real-person communication permissions"; these are
existing, ungated, and unlogged.

Note the production DB has a populated `do_not_contact` table (4 rows) — a
compliance mechanism that this route bypasses entirely.

### 13.5 Hygiene: 11 duplicated `coreRequest()` helpers

The Core integration is plain HTTP/JSON to `127.0.0.1:8770` with a static bearer
token from `config.json` — via **11 independently duplicated copies of an
identical `coreRequest()` helper**, one per module. Any auth, retry, or timeout
change must be made correctly 11 times. Directive §9's "duplicate
implementations → one canonical path" applies directly.

### 13.6 Docs drift

- `docs/architecture.md`'s diagram still shows **local-JSON storage** — it
  predates the Core cutover entirely and omits `http-server.js`. Third
  independent confirmation of §8.3.
- `docs/security.md` **falsely claims** Gmail + llama-server are Aigentik's only
  network traffic. It omits both the Core API calls and the unauthenticated
  inbound server — i.e. the security doc omits the security problem.

### 13.7 Tests & CI

**No CI** (no `.github/`). Jest covers 15/21 modules; the two highest-risk files —
`http-server.js` and `owner-command.js` — are **untested**. All 4 runtime deps
used; no dead dependencies.

### 13.8 Plan — ordered by risk

1. **Authenticate `/send-email` and route it through the do-not-contact check and
   rule engine** — or delete the route. Highest-priority item in this section; it
   is a live ungated path to real people. Pair with §16.4's fix so both paths land
   behind one gate.
2. **Fix `contacts.js:76-89`'s latent NEW-517 shape** (§13.3).
3. **Consolidate the 11 `coreRequest()` copies** into one module.
4. **Tests for `http-server.js` and `owner-command.js`**; add CI (the repo has none).
5. **Correct `docs/architecture.md` and `docs/security.md`** (§13.6).
6. **Resolve the dual `llama-server` ownership** (§2.2) — this is Codey-OS-side
   work but Aigentik is the caller.

**Status:** core pipeline IMPLEMENTED and in production. Core integration
IMPLEMENTED and correct. `/send-email` route **IMPLEMENTED but unsafe**. CI
MISSING. Docs stale.

**Production-coupling note (directive §5):** Aigentik writes to the live store via
Core, touching `communication_history`, `contacts`, `do_not_contact`,
`automation_rules`. It is therefore inside the §9 firewall: any development
against Aigentik must point at a copied DB via `RESTORICON_DB_PATH`, and **must
not exercise the live email path at all.**

## 14. Codey-Estimator completion & integration

### 14.1 Correction to the duplicate-implementation hypothesis

The census framing (mine, and directive §12's) assumed two competing estimator
implementations. **That is wrong.** `Codey-OS/codey_estimator/` (21 `.py`) is a
**byte-for-byte verbatim vendored copy** of
`Codey-Estimator-reference/src/codey_estimator/` — confirmed by `diff` on every
file pair; the only difference is a provenance docstring in the package
`__init__.py`.

The reference repo is a **stdlib-only calculation/catalog/parsing library** with
no DB, API, or service code of its own (`pyproject.toml: dependencies = []`). It
was never a standalone application. So there is **no "which is canonical" merge
question** and no risk of "losing a standalone working implementation" — the thing
directive §4 was protecting against does not apply here.

The service/API/persistence layer exists **only** in Codey-OS:
`restoricon_core/services/estimate_service.py`, `pricing_repo.py`,
`pricing_job_service.py`, `routes.py` — built on top of the vendored library.

**Revised disposition:** keep the reference repo as the upstream vendoring source;
`codey_estimator/` stays a vendored copy. The real question is not integration
*topology* but how much of the vendored library is actually used.

### 14.2 Reachability — 10 of 21 vendored modules are DORMANT

Traced to a real entry point:
`codey-start` → `lib/service_manager.sh:start_restoricon()` →
`python3 -m restoricon_core.api.server` → `EstimateService` / `pricing_repo.py`.

That path imports **7 of 21** vendored modules: `calc/engine`, `dto`, `errors`,
`units`, `money`, `ports`, `refresh`.

**DORMANT (10 files, zero callers anywhere in `restoricon_core/`):**
- `catalog/*.py` — material matching and normalization
- `retailers/*.py` — retailer product parsing and CSV import

`pricing_job_service.py` is only 122 lines of job-lifecycle bookkeeping. **The
scraping/matching logic that would call `catalog.matcher` or
`retailers.csv_import` does not exist.** The job layer is a shell around a worker
that was never written.

This closes the loop on §9.2's empty-table finding with a mechanism:
`material_matches`, `retailer_products`, `price_observations` are schema-complete
and empty **because nothing writes to them** — not because the feature is idle.

### 14.3 Schema drift: two confirmed doc-vs-reality mismatches

Both from one root cause — `codey_estimator_schema.md` is a stale B9.1-era
snapshot never updated for the B9.x pricing round:

| Doc claim | Reality |
|---|---|
| `estimate_line_items`'s 4 pricing-id columns have "NO FOREIGN KEY, deferred to a later phase" | Live DB and `restoricon_core/database.py:414-432` have **all 4 FKs attached** |
| `estimates.property_id` is "bare INTEGER, NO FOREIGN KEY" | Live DB has the FK attached, via `_migrate_estimates_property_id_fk` (`database.py:3022`) |

The doc is *more pessimistic* than reality — drift in the safe direction, but it
would mislead anyone planning the "later phase" that already happened.

### 14.4 B9.x commit-before-raise bug — verified fixed

Re-verified by reading `restoricon_core/database.py:3060-3204` directly rather
than trusting the memory note. The pre-flight dangling-id check runs before any
DDL touches disk, and the terminal `PRAGMA foreign_key_check`
(`database.py:3185-3189`) is still inside the `with conn:` block — so raising
there rolls back instead of leaving a committed partial write. Matches the
code-reviewer's round-2 approval, independently confirmed from source.

### 14.5 Branch anomaly — resolved, not a finding

`Codey-Estimator-reference`'s missing `main` branch is a **shallow single-commit
clone artifact**, intentional per `NEW_ISSUES.md:18426` (cloned as a read-only
vendoring source). Not abandoned work. Confirming against the real remote would
need network access — out of census scope.

### 14.6 Remaining work and definition of done

1. **Write the pricing worker.** Build the service that actually calls
   `catalog.matcher` and `retailers.csv_import`. This is the missing piece, not a
   wiring change — ~10 dormant modules are waiting on a caller that was never
   written. Until it exists, the whole pricing/retailer subsystem is inert.
2. **Fix the two schema-doc mismatches** in `codey_estimator_schema.md` (§14.3).
3. **Confirm whether dedicated pricing/retailer API routes exist** — not checked
   this pass, logged as an open question.
4. **No data migration needed** — independently confirmed twice (empty tables;
   and the reference repo's own HEAD commit).
5. **Add a vendoring-drift check** so the verbatim copy cannot silently diverge
   from the reference repo.

**Definition of done:** a pricing job runs end-to-end from a real retailer input
to populated `material_matches` / `price_observations` / `retailer_products`
rows, with tests, behind the §16 gateway, against a **copy** of the production DB
— never the live store (§9.3).

**Status:** `calc` path IMPLEMENTED and reachable. `catalog` + `retailers`
DORMANT. Pricing worker MISSING. Schema doc PARTIAL (drifted).

## 15. Memory / learning / sleep / curiosity / teacher / self-improvement

Directive §8 asks specifically whether memory is *"actually read back into
behavior."* Answered below, and the answer is the foundation of the whole roadmap.

### 15.1 The five-tier memory: one tier reaches behavior

| Tier | Written? | **Read back into a prompt?** | Status |
|---|---|---|---|
| 1 Working | yes | **yes** — `prompts/layered_prompt.py:355` → `core/context.py:176` → `core/memory_v2.py:593` | PARTIAL (see gate below) |
| 2 Project | yes (`daemon.py:937,944`) | **no** — stores an **md5 hash, not content** | WRITE-ONLY |
| 3 Long-term embeddings | — | **no** — `store_in_longterm` and `Memory.search()` have **zero callers** | DORMANT |
| 4 / 5 Symbolic | only inside `_run_symbolic_pipeline` | gated off: `CODEY_SYMBOLIC=0` (`core/agent.py:1327`) | DORMANT |
| 6 `Memory._summary` (undocumented) | **zero production writers** | no | DORMANT — superseded by `core/summarizer.py` |

**Tier 1's silent cliff:** auto-loading is gated at `core/agent.py:1641` by
`if used < total * 0.5` — so working memory **silently stops loading** once the
prompt fills half of `n_ctx`. Memory quietly disappears exactly when context is
most contested, with no signal.

**Tier 2 is a false positive in disguise:** the prompt *does* render a "Project
Memory" block — but it comes from the unrelated `core/codeymd.py`, not from tier 2.
Anyone reading the prompt output would conclude tier 2 works.

**Tier 3 is a dead parallel retrieval stack.** `core/embeddings.get_embedding_store`
is called from exactly one place (`memory_v2.py:299`). The live RAG uses a
*separate* numpy index in `tools/kb_semantic.py`. Two retrieval systems; the
documented one is dead.

**Record correction (CLAUDE.md rule 6):** `core/memory_v2.py:5-22`'s docstring
asserts five working tiers **as present-tense fact**. It is wrong and should be
corrected in place — it is the primary source of this misconception.

### 15.2 RAG is wired end-to-end — and has no corpus

`$CODEY_DIR/knowledge` **does not exist**; `kb_semantic.has_index()` returns
**False** (both verified statically). So `retrieve()` returns `""` on **every
call**, and the `retrieval` and `skills` prompt layers are **permanently empty**.

There is no programmatic ingestion path either: `index_directory` /
`build_semantic_index` have **zero Python callers and no `__main__`**. The only
invoker is `tools/setup_skills.sh`, which has never been run. Likely
`install.sh` gap (CLAUDE.md rule 11).

This is the cleanest example of the pattern this census exists to find: the
plumbing is complete and correct, and it moves nothing, because the reservoir was
never filled.

### 15.3 `core/` is canonical; the `ccos/` cognition stack is unreached

Exhaustive import grep from the live tree: **9 hits across 2 modules**; transitive
closure adds three more. **The live CCOS surface is exactly five modules** —
`plugin_manager`, `capability_registry`, `manifest_schema_v2`, `task_context`,
`task_blackboard`.

Unreached (~6,500 LOC, callers only in `ccos/demo_*.py` and tests):
`ccos/core/planner.py`, `agent_orchestrator.py`, `goal_engine`,
`reflection_engine`, `telemetry_engine` (724 lines, **zero callers at all**),
`lifecycle_manager`, `tool_router`, `domain_router`, `ccos_memory`.

Corroborates §16.2 and §2.1 from a third independent direction. **Resolution for
the blueprint: `core/` is canonical for cognition.** `core/planner_v2.py` is the
production planner (`core/daemon.py:889`).

### 15.4 Self-improvement dormancy is designed, not accidental

`tests/test_promotion_gate.py:91` **asserts** that no `core/`/`tools/`/`utils/`
file imports the self-improvement modules. The dormancy is enforced by a test —
deliberate, and consistent with CLAUDE.md rule 1's gating intent.

**But `CODEY_SELF_IMPROVE=on` changes nothing today.** No production path imports
those modules at all, and **no production code ever constructs an approving
`GateDecision`.** The env switch is a kill switch for a machine that isn't
connected. Rule 1's "activation behind the promotion gate" has no gate bridge yet.

**Latent hazard:** `cap_metrics` holds **454 rows** and `reflections.jsonl` is
**235 KB with today's mtime** — and **no reachable writer**. If a gate bridge is
ever built, **stale or demo-generated metrics would silently drive real promotion
decisions.** This must be purged or quarantined *before* any gate is wired, not
after. Directive §12's "evaluation leakage risk" in concrete form.

### 15.5 Trajectory fidelity — main truncates

`core/trajectory.py:24-25` sets `_MAX_RESULT = 1000`. Main's trajectory store
**truncates at record time**, which bounds any fine-tuning or
experience-replay claim built on it. On-device: **5 episodes, 0 teacher_traces**.

Unmerged `codey-os-dev-v2` commit `97ad62d` fixes **exactly this** — full fidelity
at record, plus `core/export_hygiene.py` to truncate only at export. That is
precisely directive §14's principle ("canonical trajectories remain complete;
display/export truncation is separate").

**Recommendation: cherry-pick `97ad62d` as the first roadmap work package.** It is
already written, matches the stated principle, and every later developmental stage
depends on trajectory fidelity. Re-review it rather than trusting the branch.

### 15.6 Ledger items (CLAUDE.md rule 8)

- `core/resource_gate.py:1076` — stale comment claims nothing calls
  `reserve_slot()`; `core/loader_v2.py:1450` is the single real production call
  site (verified repo-wide).
- `core/memory_v2.py:5-22` — docstring asserts five working tiers as fact.
- `ccos_memory.py`'s declared schema is **absent from its own DB**, and **three
  modules share that DB path with disjoint schemas.**
- `cap_metrics` (454 rows) and `reflections.jsonl` (235 KB, today's mtime) have no
  reachable writer.

### 15.7 Plan — dependency-ordered

Nothing in S2–S5 can be built on the current base, because the substrate those
stages assume (memory read-back, a corpus, complete trajectories) is not there.
So the order is forced:

**Stage A — make experience real (S0).**
1. Cherry-pick/re-verify `97ad62d` — full-fidelity trajectories + export hygiene.
2. Purge or quarantine `cap_metrics` + `reflections.jsonl` before any gate exists.
3. Fix the §12.3 fabricating device mock — fake successes must never enter the
   trajectory store.
4. Correct `memory_v2.py:5-22`'s docstring and `resource_gate.py:1076` (rule 6).

**Stage B — make memory actually read back (S2 prerequisite).**
5. Decide tier 2: store content, or delete the tier. A hash is not memory.
6. Decide tier 3 vs `tools/kb_semantic.py` — **one** retrieval stack. Recommend
   keeping the live numpy index and deleting the dead embedding store, with the
   §9 equivalence argument stated.
7. Replace `agent.py:1641`'s silent 50% cliff with explicit, observable budgeting.
8. Build a real ingestion path for the knowledge corpus and add it to
   `install.sh`. Until a corpus exists, the `retrieval`/`skills` layers are
   decoration.

**Stage C — build the gate before the thing it gates.**
9. Implement the promotion gate for real: candidate vs baseline on a frozen
   benchmark, regression slice, append-only ledger, rollback — and production code
   that can actually construct an approving `GateDecision`. Per rule 1 this is the
   precondition for activation, and §17 owns the design.
10. Only then bridge the self-improvement modules, keeping
    `tests/test_promotion_gate.py:91`'s assertion as the guard until the gate is
    live and tested.

**Stage D — S3+ (curiosity, sleep/consolidation, teachers, LoRA/SFT).** Not
plannable in detail yet: every one of these consumes verified experience, and
Stages A–C are what make experience verified. Sketched in §21, with the research
uncertainties isolated in §22.

**The headline:** the system currently has no mechanism by which experience changes
future behavior. Directive §14's first principle — *"experience is not learning
until it measurably changes future behavior"* — is not yet satisfiable, and
Stages A and B exist to make it satisfiable before anything is built on top.

## 16. Action Gateway / worlds / autonomy / safety

### 16.1 Current state: there is no Action Gateway — MISSING

Real-world actions reach the world through **three disjoint surfaces with three
different safety regimes**:

| Surface | Entry | Safety regime |
|---|---|---|
| Coding agent tools | `core/agent.py:335-352` (`TOOLS` dict) | 18 substring patterns + y/n prompt; bypassable via `yolo=True` (`core/task_executor.py:393`) |
| CCOS capabilities | `ccos/core/plugin_manager.py:446` (`call_capability`) | **none — zero safety checks of any kind** |
| Restoricon services | `restoricon_core/` | properly RBAC'd and audited |

**The system's one safety validator has never run.** `validate_tool_safety`
(`ccos/core/tool_router.py:23`) has exactly one caller —
`ccos/core/agent_orchestrator.py:1094`, inside `execute_plan`, which is
**unreachable**. The safety veto is dead code.

### 16.2 ~8,000 lines of CCOS are DORMANT

`from ccos` across all production trees returns 9 lines touching only **2 of ~25**
ccos modules (`plugin_manager`, `task_blackboard`). Dormant: sandbox,
tool_router, agent_orchestrator, planner, lifecycle_manager, device_manager,
telemetry_engine, reflection_engine.

Consequences:
- **The sandbox never runs.** The agent's `shell` tool does not use it.
- **Two planners exist.** Production uses `core/planner_v2.py` (via
  `core/daemon.py:889`), not `ccos/core/planner.py`. See §5 for the canonical call.
- The OS-shell story in `CODEY_MASTER_PLAN.md` §3 describes a layer that is, in
  live-path terms, largely not wired. This is the single largest gap between
  documented and actual architecture.

### 16.3 Two dormant shell validators — and a green test suite over dead code

- `_validate_command` + its 54-entry `ALLOWED_COMMANDS`
  (`tools/shell_tools.py:38-83,162`) — **zero callers**.
- `validate_command_structure` (`tools/shell_tools.py:108`) — called **only** by
  `tests/security/test_shell_injection.py`. A passing security suite exercising a
  function production never calls. This is exactly the "a fix that passes every
  test can still be wrong" pattern in CLAUDE.md, one level up: the *test* passes
  and guards nothing.

Assessed honestly: **not a live injection hole** — the absence of `shell=True` is
what actually saves it, not the validators. And the unattended daemon is better
guarded than the interactive agent (`_DAEMON_ALLOWED_PREFIXES` is real and
correctly excludes git writes).

### 16.4 Unaudited external sends

`restoricon_core/notification_service.py:13,53-64` POSTs to Aigentik → Gmail with
**zero RBAC checks and zero audit records**. This is the clearest
externally-visible irreversible action in the system, and it is ungated and
unlogged. Directive §15 human-gates "new real-person communication permissions";
this path predates any such gate.

### 16.5 Two latent gateway defects — fix before wiring CCOS

Correct in shape, inert only because the surrounding layers are dead. They become
live the moment CCOS is connected, so they must be fixed *first*:
- `extended_api.py` — `allow_dangerous` is a defaulted kwarg, not a boundary.
- `device_bridge` — telephony veto blocks only emergency numbers, and its auth
  **fails open**.

### 16.6 Capability registry: inventory, not enforcement

161 capabilities, **all marked `active`**, only **8 ever used**
(`ccos/data/capabilities.json`, gitignored, write-mostly). Contains 3 leaked test
fixtures and 4 orphan `speech.*` rows whose `tts_speech` module **exists
nowhere**. Manifest `permissions`, `resource_limits`, `restart_policy` and
`inputs_schema` are schema-validated and **never enforced**.

Two `external_process` plugins (`private_agent`, `aigentik`) are registered but
**cannot start** — missing entry files, verified by listing.

### 16.7 Record correction (CLAUDE.md rule 6)

Project memory recorded "all 55 service audit sites canonical" (2026-09-03).
Actual current count: ~137 `.log(` sites / 154 `build_audit_details` uses. The
count has roughly tripled; the memory note was accurate when written and is now
stale. **Audit coverage gap closed at `notification_service` (WP0.2,
2026-10-07).** `pdf_service` was re-checked and found not to be a gap (rule-6
correction, see §21 item 4). **Gap remains at `pricing_repo`** (zero audit/actor
plumbing at all; logged, not fixed, in this P0 round -- it's a dormant subsystem,
`NEW-777`).

### 16.8 Further safety findings

- Sandbox `ALLOWED_DIRS` includes `ccos/` itself — a self-modification hole.
  Needs an explicit rule-1 decision from Ish before the sandbox is ever activated.
- `patch_file` has **no confirmation, no protected-name check, and no snapshot** —
  yet `prompts/system_prompt.py` steers the model to it for all edits.

### 16.9 Plan

Dependency order matters here: **do not wire CCOS before the gateway exists**,
because connecting it activates §16.5's defects and a sandbox that can write to
its own source.

1. **Build one Action Gateway** as the single chokepoint for every irreversible
   action — shell exec, file write/patch/delete, git writes, outbound HTTP,
   DB writes, message/email sends, device actions. All three surfaces in §16.1
   route through it. Capability manifests become *enforced* policy, not metadata.
2. **Fix §16.5's two latent defects and the fail-open auth** before any CCOS wiring.
3. **Make the dormant validators live or delete them** — state which, with the
   equivalence argument (directive §9). Retarget
   `tests/security/test_shell_injection.py` at the enforced path so the suite
   guards something real.
4. **Close the audit gaps** (`notification_service`, `pricing_repo`) and bring
   external sends under RBAC + audit. **Rule-6 correction (2026-10-07,
   WP0.2):** `pdf_service` is not actually a gap -- re-checked its one real
   call site (`crm_service.py`'s `sign_contract`) and found both outcomes
   already audited: success via the `create_document` call's own audit
   entry, failure via an existing `pdf_generation_failed` audit.log call
   (`crm_service.py:4553`, predates this round). Downgraded from the
   original census claim rather than left standing.
5. **Snapshot-before-patch** for `patch_file`, with protected-name checks.
6. **Worlds / Playground isolation** keyed on `RESTORICON_DB_PATH` (§9.3) so
   developmental work can never address the live store.
7. **Autonomy ceilings** stay human-authorized per directive §15; the gateway is
   where a ceiling is technically expressible at all, which is why it is S0 work
   and not deferred.

**Research-vs-engineering note:** items 1–6 are ordinary engineering. Deciding
*what* autonomy ceiling is safe per capability (§22) is not.

## 17. Benchmark / evaluation / promotion / rollback

### 17.1 CRITICAL: evaluation leakage is prescribed by the project's own documentation

**Verified independently by me, all three hops:**

| Hop | Evidence |
|---|---|
| 1 | `bench/runner.py:32-35` — on each bench task: `label_tag(f"bench:{t.id}", f"bench:{sh[:12]}", passed, ...)`. Bench episodes are written into the trajectory store, tagged `bench:*`. |
| 2 | `core/trajectory.py:108-114` — `verified_episodes()` runs `SELECT ... WHERE verifier IS NOT NULL` + `AND passed=1`, with **no tag predicate**. Bench episodes are selected indiscriminately. |
| 3 | `core/finetune_prep.py:127-130` — iterates `verified_episodes(path=path, only_passed=True)` and converts each into a training example. |

**The 8 frozen benchmark tasks become the training set. The gate then grades
candidates on those same 8 tasks.** Every promotion decision thereafter is
measuring memorization.

**This is not drift — it is the documented plan.** `AGI_AUDIT_LOG.md`'s Phase 3
entry instructs: *"enable `CODEY_TRAJECTORY=1`, run the bench, label episodes."*
**The prescribed next step is the thing that destroys the evaluator.**

The root cause is visible in one line: `core/trajectory.py:108`'s own docstring
calls `verified_episodes()` *"the only eligible fine-tune/eval data"* — conflating
the training source and the evaluation source in a single function. The leak is
architectural, not a slip.

Latent today (flags unset), **fires on the first prescribed run**. **Not fixed on
`codey-os-dev-v2`** either — its new `core/export_hygiene.py` contains zero hits
for `bench`/`tag`/`verifier`.

**This is the highest-priority fix in the entire blueprint.** Everything in
directive §13's S4–S6 (champion/challenger evaluation, verified datasets,
evidence-based autonomy) is meaningless if the evaluator is contaminated, and the
contamination would be invisible — scores would go *up*.

### 17.2 Rollback is MISSING — CLAUDE.md rule 1 is 3-of-4 in code

Rule 1 requires: candidate vs baseline on a frozen benchmark, a regression slice,
an append-only ledger, **and rollback**.

| Requirement | State |
|---|---|
| Promotion gate | ✓ `bench/gate.py:23-40` — genuinely conservative, fail-closed |
| Frozen suite | ✓ lock verified live |
| Append-only ledger | ✓ append-mode — **but empty; no bench result has ever been written** |
| **Rollback** | ✗ **MISSING** |

`ccos/core/capability_optimizer.py:397-422` backs up to `data/versions/` and writes
a `previous_version` field. **Nothing reads either.** An exhaustive grep for
`previous_version|def rollback|def revert|versions/` returns only that write plus
two unrelated functions (`core/checkpoint.py:184`, `core/lora_import.py:451`).

**No model/adapter registry exists.** Adapter adoption's gate requirement is
DOCS-ONLY — printed as advice at `core/finetune_prep.py:601,783-784`, while
`core/lora_import.py` **consults no gate at all** (zero hits).

So the one safety property that makes rule 1's "activation" acceptable — the
ability to undo a bad promotion — is the one that does not exist.

**What keeps this latent:** `compare_and_upgrade`'s unprotected live-overwrite is
unreachable because its only caller hardcodes `no_evaluator()`. The missing
rollback is harmless precisely because the gate is not yet connected — which is
exactly why rollback must be built *before* the connection, not after.

### 17.3 The AGI scorecard does not exist in the repo

18/100 is cited twice in prose, with **no rubric anywhere**. The baseline is
**unreproducible** and progress toward rule 1's stated ceiling is **unmeasurable**.
`AGI_AUDIT_LOG.md` is also stale (last entry 2026-09-30, despite 2026-10-01
AGI-track work).

Rule 1 says *"a score is not a goal in itself... never a number that was pushed up
by relabeling."* With no rubric in the repo, there is currently no way to tell a
real improvement from a relabeling. **The rubric must be written down and version-
controlled before the number is used to justify anything.**

### 17.4 The `bench/verify.py` latent bug and the real dev-v2 scope

Main's `bench/verify.py:17-18` has a `copy2`-over-`iterdir()` bug (fixed on
dev-v2). It **cannot fire today** because all 8 `hidden/` dirs hold exactly one
file — it will break **silently** on suite growth, swallowed by
`except Exception: return False` at `:23-24`. A benchmark that silently returns
"fail" as the suite grows is worse than one that crashes.

**Scoping correction to §4.1 (and to my earlier framing):** the dev-v2 bench diff
is only 3 lines in `verify.py`, but `97ad62d` is **not** the only unmerged commit —
`8d1c37e` precedes it, and together they carry **944 insertions across 11 files**
that main lacks, including `core/export_hygiene.py`, directly on the fine-tune
export path. The cherry-pick recommended in §15.5 is therefore a **two-commit,
11-file reconcile**, not a 3-line patch. It needs full code review, not a
fast-forward.

### 17.5 Plan — strictly ordered, and the order is load-bearing

**Nothing in this section may be connected before step 1 and step 3 are done.**

1. **Close the leakage.** Partition the trajectory store by provenance: bench
   episodes must be *structurally ineligible* as training data, not merely
   filtered by convention. Split `verified_episodes()` into distinct
   training-source and evaluation-source accessors so the conflation in its
   docstring becomes impossible to express. Then **correct `AGI_AUDIT_LOG.md`'s
   Phase 3 instruction**, which currently prescribes the leak.
2. **Add a leakage regression test** that fails if any `bench:`-tagged episode can
   reach `finetune_prep`. This is the test that protects every later stage.
3. **Build rollback for real** — and a model/adapter registry. Make
   `core/lora_import.py` consult the gate. Until an adopted adapter can be undone,
   no adapter should be adoptable.
4. **Write the scorecard rubric into the repo**, version-controlled, and recompute
   the baseline from it. Report the measured number, never the aspirational one.
5. **Reconcile dev-v2** (two commits, 11 files, 944 insertions) under full review.
6. **Fix `bench/verify.py`** and remove the `except Exception: return False`
   silent-failure swallow.
7. **Write the first real gate result to the ledger** — it is currently empty, so
   the append-only mechanism is untested in practice.
8. **Only then** bridge self-improvement (§15.7 Stage C).

### 17.6 Decisions needed from Ish

1. **The leakage fix changes the documented Phase 3 workflow.** `AGI_AUDIT_LOG.md`
   currently instructs the leaking procedure. Confirm it should be rewritten.
2. **The gate's 30-pair minimum costs ~13 hours of device time**
   (`PROJECT_LOG.md:25`). This is the **binding constraint on the entire AGI
   track** — not a code problem. It needs a scheduling decision (overnight runs?
   a smaller statistically-defensible minimum? NPU speedup first, per §10?)
   before the roadmap's cadence can be set realistically.

## 18. Brain abstraction and future brain-swap

Directive §2: *"The neural model is a replaceable brain, not Codey's identity."*

### 18.1 Current state: the brain is not separable

- **No backend abstraction** (§10.4) — `llama-server` specifics are spread through
  `loader_v2.py`, `daemon.py`, `resource_gate.py`, `embed_server.py`, and
  Aigentik's `ensure_model_cli.py`.
- **Two spawn sites with divergent flags** (§2.4).
- **Model-specific assumptions are baked into resource math** — §2.3's KV cost
  model assumes a layer topology that the deployed model does not have.
- **No model/adapter registry** (§17.2).

### 18.2 What must survive a swap — and currently would not

Model-independent development is supposed to persist across brain replacement.
Today:

| Asset | Survives a swap? |
|---|---|
| Trajectories | partially — **truncated** (§15.5) |
| Skill library | **does not exist** |
| Memory tiers 2–6 | no — write-only or dormant (§15.1) |
| Knowledge corpus | **does not exist** (§15.2) |
| Benchmark results ledger | empty (§17.2) |
| Capability registry | yes, but unenforced and partly stale (§16.6) |

**So a brain swap today would lose almost nothing — because almost nothing
model-independent has accumulated yet.** That is the honest statement, and it is
oddly good news: the architecture can be fixed before there is anything to lose.

### 18.3 Plan

1. **BrainManager boundary** (§10.6 N1) — the precondition. Model identity,
   spawn, lifecycle, context policy, tokenization, and streaming behind one
   contract; adapters for CPU llama-server (baseline), NPU, OpenCL.
2. **Model/adapter registry** with provenance and gate results (§17.5 step 3).
3. **Make the resource model topology-aware** rather than assuming uniform
   attention (§2.3) — otherwise every new brain re-breaks the admission math.
4. **Build the model-independent assets** (§15.7 Stages A–B) — full trajectories,
   a real corpus, memory that reads back. Until these exist, "brain swap preserves
   development" is untestable.
5. **Define the re-verification suite**: after a swap, re-run the frozen benchmark
   and the retention/transfer measures, and record both in the ledger. A swap is
   not complete until accumulated development is demonstrated to survive it.

**Research uncertainty (§22):** how much of "development" is genuinely
model-independent is an open empirical question, not an engineering task. The
architecture should make it *measurable* rather than assume an answer.

## 19. Resource / thermal / battery / inference scheduling

### 19.1 What is genuinely live

The resource gate is **real, not shelfware** — the strongest subsystem found:
- `rg.reserve_slot(spec, port=PRIMARY_SERVER_PORT, meminfo=...)` at
  `core/loader_v2.py:1450` — the NEW-259 `port=` fix is present and correct.
- Context budget live at **three** real call sites.
- Per-port lock at `core/loader_v2.py:564-600`.
- `~/.codeyOS/resource_bus.db` mtime 2026-10-06.

### 19.2 Live gaps

| Gap | Evidence | Consequence |
|---|---|---|
| **KV cost model may be ~4× wrong** | §2.3 — `full_attention_interval=4` means only ~8 of 32 blocks hold a KV cache; `core/resource_gate.py` (4,911 lines) not audited | Gate may refuse loads it could safely admit; corrupts every §10/§19 scheduling decision |
| **Dashboard users are invisible** | §2.5 — `is_interactive_session_active()` (`resource_gate.py:3961-3981`) scans TUI PID files only; sole writer `main.py:401-447`; nothing in `restoricon_core/` writes a marker | Dashboard-only work reads as "no human present", changing dispatch deferral, `n_ctx` choice, and admission at 3 sites |
| **Second model-load owner** | §2.2 — Aigentik's `ensure_model_cli.py` bypass, `stdio:'ignore'` | 2.7 GB load outside the daemon, failures silent. Rule 2 territory. |
| **Thermal accounting is daemon-only** | no interactive path brackets inference | interactive sessions accrue no thermal duration |
| **`ThermalManager.reset()` has no auto trigger** | the "cooldown period" its docstring names is **absent from all nine `THERMAL_CONFIG` keys** (verified by full dump, not by grepping for `cooldown`) | documented cooldown behaviour does not exist |
| **`resource_bus`'s generic half is DORMANT** | `request_resource` / `release_lease` / `poll_queue` — zero callers | ~half the module is unused |
| **No PID file for the embed server** | port 8082 orphans untracked; `codeydOS` cleans only 8080 | leaked servers hold RAM invisibly |
| **No readiness gating** | §2.6 — `nohup &` + `sleep 0.5` + `kill -0` | PID file written before bind can fail |

Plus §C2-F2: **254 leaked state dirs** from `core/resource_bus.py:112-121`, masked
by `.gitignore:46` rather than fixed.

### 19.3 Plan

1. **Audit the KV cost model against the real `qwen35` topology** (§10.6 Phase N3).
   Prerequisite for everything else here — a 4× error invalidates all admission math.
2. **Restore the interactivity signal for the dashboard**, with the
   freshness/liveness guard `resource_gate.py:3977-3980` already specifies. Aligns
   with the standing "dashboard = single control surface" direction.
3. **Single model-load owner.** Route Aigentik through the daemon socket (its
   release path already does) and stop ignoring stderr. Folds into §10.6 Phase N1 —
   the BrainManager boundary is where ownership becomes expressible.
4. **PID file + tracked lifecycle for the embed server**; extend `codeydOS` cleanup
   beyond 8080.
5. **Bracket thermal accounting on the interactive path**; implement the cooldown
   the docstring promises or delete the claim (rule 6).
6. **Fix the `resource_bus` state-dir leak** at source and remove the `.gitignore`
   mask, so the symptom can't silently return.
7. **Readiness gating**: wait for an actual port bind, not a fork. **Requires
   code-reviewer approval** — CLAUDE.md rule 4, process lifecycle.
8. **Delete or wire `resource_bus`'s dormant generic half**, with the §9
   equivalence argument.
9. **Battery**: `battery-watch.py` runs outside the repo entirely (PID 31924).
   Decide whether it becomes a tracked input to scheduling or stays external —
   currently it informs nothing.

**NPU interaction:** the single-NPU-session ceiling (§10.3) must become a hard
resource-gate constraint before any NPU adapter is admitted, or three servers will
contend for one session.

## 20. Testing / CI / observability / security / dependency cleanup

### 20.1 Zero CI — the headline

`.github/` contains **one file** (`REPOSITORY_DESCRIPTION.md`). There is **no
`workflows/` directory** — verified directly:
```
$ ls .github/workflows/
ls: cannot access '.github/workflows/': No such file or directory
```
No GitLab, Circle, Makefile, or pre-commit config either. **No pytest config at
all** — `pytest.ini`, `pyproject.toml`, and a root `conftest.py` are all absent.

**2,854 tests exist and nothing ever runs them automatically.**

CLAUDE.md's map claims `.github/ GitHub workflows + repo description` — **false**,
and a fifth independent instance of CLAUDE.md drift (§8.3).

Note the contrast: Private-Codey-Agent *has* CI
(`.github/workflows/android-release.yml`) and it is almost certainly red (§12.1).
Codey-OS has none at all.

### 20.2 Test-suite quality findings

- **A green suite over dead code**: `tests/security/test_shell_injection.py` is the
  only caller of `validate_command_structure` (§16.3). It passes and guards nothing.
- `tests/test_promotion_gate.py:91` is used *well* — it asserts the
  self-improvement dormancy invariant (§15.4). Good pattern; more invariants
  should be enforced this way (e.g. the §17.5 leakage test, the §8.4 repo-map test).
- Verbatim scoped run (A4 subset; full suite deliberately **not** run — 2,854
  tests, 768 Mi free, a 2.74 GB sparse-file test, and `restoricon.db` risk):
  ```
  ..................................                                       [100%]
  34 passed in 26.52s
  ```
- **Test-environment trap confirmed:** `HTTP_PROXY=http://127.0.0.1:41245` (+3
  variants) **was set**. The scoped run used `env -u` to clear all four. Without
  that, the suite produces a false ~34-failure result. This is in project memory and
  it bit again — it belongs in a `conftest.py` that clears proxy vars, not in
  tribal knowledge.

### 20.3 Dependency hygiene (CLAUDE.md rule 11)

- **Violation:** `python_multipart` imported **unguarded** at
  `restoricon_core/api/routes.py:2414`, installed on-device
  (`python-multipart==0.0.32`), **absent from both `requirements.txt` and
  `install.sh`.** A fresh clone running `install.sh` gets a broken Core API.
- 5 orphaned declared deps.
- `install.sh:219-220` clones llama.cpp `--depth 1` **unpinned** (NEW-757) —
  structurally incompatible with the commit-pinned NPU patch sets (§10.5).
- No `sqlite3` CLI installed despite a SQLite-centric system (§C2-F6).
- A near-miss worth recording: `rich` looked unused until its submodule-form
  imports were found at `core/display.py:8-9`. Import-form variation defeats naive
  dependency sweeps — any automated check must account for it.

### 20.4 Observability: two telemetry systems, and the map names the wrong one

| System | State |
|---|---|
| **`telemetry/` (top-level)** | **LIVE** — ~160 KB, 9 real production callers, 250 run files on disk, design doc accurate |
| `ccos/core/telemetry_engine.py` | **DORMANT** — 728 lines; only referents are itself, its demo, and its test |

**CLAUDE.md's map names the dormant one and omits the live one.** Sixth drift
instance. `docs/telemetry_layer_design.md` (1,310 lines) is accurate for the live
system — one of the few docs that holds up.

### 20.5 Security

Consolidated from §16, §13.4, and A1:
- **Two unauthenticated paths to real email** (§13.4, §16.4) — highest-severity
  security findings in the census.
- **Device bridge auth fails open** (§16.5).
- **The only safety validator never runs** (§16.1).
- `config.json:3` holds a **live Cloudflare tunnel token in plaintext**. It **is**
  gitignored (`.gitignore:30`) and `git ls-files` confirms untracked, and
  `show_service_config` redacts token-shaped keys when printing
  (`service_manager.sh:980-993`). **Recorded as plaintext-on-device, deliberately
  not escalated as a repo leak** — the handling is correct; the storage is a
  residual risk to decide on.
- Aigentik's Core bearer token is static, read from `config.json`, duplicated
  across 11 helpers (§13.5).

### 20.6 Plan

1. **Add CI.** Minimum: run the test suite on push, with proxy vars cleared. This
   is the cheapest high-value change in the entire blueprint — 2,854 tests already
   exist.
2. **Add `pytest.ini` + root `conftest.py`** that unsets `HTTP_PROXY`/`HTTPS_PROXY`
   (+variants), so §20.2's trap cannot recur.
3. **Fix the rule-11 violations**: add `python-multipart` to `requirements.txt` and
   `install.sh`; prune the 5 orphans; resolve the llama.cpp pin (§10.5 decision 1);
   add `sqlite3` if any workflow needs it.
4. **Retarget `test_shell_injection.py`** at the enforced path (§16.3).
5. **Add invariant tests** for: §17.5 leakage, §8.4 repo-map completeness,
   §15.4 self-improvement dormancy (already exists — keep).
6. **Delete `ccos/core/telemetry_engine.py`** or justify keeping 728 dormant lines;
   correct CLAUDE.md's map to name `telemetry/`.
7. **Security fixes in §13.8 / §16.9 order** — the two email paths first.
8. **Decide on the plaintext tunnel token** (move to a keystore, or accept and
   document).

## 21. Dependency-ordered master roadmap

**Ordering principle.** Three things come before everything else, because each
makes later work either safe or meaningful: live ungated paths to real people
(P0), a trustworthy evaluator (P0), and the ability to undo a promotion (P1).
Directive §13's developmental stages are preserved in intent, but S0 is larger
than the old plan assumed — the census found that the measurement substrate
(trajectory fidelity, a clean evaluator, rollback) does not yet exist.

Every phase ends with Codey runnable. No phase is an unmergeable rewrite.

---

### P0 — Stop the bleeding (no dependencies; start immediately)

Each item here is either a live path to irreversible real-world action, or a
mechanism that would silently corrupt the data the whole research programme rests
on.

**WP0.1 — Authenticate Aigentik's `/send-email`** — **DONE 2026-10-07.** Scope
widened beyond the named route: `/send-invite` and `/send-cancellation` had the
identical gap (confirmed by reading `http-server.js`), closed for all three. New
shared-secret bearer auth (`internal-auth.js`, `~/.codeyOS/aigentik_internal_token`,
install.sh-generated) + do-not-contact gate on all three routes. Two
code-reviewer rounds (round 1: CHANGES REQUESTED on a cache-poisoning bug, an
install.sh idempotency gap, and auth running after the body read; round 2:
APPROVED after all three fixed and re-verified independently). Rule-engine
gating (`email-rules.js`) deliberately not applied -- that module classifies
inbound mail, it isn't an outbound-send gate.
- *Objective:* no unauthenticated local caller can send real email.
- *Deps:* none. *Repo:* Codey-Aigentik — `http-server.js`.
- *Intent:* require the bearer token; route through the do-not-contact check and
  rule engine, or delete the route if nothing legitimate calls it.
- *Tests:* first tests for `http-server.js` (currently zero) — unauthenticated
  request rejected; DNC-listed address rejected.
- *Gate:* code-reviewer (security). *Rollback:* single-file revert.
- *Doc:* correct `docs/security.md`'s false network-traffic claim (§13.6).
- *DoD:* an unauthenticated POST cannot send mail; a DNC address cannot be mailed.

**WP0.2 — RBAC + audit on `notification_service`** — **DONE 2026-10-07.** RBAC
to *trigger* a send was already adequate at both real call sites
(`crm_service.py`'s PM-assignment email, `routes.py`'s compose route); the real
gap was the send itself having no audit trail. Added `audit.log` calls
(success/failure/exception) at both sites. code-reviewer APPROVED. `pdf_service`
re-checked and found not to be a gap (see §16.7/§21 item 4 corrections);
`pricing_repo`'s gap logged, not fixed (dormant subsystem, `NEW-777`).
- *Objective:* close the second unaudited path to real email (§16.4).
- *Deps:* none. *Repo:* Codey-OS — `restoricon_core/notification_service.py`.
- *Intent:* apply the existing RBAC check and audit envelope used by the other ~137
  sites. Also close the `pdf_service` / `pricing_repo` audit gaps.
- *Tests:* audit record written per send; unauthorized role rejected.
- *Gate:* code-reviewer (security). *Rollback:* revert.
- *DoD:* every outbound notification appears in `audit_log`.

**WP0.3 — Device bridge must fail loudly, not fabricate** — **DONE 2026-10-07**
(the live-danger part), after one review round caught a real regression.
`ccos/core/device_bridge.py` no longer registers fabricating mock handlers by
default (`NEW-767`); an action with no real handler now returns an explicit
"Device not connected" error. Added a real telephony safety veto to the Dart
acting side (`device_bridge_client_service.dart`), which previously had none
(§12.4's asymmetry). **Round-1 code-reviewer caught a Critical regression the
implementer's own test run never surfaced:** `ccos/plugins/device/bridge/test.py`
(not pytest-collected — plain `test.py`, not `test_*.py`, and it's the real
mechanism `ccos/core/sandbox.py`'s `run_plugin_test()` invokes for
`agent_orchestrator`'s `PLUGIN_TEST` step) still asserted the old fabricated-
success shape and crashed for real when the reviewer ran it directly. Fixed by
rewriting it to assert the fail-loud contract, *not* by registering fake
handlers on the real production singleton (which would have reintroduced
NEW-767 inside the orchestrator's own process) — confirmed by running
`python3 ccos/plugins/device/bridge/test.py` directly, both standalone and
immediately after the pytest file that mutates the same module-level
singleton (also given a `try/finally` teardown per the same review). Round 2:
APPROVED. The fail-open auth fix is deliberately **not** done here —
confirmed dormant (no production caller ever opens the real network socket),
and the blueprint's own §12.7 sequences that fix after a transport decision
this WP doesn't make (`NEW-794`). Dart changes are code-complete, not
build-verified — no flutter/dart on this device (`NEW-795`).
- *Objective:* an unconnected limb never reports success (§12.3). **Highest
  data-integrity priority in the blueprint.**
- *Deps:* none. *Repos:* Codey-OS (`device_bridge`, mock dispatch),
  Private-Codey-Agent (`handleRequestEnvelope`).
- *Intent:* replace mock default handlers with explicit `NotConnected` errors; fix
  the fail-open auth; move the telephony veto to the acting side.
- *Tests:* calling any device capability with no bridge returns an error, never a
  synthetic payload; emergency-number veto enforced on the acting path.
- *Gate:* code-reviewer (security + safety). *Rollback:* revert.
- *DoD:* no code path can return `"sent": True` without a real send.

**WP0.4 — Fix the Private-Codey-Agent compile break** — **DONE 2026-10-07**
(mechanically). Both `home_screen.dart` call sites now construct and pass
`RestoriconApiClient()`. CI history checked: every run in this repo's history
is `workflow_dispatch`, none `push`-triggered, despite the workflow declaring
a push trigger (`NEW-793`) — which is why this break went uncaught. Not
build-verified — no flutter/dart on this device (`NEW-795`).
- *Objective:* the app builds (§12.1).
- *Deps:* none. *Repo:* Private-Codey-Agent — `lib/screens/home_screen.dart:637,1054`.
- *Intent:* pass the required `apiClient`; check CI history for how long
  `android-release.yml` has been red.
- *Tests:* CI build green. *Gate:* code-reviewer (light).
- *Rollback:* revert. *DoD:* `flutter build apk --release` succeeds in CI.

**WP0.5 — Close the evaluation leak**
- *Objective:* benchmark episodes are **structurally ineligible** as training data
  (§17.1). Without this, every later measurement is meaningless.
- *Deps:* none. *Repo:* Codey-OS — `core/trajectory.py:108-114`,
  `core/finetune_prep.py:127-130`, `bench/runner.py:32-35`.
- *Intent:* split `verified_episodes()` into separate training-source and
  evaluation-source accessors; partition by provenance so the conflation in its
  docstring cannot be expressed. Correct `AGI_AUDIT_LOG.md`'s Phase 3 instruction,
  which currently prescribes the leak.
- *Tests:* **a regression test that fails if any `bench:`-tagged episode can reach
  `finetune_prep`.** This is the acceptance criterion.
- *Gate:* code-reviewer. *Rollback:* revert.
- *Doc:* `AGI_AUDIT_LOG.md` Phase 3 rewritten; `core/trajectory.py:108` docstring
  corrected (rule 6).
- *DoD:* the leakage test is green and in CI (after WP1.1).
- *Needs Ish:* confirms the documented Phase 3 workflow changes (§17.6).

**WP0.7 — Move the Cloudflare tunnel token out of plaintext** *(Ish's decision 7)*
- *Objective:* remove the last plaintext credential on device (§20.5).
- *Deps:* none. *Repo:* Codey-OS — `config.json:3`, reusing
  `core/backup_secrets.py`'s `~/.codeyOS/age.key` at-rest pattern.
- *Intent:* encrypt the token at rest via the mechanism the project already has;
  load/decrypt at service start. **No rotation** — Ish's call, and no exposure
  evidence (gitignored, `git ls-files`-confirmed untracked, and
  `lib/service_manager.sh:980-993` already redacts token-shaped keys on print).
- *Tests:* the service starts with the token encrypted; `config.json` contains no
  credential; printing stays redacted.
- *Gate:* code-reviewer (security). *Rollback:* keep the plaintext value in the
  escrow path until the encrypted load is confirmed working, then remove.
- *DoD:* no plaintext credential in any file on device.

**WP0.6 — Quarantine unsourced metrics**
- *Objective:* stale/demo data cannot drive future promotion decisions (§15.4).
- *Deps:* none. *Repo:* Codey-OS — `cap_metrics` (454 rows),
  `ccos/data/reflections.jsonl` (235 KB), both with no reachable writer.
- *Intent:* move aside with provenance recorded; do not delete until the §17 gate
  design confirms they're unwanted.
- *Tests:* gate code reads no row lacking provenance.
- *Rollback:* restore from the moved copy. *DoD:* no unsourced metric is readable
  by any gate path.

---

### P1 — Make measurement trustworthy (S0)

**WP1.1 — CI and test hygiene** *(cheapest high-value change in the blueprint)* — **DONE 2026-10-07.** `.github/workflows/tests.yml` + `pytest.ini` (`norecursedirs = bench/tasks`, the 8 collection errors it was causing are gone) + root `conftest.py` (proxy-var clearing, NEW-756). code-reviewer APPROVED. Local baseline (can't fully verify here — see `NEW-791`): 1456 passed/1 skipped across everything except `tests/test_restoricon_core`, which OOM-crashes this specific device at ~81% through the full run; not caused by this change, logged as `NEW-791`, first real CI run should be watched for the same shape.
- *Objective:* 2,854 existing tests actually run (§20.1).
- *Deps:* none. *Repo:* Codey-OS — new `.github/workflows/`, `pytest.ini`, root
  `conftest.py`.
- *Intent:* run the suite on push; `conftest.py` unsets `HTTP_PROXY`/`HTTPS_PROXY`
  (+variants) so §20.2's false-failure trap cannot recur.
- *Tests:* CI green on a clean checkout. *Gate:* code-reviewer (light).
- *Rollback:* delete the workflow. *Doc:* correct CLAUDE.md's false
  ".github/ workflows" claim.
- *DoD:* a PR with a failing test is visibly red.

**WP1.2 — Reconcile `codey-os-dev-v2`**
- *Objective:* recover the stranded S0 work (§17.4).
- *Deps:* WP1.1 (so the merge is tested). *Repo:* Codey-OS.
- *Scope correction:* **two commits, 11 files, 944 insertions** — including
  `core/export_hygiene.py` on the fine-tune export path. Not a 3-line patch.
- *Intent:* full review, then cherry-pick or re-implement. Trajectories full
  fidelity at record; truncation only at export (directive §14).
- *Tests:* a long trajectory round-trips uncut; export truncates.
- *Gate:* code-reviewer (full — it touches the learning data path).
- *Rollback:* rollback tag before the merge.
- *DoD:* `_MAX_RESULT` no longer truncates at record time; dev-v2 is merged or
  formally superseded and the branch deleted.

**WP1.3a — Derive the gate's required sample size** *(Ish's decision 3; do before WP1.3)* — **DONE 2026-10-07.** `bench/power_analysis.py` + `.md`. No reviewer gate per this work package's own spec. **Honest result, not the hoped-for direction:** under every scenario tried, 30 pairs is under-powered, not conservative — the table ranges 57-182 required pairs depending on assumed discordance/effect size (no empirical estimate exists, `NEW-762`'s empty ledger). Working default pending a pilot: n=100 (~22-24h device time at this session's measured ~780-820s/task-rep), which is *more* device time than the old 30-pair/13h figure, not less — reported as derived, not shaded toward the old number.
- *Objective:* replace the 30-pair/~13 h figure with a statistically derived `n`.
- *Deps:* none — this is arithmetic, **zero device time**.
- *Intent:* power analysis for the effect size the gate needs to detect. The 30-pair
  number was a cost estimate, never a derived requirement; nobody computed what `n`
  the gate actually needs. Then batch whatever `n` it implies into overnight runs.
- *Tests:* the derivation is recorded and reproducible (same inputs → same `n`).
- *DoD:* a documented required `n` with its assumptions stated, and the resulting
  wall-clock cost. **If the answer is 30, that is a valid outcome** — the point is
  to know rather than assume. Feeds `bench/scorecard.md` (WP1.4).

**WP1.3 — Rollback and a model/adapter registry**
- *Objective:* satisfy the missing fourth element of CLAUDE.md rule 1 (§17.2).
- *Deps:* WP1.1. *Repo:* Codey-OS — `bench/gate.py`, `core/lora_import.py`,
  `core/checkpoint.py:184` (wire the existing `checkpoint.rollback/list/prune`
  rather than writing new code).
- *Intent:* a promotion is undoable; `lora_import` consults the gate; a registry
  records model/adapter provenance and gate results.
- *Tests:* promote-then-rollback restores the prior baseline exactly; adapter
  adoption without a passing gate is refused.
- *Gate:* code-reviewer. *Rollback:* the feature *is* rollback — test it both ways.
- *DoD:* no adapter can be adopted that cannot be un-adopted.

**WP1.4 — Write the scorecard rubric into the repo**
- *Objective:* make the 18/100 baseline reproducible (§17.3).
- *Deps:* none. *Repo:* Codey-OS — new `bench/scorecard.md` + scoring code.
- *Intent:* version-control the rubric; recompute the baseline from it. Per rule 1,
  report the measured number, never one raised by relabeling.
- *Tests:* scoring is deterministic on fixed input.
- *DoD:* anyone can recompute the score and get the same number.

**WP1.5 — `bench/verify.py` and silent-failure removal**
- *Objective:* the benchmark cannot silently report failure as the suite grows (§17.4).
- *Deps:* WP1.2 (the fix is on dev-v2). *Repo:* Codey-OS — `bench/verify.py:17-24`.
- *Intent:* fix `copy2`-over-`iterdir()`; remove `except Exception: return False`.
- *Tests:* a multi-file `hidden/` dir verifies correctly; a real error raises.
- *DoD:* no benchmark path swallows exceptions into a false verdict.

**WP1.6 — Audit the KV cost model**
- *Objective:* resolve the possible ~4× memory overestimate (§2.3). Blocks §19 and
  all NPU admission math.
- *Deps:* none. *Repo:* Codey-OS — `core/resource_gate.py` (4,911 lines).
- *Intent:* make cost topology-aware for `qwen35`'s `full_attention_interval=4`
  (~8 of 32 blocks hold a KV cache) plus SSM state.
- *Tests:* computed cost matches measured RSS within a stated tolerance.
- *Gate:* **live-verifier** — needs a real model load under rule 2 (one cycle,
  `free -h` recorded, confirmed unloaded).
- *Rollback:* revert to the current estimator. *DoD:* predicted vs actual memory
  agree on the deployed model.

**WP1.7 — Dependency and install.sh correctness (rule 11)**
- *Objective:* a fresh clone works (§20.3).
- *Deps:* none — the llama.cpp pin is now decided (WP1.7a).
- *Repo:* Codey-OS — `requirements.txt`, `install.sh`.
- *Intent:* add `python-multipart`; prune 5 orphans; add `sqlite3` if needed.

**WP1.7a — Pin `install.sh`'s llama.cpp clone** *(Ish's decision 4b)*
- *Objective:* fix `NEW-757`'s root cause — the unpinned clone that caused this
  drift twice and left the OpenCL repo's preservation audit stale (`NEW-788`).
- *Deps:* none. *Repo:* Codey-OS — `install.sh:219-220`.
- *Intent:* pin `install_llama_cpp()`'s `git clone --depth 1` to **`4f540676`**
  (current, verified to have `--load-mode` and to match the Termux package's flag
  set). Patch forward-port is **not** part of this — deferred to WP3.4.
- *Tests:* a fresh install resolves the pinned revision; the spawn contract from
  `b5b805a` still works against it.
- *Doc:* correct the OpenCL repo's preservation-audit premise (`NEW-788`).
- *DoD:* `install.sh` produces a binary whose flag set matches what
  `core/loader_v2.py` emits, deterministically.
- *Tests:* a clean-environment install check in CI if feasible.
- *DoD:* no unguarded import of an undeclared dependency.

---

### P2 — Action Gateway and the production firewall

**Dependency note:** P2 must precede any CCOS wiring. Connecting CCOS activates
§16.5's latent defects and a sandbox whose `ALLOWED_DIRS` includes `ccos/` itself.

**WP2.1 — Build the Action Gateway**
- *Objective:* one chokepoint for every irreversible action (§16.1).
- *Deps:* P0 (don't build a gateway around known-broken paths).
- *Repo:* Codey-OS — new module; `core/agent.py:335-352`,
  `ccos/core/plugin_manager.py:446`, `restoricon_core/` all route through it.
- *Intent:* shell exec, file write/patch/delete, git writes, outbound HTTP, DB
  writes, message/email sends, device actions — all pass one audited,
  policy-checked boundary. Capability manifest `permissions` / `resource_limits`
  become **enforced**, not metadata.
- *Tests:* every destructive primitive is unreachable except via the gateway (an
  invariant test, like §15.4's dormancy assertion).
- *Gate:* code-reviewer (mandatory — security + process control).
- *Rollback:* rollback tag; the gateway is additive until the old paths are removed.
- *DoD:* no destructive call site bypasses the gateway; the §16.1 three-surface
  split is gone.

**WP2.2 — Worlds / Playground isolation**
- *Objective:* developmental work can never address the live store (§9.3, directive §5).
- *Deps:* WP2.1. *Repo:* Codey-OS — `restoricon_core/database.py:18`.
- *Intent:* `RESTORICON_DB_PATH` always points at a copy in dev/test/Playground
  configurations; the live path is never a default. The gateway refuses production
  writes without explicit authorization.
- *Tests:* a test run cannot open the live DB (assert on resolved path).
- *Gate:* code-reviewer. *DoD:* the live store is unreachable from any
  non-production configuration.

**WP2.3 — Registry and validator cleanup**
- *Objective:* the safety machinery either works or is gone (§16.3, §16.6).
- *Deps:* WP2.1. *Repo:* Codey-OS — `tools/shell_tools.py:38-83,108,162`,
  `ccos/data/capabilities.json`.
- *Intent:* make one shell validator live (or delete both with the equivalence
  argument); retarget `tests/security/test_shell_injection.py` at the enforced
  path; purge 3 leaked fixtures and 4 orphan `speech.*` rows.
- *Tests:* the security suite exercises the path production uses.
- *DoD:* no green test covers a function production never calls.

**WP2.4 — Snapshot before patch**
- *Objective:* `patch_file` is undoable (§16.8).
- *Deps:* WP2.1. *Repo:* Codey-OS — `tools/patch_tools.py`.
- *Intent:* snapshot + protected-name check before applying. The system prompt
  steers the model here for all edits, so this is a high-traffic path.
- *Tests:* a patch can be reverted; protected paths refused.
- *DoD:* every `patch_file` call is recoverable.

**WP2.3a — Remove `ccos/` from sandbox `ALLOWED_DIRS`** *(Ish's decision 5)* — **DONE 2026-10-07.** `ccos/core/sandbox.py` entry removed; `ccos/tests/test_sandbox_path_validation.py`'s invariant test asserts on the resolved path (not source text), plus a behavioral test confirming a `ccos/` file access is now blocked. code-reviewer APPROVED (also swept `Sandbox(` callers repo-wide — none depend on `ccos/` being writable).
- *Objective:* close the self-modification hole before it can ever matter.
- *Deps:* none — **can land immediately**; the sandbox never runs today, so this
  costs nothing and carries no regression risk.
- *Repo:* Codey-OS — `ccos/core/sandbox.py` (`ALLOWED_DIRS`).
- *Intent:* remove `ccos/` from the allowlist. Self-modification is a capability to
  grant deliberately later — behind the promotion gate, with working rollback
  (WP1.3) — not one inherited from a config default written before the gate existed.
- *Tests:* an invariant test asserting `ccos/` is not in `ALLOWED_DIRS`, so a future
  edit cannot silently reopen it.
- *Rollback:* trivial revert. *DoD:* sandboxed code cannot write to the sandbox or
  the capability layer governing it.

---

### P3 — Brain abstraction and NPU (directive §6's first priority)

**Structure per Ish's decision 4a:** `qwen35` is kept and the SSM-state-migration
research is accepted as the path to NPU eligibility. Because that research is
open-ended, it runs as a **parallel track** and does **not** gate WP3.1 — the
BrainManager boundary is worth building on its own merits and is what the research
plugs into when it lands.

```
P3a (research track, open-ended)     P3b (engineering track, bounded)
  WP3.0 supports_op check    ──────▶   WP3.1 BrainManager boundary
  WP3.0b SSM migration R&D             WP3.2 single model-load owner
         │                                    │
         └──────────▶ WP3.4 NPU adapter ◀─────┘
```

**WP3.0 — `ggml-hexagon supports_op` check** *(do first; static, free)*
- *Objective:* determine whether `qwen35`'s SSM ops and `nomic-bert`'s non-causal
  attention are supported at all. **This scopes the research in 4a** — if the ops
  are unsupported at the backend level, SSM-state migration alone will not be
  enough, and that is much better known before the research starts than after.
- *Deps:* none. *Repo:* OpenCL-S24-Ultra (read-only). No model load.
- *DoD:* a documented yes/no per op class, recorded in the blueprint.

**WP3.0b — SSM-state-migration research** *(Ish's decision 4a; research, §22 item 2)*
- *Objective:* make `qwen35`'s hybrid SSM+attention state migratable between
  backends so prefill→decode handoff becomes possible without changing models.
- *Deps:* WP3.0 (which tells you whether the ops exist at all).
- *Scope:* `ssm.conv_kernel`/`state_size`/`group_count`/`inner_size` state plus the
  ~8-of-32 attention blocks' KV cache; patch allowlists currently
  `QWEN2||QWEN3` (#5) and `QWEN2||QWEN3||(LLAMA&&!is_swa_any())` (#7).
- *Gate:* a correctness check before any performance claim — a migrated state must
  produce **identical** output to an un-migrated run on the same prompt. Per §10.3,
  a backend that silently falls back is worse than one that fails, so verify
  *where* work ran, not just that it returned.
- *Explicitly research, not engineering (§22 item 2):* **no timeline committed, and
  it is not permitted to become a dependency of any other work package.** If it
  stalls, P3b continues and the NPU adapter waits.
- *DoD:* either a working migration with a correctness proof, or a documented
  negative result with the reason — both are acceptable outcomes.

**WP3.1 — BrainManager boundary** *(valuable regardless of NPU)*
- *Objective:* backend-independent inference adapter (§10.6 N1, §18.3).
- *Deps:* WP1.6 (cost model must be right first).
- *Repo:* Codey-OS — `core/loader_v2.py`, `core/daemon.py`, `core/inference*.py`,
  `embed_server.py`, `utils/config.py`.
- *Intent:* abstract process model, lifecycle, memory accounting, context handling,
  tokenizer, streaming, failure modes. **Backends must declare where work actually
  ran** (§10.3 — OpenCL silently running attention on CPU is the failure mode to
  defend against). Unify the two divergent spawn sites (§2.4). CPU llama-server is
  adapter #1 and the baseline.
- *Tests:* adapter contract tests; CPU adapter passes identically to today.
- *Gate:* code-reviewer (process lifecycle — rule 4) + live-verifier.
- *Rollback:* rollback tag; keep the direct path until the adapter is proven.
- *DoD:* no module outside the adapter references llama-server specifics.

**WP3.2 — Single model-load owner**
- *Objective:* eliminate the daemon bypass (§2.2) — top operational risk, rule 2.
- *Deps:* WP3.1. *Repos:* Codey-OS (`tools/ensure_model_cli.py`),
  Codey-Aigentik (`index.js:228`).
- *Intent:* route Aigentik's load through the daemon socket (its release path
  already does); stop `stdio:'ignore'` swallowing failures.
- *Tests:* concurrent load attempts serialize; failures surface to the caller.
- *Gate:* code-reviewer (mandatory — process lifecycle) + **live-verifier** under
  rule 2.
- *DoD:* exactly one process can load a model; Aigentik sees load errors.

**WP3.3 — ~~Model eligibility decision~~ RESOLVED (Ish, 2026-10-06)**
- **4a:** keep `qwen35`; pursue SSM-state migration → **WP3.0b**.
- **4b:** pin `install.sh` to `4f540676` → **WP1.7a**. Patch forward-port deferred
  into WP3.4, where it belongs with the adapter work.

**WP3.4 — NPU adapter** *(gated on WP3.0 + WP3.0b + WP3.1)*
- Includes forward-porting the 8 patches to the pinned revision (deferred here from
  decision 4b), since that work only pays off once the adapter exists.
- *Objective:* NPU as a selectable backend, CPU preserved as default.
- *Intent:* build `llama-server` for the accelerator trees
  (`-DLLAMA_BUILD_SERVER=OFF` today); express the **single-session ceiling** as a
  hard resource-gate constraint; record per-model/per-context/per-workload
  compatibility rather than assuming it.
- *Gate:* **no production default change** without a matched, n≥3,
  temperature-controlled benchmark on an actually-deployed model, recorded in the
  §17 ledger. The Mistral-7B result does not meet this bar.
- *Rollback:* CPU remains default until the gate passes. *DoD:* NPU selectable,
  CPU unchanged, compatibility recorded.

---

### P4 — Make memory read back (S2 prerequisite)

- **WP4.1 — Tier 2 decision:** store content or delete the tier (§15.1). A hash is
  not memory. Also correct `core/memory_v2.py:5-22`'s false docstring (rule 6).
- **WP4.2 — One retrieval stack:** keep `tools/kb_semantic.py`, delete
  `core/embeddings`' dead store, with the equivalence argument stated (§6.2).
- **WP4.3 — Replace the silent context cliff** at `core/agent.py:1641` with
  explicit, observable budgeting.
- **WP4.4 — Knowledge-corpus ingestion:** build the missing programmatic path; add
  to `install.sh` (§15.2). Until a corpus exists the `retrieval`/`skills` prompt
  layers are decoration.
- **WP4.5 — Restore the interactivity signal for dashboard users** with the
  freshness/liveness guard `resource_gate.py:3977-3980` already specifies (§2.5).
  Aligns with the standing "dashboard = single control surface" direction.

Each: deps P1; tests assert retrieved content reaches the prompt; DoD is
**behavioural** — a stored fact demonstrably changes a later response.

---

### P5 — Cleanup and restructure (§6.5 order; continuous, not deferred)

P5 runs **in parallel** with P2–P4 as bounded batches, per directive §9 — not
saved for the end. Order: rule-6 comment corrections and the `resource_bus` leak
first (cheap, zero-risk), then duplicate consolidation one pair per batch
(§6.1), then dead-code deletion with replacement arguments (§6.2), then the
`ccos/core` vs `ccos/dormant` split (§7.2) **last**. Doc work (§8.4, **approved by
Ish 2026-10-06**) lands with each batch, and the CLAUDE.md map-completeness test
(§8.4 item 1) ships in P1 alongside CI.

**WP5.1 — Split `restoricon_core/` into its own repo** *(Ish's decision 6; §3.5)*
- *Objective:* give the production business system an independent release lifecycle,
  per directive §4.
- *Deps:* **P0 complete** (so the `notification_service.py` security fix lands in one
  repo, not across a move) **and P2's Action Gateway complete** (so the split is a
  real architectural boundary rather than a relocation of the
  three-disjoint-surfaces problem). Both constraints are explained in §3.5.
- *Repo:* new production repo + Codey-OS — `restoricon_core/` (~29 `.py`) plus the
  API surface.
- *Intent:* `git filter-repo`/`git mv` to preserve history; one versioned cross-repo
  API contract with a single endpoint source of truth (§3.4); `RESTORICON_DB_PATH`
  remains the DB seam.
- *Tests:* the Core API's full suite passes from the new repo; Aigentik's 54 call
  sites and Private-Codey-Agent's client still resolve (after WP0.4/§12.7).
- *Gate:* code-reviewer (mandatory — it moves all the RBAC and most of the
  destructive surface). **No live-verifier availability concern** — production is
  manually started (§9.4), which is what makes this split cheap to do safely now.
- *Rollback:* rollback tag before the move; the old path stays importable until the
  new repo is proven.
- *Cleanup/doc:* CLAUDE.md map regenerated (it currently omits `restoricon_core/`
  entirely — `NEW-772`); `docs/INDEX.md` updated; §3 contracts rewritten.
- *DoD:* Codey-OS no longer contains production business code; the Core API serves
  from its own repo with its own release tags; one commit cannot change both the
  research system and the production system.

---

### P6 — Developmental stages S2–S6

**Not plannable in detail yet, and saying so is the honest answer.** Every stage
here consumes verified experience; P0–P4 are what make experience verified.
Attempting detailed work packages now would reproduce the error this census
exists to correct — planning from intent rather than from the system's actual state.

| Stage | Gate to enter | Prereqs |
|---|---|---|
| S2 memory & imitation | a stored fact measurably changes a later response | P4 complete |
| S3 curiosity & practice | practice generation measured by learning progress, not novelty | S2 + §17 ledger populated |
| S4 self-directed improvement | gate + rollback proven on a real promotion | P1, WP1.3, WP0.5 |
| S5 brain swap | model-independent assets demonstrably survive a swap | §18.3 complete |
| S6 graduated autonomy | clean safety history + human-authorized ceilings | P2 complete; §16.9 human gates |

**Re-plan P6 in detail when P4 completes** — and update this blueprint's status
(directive §11) rather than spawning a competing master plan.

---

### Decisions — ALL RESOLVED by Ish, 2026-10-06

| # | Decision | Ish's call |
|---|---|---|
| 1 | Is Restoricon production live? | **Manually started, not yet in full use.** Data integrity — not availability — is the binding constraint; services may be stopped/restarted during development under a check-before-acting rule. §9.4 |
| 2 | Rewrite `AGI_AUDIT_LOG.md`'s Phase 3 workflow, which prescribes the leak | **Yes.** WP0.5 includes the rewrite. |
| 3 | The gate's 30-pair / ~13 h device-time minimum | **Derive a defensible smaller `n` via power analysis first, then batch overnight.** The 30-pair figure was a cost, never a derived requirement. WP1.3a. |
| 4a | NPU model eligibility | **Do the SSM-state-migration research to support `qwen35`.** Keeps the single-model architecture. Accepted as open-ended research (§22 item 2). |
| 4b | llama.cpp pin | **Pin `install.sh` to a known-good revision (`4f540676`).** Patch forward-port deferred to the NPU task. WP1.7a. |
| 5 | Sandbox `ALLOWED_DIRS` including `ccos/` | **Remove `ccos/`.** Costs nothing today (the sandbox never runs); self-modification is re-granted deliberately later, behind the gate with working rollback. WP2.3a. |
| 6 | Should `restoricon_core/` split out? | **Split it into its own repo now.** Supersedes §3.3's recommendation — see §3.5 for the decision record and the sequencing constraint. |
| 7 | Plaintext Cloudflare tunnel token | **Move to the existing age/keystore mechanism.** No rotation (no exposure evidence). WP0.7. |
| 8 | Escrow DR key (`setup_dr_key.py --force`) | **Still open** — carried over from the admin-dashboard programme; not raised this round. Flagged, not forgotten. |

**Two decisions went against the blueprint's recommendation (4a and 6). Both are
recorded as Ish's calls and the roadmap below implements them**, with one
sequencing constraint noted on each — not a re-litigation, just ordering:

- **4a:** the SSM research is open-ended, so it must **not** gate the BrainManager
  boundary. P3 runs them in parallel: the boundary is independently valuable
  (it fixes the dual model-load owner and the divergent spawn sites) and the
  research feeds the adapter when it lands.
- **6:** the split touches the file holding the two unauthenticated email paths
  (`notification_service.py`), so it is sequenced **after P0**. Doing surgery on
  that file mid-move would mean fixing a live security hole across a repo
  boundary.

## 22. Known research uncertainties (separated from engineering)

Everything in §21 is ordinary engineering. The items below are **not**, and the
blueprint's position is that the architecture should make them *measurable* rather
than assume answers.

1. **How much of "development" is genuinely model-independent?** §18 assumes
   trajectories, skills, and memory survive a brain swap. Untested — and currently
   untestable, since almost nothing model-independent has accumulated (§18.2).
   *Make measurable:* define the post-swap re-verification suite before the first swap.
2. **Whether `qwen35`'s hybrid SSM/attention state can migrate between backends
   at all.** Blocks NPU prefill→decode for the deployed model (§10.1). This is a
   genuine research question in llama.cpp territory, not an integration task.
   **Ish chose this path (decision 4a, 2026-10-06)** over deploying a Qwen3 model,
   to keep the single-model architecture — so it is now an *accepted research
   track* (WP3.0b) rather than a hypothetical. The standing rule below still
   applies with full force: **it may not become a dependency of any other work
   package.** P3b (BrainManager, single load owner) proceeds in parallel and waits
   on nothing here; only WP3.4's NPU adapter does. A documented negative result is
   an acceptable outcome.
3. **Whether the single-NPU-session ceiling is fixable.** Cause of `0x200`
   AEE_ERPC unidentified (§10.3). Codey-OS needs three servers.
4. **What a defensible minimum sample is for promotion.** The 30-pair/13-hour
   figure (§17.6) is a cost, not a derived statistical requirement. Choosing a
   smaller defensible n is a statistics question.
5. **Whether learning-progress curiosity works at this scale.** Directive §14
   prefers it over raw novelty. Reasonable, and unvalidated for a 4B local model
   on-device.
6. **Whether LoRA/SFT on self-generated verified data improves anything here.**
   Assumed by S4. With the leak closed (WP0.5) the honest answer is unknown — and
   the sample sizes available on-device may be too small to tell.
7. **What autonomy ceiling is safe per capability.** §16.9 and directive §15 keep
   this human-gated. The gateway makes a ceiling *expressible*; it does not make it
   *knowable*.
8. **Whether sleep/consolidation earns its cost on-device.** Replay, dedup, failure
   clustering, procedure extraction — all plausible, all unmeasured, all competing
   for the same thermal and battery budget as useful work (§19).

**Standing rule for this section:** nothing here is permitted to become a roadmap
dependency dressed as an engineering task. If a work package turns out to rest on
one of these, it stops and returns here for an explicit decision.
