# C3 frozen classification author report

Author /root:C3, reviewer blank. Frozen revision `770dc6639e4100ea3215fca07d923769a8290078`. All13sourcehashes match fullarchive manifest. 159 exact keys preserved, no aggregates. Static source/caller review only; no product/installer/services/network/model execution. UNKNOWN0 within author unit is not independent approval or global closure.

Classes: {"OPERATOR_BOOTSTRAP": 65, "OPERATOR_SCRIPT_RUNNABLE": 27, "FALSE_POSITIVE": 54, "BOOKKEEPING": 13}.

Reach operator-only describes normal explicit script/launcher entry, not a security isolation claim: direct named F3 operands are HIGH and require confirmation, while copied/imported arbitrary same-uid script remains accepted F2 ceiling. CI rows test-only. Every row carries exact frozen line plus actual context; shell scanner false-positive categories/qualname drift explicitly adjudicated, FD exec is bookkeeping, real commands not hidden as metadata. No new unledgered HIGH beyond known publishing/bootstrap/opaque-script class was found.

## .github/workflows/tests.yml

Push/PR CI installs pip/dependencies on ubuntu-latest; these are actual external package/install effects in the configured CI job, not device runtime. Test step clears proxies. Operator-maintained workflow, no product ActionGateway. Source yml reviewed in full.

## codey

Operator unified launcher resolves installed root, sources service_manager functions then finite case dispatch. start/default starts audited finite service profiles and execs codeyOS with argv data; inner core/cli_client and main protections determine effects. No independent outer tty gate. Direct named F3 launcher is HIGH in shell operand scan; arbitrary copied/imported wrapper remains accepted F2 ceiling NEW-1028/NEW-1069. Tests test_service_public_lifecycle.py and test_shell_g15e_protected_scan.py cover fixture mechanics/named operands only.

## codey-start

Operator start wrapper resolves installed root and sources service_manager then starts finite profiles, prepares bootstrap env, execs codeyOS argv data. No independent outer tty gate. Named F3 script execution is HIGH; same-uid opaque-wrapper ceiling NEW-1028/NEW-1069 remains. Tests test_service_public_lifecycle.py/test_shell_g15e_protected_scan.py, disposable fixtures only.

## codey-stop

Operator stop wrapper resolves root and sources service_manager; stop_all_services delegates finite ACT lifecycle envelope, identity cleanup inside owned mechanics. Named F3 restrictions and accepted service-stop wrapper/script ceiling NEW-1070/NEW-1028 coexist; no isolation claim. Tests test_service_public_lifecycle.py/test_service_action_gateway.py.

## codeyOS

Operator CLI wrapper execs fixed core/cli_client.py with argv as data; commands and interactive/daemon mode route there. Named F3 launch HIGH in shell operand scan, arbitrary same-uid wrapper ceiling NEW-1028/NEW-1069. Test_service_public_lifecycle.py and CLI client/gateway tests cover finite boundaries, not arbitrary Python isolation.

## codeydOS

Operator finite start/stop/status/restart/reload/config dispatcher sourcing service_manager. Mutations delegate service_lifecycle main -> service_actions.run_public finite _validate ACT/READ -> gate_exec before private worker. Named F3 HIGH, F2 ceiling retained. Tests test_service_action_gateway.py/test_service_public_lifecycle.py.

## codey-metrics

Operator telemetry CLI execs python -m telemetry.cli after installed-root cd, passes argv data. Telemetry handlers include diagnostic writes/rotation; source launcher is not a permission boundary. Named F3 launcher HIGH, arbitrary script ceiling retained. Tests test_telemetry_cli.py/test_telemetry_rotation.py verify disposable telemetry, not attended operator authorization.

## lib/service_manager.sh

Sourced installed library has no top-level service dispatch/state creation. bootstrap_environment source defines helper; start/stop/status wrappers delegate fixed selectors to service_lifecycle public -> finite service_actions.run_public ACT/READ gate_exec worker. Sourced direct helper invocation is same-uid installed-code contract, no sandbox. Tests test_service_action_gateway.py/test_service_public_lifecycle.py/test_service_manager_config.py. Named lib script operands HIGH; accepted F2 ceiling.

## lib/service_lifecycle.sh

Private sourced lifecycle library is reached by service_lifecycle.lock_exec worker after public service_actions gate_exec; finite validated service profiles/lock FDs, identity/orphan preflight before launch/log mkdir, exact coprocess helper retention and pipe readiness, no bare-name signal. Litestream branch invokes separately reviewed backup helpers. eval restores Bash trap-p serialization, never argv/data. Direct same-uid sourcing bypasses public envelope under accepted F2 ceiling NEW-1028/NEW-1069; no generic sandbox. Tests test_service_lifecycle_mechanics.py/test_owned_service_spawn.py/test_service_public_lifecycle.py; known shutdown-budget baseline remains.

## install.sh

Operator installer main calls system/pip installs, pinned clone/build, model downloads, chmod/config/state/token/startup/symlink/Litestream setup. Initial default-Yes read and --yes are not shared tty authorization. Token create umask077, existing nonempty preserved; DR helper has its own tty check, whole installer does not. Direct F3 bash install.sh HIGH; copied/imported opaque script ceiling NEW-1028/NEW-1069. Bootstrap effects intentionally not claimed gateway-protected. Tests test_service_manager_config.py/test_protected_paths.py cover setup strings/named restrictions, no installer executed.

## setup.sh

Operator setup chmods two launchers, appends PATH to selected shell startup, sources startup and creates state dir. No shared tty gate; named setup*.sh HIGH, arbitrary wrapper ceiling NEW-1028/NEW-1069. Tests test_file_tools_protected_classification.py/test_protected_paths.py cover named-write policy; not live installation.

## setup_repo.sh

Operator publishing script initializes Git if needed then gh repo create --public --source=. --push or remote/add/commit/push fallback. No shared tty gate; named setup*.sh HIGH, arbitrary opaque wrapper remains ceiling. Concrete sibling already NEW-1070 and NEW-1028; not newly accepted or silently fixed. Tests test_shell_g15e_protected_scan.py/test_file_tools_protected_classification.py cover named operand protection, not publisher execution.

## tools/setup_skills.sh

Operator knowledge setup creates dirs, clones/pulls eleven fixed remote repos into CODEY_DIR/knowledge/skills; top-level Python heredocs index corpus and may build embedding index. Shell scanner incorrectly retains clone_repo qualname after function close; exact source line, not mechanical qualname, determines reach. No shared tty/gateway; named F3 script HIGH, arbitrary opaque wrapper ceiling NEW-1028/NEW-1069. Tests test_protected_paths.py/test_shell_g15e_protected_scan.py cover named restriction, no setup/model run.

Independent reviewer must choose ceil25% random159=40 rows with own deterministic seed, UNION mandatory allUNMEDIATED/helperGATED/native/kill/READcanonical/unmatchedbusiness (none in this shell unit). Suggest inspect all quoted/control-flow FP and FD bookkeeping too if budget permits. Reviewer reclassifies first; >15%randomdisagreement redo. Source freeze unchanged.

Review correction: install.sh line114 pkg-install category corrected to real OPERATOR_BOOTSTRAP; separate termux-cmd marker remains FALSE_POSITIVE (dependency name). All scripts cloned count corrected to11. No source mutation. Independent review not inferred until explicit reapproval.
