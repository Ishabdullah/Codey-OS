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
| Shell | `tools/shell_tools.py::shell` is gated. Slice 17 addresses human/daemon refusal accounting. Plain `git push` is ACT despite HIGH_IMPACT dedicated publishing policy (NEW-873). `_execute_shell_command` ignores return codes and returns caught failures normally (NEW-874). Arbitrary executable contents and command options need classification closure. |
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

## Dependency order after slice 17

These are **14 work groups plus closure**, not 14 promised slices. Each group
must be split into bounded, architect-scoped slices before implementation.
Exact remaining slice count is unknown and can grow with findings.

1. Shell classification and helper-policy bypasses.
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
