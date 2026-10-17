# WP2.1 13d shell public-operation disposable audit verification

2026-10-16. Independent initial result: FAIL. Frozen6 hashes checked before; final hash check not reached.

Public codey/codeydOS/direct service_lifecycle frontends used actual gateway and retained fixed private-worker invocation, with every setup/profile/service helper simulated by the reviewed fail-closed fixture before effects. Actual JSONL rows verified one envelope per all-start/stop/restart, correct ACT/READ and static labels, after-worker disposition ordering, partial2/worker7/absenceREAD1 FAILED, no secret/prompt/config/log payload leakage. Config-show recursively redacted fixture values; log output stayed outside audit. Source-only was pure; public READ retained accepted fixed schema/checkpoint initialization without PID/config/lock creation. Bootstrap fakeTUI followed exactly the service envelope with original argv/env and exit23; interactive future actions were not treated as one audited service action.

Initial harness failure: the final event-count assertion incorrectly required an after-_worker_main event from lock-exec workers which legitimately os.exec into private Bash and do not return. The invalid --internal probe also incorrectly used the fixture interpreter allowlist rather than direct public parser invocation; the fixture denied it with91/BLOCKED, and teardown reported that rejected command attempt. No unsupported source operation executed. These are harness errors, not established source defects.

Reached public commands/audit assertions are recorded literally below and passed individually, including composite one-row authority/outcome/status, source bootstrap constraints, payload redaction/exclusion and fakeTUI23. Actual signal/ordinary-worker test and final hashes were NOT reached. No retry performed in this initial run. All reached fixed workers and Bash-owned simulated helper jobs had completed before the postcheck; teardown touched release marker and retained no actual service child. Raw output was fsynced continuously to /data/data/com.termux/files/usr/tmp/wp21_13d_shell_live_raw.log.

Limits: no actual application service/model/daemon/cloud/network/live store/credential contents ran. Private installed Python mechanics remain callable by same-UID arbitrary Python; no cryptographic anti-bypass claim. No public audit coverage is inferred for other13d native CLI/RPC changes, active NEW-966/968 or later foreign-upgrade work.

Literal output:

