# WP2.1 group14 slices 14b / 14c / 14e: disposable on-device verification

Date: 2026-10-18. Commits under test: 249b61b (14b, 14c) and 96ad7f4 (14e). No source or tracking doc was edited; this file is the only new repo entry. No model, llama binary, network or real service was used. Raw logs, harnesses and workspaces: `/data/data/com.termux/files/usr/tmp/g14bce/` (logs fsynced; harness scripts in `h/`).

## Method and what is REAL vs FAKED

Every harness ran as `env -u HTTP_PROXY ... HOME=$T/home|per-case CODEY_STATE_DIR=... CODEY_ACTION_GATEWAY_AUDIT=<private file> python -I -B` from outside the repo with explicit `sys.path` (repo imported read-only; `-B` so no .pyc is written into the tree).

REAL: core.filehistory, core.filesystem.Filesystem (incl. `restore`), core.checkpoint.create_checkpoint (writes into the disposable state dir; the tmp CODE_DIR has no git worktree and none exists in any ancestor of the tmp tree, so the git step is skipped), core.action_gateway (private audit file), core.linter, /data/data/com.termux/files/usr/bin/ruff 0.17.1, core.lora_import (`_confirm_on_tty`, `import_lora_adapter`, `rollback_to_backup`, `rollback_adoption`), core.model_registry + state DB (disposable), real kernel pty via `pty.fork` with a controlling terminal, real `/dev/tty`.

FAKED / PATCHED (all disposable):
- 14b: `core.checkpoint.CODE_DIR` and `core.filesystem.CODE_DIR` set to a tmp dir so `is_core_file` classifies `<tmp>/repo/core/x.py` as core (same approach as tests/test_undo_action_boundaries.py).
- 14b: `main._undo_confirmation` was AST-extracted verbatim from the real main.py (not `import main`) and exec'd; main.py unmodified.
- 14b: the "Ctrl-C" case uses a monkeypatched `builtins.input` raising KeyboardInterrupt (see finding F1: a real SIGINT/^C does not interrupt `input()` on this device even for a bare `python -c`).
- 14c: fake `flake8` and `mypy` shell scripts first on PATH that append to a marker file.
- 14e: `core.loader_v2` replaced by a stub module in `sys.modules` (records unload/load_primary events with backup/marker/cfg state); fake `~/llama.cpp/convert-lora.py` (writes `MERGE_MARKER` and the `--outfile`); tiny fake text files for base model, adapter, safetensors. `llama_cpp` is not installed, so `_merge_with_shell` ran my fake script. Gate passes use a `SimpleNamespace(promote=True, ...)` FAKE gate decision (the real benchmark gate was not run); override cases use `operator_override=True` with the real default `no_evaluator()` decision.

## free -h and process checks (literal)

First (start of session, `baseline.txt`):
```
               total        used        free      shared  buff/cache   available
Mem:            10Gi       6.9Gi       259Mi        68Mi       4.0Gi       3.9Gi
Swap:           15Gi       4.7Gi        11Gi
```
Per-cycle snapshots taken before each harness run are in free-b-before.txt, free-b2-before.txt, free-c-before.txt, free-c2-before.txt, free-e1-before.txt, free-e2-before.txt. Samples:
`free-b-before.txt`
```
               total        used        free      shared  buff/cache   available
Mem:            10Gi       7.3Gi       252Mi        81Mi       3.6Gi       3.5Gi
Swap:           15Gi       4.7Gi        11Gi
```
`free-e2-before.txt`
```
               total        used        free      shared  buff/cache   available
Mem:            10Gi       7.7Gi       216Mi        86Mi       3.3Gi       3.2Gi
Swap:           15Gi       4.5Gi        11Gi
```
Last (free-final.txt):
```
               total        used        free      shared  buff/cache   available
Mem:            10Gi       7.7Gi       221Mi        87Mi       3.3Gi       3.1Gi
Swap:           15Gi       4.5Gi        11Gi
```
Final process check, `ps -A -o pid,args` filtered for `llama-server|b_child|e_flow|e_tty|c_harness` (no match; no llama-server was ever started by this work):
```
(end ps filter)
```
Memory was tight throughout (free 200-500Mi, available 3.1-3.9Gi, swap 4.5-4.7Gi used) but nothing here loads a model and no instability occurred.

## Integrity

`sha256sum` of core/filehistory.py core/filesystem.py core/linter.py core/lora_import.py main.py core/checkpoint.py before (baseline.txt) and after (final_state.txt) are identical:
```
084c7d9e00194d0bdb255d56227151224d581d9853f82afad8511b9dbe343256  core/filehistory.py
b20fe86649226cf49e3021737015ef3db974a9e01b78d2956c362864f7c69402  core/filesystem.py
20fa950b8af7a5da0c9ad3f0004f3fbcd330f35b67e032b7bf5114f0eb61549e  core/linter.py
bc707aaf5a9982478b1f0a40f34f8fc31d36bd3738c041bf21b5a33fc8568303  core/lora_import.py
59a822da794a7432f034f65bd41573b3a74a113240b1053abe5e99e747cea8f9  main.py
6b913028634c3e0cce5338efec3cec6d60e8fc3c5a473329b320c87398637d6a  core/checkpoint.py
```
`git status --short` excluding pre-existing `.claude/` entries was empty before and after (final_state.txt shows nothing after `---`). A scan for any repo file (excluding .git and .claude) with mtime newer than the baseline found none. This report was written after that snapshot.

## Summary

| Slice | Checks | Result |
|---|---|---|
| 14b /undo | 44 (b_run2.log) | 44 PASS. Run 1 had 2 harness FAILs (real Ctrl-C), kept below with the corrected run. |
| 14c ruff envelope | 28 (c_run2.log) | 28 PASS. Run 1 had 3 harness FAILs (kept below). Plus one real pre-existing finding F2. |
| 14e LoRA gate | 14 tty (e_tty_run1.log) + 55 flow (e_flow_run1.log) | 69 PASS, first try. |

## Findings that need attention

F1 (environment, affects the 14b Ctrl-C claim). In a real pty, a ^C (and `os.kill(pid, SIGINT)`) does NOT interrupt Python's `input()` on this device, even for a bare `python -I -c 'input("prompt> ")'` (probe: `h/ctrlc_probe.py`, output below). It does interrupt `os.read` (probe 2) and `_confirm_on_tty` (14e), which reads with `os.read`. So the 14b prompt (`_undo_confirmation` uses `input()`) cannot be cancelled with Ctrl-C in this configuration; the child hung until my harness SIGKILLed its own PID. This is not caused by the 14b code (a bare python reproduces it), and the gateway's KeyboardInterrupt to refusal mapping was verified only with a simulated `KeyboardInterrupt` from `input`. Whether the real interactive REPL differs (e.g. readline loaded in the real main) was not tested. n / empty / EOF (^D) are verified for real.

