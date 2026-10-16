# WP2.1 13c.2b.2 private lifecycle mechanics live verification

2026-10-16. Independent result: FAIL.

This run stopped when its guardian result-marker observer saw an existing file with empty contents between Bash redirection creation and printf writing. int('') raised ValueError. This is a fixture observation race; source correctness or incorrectness is not established by that failure. No retry was performed. The finally block released guardian control and confirmed Bash/helper/real child cleanup (main return2, Bash OS2, one child return -15); caller traps matched and fired.

Reached checks: special symlink/FIFO/directory lock refusal before interpreter, real published/failure coproc OS0/OS2 mappings, exact trap restoration, and trailing/EOF readiness waiting with outer lock held. Guardian same-lock assertion and final real recorded-child reload/stop/innocent checks were not reached. Every helper child created in reached cases has a retained-Popen completion record showing reap; all five parent Bash handles had completed. No USR1/innocent fixtures were spawned. Environment was disposable HOME/state/PATH with fail-closed interpreter dispatch. No public service entrypoint ran.

Limits: no public service shell invoked; shells remain unmigrated. Successful-spawn wrapper cleans its child before helper exit, so this verifies private handoff mechanics rather than a long-lived installed service. Guardian liveness failure/invalid protocol were injected around real children. SIGKILL/host crash can defeat memory-only ownership. No audit coverage claim, models, installed services, cloud/network/live store or credentials.

Literal immediately flushed output:

```text
$ free -h (before)
               total        used        free      shared  buff/cache   available
Mem:            10Gi       7.1Gi       338Mi        87Mi       3.8Gi       3.8Gi
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
SHELL guardian OSrc= 2 ownedspawn= {'main_return': 2, 'children': 1, 'codes': [-15]} stdout= b'' stderr= b'Service launch failed; retained guardian owns cleanup and lifecycle lock.\n' exact_traps_restored=True
Traceback (most recent call last):
  File "/data/data/com.termux/files/usr/tmp/b2_verify.py", line 65, in <module>
    awaitfile(marker);assert int(marker.read_text())==2 and h.poll() is None
                             ~~~^^^^^^^^^^^^^^^^^^^^
ValueError: invalid literal for int() with base 10: ''
$ free -h (after)
               total        used        free      shared  buff/cache   available
Mem:            10Gi       7.1Gi       322Mi        87Mi       3.8Gi       3.7Gi
Swap:           15Gi       3.7Gi        12Gi
RESULT FAIL
```
