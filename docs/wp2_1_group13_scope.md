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


## 13e refinements — independently inspected spawn/reaper/caller details

Earliest binding must be inside LlamaServer._spawn_locked immediately after
Popen assigns the owned handle, before identity publication, logging and the
up-to-60-second health wait. ModelLoader retaining/binding only after start()
returns leaves exactly the failed-start/interrupt interval unprotected. Retain
reservation ID before calling start; provide a narrow core-owned spawn callback
or equivalent reservation context. Genuine spawn invokes it; adoption never
does. Pending binding must preserve status/cost/swap data. A False return from
binding or mark_resident is a real failure, not just exceptions: current
confirm_resident_and_mark_slot ignores mark_resident's False result. No healthy
success without its expected slot. release_slot False meaning already absent
is different from an I/O exception: safely absent accounting must not become
permanent cleanup-pending debt.

Actual reaper inspection: _pid_alive catches PermissionError and can conclude
dead from precomputed health-port False; reserve_slot and list_slots both drop
the row. A genuinely owned failed-start/loading child need not answer /health,
so binding alone does not protect its PENDING reservation in this case.

Narrow allowed refinement: bind_pending_slot_pid also marks the row as a
core-owned PENDING child. For marker is True AND status PENDING only, liveness
must treat PermissionError conservatively alive without port-health death
inference (e.g. shared slot helper calls _pid_alive with port=None). ESRCH still
reaps. Use same helper/selection at both reserve_slot/list_slots reap sites;
precheck may skip marked rows because no port result is needed. Clear marker
atomically on mark_resident; RESIDENT behavior must preserve existing NEW-432
health inference even if a stale marker remains. Unmarked PENDING retains its
existing semantics. No HTTP under flock or admission/ceiling math changes.

Discriminating tests at BOTH reap sites: marked PENDING + PermissionError +
unreachable port remains with unchanged status/cost/swap claim; ESRCH is reaped;
RESIDENT with stale marker still follows original health inference; unmarked
PENDING remains original behavior. This is conservative retention, not a new
permission or a claim of identity-safe reaping after PID reuse.

Caller ordering addition: rollback_to_backup currently copy2s backup to target,
unlinks backup and mutates cfg before unload. Move the owned-unload precondition
before those mutations; new teardown failure must preserve backup bytes, target
bytes and original cfg, with no reload. This is failure propagation for the
owned-model operation, not adopted-process kill authority or broader promotion/
artifact authorization (group14). Retain existing adoption semantics separately.

Final bounded assessment: the spec now covers genuine spawn, slow/failed start,
resident-confirmation false/exception, owned stop/reap, failed cleanup retries,
reservation binding/reaping/release, direct and ensure-model reload, singleton
reset, daemon release/shutdown, main fallback and LoRA swap/rollback. Interruptions
must preserve the same ownership/accounting invariants as ordinary failures.
No source implementation approval is implied: independent reviewer still needs
the actual diff and fixture evidence, particularly lock order and adoption.


## 13c.2 API handoff refinements — committed identity implementation

Actual API names: LifecycleRecord(pid_file, service, lock_fd=None,
blocking=True); CLI accepts record/inspect/cleanup/signal/stop and --lock-fd.
inspect/signal statuses are running=0, absent-dead=1, unsafe-unverifiable=2;
completed stop/cleanup returns 0. Helpers print the state string; use exit status
rather than collapsing unsafe into not-running. Use exact canonical service
keys: daemon codeyOS, model llama-server-8080; display labels are separate.

Lock inode is <pid_file>.lifecycle.lock; existing Aigentik aigentik.lock is NOT
the same inode and cannot be inherited as that lock. Once outer shell owns the
correct lock, helper invocations use --lock-fd with that exact inherited open
file description. Do not independently reacquire it and deadlock. Long-lived
service children close the FD explicitly; helper children inherit it only for
their bounded call. CLI publish proves the target child belongs to its parent:
record helper must be directly invoked by the launching shell, not inside
command substitution adding an intervening shell. Redirect its state output
if necessary rather than capturing record via $(...).

Daemon startup handoff: shell holds lifecycle lock, spawns daemon with lock FD
closed, directly publishes child record using helper's inherited lock FD, then
releases. Python check_pid_file waits for release and recognizes own identity.
Do not wait on daemon readiness while holding its lock. Core daemon shutdown
already attempts nonblocking record cleanup so shell stop can await its exit.

Remove top-level mkdir from sourced service library and public shell dispatch;
parent environment preparation performs no directory writes. Identity helper
__enter__ itself creates parent/lock, so invoke it within operation callback
once13d exists. Missing-state READ status may return absent without constructing
a root. Status inspection need not mutate stale records; explicit cleanup/start/
stop remains responsible for controlled cleanup. No directory-creation exception
is granted merely because a public command says status.

### Selected narrow reconciliation: configured daemon PID/socket/log paths

