# WP2.1 group 13 scope — Lifecycle/admin operations

Architect handoff, 2026-10-15. Source inspection, not live-service validation.
This report owns no finding IDs or completion status; blueprint WP2.1 and
NEW_ISSUES.md remain authoritative. Coordinator accepted sequential slices
13a, 13b, 13c.1, 13c.2. Mandatory reviewer approval before every commit;
process changes also need disposable-process live verification. No model loads,
live-store mutations, service restart or existing-process kill is implied.

## 13a — Recovery/fix/TDD execution

Actual direct boundaries: core/fixmode.py run_and_capture (CLI --fix),
core/tdd.py run_tests (CLI --tdd), and core/recovery.py execute_strategy.
main.py currently passes yolo=True into fix_file. Recovery's CCOS wrapper
exists, but coding.recovery_execute_strategy is absent from the core authority
table: ordinary call_capability already refuses it. Its core callable gap is
not a demonstrated live CCOS exploit.

Gate complete run_and_capture/run_tests execution, preserving result contracts.
Current shell policy ordinarily classifies Python/pytest ACT; opaque contents
remain NEW-904, not a newly resolved HIGH policy. Preserve truthful nonzero,
timeout and refusal distinctions. Refusal must abort dependent fix/TDD work,
not masquerade as a failing test and provoke more edits. Recovery actions:
package installation HIGH_IMPACT with actual confirmation/default refusal;
search/which READ; ordinary mkdir ACT with established self-modification/path
authority; pytest follows existing shell classification. Never audit normal
returned failure strings as success. Add no recovery capability entries/callers.

Tests: refused subprocess never called; nonzero/timeout outcomes; preserved
successful output; fix/TDD refusal abort; recovery classifications; install
headless refusal; temporary-path behavior. Disposable marker-writing Python
fixture can verify execution and audit without running project tests/models.

## 13b — Owned Popen supervision and truthful results

ccos/core/plugin_manager.py ProcessSupervisor start/stop has real ownership
and outcome defects: duplicate start overwrites a tracked child; pid-file
write failure can return False after spawn; stop pops tracking early, trusts
integer pid-file fallback, signals before polling, suppresses errors, removes
records and always returns True. PluginManager.unload ignores stop failure.
NEW-916 already records immediately failing children marked ACTIVE.

Reachable: core/dashboard_data.py lazily invokes load_all, including external
plugin stubs. Do not call the complete mechanism dormant.

Use retained owned Popen handles for signaling; never signal solely from a
pid-file integer. Poll before signaling and reap children. Duplicate live
start must not spawn/overwrite. Failed post-spawn setup must stop/reap that
exact child or retain its handle and report incomplete cleanup. Observe early
exit and configured health failure rather than reporting ACTIVE. Keep waits
bounded. Retain ownership until confirmed exit; preserve tracking on failure.
Remove only the associated unchanged PID record. unload must propagate stop
failure without unregistering capabilities or discarding module/plugin state.

Tests plus real fixtures: duplicate start, exited handle, forged PID record
pointing to independently fixture-owned child, malformed record, setup-write
failure, stop failure, health failure, replaced record, unload failure. Always
finally-cleanup exact fixture Popen handles. No real plugins/services.

## 13c.1 — Shared durable process identity

Implement lightweight stdlib-only core/process_identity.py or equivalent,
usable from shell with no config/state/model imports. Preserve integer .pid
files for compatibility, add <pid_file>.identity JSON with exactly version,
service, pid, boot_id, start_ticks, uid. Capture only launcher-spawned processes
or current daemon self-publication. boot_id comes from proc boot_id; start_ticks
from /proc/PID/stat field 22 (parse after final closing parenthesis); UID from
/proc/PID/status. Reject PID <=1, bool/noninteger/overflow, malformed/missing
fields, inconsistent .pid, symlink records and unverifiable identity. Compare
boot/start/UID immediately before every signal, including escalation/reload.
Original zombie/exited process is stopped, not a replacement to signal.

Atomic temp-and-replace publication and compare-before-cleanup under stable
per-service .lifecycle.lock; deletion must preserve replaced records. Expose
record/inspect/signal-stop/cleanup internal operations with distinct running,
absent-dead and unsafe-unverifiable results. Unsafe blocks stop AND duplicate
startup. No argv recording (Cloudflare argv has a secret).

