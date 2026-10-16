# WP2.1 13c.2b.3 focused resumed public disposable verification

2026-10-16. Independent result: PASS.

Initial FAIL report remains preserved with its first40 passed public cases. The added41st case had incorrectly expected stopped daemon statusOS0; authorized harness-only correction expects the documented absent-dead/OS1. This focused resumed run repeats only that case and the previously not-reached actual metadata-lock cycle. No production source change. Raw output is flushed/fsynced on every write to /data/data/com.termux/files/usr/tmp/wp21_b3_live_resumed_raw.log before subsequent assertions.

Frozen18 SHA snapshot checked before/after; public start/reload/restart/stop/status use the audited fail-closed simulated profile harness. All setup/backup/profile effects remain stubbed. Only the separate metadata cycle uses an actual ordinary child.

The independent actual cycle runs a disposable daemon-like Python process manually attaching its own ordinary child to LlamaServer. Parent holds the actual model lifecycle lock while requesting stop; ordinary child is reaped and owner exits normally without forced kill. Parent observes preserved metadata, verifies dead identity, and removes unchanged records. No full daemon/model was started.

Limits: public fixed profile processes were simulated, not real application services. Owned-spawn actual-child mechanics were verified separately in b1/b2; this public run does not activate any application. Existing NEW-954/955 payload/exit issues remain13g; no client bug fix or public audit coverage claim. Relative custom-path choice remains pending. Frozen scope excludes concurrent13f/embed/inference/new client work. Initial/final RAM and complete literal command outputs follow.

```text
$ free -h (before)
               total        used        free      shared  buff/cache   available
Mem:            10Gi       7.1Gi       559Mi        78Mi       3.5Gi       3.7Gi
Swap:           15Gi       4.1Gi        11Gi
Frozen SHA256 snapshot verified: 18 files
BEGIN CASE 1 daemon public start/reload/restart/stop/status simulated fixed profile
PUBLIC COMMAND ['/data/data/com.termux/files/usr/bin/bash', '/data/data/com.termux/files/home/Codey-OS/codeydOS', 'start'] cwd= None OSrc= 0
STDOUT:
DEAD
  llama-server-8080 → stopped (verified owned-process exit)
  daemon → started (verified process identity; application readiness pending)
STDERR:

PUBLIC COMMAND ['/data/data/com.termux/files/usr/bin/bash', '/data/data/com.termux/files/home/Codey-OS/codeydOS', 'reload'] cwd= None OSrc= 0
STDOUT:

STDERR:

PUBLIC COMMAND ['/data/data/com.termux/files/usr/bin/bash', '/data/data/com.termux/files/home/Codey-OS/codeydOS', 'restart'] cwd= None OSrc= 0
STDOUT:
DEAD
  daemon → stopped (verified owned-process exit)
DEAD
  llama-server-8080 → stopped (verified owned-process exit)
DEAD
  llama-server-8080 → stopped (verified owned-process exit)
  daemon → started (verified process identity; application readiness pending)
STDERR:

PUBLIC COMMAND ['/data/data/com.termux/files/usr/bin/bash', '/data/data/com.termux/files/home/Codey-OS/codeydOS', 'stop'] cwd= None OSrc= 0
STDOUT:
DEAD
  daemon → stopped (verified owned-process exit)
DEAD
  llama-server-8080 → stopped (verified owned-process exit)
  Requested services stopped with verified exits.
STDERR:

PUBLIC COMMAND ['/data/data/com.termux/files/usr/bin/bash', '/data/data/com.termux/files/home/Codey-OS/codeydOS', 'status'] cwd= None OSrc= 1
STDOUT:
  daemon: absent-dead
Model: fixture disabled
STDERR:

PASS CASE 1 daemon public start/reload/restart/stop/status simulated fixed profile event_labels= ['adapter:lock-exec', 'identity:inspect:codeyOS', 'identity:stop:llama-server-8080', 'adapter:parse-ready', 'identity:spawn:codeyOS', 'profile:codeyOS', 'adapter:lock-exec', 'identity:signal:codeyOS', 'adapter:lock-exec', 'identity:stop:codeyOS', 'identity:stop:llama-server-8080', 'identity:inspect:codeyOS', 'identity:stop:llama-server-8080', 'identity:spawn:codeyOS', 'profile:codeyOS', 'adapter:parse-ready', 'adapter:lock-exec', 'identity:stop:codeyOS', 'identity:stop:llama-server-8080', 'adapter:status', 'model-status-stub']
All public profile evidence above uses audited fail-closed simulated service helpers; no real profile executable ran.
ACTUAL NONBLOCKING METADATA CYCLE: daemon-like OSrc= 0 stdout= 'daemon-like normal exit after ordinary child reaped\n' stderr= '' child= {'stopped': True, 'child_returncode': -15, 'process_cleared': True} parent kept model lock through normal process exit; bytes preserved then verified-dead cleanup=True
PASS actual owned ordinary-child metadata cycle; no forced daemon-like kill/model/service
Frozen SHA256 snapshot verified: 18 files
$ free -h (after)
               total        used        free      shared  buff/cache   available
Mem:            10Gi       7.1Gi       553Mi        78Mi       3.5Gi       3.7Gi
Swap:           15Gi       4.1Gi        11Gi
RESULT PASS public cases completed= 1
```