Confirmed Medium, nondefault-config compatibility defect; no live incidence
claimed. Exact inspected evidence: utils/config.py331-334 default paths;
core/daemon.py103-105 initializes globals to defaults; main around2307 calls
check_pid_file BEFORE Daemon construction; Daemon.__init__876-882 then overrides
PID_FILE/SOCKET_FILE/LOG_FILE from config daemon.pid_file/socket_file/log_file.
codeyOS10-12, codeydOS29-30 and service_manager13-14 assume defaults. Fresh-process
core.daemon.send_command around2186 uses default socket; observability.py218/252
uses default PID. Thus custom paths are supported in daemon construction but
ignored by its launcher, clients and initial duplicate check. Identity migration
cannot claim equivalent ownership when records refer to different paths.

Preserve this supported configuration with a single narrow resolver in existing
core.daemon_config, using its parser/default merge rather than another JSON
parser. resolve_daemon_paths(config=None) returns effective pid/socket/log paths;
optional already-loaded config avoids second snapshots during Daemon init.
Remove daemon_config's import-time CONFIG_DIR.mkdir; create directories at actual
save/default-create boundaries. Resolver reads only; no new setup dependencies.
Do not change arbitrary config handling, persistence schema, admission policy or
relative-path semantics. Existing relative values remain relative to the invoking
process cwd unless separately scoped; resolve once for each complete operation
and use the same snapshot throughout it.

Wire daemon duplicate check, publication/server startup, is_daemon_running and
send_command to effective paths, including fresh CLI/planner imports. Preserve
existing test monkeypatches through explicit optional paths/config fixtures,
not by retaining conflicting production sources. Observability daemon PID and
its uptime-mtime comparison use the same effective PID path. Shell shared manager,
codeydOS and codeyOS resolve effective daemon pid/socket/log paths lazily inside
operation mechanics (source remains write-free). Non-daemon service paths remain
under selected state root. State DB display remains actual state.db convention;
do not confuse daemon log/path override with moving every state artifact.

Use finite field selection/data arguments between resolver and shell; never eval
returned shell code or interpolate config values into generated Python. Preserve
spaces in paths and existing inherited environment. Missing config retains
defaults; existing invalid-config fallback remains consistent across consumers.
No new public --internal bypass, config mutation feature or product fork.

Tests: temporary root config with custom absolute pid/socket/log; duplicate check
uses custom PID before constructing daemon; shell launch/stop/status/reload and
codeyOS client share custom record/socket; fresh send_command/planner connection
uses custom socket; observability PID+mtime aligns; defaults unchanged; read-only
resolver/source of libraries on absent root creates no directory; custom-path
fixtures include spaces. All sockets/children are disposable, no real services.
If an unanticipated additional consumer cannot be reconciled narrowly, retain
it explicitly rather than claiming all custom-path compatibility is closed.


13c.2 test safety prerequisite (NEW-957 incident): before running any existing
shell lifecycle tests, inspect fixture PIDs and helper/subprocess mocks. A test-
looking integer is never safe to signal. Replace synthetic PID lifecycle calls
with fully mocked identity helper/signals, or exact currently retained fixture
Popen handles. Adding identity wrappers can make old partial mocks reach real
helpers; cover every migrated entrypoint. Only explicit disposable-child tests
may exercise actual signaling, with finally cleanup and no inherited live root.
Custom-path reconciliation is coordinator-ledger NEW-959, Medium, scoped here.


## Relative configured daemon paths — superseding refinement

This supersedes the earlier sentence preserving invoking-cwd relative semantics.
Actual launch trace: codeydOS199 nohup inherits caller cwd; its generated script
only sets sys.path/CODEY_DIR around190-192. codey's $(cd ... && pwd) locates the
repo in a subshell and does NOT change parent cwd. No daemon launch chdir was
found. Therefore invoking-relative PID/socket/log paths already disagree when
later clients run from another directory; merely sharing parser logic cannot
fix NEW-959 while preserving that unstable interpretation.

Pending option B (NOT SELECTED): use a shared stable path base, the directory
containing daemon config.json (the selected CODEY_STATE_DIR root). Snapshot that config path/base to absolute
once per complete operation. Absolute configured PID/socket/log values stay
unchanged; relative configured values resolve against this shared config base,
then become absolute before any identity/log/socket operation. All shell and
Python consumers use those exact resolved values. Do NOT chdir the daemon/TUI
to enforce path semantics: utils.config.WORKSPACE_ROOT derives from cwd and
changing cwd would unintentionally change the agent's workspace.

Document this explicit correction to relative-path semantics. It is not an
automatic data/process-record migration: deployments previously using paths
relative to a launch cwd should convert config values to those original absolute
locations before rollout. Do not scan arbitrary directories for old PID records,
adopt discovered processes or move/delete old files automatically. Existing
absolute configurations and defaults require no migration. As with an operator
changing configured absolute paths, launcher agreement on the new config does
not prove an unrelated older-location service was stopped; retain that deployment
limit honestly. Coordinator correction: this compatibility behavior requires Ish's decision;
no stable-base implementation is authorized until that answer arrives.

Tests: config root in temporary directory with relative custom PID/socket/log,
launch fixture from directory A, inspect/stop/client from directory B; all select
the same absolute config-root paths. Assert daemon/TUI cwd and WORKSPACE_ROOT
remain the original intended workspace. Cover relative CODEY_STATE_DIR input
by snapshotting it against entrypoint cwd once and passing/exporting the resulting
absolute root across the operation's child processes; user-supplied absolute
state root remains unchanged. No actual services/model loads.


