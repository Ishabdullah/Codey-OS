# WP2.1 slice 13a disposable-process live verification

2026-10-15. Independent verification after reviewer approval: PASS.

Actual Python success, exit 7, self-SIGTERM and disposable pytest pass/fail used real subprocess execution. Recovery mkdir used an explicitly temporary Filesystem. Package-install refusal used a subprocess spy: no pip command ran. CODEY_STATE_DIR and CODEY_ACTION_GATEWAY_AUDIT were set to temporary paths before Codey imports. No model, service, live store, peer or external send was invoked. subprocess.run owned and reaped fixture children. Slice 13a only: timeout, full fix/TDD agent workflows and real package installation were not live tested.

Literal output:

```text
$ free -h (before)
               total        used        free      shared  buff/cache   available
Mem:            10Gi       7.4Gi       1.2Gi        76Mi       2.4Gi       3.4Gi
Swap:           15Gi       3.8Gi        12Gi
run_and_capture success (True, 'fixture success\n') refused= False execution_error= False
AUDIT {"action": "fixmode.run_and_capture", "authority": "ACT", "command": "fixmode.run_and_capture", "outcome": "allowed", "reason": "command executed", "ts": 1792069933.9199119}
run_and_capture exit7 (False, 'fixture exit seven\n') refused= False execution_error= False
AUDIT {"action": "fixmode.run_and_capture", "authority": "ACT", "command": "fixmode.run_and_capture", "outcome": "failed", "reason": "Process exited with nonzero status", "ts": 1792069933.9847746}
run_and_capture self-SIGTERM (False, '[ERROR] Process interrupted by signal 15') refused= False execution_error= True
AUDIT {"action": "fixmode.run_and_capture", "authority": "ACT", "command": "fixmode.run_and_capture", "outcome": "failed", "reason": "Process execution interrupted", "ts": 1792069934.0357695}
run_tests test_success.py returncode= 0 passed= 1 failed= 0 errors= 0 all_pass= True execution_error= False
============================= test session starts ==============================
collecting ... collected 1 item

test_success.py::test_fixture PASSED                                     [100%]

============================== 1 passed in 0.01s ===============================
AUDIT {"action": "tdd.run_tests", "authority": "ACT", "command": "tdd.run_tests", "outcome": "allowed", "reason": "command executed", "ts": 1792069934.3740513}
run_tests test_failure.py returncode= 1 passed= 0 failed= 1 errors= 0 all_pass= False execution_error= False
============================= test session starts ==============================
collecting ... collected 1 item

test_failure.py::test_fixture FAILED                                     [100%]

=================================== FAILURES ===================================
_________________________________ test_fixture _________________________________
test_failure.py:1: in test_fixture
    def test_fixture(): assert False
                        ^^^^^^^^^^^^
E   assert False
=========================== short test summary info ============================
FAILED test_failure.py::test_fixture - assert False
============================== 1 failed in 0.04s ===============================
AUDIT {"action": "tdd.run_tests", "authority": "ACT", "command": "tdd.run_tests", "outcome": "failed", "reason": "Process exited with nonzero status", "ts": 1792069934.7633088}
recovery pip no callback: 'HIGH_IMPACT command with no confirmation path available; failing closed per policy (not attempted).' subprocess_calls= 0
AUDIT {"action": "recovery.pip_install", "authority": "HIGH_IMPACT", "command": "recovery.pip_install", "outcome": "refused", "reason": "HIGH_IMPACT command with no confirmation path available; failing closed per policy (not attempted).", "ts": 1792069934.7647974}
recovery mkdir: 'Created parent directory: /data/data/com.termux/files/usr/tmp/codey-13a-live-_6hmki7l/nested' directory_exists= True
AUDIT {"action": "recovery.mkdir_then_write", "authority": "ACT", "command": "recovery.mkdir_then_write", "outcome": "allowed", "reason": "command executed", "ts": 1792069934.7662354}
PASS: 7 isolated checks; temporary state removed.
$ free -h (after)
               total        used        free      shared  buff/cache   available
Mem:            10Gi       7.4Gi       1.2Gi        76Mi       2.4Gi       3.4Gi
Swap:           15Gi       3.8Gi        12Gi
```
