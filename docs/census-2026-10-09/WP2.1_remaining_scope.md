# WP2.1 remaining scope — provisional source census, 2026-10-09

This is a work inventory, not evidence that WP2.1 is complete. The architect
prepared it after slices 15/16, coordinated against `639f18f` before slice 17.
The scan did not retain HEAD/file hashes; this is not a cryptographically pinned
snapshot. Candidate line numbers describe that scan and can move in later slices.
The blueprint §21 remains the work register; the findings ledger owns issue status.

The source-only AST inventory searched 201 non-test Python files across `core/`,
`tools/`, `ccos/`, `restoricon_core/`, `utils/`, `pipeline/`, and `main.py`, with
zero parse failures. It retained 1,384 candidate calls in 122 files, including
string replacement, dictionary access, SQL reads and other false positives.
Coordinator independently compared the searched-path list against these roots:
201 files, no missing paths, no candidate paths outside that list. This verifies
file-list scope, not runtime reachability or side-effect coverage.

- `searched_files.tsv` lists every searched relative path.
- `candidate_calls.tsv` retains file, line, enclosing scope and callee. Every row
  starts as an unresolved candidate; none is an exemption or a verified bypass.
- Source expressions were retained in the temporary supporting JSON at
  `/data/data/com.termux/files/usr/tmp/codey-wp21-remaining-census.json`.
  No standalone scanner was retained. Future rescans must record their rules,
  source revision, dirty paths and file hashes; the counts alone are not a
  reproducible coverage proof.

Tests, `test.py`, `test_*`, and `demo_*` were excluded. Shell, JavaScript, native
code, sibling repositories, generated source, dynamic import/getattr, and arbitrary
executable contents require separate closure. Do not infer exemption from absence
in this inventory. The old four-of-42 write-primitive counter measures neither
all side effects nor overall WP2.1 progress.

## Actual boundary gaps and unresolved candidates

| Category | Current source evidence and remaining work |
|---|---|
| Shell | `tools/shell_tools.py::shell` is gated. Slice 17 covers human/daemon refusal accounting. Slice 18 covers direct `git push`/`git-push` and recognized global-prefix publishing as HIGH_IMPACT (NEW-873 subset). Slice 19 covers send-pack/http-push and standalone forms (NEW-876). Slice 20 makes unknown effective Git operations and all git-* executables HIGH, conservatively including unreviewed standard operations. Slice 21 makes every direct git/git-* invocation HIGH, including reads/help/queries, with headless shell Git now refused. Slice 22 makes find/xargs and argument-bearing env HIGH; bare parsed env READ. Broader wrappers/scripts/opaque effects NEW-875 remain open; Slice 23 fixes dedicated search_files NEW-878 with literal in-process READ basename traversal, static audit and truthful failed outcomes (matching/deadline/race limits disclosed). Slice 24 selects absolute installation Git for all 28 dedicated calls, preventing initial PATH substitution for current trusted-kwargs callers; installation integrity assumed, no sandbox/immutable proof. Slice 25 adds controlled ambient child environments across complete local/scoped commit and checkpoint Git sequences: metadata retained, fixed installation PATH/C locale/system-config exclusion, other injection/redirect/execution controls removed. Repository/global config/hooks/secondary helpers, other calls' ambient environment and query mediation/fidelity NEW-877 remain open. Slice 26 fixes scoped filename/pathspec interpretation NEW-879 with literal flags across status/stage/diff/commit and four public-status ambient mode keys removed in a child copy; directories remain intentional subtrees and public empty status unrestricted. Real temp prior overscope/fixed mechanics verified, no containment guarantee. Slice 27 isolates scoped commit and nonempty checkpoint config/administration: positive data settings, native conversions, effective filters rejected, unsupported layouts explicit, owned HEAD lock/detached publication, checked-error plus cleanup accounting. 96 new cases / 675 tests; partial effects possible, no atomicity or hostile-concurrency guarantee. Slice 28 migrates broad commits: whole-root add-all versus staged-only existing blobs, bounded ordinary merge/squash continuation, observed parent/effect checks and guarded metadata cleanup, detached publication despite later metadata failures. 84 new cases / 759 tests; clean pending merge no-op fixed with actual helper red→green. Partial effects/unsupported states explicit. Queries/no-path checkpoint/other helper configuration remain NEW-877 open. `_execute_shell_command` ignores return codes and returns caught failures normally (NEW-874). Arbitrary executable contents and command options need classification closure. |
| CCOS | `PluginManager.call_capability` has direct-handler, HTTP and in-process dispatch; `execute` directly invokes plugin functions. They have no gateway boundary. Callers include agent/daemon, CRM tools, planner/lifecycle, dashboard and API panels. Low traffic is not measured evidence or an exemption. |
| Manifest enforcement | `permissions` and `resource_limits` are metadata. Dispatch must enforce both, including generated `pm.call_capability` calls. A gate inside that method covers generated calls to it; correct NEW-839's hypothetical framing when implemented. |
| Device/messages | `TermuxAPI.execute`, extended `_run`, and DeviceBridge handlers can actuate devices without gateway mediation. SMS/calls/settings/downloads need operation classification. Missing default handlers do not cover real registered handlers. |
| Business DB | API/service/auth mutation SQL has no gateway boundary. `DatabaseManager.transaction` is atomicity, not authority. Classify complete operations: ordinary CRUD ACT; security, important deletion and monetary actions HIGH_IMPACT. Preserve RBAC and transaction context. |
| Notifications | `NotificationService._post_request` sends email/invite/cancellation without gateway mediation; project updates, compose and estimate delivery reach it. Existing auth/audit/DNC checks remain required. Ordinary message sending is ACT, public publishing HIGH_IMPACT. |
| HTTP/IPC | Remote CCOS dispatch, CRM GET, cloud inference/planning, local inference/embedding/health/tokenization, daemon/device sockets require classification. Trusted local protocol differs from publishing/remote egress; record evidence for any mechanism exclusion. |
| User-facing files | `/ignore`, `run_init`/`write_codeymd`, session save/delete, task queue/config, voice configuration, generated design notes, document uploads, KB/export/model artifacts remain candidates. Gated tool wrappers do not cover direct callers. |
| Checkpoints | Creation is reachable from filesystem self-modification; backup copies/database writes and independent prune need complete-operation coverage. Git attempt and rollback are gated. NEW-863 identity and NEW-810/871/872 recovery limitations remain. |
| Internal persistence | State/memory/symbolic graph/trajectory/resource coordination/telemetry writes need caller tracing and an explicit trusted-mechanism contract where appropriate. Gateway audit persistence must avoid recursive mediation. |
| Lifecycle/admin | Loader/embed/daemon/plugin-supervisor PID/log/process effects and recovery/test runners remain candidates. Human-only setup/backup scripts need caller evidence; administrative naming does not exempt destruction. |
| Self-improvement | Optimizer promotion and recombiner generation write executable artifacts. Gateway mediation must preserve the independent promotion gate and default-off operator switch. |
| Imports/trust/cache | NEW-855 eager state initialization remains. Notes gateway coverage does not fix prompt trust or NEW-857/858/859 integrity/cache. NEW-844 is attempted execution followed by bookkeeping failure, not refusal. |

