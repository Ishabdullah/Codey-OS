# WP2.1 13d shell focused resumed public-operation verification

2026-10-16. Independent resumed result: PASS. Frozen6 hashes checked before/after.

Initial FAIL/raw and previously reached whole-operation cases remain preserved. This coordinator-authorized focused harness resume corrected only instrumentation: direct unsupported-option parsing avoids fixture allowlist, and lock-exec workers are not expected to return after private os.exec. Focused all-stop ACT, status READ, config-create ACT and injected7 READ ran through actual public gateway/retained fixed worker with all service effects simulated/denied by the audited temporary interpreter. Four workers saw no new audit row before effects; only three returningREAD/config/injected7 workers generated after-return markers; lock-exec completed its actual public command before the observed row. Unsupported--internal direct public parser returned2 before worker/audit/service effects. Earlier initial-run successful public scope is not silently repeated or relabeled.

An independent real ordinary worker fixture replaced only private worker argv in a disposable subprocess. Parent received actual SIGTERM via its retained Popen while worker lived; gateway waited its natural exit0/reap and then returned143 with one FAILED/static interruption row. This is explicit test-only worker substitution, distinct from the real fixed-worker profile invocation above. All exact Popen/Bash-owned jobs were waited/reaped. Raw output continuously fsynced to /data/data/com.termux/files/usr/tmp/wp21_13d_shell_live_resumed_raw.log.

Limits: no actual application service/model/daemon/cloud/network/live store/credential contents ran. Private installed Python mechanics remain callable by same-UID arbitrary Python; no cryptographic anti-bypass claim. No public audit coverage is inferred for other13d native CLI/RPC changes, active NEW-966/968 or later foreign-upgrade work.

Literal output:

```text
$ free -h (before)
               total        used        free      shared  buff/cache   available
Mem:            10Gi       7.1Gi       712Mi        65Mi       3.2Gi       3.7Gi
Swap:           15Gi       5.2Gi        10Gi
Approved shell13d six-file SHA256 matched
PUBLIC COMMAND= ['/data/data/com.termux/files/usr/bin/bash', '/data/data/com.termux/files/home/Codey-OS/codey-stop'] OSrc= 0 stdout= 'DEAD\n  backup-docs → stopped (verified owned-process exit)\nDEAD\n  litestream → stopped (verified owned-process exit)\nDEAD\n  cloudflared → stopped (verified owned-process exit)\nDEAD\n  aigentik → stopped (verified owned-process exit)\nDEAD\n  restoricon → stopped (verified owned-process exit)\nDEAD\n  daemon → stopped (verified owned-process exit)\nDEAD\n  llama-server-8080 → stopped (verified owned-process exit)\n  Requested services stopped with verified exits.\n' stderr= ''
AUDIT NEW= [{'ts': 1792204962.0090914, 'authority': 'ACT', 'action': 'service.all.stop', 'command': 'service all.stop', 'outcome': 'allowed', 'reason': 'command executed'}]
PASS lock-exec actual public command completed/reaped before observed audit row; no impossible after-return marker required across private exec
PUBLIC COMMAND= ['/data/data/com.termux/files/usr/bin/bash', '/data/data/com.termux/files/home/Codey-OS/codey', 'status'] OSrc= 0 stdout= 'Codey-OS Services Status:\n  daemon: absent-dead\n  restoricon: absent-dead\n  aigentik: absent-dead\n  cloudflared: absent-dead\n  litestream: absent-dead\n  backup-docs: absent-dead\n' stderr= ''
AUDIT NEW= [{'ts': 1792204962.2706254, 'authority': 'READ', 'action': 'service.status.all', 'command': 'service status.all', 'outcome': 'allowed', 'reason': 'command executed'}]
PUBLIC COMMAND= ['/data/data/com.termux/files/usr/tmp/shell13d-o_ymunx_/public/bin/python3', '/data/data/com.termux/files/home/Codey-OS/core/service_lifecycle.py', 'config-create'] OSrc= 0 stdout= 'Default config created at: /data/data/com.termux/files/usr/tmp/shell13d-o_ymunx_/public/selected state/config.json\n' stderr= ''
AUDIT NEW= [{'ts': 1792204962.4861033, 'authority': 'ACT', 'action': 'service.config-create', 'command': 'service config-create', 'outcome': 'allowed', 'reason': 'command executed'}]
PUBLIC COMMAND= ['/data/data/com.termux/files/usr/tmp/shell13d-o_ymunx_/public/bin/python3', '/data/data/com.termux/files/home/Codey-OS/core/service_lifecycle.py', 'status', 'all'] OSrc= 7 stdout= '' stderr= 'Service operation failed; see operation output and audit.\n'
AUDIT NEW= [{'ts': 1792204962.7045302, 'authority': 'READ', 'action': 'service.status.all', 'command': 'service status.all', 'outcome': 'failed', 'reason': 'Service worker completed with exit 7; public status 7.'}]
DIRECT INVALID PUBLIC PARSER OSrc= 2 stdout= '' stderr= 'Service mechanics unavailable or unsafe\n'
PASS rows absent before ALL4 workers; after-return markers only3 returningREAD/config/injected7; direct unsupported option rejected before worker/audit/service effects
ACTUAL SIGNAL PARENT OSrc= 143 stdout= 'actual worker natural exit0 confirmed before public interruption143\n' stderr= 'Service operation failed; see operation output and audit.\n'
SIGNAL AUDIT= [{'ts': 1792204963.7925673, 'authority': 'READ', 'action': 'service.status.all', 'command': 'service status.all', 'outcome': 'failed', 'reason': 'Service worker completed with exit 0; public status 143. Interruption observed; worker disposition confirmed.'}]
PASS exact owned parent signaled; ordinary worker natural exit/reap preserved; FAILED interruption audit after disposition; no auto-kill/respawn
Approved shell13d six-file SHA256 matched
$ free -h (after)
               total        used        free      shared  buff/cache   available
Mem:            10Gi       7.1Gi       689Mi        65Mi       3.2Gi       3.7Gi
Swap:           15Gi       5.2Gi        10Gi
RESULT PASS
```
