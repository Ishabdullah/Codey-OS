# WP2.1 group 13 live verification: NEW-969 and NEW-970 (2026-10-17)

Scope: disposable on-device harnesses only. No model loaded, no real service/audio/peer/cloud touched, no source or tracking doc edited. Raw logs and harness scripts: `/data/data/com.termux/files/usr/tmp/g13/` (partA.py, run_partA.sh, partA_run1.log, partB.py, partB_v1_initial.py, run_partB.sh, partB_run1.log, partB_run2_corrected.log, sha_before.txt, sha_after.txt).

## Baseline (RAM rule), before any run
```
               total        used        free      shared  buff/cache   available
Mem:            10Gi       7.0Gi        85Mi        64Mi       4.2Gi       3.9Gi
Swap:           15Gi       3.9Gi        12Gi
```
After all runs:
```
               total        used        free      shared  buff/cache   available
Mem:            10Gi       6.8Gi       346Mi        56Mi       4.0Gi       4.0Gi
Swap:           15Gi       4.0Gi        12Gi
```
`ps aux | grep -E "llama-server|termux-(speech|tts)" | grep -v grep` after: no output (no stray harness children).

## Checksums (before == after, match expected prefixes/suffixes)
```
cd006f1d50dcb6c902c083d177a443200a0c22f63b40809ea8b86693e40e1567  core/loader_v2.py
09f1ca60d4c367c532b096ed352112165a25605529814729d50d7b774cfdc3f2  core/resource_gate.py
41facb9a7f673deebc1579d06707fe57f7aac345376b8b202e7f1096805eff63  core/voice.py
6703c19be02c0c32af626cafbb37840a9231f4998ceb6f4baf9eb8ffe1cb8fea  main.py
10f379130b35dabab31a351335af6565a7981ecd2f9f59167e927c0eff87710c  tests/test_foreign_primary_identity.py
fc829687082ac555bfaac5b5d4816c8a5e6a9d0b748aa82e8e216c3abf4f8fc6  tests/test_voice_action_boundaries.py
```
`diff sha_before.txt sha_after.txt` printed nothing (SHA_UNCHANGED).

## Method and what is real vs faked
Environment: HTTP(S)_PROXY unset, HOME and CODEY_STATE_DIR under the Termux tmp (A_1/, B_N/), `python3 -I` run from outside the repo with `sys.path` set explicitly.

Part A real: /proc reads (exe symlink, cmdline, stat start_ticks, boot_id, uid, state), real `os.kill` SIGTERM to a retained harness child, real fcntl flock on the resource_gate lock, real slot-store JSON, real `daemon_task_in_progress()` (disposable state dir, returned False), real `_is_port_in_use()` (nothing listens, returned False).
Part A faked or synthetic: the "llama-server" is a C sleep-loop stub compiled to `A_1/bin/llama-server` (a real ELF, so `/proc/pid/exe` really resolves to it), `loader_v2.LLAMA_SERVER_BIN` monkeypatched to it, it never binds the port (so the port-free wait is trivially satisfied, not exercised against a real listener); PID recycling is simulated by editing the `expected` dict (start_ticks +/-1, boot_id), not by a real recycle; `resolve` callbacks in direct capture calls are lambdas (the full-path calls A2/A2c/A3b use the real `_resolve_resident_pid_and_n_ctx` via the slot store). A harness guard wrapped `os.kill` and would have raised on any nonzero signal to a PID not in the harness's retained-Popen set (it never fired). A child killed by TERM sat as a zombie (state Z, counted dead by `_foreign_state`) until the harness `poll()`ed it; the harness did the reaping.

Part B real: fake `termux-speech-to-text` / `termux-tts-speak` shell scripts (write `marker.log`, print canned JSON, exit with FAKE_*_RC), `PATH` = only the fakebin dir (real `/data/data/com.termux/files/usr/bin` not on PATH), `command -v` printed the fakes before every run and `shutil.which` was re-asserted at start and end, a `subprocess.run/Popen` spy asserted the resolved argv[0] lives in fakebin before passing through, private `ActionGateway(audit_file=...)`. Part B faked: main.py `_voice_confirmation` is AST-extracted (same technique as the repo test) with `input`/`sys.stdin` stubbed; not a real TTY.