Legacy live integer-only records fail closed, remain visible and block duplicate
spawn. Do not adopt by basename/cwd. Confirmed dead legacy records may be retired
under lock; ambiguous/malformed records remain unresolved. New records support
legitimate cross-process stop/restart. These are stale/reuse defenses, not
protection from an account able to forge its own state directory.

Environment probe: pidfd_open False; pidfd_send_signal False. Immediate identity
rechecks narrow but do not remove kernel check-to-signal PID-reuse races. Do not
claim pidfd semantics or add ctypes/syscall machinery in this bounded slice.

Migrate Python writers: core/daemon.py check_pid_file/write_pid_file/
remove_pid_file (retain own-PID exception for shell prewrite), and
core/loader_v2.py spawned llama PID publication around 807 and removal around
940. Preserve existing owned-child termination mechanics. Review lock ordering:
never hold a lock while waiting on a component requiring it.

## 13c.2 — Shell consumers and complete lifecycle fidelity

Files: lib/service_manager.sh, codeydOS, necessary dispatcher propagation in
codey/codey-start/codey-stop. Shared records: codeyOS.pid, restoricon-api.pid,
aigentik.pid, litestream.pid, cloudflared.pid, backup-docs.pid. codeydOS also
consumes llama-server-8080.pid. codeydOS must honor CODEY_STATE_DIR.

Replace raw integer kill trust in shared helpers, daemon start/status/stop/
reload and kill_llama_server_gracefully. Serialize complete per-service starts
and stops with lifecycle locks; preserve Aigentik child FD-close protection
and extend to new locks. Publish identity for every spawned child before
success. Publication failure cannot claim success or erase a replacement.
Unsafe records must not fall through boolean-false into duplicate startup.
Stop succeeds only after original-process exit; failed signal/unconfirmed
termination/identity change returns nonzero and preserves evidence. Remove
codeydOS stop's failure suppression; restart must not start after failed stop.
Composite stop attempts all services, aggregates failures and reports all
stopped only when true.

Aigentik/Litestream/document-backup orphan paths currently kill fresh cwd+
entrypoint matches. Those lack recorded spawn provenance: scans become
diagnostic-only unless a candidate has matching persisted ownership identity.
Do not kill untracked matches or automatically duplicate them. Preserve
existing cwd/runtime/token matching accuracy for diagnostics. This follows
Rule 3, not a blanket permission to terminate newly discovered processes.

Do not change log paths/contents, backup policy, tunnel secrets, inference
ports, or API bind/auth. Record publication must not truncate logs.

Fixtures: cross-shell record/stop; bad/0/negative/malformed PIDs; wrong boot/
start/UID; missing sidecar; separate fixture child survives forged/stale PID;
replaced records survive; ignored TERM -> verified KILL -> exit; failed signal;
concurrent start/stop and duplicate starts; shell prewrite plus daemon self
publication; validated reload; legacy live blocks start/stop; all orphan paths
preserve unowned processes; composite failure propagation. Temp state roots
and fake service/interpreter fixtures only, exact-handle finally cleanup.

## Narrow mechanism contracts and retained residuals

Default PluginManager bootstrap scans only installed repo ccos/plugins (two
levels). Production callers load agent, crm_core_query, or dashboard load_all.
Custom plugin_dirs is constructor configuration; no live install/upload/
activation endpoint was found. Established bootstrap import of protected
installed repository code can be treated like normal Codey imports, without
new policy fork. This does NOT exempt arbitrary custom roots, runtime-generated
plugins, replaced manifests/executables or arbitrary PluginManager.execute.
Generated/new artifact activation belongs to group 14 promotion/authority.

Model/embed automatic startup/shutdown and daemon watchdog/resource release
are subordinate mechanisms only under explicit fixed-executable/ownership/
resource contracts; not whole-module exemptions. Daemon socket is chmod 0600,
but submission/cancel/config independent command boundaries stay unresolved
with NEW-939. Sandbox shell=True execution belongs to group14 optimizer/
recombiner boundaries. Flake8/mypy plugin/config execution is not universally
harmless READ; retain for final census. Installed admin/service entrypoints do
not exempt destructive PID helpers. Operator-configured API host defaults
loopback; changing binding/auth is distinct from ordinary service bootstrap.

NEW-939 CLI/config/taskqueue/design/KB/export/model-artifact residuals, opaque
script policy NEW-904, and arbitrary PluginManager.execute remain explicit
final-census follow-ups. No whole-repo closure claim follows from these slices.