F2 (real, pre-existing, outside 14c's envelope change). `core.linter._parse_colon_format` strips only the absolute filepath or the bare basename as prefix, but ruff concise output prints cwd-relative paths for files under the cwd. When the process cwd is an ANCESTOR of the file's directory and the absolute path is passed, ruff prints `ws_noconf/t.py:1:1: ...`, the parser matches neither prefix, and all violations are silently dropped (`run_linter` returns `ruff, 0 issues` while raw ruff reports 2). Evidence: `c_parser_probe.log` below and c_run1.log (`A run_linter -> ruff []`). Works when cwd is the file's dir or unrelated to it. The parser and `--output-format=concise` predate 14c (git show 249b61b shows they were not changed), so it is not a 14c regression; it should be logged to NEW_ISSUES.md by the coordinator (rule 8). Not fixed here.

F3 (observation, not a defect). User-facing `[ERROR]` strings from `/undo` failures contain the path and the errno text (for example `[Errno 13] Permission denied: '<path>'`); only the audit rows are static. That matches the documented design (static audit, caller message carries detail).

F4 (observation). Refusal of a LoRA adoption with no controlling terminal is audited with reason `Human confirmation unavailable due to callback failure; command not attempted.` (OSError path); decline gives `Human confirmation declined...`; EOF/^C give `...unavailable or interrupted...`. All are refusals with the HIGH_IMPACT authority and static `lora_import.adopt` / `lora adapter adoption` labels.

## 14b results

### Run 1 (b_run1.log): 42 PASS, 2 FAIL, harness mistake kept on record
Failed lines (literal):
```
FAIL: 14b core pty CtrlC: file unchanged None
FAIL: 14b core pty CtrlC: refused audit row, no checkpoint, history intact ([], [])
```
Cause: the child never returned from `input()` after a real ^C (`rc=9` in the log is my own SIGKILL after the 60 s harness timeout; the `TIMEOUT-killed-own-pid` entry confirms it). I first suspected my harness; probes below show it is the device's `input()` behaviour (F1). Real-^C repeat x3 (output of the background run, `b_ctrlc_real_sigint_hang.log`):
```
0 status 9 signaled True sig 9 exit None [('sent', b'\x03', 0.76), ('TIMEOUT-killed-own-pid', 29731)] "CHILD-START isatty=True confirm_is_none=False\r\nRestore Codey core file /data/data/com.termux/files/usr/tmp/g14bce/b/core_pty_CtrlC/repo/core/x.py from history? [y/N]: <<SENT b'\\x03'>>^C"
(no audit)
1 status 9 signaled True sig 9 exit None [('sent', b'\x03', 1.08), ('TIMEOUT-killed-own-pid', 30337)] "CHILD-START isatty=True confirm_is_none=False\r\nRestore Codey core file /data/data/com.termux/files/usr/tmp/g14bce/b/core_pty_CtrlC/repo/core/x.py from history? [y/N]: <<SENT b'\\x03'>>^C"
(no audit)
2 status 9 signaled True sig 9 exit None [('sent', b'\x03', 0.73), ('TIMEOUT-killed-own-pid', 31137)] "CHILD-START isatty=True confirm_is_none=False\r\nRestore Codey core file /data/data/com.termux/files/usr/tmp/g14bce/b/core_pty_CtrlC/repo/core/x.py from history? [y/N]: <<SENT b'\\x03'>>^C"
(no audit)

[exited with code 0]
```
Bare-python probe (`h/ctrlc_probe.py`, output copied from the terminal):
```
plain status 9 [('sent', b'\x03', 0.55), ('TIMEOUT-killed-own-pid', 32257)] "SIGINT handler: <built-in function default_int_handler>\r\nprompt> <<SENT b'\\x03'>>^C"
os.kill-SIGINT status 9 [('os.kill SIGINT own pid', 32571, 0.58), ('TIMEOUT-killed-own-pid', 32571)] "SIGINT handler: <built-in function default_int_handler>\r\nprompt> <<SENT 'SIGINT'>>"
```
Probe 2 (`h/ctrlc_probe2.py`): os.read IS interrupted by both ^C and os.kill:
```
b'\x03' status 9 [('sent', b'\x03', 0.55), ('sent', b'\x03', 1.05), ('TIMEOUT-killed-own-pid', 372)] "ready\r\n<<SENT b'\\x03'>>^CHANDLER RAN\r\nos.read interrupted\r\n<<SENT b'\\x03'>>prompt> ^C"
'SIGINT' status 9 [('os.kill SIGINT own pid', 507, 0.55), ('os.kill SIGINT own pid', 507, 1.05), ('TIMEOUT-killed-own-pid', 507)] "ready\r\n<<SENT 'SIGINT'>>HANDLER RAN\r\nos.read interrupted\r\n<<SENT 'SIGINT'>>prompt> "
```
### Corrected run 2 (b_run2.log): all PASS; the Ctrl-C case now uses a simulated KeyboardInterrupt from `input`
Last line: `SUMMARY 44 pass of 44 FAILS: []`

Key excerpt, core-file undo approved via real pty with the real `_undo_confirmation` and real checkpoint:
```
--- case=core_pty_y mode=conf pty=True rc=0 sent_all=True
CHILD-START isatty=True confirm_is_none=False
Restore Codey core file /data/data/com.termux/files/usr/tmp/g14bce/b/core_pty_y/repo/core/x.py from history? [y/N]: <<SENT b'y\n'>>y
[1;36mℹ  Checkpoint: creating '1792299131-9c7320fc' - Self-modification: x.py[0m
[1;32m✓  Checkpoint '1792299131-9c7320fc' created (2 files backed up)[0m
[1;36mℹ  Checkpoint created before modifying [0m
[1;36m/data/data/com.termux/files/usr/tmp/g14bce/b/core_pty_y/repo/core/x.py[0m
[1;32m✓  Restored [0m
[1;32m/data/data/com.termux/files/usr/tmp/g14bce/b/core_pty_y/repo/core/x.py to [0m
[1;32mversion from 00:52:11 (1 older version available)[0m

STATE={"msg": "Restored /data/data/com.termux/files/usr/tmp/g14bce/b/core_pty_y/repo/core/x.py to version from 00:52:11 (1 older version available)", "confirm_is_none": false, "isatty": true, "target_content": "old = 1\n", "extra": {}, "real_content": null, "versions": [["00:52:11 (pre-undo)", "new = 2\n"]], "checkpoints": ["1792299131-9c7320fc/core/x.py"], "ckpt_dirs": ["1792299131-9c7320fc"], "base": "/data/data/com.termux/files/usr/tmp/g14bce/b/core_pty_y"}
NEW_CKPT=['1792299131-9c7320fc']
AUDIT:
{"ts": 1792299131.8412073, "authority": "HIGH_IMPACT", "action": "filehistory.undo", "command": "undo restore", "outcome": "allowed", "reason": "command executed"}

```
Simulated KeyboardInterrupt case and read_fail case:
```
--- case=core_pty_CtrlC mode=conf pty=True rc=0 sent_all=False
CHILD-START isatty=True confirm_is_none=False
Restore Codey core file /data/data/com.termux/files/usr/tmp/g14bce/b/core_pty_CtrlC/repo/core/x.py from history? [y/N]: <simulated KeyboardInterrupt>

STATE={"msg": "[ERROR] Could not restore /data/data/com.termux/files/usr/tmp/g14bce/b/core_pty_CtrlC/repo/core/x.py: Human confirmation unavailable or interrupted; command not attempted.", "confirm_is_none": false, "isatty": true, "target_content": "new = 2\n", "extra": {}, "real_content": null, "versions": [["00:52:15", "old = 1\n"]], "checkpoints": ["1792299131-9c7320fc/core/x.py"], "ckpt_dirs": ["1792299131-9c7320fc"], "base": "/data/data/com.termux/files/usr/tmp/g14bce/b/core_pty_CtrlC"}
NEW_CKPT=[]
AUDIT:
{"ts": 1792299135.3537638, "authority": "HIGH_IMPACT", "action": "filehistory.undo", "command": "undo restore", "outcome": "refused", "reason": "Human confirmation unavailable or interrupted; command not attempted."}

--- case=read_fail mode=none pty=False rc=0 sent_all=True
CHILD-START isatty=False confirm_is_none=True

STATE={"msg": "[ERROR] Could not restore /data/data/com.termux/files/usr/tmp/g14bce/b/read_fail/ws/secret.txt: [Errno 13] Permission denied: '/data/data/com.termux/files/usr/tmp/g14bce/b/read_fail/ws/secret.txt'", "confirm_is_none": true, "isatty": false, "target_content": "NEW-SECRET-CONTENT", "extra": {}, "real_content": null, "versions": [["00:52:18", "OLD-SECRET-CONTENT"]], "checkpoints": ["1792299131-9c7320fc/core/x.py"], "ckpt_dirs": ["1792299131-9c7320fc"], "base": "/data/data/com.termux/files/usr/tmp/g14bce/b/read_fail"}
NEW_CKPT=[]
AUDIT:
{"ts": 1792299138.8524063, "authority": "ACT", "action": "filehistory.undo", "command": "undo restore", "outcome": "failed", "reason": "restore failed"}
```
All 14b check lines (b_run2.log), verbatim:
```
PASS: 14b ordinary /undo restores file old
PASS: 14b ordinary: exactly one audit row ACT allowed [{'ts': 1792299129.8370593, 'authority': 'ACT', 'action': 'filehistory.undo', 'command': 'undo restore', 'outcome': 'allowed', 'reason': 'command executed'}]
PASS: 14b ordinary: history = [pre-undo 'new'] only [['00:52:09 (pre-undo)', 'new']]
PASS: 14b ordinary: no checkpoint taken []
PASS: 14b ordinary: audit has no path/content []
PASS: 14b core no-tty: _undo_confirmation returned None (real fn) 
PASS: 14b core no-tty: refused, file untouched [ERROR] Could not restore /data/data/com.termux/files/usr/tmp/g14bce/b/core_noconfirm/repo/core/x.py: HIGH_IMPACT command with no confirmation path available; failing closed per policy (not attempted).
PASS: 14b core no-tty: audit HIGH_IMPACT refused, one row [{'ts': 1792299130.305295, 'authority': 'HIGH_IMPACT', 'action': 'filehistory.undo', 'command': 'undo restore', 'outcome': 'refused', 'reason': 'HIGH_IMPACT command with no confirmation path available; failing closed per policy (not attempted).'}]
PASS: 14b core no-tty: no checkpoint, history unchanged (1 version) ([], [['00:52:10', 'old = 1\n']])
PASS: 14b core no-tty: audit static []
PASS: 14b core confirm=None explicit: refused, untouched 
PASS: 14b core pty 'y': prompt shown on pty 
PASS: 14b core pty 'y': restored old = 1
PASS: 14b core pty 'y': audit one row HIGH_IMPACT allowed [{'ts': 1792299131.8412073, 'authority': 'HIGH_IMPACT', 'action': 'filehistory.undo', 'command': 'undo restore', 'outcome': 'allowed', 'reason': 'command executed'}]
PASS: 14b core pty 'y': exactly one real checkpoint created ['1792299131-9c7320fc']
PASS: 14b core pty 'y': checkpoint holds PRE-restore content ('new = 2') new = 2
PASS: 14b core pty 'y': history has pre-undo entry 
PASS: 14b core pty 'y': audit static []
PASS: 14b core pty n: file unchanged new = 2
PASS: 14b core pty n: refused audit row, no checkpoint, history intact ([{'ts': 1792299132.8659325, 'authority': 'HIGH_IMPACT', 'action': 'filehistory.undo', 'command': 'undo restore', 'outcome': 'refused', 'reason': 'Human confirmation declined; command not attempted.'}], [])
PASS: 14b core pty n: audit static 
PASS: 14b core pty empty: file unchanged new = 2
PASS: 14b core pty empty: refused audit row, no checkpoint, history intact ([{'ts': 1792299133.8658333, 'authority': 'HIGH_IMPACT', 'action': 'filehistory.undo', 'command': 'undo restore', 'outcome': 'refused', 'reason': 'Human confirmation declined; command not attempted.'}], [])
PASS: 14b core pty empty: audit static 
PASS: 14b core pty EOF(^D): file unchanged new = 2
PASS: 14b core pty EOF(^D): refused audit row, no checkpoint, history intact ([{'ts': 1792299134.878986, 'authority': 'HIGH_IMPACT', 'action': 'filehistory.undo', 'command': 'undo restore', 'outcome': 'refused', 'reason': 'Human confirmation unavailable or interrupted; command not attempted.'}], [])
PASS: 14b core pty EOF(^D): audit static 
PASS: 14b core pty CtrlC-simulated-KeyboardInterrupt: file unchanged new = 2
PASS: 14b core pty CtrlC-simulated-KeyboardInterrupt: refused audit row, no checkpoint, history intact ([{'ts': 1792299135.3537638, 'authority': 'HIGH_IMPACT', 'action': 'filehistory.undo', 'command': 'undo restore', 'outcome': 'refused', 'reason': 'Human confirmation unavailable or interrupted; command not attempted.'}], [])
PASS: 14b core pty CtrlC-simulated-KeyboardInterrupt: audit static 
PASS: 14b core pty --yolo: confirm None, no prompt, refused (True, True)
PASS: 14b core pty CODEY_DAEMON_MODE=1: confirm None, refused 
PASS: 14b core pty CODEY_NON_INTERACTIVE=1: confirm None, refused 
PASS: 14b symlink-escape: outside target byte-for-byte untouched outside-modified
PASS: 14b symlink-escape: refused/failed (error msg), history not popped [ERROR] Could not restore /data/data/com.termux/files/usr/tmp/g14bce/b/symlink_escape/ws/link.txt: Access denied: /data/data/com.termux/files/usr/tmp/g14bce/b/symlink_escape/outside/target.txt is outside workspace (/data/data/com.termux/files/usr/tmp/g14bce/b/symlink_escape/ws)
PASS: 14b symlink-escape: one audit row failed, static [{'ts': 1792299137.373547, 'authority': 'ACT', 'action': 'filehistory.undo', 'command': 'undo restore', 'outcome': 'failed', 'reason': 'restore failed'}]
PASS: 14b symlink->core file (no confirm): classified HIGH, refused, target untouched [{'ts': 1792299137.8246896, 'authority': 'HIGH_IMPACT', 'action': 'filehistory.undo', 'command': 'undo restore', 'outcome': 'refused', 'reason': 'HIGH_IMPACT command with no confirmation path available; failing closed per policy (not attempted).'}]
PASS: 14b .git target: refused (failed), file untouched [ERROR] Could not restore /data/data/com.termux/files/usr/tmp/g14bce/b/git_target/ws/.git/config: Access denied: /data/data/com.termux/files/usr/tmp/g14bce/b/git_target/ws/.git/config is inside a Git metadata directory (/data/data/com.termux/files/usr/tmp/g14bce/b/git_target/ws/.git) and cannot be modified.
PASS: 14b .git target: audit row failed static 'restore failed' [{'ts': 1792299138.277138, 'authority': 'ACT', 'action': 'filehistory.undo', 'command': 'undo restore', 'outcome': 'failed', 'reason': 'restore failed'}]
PASS: 14b read_text failure (chmod 000): [ERROR] returned, audit failed row [ERROR] Could not restore /data/data/com.termux/files/usr/tmp/g14bce/b/read_fail/ws/secret.txt: [Errno 13] Permission denied: '/data/data/com.termux/files/usr/tmp/g14bce/b/read_fail/ws/secret.txt'
PASS: 14b read_text failure: audit reason static, no path/content/errno []
PASS: 14b read_text failure: history not popped 
PASS: 14b write failure (chmod 444): failed row, static [{'ts': 1792299139.2389894, 'authority': 'ACT', 'action': 'filehistory.undo', 'command': 'undo restore', 'outcome': 'failed', 'reason': 'restore failed'}]
PASS: 14b write failure: content unchanged, history not popped 
SUMMARY 44 pass of 44 FAILS: []
```
Full per-case transcripts including the audit rows are in b_run2.log and per-case audit files audit-b-*.jsonl.

## 14c results

### Run 1 (c_run1.log): 23 PASS, 3 FAIL, harness mistakes kept on record
```
FAIL: control: raw ruff w/o --no-cache DOES create .ruff_cache c/control/t.py:1:1: I001 [*] Import block is un-sorted or un-formatted
FAIL: ruff run, linter name 'ruff', F401 parsed 
FAIL: no .ruff_cache created anywhere except the deliberate raw-ruff control ['/data/data/com.termux/files/usr/tmp/g14bce/.ruff_cache']
SUMMARY 23 pass of 26 FAILS: ['control: raw ruff w/o --no-cache DOES create .ruff_cache', "ruff run, linter name 'ruff', F401 parsed", 'no .ruff_cache created anywhere except the deliberate raw-ruff control']
```
Causes: (1) my control ran raw ruff with cwd=$T, so the `.ruff_cache` landed in `$T/.ruff_cache`, not in the control dir (the product runs, also with cwd=$T, were NOT the source: the same stray cache did not reappear in run 2 where control has its own cwd); (2) the A/B assertion hit finding F2 because cwd was an ancestor of the file. I removed the stray `$T/.ruff_cache` (my own tmp dir) and re-ran with the control isolated in its own cwd and product runs in the file's dir or a neutral dir.

### Corrected run 2 (c_run2.log)
```
skipped_linters() = ['flake8', 'mypy']  get_available_linters() = ['ruff', 'flake8', 'mypy']
PASS: fake flake8/mypy discoverable on PATH 
PASS: control: raw ruff w/o --no-cache DOES create .ruff_cache t.py:1:1: I001 [*] Import block is un-sorted or un-formatted
control raw `ruff check --no-cache -x.py` rc 2 stderr: error: unexpected argument '-x' found
PASS: control: raw -x.py w/o '--' is mis-parsed as option (rc=2 error) 
RAW ruff output from cwd=neutral for abs path: '/data/data/com.termux/files/usr/tmp/g14bce/c/ws_noconf/t.py:1:1: I001 [*] Import block is un-sorted or un-formatted\n/data/data/com.termux/files/usr/tmp/g14bce/c/ws_noconf/t.py:1:8: F401 [*] `os` imported but unused\nFound 2 errors.\n[*] 2 fixable with `--fix`.\n'
PARSER-PROBE run_linter(abs path, cwd elsewhere) -> ruff ['Line 1:1 [I001] [*] Import block is un-sorted or un-formatted', 'Line 1:8 [F401] [*] `os` imported but unused']
PASS: PARSER-PROBE (pre-existing _parse_colon_format): issues parsed when cwd != file dir (raw ruff reported violations; parser returned 2)
A run_linter -> ruff ['Line 1:1 [I001] [*] Import block is un-sorted or un-formatted', 'Line 1:8 [F401] [*] `os` imported but unused']
PASS: ruff run, linter name 'ruff', F401 parsed 
PASS: one audit row for this run {'ts': 1792299175.0375602, 'authority': 'ACT', 'action': 'linter.ruff', 'command': 'linter.ruff', 'outcome': 'allowed', 'reason': 'command executed'}
PASS: audit row static (action linter.ruff, no path) {'ts': 1792299175.0375602, 'authority': 'ACT', 'action': 'linter.ruff', 'command': 'linter.ruff', 'outcome': 'allowed', 'reason': 'command executed'}
B run_linter -> ruff ['Line 1:1 [I001] [*] Import block is un-sorted or un-formatted']
PASS: workspace ruff.toml honored (A/B: F401 absent with ignore) 
PASS: B: one audit row 
run_all_linters -> [('ruff', ['Line 1:1 [I001] [*] Import block is un-sorted or un-formatted', 'Line 1:8 [F401] [*] `os` imported but unused']), ('syntax', [])]
PASS: run_all_linters: ruff + syntax results, one audit row, ruff issues parsed 
-x.py -> ruff ['Line 1:1 [I001] [*] Import block is un-sorted or un-formatted', 'Line 1:8 [F401] [*] `os` imported but unused']
PASS: file named -x.py (bare relative) linted via '--': ruff, F401 parsed 
PASS: -x.py: one audit row 
FIFO -> none [] [] audit rows added: 0
PASS: FIFO: no hang, no exception, zero ruff executions/audit rows (False, 'none')
PASS: FIFO: returns no issues 
directory -> none [] [] audit rows added: 0
PASS: directory: no hang, no exception, zero ruff executions/audit rows (False, 'none')
PASS: directory: returns no issues 
symlink->dir -> none [] [] audit rows added: 0
PASS: symlink->dir: no hang, no exception, zero ruff executions/audit rows (False, 'none')
PASS: symlink->dir: returns no issues 
NUL path -> none [] [] audit rows added: 0
PASS: NUL path: no hang, no exception, zero ruff executions/audit rows (False, 'none')
PASS: NUL path: returns no issues 
nonexistent -> none [] [] audit rows added: 0
PASS: nonexistent: no hang, no exception, zero ruff executions/audit rows (False, 'none')
PASS: nonexistent: returns no issues 
CODEY_LINTER='' -> run_linter ruff 2 issues; run_all ['ruff', 'syntax']; audit rows added 2
CODEY_LINTER='ruff' -> run_linter ruff 2 issues; run_all ['ruff', 'syntax']; audit rows added 2
CODEY_LINTER='flake8' -> run_linter none 0 issues; run_all ['ruff', 'syntax']; audit rows added 1
CODEY_LINTER='mypy' -> run_linter none 0 issues; run_all ['ruff', 'syntax']; audit rows added 1
CODEY_LINTER='pylint' -> run_linter none 0 issues; run_all ['ruff', 'syntax']; audit rows added 1
PASS: fake flake8 marker ABSENT after all runs incl CODEY_LINTER=flake8 
PASS: fake mypy marker ABSENT after all runs incl CODEY_LINTER=mypy 
PASS: control: fake flake8 on PATH writes marker when actually run 
all .ruff_cache dirs under /data/data/com.termux/files/usr/tmp/g14bce : ['/data/data/com.termux/files/usr/tmp/g14bce/c/control/.ruff_cache']
PASS: no .ruff_cache created anywhere except the deliberate raw-ruff control ['/data/data/com.termux/files/usr/tmp/g14bce/c/control/.ruff_cache']
PASS: neutral cwd, ws_noconf, ws_conf, dash have no .ruff_cache 
PASS: all audit rows are linter.ruff ACT allowed static 
SUMMARY 28 pass of 28 FAILS: []
```
Final audit rows of the run (11 rows; each run_linter or run_all_linters call that reached ruff produced exactly one, FIFO/directory/symlink-to-dir/NUL/nonexistent produced zero):
```
{"ts": 1792299174.9978733, "authority": "ACT", "action": "linter.ruff", "command": "linter.ruff", "outcome": "allowed", "reason": "command executed"}
{"ts": 1792299175.0375602, "authority": "ACT", "action": "linter.ruff", "command": "linter.ruff", "outcome": "allowed", "reason": "command executed"}
{"ts": 1792299175.0854151, "authority": "ACT", "action": "linter.ruff", "command": "linter.ruff", "outcome": "allowed", "reason": "command executed"}
{"ts": 1792299175.123879, "authority": "ACT", "action": "linter.ruff", "command": "linter.ruff", "outcome": "allowed", "reason": "command executed"}
{"ts": 1792299175.166498, "authority": "ACT", "action": "linter.ruff", "command": "linter.ruff", "outcome": "allowed", "reason": "command executed"}
{"ts": 1792299175.2118678, "authority": "ACT", "action": "linter.ruff", "command": "linter.ruff", "outcome": "allowed", "reason": "command executed"}
{"ts": 1792299175.2522845, "authority": "ACT", "action": "linter.ruff", "command": "linter.ruff", "outcome": "allowed", "reason": "command executed"}
{"ts": 1792299175.2912195, "authority": "ACT", "action": "linter.ruff", "command": "linter.ruff", "outcome": "allowed", "reason": "command executed"}
{"ts": 1792299175.328135, "authority": "ACT", "action": "linter.ruff", "command": "linter.ruff", "outcome": "allowed", "reason": "command executed"}
{"ts": 1792299175.3641999, "authority": "ACT", "action": "linter.ruff", "command": "linter.ruff", "outcome": "allowed", "reason": "command executed"}
{"ts": 1792299175.3945932, "authority": "ACT", "action": "linter.ruff", "command": "linter.ruff", "outcome": "allowed", "reason": "command executed"}
{"ts": 1792299175.4407692, "authority": "ACT", "action": "linter.ruff", "command": "linter.ruff", "outcome": "allowed", "reason": "command executed"}
```
F2 probe (c_parser_probe.log):
```
cwd=/data/data/com.termux/files/usr/tmp/g14bce/c
  raw ruff first line: 'ws_noconf/t.py:1:1: I001 [*] Import block is un-sorted or un-formatted'
  run_linter(abs path) -> ruff, 0 issues []
cwd=/data/data/com.termux/files/usr/tmp/g14bce/c/ws_noconf
  raw ruff first line: 't.py:1:1: I001 [*] Import block is un-sorted or un-formatted'
  run_linter(abs path) -> ruff, 2 issues ['Line 1:1 [I001] [*] Import block is un-sorted or un-formatted', 'Line 1:8 [F401] [*] `os` imported but unused']
cwd=/data/data/com.termux/files/usr/tmp/g14bce/c/neutral
  raw ruff first line: '/data/data/com.termux/files/usr/tmp/g14bce/c/ws_noconf/t.py:1:1: I001 [*] Import block is un-sorted or un-formatted'
  run_linter(abs path) -> ruff, 2 issues ['Line 1:1 [I001] [*] Import block is un-sorted or un-formatted', 'Line 1:8 [F401] [*] `os` imported but unused']
```

## 14e results

### TTY primitive (e_tty_run1.log): 14 PASS
Real `pty.fork` child, controlling terminal, real `/dev/tty`. Stale `y\n` is written to the pty master before the child imports and prompts; a negative control (same pre-write, read from /dev/tty WITHOUT the flush) returned the queued `y\n`, proving the typeahead really was in the queue; with the flush in `_confirm_on_tty` the child was still blocked 2 s after the prompt appeared and only the fresh answer decided.
```
--- y: status=0 log=[('sent', b'y\n', 0.56)] out="PROMPT-E> <<SENT b'y\\n'>>y\r\n"
PASS: _confirm_on_tty real pty answer 'y' -> returned=True returned=True
--- yes: status=0 log=[('sent', b'yes\n', 0.56)] out="PROMPT-E> <<SENT b'yes\\n'>>yes\r\n"
PASS: _confirm_on_tty real pty answer 'yes' -> returned=True returned=True
--- Y_upper: status=0 log=[('sent', b'Y\n', 0.56)] out="PROMPT-E> <<SENT b'Y\\n'>>Y\r\n"
PASS: _confirm_on_tty real pty answer 'Y_upper' -> returned=True returned=True
--- n: status=0 log=[('sent', b'n\n', 0.56)] out="PROMPT-E> <<SENT b'n\\n'>>n\r\n"
PASS: _confirm_on_tty real pty answer 'n' -> returned=False returned=False
--- empty: status=0 log=[('sent', b'\n', 0.55)] out="PROMPT-E> <<SENT b'\\n'>>\r\n"
PASS: _confirm_on_tty real pty answer 'empty' -> returned=False returned=False
--- maybe: status=0 log=[('sent', b'yes please\n', 0.56)] out="PROMPT-E> <<SENT b'yes please\\n'>>yes please\r\n"
PASS: _confirm_on_tty real pty answer 'maybe' -> returned=False returned=False
--- EOF: status=0 log=[('sent', b'\x04', 0.55)] out="PROMPT-E> <<SENT b'\\x04'>>"
PASS: _confirm_on_tty real pty answer 'EOF' -> raised=EOFError raised=EOFError
--- ctrlC_real: status=0 log=[('sent', b'\x03', 0.6)] out="PROMPT-E> <<SENT b'\\x03'>>^C"
PASS: _confirm_on_tty real pty answer 'ctrlC_real' -> raised=KeyboardInterrupt raised=KeyboardInterrupt
--- negative control (no flush): noflush-read=b'y\n' b'y\r\n'
PASS: NEG CONTROL: stale 'y\n' really IS queued on the tty (read without flush returns it) noflush-read=b'y\n'
--- stale then n: returned=False finished_before_fresh_answer= False b'y\r\nPROMPT-E> n\r\n'
PASS: stale 'y\n' typeahead did NOT approve: child still blocked 2s after prompt False
PASS: stale y then fresh 'n' -> returned=False returned=False
--- stale then y: returned=True finished_before_fresh_answer= False b'y\r\nPROMPT-E> y\r\n'
PASS: stale 'y\n' then fresh 'y' -> only fresh answer approves (blocked until then) (False, 'returned=True')
PASS: stale y then fresh EOF -> raised EOFError (stale not consumed as approval) (False, 'raised=EOFError')
--- no tty: b'' raised=OSError
PASS: no controlling tty (setsid, stdin=/dev/null): raises (never returns True) raised=OSError
SUMMARY 14 pass of 14 FAILS: []
```
### Adopt / rollback flows (e_flow_run1.log): 55 PASS
Real `import_lora_adapter`, `rollback_to_backup`, and the documented `rollback_adoption` one-liner (main.py:2393 text, exec'd verbatim) with the stub loader. Refusal paths (n, empty, EOF, ^C, no-tty, override+n, override+no-tty) each left: only `base.gguf` in the models dir, no merge marker, no `$HOME/models`, zero loader calls, one registry row adopted=False, one HIGH_IMPACT refused audit row with static labels. Gate-less default (no override) is refused by the promotion gate before any prompt. Approved merge path: backup existed when the fake merge ran (marker `merge-ran backup_exists=True`), `loader.unload` observed after backup and marker with cfg already on the merged file, then `load_primary`. `operator_override` alone never approves (ovr_n, ovr_notty); override plus a human `y` adopts and records is_operator_override=1. Rollback via one-liner: `n`, no-tty and EOF refuse and leave backup intact and rolled_back=0; `y` restores the corrupted base (`CORRUPTED-BASE` -> `BASE-MODEL-BYTES`), deletes the backup, marks rolled_back=1.
```
PASS: gp_n: prompt rendered on pty with HIGH IMPACT text + adapter path 
PASS: gp_n: zero backup/merge/swap side effects (['base.gguf'], None, False, ['start'])
PASS: gp_n: exactly one registry row, adopted=False [{'id': '1792299291232110728', 'adopted': False, 'rolled_back': False, 'is_operator_override': 0, 'gate_promote': 1, 'backup_path': None, 'model_path': None}]
PASS: gp_n: one HIGH_IMPACT refused audit row, static labels [{'ts': 1792299291.2301323, 'authority': 'HIGH_IMPACT', 'action': 'lora_import.adopt', 'command': 'lora adapter adoption', 'outcome': 'refused', 'reason': 'Human confirmation declined; command not attempted.'}]
PASS: gp_n: results report refusal (success False) {'success': False, 'adapter_path': '/data/data/com.termux/files/usr/tmp/g14bce/e/gp_n/adapter', 'model_variant': 'primary', 'adapter_info': {'path': '/data/data/com.termux/files/usr/tmp/g14bce/e/gp_n/adapter', 'size_mb': 4.291534423828125e-05, 'base_model': 'unknown', 'lora_r': 8, 'lora_alpha': 'unknown'}, 'error': 'Refused: no human confirmation on /dev/tty (declined, unavailable or no terminal); nothing was copied, merged or swapped'}
PASS: gp_empty: prompt rendered on pty with HIGH IMPACT text + adapter path 
PASS: gp_empty: zero backup/merge/swap side effects (['base.gguf'], None, False, ['start'])
PASS: gp_empty: exactly one registry row, adopted=False [{'id': '1792299291963169269', 'adopted': False, 'rolled_back': False, 'is_operator_override': 0, 'gate_promote': 1, 'backup_path': None, 'model_path': None}]
PASS: gp_empty: one HIGH_IMPACT refused audit row, static labels [{'ts': 1792299291.9626884, 'authority': 'HIGH_IMPACT', 'action': 'lora_import.adopt', 'command': 'lora adapter adoption', 'outcome': 'refused', 'reason': 'Human confirmation declined; command not attempted.'}]
PASS: gp_empty: results report refusal (success False) {'success': False, 'adapter_path': '/data/data/com.termux/files/usr/tmp/g14bce/e/gp_empty/adapter', 'model_variant': 'primary', 'adapter_info': {'path': '/data/data/com.termux/files/usr/tmp/g14bce/e/gp_empty/adapter', 'size_mb': 4.291534423828125e-05, 'base_model': 'unknown', 'lora_r': 8, 'lora_alpha': 'unknown'}, 'error': 'Refused: no human confirmation on /dev/tty (declined, unavailable or no terminal); nothing was copied, merged or swapped'}
PASS: gp_eof: prompt rendered on pty with HIGH IMPACT text + adapter path 
PASS: gp_eof: zero backup/merge/swap side effects (['base.gguf'], None, False, ['start'])
PASS: gp_eof: exactly one registry row, adopted=False [{'id': '1792299292620375831', 'adopted': False, 'rolled_back': False, 'is_operator_override': 0, 'gate_promote': 1, 'backup_path': None, 'model_path': None}]
PASS: gp_eof: one HIGH_IMPACT refused audit row, static labels [{'ts': 1792299292.6198661, 'authority': 'HIGH_IMPACT', 'action': 'lora_import.adopt', 'command': 'lora adapter adoption', 'outcome': 'refused', 'reason': 'Human confirmation unavailable or interrupted; command not attempted.'}]
PASS: gp_eof: results report refusal (success False) {'success': False, 'adapter_path': '/data/data/com.termux/files/usr/tmp/g14bce/e/gp_eof/adapter', 'model_variant': 'primary', 'adapter_info': {'path': '/data/data/com.termux/files/usr/tmp/g14bce/e/gp_eof/adapter', 'size_mb': 4.291534423828125e-05, 'base_model': 'unknown', 'lora_r': 8, 'lora_alpha': 'unknown'}, 'error': 'Refused: no human confirmation on /dev/tty (declined, unavailable or no terminal); nothing was copied, merged or swapped'}
PASS: gp_ctrlc: prompt rendered on pty with HIGH IMPACT text + adapter path 
PASS: gp_ctrlc: zero backup/merge/swap side effects (['base.gguf'], None, False, ['start'])
PASS: gp_ctrlc: exactly one registry row, adopted=False [{'id': '1792299293306259008', 'adopted': False, 'rolled_back': False, 'is_operator_override': 0, 'gate_promote': 1, 'backup_path': None, 'model_path': None}]
PASS: gp_ctrlc: one HIGH_IMPACT refused audit row, static labels [{'ts': 1792299293.304563, 'authority': 'HIGH_IMPACT', 'action': 'lora_import.adopt', 'command': 'lora adapter adoption', 'outcome': 'refused', 'reason': 'Human confirmation unavailable or interrupted; command not attempted.'}]
PASS: gp_ctrlc: results report refusal (success False) {'success': False, 'adapter_path': '/data/data/com.termux/files/usr/tmp/g14bce/e/gp_ctrlc/adapter', 'model_variant': 'primary', 'adapter_info': {'path': '/data/data/com.termux/files/usr/tmp/g14bce/e/gp_ctrlc/adapter', 'size_mb': 4.291534423828125e-05, 'base_model': 'unknown', 'lora_r': 8, 'lora_alpha': 'unknown'}, 'error': 'Refused: no human confirmation on /dev/tty (declined, unavailable or no terminal); nothing was copied, merged or swapped'}
PASS: gp_notty: no tty -> no prompt 
PASS: gp_notty: zero backup/merge/swap side effects (['base.gguf'], None, False, ['start'])
PASS: gp_notty: exactly one registry row, adopted=False [{'id': '1792299293745283383', 'adopted': False, 'rolled_back': False, 'is_operator_override': 0, 'gate_promote': 1, 'backup_path': None, 'model_path': None}]
PASS: gp_notty: one HIGH_IMPACT refused audit row, static labels [{'ts': 1792299293.7446792, 'authority': 'HIGH_IMPACT', 'action': 'lora_import.adopt', 'command': 'lora adapter adoption', 'outcome': 'refused', 'reason': 'Human confirmation unavailable due to callback failure; command not attempted.'}]
PASS: gp_notty: results report refusal (success False) {'success': False, 'adapter_path': '/data/data/com.termux/files/usr/tmp/g14bce/e/gp_notty/adapter', 'model_variant': 'primary', 'adapter_info': {'path': '/data/data/com.termux/files/usr/tmp/g14bce/e/gp_notty/adapter', 'size_mb': 4.291534423828125e-05, 'base_model': 'unknown', 'lora_r': 8, 'lora_alpha': 'unknown'}, 'error': 'Refused: no human confirmation on /dev/tty (declined, unavailable or no terminal); nothing was copied, merged or swapped'}
PASS: ovr_n: prompt states operator override True 
PASS: ovr_n: zero backup/merge/swap side effects (['base.gguf'], None, False, ['start'])
PASS: ovr_n: exactly one registry row, adopted=False [{'id': '1792299294562125101', 'adopted': False, 'rolled_back': False, 'is_operator_override': 1, 'gate_promote': 0, 'backup_path': None, 'model_path': None}]
PASS: ovr_n: one HIGH_IMPACT refused audit row, static labels [{'ts': 1792299294.5602338, 'authority': 'HIGH_IMPACT', 'action': 'lora_import.adopt', 'command': 'lora adapter adoption', 'outcome': 'refused', 'reason': 'Human confirmation declined; command not attempted.'}]
PASS: ovr_n: results report refusal (success False) {'success': False, 'adapter_path': '/data/data/com.termux/files/usr/tmp/g14bce/e/ovr_n/adapter', 'model_variant': 'primary', 'adapter_info': {'path': '/data/data/com.termux/files/usr/tmp/g14bce/e/ovr_n/adapter', 'size_mb': 4.291534423828125e-05, 'base_model': 'unknown', 'lora_r': 8, 'lora_alpha': 'unknown'}, 'error': 'Refused: no human confirmation on /dev/tty (declined, unavailable or no terminal); nothing was copied, merged or swapped'}
PASS: ovr_n: registry row is_operator_override=1 yet adopted=0 [{'id': '1792299294562125101', 'adopted': False, 'rolled_back': False, 'is_operator_override': 1, 'gate_promote': 0, 'backup_path': None, 'model_path': None}]
PASS: ovr_notty: zero backup/merge/swap side effects (['base.gguf'], None, False, ['start'])
PASS: ovr_notty: exactly one registry row, adopted=False [{'id': '1792299294990628799', 'adopted': False, 'rolled_back': False, 'is_operator_override': 1, 'gate_promote': 0, 'backup_path': None, 'model_path': None}]
PASS: ovr_notty: one HIGH_IMPACT refused audit row, static labels [{'ts': 1792299294.990128, 'authority': 'HIGH_IMPACT', 'action': 'lora_import.adopt', 'command': 'lora adapter adoption', 'outcome': 'refused', 'reason': 'Human confirmation unavailable due to callback failure; command not attempted.'}]
PASS: ovr_notty: results report refusal (success False) {'success': False, 'adapter_path': '/data/data/com.termux/files/usr/tmp/g14bce/e/ovr_notty/adapter', 'model_variant': 'primary', 'adapter_info': {'path': '/data/data/com.termux/files/usr/tmp/g14bce/e/ovr_notty/adapter', 'size_mb': 4.291534423828125e-05, 'base_model': 'unknown', 'lora_r': 8, 'lora_alpha': 'unknown'}, 'error': 'Refused: no human confirmation on /dev/tty (declined, unavailable or no terminal); nothing was copied, merged or swapped'}
PASS: nogate (default no_evaluator, no override): refused by promotion gate BEFORE any prompt ({'success': False, 'adapter_path': '/data/data/com.termux/files/usr/tmp/g14bce/e/nogate/adapter', 'model_variant': 'primary', 'error': 'Refused by promotion gate: no evaluator exists for this target; refusing to promote'}, [])
PASS: gp_y: results success True, registry_id set {'success': True, 'adapter_path': '/data/data/com.termux/files/usr/tmp/g14bce/e/gp_y/adapter', 'model_variant': 'primary', 'adapter_info': {'path': '/data/data/com.termux/files/usr/tmp/g14bce/e/gp_y/adapter', 'size_mb': 4.291534423828125e-05, 'base_model': 'unknown', 'lora_r': 8, 'lora_alpha': 'unknown'}, 'backup_path': '/data/data/com.termux/files/usr/tmp/g14bce/e/gp_y/models/base.backup.gguf', 'model_path': '/data/data/com.termux/files/usr/tmp/g14bce/e/gp_y/home/models/codey-finetuned/codeyOS-finetuned-primary.gguf', 'message': 'Swapped to fine-tuned model', 'registry_id': '1792299296022410309'}
PASS: gp_y: backup file created with base bytes ['base.backup.gguf', 'base.gguf']
PASS: gp_y: fake merge ran AFTER backup existed (marker records backup_exists=True) merge-ran backup_exists=True
PASS: gp_y: swap (loader.unload) observed AFTER backup and merge marker, cfg already pointing at merged file [{'op': 'loader.unload', 'backup_exists': True, 'merge_marker_exists': True, 'cfg_MODEL_PATH': '/data/data/com.termux/files/usr/tmp/g14bce/e/gp_y/home/models/codey-finetuned/codeyOS-finetuned-primary.gguf', 'cfg_is_base': False, 't': 1792299296.0215619}]
PASS: gp_y: load_primary called once after unload 
PASS: gp_y: merged file exists under disposable HOME/models only 
PASS: gp_y: one registry row adopted=1, backup_path recorded [{'id': '1792299296022410309', 'adopted': True, 'rolled_back': False, 'is_operator_override': 0, 'gate_promote': 1, 'backup_path': '/data/data/com.termux/files/usr/tmp/g14bce/e/gp_y/models/base.backup.gguf', 'model_path': '/data/data/com.termux/files/usr/tmp/g14bce/e/gp_y/home/models/codey-finetuned/codeyOS-finetuned-primary.gguf'}]
PASS: gp_y: one HIGH_IMPACT allowed audit row, static [{'ts': 1792299296.0281065, 'authority': 'HIGH_IMPACT', 'action': 'lora_import.adopt', 'command': 'lora adapter adoption', 'outcome': 'allowed', 'reason': 'command executed'}]
PASS: ovr_y_rb: override + human 'y' adopts (pre-merged path); registry is_operator_override=1 adopted=1 [{'id': '1792299296720966246', 'adopted': True, 'rolled_back': False, 'is_operator_override': 1, 'gate_promote': 0, 'backup_path': '/data/data/com.termux/files/usr/tmp/g14bce/e/ovr_y_rb/models/base.backup.gguf', 'model_path': '/data/data/com.termux/files/usr/tmp/g14bce/e/ovr_y_rb/adapter/tuned.gguf'}]
PASS: ovr_y_rb: swap onto tuned.gguf after backup [{'op': 'loader.unload', 'backup_exists': True, 'merge_marker_exists': False, 'cfg_MODEL_PATH': '/data/data/com.termux/files/usr/tmp/g14bce/e/ovr_y_rb/adapter/tuned.gguf', 'cfg_is_base': False, 't': 1792299296.7196593}]
PASS: rollback one-liner 'n': refused message, nothing changed [False, 'Rollback refused: no human confirmation on /dev/tty (declined, unavailable or no terminal); nothing was changed']
PASS: rollback 'n': registry rolled_back=0, no loader calls in rollback process 
PASS: rollback 'n': audit has HIGH_IMPACT refused lora_import.rollback row {'ts': 1792299297.5291114, 'authority': 'HIGH_IMPACT', 'action': 'lora_import.rollback', 'command': 'lora model rollback', 'outcome': 'refused', 'reason': 'Human confirmation declined; command not attempted.'}
PASS: rollback one-liner no-tty: refused, backup intact, rolled_back=0 
PASS: rollback one-liner EOF: refused, backup intact, rolled_back=0 
PASS: rollback one-liner 'y': ok, original restored (CORRUPTED-BASE -> BASE-MODEL-BYTES), backup deleted ([True, 'Rolled back successfully'], ['base.gguf'], 'BASE-MODEL-BYTES')
PASS: rollback 'y': registry rolled_back=1, loader unload+load called, cfg back to base [{'id': '1792299296720966246', 'adopted': True, 'rolled_back': True, 'is_operator_override': 1, 'gate_promote': 0, 'backup_path': '/data/data/com.termux/files/usr/tmp/g14bce/e/ovr_y_rb/models/base.backup.gguf', 'model_path': '/data/data/com.termux/files/usr/tmp/g14bce/e/ovr_y_rb/adapter/tuned.gguf'}]
PASS: rollback_to_backup direct 'n': refused, base stays CORRUPTED, backup intact 
PASS: rollback_to_backup direct 'y': restored, backup deleted 
SUMMARY 55 pass of 55 FAILS: []
```
Full per-case transcripts (prompt text, results dict, event log with timestamps, audit rows) are in e_flow_run1.log.
