# WP2.1 slice 13c.2a disposable configured-path verification

2026-10-15. Independent on-device verification: STOPPED / FAIL at the first fresh-process import/READ check. No later lifecycle, UDS, plugin RPC or observability scenario ran.

The first fixture set temporary CODEY_STATE_DIR and audit environment, then ran a fresh Python process importing core.daemon_config, the public daemon_control plugin and main; it resolved paths, read plugin PID status and main._daemon_is_running. The combined assertion required child returncode zero and the missing state root to remain absent. That assertion failed. The available output does not distinguish nonzero subprocess status from root creation, so neither cause is asserted here. TemporaryDirectory cleanup removed the fixture.

The harness buffered the baseline free -h and subprocess stdout/stderr until successful completion. Its exception therefore prevented those readings from reaching tool output. They are unavailable; no after reading or PASS is claimed. This is a harness reporting limitation. Coordinator was informed immediately; no rerun was performed to mask the failure. No model/full daemon/existing service/network/live store was started or touched.

Literal available output:

```text
/data/data/com.termux/files/usr/tmp/codey_c2a_verify.py
Traceback (most recent call last):
  File "/data/data/com.termux/files/usr/tmp/codey_c2a_verify.py", line 10, in <module>
    child=subprocess.run([sys.executable,'-c',body],cwd=repo,env=env,capture_output=True,text=True,timeout=15);print('Fresh missing-root READ rc=',child.returncode,'stdout=',repr(child.stdout),'stderr=',repr(child.stderr));assert child.returncode==0 and not missing.exists();print('PASS import/READ left missing root absent; no lock created')
                                                                                                                                                                                                                                      ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError
```