## Part A results (NEW-969): 48 PASS / 48, 0 FAIL (log below)
- A1 capture: succeeds only for exe+model+port argv match (also `--model=`/`--port=` forms); refused (None) for wrong port param, wrong model param, resolver returning other pid, resolved ctx >= wanted, bool port, pid 1, own pid, same-name different-path exe, argv port differs, argv model differs, duplicate `--port`, duplicate `-m`, non-decimal port, missing `--port`. Zero signals recorded across all of these; all children still alive.
- A2 kill path: full `_upgrade_resident_if_safe` returned `killed`; signals were exactly `[(9193, SIGTERM)]`; child rc -15, row released (`[]`). A2b: changed row, non-True `confirm_dead`, raising `confirm_dead` all returned False and kept the row; unchanged row + True released. A2c: wrong-exe resident registered in the slot store returned `not_safe`, zero signals, child alive, row kept.
- A3 contended lock: A3a (direct): releaser blocked on the held flock (True), holder killed+reaped original and swapped in `successor-gen-2`, release returned False, successor intact. A3b (inside the full function, real kill via a wrapper that calls the real `_kill_single_pid_term_then_kill`, then a thread takes the lock and swaps in `successor-gen-3`): returned `port_stuck`, 1.73s elapsed (blocked), successor row preserved, only a TERM to the owned child.
- A4 replaced identity: start_ticks +1, -1, and boot_id edits produced `ForeignStopOutcome(outcome='unsafe', attempted=False, replaced=True)`, no signal, child alive; pid/uid mismatch, None, {} and bad `wait_s` (True, -1, inf, "8") and pid 1 refused with no signal.
- Not exercised: SIGKILL escalation (child always died on TERM), signal PermissionError path, a real PID recycle, and port-binding behaviour.

## Part B results (NEW-970)
- Initial run (`partB_run1.log`): 33 PASS / 2 FAIL. Both FAILs were harness mistakes, kept here: my `subprocess.Popen` spy also counted the Popen that `subprocess.run` calls internally, so `calls` held 2 entries for one invocation (`calls=[('run', ['termux-speech-to-text']), ('popen', ['termux-speech-to-text'])]`) and the "exactly once" assertion tripped. The fake's own marker file showed a single line (`marker=['stt invoked argv=']`) in that same run, i.e. one real invocation. The B4 failure was the same cause (marker had 1 line with the text).
- Corrected resumed run (`partB_run2_corrected.log`, spy ignores Popen nested inside run): 35 PASS / 35, 0 FAIL.
- Covered in the corrected run: confirm True invokes the fake exactly once with one allowed HIGH_IMPACT audit row; confirm None / `lambda: False` / EOFError / KeyboardInterrupt / RuntimeError(secret) / truthy `"yes"` / non-callable all return None, marker absent, no subprocess call, audit rows all `refused`; real main.py adapter with EOF, KeyboardInterrupt, and non-tty: None, marker absent; nonzero-exit STT fake with JSON text returns None (marker present, one line, audit `failed`); speak success invokes the TTS fake once with the text in argv, one ACT audit row; speak nonzero returns False with `failed`. Audit bytes never contained the transcript, speak text, `termux-*` names or `Unset`.

No result contradicted the implementer/reviewer expectations.

