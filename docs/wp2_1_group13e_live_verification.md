# WP2.1 slice 13e disposable-process live verification

2026-10-15. Independent on-device verification after reviewer source approval round 2: PASS.

Actual lightweight Python children were spawned with start_new_session=True and retained exact Popen handles. No model process was started. These handles were manually attached to LlamaServer/ModelLoader fixtures with temporary durable identities and fake slot IDs. Actual LlamaServer.stop and ModelLoader.unload exercised TERM, ignored TERM/KILL, retention/retry after injected signaling and wait failures, preserved replacement records, and reservation-release failure/retry. Release callbacks assert the actual fixture was already reaped before accounting release. An independently owned innocent fixture survived every scenario and was finally cleaned by its own retained handle. Temporary state/audit env was set before Codey imports. No models, existing services, live stores, network or synthetic-PID signaling.

Limits: admission/reservation data and release callbacks were fake; no real reservation-store mutation or loader-start/model health path was exercised. Signals were deliberately suppressed during the injected wait error to keep that fixture alive. This proves teardown/accounting call order with actual children, not real model RAM behavior, failed-load reservation binding, or full caller integration. Replacement identity was injected by editing only the temporary PID record. All fixture children were reaped in finally cleanup.

Literal output:

```text
$ free -h (before)
               total        used        free      shared  buff/cache   available
Mem:            10Gi       6.7Gi       1.0Gi        67Mi       3.5Gi       4.1Gi
Swap:           15Gi       4.2Gi        11Gi
PASS normal actual_returncode= -15 identity_removed=True release_events= [('fixture-slot-normal', -15, 'reaped-before-release')] innocent_alive=True
PASS ignore actual_returncode= -9 identity_removed=True release_events= [('fixture-slot-ignore', -9, 'reaped-before-release')] innocent_alive=True
PASS injected signal refusal: exact_handle/PID/slot/identity retained; load/start retries refused; no replacement/reservation/release
PASS injected wait error with signals suppressed: live child/handle/slot/identity retained; no release
PASS retry after restored real signaling/wait: reaped=True identity_removed=True release_events= [('fixture-slot-retry', -15, 'reaped-before-release')]
PASS replaced identity evidence: owned child_reaped=True unrelated_record_preserved=True innocent_alive=True release_events= [('fixture-slot-replacement', -15, 'reaped-before-release')]
PASS injected reservation-release error: actual_child_reaped=True slot_retained=True cleanup_pending=True
PASS reservation-release retry: slot_cleared=True release_events= [('fixture-slot-accounting', -15, 'reaped-before-release'), ('fixture-slot-accounting', -15, 'reaped-before-release')]
Finally cleanup: retained exact Popen handles= 6 all_reaped= True
PASS all disposable teardown/accounting scenarios; temporary state removed.
$ free -h (after)
               total        used        free      shared  buff/cache   available
Mem:            10Gi       6.7Gi       1.0Gi        67Mi       3.5Gi       4.1Gi
Swap:           15Gi       4.2Gi        11Gi
```
