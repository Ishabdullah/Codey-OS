# B3 — Estimator Capability Census (Codey-Estimator-reference vs codey_estimator/)

Scope: `/data/data/com.termux/files/home/Codey-Estimator-reference` (standalone)
vs `/data/data/com.termux/files/home/Codey-OS/codey_estimator/` (vendored copy)
vs `restoricon_core/` (consumer) vs live production DB schema.
Method: static inspection only, no services started, no model loaded, DB copy
read via python3 `sqlite3` module only.

## (a) Module mapping table

`Codey-Estimator-reference/src/codey_estimator/` (21 .py) is **byte-for-byte
identical** to `Codey-OS/codey_estimator/` (21 .py) with ONE exception
(`__init__.py`, which carries a vendoring-provenance docstring in the
Codey-OS copy). Verified with `diff` on every file pair — all 20 non-`__init__`
files diffed empty; the four package `__init__.py` files (`calc/__init__.py`,
`catalog/__init__.py`, `retailers/__init__.py`) also diffed empty; only the
top-level `codey_estimator/__init__.py` differs (18-line provenance docstring
added, `Codey-OS/codey_estimator/__init__.py:1-18`).

This is confirmed by the vendoring commit itself:
`Codey-OS` commit `ef04dab` ("B9.2: EstimateService core, vendored
codey_estimator, and a real migration fix") — commit message states
"Vendors the codey_estimator calculation library (cloned from
github.com/Ishabdullah/Codey-Estimator, verbatim)". `codey_estimator/__init__.py:1-18`
documents it was vendored from commit `df0730f79f902835974101e6c05c18c8c20ce270`
(2026-09-27) on 2026-09-29, and explicitly instructs: "Do not hand-edit files
under this package to fix a bug — fix it upstream in Codey-Estimator and
re-vendor."

