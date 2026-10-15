# WP2.1 slice 13c.1 disposable-process live verification

2026-10-15. Independent on-device verification after source approval: PASS.

Read the fixture-safety incident and safe ordering correction first. Only actual fixture Popen children were recorded/signaled; finally cleanup retained every exact handle and reaped it. Temporary CODEY_STATE_DIR and audit were set before Codey imports. Cross-process CLI, sibling shell exec helper, boot/start/UID tampering, legacy-live refusal, real USR1 marker, TERM-ignore/KILL escalation, replaced-record refusal, inherited-FD lock retention/release and real daemon helper self-publication/shutdown were exercised. No models, existing services, live stores, network or placeholder PID signals.

Limits: boot/start/UID mismatches were injected by editing temporary identity metadata. Daemon helpers ran in a disposable Python child, without a daemon event loop. Loader wiring, publication failure fallback, and NEW-956/957 lifecycle repair were not live tested. Ordinary /proc identity checks retain the documented PID reuse race; no pidfd claim.

Literal output:

```text
$ free -h (before)
               total        used        free      shared  buff/cache   available
Mem:            10Gi       6.6Gi       1.1Gi        59Mi       3.4Gi       4.2Gi
Swap:           15Gi       4.4Gi        11Gi
CLI inspect owned rc= 0 stdout= 'running\n' stderr= ''
CLI stop owned rc= 0 stdout= 'absent-dead\n' stderr= ''
PASS publish -> cross-process stop/reap returncode= -15
CLI record sibling rc= 0 stdout= 'running\n' stderr= ''
CLI inspect sibling rc= 0 stdout= 'running\n' stderr= ''
CLI stop sibling rc= 0 stdout= 'absent-dead\n' stderr= ''
CLI inspect sibling rc= 1 stdout= 'absent-dead\n' stderr= ''
PASS sibling shell exec CLI publication and external stop
CLI inspect boot_id rc= 2 stdout= 'unsafe-unverifiable\n' stderr= ''
CLI stop boot_id rc= 2 stdout= 'unsafe-unverifiable\n' stderr= ''
PASS mismatch/legacy boot_id innocent_survives=True evidence_preserved=True
CLI inspect start_ticks rc= 2 stdout= 'unsafe-unverifiable\n' stderr= ''
CLI stop start_ticks rc= 2 stdout= 'unsafe-unverifiable\n' stderr= ''
PASS mismatch/legacy start_ticks innocent_survives=True evidence_preserved=True
CLI inspect uid rc= 2 stdout= 'unsafe-unverifiable\n' stderr= ''
CLI stop uid rc= 2 stdout= 'unsafe-unverifiable\n' stderr= ''
PASS mismatch/legacy uid innocent_survives=True evidence_preserved=True
CLI inspect legacy rc= 2 stdout= 'unsafe-unverifiable\n' stderr= ''
CLI stop legacy rc= 2 stdout= 'unsafe-unverifiable\n' stderr= ''
PASS mismatch/legacy legacy innocent_survives=True evidence_preserved=True
CLI signal reload rc= 0 stdout= 'running\n' stderr= ''
CLI stop reload rc= 0 stdout= 'absent-dead\n' stderr= ''
PASS real SIGUSR1 handler wrote marker; no HUP
CLI stop ignore rc= 0 stdout= 'absent-dead\n' stderr= ''
PASS TERM ignored -> KILL confirmed returncode= -9
PASS replaced PID record preserved; original and innocent children survive refusal
CLI record lock rc= 0 stdout= 'running\n' stderr= ''
Inherited-FD lock probe rc= 0 stdout= 'lock remains held\n'
CLI stop lock rc= 0 stdout= 'absent-dead\n' stderr= ''
PASS inherited helper did not unlock launcher; lock released after parent context
Daemon helpers rc= 0 stdout= 'PASS daemon own prewrite/publication; shutdown nonblocking under lock; later cleanup true\n' stderr= ''
Finally cleanup: exact fixture Popen handles= 8 all_reaped= True
PASS all isolated scenarios; temporary state removed.
$ free -h (after)
               total        used        free      shared  buff/cache   available
Mem:            10Gi       6.7Gi       1.0Gi        59Mi       3.4Gi       4.2Gi
Swap:           15Gi       4.4Gi        11Gi
```
