# WP2.1 13c.2b.2 resumed private lifecycle mechanics live verification

2026-10-16. Independent resumed result (after coordinator-authorized harness-only marker fix): PASS.

The initial FAIL artifact remains unchanged. Its observer parsed an existing-but-empty marker before Bash printf completed; this resumed harness waits for a complete newline-terminated result with a bounded deadline. No production change or erased failure.

Actual private Bash/coproc and finite lock-exec adapter ran only under disposable HOME/state/PATH with fail-closed interpreter dispatch. Real OwnedLaunch children were retained out of band by an independent temporary wrapper, reaped before its OS exit, and actual main(spawn) return mapped to that exit. Parent retained real Bash/USR1/innocent Popen handles. Metadata denial, trailing/EOF and deferred guardian cleanup were explicit test-only injections. Complex caller traps were compared and actually fired after success/failure. Special locks refused before interpreter; actual recorded own-child reload/stop preserved an innocent child.

Limits: no public service shell invoked; shells remain unmigrated. Successful-spawn wrapper cleans its child before helper exit, so this verifies private handoff mechanics rather than a long-lived installed service. Guardian liveness failure/invalid protocol were injected around real children. SIGKILL/host crash can defeat memory-only ownership. No audit coverage claim, models, installed services, cloud/network/live store or credentials.

Literal immediately flushed output:

```text
$ free -h (before)
               total        used        free      shared  buff/cache   available
Mem:            10Gi       7.1Gi       314Mi        87Mi       3.8Gi       3.7Gi
Swap:           15Gi       3.7Gi        12Gi
ADAPTER ('lock-exec', 'restoricon', 'preflight') rc= 2 stdout= '' stderr= 'Service mechanics unavailable or unsafe\n'
PASS unsafe symlink lock refused before interpreter; target unchanged
ADAPTER ('lock-exec', 'restoricon', 'preflight') rc= 2 stdout= '' stderr= 'Service mechanics unavailable or unsafe\n'
PASS unsafe fifo lock refused before interpreter; target unchanged
ADAPTER ('lock-exec', 'restoricon', 'preflight') rc= 2 stdout= '' stderr= 'Service mechanics unavailable or unsafe\n'
PASS unsafe directory lock refused before interpreter; target unchanged
PASS actual coproc savedjob/FD handshake success OSreturn= 0
SHELL success OSrc= 0 ownedspawn= {'main_return': 0, 'children': 1, 'codes': [-15]} stdout= b'' stderr= b'' exact_traps_restored=True
PASS actual coproc savedjob/FD handshake failed OSreturn= 2
SHELL failed OSrc= 2 ownedspawn= {'main_return': 2, 'children': 1, 'codes': [-15]} stdout= b'' stderr= b'' exact_traps_restored=True
PASS fullpipe trailing no result/fallback; parent lock held while waiting actual helper
SHELL trailing OSrc= 2 ownedspawn= {'main_return': 2, 'children': 1, 'codes': [-15]} stdout= b'' stderr= b'Service mechanics unavailable or unsafe\nService readiness failed; helper finished, service identity requires inspection.\n' exact_traps_restored=True
PASS fullpipe eof no result/fallback; parent lock held while waiting actual helper
SHELL eof OSrc= 2 ownedspawn= {'main_return': 2, 'children': 1, 'codes': [-15]} stdout= b'' stderr= b'Service mechanics unavailable or unsafe\nService readiness failed; helper finished, service identity requires inspection.\n' exact_traps_restored=True
PASS retained guardian after function return2/outerFDclose: same lock held; Bash waits actual helper
SHELL guardian OSrc= 2 ownedspawn= {'main_return': 2, 'children': 1, 'codes': [-15]} stdout= b'' stderr= b'Service launch failed; retained guardian owns cleanup and lifecycle lock.\n' exact_traps_restored=True
ADAPTER ('lock-exec', 'daemon', 'reload') rc= 0 stdout= 'running\n' stderr= ''
ADAPTER ('lock-exec', 'daemon', 'stop') rc= 0 stdout= 'absent-dead\n' stderr= ''
PASS actual verified private reload/stop/reap; innocent survives; identity removed
Allowlisted dispatch trace: ['parse-ready', 'spawn', 'spawn', 'parse-ready', 'spawn', 'parse-ready', 'spawn', 'parse-ready', 'parse-ready', 'spawn', 'signal', 'stop']
PASS retained parent Bash/child handles all reaped= 7
$ free -h (after)
               total        used        free      shared  buff/cache   available
Mem:            10Gi       7.1Gi       292Mi        87Mi       3.8Gi       3.7Gi
Swap:           15Gi       3.7Gi        12Gi
RESULT PASS
```