## Verbatim log: Part A (partA_run1.log)
```
== environment ==
CODEY_STATE_DIR = /data/data/com.termux/files/usr/tmp/g13/A_1/state HOME = /data/data/com.termux/files/usr/tmp/g13/A_1/home
rg.CODEY_STATE_DIR = /data/data/com.termux/files/usr/tmp/g13/A_1/state
lv.LLAMA_SERVER_BIN = /data/data/com.termux/files/usr/tmp/g13/A_1/bin/llama-server
uid = 10247

== A1 capture (real /proc) ==
child pid 9193 cmdline: b'/data/data/com.termux/files/usr/tmp/g13/A_1/bin/llama-server -m /data/data/com.termux/files/usr/tmp/g13/A_1/model.gguf --port 18931 -c 2048 ' exe -> /data/data/com.termux/files/usr/tmp/g13/A_1/bin/llama-server
capture result: {'pid': 9193, 'boot_id': 'f3023781-05a2-44b7-a7ec-43f30d1d8422', 'start_ticks': 105208576, 'uid': 10247, 'parent_pid': 9189, 'state': 'S'}
PASS A1 capture succeeds on exe/model/port match 
PASS A1 captured identity matches independent process_info {'pid': 9193, 'boot_id': 'f3023781-05a2-44b7-a7ec-43f30d1d8422', 'start_ticks': 105208576, 'uid': 10247, 'parent_pid': 9189, 'state': 'S'}
PASS A1 refused: wrong port param None
PASS A1 refused: wrong model param None
PASS A1 refused: resolve returns other pid None
PASS A1 refused: resolved ctx >= wanted None
PASS A1 refused: bool port None
PASS A1 refused: pid 1 None
PASS A1 refused: own pid (exe is python, not stub) None
  variant exe mismatch (same name, different path) pid 9195 cmdline: b'/data/data/com.termux/files/usr/tmp/g13/A_1/other/llama-server -m /data/data/com.termux/files/usr/tmp/g13/A_1/model.gguf --port 18931 -c 2048 ' exe -> /data/data/com.termux/files/usr/tmp/g13/A_1/other/llama-server
PASS A1 refused: exe mismatch (same name, different path) None
  variant argv port differs from expected pid 9196 cmdline: b'/data/data/com.termux/files/usr/tmp/g13/A_1/bin/llama-server -m /data/data/com.termux/files/usr/tmp/g13/A_1/model.gguf --port 18938 -c 2048 ' exe -> /data/data/com.termux/files/usr/tmp/g13/A_1/bin/llama-server
PASS A1 refused: argv port differs from expected None
  variant argv model differs from expected pid 9197 cmdline: b'/data/data/com.termux/files/usr/tmp/g13/A_1/bin/llama-server -m /data/data/com.termux/files/usr/tmp/g13/A_1/model2.gguf --port 18931 -c 2048 ' exe -> /data/data/com.termux/files/usr/tmp/g13/A_1/bin/llama-server
PASS A1 refused: argv model differs from expected None
  variant duplicate --port flags pid 9208 cmdline: b'/data/data/com.termux/files/usr/tmp/g13/A_1/bin/llama-server -m /data/data/com.termux/files/usr/tmp/g13/A_1/model.gguf --port 18931 -c 2048 --port 18931 ' exe -> /data/data/com.termux/files/usr/tmp/g13/A_1/bin/llama-server
PASS A1 refused: duplicate --port flags None
  variant duplicate -m flags pid 9209 cmdline: b'/data/data/com.termux/files/usr/tmp/g13/A_1/bin/llama-server -m /data/data/com.termux/files/usr/tmp/g13/A_1/model.gguf --port 18931 -c 2048 -m /data/data/com.termux/files/usr/tmp/g13/A_1/model.gguf ' exe -> /data/data/com.termux/files/usr/tmp/g13/A_1/bin/llama-server
PASS A1 refused: duplicate -m flags None
PASS A1 refused: non-decimal port '18931x' None
PASS A1 refused: missing --port 
PASS A1 accepted: --model=/--port= forms 
PASS A1 ZERO signals sent during all capture calls signals=[]
PASS A1 all spawned children still alive after refusals 

== A4 replaced identity (expected dict edited; /proc real) ==
  edited start_ticks -> ForeignStopOutcome(outcome='unsafe', attempted=False, replaced=True) foreign_state: replaced
PASS A4 edited start_ticks=105208577: no signal, outcome unsafe/replaced 
  edited boot_id -> ForeignStopOutcome(outcome='unsafe', attempted=False, replaced=True) foreign_state: replaced
PASS A4 edited boot_id=00000000-0000-0000-0000-000000000000: no signal, outcome unsafe/replaced 
  edited start_ticks -> ForeignStopOutcome(outcome='unsafe', attempted=False, replaced=True) foreign_state: replaced
PASS A4 edited start_ticks=105208575: no signal, outcome unsafe/replaced 
   expected pid != target -> ForeignStopOutcome(outcome='unsafe', attempted=False, replaced=False)
PASS A4 expected pid != target: unsafe, no signal 
   uid mismatch -> ForeignStopOutcome(outcome='unsafe', attempted=False, replaced=False)
PASS A4 uid mismatch: unsafe, no signal 
   expected None -> ForeignStopOutcome(outcome='unsafe', attempted=False, replaced=False)
PASS A4 expected None: unsafe, no signal 
   empty dict -> ForeignStopOutcome(outcome='unsafe', attempted=False, replaced=False)
PASS A4 empty dict: unsafe, no signal 
PASS A4 bad wait_s=True: unsafe, no signal 
PASS A4 bad wait_s=-1: unsafe, no signal 
PASS A4 bad wait_s=inf: unsafe, no signal 
PASS A4 bad wait_s='8': unsafe, no signal 
PASS A4 pid 1 refused, no signal 
  signals so far: [] child alive: True

== A2 full _upgrade_resident_if_safe: kill + release ==
registered row: [{'slot_id': '7ef37a9cbba74a6aa1c70ba69ff2d835', 'model_id': 'primary', 'cost_bytes': 1234, 'pid': 9193, 'port': 18931, 'threads': None, 'status': 'resident', 'registered_at': 1792239099.7671144, 'swap_bytes_claimed': 0, 'n_ctx': 2048}]
daemon_task_in_progress() (real, disposable state dir) -> False
result: killed elapsed 0.22s signals: [(9193, <Signals.SIGTERM: 15>)]
child poll() (before wait): -15 -> zombie reaped by poll
PASS A2 returns killed killed
PASS A2 exactly one SIGTERM to own child, no SIGKILL [(9193, <Signals.SIGTERM: 15>)]
PASS A2 child exited by SIGTERM (rc=-15) and reaped by harness -15
PASS A2 original row released []
PASS A2 /proc entry gone after reap 

== A2b release_slot_if_unchanged: changed row preserved (uncontended) ==
PASS A2b changed row -> False, row preserved [{'slot_id': '2f4873b27d10460a97459431ac322717', 'model_id': 'primary', 'cost_bytes': 1234, 'pid': 9225, 'port': 18931, 'threads': None, 'status': 'resident', 'registered_at': 1792239100.310343, 'swap_bytes_claimed': 0, 'n_ctx': 4096}]
PASS A2b confirm_dead non-True -> False, row preserved 
PASS A2b confirm_dead raises -> False, row preserved 
PASS A2b unchanged + confirm_dead True -> True, row removed 

== A2c full path refusal: child exe mismatch registered as resident ==
PASS A2c wrong-exe resident -> not_safe, zero signals, child alive, row kept res=not_safe signals=[]

== A3a contended lock, direct release_slot_if_unchanged ==
holder log: [('child dead, reaped', -9), ('swapped in', {'slot_id': 'successor-gen-2', 'model_id': 'primary', 'cost_bytes': 1234, 'pid': 9189, 'port': 18931, 'threads': None, 'status': 'resident', 'registered_at': 1792239100.7034247, 'swap_bytes_claimed': 0, 'n_ctx': 8192})] | releaser blocked while lock held: True | result: [False, 1.1193671226501465]
rows after: [{'slot_id': 'successor-gen-2', 'model_id': 'primary', 'cost_bytes': 1234, 'pid': 9189, 'port': 18931, 'threads': None, 'status': 'resident', 'registered_at': 1792239100.7034247, 'swap_bytes_claimed': 0, 'n_ctx': 8192}]
PASS A3a releaser was genuinely blocked on the held flock 
PASS A3a release returned False 
PASS A3a successor row preserved intact 

== A3b contended lock inside full _upgrade_resident_if_safe ==
result: port_stuck elapsed 1.73s [('real kill outcome', ForeignStopOutcome(outcome='exited', attempted=True, replaced=False)), 'swapped successor in while holding lock'] signals: [(9231, <Signals.SIGTERM: 15>)]
rows after: [{'slot_id': 'successor-gen-3', 'model_id': 'primary', 'cost_bytes': 1234, 'pid': 9189, 'port': 18931, 'threads': None, 'status': 'resident', 'registered_at': 1792239102.0039804, 'swap_bytes_claimed': 0, 'n_ctx': 8192}]
PASS A3b returns port_stuck (accounting retained, respawn refused) port_stuck
PASS A3b release call blocked on lock (>=1s elapsed) 1.73s
PASS A3b successor row preserved 
PASS A3b only a TERM to owned child [(9231, <Signals.SIGTERM: 15>)]

leftover harness children in /proc: []
SUMMARY 48 pass / 48 total; FAILS: []
exit=0
```

