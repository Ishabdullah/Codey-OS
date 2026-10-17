# WP2.1 13d native bare-UDS/SQLite verification

2026-10-16. Independent result: PASS. Approved2 source/test hashes and frozen diff checked before/after.

Actual bare DaemonServer, selected path parser, temporary SQLite StateStore and UDS exercised native READ rows, operator enqueue/cancel ACT, failures, zero-enqueue planner matrix, postcommit logging-warning fidelity, and release outcome/audit/cooldown semantics. Planner/thermal/loader/probe/unload were fixed model-free modules installed before daemon import. No active NEW969 loader source was imported. Release callback ran in actual asyncio executor with real SWAP Lock; cancellation was held until an Event-controlled callback finished, then propagated. Denied release executed no unload. All real sockets were AF_UNIX only; subprocess, OS signals and HTTP were fail-closed forbidden before core import. UDS/event-loop/executor threads and SQLite closed in finally. Raw literal output continuously fsynced to /data/data/com.termux/files/usr/tmp/wp21_13d_native_live_raw.log.

Limits: fake model/planner outcomes are explicit dependency injections, not model or real unload/adopted-process proof. Only bare handlers ran; no full Daemon/watchdog/task executor/model/startup, network/real ports/resource-gate store/live data/default plugins/services/cloud/credentials. Public release callers/shell and future voice/main boundaries remain separate.

Literal output:

```text
$ free -h (before)
               total        used        free      shared  buff/cache   available
Mem:            10Gi       7.0Gi       637Mi        67Mi       3.4Gi       3.8Gi
Swap:           15Gi       5.2Gi        10Gi
Approved native2 files + frozen diff SHA256 matched
ℹ  Received command: ping
ACTUAL UDS ping data= None response= {'status': 'ok', 'message': 'pong'} AUDIT= [{'ts': 1792205093.0929334, 'authority': 'READ', 'action': 'daemon.ping', 'command': 'daemon:ping', 'outcome': 'allowed', 'reason': 'command executed'}]
ℹ  Received command: status
ACTUAL UDS status data= None response= {'status': 'ok', 'daemon': 'running', 'pid': 29263, 'tasks': {'pending': 0, 'running': 0, 'running_active': 0, 'done': 0}, 'state': {}} AUDIT= [{'ts': 1792205093.1193793, 'authority': 'READ', 'action': 'daemon.status', 'command': 'daemon:status', 'outcome': 'allowed', 'reason': 'command executed'}]
ℹ  Received command: health
ACTUAL UDS health data= None response= {'status': 'ok', 'healthy': True, 'pid': 29263, 'uptime_seconds': 0, 'memory_mb': 204.3, 'tasks': {'pending': 0, 'stuck': []}, 'recent_actions': 0} AUDIT= [{'ts': 1792205093.1382568, 'authority': 'READ', 'action': 'daemon.health', 'command': 'daemon:health', 'outcome': 'allowed', 'reason': 'command executed'}]
ℹ  Received command: task
ACTUAL UDS task data= None response= {'status': 'ok', 'tasks': []} AUDIT= [{'ts': 1792205093.1548166, 'authority': 'READ', 'action': 'daemon.task', 'command': 'daemon:task', 'outcome': 'allowed', 'reason': 'command executed'}]
ℹ  Received command: command
ACTUAL UDS command data= {'prompt': 'PRIVATE operator literal', 'yolo': True} response= {'status': 'ok', 'message': 'Task queued', 'task_id': 1} AUDIT= [{'ts': 1792205093.1790195, 'authority': 'ACT', 'action': 'daemon.command', 'command': 'daemon:command', 'outcome': 'allowed', 'reason': 'command executed'}]
ℹ  Received command: cancel
ACTUAL UDS cancel data= {'id': 1} response= {'status': 'ok', 'message': 'Task 1 cancelled'} AUDIT= [{'ts': 1792205093.1966984, 'authority': 'ACT', 'action': 'daemon.cancel', 'command': 'daemon:cancel', 'outcome': 'allowed', 'reason': 'command executed'}]
ℹ  Received command: cancel
ACTUAL UDS cancel data= {'id': 999999} response= {'status': 'error', 'message': 'Task 999999 not found'} AUDIT= [{'ts': 1792205093.211912, 'authority': 'ACT', 'action': 'daemon.cancel', 'command': 'daemon:cancel', 'outcome': 'failed', 'reason': 'Daemon operation failed'}]
ℹ  Received command: command
ACTUAL UDS command data= {'prompt': 'PRIVATE plan', 'plan_only': True} response= {'status': 'ok', 'message': 'Plan response', 'task_ids': [], 'plan': ['a', 'b']} AUDIT= []
ℹ  Received command: command
ACTUAL UDS command data= {'prompt': 'PRIVATE plan', 'plan_only': True} response= {'status': 'ok', 'message': 'Plan response', 'task_ids': [], 'plan': ['a']} AUDIT= []
ℹ  Received command: command
ACTUAL UDS command data= {'prompt': 'PRIVATE plan', 'plan_only': True} response= {'status': 'ok', 'message': 'Plan response', 'task_ids': [], 'plan': []} AUDIT= []
ℹ  Received command: command
ACTUAL UDS command data= {'prompt': 'PRIVATE plan', 'plan_only': True} response= {'status': 'ok', 'message': 'Plan response', 'task_ids': [], 'plan': []} AUDIT= []
ℹ  Received command: command
⚠  Planner request timed out; returning no plan
ACTUAL UDS command data= {'prompt': 'PRIVATE plan', 'plan_only': True} response= {'status': 'ok', 'message': 'No plan available', 'task_ids': [], 'plan': []} AUDIT= []
ℹ  Received command: command
ACTUAL UDS command data= {'prompt': 'PRIVATE plan', 'plan_only': True} response= {'status': 'ok', 'message': 'No plan available', 'task_ids': [], 'plan': []} AUDIT= []
ℹ  Received command: command
⚠  Planner unavailable; returning no plan
ACTUAL UDS command data= {'prompt': 'PRIVATE plan', 'plan_only': True} response= {'status': 'ok', 'message': 'No plan available', 'task_ids': [], 'plan': []} AUDIT= []
ℹ  Received command: command
ACTUAL UDS command data= {'prompt': 'PRIVATE plan', 'plan_only': True, 'no_plan': True} response= {'status': 'ok', 'message': 'No plan available', 'task_ids': [], 'plan': []} AUDIT= []
PASS planner >1/1/0/None/no_plan/timeout/refused/error all zero new SQLite tasks
ℹ  Received command: command
⚠  Daemon task operation committed; episodic logging failed
ACTUAL UDS command data= {'prompt': 'PRIVATE committed once'} response= {'status': 'ok', 'message': 'Task queued', 'task_id': 2, 'warning': 'Task operation committed; episodic logging failed'} AUDIT= [{'ts': 1792205093.3407874, 'authority': 'ACT', 'action': 'daemon.command', 'command': 'daemon:command', 'outcome': 'allowed', 'reason': 'command executed'}]
PASS episodic postcommit failure preserves success with one actual persisted task
ℹ  Received command: release_model_slot
ℹ  release_model_slot: primary released on external request
ACTUAL UDS release_model_slot data= {'model_id': 'primary'} response= {'status': 'ok', 'released': True, 'outcome': 'released', 'message': "'primary' released and confirmed freed"} AUDIT= [{'ts': 1792205093.3633416, 'authority': 'ACT', 'action': 'daemon.release_model_slot', 'command': 'daemon:release_model_slot:primary', 'outcome': 'allowed', 'reason': 'command executed'}]
PASS unload actual executor_thread= 516092324976 eventloop_thread= 516111215728 SWAP held during callback; confirmed cooldown only
ℹ  Received command: release_model_slot
✗  release_model_slot: model release failed
ACTUAL UDS release_model_slot data= {'model_id': 'primary'} response= {'status': 'error', 'released': False, 'outcome': 'error', 'message': 'Model cleanup remained pending'} AUDIT= [{'ts': 1792205093.394226, 'authority': 'ACT', 'action': 'daemon.release_model_slot', 'command': 'daemon:release_model_slot:primary', 'outcome': 'failed', 'reason': 'Daemon model release failed'}]
ℹ  Received command: release_model_slot
✗  release_model_slot: model release failed
ACTUAL UDS release_model_slot data= {'model_id': 'primary'} response= {'status': 'error', 'released': False, 'outcome': 'error', 'message': 'Model cleanup remained pending'} AUDIT= [{'ts': 1792205093.4131634, 'authority': 'ACT', 'action': 'daemon.release_model_slot', 'command': 'daemon:release_model_slot:primary', 'outcome': 'failed', 'reason': 'Daemon model release failed'}]
ℹ  Received command: release_model_slot
✗  release_model_slot: model release failed
ACTUAL UDS release_model_slot data= {'model_id': 'primary'} response= {'status': 'error', 'released': False, 'outcome': 'error', 'message': 'PRIVATE unload failure'} AUDIT= [{'ts': 1792205093.4295824, 'authority': 'ACT', 'action': 'daemon.release_model_slot', 'command': 'daemon:release_model_slot:primary', 'outcome': 'failed', 'reason': 'Daemon model release failed'}]
ℹ  Received command: release_model_slot
ACTUAL UDS release_model_slot data= {'model_id': 'primary'} response= {'status': 'ok', 'released': False, 'outcome': 'already_unloaded', 'message': "'primary' was not loaded — nothing to release"} AUDIT= [{'ts': 1792205093.4579153, 'authority': 'ACT', 'action': 'daemon.release_model_slot', 'command': 'daemon:release_model_slot:primary', 'outcome': 'allowed', 'reason': 'command executed'}]
ℹ  Received command: release_model_slot
ACTUAL UDS release_model_slot data= {'model_id': 'PRIVATE invalid'} response= {'status': 'error', 'released': False, 'outcome': 'invalid_model_id', 'message': "model_id must be 'primary', got 'PRIVATE invalid'"} AUDIT= [{'ts': 1792205093.4733217, 'authority': 'ACT', 'action': 'daemon.release_model_slot', 'command': 'daemon:release_model_slot', 'outcome': 'failed', 'reason': 'Daemon operation failed'}]
ℹ  Received command: release_model_slot
ACTUAL UDS release_model_slot data= {'model_id': 'primary'} response= {'status': 'ok', 'released': False, 'outcome': 'busy_task_running', 'message': 'a task is actively executing — declined to avoid releasing a model out from under in-flight inference'} AUDIT= [{'ts': 1792205093.4846036, 'authority': 'ACT', 'action': 'daemon.release_model_slot', 'command': 'daemon:release_model_slot', 'outcome': 'allowed', 'reason': 'command executed'}]
ℹ  Received command: release_model_slot
ACTUAL UDS release_model_slot data= {'model_id': 'primary'} response= {'status': 'ok', 'released': False, 'outcome': 'busy_swap_in_flight', 'message': 'a primary load/restart is already in flight — declined'} AUDIT= [{'ts': 1792205093.499142, 'authority': 'ACT', 'action': 'daemon.release_model_slot', 'command': 'daemon:release_model_slot', 'outcome': 'allowed', 'reason': 'command executed'}]
ℹ  Received command: release_model_slot
ACTUAL UDS release_model_slot data= {'model_id': 'primary'} response= {'status': 'ok', 'released': False, 'outcome': 'cooldown', 'message': "released 'primary' too recently — retry in 5.0s"} AUDIT= [{'ts': 1792205093.5129445, 'authority': 'ACT', 'action': 'daemon.release_model_slot', 'command': 'daemon:release_model_slot', 'outcome': 'allowed', 'reason': 'command executed'}]
ℹ  Received command: release_model_slot
✗  release_model_slot: model release failed
ACTUAL UDS release_model_slot data= {'model_id': 'primary'} response= {'status': 'error', 'released': False, 'outcome': 'error', 'message': 'Daemon model release unavailable'} AUDIT= [{'ts': 1792205093.525893, 'authority': 'ACT', 'action': 'daemon.release_model_slot', 'command': 'daemon:release_model_slot:primary', 'outcome': 'refused', 'reason': 'Injected refusal'}]
ACTUAL cancellation observed while fake worker blocked; SWAP still held; request not done
PASS cancellation propagated only after actual executor callback resolved; audit= [{'ts': 1792205093.5583453, 'authority': 'ACT', 'action': 'daemon.release_model_slot', 'command': 'daemon:release_model_slot:primary', 'outcome': 'allowed', 'reason': 'command executed'}]
ℹ  Daemon socket stopped
Finally UDS unlinked/closed, eventloop+executor threads joined, temporary SQLite closed; no process spawned/signaled
Approved native2 files + frozen diff SHA256 matched
$ free -h (after)
               total        used        free      shared  buff/cache   available
Mem:            10Gi       7.0Gi       630Mi        67Mi       3.4Gi       3.8Gi
Swap:           15Gi       5.2Gi        10Gi
RESULT PASS
```
