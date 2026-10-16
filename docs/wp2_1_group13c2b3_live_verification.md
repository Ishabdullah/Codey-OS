# WP2.1 13c.2b.3 public disposable verification

2026-10-16. Independent result: FAIL.

Initial frozen 18-file reviewer SHA snapshot checked before execution; final recheck was not reached in this failed run. Independent orchestrator reuses the source-audited public fixture isolation/allowlist primitives and adds literal command-result capture plus an independent actual ordinary-child metadata-lock cycle. Public profile tests simulate service helpers: every interpreter/setup/Litestream secrets backup/cloud/backup/Aigentik/Restoricon launch is stubbed or denied before invocation. Dummy credentials/token only; no real credential contents. Synthetic protocol PIDs are never signaled. Guarded identity refusals replace all OS signaling; actual orphan/UDS identity fixtures retain exact Popen handles and finally reap them. All six symlink-installed entrypoints/root failure, environment/TUI exits, six fixed profiles/composites/concurrent exclusion/guardian/private protocol and custom-spaces UDS were exercised.

Reached scope: first 40 public cases passed. Added case41 completed simulated daemon start/reload/restart/stop with OS0, then codeydOS status reported absent-dead with OS1. The added harness wrongly required OS0 for status after stop and raised. This matches the existing audited status convention; no source contradiction is established. Per-case finally cleanup completed. No rerun was performed in this initial run.

The independent actual ordinary-child model metadata-lock cycle was scheduled after case41 and was NOT reached. Final frozen SHA recheck likewise was NOT reached; initial18-file hash verification passed. The raw FAIL output below is preserved. No actual daemon or model process ran.

Limits: public fixed profile processes were simulated, not real application services. Owned-spawn actual-child mechanics were verified separately in b1/b2; this public run does not activate any application. Existing NEW-954/955 payload/exit issues remain13g; no client bug fix or public audit coverage claim. Relative custom-path choice remains pending. Frozen scope excludes concurrent13f/embed/inference/new client work. Initial/final RAM and complete literal command outputs follow.

