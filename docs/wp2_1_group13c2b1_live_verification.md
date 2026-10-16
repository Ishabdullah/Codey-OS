# WP2.1 13c.2b.1 disposable owned-spawn verification

2026-10-16. Independent on-device result: PASS.

Approved stdlib OwnedLaunch/main(spawn) ran actual lightweight Python fixture children. Independent helper wrapper retained every actual child Popen out of band; parent retained actual helper Popen handles and lifecycle FDs. Metadata failures, deferred guardian cleanup, EOF and record replacement were injected only by a temporary helper wrapper; no production source or bypass flag changed. Child private FDs/HUP inheritance, append-log preservation, actual TERM/KILL reaping, record preservation, same-lock retention after parent FD close, competing start refusal, TERM request retention and controlled retry were checked. A test-only backstop worker was available outside signal context; signal handler only sets a flag. Completion records distinguish whether it was used.

The temporary wrapper intentionally exits normally after its finally cleanup: helper_returncode=0 is the wrapper exit, while completion.rc records actual main(spawn) return (0 published, 2 failed). This harness does not assert the production __main__ OS exit mapping.

Limits: successful CLI handoff was kept inside a temporary helper harness so its child retained an out-of-band Popen until fixture cleanup; this does not prove application readiness or installed shell integration. Public shells remain unmigrated; no Action Gateway/audit coverage is claimed. Guardian cleanup failure was explicitly injected against real children. SIGKILL/host crash can defeat in-memory guardian ownership. No model, existing service, network, live-store or arbitrary numeric-PID signal was used. State/audit environment was temporary before imports. Initial/final RAM and all literal output follow.

```text
$ free -h (before)
               total        used        free      shared  buff/cache   available
Mem:            10Gi       7.2Gi       216Mi        83Mi       3.7Gi       3.6Gi
Swap:           15Gi       3.6Gi        12Gi
PASS actual spawn CLI b'published 21270\n' verified_live=True child_private_FDs_closed=True HUP_ignored=True existing_log_preserved=True
CLEANUP success helper_returncode= 0 completion= {'rc': 0, 'child_count': 1, 'codes': [-15], 'backstop': False} stdout= b'' stderr= b''
PASS publication/readback failure write1 ready= b'failed-cleanup-confirmed\n' child_returncodes= [-15] innocent_alive=True replacement_preserved= False
CLEANUP write1 helper_returncode= 0 completion= {'rc': 2, 'child_count': 1, 'codes': [-15], 'backstop': False} stdout= b'' stderr= b''
PASS publication/readback failure write2 ready= b'failed-cleanup-confirmed\n' child_returncodes= [-15] innocent_alive=True replacement_preserved= False
CLEANUP write2 helper_returncode= 0 completion= {'rc': 2, 'child_count': 1, 'codes': [-15], 'backstop': False} stdout= b'' stderr= b''
PASS publication/readback failure ignore ready= b'failed-cleanup-confirmed\n' child_returncodes= [-9] innocent_alive=True replacement_preserved= False
CLEANUP ignore helper_returncode= 0 completion= {'rc': 2, 'child_count': 1, 'codes': [-9], 'backstop': False} stdout= b'' stderr= b''
PASS publication/readback failure replace ready= b'failed-cleanup-confirmed\n' child_returncodes= [-15] innocent_alive=True replacement_preserved= True
CLEANUP replace helper_returncode= 0 completion= {'rc': 2, 'child_count': 1, 'codes': [-15], 'backstop': False} stdout= b'' stderr= b''
Competing launch rc= 2 stdout= 'competing launch blocked before spawn\n'
PASS retained guardian after parent FD close; same lock blocks competing start; exact-helper TERM request preserves live ownership
PASS controlled guardian retry: child reaped; helper exited; same lifecycle lock released
CLEANUP guardian helper_returncode= 0 completion= {'rc': 2, 'child_count': 1, 'codes': [-15], 'backstop': False} stdout= b'' stderr= b''
PASS broken readiness reader: no success, one child cleanup confirmed before helper exit
CLEANUP broken helper_returncode= 0 completion= {'rc': 2, 'child_count': 1, 'codes': [-15], 'backstop': False} stdout= b'' stderr= b''
PASS readiness EOF: invalid result, actual helper alive, parent keeps lock; no fallback spawn
PASS readiness EOF recovery: waited actual helper; child reaped; no second child
CLEANUP eof helper_returncode= 0 completion= {'rc': 2, 'child_count': 1, 'codes': [-15], 'backstop': False} stdout= b'' stderr= b''
PASS independent innocent fixture survived all launch/cleanup cases
Finally parent cleanup: all retained helper/innocent Popen handles reaped= 9
$ free -h (after)
               total        used        free      shared  buff/cache   available
Mem:            10Gi       7.2Gi       237Mi        83Mi       3.7Gi       3.6Gi
Swap:           15Gi       3.6Gi        12Gi
RESULT PASS
```
