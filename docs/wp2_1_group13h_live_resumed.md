# WP2.1 13h resumed plugin activation disposable live verification

2026-10-16. Independent resumed result after reviewer-authorized harness correction: PASS.

Initial FAIL artifact remains preserved: that harness incorrectly expected a legitimately restored original READ capability to be blocked. This resumed run explicitly distinguishes restored-original identity (READ allowed once, usage12 to13) from failed-attempt staged identity (activation-incomplete refusal, no handler call). Both include actual retained-child cleanup/retry. No production source changed.

Only approved plugin_manager source and temporary manifests/registries were used. All capability shapes were valid. A real ordinary ProcessSupervisor launched lightweight Python children; the valid second registration mutated then raised after spawn. The first case confirmed real reap, BROKEN/non-ACTIVE status and exact pre-existing registry objects/counters restored. The second injected terminate denial around the exact owned Popen, confirmed retained ownership/BROKEN attempt, restored READ allowed and direct execute refused, no replacement while cleanup remained pending, real cleanup retry, and a single subsequent recovered spawn/one registration per capability. An independently owned innocent child survived until finally cleanup. HOME/state/audit/config context and registries were temporary before Codey imports. Every exact fixture Popen was finally waited/reaped.

Limits: termination denial and registry exception were fixture injections. This does not establish durable registry atomicity or arbitrary/generated-plugin activation authorization. Public dispatch RLock races remain covered by approved unit tests, not repeated concurrently in this live harness. No default installed plugins, model, existing service, real ports, cloud/network/live stores/credentials or public service scripts were used. The concurrently changing shell/core-daemon sources were not imported or executed.

Literal immediately flushed output:

```text
$ free -h (before)
               total        used        free      shared  buff/cache   available
Mem:            10Gi       6.9Gi       429Mi        79Mi       3.8Gi       3.9Gi
Swap:           15Gi       4.2Gi        11Gi
Approved plugin_manager SHA256= b660f10eb64c7f2987434daed894c63a94d15f60e9073656a6596bbf440eaee1
PASS real post-spawn second registration failure: load=False status= broken child_returncode= -15 child_reaped=True original_objects/counters_restored=True partial_capability_absent=True innocent_alive=True
PASS restored-original identity (not staged): independent READ handler called once; usage12->13; audit= {'ts': 1792180433.402489, 'authority': 'READ', 'action': 'ccos.call_capability:system.info', 'command': 'system.info', 'outcome': 'allowed', 'reason': 'command executed'}
PASS injected cleanup denial: exact live Popen/PID retained, BROKEN retry marker held; restored READ allowed/direct execute blocked; retry spawned no replacement
PASS real owned cleanup retry: old_child_returncode= -15 attempt cleared=True originals intact=True
PASS recovery: old child reaped before single new spawn, registration_once_each= ['system.info', 'system.processes'] recovery child reaped=True innocent_alive=True
PASS current registry IS failed-attempt staged object: classified READ activation-incomplete refusal; zero handler calls; audit= {'ts': 1792180433.652632, 'authority': 'HIGH_IMPACT', 'action': 'ccos.call_capability:system.info', 'command': 'system.info', 'outcome': 'refused', 'reason': 'plugin activation incomplete; capability unavailable'}
PASS staged/owned cleanup retry: exact child reaped; original restored; retry debt cleared; no duplicate; innocent survives
Finally: exact retained Popen handles= 5 all_waited/reaped=True
$ free -h (after)
               total        used        free      shared  buff/cache   available
Mem:            10Gi       6.9Gi       413Mi        79Mi       3.8Gi       3.9Gi
Swap:           15Gi       4.2Gi        11Gi
RESULT PASS
```