```text
$ free -h (before)
               total        used        free      shared  buff/cache   available
Mem:            10Gi       7.0Gi       650Mi        77Mi       3.5Gi       3.9Gi
Swap:           15Gi       4.1Gi        11Gi
Frozen SHA256 snapshot verified: 18 files
BEGIN CASE 1 source/status pure missing root
PUBLIC COMMAND ['/data/data/com.termux/files/usr/bin/bash', '/data/data/com.termux/files/home/Codey-OS/codey', 'status'] cwd= None OSrc= 0
STDOUT:
Codey-OS Services Status:
  daemon: absent-dead
  restoricon: absent-dead
  aigentik: absent-dead
  cloudflared: absent-dead
  litestream: absent-dead
  backup-docs: absent-dead
STDERR:

PASS CASE 1 source/status pure missing root event_labels= ['adapter:status']
BEGIN CASE 2 six public fixed start profiles and setup/backup stubs
PUBLIC COMMAND ['/data/data/com.termux/files/usr/bin/bash', '/data/data/com.termux/files/home/Codey-OS/codey', 'start'] cwd= None OSrc= 0
STDOUT:
Starting all Codey-OS services in background...
DEAD
  llama-server-8080 → stopped (verified owned-process exit)
  daemon → started (verified process identity; application readiness pending)
  restoricon → started (verified process identity; application readiness pending)
  aigentik → started (verified process identity; application readiness pending)
  cloudflared → started (verified process identity; application readiness pending)
  Secrets → DR backup uploaded
  litestream → started (verified process identity; application readiness pending)
  backup-docs → started (verified process identity; application readiness pending)
STDERR:

PUBLIC COMMAND ['/data/data/com.termux/files/usr/bin/bash', '/data/data/com.termux/files/home/Codey-OS/codey', 'start'] cwd= None OSrc= 0
STDOUT:
Starting all Codey-OS services in background...
  daemon → already running (verified identity)
  restoricon → already running (verified identity)
  aigentik → already running (verified identity)
  cloudflared → already running (verified identity)
  litestream → already running (verified identity)
  backup-docs → already running (verified identity)
STDERR:

PASS CASE 2 six public fixed start profiles and setup/backup stubs event_labels= ['adapter:lock-exec', 'identity:inspect:codeyOS', 'identity:stop:llama-server-8080', 'identity:spawn:codeyOS', 'profile:codeyOS', 'adapter:parse-ready', 'identity:inspect:restoricon-api', 'adapter:parse-ready', 'identity:spawn:restoricon-api', 'profile:restoricon-api', 'identity:inspect:aigentik', 'adapter:parse-ready', 'identity:spawn:aigentik', 'profile:aigentik', 'identity:inspect:cloudflared', 'adapter:parse-ready', 'identity:spawn:cloudflared', 'profile:cloudflared', 'identity:inspect:litestream', 'setup-litestream-stub', 'timeout-secrets-stub', 'backup-secrets-stub', 'adapter:parse-ready', 'identity:spawn:litestream', 'profile:litestream', 'identity:inspect:backup-docs', 'identity:spawn:backup-docs', 'profile:backup-docs', 'adapter:parse-ready', 'adapter:lock-exec', 'identity:inspect:codeyOS', 'identity:inspect:restoricon-api', 'identity:inspect:aigentik', 'identity:inspect:cloudflared', 'identity:inspect:litestream', 'identity:inspect:backup-docs']
BEGIN CASE 3 composite stop all; restart abort on failure
PUBLIC COMMAND ['/data/data/com.termux/files/usr/bin/bash', '/data/data/com.termux/files/home/Codey-OS/codey-stop'] cwd= None OSrc= 2
STDOUT:
DEAD
  backup-docs → stopped (verified owned-process exit)
DEAD
  litestream → stopped (verified owned-process exit)
DEAD
  cloudflared → stopped (verified owned-process exit)
UNSAFE
DEAD
  restoricon → stopped (verified owned-process exit)
DEAD
  daemon → stopped (verified owned-process exit)
DEAD
  llama-server-8080 → stopped (verified owned-process exit)
STDERR:
  aigentik → stop not completed or identity unavailable
PUBLIC COMMAND ['/data/data/com.termux/files/usr/bin/bash', '/data/data/com.termux/files/home/Codey-OS/codey', 'restart'] cwd= None OSrc= 2
STDOUT:
Restarting all Codey-OS services...
DEAD
  backup-docs → stopped (verified owned-process exit)
DEAD
  litestream → stopped (verified owned-process exit)
DEAD
  cloudflared → stopped (verified owned-process exit)
UNSAFE
DEAD
  restoricon → stopped (verified owned-process exit)
DEAD
  daemon → stopped (verified owned-process exit)
DEAD
  llama-server-8080 → stopped (verified owned-process exit)
STDERR:
  aigentik → stop not completed or identity unavailable
PASS CASE 3 composite stop all; restart abort on failure event_labels= ['adapter:lock-exec', 'identity:stop:backup-docs', 'identity:stop:litestream', 'identity:stop:cloudflared', 'identity:stop:aigentik', 'identity:stop:restoricon-api', 'identity:stop:codeyOS', 'identity:stop:llama-server-8080', 'adapter:lock-exec', 'identity:stop:backup-docs', 'identity:stop:litestream', 'identity:stop:cloudflared', 'identity:stop:aigentik', 'identity:stop:restoricon-api', 'identity:stop:codeyOS', 'identity:stop:llama-server-8080']
BEGIN CASE 4 bootstrap environment/TUI OS23 codey[]
PUBLIC COMMAND ['/data/data/com.termux/files/usr/bin/bash', '/data/data/com.termux/files/home/Codey-OS/codey'] cwd= None OSrc= 23
STDOUT:
DEAD
  llama-server-8080 → stopped (verified owned-process exit)
  daemon → started (verified process identity; application readiness pending)
  restoricon → started (verified process identity; application readiness pending)
  aigentik → started (verified process identity; application readiness pending)
  cloudflared → started (verified process identity; application readiness pending)
  Secrets → DR backup uploaded
  litestream → started (verified process identity; application readiness pending)
  backup-docs → started (verified process identity; application readiness pending)
  TUI         → launching codeyOS...

STDERR:

PASS CASE 4 bootstrap environment/TUI OS23 codey[] event_labels= ['adapter:lock-exec', 'identity:inspect:codeyOS', 'identity:stop:llama-server-8080', 'adapter:parse-ready', 'identity:spawn:codeyOS', 'profile:codeyOS', 'identity:inspect:restoricon-api', 'adapter:parse-ready', 'identity:spawn:restoricon-api', 'profile:restoricon-api', 'identity:inspect:aigentik', 'identity:spawn:aigentik', 'profile:aigentik', 'adapter:parse-ready', 'identity:inspect:cloudflared', 'adapter:parse-ready', 'identity:spawn:cloudflared', 'profile:cloudflared', 'identity:inspect:litestream', 'setup-litestream-stub', 'timeout-secrets-stub', 'backup-secrets-stub', 'identity:spawn:litestream', 'profile:litestream', 'adapter:parse-ready', 'identity:inspect:backup-docs', 'identity:spawn:backup-docs', 'profile:backup-docs', 'adapter:parse-ready', 'TUI']
BEGIN CASE 5 bootstrap environment/TUI OS23 codey['a prompt', '--yolo']
PUBLIC COMMAND ['/data/data/com.termux/files/usr/bin/bash', '/data/data/com.termux/files/home/Codey-OS/codey', 'a prompt', '--yolo'] cwd= None OSrc= 23
STDOUT:
DEAD
  llama-server-8080 → stopped (verified owned-process exit)
  daemon → started (verified process identity; application readiness pending)
  restoricon → started (verified process identity; application readiness pending)
  aigentik → started (verified process identity; application readiness pending)
  cloudflared → started (verified process identity; application readiness pending)
  Secrets → DR backup uploaded
  litestream → started (verified process identity; application readiness pending)
  backup-docs → started (verified process identity; application readiness pending)
  TUI         → launching codeyOS...

STDERR:

PASS CASE 5 bootstrap environment/TUI OS23 codey['a prompt', '--yolo'] event_labels= ['adapter:lock-exec', 'identity:inspect:codeyOS', 'identity:stop:llama-server-8080', 'adapter:parse-ready', 'identity:spawn:codeyOS', 'profile:codeyOS', 'identity:inspect:restoricon-api', 'identity:spawn:restoricon-api', 'profile:restoricon-api', 'adapter:parse-ready', 'identity:inspect:aigentik', 'identity:spawn:aigentik', 'profile:aigentik', 'adapter:parse-ready', 'identity:inspect:cloudflared', 'identity:spawn:cloudflared', 'profile:cloudflared', 'adapter:parse-ready', 'identity:inspect:litestream', 'setup-litestream-stub', 'timeout-secrets-stub', 'backup-secrets-stub', 'adapter:parse-ready', 'identity:spawn:litestream', 'profile:litestream', 'identity:inspect:backup-docs', 'identity:spawn:backup-docs', 'profile:backup-docs', 'adapter:parse-ready', 'TUI']
BEGIN CASE 6 bootstrap environment/TUI OS23 codey['start', 'prompt']
PUBLIC COMMAND ['/data/data/com.termux/files/usr/bin/bash', '/data/data/com.termux/files/home/Codey-OS/codey', 'start', 'prompt'] cwd= None OSrc= 23
STDOUT:
DEAD
  llama-server-8080 → stopped (verified owned-process exit)
  daemon → started (verified process identity; application readiness pending)
  restoricon → started (verified process identity; application readiness pending)
  aigentik → started (verified process identity; application readiness pending)
  cloudflared → started (verified process identity; application readiness pending)
  Secrets → DR backup uploaded
  litestream → started (verified process identity; application readiness pending)
  backup-docs → started (verified process identity; application readiness pending)
STDERR:

PASS CASE 6 bootstrap environment/TUI OS23 codey['start', 'prompt'] event_labels= ['adapter:lock-exec', 'identity:inspect:codeyOS', 'identity:stop:llama-server-8080', 'adapter:parse-ready', 'identity:spawn:codeyOS', 'profile:codeyOS', 'identity:inspect:restoricon-api', 'identity:spawn:restoricon-api', 'adapter:parse-ready', 'profile:restoricon-api', 'identity:inspect:aigentik', 'adapter:parse-ready', 'identity:spawn:aigentik', 'profile:aigentik', 'identity:inspect:cloudflared', 'identity:spawn:cloudflared', 'profile:cloudflared', 'adapter:parse-ready', 'identity:inspect:litestream', 'setup-litestream-stub', 'timeout-secrets-stub', 'backup-secrets-stub', 'adapter:parse-ready', 'identity:spawn:litestream', 'profile:litestream', 'identity:inspect:backup-docs', 'adapter:parse-ready', 'identity:spawn:backup-docs', 'profile:backup-docs', 'TUI']
BEGIN CASE 7 bootstrap environment/TUI OS23 codey-start['hello world']
PUBLIC COMMAND ['/data/data/com.termux/files/usr/bin/bash', '/data/data/com.termux/files/home/Codey-OS/codey-start', 'hello world'] cwd= None OSrc= 23
STDOUT:
DEAD
  llama-server-8080 → stopped (verified owned-process exit)
  daemon → started (verified process identity; application readiness pending)
  restoricon → started (verified process identity; application readiness pending)
  aigentik → started (verified process identity; application readiness pending)
  cloudflared → started (verified process identity; application readiness pending)
  Secrets → DR backup uploaded
  litestream → started (verified process identity; application readiness pending)
  backup-docs → started (verified process identity; application readiness pending)
  TUI         → launching codeyOS...

STDERR:

PASS CASE 7 bootstrap environment/TUI OS23 codey-start['hello world'] event_labels= ['adapter:lock-exec', 'identity:inspect:codeyOS', 'identity:stop:llama-server-8080', 'identity:spawn:codeyOS', 'profile:codeyOS', 'adapter:parse-ready', 'identity:inspect:restoricon-api', 'adapter:parse-ready', 'identity:spawn:restoricon-api', 'profile:restoricon-api', 'identity:inspect:aigentik', 'adapter:parse-ready', 'identity:spawn:aigentik', 'profile:aigentik', 'identity:inspect:cloudflared', 'adapter:parse-ready', 'identity:spawn:cloudflared', 'profile:cloudflared', 'identity:inspect:litestream', 'setup-litestream-stub', 'timeout-secrets-stub', 'backup-secrets-stub', 'adapter:parse-ready', 'identity:spawn:litestream', 'profile:litestream', 'identity:inspect:backup-docs', 'identity:spawn:backup-docs', 'profile:backup-docs', 'adapter:parse-ready', 'TUI']
BEGIN CASE 8 failed bootstrap never TUI
PUBLIC COMMAND ['/data/data/com.termux/files/usr/bin/bash', '/data/data/com.termux/files/home/Codey-OS/codey-start'] cwd= None OSrc= 2
STDOUT:
DEAD
  llama-server-8080 → stopped (verified owned-process exit)
  daemon → started (verified process identity; application readiness pending)
STDERR:
  restoricon → launch failed; partial state may require inspection
PASS CASE 8 failed bootstrap never TUI event_labels= ['adapter:lock-exec', 'identity:inspect:codeyOS', 'identity:stop:llama-server-8080', 'adapter:parse-ready', 'identity:spawn:codeyOS', 'profile:codeyOS', 'identity:inspect:restoricon-api', 'adapter:parse-ready', 'identity:spawn:restoricon-api', 'profile:restoricon-api']
BEGIN CASE 9 installed symlink root codey
PUBLIC COMMAND ['/data/data/com.termux/files/usr/bin/bash', '/data/data/com.termux/files/usr/tmp/b3-live-4e5lp31c/case-9/installed links/codey', 'help'] cwd= /data/data/com.termux/files/usr/tmp/b3-live-4e5lp31c/case-9 OSrc= 0
STDOUT:
Codey-OS Unified Command & Service Orchestrator

Usage:
  codey [command] [arguments...]

Commands:
  (no args)       Start all services and enter interactive TUI (codeyOS)
  start           Start all services in background
  stop            Stop all Codey-OS services cleanly
  status          Show status of all services and daemon model health
  restart         Restart all services cleanly
  logs [service]  Show service logs (daemon, restoricon, aigentik, cloudflare, litestream, backup-docs)
  config          Show active configuration settings
  help, --help    Show this help message

Options & Passthrough:
  Any other command or flag (e.g. codey "Fix bug in main.py") automatically
  ensures all services are running and passes arguments directly to codeyOS.
STDERR:

PASS CASE 9 installed symlink root codey event_labels= []
BEGIN CASE 10 installed symlink root codey-start
PUBLIC COMMAND ['/data/data/com.termux/files/usr/bin/bash', '/data/data/com.termux/files/usr/tmp/b3-live-4e5lp31c/case-10/installed links/codey-start'] cwd= /data/data/com.termux/files/usr/tmp/b3-live-4e5lp31c/case-10 OSrc= 0
STDOUT:
DEAD
  llama-server-8080 → stopped (verified owned-process exit)
  daemon → started (verified process identity; application readiness pending)
  restoricon → started (verified process identity; application readiness pending)
  aigentik → started (verified process identity; application readiness pending)
  cloudflared → started (verified process identity; application readiness pending)
  Secrets → DR backup uploaded
  litestream → started (verified process identity; application readiness pending)
  backup-docs → started (verified process identity; application readiness pending)
  TUI         → launching codeyOS...

STDERR:

PASS CASE 10 installed symlink root codey-start event_labels= ['adapter:lock-exec', 'identity:inspect:codeyOS', 'identity:stop:llama-server-8080', 'adapter:parse-ready', 'identity:spawn:codeyOS', 'profile:codeyOS', 'identity:inspect:restoricon-api', 'identity:spawn:restoricon-api', 'profile:restoricon-api', 'adapter:parse-ready', 'identity:inspect:aigentik', 'adapter:parse-ready', 'identity:spawn:aigentik', 'profile:aigentik', 'identity:inspect:cloudflared', 'identity:spawn:cloudflared', 'profile:cloudflared', 'adapter:parse-ready', 'identity:inspect:litestream', 'setup-litestream-stub', 'timeout-secrets-stub', 'backup-secrets-stub', 'identity:spawn:litestream', 'profile:litestream', 'adapter:parse-ready', 'identity:inspect:backup-docs', 'adapter:parse-ready', 'identity:spawn:backup-docs', 'profile:backup-docs', 'TUI']
BEGIN CASE 11 installed symlink root codey-stop
PUBLIC COMMAND ['/data/data/com.termux/files/usr/bin/bash', '/data/data/com.termux/files/usr/tmp/b3-live-4e5lp31c/case-11/installed links/codey-stop'] cwd= /data/data/com.termux/files/usr/tmp/b3-live-4e5lp31c/case-11 OSrc= 0
STDOUT:
DEAD
  backup-docs → stopped (verified owned-process exit)
DEAD
  litestream → stopped (verified owned-process exit)
DEAD
  cloudflared → stopped (verified owned-process exit)
DEAD
  aigentik → stopped (verified owned-process exit)
DEAD
  restoricon → stopped (verified owned-process exit)
DEAD
  daemon → stopped (verified owned-process exit)
DEAD
  llama-server-8080 → stopped (verified owned-process exit)
  Requested services stopped with verified exits.
STDERR:

PASS CASE 11 installed symlink root codey-stop event_labels= ['adapter:lock-exec', 'identity:stop:backup-docs', 'identity:stop:litestream', 'identity:stop:cloudflared', 'identity:stop:aigentik', 'identity:stop:restoricon-api', 'identity:stop:codeyOS', 'identity:stop:llama-server-8080']
BEGIN CASE 12 installed symlink root codeydOS
PUBLIC COMMAND ['/data/data/com.termux/files/usr/bin/bash', '/data/data/com.termux/files/usr/tmp/b3-live-4e5lp31c/case-12/installed links/codeydOS', 'status'] cwd= /data/data/com.termux/files/usr/tmp/b3-live-4e5lp31c/case-12 OSrc= 1
STDOUT:
  daemon: absent-dead
Model: fixture disabled
STDERR:

PASS CASE 12 installed symlink root codeydOS event_labels= ['adapter:status', 'model-status-stub']
BEGIN CASE 13 installed symlink root codeyOS
PUBLIC COMMAND ['/data/data/com.termux/files/usr/bin/bash', '/data/data/com.termux/files/usr/tmp/b3-live-4e5lp31c/case-13/installed links/codeyOS', 'hello'] cwd= /data/data/com.termux/files/usr/tmp/b3-live-4e5lp31c/case-13 OSrc= 0
STDOUT:

STDERR:

PASS CASE 13 installed symlink root codeyOS event_labels= ['adapter:paths', 'direct-main-stub']
BEGIN CASE 14 installed symlink root codey-metrics
PUBLIC COMMAND ['/data/data/com.termux/files/usr/bin/bash', '/data/data/com.termux/files/usr/tmp/b3-live-4e5lp31c/case-14/installed links/codey-metrics', 'doctor'] cwd= /data/data/com.termux/files/usr/tmp/b3-live-4e5lp31c/case-14 OSrc= 17
STDOUT:

STDERR:

PASS CASE 14 installed symlink root codey-metrics event_labels= ['metrics-stub']
BEGIN CASE 15 actual innocent orphan diagnostic aigentik
PUBLIC COMMAND ['/data/data/com.termux/files/usr/bin/bash', '-c', 'source "$1"; "$2"', 'fixture', '/data/data/com.termux/files/home/Codey-OS/lib/service_manager.sh', 'status_aigentik'] cwd= None OSrc= 1
STDOUT:
  aigentik: absent-dead
  aigentik: UNTRACKED matches (diagnostic only): 20351
STDERR:

PUBLIC COMMAND ['/data/data/com.termux/files/usr/bin/bash', '-c', 'source "$1"; "$2"', 'fixture', '/data/data/com.termux/files/home/Codey-OS/lib/service_manager.sh', 'start_aigentik'] cwd= None OSrc= 2
STDOUT:

STDERR:
  aigentik → startup blocked by UNTRACKED matches (diagnostic only): 20351
PUBLIC COMMAND ['/data/data/com.termux/files/usr/bin/bash', '-c', 'source "$1"; "$2"', 'fixture', '/data/data/com.termux/files/home/Codey-OS/lib/service_manager.sh', 'stop_aigentik'] cwd= None OSrc= 2
STDOUT:
DEAD
  aigentik → stopped (verified owned-process exit)
STDERR:
  aigentik → UNTRACKED matches preserved (diagnostic only): 20351
PASS CASE 15 actual innocent orphan diagnostic aigentik event_labels= ['adapter:status', 'adapter:lock-exec', 'identity:inspect:aigentik', 'adapter:lock-exec', 'identity:stop:aigentik']
BEGIN CASE 16 actual innocent orphan diagnostic litestream
PUBLIC COMMAND ['/data/data/com.termux/files/usr/bin/bash', '-c', 'source "$1"; "$2"', 'fixture', '/data/data/com.termux/files/home/Codey-OS/lib/service_manager.sh', 'status_litestream'] cwd= None OSrc= 1
STDOUT:
  litestream: absent-dead
  litestream: UNTRACKED matches (diagnostic only): 20369
STDERR:

PUBLIC COMMAND ['/data/data/com.termux/files/usr/bin/bash', '-c', 'source "$1"; "$2"', 'fixture', '/data/data/com.termux/files/home/Codey-OS/lib/service_manager.sh', 'start_litestream'] cwd= None OSrc= 2
STDOUT:

STDERR:
  litestream → startup blocked by UNTRACKED matches (diagnostic only): 20369
PUBLIC COMMAND ['/data/data/com.termux/files/usr/bin/bash', '-c', 'source "$1"; "$2"', 'fixture', '/data/data/com.termux/files/home/Codey-OS/lib/service_manager.sh', 'stop_litestream'] cwd= None OSrc= 2
STDOUT:
DEAD
  litestream → stopped (verified owned-process exit)
STDERR:
  litestream → UNTRACKED matches preserved (diagnostic only): 20369
PASS CASE 16 actual innocent orphan diagnostic litestream event_labels= ['adapter:status', 'adapter:lock-exec', 'identity:inspect:litestream', 'adapter:lock-exec', 'identity:stop:litestream']
BEGIN CASE 17 actual innocent orphan diagnostic backup-docs
PUBLIC COMMAND ['/data/data/com.termux/files/usr/bin/bash', '-c', 'source "$1"; "$2"', 'fixture', '/data/data/com.termux/files/home/Codey-OS/lib/service_manager.sh', 'status_backup_docs'] cwd= None OSrc= 1
STDOUT:
  backup-docs: absent-dead
  backup-docs: UNTRACKED matches (diagnostic only): 20425
STDERR:

PUBLIC COMMAND ['/data/data/com.termux/files/usr/bin/bash', '-c', 'source "$1"; "$2"', 'fixture', '/data/data/com.termux/files/home/Codey-OS/lib/service_manager.sh', 'start_backup_docs'] cwd= None OSrc= 2
STDOUT:

STDERR:
  backup-docs → startup blocked by UNTRACKED matches (diagnostic only): 20425
PUBLIC COMMAND ['/data/data/com.termux/files/usr/bin/bash', '-c', 'source "$1"; "$2"', 'fixture', '/data/data/com.termux/files/home/Codey-OS/lib/service_manager.sh', 'stop_backup_docs'] cwd= None OSrc= 2
STDOUT:
DEAD
  backup-docs → stopped (verified owned-process exit)
STDERR:
  backup-docs → UNTRACKED matches preserved (diagnostic only): 20425
PASS CASE 17 actual innocent orphan diagnostic backup-docs event_labels= ['adapter:status', 'adapter:lock-exec', 'identity:inspect:backup-docs', 'adapter:lock-exec', 'identity:stop:backup-docs']
BEGIN CASE 18 guarded actual identity refusal 0
PUBLIC COMMAND ['/data/data/com.termux/files/usr/bin/bash', '-c', 'source "$1"; "$2"', 'fixture', '/data/data/com.termux/files/home/Codey-OS/lib/service_manager.sh', 'start_restoricon'] cwd= None OSrc= 2
STDOUT:

STDERR:
  restoricon → startup blocked: unsafe/unverifiable identity
PUBLIC COMMAND ['/data/data/com.termux/files/usr/bin/bash', '-c', 'source "$1"; "$2"', 'fixture', '/data/data/com.termux/files/home/Codey-OS/lib/service_manager.sh', 'stop_restoricon'] cwd= None OSrc= 2
STDOUT:
unsafe-unverifiable
STDERR:
  restoricon → stop not completed or identity unavailable
PASS CASE 18 guarded actual identity refusal 0 event_labels= ['adapter:lock-exec', 'adapter:lock-exec']
BEGIN CASE 19 guarded actual identity refusal -1
PUBLIC COMMAND ['/data/data/com.termux/files/usr/bin/bash', '-c', 'source "$1"; "$2"', 'fixture', '/data/data/com.termux/files/home/Codey-OS/lib/service_manager.sh', 'start_restoricon'] cwd= None OSrc= 2
STDOUT:

STDERR:
  restoricon → startup blocked: unsafe/unverifiable identity
PUBLIC COMMAND ['/data/data/com.termux/files/usr/bin/bash', '-c', 'source "$1"; "$2"', 'fixture', '/data/data/com.termux/files/home/Codey-OS/lib/service_manager.sh', 'stop_restoricon'] cwd= None OSrc= 2
STDOUT:
unsafe-unverifiable
STDERR:
  restoricon → stop not completed or identity unavailable
PASS CASE 19 guarded actual identity refusal -1 event_labels= ['adapter:lock-exec', 'adapter:lock-exec']
BEGIN CASE 20 guarded actual identity refusal malformed
PUBLIC COMMAND ['/data/data/com.termux/files/usr/bin/bash', '-c', 'source "$1"; "$2"', 'fixture', '/data/data/com.termux/files/home/Codey-OS/lib/service_manager.sh', 'start_restoricon'] cwd= None OSrc= 2
STDOUT:

STDERR:
  restoricon → startup blocked: unsafe/unverifiable identity
PUBLIC COMMAND ['/data/data/com.termux/files/usr/bin/bash', '-c', 'source "$1"; "$2"', 'fixture', '/data/data/com.termux/files/home/Codey-OS/lib/service_manager.sh', 'stop_restoricon'] cwd= None OSrc= 2
STDOUT:
unsafe-unverifiable
STDERR:
  restoricon → stop not completed or identity unavailable
PASS CASE 20 guarded actual identity refusal malformed event_labels= ['adapter:lock-exec', 'adapter:lock-exec']
BEGIN CASE 21 guarded actual identity refusal legacy-live
PUBLIC COMMAND ['/data/data/com.termux/files/usr/bin/bash', '-c', 'source "$1"; "$2"', 'fixture', '/data/data/com.termux/files/home/Codey-OS/lib/service_manager.sh', 'start_restoricon'] cwd= None OSrc= 2
STDOUT:

STDERR:
  restoricon → startup blocked: unsafe/unverifiable identity
PUBLIC COMMAND ['/data/data/com.termux/files/usr/bin/bash', '-c', 'source "$1"; "$2"', 'fixture', '/data/data/com.termux/files/home/Codey-OS/lib/service_manager.sh', 'stop_restoricon'] cwd= None OSrc= 2
STDOUT:
unsafe-unverifiable
STDERR:
  restoricon → stop not completed or identity unavailable
PASS CASE 21 guarded actual identity refusal legacy-live event_labels= ['adapter:lock-exec', 'adapter:lock-exec']
BEGIN CASE 22 guarded actual identity refusal boot
PUBLIC COMMAND ['/data/data/com.termux/files/usr/bin/bash', '-c', 'source "$1"; "$2"', 'fixture', '/data/data/com.termux/files/home/Codey-OS/lib/service_manager.sh', 'start_restoricon'] cwd= None OSrc= 2
STDOUT:

STDERR:
  restoricon → startup blocked: unsafe/unverifiable identity
PUBLIC COMMAND ['/data/data/com.termux/files/usr/bin/bash', '-c', 'source "$1"; "$2"', 'fixture', '/data/data/com.termux/files/home/Codey-OS/lib/service_manager.sh', 'stop_restoricon'] cwd= None OSrc= 2
STDOUT:
unsafe-unverifiable
STDERR:
  restoricon → stop not completed or identity unavailable
PASS CASE 22 guarded actual identity refusal boot event_labels= ['adapter:lock-exec', 'adapter:lock-exec']
BEGIN CASE 23 guarded actual identity refusal start
PUBLIC COMMAND ['/data/data/com.termux/files/usr/bin/bash', '-c', 'source "$1"; "$2"', 'fixture', '/data/data/com.termux/files/home/Codey-OS/lib/service_manager.sh', 'start_restoricon'] cwd= None OSrc= 2
STDOUT:

STDERR:
  restoricon → startup blocked: unsafe/unverifiable identity
PUBLIC COMMAND ['/data/data/com.termux/files/usr/bin/bash', '-c', 'source "$1"; "$2"', 'fixture', '/data/data/com.termux/files/home/Codey-OS/lib/service_manager.sh', 'stop_restoricon'] cwd= None OSrc= 2
STDOUT:
unsafe-unverifiable
STDERR:
  restoricon → stop not completed or identity unavailable
PASS CASE 23 guarded actual identity refusal start event_labels= ['adapter:lock-exec', 'adapter:lock-exec']
BEGIN CASE 24 guarded actual identity refusal uid
PUBLIC COMMAND ['/data/data/com.termux/files/usr/bin/bash', '-c', 'source "$1"; "$2"', 'fixture', '/data/data/com.termux/files/home/Codey-OS/lib/service_manager.sh', 'start_restoricon'] cwd= None OSrc= 2
STDOUT:

STDERR:
  restoricon → startup blocked: unsafe/unverifiable identity
PUBLIC COMMAND ['/data/data/com.termux/files/usr/bin/bash', '-c', 'source "$1"; "$2"', 'fixture', '/data/data/com.termux/files/home/Codey-OS/lib/service_manager.sh', 'stop_restoricon'] cwd= None OSrc= 2
STDOUT:
unsafe-unverifiable
STDERR:
  restoricon → stop not completed or identity unavailable
PASS CASE 24 guarded actual identity refusal uid event_labels= ['adapter:lock-exec', 'adapter:lock-exec']
BEGIN CASE 25 last composite lock blocks all effects symlink
PUBLIC COMMAND ['/data/data/com.termux/files/usr/bin/bash', '/data/data/com.termux/files/home/Codey-OS/codey', 'start'] cwd= None OSrc= 2
STDOUT:
Starting all Codey-OS services in background...
STDERR:
Service mechanics unavailable or unsafe
PASS CASE 25 last composite lock blocks all effects symlink event_labels= ['adapter:lock-exec']
BEGIN CASE 26 last composite lock blocks all effects fifo
PUBLIC COMMAND ['/data/data/com.termux/files/usr/bin/bash', '/data/data/com.termux/files/home/Codey-OS/codey', 'start'] cwd= None OSrc= 2
STDOUT:
Starting all Codey-OS services in background...
STDERR:
Service mechanics unavailable or unsafe
PASS CASE 26 last composite lock blocks all effects fifo event_labels= ['adapter:lock-exec']
BEGIN CASE 27 last composite lock blocks all effects contended
PUBLIC COMMAND ['/data/data/com.termux/files/usr/bin/bash', '/data/data/com.termux/files/home/Codey-OS/codey', 'start'] cwd= None OSrc= 2
STDOUT:
Starting all Codey-OS services in background...
STDERR:
Service mechanics unavailable or unsafe
PASS CASE 27 last composite lock blocks all effects contended event_labels= ['adapter:lock-exec']
BEGIN CASE 28 concurrent composite start/stop excludes interleaving
PUBLIC COMMAND ['/data/data/com.termux/files/usr/bin/bash', '/data/data/com.termux/files/home/Codey-OS/codey-stop'] cwd= None OSrc= 2
STDOUT:

STDERR:
Service mechanics unavailable or unsafe
PUBLIC COMMAND ['/data/data/com.termux/files/usr/bin/bash', '/data/data/com.termux/files/home/Codey-OS/codey', 'start'] cwd= None OSrc= 0
STDOUT:
Starting all Codey-OS services in background...
DEAD
  llama-server-8080 → stopped (verified owned-process exit)
  daemon → started (verified process identity; application readiness pending)
  restoricon → started (verified process identity; application readiness pending)
  aigentik → started (verified process identity; application readiness pending)
  cloudflared → started (verified process identity; application readiness pending)
  Secrets → DR backup uploaded
  litestream → started (verified process identity; application readiness pending)
  backup-docs → started (verified process identity; application readiness pending)
STDERR:

PASS CASE 28 concurrent composite start/stop excludes interleaving event_labels= ['adapter:lock-exec', 'identity:inspect:codeyOS', 'identity:stop:llama-server-8080', 'identity:spawn:codeyOS', 'profile:codeyOS', 'adapter:parse-ready', 'adapter:lock-exec', 'identity:inspect:restoricon-api', 'adapter:parse-ready', 'identity:spawn:restoricon-api', 'profile:restoricon-api', 'identity:inspect:aigentik', 'identity:spawn:aigentik', 'profile:aigentik', 'adapter:parse-ready', 'identity:inspect:cloudflared', 'identity:spawn:cloudflared', 'adapter:parse-ready', 'profile:cloudflared', 'identity:inspect:litestream', 'setup-litestream-stub', 'timeout-secrets-stub', 'backup-secrets-stub', 'adapter:parse-ready', 'identity:spawn:litestream', 'profile:litestream', 'identity:inspect:backup-docs', 'identity:spawn:backup-docs', 'profile:backup-docs', 'adapter:parse-ready']
BEGIN CASE 29 selected non200 guardian excludes only selected lock
PUBLIC COMMAND ['/data/data/com.termux/files/usr/bin/bash', '/data/data/com.termux/files/home/Codey-OS/codey', 'start'] cwd= None OSrc= 2
STDOUT:
Starting all Codey-OS services in background...
DEAD
  llama-server-8080 → stopped (verified owned-process exit)
  daemon → started (verified process identity; application readiness pending)
STDERR:
Service launch failed; retained guardian owns cleanup and lifecycle lock.
  restoricon → launch failed; partial state may require inspection
PASS CASE 29 selected non200 guardian excludes only selected lock event_labels= ['adapter:lock-exec', 'identity:inspect:codeyOS', 'identity:stop:llama-server-8080', 'adapter:parse-ready', 'identity:spawn:codeyOS', 'profile:codeyOS', 'identity:inspect:restoricon-api', 'adapter:parse-ready', 'identity:spawn:restoricon-api', 'profile:restoricon-api']
BEGIN CASE 30 malformed composite protocol retains full operation
PUBLIC COMMAND ['/data/data/com.termux/files/usr/bin/bash', '/data/data/com.termux/files/home/Codey-OS/codey', 'start'] cwd= None OSrc= 2
STDOUT:
Starting all Codey-OS services in background...
DEAD
  llama-server-8080 → stopped (verified owned-process exit)
  daemon → started (verified process identity; application readiness pending)
STDERR:
Service mechanics unavailable or unsafe
Service readiness failed; helper finished, service identity requires inspection.
  restoricon → launch failed; partial state may require inspection
PASS CASE 30 malformed composite protocol retains full operation event_labels= ['adapter:lock-exec', 'identity:inspect:codeyOS', 'identity:stop:llama-server-8080', 'identity:spawn:codeyOS', 'profile:codeyOS', 'adapter:parse-ready', 'identity:inspect:restoricon-api', 'identity:spawn:restoricon-api', 'profile:restoricon-api', 'adapter:parse-ready']
BEGIN CASE 31 inherited credential/PYTHONPATH precedence
PUBLIC COMMAND ['/data/data/com.termux/files/usr/bin/bash', '/data/data/com.termux/files/home/Codey-OS/codey-start'] cwd= None OSrc= 0
STDOUT:
DEAD
  llama-server-8080 → stopped (verified owned-process exit)
  daemon → started (verified process identity; application readiness pending)
  restoricon → started (verified process identity; application readiness pending)
  aigentik → started (verified process identity; application readiness pending)
  cloudflared → started (verified process identity; application readiness pending)
  Secrets → DR backup uploaded
  litestream → started (verified process identity; application readiness pending)
  backup-docs → started (verified process identity; application readiness pending)
  TUI         → launching codeyOS...

STDERR:

PASS CASE 31 inherited credential/PYTHONPATH precedence event_labels= ['adapter:lock-exec', 'identity:inspect:codeyOS', 'identity:stop:llama-server-8080', 'adapter:parse-ready', 'identity:spawn:codeyOS', 'profile:codeyOS', 'identity:inspect:restoricon-api', 'identity:spawn:restoricon-api', 'profile:restoricon-api', 'adapter:parse-ready', 'identity:inspect:aigentik', 'adapter:parse-ready', 'identity:spawn:aigentik', 'profile:aigentik', 'identity:inspect:cloudflared', 'adapter:parse-ready', 'identity:spawn:cloudflared', 'profile:cloudflared', 'identity:inspect:litestream', 'setup-litestream-stub', 'timeout-secrets-stub', 'backup-secrets-stub', 'adapter:parse-ready', 'identity:spawn:litestream', 'profile:litestream', 'identity:inspect:backup-docs', 'adapter:parse-ready', 'identity:spawn:backup-docs', 'profile:backup-docs', 'TUI']
BEGIN CASE 32 optional missing profiles skipped without setup
PUBLIC COMMAND ['/data/data/com.termux/files/usr/bin/bash', '/data/data/com.termux/files/home/Codey-OS/codey', 'start'] cwd= None OSrc= 0
STDOUT:
Starting all Codey-OS services in background...
DEAD
  llama-server-8080 → stopped (verified owned-process exit)
  daemon → started (verified process identity; application readiness pending)
  restoricon → started (verified process identity; application readiness pending)
  aigentik → optional service unavailable/not configured; skipped
  cloudflared → optional service unavailable/not configured; skipped
  litestream → optional service unavailable/not configured; skipped
  backup-docs → started (verified process identity; application readiness pending)
STDERR:

PASS CASE 32 optional missing profiles skipped without setup event_labels= ['adapter:lock-exec', 'identity:inspect:codeyOS', 'identity:stop:llama-server-8080', 'adapter:parse-ready', 'identity:spawn:codeyOS', 'profile:codeyOS', 'identity:inspect:restoricon-api', 'identity:spawn:restoricon-api', 'profile:restoricon-api', 'adapter:parse-ready', 'identity:inspect:aigentik', 'identity:inspect:cloudflared', 'identity:inspect:litestream', 'identity:inspect:backup-docs', 'adapter:parse-ready', 'identity:spawn:backup-docs', 'profile:backup-docs']
BEGIN CASE 33 config selected temp root
PUBLIC COMMAND ['/data/data/com.termux/files/usr/bin/bash', '/data/data/com.termux/files/home/Codey-OS/codeydOS', 'config'] cwd= None OSrc= 0
STDOUT:
Default config created at: /data/data/com.termux/files/usr/tmp/b3-live-4e5lp31c/case-33/selected state/config.json
STDERR:

PASS CASE 33 config selected temp root event_labels= ['adapter:config-create']
BEGIN CASE 34 public codeyOS custom-spaces snapshot actual disposable UDS
PUBLIC COMMAND ['/data/data/com.termux/files/usr/bin/bash', '/data/data/com.termux/files/home/Codey-OS/codeyOS', 'status'] cwd= None OSrc= 0
STDOUT:
Codey-OS Daemon Status
========================================
PID:            123
Status:         Running
Uptime:         0 seconds
Memory:         0 MB

Task Queue:
  Pending:      0
  Stuck:        None

Recent Actions: 0 logged

State Database: /data/data/com.termux/files/usr/tmp/b3-live-4e5lp31c/case-34/selected state/state.db
STDERR:

PUBLIC COMMAND ['/data/data/com.termux/files/usr/bin/bash', '/data/data/com.termux/files/home/Codey-OS/codeyOS', 'status'] cwd= None OSrc= 1
STDOUT:
Codey-OS daemon is not running
Use 'codeydOS start' to start the daemon
STDERR:
Daemon identity is unsafe/unverifiable; connection refused
PUBLIC COMMAND ['/data/data/com.termux/files/usr/bin/bash', '/data/data/com.termux/files/home/Codey-OS/codeyOS', 'plain prompt'] cwd= None OSrc= 0
STDOUT:

STDERR:

PASS CASE 34 public codeyOS custom-spaces snapshot actual disposable UDS event_labels= ['adapter:paths', 'adapter:usable-daemon', 'status-rpc-fixture', 'adapter:paths', 'adapter:usable-daemon', 'adapter:paths', 'direct-main-stub']
BEGIN CASE 35 root refusal no cwd fallback codey
PUBLIC COMMAND ['/data/data/com.termux/files/usr/bin/bash', '/data/data/com.termux/files/home/Codey-OS/codey'] cwd= None OSrc= 2
STDOUT:

STDERR:
Cannot resolve installed Codey-OS entrypoint.
PASS CASE 35 root refusal no cwd fallback codey event_labels= []
BEGIN CASE 36 root refusal no cwd fallback codey-start
PUBLIC COMMAND ['/data/data/com.termux/files/usr/bin/bash', '/data/data/com.termux/files/home/Codey-OS/codey-start'] cwd= None OSrc= 2
STDOUT:

STDERR:
Cannot resolve installed Codey-OS entrypoint.
PASS CASE 36 root refusal no cwd fallback codey-start event_labels= []
BEGIN CASE 37 root refusal no cwd fallback codey-stop
PUBLIC COMMAND ['/data/data/com.termux/files/usr/bin/bash', '/data/data/com.termux/files/home/Codey-OS/codey-stop'] cwd= None OSrc= 2
STDOUT:

STDERR:
Cannot resolve installed Codey-OS entrypoint.
PASS CASE 37 root refusal no cwd fallback codey-stop event_labels= []
BEGIN CASE 38 root refusal no cwd fallback codeyOS
PUBLIC COMMAND ['/data/data/com.termux/files/usr/bin/bash', '/data/data/com.termux/files/home/Codey-OS/codeyOS'] cwd= None OSrc= 2
STDOUT:

STDERR:
Cannot resolve installed Codey-OS entrypoint.
PASS CASE 38 root refusal no cwd fallback codeyOS event_labels= []
BEGIN CASE 39 root refusal no cwd fallback codeydOS
PUBLIC COMMAND ['/data/data/com.termux/files/usr/bin/bash', '/data/data/com.termux/files/home/Codey-OS/codeydOS'] cwd= None OSrc= 2
STDOUT:

STDERR:
Cannot resolve installed Codey-OS entrypoint.
PASS CASE 39 root refusal no cwd fallback codeydOS event_labels= []
BEGIN CASE 40 root refusal no cwd fallback codey-metrics
PUBLIC COMMAND ['/data/data/com.termux/files/usr/bin/bash', '/data/data/com.termux/files/home/Codey-OS/codey-metrics'] cwd= None OSrc= 2
STDOUT:

STDERR:
Cannot resolve installed Codey-OS entrypoint.
PASS CASE 40 root refusal no cwd fallback codey-metrics event_labels= []
BEGIN CASE 41 daemon public start/reload/restart/stop/status simulated fixed profile
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

Traceback (most recent call last):
  File "/data/data/com.termux/files/usr/tmp/b3_live_verify.py", line 55, in <module>
    case('daemon public start/reload/restart/stop/status simulated fixed profile',daemonoperations)
    ~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/data/data/com.termux/files/usr/tmp/b3_live_verify.py", line 29, in case
    print('BEGIN CASE',count,label);func(h,*args);events=m.events(h);assert not any(e['label'] in ('BLOCKED','FORBIDDEN_SIGNAL_ATTEMPT') for e in events);print('PASS CASE',count,label,'event_labels=',[e['label']+(':'+e['service'] if 'service' in e else '') for e in events])
                                    ~~~~^^^^^^^^^
  File "/data/data/com.termux/files/usr/tmp/b3_live_verify.py", line 53, in daemonoperations
    answer=m.run_public(h,'codeydOS',op);assert answer.returncode==0,(op,answer.stderr)
                                                ^^^^^^^^^^^^^^^^^^^^
AssertionError: ('status', '')
$ free -h (after)
               total        used        free      shared  buff/cache   available
Mem:            10Gi       7.1Gi       547Mi        78Mi       3.5Gi       3.7Gi
Swap:           15Gi       4.1Gi        11Gi
RESULT FAIL public cases completed= 41
```
