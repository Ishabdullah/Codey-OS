# WP2.1 group 13 scope — Lifecycle/admin operations

Architect handoff, 2026-10-15. Source inspection, not live-service validation.
This report owns no finding IDs or completion status; blueprint WP2.1 and
NEW_ISSUES.md remain authoritative. Coordinator accepted sequential slices
13a, 13b, 13c.1, 13c.2, then 13d (authority/audit envelope). Mandatory reviewer approval before every commit;
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


## Authority clarification — ownership is not an audit decision

13b fixes supervisor ownership/fidelity, not an independent policy boundary.
start/stop_external_plugin are subordinate to installed PluginManager bootstrap
or a separately authorized activation operation. PID writers/removers are
subordinate bookkeeping and must not acquire gateway confirmation of their own.
Installed-code bootstrap's narrow contract above is supported by actual callers;
there is no identified production agent capability choosing arbitrary plugin
load/unload. Arbitrary execute/custom/generated activation remains unresolved.

Explicit operator invocation of codey/codeydOS supplies an instruction but does
not create a WP2.1 audit record. The standalone shell lifecycle paths therefore
have a real complete-operation audit gap. An agent's invocation through shell()
has an outer command audit; that does not close standalone invocation coverage.
13c identity validation alone must not be described as closing this gap.

## 13d — Shell complete-operation gateway/audit envelope

Implement after 13c.2, or integrate only if its separate review scope stays
clear. Ordinary configured service start/stop/reload/restart/bootstrap is ACT;
use existing ACT behavior (no invented headless refusal). Explicit entrypoint
invocation is the instruction; do not add a second human prompt. READ operations
are status/logs/config display; codeydOS config creates a default config and is
ACT, separately identified from config display. No security/binding/auth editing
is authorized by those classifications. Existing unresolved arbitrary config
mutation remains NEW-939, not grandfathered by this slice.

Use one Python gateway wrapper (e.g. core/service_actions.py) with a core-owned
finite operation map. It selects authority, action label and a fixed private
shell mechanics callback, invokes ActionGateway.gate_exec, and translates the
result to the caller's exit status. Operations: all-start, all-stop, all-restart,
bootstrap; daemon-start/stop/restart/reload; all-status, daemon-status, logs,
config-show, daemon-config-create. Reject unknown operations before execution;
never accept arbitrary shell command/function text from argv as a mapped action.

Refactor public shell dispatch into thin entrypoints calling this wrapper.
Mechanics live in sourced libraries with no top-level command dispatch; existing
functions can become private mechanics rather than re-entering public commands.
For example, split codeydOS daemon mechanics into lib/daemon_manager.sh so the
all-services callback calls private daemon functions, not public codeydOS and a
second gateway. There must be no public --internal option, environment variable,
caller-supplied approval token or audit-disable flag. Private sourced mechanics
are not a new public command/API; arbitrary code access is the already-disclosed
opaque-script boundary, not an authentication property of function naming.

The Python callback runs the mapped mechanics in a child bash using an argv
list. A static bash fragment may source a fixed library and invoke a mapped
function, passing data as positional arguments; do not interpolate caller text
into shell source. Preserve existing repo-root selection, ambient PATH,
CODEY_STATE_DIR, CODEY_DIR/PYTHONPATH propagation and quoted original arguments.
Do not print or audit config values/tunnel tokens or full environment. Labels
contain operation/service names only. Use inherited stdin/stdout/stderr rather
than capture/reprint: current output, streaming and terminal behavior must stay
intact. Close internal FDs in children so lifecycle locks cannot be inherited.
The wrapper must not hold lifecycle locks while starting its mechanics child.

Bootstrap audits only the service-start phase; after successful return, the
public shell execs codeyOS with original argv as before. The gateway callback
must not swallow the TUI's entire interactive lifetime or alter its exit/signal
behavior. Codey default/flag passthrough, codey-start, and codey start-with-prompt
share this rule. Restart uses one callback (stop then start); failed stop must
prevent start. Reuse private mechanics to avoid nested operation audits.

Nonzero child exit is a FAILED audit (raise inside callback); preserve the actual
exit code at the public entrypoint. Refusal never executes mechanics. Exceptions
before spawn, launch failure and interruptions must not emit ALLOWED. Successful
zero-exit mechanics returns a normal callback result. Audit failure remains the
gateway's established best-effort behavior; do not introduce recursive audit or
turn failed persistence into permission to run an otherwise-refused operation.

