# NEW-967 daemon shutdown grace disposable verification

2026-10-16. Independent result: PASS. Approved two-file hashes matched before/after.

Actual private _codey_locked_identity stop used the validated inherited lockFD and actual process_identity stop. A fail-closed interpreter wrapper accepted only this exact stop argv with canonical codeyOS timeout45, recorded it, and execed the real identity helper. Temporary HOME/state/config/audit/paths and ordinary retained Popen children only. The daemon-like fixture acknowledged TERM, slept6seconds for ordinary simulated cleanup, then exited normally0; helper observed confirmed death and removed unchanged PID/identity records, with an independently owned innocent fixture still alive. Finally all exact Popen handles were waited/reaped. Raw output continuously fsynced to /data/data/com.termux/files/usr/tmp/wp21_new967_live_raw.log.

Limits: ordinary six-second cleanup is simulated, not real daemon/model teardown. Only canonical daemon profile was live tested; unchanged other-profile5 and45/90 boundary/escalation behavior remain approved command-trace/fake-clock unit evidence. No real daemon/model/services/cloud/network/live stores/credentials or public service setup ran. Combined13f/client mechanisms are outside this two-file claim.

Literal output:

```text
$ free -h (before)
               total        used        free      shared  buff/cache   available
Mem:            10Gi       7.3Gi       603Mi        66Mi       3.1Gi       3.5Gi
Swap:           15Gi       5.6Gi        10Gi
Approved NEW967 two-file hashes matched
ACTUAL PRIVATE STOP COMMAND= ['/data/data/com.termux/files/usr/bin/python3', '-c', 'import os,sys;fd=int(sys.argv[1]);os.dup2(fd,200,inheritable=True);os.close(fd) if fd!=200 else None;os.execv(sys.argv[2],sys.argv[2:])', '4', '/data/data/com.termux/files/usr/bin/bash', '-c', 'source "$1"; _codey_locked_identity 200 stop codeyOS "$2"', 'fixture', '/data/data/com.termux/files/home/Codey-OS/lib/service_lifecycle.sh', '/data/data/com.termux/files/usr/tmp/new967-live-a4vwlpo8/daemon-like.pid']
ACTUAL PRIVATE STOP OSrc= 0 elapsed_seconds= 6.19 stdout= 'absent-dead\n' stderr= ''
PASS daemon-like fixture TERM acknowledged, ordinary cleanup6s, NORMAL child exit0 (not KILL), verified-dead records removed; innocent survives; actual profile timeout45 traced
Finally exact owned Popen handles reaped= 3 returncodes= [0, -15, 0]
Approved NEW967 two-file hashes matched
$ free -h (after)
               total        used        free      shared  buff/cache   available
Mem:            10Gi       7.3Gi       578Mi        66Mi       3.1Gi       3.5Gi
Swap:           15Gi       5.6Gi        10Gi
RESULT PASS
```