## Verbatim log: Part B initial run (partB_run1.log, 2 harness-mistake FAILs retained)
```
--- command -v:
/data/data/com.termux/files/usr/tmp/g13/B_1/fakebin/termux-speech-to-text
/data/data/com.termux/files/usr/tmp/g13/B_1/fakebin/termux-tts-speak
PATH = /data/data/com.termux/files/usr/tmp/g13/B_1/fakebin
command -v termux-speech-to-text -> /data/data/com.termux/files/usr/tmp/g13/B_1/fakebin/termux-speech-to-text
command -v termux-tts-speak -> /data/data/com.termux/files/usr/tmp/g13/B_1/fakebin/termux-tts-speak
ℹ  [Voice] Listening... (speak now, Ctrl+C to cancel)
✓  [Voice] Heard: CANNED-TRANSCRIPT-qq77
PASS B1 listen(confirm=True) returns canned transcript 'CANNED-TRANSCRIPT-qq77'
FAIL B1 fake invoked exactly once marker=['stt invoked argv='] calls=[('run', ['termux-speech-to-text']), ('popen', ['termux-speech-to-text'])]
PASS B1 one audit row allowed HIGH_IMPACT voice.listen [{'ts': 1792239046.5289636, 'authority': 'HIGH_IMPACT', 'action': 'voice.listen', 'command': 'voice.listen', 'outcome': 'allowed', 'reason': 'command executed'}]
PASS B1 audit bytes lack transcript {"ts": 1792239046.5289636, "authority": "HIGH_IMPACT", "action": "voice.listen", "command": "voice.listen", "outcome": "allowed", "reason": "command executed"}

⚠  [Voice] Recording refused or failed.
PASS B2 deny[None] returns None r=None exc=None
PASS B2 deny[None] marker file absent, no subprocess marker_exists=False calls=[]
PASS B2 deny[None] audit rows all refused, no payload ['refused']
⚠  [Voice] Recording refused or failed.
PASS B2 deny[lambda False] returns None r=None exc=None
PASS B2 deny[lambda False] marker file absent, no subprocess marker_exists=False calls=[]
PASS B2 deny[lambda False] audit rows all refused, no payload ['refused']
⚠  [Voice] Recording refused or failed.
PASS B2 deny[EOFError] returns None r=None exc=None
PASS B2 deny[EOFError] marker file absent, no subprocess marker_exists=False calls=[]
PASS B2 deny[EOFError] audit rows all refused, no payload ['refused']
⚠  [Voice] Recording refused or failed.
PASS B2 deny[KeyboardInterrupt] returns None r=None exc=None
PASS B2 deny[KeyboardInterrupt] marker file absent, no subprocess marker_exists=False calls=[]
PASS B2 deny[KeyboardInterrupt] audit rows all refused, no payload ['refused']
⚠  [Voice] Recording refused or failed.
PASS B2 deny[RuntimeError(secret)] returns None r=None exc=None
PASS B2 deny[RuntimeError(secret)] marker file absent, no subprocess marker_exists=False calls=[]
PASS B2 deny[RuntimeError(secret)] audit rows all refused, no payload ['refused']
⚠  [Voice] Recording refused or failed.
PASS B2 deny[truthy 'yes'] returns None r=None exc=None
PASS B2 deny[truthy 'yes'] marker file absent, no subprocess marker_exists=False calls=[]
PASS B2 deny[truthy 'yes'] audit rows all refused, no payload ['refused']
⚠  [Voice] Recording refused or failed.
PASS B2 deny[not callable] returns None r=None exc=None
PASS B2 deny[not callable] marker file absent, no subprocess marker_exists=False calls=[]
PASS B2 deny[not callable] audit rows all refused, no payload ['refused']
⚠  [Voice] Recording refused or failed.
PASS B2b main.py adapter input raises EOFError -> None, marker absent r=None
⚠  [Voice] Recording refused or failed.
PASS B2b main.py adapter input raises KeyboardInterrupt -> None, marker absent r=None
⚠  [Voice] Recording refused or failed.
PASS B2b main.py adapter non-tty -> None, marker absent 
ℹ  [Voice] Listening... (speak now, Ctrl+C to cancel)
⚠  [Voice] Recording refused or failed.
PASS B3 nonzero-exit fake with JSON text returns None None
PASS B3 fake invoked once (marker 1 line) ['stt invoked argv=']
PASS B3 audit outcome failed, no payload [{'ts': 1792239046.8535817, 'authority': 'HIGH_IMPACT', 'action': 'voice.listen', 'command': 'voice.listen', 'outcome': 'failed', 'reason': 'Voice recording execution failed'}]
PASS B4 speak returns True True
FAIL B4 tts fake invoked exactly once with text in argv ['tts invoked argv=Canned speak sentence zz99']
PASS B4 audit: one ACT voice.speak row, no text/argv [{'ts': 1792239046.8953454, 'authority': 'ACT', 'action': 'voice.speak', 'command': 'voice.speak', 'outcome': 'allowed', 'reason': 'command executed'}]
PASS B4 speak nonzero fake returns False + failed audit False
PATH = /data/data/com.termux/files/usr/tmp/g13/B_1/fakebin
command -v termux-speech-to-text -> /data/data/com.termux/files/usr/tmp/g13/B_1/fakebin/termux-speech-to-text
command -v termux-tts-speak -> /data/data/com.termux/files/usr/tmp/g13/B_1/fakebin/termux-tts-speak
SUMMARY 33 pass / 35 total; FAILS: ['B1 fake invoked exactly once', 'B4 tts fake invoked exactly once with text in argv']
exit=0
```