## Relative-path decision pending Ish — controlling status

Coordinator has surfaced three options to Ish: (A, recommended) require absolute
custom daemon paths and refuse ambiguous relative values; (B) stable state-root
anchor with documented migration; (C) retain caller-relative behavior and its
explicit residual. No option has been selected in this report. Earlier architect
statements that stable anchoring needed no product decision are superseded:
existing running instances/duplicate-start consequences make this a genuine
compatibility choice. The exact launch-cwd trace above remains confirmed;
the stable-anchor paragraphs/tests describe option B only, not approved scope.
Keep dependent relative-path implementation pending Ish's answer. 13e and
absolute-path/identity mechanics remain independently actionable. Do not silently
rewrite deployment path semantics or choose a migration policy in implementation.


## 13c.2b — Publication failure must retain real ownership

Problem: after a shell spawns $!, record failure followed by return/lock release
can leave an unrecorded service. Restoricon/Cloudflare have no orphan scan, so
later start can duplicate it. Bash may already reap a short-lived $! and permit
PID reuse: captured integer plus late kill is not a safe cleanup capability.
No product fork: retain ownership only of the process this launcher spawned.

Selected mechanism: extend the stdlib process_identity CLI with an internal
owned-spawn operation. The helper itself Popen-spawns the service while holding
the launcher's validated inherited lifecycle lock, then publishes that owned
child (normal publish direct-child proof, no adopt/discover). It retains the
Popen throughout publication/startup checking and failure cleanup. A real owned
Popen can poll/wait/reap its child; it does not depend on Bash's already-reaped
integer. Do not simply add late record-then-kill around old shell $! paths.

Finite service mechanics supply argv as a list, cwd, append-log destination and
existing service environment. No shell=True or command-text interpolation. Keep
HUP resistance/session behavior explicitly compatible with the existing nohup
launch; close every lifecycle/ready FD in the service child. Do not modify its
credentials, PATH, configured ports or args. No command/secret argv may be
printed into protocol, diagnostics or audit. The helper is process mechanics;
13d supplies the complete-operation authority/audit envelope.

### Ownership/cleanup outcomes

Before Popen succeeds, any failure is a no-child failure. After Popen succeeds,
any exception (record write, snapshot/proc failure, startup observation, log
handling, ordinary interruption) must converge through owned cleanup. Retain
the child handle before any post-spawn operation can throw. Poll before signal;
TERM + bounded wait, KILL + bounded final wait. Only confirmed exit AND reap
allows the failed launch to finish with no retained ownership. Never signal a
PID read from a record, adopt an old process or expand to a process group not
created/owned by this launch. A replaced record is preserved independently of
owned-child cleanup.

Successful publish plus bounded current liveness check emits published PID and
returns success; failure emits failure only after cleanup, or explicit retained-
guardian failure below. Service startup timing stays bounded as today; recorded
and still alive is not proof its application health/API is ready. Daemon may be
blocked in its own check_pid_file until outer launch lock release, so do not
wait for its application readiness under this lock.

If kill/wait remains unconfirmed, do NOT drop the Popen, exit the helper or close
its inherited lock. Retain an explicit failed-launch guardian process holding
that exact lifecycle lock/open-description until owned child is confirmed exited
and reaped. Guardian can periodically observe/retry bounded owned cleanup; no
new service spawn, orphan discovery or arbitrary recovery. Avoid a busy loop or
unbounded output. Signal/interrupt handling must preserve ownership/lock or
complete owned cleanup, not silently release them while the child survives.
A forced SIGKILL/host crash can defeat in-memory fallback; disclose this limit.
When all filesystem writes fail no implementation can promise durable markers.
Existing lock inode must never be replaced or unlinked as a recovery shortcut.

### Private readiness channel and shell handoff

Use a private pipe FD, never public stdout framing/eval or a disk file that may
be unwritable. Exactly one bounded machine result after startup/cleanup decision:
published <child_pid>; failed-cleanup-confirmed; or retained <guardian_pid>
<child_pid>. Require strict result grammar and valid positive PIDs; protocol
contents are diagnostic, never authority to signal. Child stdout/stderr remain
append-log streams, no pipe inheritance. Ready FD closes after sending; guardian
must not hold it open while waiting for its child.

Shell function holds lifecycle FD while reading result. On published, wait for
successful helper completion, then release outer lock and return success. On
failed-cleanup-confirmed, wait helper completion and return failure. On retained,
return failure with an explicit retained-ownership/lock-contended diagnostic;
DO NOT wait forever for guardian. Shell closes its FD, but helper retains same
open-description lock. Future start/stop/status use bounded/nonblocking lock
acquisition and report contended/unsafe; no duplicate service or false stopped
success. No public flag/environment variable may skip lock or publication.
A Bash process-substitution/coproc pipe is acceptable; do not use a pipeline
that loses status, `$!` meaning or closes the helper's required lock FD. Helper
owns actual service Popen, so direct-child proof does not depend on pipe-shell
parentage. Keep guardian service PID and its own PID distinct in diagnostics.

