# WP2.1 slice 13b disposable-process live verification

2026-10-15. Independent on-device verification after reviewer round 2 approval: PASS.

Real Python fixture children exercised owned start/duplicate/stop, immediate exit, forged and replaced PID records, and injected publication/health/stop failures. All seven scenarios used temporary state; audit env and explicit temporary CapabilityRegistry were configured before any registry use. Subprocess spawning was wrapped solely to retain every exact Popen handle for finally cleanup. Every fixture child was reaped. No models, real plugins, existing services, live stores, network or unknown-process signaling.

Limits: publication denial, health failure and initial stop refusal were injected around real children; no live HTTP health check, full PluginManager reload/unload, cross-process identity, or service-shell behavior was tested. Literal output:

```text
$ free -h (before)
               total        used        free      shared  buff/cache   available
Mem:            10Gi       6.6Gi       471Mi        69Mi       4.1Gi       4.2Gi
Swap:           15Gi       3.3Gi        12Gi
PASS owned start / duplicate: spawned=1 same_handle=True; stop=True returncode= -15 pipes_closed= True
PASS immediate exit: start=False status= broken returncode= 2 record_absent= True
PASS forged record: stop=False start=False foreign_alive=True record_preserved=True
PASS replaced record: stop=True owned_returncode= -15 foreign_alive=True replacement_preserved=True
PASS publication failure: start=False child_reaped=True returncode= -15 ownership_released=True
PASS injected health failure: start=False child_reaped=True returncode= -15 record_absent=True
PASS injected stop failure then retry: failure_retained_handle=True retry=True child_reaped=True
Finally cleanup: fixture_children= 7 all_reaped= True
PASS: 7 isolated lifecycle scenarios; all fixture state removed.
$ free -h (after)
               total        used        free      shared  buff/cache   available
Mem:            10Gi       6.6Gi       462Mi        69Mi       4.1Gi       4.2Gi
Swap:           15Gi       3.3Gi        12Gi
```
