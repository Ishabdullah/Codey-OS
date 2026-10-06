# C2 — Coordinator's direct findings (2026-10-06)

## F1. CLAUDE.md's repo map omits four substantial tracked subsystems — DOC DRIFT

CLAUDE.md's "Current repo structure" block lists `ccos/ core/ docs/ lib/ pipeline/
prompts/ tests/ tools/ utils/` plus top-level files. Actual tracked top-level
Python subsystems, by file count:

| Dir | Tracked files | `.py` | In CLAUDE.md map? |
|---|---|---|---|
| `tests/` | 201 | 201 | yes |
| `ccos/` | 122 | 100 | yes |
| `core/` | 64 | 64 | yes |
| **`bench/`** | 44 | 34 | **NO** |
| **`restoricon_core/`** | 29 | 29 | **NO** |
| `docs/` | 28 | 0 | yes |
| `pipeline/` | 25 | 25 | yes |
| **`codey_estimator/`** | 21 | 21 | **NO** |
| **`telemetry/`** | 11 | 9 | **NO** |
| `tools/` | 11 | 10 | yes |
| `utils/` | 4 | 4 | yes |
| `prompts/` | 4 | 4 | yes |
| `lib/` | 1 | 0 | yes |

The four undocumented dirs hold **93 tracked Python files** — ~19% of the repo's
502 `.py` files — and they are precisely the subsystems the directive cares most
about: evaluation (`bench/`), the Restoricon production layer
(`restoricon_core/`), the estimator integration (`codey_estimator/`), and
observability (`telemetry/`).

This matters beyond tidiness: CLAUDE.md is the file every new agent context reads
first, and it is the stated defence against the repeat-finding problem
(`NEW-26`/`NEW-27`). An agent trusting that map would not know `restoricon_core/`
or `codey_estimator/` exist.

**Consequence for §7 (target tree) and §8 (doc plan):** the map must be
regenerated from `git ls-files`, and ideally checked by a test rather than
maintained by hand.

**Also note:** `codey_estimator/` existing *inside* Codey-OS alongside the
separate `Codey-Estimator-reference` repo is the duplicate-implementation
question directive §12 asks about. Census B3 is sizing it.

## F2. 254 leaked 32-hex state directories in the repo root — 7.9 MB

```
$ ls -d */ | grep -cE '^[0-9a-f]{32}/$'
254
$ du -csh <those dirs> | tail -1
7.9M	total
```

Each contains exactly:
```
-rw------- 28672 Sep  3 14:46 resource_bus.db
-rw-------     0 Sep  3 14:46 resource_bus.lock
```

mtimes span 2026-09-03 → 2026-10-06, i.e. still accumulating.

**Mechanism:** `core/resource_bus.py:112-121` — `_get_db_path()` /
`_get_lock_path()` call `base.mkdir(parents=True, exist_ok=True)` on
`Path(state_dir)` or `Path(CODEY_STATE_DIR)`. When that value is a bare 32-hex
*relative* name, the directory is created relative to CWD — the repo root.

**Not the unit tests.** `tests/test_resource_gate.py:651+` correctly passes
pytest's `tmp_path`. Root cause is something supplying a bare hex session id as
the state dir; `.gitignore:46` describes the pattern as "Session log directories
(32-char hex)". Exact producer not yet identified — handed to the hygiene pass.

**The notable part:** the response to this leak was a `.gitignore` rule
(`.gitignore:44-46`) that hides the symptom, leaving the write-into-repo-root
behaviour in place. Related to the test-isolation class already fixed in
`dd49c1d` (recombiner/optimizer/sandbox), which this instance escaped.

## F3. Live Restoricon production store — verified contents (read-only)

**Path:** `~/.codeyOS/restoricon.db`, 4,018,176 bytes, mtime 2026-09-30 17:50,
with a live `-wal` (1,058,872 b) and `-shm` (32,768 b).

Method: copied db + wal + shm to scratchpad and inspected **only the copy**.
Original mtimes confirmed unchanged afterwards. No process was writing (census
started with no Codey processes running). No `sqlite3` CLI on device — used
Python's `sqlite3` module.

**70 tables; 31 populated, 39 empty.**

Populated (real business data — this is live, not fixtures):

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

**Empty (39)** — and the pattern is the finding:

- **Every estimator table is empty:** `estimates`, `estimate_line_items`,
  `estimate_versions`, `estimate_decisions`, `estimate_number_sequences`,
  `estimate_share_links`. Independently corroborated by
  `Codey-Estimator-reference` HEAD `df0730f` (2026-09-27) "Record §21 DB check
  result: estimates table is empty, no migration needed".
  ⇒ The estimator integration is **schema-only / never exercised in production**.
- **Every pricing/retailer table is empty:** `canonical_materials`,
  `labor_rates`, `labor_rate_history`, `price_book_items`, `price_observations`,
  `pricing_jobs`, `material_matches`, `retailers`, `retailer_products`,
  `retailer_stores`, `package_options`, `search_cache`, and the
  `product_search_fts*` shadow tables.
  ⇒ The B9.x pricing-tables work is **code/schema-complete but carries zero
  production data**. It cannot have been validated against real use.
- Other empty: `employees`, `equipment`, `equipment_deployments`, `timesheets`,
  `staff_schedules`, `staff_schedules_archive`, `territories`, `vendors`,
  `purchase_orders`, `project_milestones`, `compliance_items`,
  `customer_credits`, `financial_transactions`, `financing_records`,
  `homecare_subscriptions`, `marketing_campaigns`, `review_requests`.

**Interpretation for the blueprint:** the live production surface is much
narrower than the 70-table schema implies. Actual production dependency is
concentrated in CRM/comms (`contacts`, `communication_history`, `customers`,
`leads`, `opportunities`), auth (`users`, `api_tokens`), audit (`audit_log`), and
a thin job layer (`projects`, `work_orders`, `invoices`, `contracts`,
`appointments`). That is the set the §9 firewall must protect. The other ~39
tables are build-out ahead of use — safe to refactor, and *not* evidence of
working features.

`_litestream_seq` has 1 row and `_litestream_lock` is empty ⇒ Litestream
replication is configured (`core/setup_litestream.py`) but see A4/B4 for whether
it is actually running. It was not running at census start.

## F4. Production store ownership — code paths

| Site | Role |
|---|---|
| `restoricon_core/database.py:18` | canonical path resolution: `os.getenv("RESTORICON_DB_PATH", "~/.codeyOS/restoricon.db")` |
| `utils/config.py:717` | `str(CODEY_STATE_DIR / "restoricon.db")` |
| `utils/config.py:689` | documents defaults: host `127.0.0.1`, port **8770**, that db path |
| `config.json:8` | `"db_path": "~/.codeyOS/restoricon.db"` |
| `lib/service_manager.sh:238,244` | shell fallback `127.0.0.1|8770|$DAEMON_DIR/restoricon.db` |

⇒ Core API serves this store on **127.0.0.1:8770** (loopback only). The env
override `RESTORICON_DB_PATH` is the clean seam for pointing development at a
copy — central to the §9 firewall design.

4 dated production backups exist in `~/.codeyOS/` (pre-b9.1, pre-b816phase5,
pre-bounce-loop-fix, pre_d2_role_migration), showing the established
backup-before-migration convention.

## F5. No Codey / Restoricon process running at census start

`ps aux` showed only `python battery-watch.py` (PID 31924, started "2022" per
ps's field — i.e. long-running). `ss -tlnp` showed **no listening TCP ports** —
so the Core API on 8770 is down.

This is a **finding, not an all-clear**: Restoricon's production data exists and
is current to 2026-09-30, but the service over it is not up. Either it is started
on demand, or production is effectively offline. Must be resolved with Ish before
the §9 firewall map can claim to be complete — it changes what "keep Restoricon
operational" concretely requires.

## F6. Environment facts that bit this census (worth encoding)

- Bare `find` and `grep` **silently return nothing** in this Termux shell —
  not an error, empty output. Early census commands produced false negatives
  (e.g. "no .db files in Codey-OS" while `ccos/data/ccos_memory.db` exists).
  Full binary paths are required. Already in project memory; confirms it.
- No `sqlite3` CLI installed, though the project is SQLite-centric throughout.
  Per CLAUDE.md rule 11, if any workflow assumes it, `install.sh` must add it.
- `/tmp` is not writable (`Permission denied`); scratchpad must be used.