Partial operations are not refusals or atomic rollback: preserve per-service
success/failure output from 13c.2, aggregate return status, and include the actual
exit code plus an explicit partial-effects-possible statement in the FAILED
reason for composite operations. Do not claim no effects merely because a later
phase failed. Successful composite summaries require all phases successful.
No new machine-readable stdout framing or secret-bearing argv capture is needed.

Tests: each public entrypoint reaches its mapped authority/action exactly once;
all-service calls do not re-enter daemon wrapper; restart failure prevents start;
partial start/stop emits FAILED while preserving earlier fixture markers/output;
nonzero rc survives; status/log/config display READ; config-create ACT; unknown
operation rejected; refusal no subprocess; environment --internal-like values
cannot suppress gateway; bash positional args preserve spaces/metacharacters;
state/PATH/env and output streams retained; bootstrap audits before TUI exec and
preserves TUI args/exit code; lifecycle FD locks released in children. Test
fixtures use disposable fake services/temp state, never real services/models.
Real subprocess smoke verification should cover one successful and one partially
failed composite, plus bootstrap with fake TUI. Mandatory adversarial review.

No product-direction fork is required: this adds ACT/READ decision and outcome
coverage under existing policy. It does not resolve opaque executable contents,
new plugin activation, API security-setting changes or arbitrary config writes.


## Compatibility amendment — codeyOS client and bootstrap environment

Actual codeyOS read in full: DAEMON_DIR is hardcoded to $HOME/.codeyOS;
is_daemon_running reads integer PID, kill -0 probes, then checks the Unix socket.
This client is an affected consumer, not an unrelated protocol redesign.
Include codeyOS in 13c.2: derive DAEMON_DIR from CODEY_STATE_DIR with existing
home fallback; PID_FILE, SOCKET_FILE, mktemp paths and displayed state DB must
all follow that selected root. Replace integer kill probing with the shared
identity inspector. Only verified-running plus an existing Unix socket counts
as a usable daemon. Unsafe/unverifiable/legacy-live identity must produce a
distinct diagnostic; never represent it as verified or silently connect. Direct
interactive mode already bypasses daemon routing and should remain available;
status/task/cancel/background paths refuse unavailable/unverified daemon use.
Do not rewrite task payload, socket framing, timeout or prompt semantics here.
Tests use temp state roots, fake identity-helper outcomes and disposable Unix
socket fixtures: honor override, default fallback, wrong/legacy identity does
not connect, valid identity plus socket connects, direct mode stays direct.

Separate discovered residual: codeyOS generates Python source by interpolating
prompt/task IDs and paths, and several paths lose the Python exit code after
rm. These are outside narrow identity/root migration, must be logged by the
coordinator and retained for final census rather than silently rewritten here.
No claim of secure task serialization follows from identity validation.

13d's gateway child cannot export environment back into its parent. The current
start_restoricon exports repo-prefixed PYTHONPATH; start_litestream may export
GOOGLE_APPLICATION_CREDENTIALS from the existing configured credentials file.
Those exports formerly reached the TUI when its launcher sourced mechanics.
Moving service execution into a child must not accidentally drop them.

Add a small parent-side bootstrap environment preparation function, sourced by
the public entrypoint before its final codeyOS exec, after successful gated
service startup. It only sets required environment; it starts/stops nothing:
set/export CODEY_DIR consistently with existing entrypoints; prepend the repo
root to PYTHONPATH without duplicating an existing leading repo entry; choose
GOOGLE_APPLICATION_CREDENTIALS using the same existing Litestream credential
path/precedence (existing $HOME/.codeyOS/gcp_credentials.json takes precedence,
otherwise preserve an inherited configured value). Keep the child-side exports
needed for service startup. This is direct parent environment setup, not an
opaque eval of child output or a second lifecycle action. Default credential
paths are unchanged by the state-root fix unless separately scoped; this slice
must not silently relocate GCP configuration.

Do not return environment through stdout, audit payloads, eval/export snippets,
or temporary credential files. No credential contents are needed: only the
existing path. Prepare only entrypoints that will launch the TUI (codey default,
flag/prompt passthrough, codey start-with-prompt, codey-start); explicit service
commands do not need parent environment propagation. Preserve original TUI argv,
exit/signal behavior, PATH and incoming unrelated environment. No inherited
variable may suppress the gateway. Tests with a fake TUI assert PYTHONPATH and
credential-path precedence, inspect captured stdout/audit for absence of a fake
credential marker, and prove failed bootstrap never launches the fake TUI.

