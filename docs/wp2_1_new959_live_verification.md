# WP2.1 NEW-959 live verification

Date: 2026-10-18. Final reviewed source was exercised on-device in disposable
directories. No model, daemon, installed service, network operation, production
database, or unknown PID was used or signalled. Proxy variables were unset and
service dispatch was fail-closed.

## S1 — public daemon-path consumers

Raw report: `/data/data/com.termux/files/usr/tmp/n959-live-final2-YjdbaS/report.log`
(SHA-256 `7ea5fd5e7fdf8038b0225267f23feadf8a9161b9c703e247dd4cf09b1f7d9e91`;
539 lines, 39,405 bytes). The real entrypoints were run for an absolute state
root containing relative daemon keys and for a relative `CODEY_STATE_DIR`:

```text
A-relative-config_RCS=[2, 2, 2, 2, 2, 2, 1, 2]
A-relative-config_AUDIT_COUNT=7
A-relative-config_LIFECYCLE_COUNT=0
B-relative-state-root_RCS=[2, 2, 2, 2, 2, 2, 1, 2]
B-relative-state-root_AUDIT_COUNT=7
B-relative-state-root_LIFECYCLE_COUNT=0
OVERALL_RESULT=PASS
```

The seven wrapped operations wrote failed local Action Gateway rows. Direct
`codeyOS status` correctly wrote no local row because authority is enforced at
the daemon-server boundary. Both config files remained byte-identical. The
known NEW-855 import bootstrap created only empty `state.db`/`checkpoints/`; no
PID, socket, log, identity sidecar, or lifecycle lock appeared.

The simulated positive profile used absolute paths containing spaces and a
leading `~/`. Start/reload/restart/stop/status returned `[0, 0, 0, 0, 1]`,
`POSITIVE_RESULT=PASS`, and two working directories resolved the same path
snapshot. Identity/spawn/readiness and service executables were faked; no
actual service ran.

```text
Mem:            10Gi       8.0Gi       461Mi        87Mi       2.7Gi       2.8Gi
Swap:           15Gi       5.3Gi        10Gi
HASHES_UNCHANGED=True
GIT_STATUS_UNCHANGED=True
Mem:            10Gi       8.0Gi       406Mi        87Mi       2.8Gi       2.8Gi
Swap:           15Gi       5.3Gi        10Gi
```

The first live run found a real product failure: `codeydOS config` accepted an
existing relative daemon configuration. It was repaired and reviewer-approved
before this PASS. Two verifier launches were later interrupted by the agent/API
runner; their partial outputs are not passing evidence.

## S2 — shell and process-identity CLI guards

Raw report: `/data/data/com.termux/files/usr/tmp/n959-s2-live2-ucY0n4/report.log`
(SHA-256 `79303124acc55bad9edd6984a9ba26c2ba9fc36bc895b62b1348b9a8de88ef54`;
81 lines, 4,876 bytes).

```text
locked-preflight rc=2 stdout_bytes=0 stderr_bytes=0 marker=absent
locked-stop rc=2 stdout_bytes=0 stderr_bytes=0 marker=absent
locked-reload rc=2 stdout_bytes=0 stderr_bytes=0 marker=absent
spawn-relative-pid rc=2 stdout_bytes=0 stderr_bytes=0 marker=absent
spawn-relative-log rc=2 stdout_bytes=0 stderr_bytes=0 marker=absent
spawn-relative-cwd rc=2 stdout_bytes=0 stderr_bytes=0 marker=absent
cli-record rc=2 stdout=unsafe-unverifiable stderr_bytes=0
cli-inspect rc=2 stdout=unsafe-unverifiable stderr_bytes=0
cli-cleanup rc=2 stdout=unsafe-unverifiable stderr_bytes=0
cli-signal rc=2 stdout=unsafe-unverifiable stderr_bytes=0
cli-stop rc=2 stdout=unsafe-unverifiable stderr_bytes=0
cli-spawn-pid rc=2 stdout_bytes=0 stderr=Owned service launch failed
cli-spawn-log rc=2 stdout_bytes=0 stderr=Owned service launch failed
cli-spawn-cwd rc=2 stdout_bytes=0 stderr=Owned service launch failed
marker_final=absent
```

The shell marker proves refusal preceded interpreter dispatch. The direct CLI
branches refused before locks, records, readiness pipes, process creation, or
signals. The first reporter hid `wc` under fail-closed PATH; it was discarded
and rerun from the clean root above.

## S3 — non-daemon lifecycle roots

Raw report: `/data/data/com.termux/files/usr/tmp/n959-s3-live2-kryVSO/report.log`
(SHA-256 `9b961ec5442a468284a28492218da49a1a83b3b2f3823b36f6b706bf6e0625bd`;
45 lines, 6,133 bytes). Real lifecycle entrypoints exercised restoricon
mutation, Aigentik status, cloudflared logs, litestream start, llama-server
stop, status-all, and logs-all. Every command returned 2.

```text
audit_rows=7
lifecycle_artifacts=0
selected_pid=/data/data/com.termux/files/usr/tmp/n959-s3-live2-kryVSO/absolute root/../absolute root/litestream.pid
litestream_cwd=/data/data/com.termux/files/usr/tmp/n959-s3-live2-kryVSO/absolute root/../absolute root
```

The spawn marker remained absent. Composite output named daemon plus all five
configured non-daemon entries as `REFUSED`. The positive probe changed the
environment after selecting the litestream snapshot and proved cwd stayed
bound to its selected parent. The first reporter hid `cat`; it was discarded
and rerun cleanly.

```text
Mem:            10Gi       8.0Gi       853Mi        78Mi       2.3Gi       2.8Gi
Swap:           15Gi       6.1Gi       9.9Gi
Mem:            10Gi       8.0Gi       874Mi        78Mi       2.3Gi       2.8Gi
Swap:           15Gi       6.1Gi       9.9Gi
```

## Final regression and review

S1 received lifecycle approval after preserving the original unexpandable
`~user/...` value in refusals. S2 was approved with no findings. S3 was approved
after correcting composite reachability and `signal.pthread_kill` test guards.

```text
540 passed in 103.48s (0:01:43)
All checks passed!
```

The second line is fatal Ruff over every changed Python source/test. Shell
syntax and `git diff --check` produced no output and exited zero.