## Remaining dependency order (updated after slice 28)

These are **14 work groups plus closure**, not 14 promised slices. Each group
must be split into bounded, architect-scoped slices before implementation.
Exact remaining slice count is unknown and can grow with findings.

1. Remaining shell classification and publishing-policy bypasses (NEW-875; direct push/send-pack/http-push families covered). Direct shell Git and find/xargs/argument-bearing env covered; dedicated search_files NEW-878 fixed; dedicated Git initial executable selection covered; commit environment prerequisite covered; literal scoped operands NEW-879 covered; scoped and broad commit configuration contracts covered with explicit limits; dedicated query READ/fidelity next, then remaining Git mutation contracts (NEW-877) → remaining wrappers/embedded execution → security/destructive modes → Codey target writes → opaque-effect enforcement.
2. Shell execution-error fidelity.
3. Import/state isolation foundation.
4. CCOS dispatch and permissions.
5. Capability resource enforcement.
6. Device boundaries.
7. Business mutation boundaries.
8. Notification boundary.
9. Remaining HTTP/egress.
10. User-facing filesystem operations.
11. Checkpoint/backups/pruning.
12. Internal persistence.
13. Lifecycle/admin operations.
14. Self-improvement artifact boundaries.
15. Final closure census and adversarial verification.

Work proceeds one slice at a time: architect → implementer/test → independent
review → coordinator checks/records → commit/push → next slice. User authorized
continuous completion and publication on 2026-10-09. Verification uses isolated
temporary state; no live-store mutation, real recipient send, model load or peer
execution is implied. Full suite remains excluded for NEW-791; unavailable type
checkers and baseline lint debt must be disclosed.

## Closure requirements

Every real destructive/action boundary needs an enforced authority decision and
truthful audit. Map candidates to actual callers and dispositions with evidence;
retain uncertain reachability as open. Close direct and generated bypasses,
callback-free HIGH_IMPACT authorization, refusal/error accounting, imports,
manifest permissions/resource limits and external data egress. Validate real
mechanics only in disposable fixtures, distinguishing partial effects from refusal.
Do not mark closure on candidate counts, mocked dispatch alone, or silent policy
exceptions. RBAC credentials are not human confirmation. New unattended spending,
security or promotion-policy exceptions require user direction; settled authority
rules and routine implementation decisions do not.