This is implementation compatibility, not a new product-direction fork.


## 13e — NEW-956 owned-model teardown confirmation/accounting

Priority: after 13c.1 identity records, before shell migration if dependencies
permit. Confirmed High, separately logged by coordinator as NEW-956. NEW-74
covers adopted-state reporting/no-op and explicitly leaves adoption authority
unresolved; it does not cover losing an actually owned child after teardown
failure. Do not grant adopted-process kill authority in this slice.

Proof from actual LlamaServer.stop AST with fake child/OS only (no core imports,
models, actual processes or live state):

    unexpected-error {'returned': False, 'owned_handle_lost': True, 'started': False, 'pid_file_exists': False, 'wait_calls': 0, 'fake_child_still_alive': True}
    timeout-kill-unconfirmed {'returned': True, 'owned_handle_lost': True, 'started': False, 'pid_file_exists': False, 'wait_calls': 1, 'fake_child_still_alive': True}

Current stop finally unconditionally removes PID state and clears process/
_started. Timeout sends KILL without final wait. ModelLoader.unload ignores
False, drops server/loaded/ever-spawned state and releases its slot. Failed-load
cleanup likewise drops ownership/releases. Consequence: surviving model can
become unowned/unaccounted before another load; RAM-critical, not cosmetic.

### Low-level owned LlamaServer contract

stop returns True only after confirming/reaping this owned child; an already
exited owned child is reaped and may return True. Retain NEW-74 no-owned-handle
False behavior and adopted warning. Poll the retained Popen before signaling.
Bounded TERM wait, KILL escalation, then bounded final wait; use the Popen handle
as the ownership anchor. On unexpected signal/wait error, an additional owned
cleanup attempt is allowed, but success still requires confirmed exit/reap.
If exit remains unconfirmed, retain process handle, identity/PID evidence and
accurate teardown-pending state, return False; no unconditional finally reset.

Preserve existing dedicated-session group-stop behavior only when the owned
live child still anchors its expected group (group created by this loader).
Never signal an adopted PID or expand to discovered groups. Avoid stale captured
PID fallback after the handle has exited. Identity cleanup uses 13c.1 compare-
before-remove and preserves replacement records. Failure to remove an unrelated
replacement is not evidence the original owned child survived; report cleanup
separately from actual process exit.

Serialize start/stop transitions; idempotent retry must not overwrite a surviving
handle or publish a new child while old teardown is pending. Keep waits bounded
and locks out of asynchronous event-loop work using existing executor patterns.

### ModelLoader contract and accounting

Preserve ordinary unload success/no-op call shape (None is compatible). On an
owned child whose exit cannot be confirmed, raise a specific RuntimeError
subclass (e.g. ModelTeardownError), retain _server and _slot_id, and expose an
honest last outcome/reason; do not release the slot or claim unloaded success.
A failed load may have _loaded=False even while it retains an owned cleanup-
pending child: do not invent a healthy-loaded state to store cleanup ownership.
get_pid must keep returning its owned PID. Status should expose cleanup pending
rather than require downstream callers to infer it from is_loaded.

At the earliest owned-child convergence after spawn, retain this reservation's
slot ID, including when start fails or resident confirmation throws. Failed-
load finally may release/discard only after no child was spawned or owned exit
is confirmed. Never overwrite retained failed-cleanup ownership in a later
load_primary call. Direct load_primary, ensure_model cold load, and start retry
must first resolve retained cleanup or refuse a new load with an error outcome.
A healthy existing owned child must not be overwritten by direct load_primary.

Keep reservation accounting conservative while cleanup is pending. PENDING
reservations initially belong to the loader PID, whereas resident marking binds
the actual model PID. A surviving failed-start child must not lose accounting
merely because the loader exits: bind its existing reservation to the actual
owned child without prematurely marking it RESIDENT or dropping its reserved
cost. If needed add one narrow resource_gate bind-PENDING-slot-PID helper under
its existing locked-state contract; no admission math/status-policy rewrite.
Check its real reaping behavior and test the retained failed-start slot against
loader-death simulation. If durable accounting cannot be updated, surface that
failure and retain old ownership/evidence; do not claim cross-process accounting
is proven. Existing broader reserve-to-spawn crash windows remain separately
tracked, not silently declared fixed.

Release the slot only after confirmed owned exit. If release itself fails,
retain the slot ID for retry and report accounting cleanup failure. No new load
until cleanup is resolved; do not silently discard a conservatively retained
reservation. Adopted references have no owned child and normally no owned slot;
retain established adoption bookkeeping, never kill or free the other owner's
slot. Do not change NEW-74 adopted-state product policy.