## Verbatim log: Part B corrected run (partB_run2_corrected.log)
```
--- command -v:
/data/data/com.termux/files/usr/tmp/g13/B_2/fakebin/termux-speech-to-text
/data/data/com.termux/files/usr/tmp/g13/B_2/fakebin/termux-tts-speak
PATH = /data/data/com.termux/files/usr/tmp/g13/B_2/fakebin
command -v termux-speech-to-text -> /data/data/com.termux/files/usr/tmp/g13/B_2/fakebin/termux-speech-to-text
command -v termux-tts-speak -> /data/data/com.termux/files/usr/tmp/g13/B_2/fakebin/termux-tts-speak
ℹ  [Voice] Listening... (speak now, Ctrl+C to cancel)
✓  [Voice] Heard: CANNED-TRANSCRIPT-qq77
PASS B1 listen(confirm=True) returns canned transcript 'CANNED-TRANSCRIPT-qq77'
PASS B1 fake invoked exactly once marker=['stt invoked argv='] calls=[('run', ['termux-speech-to-text'])]
PASS B1 one audit row allowed HIGH_IMPACT voice.listen [{'ts': 1792239053.879055, 'authority': 'HIGH_IMPACT', 'action': 'voice.listen', 'command': 'voice.listen', 'outcome': 'allowed', 'reason': 'command executed'}]
PASS B1 audit bytes lack transcript {"ts": 1792239053.879055, "authority": "HIGH_IMPACT", "action": "voice.listen", "command": "voice.listen", "outcome": "allowed", "reason": "command executed"}

⚠  [Voice] Recording refused or failed.
PASS B2 deny[None] returns None r=None exc=None
PASS B2 deny[None] marker file absent, no subprocess marker_exists=False calls=[]
PASS B2 deny[None] audit rows all refused, no payload ['refused']
⚠  [Voice] Recording refused or failed.
PASS B2 deny[lambda False] returns None r=None exc=None
PASS B2 deny[lambda False] marker file absent, no subprocess marker_exists=False calls=[]
PASS B2 deny[lambda False] audit rows all refused, no payload ['refused']
⚠  [Voice] Recording refused or failed.
PASS B2 deny[EOFError] returns None r=None exc=None
PASS B2 deny[EOFError] marker file absent, no subprocess marker_exists=False calls=[]
PASS B2 deny[EOFError] audit rows all refused, no payload ['refused']
⚠  [Voice] Recording refused or failed.
PASS B2 deny[KeyboardInterrupt] returns None r=None exc=None
PASS B2 deny[KeyboardInterrupt] marker file absent, no subprocess marker_exists=False calls=[]
PASS B2 deny[KeyboardInterrupt] audit rows all refused, no payload ['refused']
⚠  [Voice] Recording refused or failed.
PASS B2 deny[RuntimeError(secret)] returns None r=None exc=None
PASS B2 deny[RuntimeError(secret)] marker file absent, no subprocess marker_exists=False calls=[]
PASS B2 deny[RuntimeError(secret)] audit rows all refused, no payload ['refused']
⚠  [Voice] Recording refused or failed.
PASS B2 deny[truthy 'yes'] returns None r=None exc=None
PASS B2 deny[truthy 'yes'] marker file absent, no subprocess marker_exists=False calls=[]
PASS B2 deny[truthy 'yes'] audit rows all refused, no payload ['refused']
⚠  [Voice] Recording refused or failed.
PASS B2 deny[not callable] returns None r=None exc=None
PASS B2 deny[not callable] marker file absent, no subprocess marker_exists=False calls=[]
PASS B2 deny[not callable] audit rows all refused, no payload ['refused']
⚠  [Voice] Recording refused or failed.
PASS B2b main.py adapter input raises EOFError -> None, marker absent r=None
⚠  [Voice] Recording refused or failed.
PASS B2b main.py adapter input raises KeyboardInterrupt -> None, marker absent r=None
⚠  [Voice] Recording refused or failed.
PASS B2b main.py adapter non-tty -> None, marker absent 
ℹ  [Voice] Listening... (speak now, Ctrl+C to cancel)
⚠  [Voice] Recording refused or failed.
PASS B3 nonzero-exit fake with JSON text returns None None
PASS B3 fake invoked once (marker 1 line) ['stt invoked argv=']
PASS B3 audit outcome failed, no payload [{'ts': 1792239053.999482, 'authority': 'HIGH_IMPACT', 'action': 'voice.listen', 'command': 'voice.listen', 'outcome': 'failed', 'reason': 'Voice recording execution failed'}]
PASS B4 speak returns True True
PASS B4 tts fake invoked exactly once with text in argv ['tts invoked argv=Canned speak sentence zz99']
PASS B4 audit: one ACT voice.speak row, no text/argv [{'ts': 1792239054.0371137, 'authority': 'ACT', 'action': 'voice.speak', 'command': 'voice.speak', 'outcome': 'allowed', 'reason': 'command executed'}]
PASS B4 speak nonzero fake returns False + failed audit False
PATH = /data/data/com.termux/files/usr/tmp/g13/B_2/fakebin
command -v termux-speech-to-text -> /data/data/com.termux/files/usr/tmp/g13/B_2/fakebin/termux-speech-to-text
command -v termux-tts-speak -> /data/data/com.termux/files/usr/tmp/g13/B_2/fakebin/termux-tts-speak
SUMMARY 35 pass / 35 total; FAILS: []
exit=0
```