EOF/crash before a valid ready result is failure, not permission to release and
retry blindly: inspect whether the helper still owns the lock, report unsafe
state, and retain the parent lock while resolving a still-live helper. Normal
exceptions must send one of the defined outcomes; unavoidable process crash
limits remain explicit rather than claimed solved. Do not introduce a second
spawn fallback. This contract is not a full general-purpose daemon supervisor.

### Callsite coverage and verification

Use owned-spawn helper for all shared service spawn sites: Restoricon, Aigentik,
Litestream, Cloudflare, document backup, and codeydOS daemon launcher. Existing
identity setup on daemon self-publication remains idempotent. Model loader has
its own Popen/NEW-956 retention path and is NOT migrated into this shell helper.
Preserve fd200 close invariant, log paths, argv quoting, actual cwd/env, selected
state root, config path resolution and no-automatic-kill orphan diagnostics.
Keep relative custom-path choice pending Ish; this mechanism needs no answer.

Mandatory before running old tests: audit synthetic PID fixtures and partial
subprocess/helper mocks (NEW-957). Use fully mocked identity/owned-spawn calls
or exact retained disposable Popen handles; never signal a test-looking number.

Unit/fake-child cases: Popen failure; identity/proc failure before publish;
first/second record-file write failure; log error; replaced record; publication
failure then TERM success; ignored TERM then KILL/reap; KILL/wait failure retains
handle+lock/guardian and returns failed readiness; retry confirms exit/releases
lock; service child inherits no lock/ready FD; malformed/EOF readiness never
starts a second service. Assert every service wrapper uses this contract.

Disposable real children: normal publication; forced metadata-write failure
with successful owned cleanup (no child remains); TERM-ignoring child KILL/reap;
controlled retained-guardian case verifies a competing launch cannot acquire
lock/spawn, then lets owned cleanup finish and confirms lock release. Failure
injection is via test monkeypatch/harness, not a production unsafe bypass flag.
Fixtures retain exact helper/child handles and finally-cleanup; no real services,
models, package installs or live roots. Reviewer verifies stdout/argv secrecy,
return propagation, daemon lock handoff and all post-Popen exception paths.


## 13c.2a bounded additions — NEW-960/NEW-961 daemon_control public contract

Actual artifact read: daemon_control.py exports check/is_running/get_task/cancel
plus self-test, while manifest and doc promise ping/status/health too. Its PID
wrapper calls the mutating startup check: creates lock/root, cleans dead records,
reports unsafe as True and its own identity as False. These names are absent
from CAPABILITY_AUTHORITY, so normal CCOS dispatch refuses them; no live agent
activation or new authority classification is authorized here.

Close within Python consumer reconciliation, not defer: expose a genuinely
read-only identity inspector distinct from startup duplicate prevention. It
reads bounded no-follow snapshots plus proc identity, checks a stable pair
(double snapshot or existing noncreating read lock); absent root remains absent,
no mkdir/lock creation/cleanup/signals. Share underlying inspection logic where
practical, but do not weaken lifecycle-mutator lock checks. An unstable/missing
pair or inaccessible identity is unsafe, not dead or verified running. Status
results confer no signal/start authority and can become stale after return.

Plugin daemon_check_pid_file uses effective resolved PID path and that inspector.
Verified identity for current process is RUNNING (startup's own-PID exception is
irrelevant to status). Return running True for verified running, False for
confirmed absent-dead, and an explicitly documented unknown (e.g. None) plus
state unsafe-unverifiable for unsafe; never mislabel startup-blocked as running.
Preserve dictionary shape and self-test's running key. Manifest description must
stop claiming READ self-healing removes stale PID files. No authority-table or
permissions additions and no newly exposed shutdown/command/release handler.

Implement the three already-promised plugin functions daemon_ping/status/health
as thin wrappers over existing core.daemon RPC helpers (private aliases avoid
name shadowing). Preserve response/exception contracts. Test the public plugin
exports, not replacement imports from core.daemon. Existing modified test.py
currently imports these3 directly from core, masking the missing plugin API;
change it to real public plugin imports after implementing wrappers.

Pin every manifest implementation symbol to an actual callable in the plugin;
keep all seven capability names unchanged. Use existing lightweight DaemonServer
fixture socket/temp StateStore to exercise public ping/status/health/task/cancel.
No full Daemon/model startup. Replace real-environment PID/status self-tests with
isolated path fixtures: own process identity => True; absent root => False and
root remains absent; legacy-live/malformed/mismatch => explicit unknown and
identical file snapshots afterward. Missing wrapper mutation breaks collection/
public-symbol test; substituting startup guard breaks nonmutation/self tests.
Normal call_capability remains unclassified-refused before and after this fix.
No real daemon/live-store writes. Mandatory reviewer coverage of public contract.


## 13c.2a NEW-960 class closure — main.py status versus startup guard

Reviewer/source follow-up confirmed main._daemon_is_running still calls the
startup-mutating check_pid_file. Its missing-record result False creates a
lifecycle lock; malformed record returns True and is mislabeled running. Actual
callers are gate recovery and shutdown. Complete the same Python-consumer class
now, rather than defer this known instance to final census.

