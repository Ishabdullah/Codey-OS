# WP2.1 slice 13c.2a resumed disposable configured-path verification

2026-10-15. Independent resumed verification after coordinator/architect disposition: PASS for the bounded criteria below. The initial FAIL report and separate import diagnostic remain unchanged. This run does not reconstruct missing initial output or retrospectively assert its precise cause.

The separate diagnostic proves daemon_config and stdlib identity imports leave missing state absent. Architect accepted existing fixed schema/bootstrap initialization for broader daemon/plugin/main imports under the group 12 contract. This resumed run records import-created temporary files and compares bytes/inode/mtime before and after pure public plugin/main READ calls; no additional files or mutations were observed.

Actual daemon.write_pid_file self-published at custom absolute PID/socket/log paths containing spaces. A bare DaemonServer handler served an actual disposable Unix socket using a temporary SQLite StateStore and independent asyncio thread. A fresh Python client resolved the temporary config/socket. Public plugin ping/status/health/task/list/cancel and main coordination completed. Observability used configured PID and rejected stale timestamp uptime. Legacy-live/malformed/wrong-UID records returned explicit unknown/False, with zero socket construction calls and identical file/signature snapshots. All socket/thread/SQLite/identity resources were cleaned; temporary CODEY_STATE_DIR/audit preceded Codey imports.

Limits: only a bare DaemonServer socket handler ran; no full Daemon/model loop, startup execution, service shell migration, real daemon, external network or live store. Startup-block-before-construction remains unit-only. Relative path decisions and normal CCOS authority classification were not exercised. Global log setup was not invoked; log path resolution was verified. Corrupt identity fixtures and no-connect spy were explicit test instrumentation.

Literal resumed output (immediately flushed throughout):

```text
$ free -h (before)
               total        used        free      shared  buff/cache   available
Mem:            10Gi       6.7Gi       576Mi        69Mi       3.8Gi       4.1Gi
Swap:           15Gi       4.2Gi        11Gi
Documented import bootstrap files: ['config.json', 'state.db', 'state.db-shm', 'state.db-wal']
PASS missing configured PID root stays absent AFTER documented bootstrap; pure plugin/main READ state/signatures unchanged
Resolved custom absolute paths: DaemonPaths(pid_file=PosixPath('/data/data/com.termux/files/usr/tmp/c2a-0xderziv/custom paths/p'), socket_file=PosixPath('/data/data/com.termux/files/usr/tmp/c2a-0xderziv/custom paths/s'), log_file=PosixPath('/data/data/com.termux/files/usr/tmp/c2a-0xderziv/custom paths/l')) socket_bytes= 63
PASS unsafe legacy plugin= {'running': None, 'state': 'unsafe-unverifiable'} main=False socket_calls=0 records/signatures_unchanged=True
PASS unsafe malformed plugin= {'running': None, 'state': 'unsafe-unverifiable'} main=False socket_calls=0 records/signatures_unchanged=True
PASS unsafe mismatch plugin= {'running': None, 'state': 'unsafe-unverifiable'} main=False socket_calls=0 records/signatures_unchanged=True
PASS self identity status=True while startup own-PID exception=False
PASS observability effective custom PID= 32348 stale timestamp uptime=0; fresh timestamp uptime= 0
ℹ  Received command: ping
Fresh configured RPC rc= 0 stdout= "{'status': 'ok', 'message': 'pong'}\n" stderr= ''
PASS actual main CLI coordination and plugin reachability=True
ℹ  Received command: ping
ℹ  Received command: status
ℹ  Received command: health
Public plugin ping: {'status': 'ok', 'message': 'pong'}
Public plugin status: {'status': 'ok', 'daemon': 'running', 'pid': 32348, 'tasks': {'pending': 0, 'running': 0, 'running_active': 0, 'done': 0}, 'state': {'daemon_started_at': '1792117818'}}
Public plugin health: {'status': 'ok', 'healthy': True, 'pid': 32348, 'uptime_seconds': 1, 'memory_mb': 174.0, 'tasks': {'pending': 0, 'stuck': []}, 'recent_actions': 0}
ℹ  Received command: task
ℹ  Received command: task
ℹ  Received command: cancel
Public task: {'status': 'ok', 'task': {'id': 1, 'description': 'disposable verification task', 'status': 'pending', 'result': None, 'created_at': 1792117819, 'started_at': None, 'completed_at': None, 'dependencies': '[]', 'retry_count': 0, 'needs_planning': 0}}
Public task list: {'status': 'ok', 'tasks': [{'id': 1, 'description': 'disposable verification task', 'status': 'pending', 'result': None, 'created_at': 1792117819, 'started_at': None, 'completed_at': None, 'dependencies': '[]', 'retry_count': 0, 'needs_planning': 0}]}
Public cancellation: {'status': 'ok', 'message': 'Task 1 cancelled'} flag= '1'
PASS actual public plugin ping/status/health/task/list/cancel over disposable UDS
ℹ  Daemon socket stopped
Finally cleanup: UDS closed/unlinked; event-loop thread joined; self identity removed; temporary SQLite closed
PASS all isolated configured-path/read/client scenarios; temporary state removed.
$ free -h (after)
               total        used        free      shared  buff/cache   available
Mem:            10Gi       6.7Gi       563Mi        69Mi       3.8Gi       4.1Gi
Swap:           15Gi       4.2Gi        11Gi
```