Use a per-loader reentrant lifecycle guard or equivalent private-method
structure so load/unload/cleanup serialize. Preserve existing SWAP_GUARD
nonblocking protocol: ensure_model and daemon release take SWAP_GUARD before
loader lifecycle lock; inner load/unload must not reacquire SWAP_GUARD. Never
invert that order or wait for health/HTTP while holding resource_gate's flock.
A per-server guard protects direct LlamaServer.start/stop callers. Retain owned
state consistently across exceptions and interruptions, not just False returns.

### Caller propagation (read/inspect every listed path)

- _spawn_locked timeout cleanup, load_primary failed-load finally,
  ModelLoader.unload, and ensure_model thermal restart. Failed teardown must
  abort replacement and preserve tm.restart_recommended for later retry.
- reset_loader: unload failure must preserve the global loader reference.
- daemon _release_model_slot_sync: _loaded=False is insufficient to declare
  already-unloaded if cleanup-pending ownership exists. No released/freed result
  or cooldown success after failed teardown; exception reaches existing error
  response. Keep blocking teardown in executor. Daemon shutdown logs the failure
  and preserves durable child/identity/accounting evidence as it exits.
- main.shutdown currently captures PID then raw killpg on unload exception.
  New teardown exception must not trigger stale bare-PID/group fallback that
  bypasses retained owned-handle checks. Prefer owned loader cleanup/retry and
  truthful warning, preserving evidence; do not report successful unload.
- lora_import.swap_to_finetuned_model primary AND secondary paths mutate cfg
  before unload. Abort reload on teardown failure and restore original cfg
  values before returning failure. rollback_to_backup must not claim successful
  reload after failed teardown/load. Do not rewrite artifact/promotion policy;
  group14 owns those independent boundaries.
- Audit all current LlamaServer.stop/ModelLoader.unload callers (including tests)
  for result assumptions; adding a False and then ignoring it recreates NEW-956.

### Tests and live verification

Fake-child tests must discriminate retained ownership on TERM failure, KILL
failure and final wait timeout; successful TERM and forced KILL both reap;
already-exited owned child reaps without signaling; adopted stays untouched;
identity replacements preserved; retry eventually clears state. ModelLoader
fixtures cover unload failure retaining slot/server/PID; failed start and
resident-confirmation exception retaining cleanup ownership/reservation; no
second spawn/reservation on retry while first child survives; release failure
retains slot ID; adopted accounting unchanged; daemon release with _loaded=False
cleanup pending; thermal restart abort/no reset; reset_loader preserves singleton;
LoRA config restored and no replacement load on failed teardown; main shutdown
avoids raw stale-PID fallback. Verify lock concurrency without model loading.

Live-verifier uses only real lightweight disposable Python children started in
an isolated session, temporary identity/state and fake admission data. One child
handles TERM normally, one ignores TERM and needs KILL. Assert bounded actual
exit, Popen.wait/reap, identity cleanup and slot release order. Injection of
failed signaling/wait against retained fixture handle proves retry/no-new-spawn;
a separately owned innocent fixture process must survive. Finally cleanup exact
fixture handles, record verbatim outputs and no remaining fixture children.
This loads no model or embedding; model RAM-load cycle is neither needed nor
represented as verified. Mandatory explicit adversarial lifecycle approval.

No product-direction fork: preserve ownership/accounting of processes already
spawned. Adopted authority and independent promotion decisions remain separate.


## 13c.1 safe ordering correction after NEW-957

Loader metadata publication failure in 13c.1 remains nonfatal, matching the
previous startup behavior: warn explicitly that durable identity is unavailable,
retain the owned Popen, and continue existing startup/health/accounting. Do not
call the currently unsafe stop or raise solely for publication failure. Missing
or inconsistent cross-process identity remains fail-closed. This is degraded
identity infrastructure, not complete lifecycle closure. Required 13e follows
immediately after 13c.1 and before shell migration, establishing safe retained
cleanup/accounting without changing NEW-74 adopted-process authority.

Every fake-Popen regression context must explicitly mock both identity writer
and LlamaServer.stop before execution. Real signaling belongs only to retained
disposable fixture handles with finally cleanup. NEW-957 preserves the initial
unguarded-fixture incident and missing-output uncertainty; do not imply zero
unknown signal attempts or reconstruct unavailable logs.