Change helper to existing pure core.daemon.is_daemon_running, which verifies
identity plus socket reachability. Unsafe means False for RPC coordination only;
it never supplies startup permission. Gate-recovery diagnostic must say no
verified reachable daemon is available, not assert no process exists. Shutdown
must not skip owned-model cleanup merely because a malformed record would block
startup. main --daemon delegates to core.daemon.main, sharing its single resolved
config/path snapshot. Core startup blocked diagnostic must describe a running
daemon OR unsafe/unverifiable record, rather than claim every block is already
running; remove nonexistent --daemon-stop advice. No capability classification
or adopted-process policy change.

Tests: missing root helper False creates nothing; malformed/legacy live False
preserves records/no socket connect; verified identity plus disposable socket
True; gate recovery no RPC for unverified; shutdown still calls owned cleanup
on unsafe state; --daemon delegates once; shared core entry passes identical
config/paths to guard and Daemon constructor; blocked startup never constructs/
runs Daemon; diagnostic contains no unsupported flag. Use isolated state before
imports and fake Daemon.run (no model); mandatory reviewer re-review after change.


## 13c.2a verification scope correction after isolated import diagnostic

Initial combined fresh import/READ missing-root assertion failed; buffered raw
child/RAM evidence was unavailable. Preserve that initial report separately.
New isolated diagnostic confirms daemon_config/stdidentity imports remain
write-free, core.daemon/plugin import creates the state directory through
core.state bootstrap, and main imports initialize fixed StateStore schema via
EpisodicMemory. Subsequent READ functions leave snapshots unchanged. Architect
accepted these observed effects under the existing group 12 schema-initialization
contract, not a new general import exemption. No lazy-import repair is required
for this bounded slice. Resumed verification compares READ effects after stated
bootstrap and tests actual configured-path UDS clients. It cannot reconstruct
the initial failed run's missing output or prove its precise cause. Preserve
these distinctions in the final census.

13c.2b readiness clarification: broken/EOF readiness while the actual helper
job remains alive retains the outer lock and waits for that owned helper job's
cleanup completion. Never signal a captured numeric helper PID or auto-spawn a
replacement. Normal valid retained-guardian status may return bounded failure
while the helper keeps the same lock and child ownership. Forced crash limits
remain explicit.


## 13c.2b consumer handoff — actual b.1 API and safe outer lock opening

Fresh source read 2026-10-16 (b.1 source approved round2, live verification in
progress; no public shell consumers migrated yet). Actual command:

    python3 core/process_identity.py spawn --pid-file P --service KEY --lock-fd N --ready-fd W --log-file L [--cwd C] [--startup-delay .5] [--timeout 5] -- argv...

Build argv arrays, never shell command strings. Retain existing service cwd,
configured args/env and log destinations. Helper Popen owns the child, ignores
HUP through its signal context, closes service-child extra FDs and directs
stdout/stderr to append log; no shell nohup/$! child publication fallback remains.

parse_spawn_ready(bytes) accepts exactly newline-terminated published PID,
failed-cleanup-confirmed, or retained GUARDIAN_PID CHILD_PID. Numeric range is
checked and guardian != child. CLI spawn return0 means successful handoff;
failed-cleanup-confirmed returns2; retained emits its one record then stays alive
holding lock until cleanup/reap, eventually exits2. Successful publication and
private result delivery commit handoff; reporting pipe failure cleans owned
child instead. Use the actual shared parser rather than looser shell split/
regex assumptions. Private pipe only; service argv/secrets never become payload.

### Safe outer lock acquisition choice

Do not use Bash > lockpath: it truncates before validation. Bare Bash <> avoids
truncation but can still follow a symlink/open a special file before core checks.
Select a narrow stdlib lock-exec adapter for service mechanics: open expected
.pid.lifecycle.lock with O_RDWR|O_CREAT|O_NOFOLLOW|O_NONBLOCK, validate regular
FD/path inode, acquire LOCK_EX|LOCK_NB, revalidate, then exec fixed repository
private Bash mechanics with only this FD deliberately inheritable. Reuse
LifecycleRecord's validated locking where possible; do not duplicate weaker
checks or accept arbitrary caller-selected shell text. Keep operations finite
(start/stop/reload for core-selected service keys). This is subordinate mechanics,
not a new public audit-skip option. 13d still owns the public authority envelope.

