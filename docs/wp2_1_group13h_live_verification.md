# WP2.1 13h plugin activation disposable live verification

2026-10-16. Independent result: FAIL.

The first real post-spawn registration-failure case passed: actual owned child was reaped, plugin BROKEN, capability list empty, pre-existing registry objects/counters restored and second attempted capability absent. In the second case, actual terminate denial retained the exact live owned Popen/PID plus BROKEN activation-attempt marker; registry originals had already been restored. Calling core-classified READ system.info returned rather than raising CapabilityRefused, causing the harness assertion shown below. A pre-existing system.info entry had been restored and a fixture handler was registered; this report does not claim the returned call used a partial staged entry. The handler call count was not printed before the assertion.

The live harness stopped at that contradiction. Direct-execute refusal, pending-load refusal, cleanup/recovery retry, and successful subsequent registration were not reached. Finally restored the injected terminate method and waited/reaped all three exact fixture Popen handles, including the independently owned innocent child. No retry was performed. Source SHA256 matched the reviewed snapshot. HOME/state/audit/registry and manifests were disposable; all capability shapes were valid.

Limits: termination denial and registry exception were fixture injections. This does not establish durable registry atomicity or arbitrary/generated-plugin activation authorization. Public dispatch RLock races remain covered by approved unit tests, not repeated concurrently in this live harness. No default installed plugins, model, existing service, real ports, cloud/network/live stores/credentials or public service scripts were used. The concurrently changing shell/core-daemon sources were not imported or executed.

Literal immediately flushed output:

```text
$ free -h (before)
               total        used        free      shared  buff/cache   available
Mem:            10Gi       6.9Gi       389Mi        80Mi       3.8Gi       3.9Gi
Swap:           15Gi       4.2Gi        11Gi
Approved plugin_manager SHA256= b660f10eb64c7f2987434daed894c63a94d15f60e9073656a6596bbf440eaee1
PASS real post-spawn second registration failure: load=False status= broken child_returncode= -15 child_reaped=True original_objects/counters_restored=True partial_capability_absent=True innocent_alive=True
Finally: exact retained Popen handles= 3 all_waited/reaped=True
Traceback (most recent call last):
  File "/data/data/com.termux/files/usr/tmp/plugin13h_live.py", line 48, in <module>
    else:raise AssertionError('Failed activation allowed classified READ')
         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: Failed activation allowed classified READ
$ free -h (after)
               total        used        free      shared  buff/cache   available
Mem:            10Gi       6.9Gi       376Mi        80Mi       3.8Gi       3.9Gi
Swap:           15Gi       4.2Gi        11Gi
RESULT FAIL
```