Verdict: **not** a subset, rewrite, client/shim, or independent fork. It is a
**verbatim vendored copy** of one specific commit of the reference repo's
`src/codey_estimator/` package only (the pure calc/catalog/retailer-parsing
library). The reference repo additionally has `tests/` (24 files),
`pyproject.toml`, `README.md`, `docs/`, none of which are vendored (expected —
tests/build metadata don't ship).

| Module | Reference (`src/codey_estimator/`) | Codey-OS (`codey_estimator/`) | Status |
|---|---|---|---|
| `__init__.py` | plain | + provenance docstring | IDENTICAL (code) |
| `calc/engine.py` | present | present | IDENTICAL |
| `catalog/*.py` (6 files) | present | present | IDENTICAL, but DORMANT in Codey-OS (see b) |
| `dto.py`, `errors.py`, `money.py`, `units.py`, `ports.py`, `refresh.py` | present | present | IDENTICAL |
| `retailers/*.py` (5 files) | present | present | IDENTICAL, but DORMANT in Codey-OS (see b) |

Critically, the reference repo is **itself purely a calc/catalog/parsing
library with no DB, no API, no service layer** (`pyproject.toml`:
`dependencies = []`, description "Restoricon estimating library (pure,
stdlib-only)"). It was never a competing *application* — the actual
persistence/service/API layer (`restoricon_core/services/estimate_service.py`,
`pricing_repo.py`, `pricing_job_service.py`, `restoricon_core/api/routes.py`,
`restoricon_core/database.py`, `restoricon_core/models.py`) exists **only** in
Codey-OS and was built on top of the vendored library. So this is not
"duplicate implementations of the same app" — it is "one library, vendored
once, with a service layer built on top in exactly one place."

Git lineage: reference repo's local clone is a **shallow clone** pinned to
exactly `df0730f` (`.git/shallow` contains only that hash) — `git log` shows
only 1 reachable commit locally, so no deeper shared-history comparison is
possible from this checkout. Codey-OS's own history shows exactly one commit
(`ef04dab`, 2026-09-29) introduced `codey_estimator/`, and no subsequent
commit touches any file under it (`git log --oneline -- codey_estimator`
returns only `ef04dab`) — confirming it has not silently diverged since
vendoring, consistent with the "do not hand-edit" instruction being honored.

## (b) Reachability verdict

**`Codey-OS/codey_estimator/` — PARTIALLY REACHABLE (IMPLEMENTED for the
reachable slice, DORMANT for the rest).**

Confirmed live entrypoint chain:
`codey-start` → `lib/service_manager.sh:start_restoricon()` (line 226, spawns
`python3 -m restoricon_core.api.server --host ... --port ... --db ...` at
`lib/service_manager.sh:247`) → `restoricon_core/api/server.py:209`
(`self.estimate_service = EstimateService(self.db, ...)`) →
`restoricon_core/api/routes.py:78` (`from ..services.estimate_service import
EstimateService`), wired into `/api/v1/estimates*` and
`/api/v1/public/estimate/*` routes (`routes.py:837-963`, `1725-1755`) →
`restoricon_core/services/estimate_service.py:82-97` imports
`codey_estimator.calc.engine.{CALC_ENGINE_VERSION,calculate}`,
`codey_estimator.dto.*`, `codey_estimator.errors.EstimatorError`.
`restoricon_core/services/pricing_repo.py:34,43` imports
`codey_estimator.ports.*` and `codey_estimator.refresh.{EpochSeconds,
RefreshStatus}`.

Exhaustive import search (`grep -rn "^from codey_estimator\|^import
codey_estimator" restoricon_core/`) found **exactly two importers**:
`estimate_service.py` and `pricing_repo.py`. Transitively reachable
submodules (traced via each file's own internal imports):
`calc/engine.py`, `dto.py`, `errors.py`, `money.py`, `units.py`, `ports.py`,
`refresh.py` — 7 of 21 vendored files.

**DORMANT (vendored, never imported by anything reachable from a real
entrypoint): `catalog/__init__.py`, `catalog/keys.py`, `catalog/matcher.py`,
`catalog/normalizer.py`, `catalog/package.py`, `catalog/schema.py`,
`catalog/text.py`, `retailers/__init__.py`, `retailers/base.py`,
`retailers/csv_import.py`, `retailers/manual.py`, `retailers/parsing.py`**
— 10 of 21 vendored files (plus `retailers/__init__.py`'s own re-exports).
Confirmed by grepping `pricing_job_service.py` and `pricing_repo.py` (the two
services that would plausibly use material matching / retailer ingestion)
for `catalog`, `matcher`, or `retailers.` — zero hits in either file.
`pricing_job_service.py` is only 122 lines (`wc -l`) and is pure job-lifecycle
bookkeeping (pending/running/succeeded/failed transitions,
`PricingJobService._finish()`), not a scraper/matcher driver — the module
that would call `catalog.matcher`/`retailers.csv_import` to actually populate
`price_observations`/`material_matches` does not exist in Codey-OS.

**`Codey-Estimator-reference` (the standalone repo itself) — DORMANT, by
design, from Codey-OS's perspective.** Searched Codey-OS for any subprocess
call, HTTP call, `sys.path` insertion, or import referencing the standalone
repo's filesystem path or package name outside the vendored copy
(`grep -rn "Codey-Estimator" --include=*.py --include=*.sh .`): the only
hits are doc/comment references to the *name* "Codey-Estimator" in
docstrings, `NEW_ISSUES.md`, `PROJECT_LOG.md`, `CODEY_MASTER_PLAN.md` — no
code path in Codey-OS executes anything from
`~/Codey-Estimator-reference` at runtime. This is intentional: the reference
repo is kept as a read-only source-of-truth for re-vendoring, per
`codey_estimator/__init__.py:13-16` and `NEW_ISSUES.md:18426` ("Ish decided
to clone the real repo ... into `~/Codey-Estimator-reference` as a read-only
source reference").

## (c) Feature-level diff

Because the vendored copy is byte-identical to the reference, there is no
feature gap *within the library itself* — every function in both repos is
the same code. The real gap is **integration**, i.e. what Codey-OS's service
layer actually calls:

| Feature | Library support (both repos, identical) | Wired in Codey-OS? |
|---|---|---|
| Line-item cost/price calculation | `calc/engine.py` (`calculate()`, `CALC_ENGINE_VERSION`) | YES — `estimate_service.py:82` |
| DTOs / customer view | `dto.py` (incl. `to_customer_view`) | YES — `estimate_service.py:83-96` |
| Error types | `errors.py` | YES |
| Units/package math | `units.py` | YES (transitively via `dto.py`/`calc/engine.py`) |
| Money/rounding | `money.py` | YES (transitively via `calc/engine.py`) |
| Refresh/rate-limit/circuit-breaker policy | `refresh.py`, `ports.py` | YES — `pricing_repo.py:34,43` (policy objects only — see below) |
| Versioning (lock/supersede) | Not in library — implemented directly in `estimate_service.py`'s `revise()` | N/A, in-repo only, not from the library |
| Share links | Not in library — `estimate_share_links` table + `routes.py`/`estimate_service.py` | N/A, in-repo only |
| Decision tracking (accept/decline) | Not in library — `estimate_decisions` table + `record_decision()` | N/A, in-repo only |
| Number sequences | Not in library — `estimate_number_sequences` table, in-repo logic | N/A, in-repo only |
| PDF/export | Not found in either repo (no `pdf`, `export`, `reportlab`, `weasyprint` reference in either tree) | **MISSING in both** |
| Material matching (`catalog/matcher.py`: UPC/model/attribute confidence matching) | present, fully implemented in library | **DORMANT** — `material_matches` table exists in live DB and is empty; no Codey-OS code calls `catalog.matcher` |
| Material normalization/catalog schema (`catalog/normalizer.py`, `catalog/schema.py`, `catalog/keys.py`, `catalog/text.py`, `catalog/package.py`) | present | **DORMANT** |
| Retailer product parsing/import (`retailers/csv_import.py`, `retailers/manual.py`, `retailers/parsing.py`, `retailers/base.py`) | present | **DORMANT** — no code path populates `retailer_products`/`price_observations` from these modules |

So: versioning, share links, decision tracking, and number sequences are
**IMPLEMENTED in Codey-OS directly** (not sourced from the library — the
library doesn't have these concepts at all). Line-item calculation and the
refresh/policy primitives are **IMPLEMENTED and reachable** via the vendored
library. Material matching and retailer ingestion are **DORMANT** — present
in the vendored code, backed by real (empty) DB tables, but with no caller.
PDF/export is **MISSING** in both repos entirely.

## (d) Three-way schema reconciliation (doc vs code vs live DB)

Live DB schema dumped directly via `python3`'s `sqlite3` module against the
read-only copy at
`.../scratchpad/dbcopy/restoricon.db` (never the original).

**MISMATCH #1 (CONFIRMED) — `estimate_line_items` pricing FKs.**
`codey_estimator_schema.md:245-256` ("Estimate Line Items (Codey-Estimator
Phase B9.1, NEW)") states explicitly: "`price_book_item_id /
retailer_product_id / price_observation_id / labor_rate_id` are bare
INTEGER, NO FOREIGN KEY — their target tables are deliberately deferred to a
later phase ... a future migration attaches real FKs once those tables
exist," and the doc's own `CREATE TABLE` block (ending `);` right after)
only has FKs on `estimate_version_id`, `equipment_id`, `subcontractor_id`.
The **live DB** (and current `restoricon_core/database.py:414-432`'s
`CREATE TABLE IF NOT EXISTS estimate_line_items`, confirmed by direct dump)
now has all four: `FOREIGN KEY (price_book_item_id) REFERENCES
price_book_items(id) ON DELETE SET NULL`, `retailer_product_id REFERENCES
retailer_products(id)`, `price_observation_id REFERENCES
price_observations(id)`, `labor_rate_id REFERENCES labor_rates(id)` — these
were attached by `_migrate_estimate_line_items_pricing_fks()`
(`database.py:3206`) in the B9.x pricing round (2026-09-30), per the
code-reviewer memory notes. **`codey_estimator_schema.md` is stale (written
at B9.1, 2026-09-27) and was never updated for the B9.x pricing round.**

**MISMATCH #2 (CONFIRMED) — `estimates.property_id` FK.**
`codey_estimator_schema.md:80-87` states: "`property_id`: bare INTEGER, NO
FOREIGN KEY. Not the ALTER-TABLE-can't-..." (deferred FK). The **live DB**
has `FOREIGN KEY (property_id) REFERENCES properties(id) ON DELETE SET
NULL` (confirmed by direct dump of `sqlite_master.sql` for `estimates`),
matching current `database.py`'s `_ESTIMATES_TABLE_V2_SQL` constant and the
corrective comment at `database.py:291` ("this comment previously claimed
properties was 'designed but not yet built' ... that was stale"). Same root
cause as Mismatch #1: `codey_estimator_schema.md` documents the B9.1-era
shape and was not updated when `_migrate_estimates_property_id_fk()`
(`database.py:3022`) attached the FK in the B9.x pricing round.

**No code/live-DB mismatch found.** Every table dumped from the live DB
(`estimates`, `estimate_line_items`, `estimate_versions`,
`estimate_decisions`, `estimate_number_sequences`, `estimate_share_links`,
and all 12 pricing/retailer tables: `canonical_materials`, `labor_rates`,
`price_book_items`, `price_observations`, `retailers`, `retailer_products`,
`retailer_stores`, `package_options`, `material_matches`, `pricing_jobs`)
matches `database.py`'s current `CREATE TABLE` constants exactly (column
set, types, CHECK constraints, FKs) — the migrations have already run
against this production DB copy and left it in the current-code shape, not
a legacy shape. (`labor_rate_history`, `search_cache`,
`product_search_fts*` were named in the task's "already established"
summary as empty but were not independently re-dumped here since they carry
no estimator-schema mismatch risk; flagged as an open item in (j).)

**Not checked against the reference repo's own schema**, because the
reference repo (`Codey-Estimator-reference`) has **no DB schema of its
own** — it is a pure calc/catalog/parsing library with zero persistence code
(confirmed: no `CREATE TABLE`, no `sqlite3`, no ORM anywhere in
`src/codey_estimator/`, consistent with `pyproject.toml`'s `dependencies =
[]`). There is nothing to three-way-reconcile on the reference-repo side —
the schema is entirely a Codey-OS artifact (`database.py` +
`codey_estimator_schema.md`), and the doc is the side that drifted.

## (e) B9.8 / pricing-tables code verification

**B9.8 `EstimateService.convert()`** — per code-reviewer memory
(`b9_8_estimate_convert_approved.md`), APPROVED round 1, with two disclosed
open gaps (NEW-736, NEW-737) about `opportunities.project_id` validation and
`contracts.project_id`/`estimates.project_id` backfill — not re-litigated
here since the task's ask is specifically the commit-before-raise question,
which is B9.x pricing tables, not B9.8.

**Commit-before-raise question (B9.x pricing round,
`_migrate_estimates_property_id_fk`, `restoricon_core/database.py:3022-3204`)**
— read directly, current state:

- Round 1 (CHANGES REQUESTED,
  `b9_x_pricing_tables_property_id_fk_commit_before_raise_changes_requested.md`):
  the original bug was that the terminal `PRAGMA foreign_key_check` ran
  AFTER the `with conn:` block had already committed the rebuild, so an
  orphaned `property_id` got a FK clause permanently written into
  `estimates`' stored DDL before the violation was ever detected — silent
  corruption on the second DB open.
- **Current code (verified by direct read, `database.py:3060-3204`):**
  1. A **pre-flight** dangling-id check (`database.py:3083-3093`) runs
     BEFORE the `with conn:` rebuild block even opens, using `NOT EXISTS`
     against `properties`, and raises `RuntimeError` with zero DDL touched
     if any row is orphaned.
  2. The rebuild itself (`database.py:3145-3189`, inside `with conn:` /
     `BEGIN IMMEDIATE`) does the drop/rename/reindex, and the **terminal
     `PRAGMA foreign_key_check(estimates)`** (table-scoped) is at
     `database.py:3185-3189`, **still inside the `with conn:` block** (the
     block doesn't close until line 3189's `raise` or falls through to
     commit after it). Raising at line 3187 triggers the `with conn:`
     context manager's own rollback — **no commit happens before the
     raise.**
  3. `conn.execute("PRAGMA foreign_keys = OFF;")` at line 3143 is OUTSIDE
     the `with conn:` block but is a pragma toggle, not a data-mutating
     statement — it is re-enabled in a `finally:` (line 3190-3191)
     regardless of whether the transaction committed or raised, so it
     doesn't leave any partial state.
  - **Verdict: fixed correctly.** The exact bug pattern described (commit
    before raise, leaving partial writes) is not present in the current
    file — the only commit point is the fall-through at the end of the
    `with conn:` block, after the FK-violation check has already passed.
    This matches the round-2 code-reviewer memory
    (`b9_x_pricing_tables_round2_approved.md`), independently re-confirmed
    here by reading the live file rather than trusting the memory note.
  - One residual, lower-risk item **outside the scope of "commit before
    raise"**: the trigger-count-preservation check
    (`database.py:3193-3204`) runs AFTER the `with conn:` block exits (i.e.
    after commit) — same shape in miniature, but the code-reviewer's round-2
    note already flags this as accepted lower risk (a lost `CREATE TRIGGER`
    would itself raise inside the transaction on a genuine failure, so the
    only way it's silently lost is a logic bug skipping the recreate call
    entirely — the assertion still catches that, one open cycle later than
    ideal, not silently). Not re-litigated further here since it's already
    a disclosed, accepted gap, not a new finding.

## (f) Remaining integration work / definition of done

Concrete gaps, in order of what "fully proving the integration" would need:

1. **Material matching pipeline (DORMANT → needs wiring).**
   `codey_estimator.catalog.matcher` is fully implemented and vendored but
   has zero callers. `material_matches` table is schema-complete and empty.
   Needs: a service (analogous to `pricing_job_service.py` but for
   matching) that calls `catalog.matcher` against `canonical_materials` and
   `retailer_products` and writes `material_matches` rows. No such service
   exists today — `pricing_job_service.py` is job-lifecycle bookkeeping
   only.
2. **Retailer ingestion pipeline (DORMANT → needs wiring).**
   `codey_estimator.retailers.{csv_import,manual,parsing,base}` are fully
   implemented and vendored but have zero callers. Needs: something that
   actually populates `retailer_products`/`price_observations` from a real
   retailer feed/CSV/manual entry flow and calls into these modules. Today
   nothing in `restoricon_core/` calls `retailers.csv_import` or
   `retailers.manual` at all.
3. **API routes for pricing/retailer management.** `routes.py` has
   `/api/v1/estimates*` and the public share-link routes, but no
   grep hit for pricing-job-trigger or retailer-CRUD routes was found in
   this pass (not exhaustively re-verified beyond the `estimate` grep in
   (b) — flagged as an open item in (j), worth a dedicated route grep).
4. **PDF/export.** Missing in both repos. Not started anywhere.
5. **Doc drift fix.** `codey_estimator_schema.md` needs its `property_id`
   and `estimate_line_items` pricing-FK sections corrected to match current
   `database.py` (Mismatches #1 and #2 above) — pure documentation debt, no
   code change required.
6. **Data migration: none needed.** Confirmed independently (both by the
   reference repo's own HEAD commit message and by this census's direct
   dump) — every estimator and pricing/retailer table is empty in the live
   DB copy. There is no data to migrate; "integration" here is 100% a code
   question, not a data-migration question.
7. **Tests for the dormant modules' integration.** `tests/test_pricing_repo.py`
   exists and covers `pricing_repo.py`/`pricing_job_service.py`'s current
   (job-lifecycle-only) scope; no test exists exercising `catalog.matcher`
   or `retailers.*` from inside Codey-OS, because nothing calls them yet —
   test coverage would follow from doing (1)/(2), not precede it.

**Definition of done** for "integration fully proven" (synthesizing the
directive's framing): the vendored library's calc/dto/errors/units/money
path is already there (reachable, tested via
`test_restoricon_core/test_b9_2_estimate_service.py` and siblings). Full
proof requires, at minimum: (1) a real caller for `catalog.matcher` and
`retailers.*` with its own reviewed/tested service, (2) a live-verify cycle
once that caller exists (code-complete isn't live-verified per rule 7), and
(3) the schema-doc corrections in (f).5. Until (1) exists, declaring the
estimator "fully integrated" would overclaim — the calculation/estimate
lifecycle is integrated; the pricing-sourcing side (the actual reason the 12
pricing/retailer tables and `catalog`/`retailers` modules exist) is not.

## (g) Branch anomaly assessment

`Codey-Estimator-reference` has no `main` branch; `origin/HEAD` points at
`claude/epic-archimedes-z3luuu`, and the local clone is a **shallow clone**
pinned to a single commit, `df0730f` (`.git/shallow` contains exactly that
one hash; `git log --oneline` / `git log --all --oneline` both show exactly
1 commit reachable from this checkout).

This is **not evidence of unfinished/unpromoted work** — it's an artifact of
how the clone was made. `NEW_ISSUES.md:18426` directly documents the intent:
Ish decided to clone `github.com/Ishabdullah/Codey-Estimator` into
`~/Codey-Estimator-reference` specifically **as a read-only source
reference** for vendoring, not as a working checkout of the project's
ongoing branch structure. A shallow single-commit clone of a feature branch
is exactly what you'd get from `git clone --depth 1 -b
claude/epic-archimedes-z3luuu ...` — consistent with "get me the latest
state of this branch to vendor from," not "give me its dev history."

Given the shallow clone, this census **cannot** determine from the local
checkout alone whether `claude/epic-archimedes-z3luuu` was ever intended to
be merged to a `main` that doesn't exist, or whether the reference repo's
own development model simply never uses `main` (e.g., an agent-authored repo
where every unit of work is its own long-lived branch, never squash-merged).
The one visible commit's message ("Record §21 DB check result: estimates
table is empty, no migration needed") reads as a documentation/verification
commit, not a feature commit — consistent with the branch being
past-feature-complete and in a "recording findings" phase at the point this
clone was taken, but this is inferred from one commit message, not verified
against the branch's fuller history (which this clone doesn't have).

**Recommendation:** if the branch anomaly itself needs resolving (vs. just
explained), that requires a non-shallow clone or direct repo access (e.g.
`gh api` against `Ishabdullah/Codey-Estimator`) to see whether `main` exists
upstream and was simply never fetched, or whether it genuinely doesn't
exist on the remote. That network check is outside this census's read-only,
local-filesystem scope and is logged as an open question in (j).

## (h) Recommended canonical path

- **Canonical source of truth for the calc/catalog/parsing library:**
  `Codey-Estimator-reference` (the standalone repo), per the existing
  directive and the `codey_estimator/__init__.py` provenance docstring's own
  instruction ("fix it upstream ... and re-vendor"). This census found
  nothing to contradict that policy — the vendored copy is verbatim, unedited,
  and the in-repo consumer code (`estimate_service.py`, `pricing_repo.py`)
  only touches the 7 modules it actually needs.
- **Canonical location for the service/API/persistence layer:**
  `Codey-OS/restoricon_core/` — this has no counterpart in the reference
  repo at all (it's out of that repo's scope by design), so there's no
  duplication question here, only a completeness question (see (f)).
- **No merge is needed or implied.** The two repos serve different, already
  well-separated roles: one is a pure calculation library (versioned,
  vendored, re-vendor-on-upstream-change), the other is the live
  service/API built on top of it. The open work is entirely in (f) — wiring
  the already-vendored `catalog`/`retailers` modules to a real caller — not
  in reconciling two implementations of the same thing.
- **Action to take:** fix the two doc mismatches in (d) (low cost, pure
  documentation), and treat (f)'s items 1-3 as the next concrete Phase B9.x+
  scope when pricing/retailer sourcing work is prioritized. No code existing
  today needs to be deleted, replaced, or deduplicated.

## (i) DORMANT findings summary

- `codey_estimator/catalog/*.py` (6 files: `__init__`, `keys`, `matcher`,
  `normalizer`, `package`, `schema`, `text`) — vendored, zero callers in
  Codey-OS. DORMANT.
- `codey_estimator/retailers/*.py` (5 files: `__init__`, `base`,
  `csv_import`, `manual`, `parsing`) — vendored, zero callers in Codey-OS.
  DORMANT.
- `Codey-Estimator-reference` as a standalone, independently-runnable
  system — DORMANT from Codey-OS's perspective (and, per its own HEAD
  commit, DORMANT in the sense that its own `estimates`-adjacent concept was
  never exercised against real data either — though that repo has no DB
  code of its own, so "DORMANT" there just means "never deployed/run against
  anything live," consistent with it being a pure library).
- All 12 pricing/retailer DB tables (`canonical_materials`, `labor_rates`,
  `labor_rate_history`, `price_book_items`, `price_observations`,
  `pricing_jobs`, `material_matches`, `retailers`, `retailer_products`,
  `retailer_stores`, `package_options`, `search_cache`,
  `product_search_fts*`) — schema-complete, empty, and (except `pricing_jobs`
  via its thin lifecycle service) have no write path in current code. This
  matches the DORMANT module findings above — same root cause, same scope.

## (j) Open questions

1. Does `github.com/Ishabdullah/Codey-Estimator` have a `main` branch on the
   actual remote (not this local shallow clone)? This census's read-only,
   no-network-call scope couldn't check; would need `gh api` or a full
   unshallow fetch.
2. Is there a dedicated route in `restoricon_core/api/routes.py` for
   triggering pricing jobs or managing retailers/canonical materials? This
   pass's `grep` was scoped to "estimate"-named routes per the task's
   primary subject; a dedicated grep for `/api/v1/pricing` / `/api/v1/
   retailers` / `/api/v1/materials` paths was not run and should be, before
   finalizing (f) item 3's claim.
3. `labor_rate_history`, `search_cache`, `product_search_fts*` were reported
   empty in the task's "already established" context but were not
   independently re-dumped by this census (time-boxed to the
   estimator-schema-critical tables). Worth a follow-up direct dump if the
   blueprint needs those three fully reconciled too.
4. Is there an intended consumer for `codey_estimator.catalog.matcher` and
   `retailers.*` already scoped in `codey_estimator_service.md` (the B9.2+
   service-layer doc) that simply hasn't been implemented yet, vs. never
   planned? `codey_estimator_service.md` was not read in full for this
   census (only grepped) — worth a dedicated read to see if the
   matching/ingestion pipeline is already specced (would change (f) from
   "design + implement" to "implement against existing spec").