```text
$ free -h (before)
               total        used        free      shared  buff/cache   available
Mem:            10Gi       7.0Gi       742Mi        65Mi       3.2Gi       3.8Gi
Swap:           15Gi       5.2Gi        10Gi
Approved shell13d six-file SHA256 matched
SOURCE ONLY OSrc= 0 stdout= '' stderr= ''
PUBLIC COMMAND= ['/data/data/com.termux/files/usr/bin/bash', '/data/data/com.termux/files/home/Codey-OS/codey', 'status'] OSrc= 0 stdout= 'Codey-OS Services Status:\n  daemon: absent-dead\n  restoricon: absent-dead\n  aigentik: absent-dead\n  cloudflared: absent-dead\n  litestream: absent-dead\n  backup-docs: absent-dead\n' stderr= ''
AUDIT NEW= [{'ts': 1792204882.1991773, 'authority': 'READ', 'action': 'service.status.all', 'command': 'service status.all', 'outcome': 'allowed', 'reason': 'command executed'}]
PASS source pure; public READ only established fixed empty schema/checkpoint bootstrap
PUBLIC COMMAND= ['/data/data/com.termux/files/usr/bin/bash', '/data/data/com.termux/files/home/Codey-OS/codey', 'start'] OSrc= 0 stdout= 'Starting all Codey-OS services in background...\nDEAD\n  llama-server-8080 → stopped (verified owned-process exit)\n  daemon → started (verified process identity; application readiness pending)\n  restoricon → started (verified process identity; application readiness pending)\n  aigentik → started (verified process identity; application readiness pending)\n  cloudflared → started (verified process identity; application readiness pending)\n  Secrets → DR backup uploaded\n  litestream → started (verified process identity; application readiness pending)\n  backup-docs → started (verified process identity; application readiness pending)\n' stderr= ''
AUDIT NEW= [{'ts': 1792204883.6363702, 'authority': 'ACT', 'action': 'service.all.start', 'command': 'service all.start', 'outcome': 'allowed', 'reason': 'command executed'}]
PUBLIC COMMAND= ['/data/data/com.termux/files/usr/bin/bash', '/data/data/com.termux/files/home/Codey-OS/codey', 'stop'] OSrc= 0 stdout= 'DEAD\n  backup-docs → stopped (verified owned-process exit)\nDEAD\n  litestream → stopped (verified owned-process exit)\nDEAD\n  cloudflared → stopped (verified owned-process exit)\nDEAD\n  aigentik → stopped (verified owned-process exit)\nDEAD\n  restoricon → stopped (verified owned-process exit)\nDEAD\n  daemon → stopped (verified owned-process exit)\nDEAD\n  llama-server-8080 → stopped (verified owned-process exit)\n  Requested services stopped with verified exits.\n' stderr= ''
AUDIT NEW= [{'ts': 1792204884.3090534, 'authority': 'ACT', 'action': 'service.all.stop', 'command': 'service all.stop', 'outcome': 'allowed', 'reason': 'command executed'}]
PUBLIC COMMAND= ['/data/data/com.termux/files/usr/bin/bash', '/data/data/com.termux/files/home/Codey-OS/codey', 'restart'] OSrc= 0 stdout= 'Restarting all Codey-OS services...\nDEAD\n  backup-docs → stopped (verified owned-process exit)\nDEAD\n  litestream → stopped (verified owned-process exit)\nDEAD\n  cloudflared → stopped (verified owned-process exit)\nDEAD\n  aigentik → stopped (verified owned-process exit)\nDEAD\n  restoricon → stopped (verified owned-process exit)\nDEAD\n  daemon → stopped (verified owned-process exit)\nDEAD\n  llama-server-8080 → stopped (verified owned-process exit)\nDEAD\n  llama-server-8080 → stopped (verified owned-process exit)\n  daemon → started (verified process identity; application readiness pending)\n  restoricon → started (verified process identity; application readiness pending)\n  aigentik → started (verified process identity; application readiness pending)\n  cloudflared → started (verified process identity; application readiness pending)\n  Secrets → DR backup uploaded\n  litestream → started (verified process identity; application readiness pending)\n  backup-docs → started (verified process identity; application readiness pending)\n' stderr= ''
AUDIT NEW= [{'ts': 1792204886.0800946, 'authority': 'ACT', 'action': 'service.all.restart', 'command': 'service all.restart', 'outcome': 'allowed', 'reason': 'command executed'}]
PUBLIC COMMAND= ['/data/data/com.termux/files/usr/bin/bash', '/data/data/com.termux/files/home/Codey-OS/codeydOS', 'reload'] OSrc= 0 stdout= '' stderr= ''
AUDIT NEW= [{'ts': 1792204886.4153764, 'authority': 'ACT', 'action': 'service.daemon.reload', 'command': 'service daemon.reload', 'outcome': 'allowed', 'reason': 'command executed'}]
PUBLIC COMMAND= ['/data/data/com.termux/files/usr/bin/bash', '/data/data/com.termux/files/home/Codey-OS/codey-stop'] OSrc= 0 stdout= 'DEAD\n  backup-docs → stopped (verified owned-process exit)\nDEAD\n  litestream → stopped (verified owned-process exit)\nDEAD\n  cloudflared → stopped (verified owned-process exit)\nDEAD\n  aigentik → stopped (verified owned-process exit)\nDEAD\n  restoricon → stopped (verified owned-process exit)\nDEAD\n  daemon → stopped (verified owned-process exit)\nDEAD\n  llama-server-8080 → stopped (verified owned-process exit)\n  Requested services stopped with verified exits.\n' stderr= ''
AUDIT NEW= [{'ts': 1792204887.0795524, 'authority': 'ACT', 'action': 'service.all.stop', 'command': 'service all.stop', 'outcome': 'allowed', 'reason': 'command executed'}]
PUBLIC COMMAND= ['/data/data/com.termux/files/usr/bin/bash', '/data/data/com.termux/files/home/Codey-OS/codeydOS', 'status'] OSrc= 1 stdout= '  daemon: absent-dead\nModel: fixture disabled\n' stderr= 'Service operation failed; see operation output and audit.\n'
AUDIT NEW= [{'ts': 1792204887.3323736, 'authority': 'READ', 'action': 'service.daemon-status', 'command': 'service daemon-status', 'outcome': 'failed', 'reason': 'Service worker completed with exit 1; public status 1.'}]
PUBLIC COMMAND= ['/data/data/com.termux/files/usr/tmp/shell13d-q78hapjm/public/bin/python3', '/data/data/com.termux/files/home/Codey-OS/core/service_lifecycle.py', 'logs', 'daemon'] OSrc= 0 stdout= '=== daemon ===\nprivate-log-secret\n' stderr= ''
AUDIT NEW= [{'ts': 1792204887.550083, 'authority': 'READ', 'action': 'service.logs.daemon', 'command': 'service logs.daemon', 'outcome': 'allowed', 'reason': 'command executed'}]
PUBLIC COMMAND= ['/data/data/com.termux/files/usr/bin/bash', '/data/data/com.termux/files/home/Codey-OS/codey', 'config'] OSrc= 0 stdout= 'Config file: /data/data/com.termux/files/usr/tmp/shell13d-q78hapjm/public/redact-config.json (exists: True)\n\nActive configurations:\n  • Cloudflare Token: configured\n  • Restoricon API:   {\'host\': \'127.0.0.1\', \'port\': 8770, \'db_path\': \'/data/data/com.termux/files/usr/tmp/shell13d-q78hapjm/public/selected state/restoricon.db\'}\n  • Aigentik:         {\'dir\': \'/data/data/com.termux/files/usr/tmp/shell13d-q78hapjm/public/aigentik app\', \'port\': 8000}\n\nLoaded raw config:\n{\n  "nested": [\n    {\n      "API_KEY": "***redacted***"\n    }\n  ],\n  "secret": "***redacted***",\n  "normal": "visible"\n}\n' stderr= ''
AUDIT NEW= [{'ts': 1792204887.7906747, 'authority': 'READ', 'action': 'service.config-show', 'command': 'service config-show', 'outcome': 'allowed', 'reason': 'command executed'}]
PUBLIC COMMAND= ['/data/data/com.termux/files/usr/tmp/shell13d-q78hapjm/public/bin/python3', '/data/data/com.termux/files/home/Codey-OS/core/service_lifecycle.py', 'config-create'] OSrc= 0 stdout= 'Default config created at: /data/data/com.termux/files/usr/tmp/shell13d-q78hapjm/public/selected state/config.json\n' stderr= ''
AUDIT NEW= [{'ts': 1792204888.0053766, 'authority': 'ACT', 'action': 'service.config-create', 'command': 'service config-create', 'outcome': 'allowed', 'reason': 'command executed'}]
PUBLIC COMMAND= ['/data/data/com.termux/files/usr/bin/bash', '/data/data/com.termux/files/home/Codey-OS/codey', 'restart'] OSrc= 2 stdout= 'Restarting all Codey-OS services...\nDEAD\n  backup-docs → stopped (verified owned-process exit)\nDEAD\n  litestream → stopped (verified owned-process exit)\nDEAD\n  cloudflared → stopped (verified owned-process exit)\nUNSAFE\nDEAD\n  restoricon → stopped (verified owned-process exit)\nDEAD\n  daemon → stopped (verified owned-process exit)\nDEAD\n  llama-server-8080 → stopped (verified owned-process exit)\n' stderr= '  aigentik → stop not completed or identity unavailable\nService operation failed; see operation output and audit.\n'
AUDIT NEW= [{'ts': 1792204888.6594305, 'authority': 'ACT', 'action': 'service.all.restart', 'command': 'service all.restart', 'outcome': 'failed', 'reason': 'Service worker completed with exit 2; public status 2. Partial effects possible.'}]
PUBLIC COMMAND= ['/data/data/com.termux/files/usr/tmp/shell13d-q78hapjm/public/bin/python3', '/data/data/com.termux/files/home/Codey-OS/core/service_lifecycle.py', 'status', 'all'] OSrc= 7 stdout= '' stderr= 'Service operation failed; see operation output and audit.\n'
AUDIT NEW= [{'ts': 1792204888.8662558, 'authority': 'READ', 'action': 'service.status.all', 'command': 'service status.all', 'outcome': 'failed', 'reason': 'Service worker completed with exit 7; public status 7.'}]
BOOTSTRAP TUI OSrc= 23 stdout= 'DEAD\n  llama-server-8080 → stopped (verified owned-process exit)\n  daemon → started (verified process identity; application readiness pending)\n  restoricon → started (verified process identity; application readiness pending)\n  aigentik → started (verified process identity; application readiness pending)\n  cloudflared → started (verified process identity; application readiness pending)\n  Secrets → DR backup uploaded\n  litestream → started (verified process identity; application readiness pending)\n  backup-docs → started (verified process identity; application readiness pending)\n  TUI         → launching codeyOS...\n\n' stderr= ''
PASS bootstrap exactly service envelope before fakeTUI; originalargv/env/exit23 retained; no whole interactive-session audit
INVALID PUBLIC SELECTOR OSrc= 91 stdout= '' stderr= ''
Traceback (most recent call last):
  File "/data/data/com.termux/files/usr/tmp/shell13d_live.py", line 54, in <module>
    attempted=[e for e in m.events(h) if e['label']=='worker-before-audit'];finished=[e for e in m.events(h) if e['label']=='worker-disposition-before-audit'];assert len(attempted)==len(finished)==len(rows());print('PASS actual retained fixed-worker invocations=',len(attempted),'one audit per complete public operation; rows appear after worker disposition')
                                                                                                                                                                      ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError

During handling of the above exception, another exception occurred:

Traceback (most recent call last):
  File "/data/data/com.termux/files/usr/tmp/shell13d_live.py", line 56, in <module>
    try:next(gen)
        ~~~~^^^^^
  File "/data/data/com.termux/files/home/Codey-OS/tests/test_service_public_lifecycle.py", line 196, in harness
    assert all(event["label"] != "BLOCKED" for event in events(item)), "unknown external command attempted"
           ~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: unknown external command attempted
$ free -h (after)
               total        used        free      shared  buff/cache   available
Mem:            10Gi       7.0Gi       745Mi        65Mi       3.2Gi       3.8Gi
Swap:           15Gi       5.2Gi        10Gi
RESULT FAIL
```