The calling public shell runs this adapter as a bounded child for that service
operation; it must not exec away the all-services coordinator. Adapter execs a
fixed private Bash function/library, passing the numeric FD as positional data,
not an env skip-lock/skip-audit token. Every helper use validates --lock-fd against
the expected inode. It is necessary to preserve the shared open-description FD
across adapter->Bash->spawn helper. Parent Bash closes its FD when finishing;
NEVER flock -u on it (that would unlock guardian's shared description). Explicitly
close unrelated lock/ready FDs in grandchildren; b1's service Popen close_fds does
this for service children. Lock content is never written/truncated; lock inode
never unlinked as recovery. Contention/symlink/FIFO/device/invalid lock is failure
before any service spawn or side effect. Do not silently skip it as success.

If implementer offers an equally safe smaller opener, reviewer must verify it
cannot follow/open a special target, block on FIFO or alter content before type/
inode validation; a racy Bash pre-test plus <> is not equivalent to O_NOFOLLOW/
O_NONBLOCK regular-file validation. Opening/creating lock metadata is subordinate
to the authorized operation, not a source-time library effect.

### Private result/job protocol

Use an anonymous pipe or carefully managed Bash coprocess with an actual saved
helper job identity and readiness FD. Capture/duplicate needed coprocess FDs and
job handle before completion can unset Bash coprocess variables. The helper must
exec in that job (no intermediary whose PID is mistaken for guardian). Bound the
line length; require newline/valid parser result. Published requires helper exit0
before parent returns0. Cleanup-confirmed requires helper exit2 and returns
failure. Retained must identify actual helper job and a distinct valid child;
close parent pipe/FD and return failure while helper keeps lock, without waiting
indefinitely. Neither protocol PID grants permission for a shell kill.

Malformed/EOF/timeout readiness: keep outer lock, close the read pipe to force
failed delivery, and wait actual helper job for owned cleanup/exit; NEVER kill a
captured helper PID or release/retry because no valid record arrived. Signal
interruptions preserve this ownership-resolution path. Valid retained result is
the bounded return case. Unexpected crash limits are already documented; do not
invent orphan kill/adoption on missing protocol. One complete operation must
not leak its lock into unrelated services/TUI. Test rapid helper completion so
FD/PID lifecycle races are exercised, not hidden by sleeps.

### Callsite/config agreement

Migrate all six shell launches plus daemon reload/stop/status, codeyOS inspection
and composites as previously scoped. Daemon handoff: spawn helper publishes
codeyOS identity, shell closes lock after helper success, core startup recognizes
its own record. No wait for application health while blocking its startup lock.
Use shared configured absolute/default path resolver. Relative custom values
retain CURRENT caller-relative semantics for now; Ish's choice remains pending
and no stable-anchor change is authorized. Preserve explicit relative residual.

Resolver path output is finite data, not mixed console output: select a fixed
field (pid/socket/log) via argv and emit only that value/data framing on its data
FD. Redirect parser/config fallback warnings to stderr so malformed-config
fallback cannot corrupt PID/socket/log values. No eval, shell fragment output or
interpolation of returned paths into Python. Preserve spaces and one path
snapshot across a complete operation; do not implement a config rewrite.

### BEFORE any service fixture run: stub every external effect

Audit whole function, not just service Popen. In particular start_litestream
runs core/setup_litestream.py and timeout60 core/backup_secrets.py BEFORE its
service spawn. The latter can encrypt/upload real secrets. It also reads HOME
litestream/GCS credential paths. Aigentik can cause model requests, Cloudflare
creates a real tunnel, and backup-docs can upload. No such side effect is allowed
in this verification. Tests must isolate paths/home filesystem in test subprocess
fixtures and stub/deny every setup/backup/timeout/cloud/interpreter command before
calling start functions. Never change coordinator's real HOME or use real cloud
credentials. A fake service executable alone is insufficient.

Use a fail-closed subprocess-command allowlist in the fixture harness, including
all Python config/query/setup script dispatches; unknown external commands fail
the test rather than falling through to installed tools. Stubs must assert exact
expected argv and return explicit temp config/paths. No live cloud/recipient/
package install/model calls. Retain actual disposable child handles with finally
cleanup, and audit old synthetic-PID tests before running them (NEW-957).

New cases: special/symlink lock paths untouched; FIFO cannot block opener; no
lock writes/truncation; guardian still excludes contender after outer shell
returns failure (proves no flock-u); rapid published/failed helper exit; broken
ready pipe resolves via actual job; all six launch sites exercise helper;
malformed-config warning cannot corrupt finite path data; Litestream setup and
secrets backup stubs were used, with explicit proof no real command escaped.


## Consumer implementation sequence refinement — 2026-10-16

Coordinator accepted this bounded decomposition after b.1 committed/pushed
cdd580d. It supersedes any implication that the entire consumer handoff must be
one implementation/review round; historical source/probe records remain intact.

- 13c.2b.2: safe finite lock-exec adapter, shared-parser private readiness/job
  handoff, finite daemon-path data channel, and fixed sourced private mechanics
  library. NO public entrypoint migration or claim of legacy-consumer repair.
- 13c.2b.3: migrate all six complete start/stop pairs, daemon reload/restart,
  codeyOS inspection and composite/public shell consumers together, with fixture
  side-effect isolation and independent disposable-process verification.

NEW-962/NEW-963 remain open until b.3 consumers are actually migrated/reviewed/
verified; b.2 is infrastructure only. Each round follows implementer -> reviewer
approval before commit and required live-fixture verification. The finite private
core-mechanics convention is unchanged: no public --internal option, no env
skip-lock/skip-audit switch, no caller-supplied approval/bypass token, no arbitrary
command/function selector in the adapter. Actual inherited FDs are validated,
not treated as self-attested authority. Public whole-operation gateway coverage
remains 13d; private mechanics cannot be reported as providing that envelope.
Ish's relative configured-path choice remains pending. No new product decision
or change to accepted trust boundaries follows from this execution split.


## 13f — Owned embedding teardown/replacement (NEW-964 proposed)

Independent scope, 2026-10-16. Ledger checked through NEW-963; no NEW-964 header
present at inspection. Coordinator allocates/logs NEW-964 separately. Confirmed
High lifecycle defect; same class as NEW-956 but NEW-956 repaired primary loader
only, not this module. Do not retrospectively mark embed covered by that repair.
Group13's earlier subordinate-mechanism contract explicitly required ownership/
resource safety; it was NOT an embed lifecycle exemption. Implement after b.3
(or independently before13d) and before group13 closes. No production edits or
real signals/models were used in this scope.

### Confirmed source and safe proof

core/embed_server.py stop around222-290: unexpected errors suppress cleanup
failure, finally clears self.process, resets started and releases slot. Timeout
sends KILL with no subsequent wait, yet logs stopped. stop_embed_server at file
end discards singleton regardless. start around58-124 can fall through from a
live unhealthy owned child into adoption/foreign-port cleanup/new spawn, and
around167 replaces self.process. Thus current failure handling can lose actual
ownership/accounting or overwrite the only handle before confirmed exit.

Actual stop AST run with fake OS/child only, no core import or real process:

    signal-failure {'returned': None, 'owned_handle_lost': True, 'slot_id_lost': True, 'released': ['fixture-slot'], 'wait_calls': 0, 'fake_child_alive': True, 'last_log': 'Embed server stopped'}
    timeout-no-final-wait {'returned': None, 'owned_handle_lost': True, 'slot_id_lost': True, 'released': ['fixture-slot'], 'wait_calls': 1, 'fake_child_alive': True, 'last_log': 'Embed server stopped'}

Safe reproducible command, pinned to the inspected stop source so future code
cannot unexpectedly run through old fake-PID assumptions:

```sh
python3 - <<'PROBE'
import ast, hashlib, subprocess
from pathlib import Path
from types import SimpleNamespace
source = Path('core/embed_server.py').read_text()
module = ast.parse(source)
cls = next(n for n in module.body if isinstance(n, ast.ClassDef) and n.name == 'EmbedServer')
stop = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'stop')
assert hashlib.sha256(ast.get_source_segment(source, stop).encode()).hexdigest() == 'f3fcfb6ae4afe7b62b374cd6a6468890801555aefaf53eb4cf2e94577b03ef27', 'Source changed: audit mocks before probing'
class Child:
    pid = 12345
    def __init__(self, timeout=False): self.timeout=timeout; self.waits=0; self.alive=True
    def terminate(self): raise PermissionError('fake failure')
    def kill(self): raise PermissionError('fake failure')
    def wait(self, timeout):
        self.waits += 1
        if self.timeout: raise subprocess.TimeoutExpired('fixture', timeout)
        raise PermissionError('fake failure')
for mode in ('signal-failure', 'timeout-no-final-wait'):
    released, messages = [], []
    def killpg(*args):
        if mode == 'signal-failure': raise PermissionError('fake failure')
    env = {'os': SimpleNamespace(name='posix', getpgid=lambda pid:pid, killpg=killpg), 'subprocess':subprocess, 'rg':SimpleNamespace(release_slot=lambda slot:released.append(slot)), 'warning':messages.append, 'info':messages.append}
    exec(compile(ast.Module(body=[stop], type_ignores=[]), '<actual-EmbedServer.stop>', 'exec'), env)
    child = Child(mode == 'timeout-no-final-wait')
    server = SimpleNamespace(process=child, _slot_id='fixture-slot', _started=True)
    result = env['stop'](server)
    print(mode, {'returned':result, 'owned_handle_lost':server.process is None, 'slot_id_lost':server._slot_id is None, 'released':released, 'wait_calls':child.waits, 'fake_child_alive':child.alive, 'last_log':messages[-1]})
PROBE
```

### Narrow implementation contract

Keep ordinary stop success None for compatibility; unconfirmed owned teardown
raises an explicit RuntimeError subclass (EmbedTeardownError), retains Popen,
existing slot ID and cleanup-pending state, and never logs stopped. Poll owned
Popen before signal; confirmed-exited child is reaped without PID/group lookup.
TERM + bounded wait, KILL + bounded FINAL wait/reap. Preserve only already-owned
dedicated-session group semantics where the live child still anchors its group;
never grant adopted PID/group kill authority. Unexpected failures/interruptions
must preserve ownership until actual exit, not drop references in finally.
Existing 13e owned-child mechanics may be reused if their API fits without
rewriting primary lifecycle again.

Release a known owned-child slot only after actual exit/reap. Release I/O failure
retains its ID for retry and reports cleanup debt; already-absent False is not a
permanent failure. stop_embed_server clears global singleton only after successful
stop/accounting cleanup; failure propagates while preserving the singleton.

Serialize per-instance start/stop and singleton creation/stop with appropriate
reentrant guards. No new spawn/adoption/foreign-port cleanup while this instance
still owns an unresolved child. An owned live unhealthy child first takes owned
cleanup/reap path; if unconfirmed, start returns False with cleanup pending,
retaining handle/slot and refusing replacement. Once old owned child is confirmed
exited/reaped, clean its old slot before considering a new occupant. Do not enter
_kill_port_occupant against one's own unresolved child as a replacement shortcut.
A stale already-exited handle must be cleared/reaped before adopting a different
healthy occupant (NEW-203's docstring-only fix did not establish this invariant).
Do not signal the dead handle's possibly reused PID first.

Wrap every post-Popen startup path (log output, early child death, health timeout,
health success, interrupts) in ownership-safe cleanup/retention, with actual handle
assigned immediately. Never overwrite pending cleanup with a new Popen. Close the
parent log stream deterministically even on Popen/logging failures; errors after
spawn cannot bypass cleanup. Start returns False on failed launch after safe
cleanup, or returns False retaining explicit pending cleanup; it does not claim
healthy readiness or drop uncertain state. is_running/is_healthy report their
actual liveness/health meanings and must not erase cleanup state.

### Accounting/adoption boundaries: preserve existing product contract

Embedding is explicitly accounted-but-exempt: NO reserve_slot/can_admit gate,
no new admission denial, no new eviction authority. Existing registration is
best-effort/nonfatal after health; preserve it. This slice does not introduce
PENDING embed registrations or pre-spawn reservations (which would also activate
NEW-202's currently harmless slot-status divergence). Lack of durable/pre-health
accounting remains an explicit limitation; retaining the owned handle prevents
this object's replacement even when no slot could be registered. Do not claim
registration I/O failure is a model-admission policy change.

After health, keep best-effort registration tied to the actual owned child.
Once a slot does exist, teardown failure must retain it. If registration throws
or later slot release fails, report accurately; never use accounting-only failure
to grant new kill/replace authority or misreport an owned child gone.

Healthy foreign adoption remains non-owning: no signal, no new permission to
stop that process. Distinguish a borrowed pre-existing slot from an observability
slot this instance itself registered for adoption; never release another owner's
slot. Preserve the established adopted-observability detachment behavior when
stop releases only its own observation registration. Existing unhealthy foreign
port-replacement policy/helpers remain separate; do not broaden them, and do not
claim this slice proves their identity/race safety. NEW-74 adoption product policy
remains separate; NEW-203's old blanket dead-handle-is-safe explanation needs an
explicit record correction because PID reuse is not excluded by a stale integer.

### Exact callers and tests

Known callers: core.daemon startup around1118-1127, 30-second watchdog around
1281-1292, shutdown around1329-1336; core.inference.py:_start_server around101-107
gets singleton and calls start when health is false. Module start_embed_server
and stop_embed_server expose singleton mechanics. No separate stop caller found
in embeddings.py/pipeline clients. Update daemon shutdown's bare except pass to
truthful warning, retain failed singleton, run bounded blocking stop in executor
as primary shutdown already does. Startup/watchdog must report failed pending
cleanup rather than claim a restart succeeded; watchdog must be able to retry
cleanup even if is_running sees a live pending-cleanup child. Inference optional
BM25 fallback remains, but cannot discard ownership or trigger another spawn
while cleanup is pending. Do not load models to test any caller.

Before regression runs, audit all fake PID/Popen tests and port probes (NEW-957,
NEW-279's live-port coupling). Mock every signaling and health/port dependency
in fake-child tests. Include: normal TERM and forced KILL final reap; TERM/KILL/
wait failure retains child+slot/singleton/no stopped log; retry succeeds; already
exited handle invokes no getpgid/killpg before adoption; unhealthy owned child
cannot be overwritten or routed to foreign killer; early child death, health
timeout and interrupt cleanup; post-Popen log failure; registration failure stays
nonfatal/exempt; slot release failure retains ID; borrowed adopted slot preserved;
self-registered adopted observation detached without signaling; singleton races;
daemon shutdown logs/retains; watchdog retry and inference fallback no replacement.

Independent live-verifier: only lightweight disposable Python children in owned
sessions/temp logs and fake slot callbacks, one normal TERM, one ignoring TERM,
plus injected cleanup failure/retry and innocent fixture preservation. Confirm
actual child exit/reap, retained references, no second spawn and slot-release
order. Keep exact fixture Popen ownership and finally cleanup; no model/embedding
weights, real ports/services/network/cloud/live stores. Report mechanics versus
mocked startup/adoption/accounting integration distinctly. Mandatory adversarial
lifecycle approval before commit; no group13 closure until this repair is reviewed
and required disposable-process evidence is recorded.


13f durability/reporting limit: retaining singleton/Popen protects retries only
while that Python owner lives. Daemon shutdown may still exit after warning;
its in-memory ownership then disappears. Best-effort registered child-PID slot
can outlive the parent, but no embed durable PID identity/restart cleanup is
added by this slice, and failed registration/disk failure offers no durability
guarantee. Do not claim in-memory retention survives daemon exit, host death or
forced kill. Replace stale daemon comment saying embed has no comparable gate
side effect: it does have best-effort residency accounting. Log explicit owned
embed cleanup failure (and avoid false embed-stopped success); bounded stop runs
in executor. Broader cross-process adopted/port cleanup remains separately scoped.
