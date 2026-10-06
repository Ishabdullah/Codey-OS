# C1 — Repo lineage & branch reconciliation (coordinator's own work)

Verified 2026-10-06. All facts from `git` output, not docs.

## Private-Codey-Agent vs private-agent — RESOLVED

**Verdict: `Private-Codey-Agent` is canonical. `private-agent` is a pure ancestor
with zero unique content and can be retired (proposal only, not executed).**

Evidence:
- Shared root commits (`7f02f8d initia`, `cf0b8b8 initial`, `5564cba app logo added`)
  — same lineage, not independent trees.
- Commit counts: `Private-Codey-Agent` 66, `private-agent` 63.
- `Private-Codey-Agent` has `origin` =
  `github.com/Ishabdullah/Private-Codey-Agent.git`, `upstream` =
  `github.com/Ishabdullah/private-agent.git`. So the fork direction is
  private-agent → Private-Codey-Agent, matching directive §3's stated lineage.
- `git log main..upstream/main` → **empty**. private-agent has nothing
  Private-Codey-Agent lacks. Strict superset, no divergence, no merge needed.
- `comm -13` on tracked-file sets → **empty**. No file exists only in private-agent.

The 3 commits unique to `Private-Codey-Agent` are precisely the Codey-OS
integration work (the "hands"/actuator layer):

| Commit | Content |
|---|---|
| `d24df11` | `feat(bridge): add loopback DeviceBridgeClientService and ThirdPartyAppAutomationService` |
| `907e5a3` | `feat(dashboard): add business dashboard screen and RestoriconApiClient for Phase B4` |
| `efe9a1c` | `feat(navigation): wire Business Dashboard into AppBar and drawer navigation` |

4 files exist only in `Private-Codey-Agent`:
- `lib/services/device_bridge_client_service.dart` — loopback bridge to Codey-OS
- `lib/services/third_party_app_automation_service.dart` — device actuation
- `lib/services/restoricon_api_client.dart` — Restoricon API consumer
- `lib/screens/business_dashboard_screen.dart` — Phase B4 dashboard

**Blueprint consequence:** the actuator integration surface is exactly these
4 files + the loopback bridge contract on the Codey-OS side. Last touched
2026-08-30 — ~5 weeks stale relative to Codey-OS `main` (2026-10-06), so the
API contract it consumes must be re-verified against the current Core API.

## Codey-OS branch state

- `main` @ `405d9cf` (2026-10-06)
- `codey-os-dev-v2` @ `97ad62d` — diverged: main is **4 ahead**, dev-v2 is **2 ahead**.
- Commits stranded on `codey-os-dev-v2` only:
  - `8d1c37e` Stage 0 kickoff: commit handoff + approved execution plan (docs only)
  - `97ad62d` S0.1: full-fidelity trajectories, export hygiene, bench grade() fix
- Rollback tags on Codey-OS: `rollback/2026-09-30-pre-agi-audit-fixes`,
  `rollback/2026-09-30-pre-agi-merge`, `rollback/2026-09-30-pre-dev-v2`.

**Blueprint consequence:** `97ad62d` is substantive Stage-0 measurement work
(trajectory fidelity + a bench `grade()` fix) that never reached main. Directive
§13 S0 depends on exactly this. Needs a reconcile decision: cherry-pick,
re-implement, or supersede. Census A4 is diffing `bench/` to determine which.

## Codey-Estimator-reference

- No `main` branch at all. `origin/HEAD` → `claude/epic-archimedes-z3luuu`.
- HEAD `df0730f` (2026-09-27) "Record §21 DB check result: estimates table is
  empty, no migration needed".
- Named `-reference` on disk, while directive §3 names it `Codey-Estimator`.
  Directory name differs from the directive's repo name — record as-is.

## Repos named in directive §3 but ABSENT locally

- `Codey` (lineage root)
- `Codey-v2` (lineage middle)
- `Aigentik-CLI` (ancestor of Codey-Aigentik)

Recorded as absent. Not reconstructed. `Codey-Aigentik` does carry an `upstream`
remote, so its fork ancestry is recoverable from the remote if ever needed.

## Codey-Aigentik

- HEAD `e76f1f0` (2026-09-15); tags `v1.0.0`, `v1.0.1`, `v1.0.2`, `v1.1.0`.
- Has `upstream/main` — fork of the Aigentik-CLI product, matching §3.
- Single branch `main`. No stranded branches.

## OpenCL-S24-Ultra

- HEAD `6f766c0` (2026-10-05) — the most recently active repo besides Codey-OS.
- Single branch `main`, tag `v0.1.0`.
- 360 tracked files: 231 `.json`, 35 `.py`, 19 `.csv`, 16 `.sh`, 14 `.cpp`, 8 `.patch`.
  The json/csv mass is benchmark result data — relevant to NPU gate evidence.

## restoricon (static site repo)

- HEAD `73eee40` (2026-09-20); 105 files, 54 `.jpg` / 16 `.html` / 6 `.js`.
- This is a **marketing website**, not the business data system. The production
  business data lives in `~/.codeyOS/restoricon.db` (inside Codey-OS's state dir).
  Directive §5's "live production" protection therefore applies primarily to that
  SQLite store and the Core API over it — not to this repo.
