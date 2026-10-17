# WP2.1 group 14d live verification: embed_server `_capture_embed_occupant` / `_kill_port_occupant` (2026-10-17)

Scope: disposable harness only. No model loaded, no real service touched, no source/tracking doc edited, no git mutation. Raw logs/scripts: `/data/data/com.termux/files/usr/tmp/g14d/` (run.sh, h.py, h2.py, run1.log, run2_corrected_case4.log, free_first.txt, free_last.txt, sha_before.txt, sha_after.txt, ps_after.txt, ps_after2.txt).

## free -h
First (before any run):
```
               total        used        free      shared  buff/cache   available
Mem:            10Gi       7.1Gi       523Mi        60Mi       3.6Gi       3.8Gi
Swap:           15Gi       4.0Gi        12Gi
```
Last (after all runs):
```
               total        used        free      shared  buff/cache   available
Mem:            10Gi       7.1Gi       502Mi        60Mi       3.6Gi       3.7Gi
Swap:           15Gi       3.9Gi        12Gi
```
`ps aux | grep -E "llama-server|embed" | grep -v grep` after: `ps aux` itself is broken in this Termux shell (printed `-G: error while loading shared libraries ...` twice, no process list; literal in ps_after.txt). Substitute `ps -A -o pid,args | grep -E "llama-server|embed" | grep -v grep` output:
```
  737 /data/data/com.termux/files/usr/bin/bash -c source /data/data/com.termux/files/home/.claude/shell-snapshots/snapshot-bash-1792238227505-dw0xgr.sh 2>/dev/null || true && shopt -u extglob 2>/dev/null || true && { \builtin unalias -- 'unsetenv'; \builtin unset -f -- 'unsetenv'; } >/dev/null 2>&1 || true && eval 'cd /data/data/com.termux/files/home/Codey-OS; cat > tests/test_embed_foreign_identity.py <<'"'"'EOF'"'"' """NEW-86/14d: synthetic proc root; every process/network/model effect forbidden.""" import os import signal import socket from types import SimpleNamespace  import pytest  from core import embed_server as es from core import loader_v2 as loader from core import process_identity as identity  PORT = 18999   @pytest.fixture def fake(tmp_path, monkeypatch):     def forbidden(*a, **k):         pytest.fail("real process/network effect forbidden")      for name in ("killpg", "getpgid"):         monkeypatch.setattr(os, name, forbidden)     monkeypatch.setattr(es.subprocess, "Popen", forbidden)     monkeypatch.setattr(es.subprocess, "run", forbidden)     monkeypatch.setattr(es.urllib.request, "urlopen", forbidden)     monkeypatch.setattr(socket, "socket", forbidden)     root = tmp_path / "proc"     boot = root / "sys/kernel/random/boot_id"     boot.parent.mkdir(parents=True)     boot.write_text("11111111-2222-3333-4444-555555555555")     pid = 32123     directory = root / str(pid)     directory.mkdir()     executable, model = tmp_path / "llama-server", tmp_path / "embed.gguf"     executable.touch()     model.touch()     (directory / "exe").symlink_to(executable)     (directory / "cwd").symlink_to(tmp_path)      def proc(*, start=100, uid=None, state="S"):         uid = os.getuid() if uid is None else uid         fields = [state, str(os.getpid())] + ["0"] * 17 + [str(start)]         (directory / "stat").write_text(f"{pid} (fixture ) cmd) " + " ".join(fields))         (directory / "status").write_text(f"Uid:\t{uid}\t{uid}\t{uid}\t{uid}\n")      def argv(values=None):         values = values or [str(executable), "-m", str(model), "--port", str(PORT), "--embedding"]         (directory / "cmdline").write_bytes(b"\0".join(os.fsencode(v) for v in values) + b"\0")      proc()     argv()     monkeypatch.setattr(es, "LLAMA_SERVER_BIN", executable)     monkeypatch.setattr(es.EmbedServer, "_PROC_ROOT", root)     actual_info = identity.process_info     monkeypatch.setattr(identity, "process_info", lambda candidate, *_: actual_info(candidate, root))     calls = []     monkeypatch.setattr(os, "kill", lambda candidate, requested: calls.append((candidate, requested)))     clock = [0.0]     monkeypatch.setattr(loader.time, "monotonic", lambda: clock[0])     monkeypatch.setattr(loader.time, "sleep", lambda d: clock.__setitem__(0, clock[0] + d))     monkeypatch.setattr(es.time, "sleep", lambda d: None)     srv = es.EmbedServer()     srv.model_path = model     srv.port = PORT     bound = [True]     srv._find_port_occupant_pid = lambda: pid     srv._port_is_bound = lambda: bound[0]     return SimpleNamespace(srv=srv, root=root, directory=directory, pid=pid, executable=executable,                            model=model, proc=proc, argv=argv, calls=calls, clock=clock, bound=bound)   def test_exact_identity_term_then_exit_clears_port(fake, monkeypatch):     def kill(pid, sig):         fake.calls.append((pid, sig))         fake.bound[0] = False         (fake.directory / "stat").unlink()         (fake.directory / "status").unlink()         (fake.directory / "exe").unlink()         (fake.directory / "cwd").unlink()         (fake.directory / "cmdline").unlink()         fake.directory.rmdir()     monkeypatch.setattr(os, "kill", kill)     assert fake.srv._kill_port_occupant() is True     assert fake.calls == [(fake.pid, signal.SIGTERM)]   def test_term_ignored_then_kill_after_revalidation(fake):     assert fake.srv._kill_port_occupant() is False  # port stays bound; truthful     assert [s for _, s in fake.calls] == [signal.SIGTERM, signal.SIGKILL]     assert {p for p, _ in fake.calls} == {fake.pid}   def test_replacement_after_term_never_gets_kill(fake, monkeypatch):     def kill(pid, sig):         fake.calls.append((pid, sig))         fake.proc(start=101)     monkeypatch.setattr(os, "kill", kill)     assert fake.srv._kill_port_occupant() is False     assert [s for _, s in fake.calls] == [signal.SIGTERM]   def test_replacement_between_capture_and_term_not_signalled(fake, monkeypatch):     real = fake.srv._capture_embed_occupant      def capture(pid):         result = real(pid)         fake.proc(start=101)         return result     fake.srv._capture_embed_occupant = capture     assert fake.srv._kill_port_occupant() is False     assert fake.calls == []   @pytest.mark.parametrize("bad", ["exe", "model", "port", "extra-model", "no-port", "uid", "zombie",                                  "no-stat", "malformed-port", "relative-wrong-model"]) def test_unrelated_or_unprovable_occupant_refused_zero_signals(fake, bad):     values = [str(fake.executable), "-m", str(fake.model), "--port", str(PORT)]     if bad == "exe":         (fake.directory / "exe").unlink()         (fake.directory / "exe").symlink_to(fake.model)     elif bad == "model":         values[2] = str(fake.executable)     elif bad == "port":         values[-1] = "8082"     elif bad == "extra-model":         values += ["--model=" + str(fake.model)]     elif bad == "no-port":         values = values[:3]     elif bad == "uid":         fake.proc(uid=os.getuid() + 1)     elif bad == "zombie":         fake.proc(state="Z")     elif bad == "no-stat":         (fake.directory / "stat").unlink()     elif bad == "malformed-port":         values[-1] = "+" + str(PORT)     elif bad == "relative-wrong-model":         values[2] = "other.gguf"     fake.argv(values)     assert fake.srv._kill_port_occupant() is False     assert fake.calls == []   def test_unknown_pid_refused(fake):     fake.srv._find_port_occupant_pid = lambda: None     assert fake.srv._kill_port_occupant() is False     assert fake.calls == []   def test_portscan_pid_changes_between_lookups_refused(fake):     seq = iter([fake.pid, 99999])     fake.srv._find_port_occupant_pid = lambda: next(seq)     assert fake.srv._kill_port_occupant() is False     assert fake.calls == []   def test_refused_occupant_that_vanishes_reports_port_free(fake):     fake.argv([str(fake.executable), "-m", "/nope", "--port", str(PORT)])     fake.bound[0] = False     assert fake.srv._kill_port_occupant() is True     assert fake.calls == [] EOF export HOME=/data/data/com.termux/files/usr/tmp/h14d CODEY_STATE_DIR=/data/data/com.termux/files/usr/tmp/s14d; mkdir -p $HOME $CODEY_STATE_DIR; unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy ALL_PROXY all_proxy python3 -m pytest -q tests/test_embed_foreign_identity.py tests/test_new83_embed_server_kill.py tests/test_new86_embed_server_pid_recycle.py tests/test_embed_owned_lifecycle.py tests/test_foreign_primary_identity.py 2>&1 | tail -40' && pwd -P >| /data/data/com.termux/files/usr/tmp/claude-4d84-cwd
  740 python3 -m pytest -q tests/test_embed_foreign_identity.py tests/test_new83_embed_server_kill.py tests/test_new86_embed_server_pid_recycle.py tests/test_embed_owned_lifecycle.py tests/test_foreign_primary_identity.py
grep-exit=0
```
## sha256 before == after (diff printed nothing, SHA_UNCHANGED)
```
536bbedcf4d3ed33e060af8542dd79eb1e72837a29a0dee2a23a588bde94d54f  /data/data/com.termux/files/home/Codey-OS/core/embed_server.py
cd006f1d50dcb6c902c083d177a443200a0c22f63b40809ea8b86693e40e1567  /data/data/com.termux/files/home/Codey-OS/core/loader_v2.py
d20d200e7e74b4d41f5ea5ec0c1761bc6ddb37d8b0bd2b8015fd69fcc605c838  /data/data/com.termux/files/home/Codey-OS/tests/test_embed_foreign_identity.py
```
embed_server.py matches expected 536bbedc..d54f.

## Real vs faked
Real: C stub `llama-server` (ELF, sleep loop; optionally binds a real loopback listener on an ephemeral free port taken from env STUB_BIND, optionally ignores TERM, optionally exits itself when a file appears) compiled per run; real `/proc` reads (exe, cmdline, cwd, stat, boot_id) through the real `_capture_embed_occupant` and `loader_v2._kill_single_pid_term_then_kill`; real `os.kill` TERM/KILL to harness-retained Popen handles; real `_port_is_bound` TCP connect; real 2s post-kill sleep. `core.loader_v2.LLAMA_SERVER_BIN` and `core.embed_server.LLAMA_SERVER_BIN` monkeypatched to the stub; EmbedServer `.model_path`/`.port` set to disposable values.
Faked: `_find_port_occupant_pid` is monkeypatched to return the child pid (the real one returned None for a real listener: `/proc/net/tcp` is Permission denied on this device, and no slot is registered). In case 4 "occupant changed between lookups" the second lookup returns a made-up pid. Case 4 identity replacement is simulated by editing the captured dict (start_ticks +/-1, boot_id) after the real capture, not a real PID recycle. Case 5 vanish: wrapper makes the child exit by itself (touch exit file, harness `wait()`s, no signal) after the real capture refused.
Guards: `os.kill` raises for any nonzero signal to a pid not in the retained set (never fired); `os.killpg`, `os.getpgid`, `os.system` raise; Popen of pkill/killall/kill/pgrep raises (none fired). Signals are logged separately for "code" vs harness "cleanup" (cleanup SIGKILLs to leftover refused children after assertions, by retained handle).
Env: proxy vars unset (only `CLAUDE_CODE_PROXY_RESOLVES_HOSTS` is present, not a proxy), HOME/CODEY_STATE_DIR under the Termux tmp, `python -I` from the run dir with sys.path set explicitly.

## Results
- Case 1 (exact exe/model/port): PASS. capture succeeded; `_kill_port_occupant` True, signals exactly `[(27575, 15)]`, child rc -15 reaped by harness, port free. 1b relative `-m embed.gguf` resolving via /proc/pid/cwd to the embed model: captured, True, one TERM.
- Case 2 (TERM ignored): PASS. signals `[(27602, 15), (27602, 9)]`, returned True in 7.21s, rc -9, port free.
- Case 3 (wrong exe, wrong model, wrong argv port, duplicate --port, duplicate -m, missing --port, relative model not resolving): PASS all. Each: zero code signals, child still alive, returned False (listener still bound), 0.00-0.01s.
- Case 4 replacement: FIRST RUN FAILED (6 FAIL, harness mistake, kept below): my harness called `run_case` (an unpatched server, whose capture is real and legitimate) before the mutated-capture call, so the real code correctly TERMed the child (`code signals [(27665, 15)]`), and the second, mutated call then hit a dead child. Zero-signal/alive/False assertions were therefore invalid. Corrected resumed run (`run2_corrected_case4.log`, cases 4 and 5 and guards only): PASS 15/15. start_ticks+1, start_ticks-1, boot_id edited each: `exit not confirmed (unsafe, PID replaced)`, zero signals, child alive, returns False. Occupant-changed-between-lookups (faked lookup): zero signals, alive, False.
- Case 5 (refused occupant exits on its own): PASS, returns True, zero signals (both runs).
- Case 6: PASS, no banned call fired; all signals only to retained pids.
- Not exercised: a real PID recycle, a real /proc/net/tcp port lookup (denied on device), PermissionError on kill, other-UID occupants.
- Run 1 totals: 55 PASS / 61, 6 FAIL (all case 4, harness mistake above). Corrected run: 15 PASS / 15. No result contradicted the implementer/reviewer expectations. Observed behavior note (not a defect): refused occupants leave `_kill_port_occupant` logging two errors (refusal, then "still occupied") before returning False.

## Verbatim log: run 1 (initial, includes the case 4 failures)
```
== environment ==
uid 10247 PORT 38527 HOME /data/data/com.termux/files/usr/tmp/g14d/R_1/home CODEY_STATE_DIR /data/data/com.termux/files/usr/tmp/g14d/R_1/state
es.LLAMA_SERVER_BIN /data/data/com.termux/files/usr/tmp/g14d/R_1/bin/llama-server lv.LLAMA_SERVER_BIN /data/data/com.termux/files/usr/tmp/g14d/R_1/bin/llama-server
proxy vars: {'CLAUDE_CODE_PROXY_RESOLVES_HOSTS': 'true'}
real _find_port_occupant_pid (unpatched) with real listener by pid 27574 -> None (/proc/net/tcp is permission-denied here; port lookup is monkeypatched in cases)
PASS 0 real _port_is_bound sees stub listener 
PASS 0b port free after harness cleanup 

== case 1: exact match -> TERM, exit ==
  capture: {'pid': 27575, 'boot_id': 'f3023781-05a2-44b7-a7ec-43f30d1d8422', 'start_ticks': 105719343, 'uid': 10247, 'parent_pid': 27573, 'state': 'S'}
PASS 1 capture succeeds 
  [1] child pid 27575 cmdline: b'/data/data/com.termux/files/usr/tmp/g14d/R_1/bin/llama-server -m /data/data/com.termux/files/usr/tmp/g14d/R_1/embed.gguf --port 38527 -c 2048 ' exe -> /data/data/com.termux/files/usr/tmp/g14d/R_1/bin/llama-server cwd -> /data/data/com.termux/files/usr/tmp/g14d/R_1
ℹ  Stopping stale embed server PID 27575 occupying port 38527
  [1] returned True elapsed 2.21s code signals [(27575, 15)] child state State:	Z (zombie) poll -15
PASS 1 returned True 
PASS 1 exactly one SIGTERM to retained child [(27575, 15)]
PASS 1 child rc -15 (reaped by harness) -15
PASS 1 port free 

== case 1b: relative -m resolving (via /proc cwd) to embed model -> captured ==
  capture: {'pid': 27593, 'boot_id': 'f3023781-05a2-44b7-a7ec-43f30d1d8422', 'start_ticks': 105719570, 'uid': 10247, 'parent_pid': 27573, 'state': 'S'}
PASS 1b relative model resolving to embed model captured 
  [1b] child pid 27593 cmdline: b'/data/data/com.termux/files/usr/tmp/g14d/R_1/bin/llama-server -m embed.gguf --port 38527 ' exe -> /data/data/com.termux/files/usr/tmp/g14d/R_1/bin/llama-server cwd -> /data/data/com.termux/files/usr/tmp/g14d/R_1
ℹ  Stopping stale embed server PID 27593 occupying port 38527
  [1b] returned True elapsed 2.21s code signals [(27593, 15)] child state State:	Z (zombie) poll -15
PASS 1b True + one TERM True [(27593, 15)]

== case 2: child ignores TERM -> KILL after revalidation ==
  [2] child pid 27602 cmdline: b'/data/data/com.termux/files/usr/tmp/g14d/R_1/bin/llama-server -m /data/data/com.termux/files/usr/tmp/g14d/R_1/embed.gguf --port 38527 -c 2048 ' exe -> /data/data/com.termux/files/usr/tmp/g14d/R_1/bin/llama-server cwd -> /data/data/com.termux/files/usr/tmp/g14d/R_1
ℹ  Stopping stale embed server PID 27602 occupying port 38527
  [2] returned True elapsed 7.21s code signals [(27602, 15), (27602, 9)] child state State:	Z (zombie) poll -9
PASS 2 returned True 
PASS 2 signals exactly TERM then KILL [(27602, 15), (27602, 9)]
PASS 2 child rc -9 -9
PASS 2 port free 

== case 3: refusals (zero signals, alive, False since port bound) ==
PASS 3 precondition port bound (wrong exe (same name, other path)) 
  [3 wrong exe (same name, other path)] child pid 27657 cmdline: b'/data/data/com.termux/files/usr/tmp/g14d/R_1/other/llama-server -m /data/data/com.termux/files/usr/tmp/g14d/R_1/embed.gguf --port 38527 -c 2048 ' exe -> /data/data/com.termux/files/usr/tmp/g14d/R_1/other/llama-server cwd -> /data/data/com.termux/files/usr/tmp/g14d/R_1
✗  embed_server: occupant of port 38527 could not be proven to be the embed 
server (identity or port ownership changed or unprovable) — refusing to signal 
anything. Free the port manually and retry.
✗  embed_server: port 38527 is still occupied after attempting to clear PID 
27657 — a child process may hold the listening socket, or the kill was aborted 
(see above). Not escalating to a broader kill; free the port manually and retry.
  [3 wrong exe (same name, other path)] returned False elapsed 0.01s code signals [] child state State:	S (sleeping) poll None
PASS 3 refused: zero signals (wrong exe (same name, other path)) []
PASS 3 refused: child alive (wrong exe (same name, other path)) 
PASS 3 refused: returned False (wrong exe (same name, other path)) False
PASS 3 cleanup port free (wrong exe (same name, other path)) 
PASS 3 precondition port bound (wrong model) 
  [3 wrong model] child pid 27659 cmdline: b'/data/data/com.termux/files/usr/tmp/g14d/R_1/bin/llama-server -m /data/data/com.termux/files/usr/tmp/g14d/R_1/model2.gguf --port 38527 -c 2048 ' exe -> /data/data/com.termux/files/usr/tmp/g14d/R_1/bin/llama-server cwd -> /data/data/com.termux/files/usr/tmp/g14d/R_1
✗  embed_server: occupant of port 38527 could not be proven to be the embed 
server (identity or port ownership changed or unprovable) — refusing to signal 
anything. Free the port manually and retry.
✗  embed_server: port 38527 is still occupied after attempting to clear PID 
27659 — a child process may hold the listening socket, or the kill was aborted 
(see above). Not escalating to a broader kill; free the port manually and retry.
  [3 wrong model] returned False elapsed 0.01s code signals [] child state State:	S (sleeping) poll None
PASS 3 refused: zero signals (wrong model) []
PASS 3 refused: child alive (wrong model) 
PASS 3 refused: returned False (wrong model) False
PASS 3 cleanup port free (wrong model) 
PASS 3 precondition port bound (wrong port (argv port != embed port; socket bound on embed port)) 
  [3 wrong port (argv port != embed port; socket bound on embed port)] child pid 27660 cmdline: b'/data/data/com.termux/files/usr/tmp/g14d/R_1/bin/llama-server -m /data/data/com.termux/files/usr/tmp/g14d/R_1/embed.gguf --port 38528 -c 2048 ' exe -> /data/data/com.termux/files/usr/tmp/g14d/R_1/bin/llama-server cwd -> /data/data/com.termux/files/usr/tmp/g14d/R_1
✗  embed_server: occupant of port 38527 could not be proven to be the embed 
server (identity or port ownership changed or unprovable) — refusing to signal 
anything. Free the port manually and retry.
✗  embed_server: port 38527 is still occupied after attempting to clear PID 
27660 — a child process may hold the listening socket, or the kill was aborted 
(see above). Not escalating to a broader kill; free the port manually and retry.
  [3 wrong port (argv port != embed port; socket bound on embed port)] returned False elapsed 0.01s code signals [] child state State:	S (sleeping) poll None
PASS 3 refused: zero signals (wrong port (argv port != embed port; socket bound on embed port)) []
PASS 3 refused: child alive (wrong port (argv port != embed port; socket bound on embed port)) 
PASS 3 refused: returned False (wrong port (argv port != embed port; socket bound on embed port)) False
PASS 3 cleanup port free (wrong port (argv port != embed port; socket bound on embed port)) 
PASS 3 precondition port bound (duplicate --port) 
  [3 duplicate --port] child pid 27661 cmdline: b'/data/data/com.termux/files/usr/tmp/g14d/R_1/bin/llama-server -m /data/data/com.termux/files/usr/tmp/g14d/R_1/embed.gguf --port 38527 --port 38527 ' exe -> /data/data/com.termux/files/usr/tmp/g14d/R_1/bin/llama-server cwd -> /data/data/com.termux/files/usr/tmp/g14d/R_1
✗  embed_server: occupant of port 38527 could not be proven to be the embed 
server (identity or port ownership changed or unprovable) — refusing to signal 
anything. Free the port manually and retry.
✗  embed_server: port 38527 is still occupied after attempting to clear PID 
27661 — a child process may hold the listening socket, or the kill was aborted 
(see above). Not escalating to a broader kill; free the port manually and retry.
  [3 duplicate --port] returned False elapsed 0.00s code signals [] child state State:	S (sleeping) poll None
PASS 3 refused: zero signals (duplicate --port) []
PASS 3 refused: child alive (duplicate --port) 
PASS 3 refused: returned False (duplicate --port) False
PASS 3 cleanup port free (duplicate --port) 
PASS 3 precondition port bound (duplicate -m) 
  [3 duplicate -m] child pid 27662 cmdline: b'/data/data/com.termux/files/usr/tmp/g14d/R_1/bin/llama-server -m /data/data/com.termux/files/usr/tmp/g14d/R_1/embed.gguf -m /data/data/com.termux/files/usr/tmp/g14d/R_1/embed.gguf --port 38527 ' exe -> /data/data/com.termux/files/usr/tmp/g14d/R_1/bin/llama-server cwd -> /data/data/com.termux/files/usr/tmp/g14d/R_1
✗  embed_server: occupant of port 38527 could not be proven to be the embed 
server (identity or port ownership changed or unprovable) — refusing to signal 
anything. Free the port manually and retry.
✗  embed_server: port 38527 is still occupied after attempting to clear PID 
27662 — a child process may hold the listening socket, or the kill was aborted 
(see above). Not escalating to a broader kill; free the port manually and retry.
  [3 duplicate -m] returned False elapsed 0.01s code signals [] child state State:	S (sleeping) poll None
PASS 3 refused: zero signals (duplicate -m) []
PASS 3 refused: child alive (duplicate -m) 
PASS 3 refused: returned False (duplicate -m) False
PASS 3 cleanup port free (duplicate -m) 
PASS 3 precondition port bound (missing --port (legacy argv)) 
  [3 missing --port (legacy argv)] child pid 27663 cmdline: b'/data/data/com.termux/files/usr/tmp/g14d/R_1/bin/llama-server -m /data/data/com.termux/files/usr/tmp/g14d/R_1/embed.gguf ' exe -> /data/data/com.termux/files/usr/tmp/g14d/R_1/bin/llama-server cwd -> /data/data/com.termux/files/usr/tmp/g14d/R_1
✗  embed_server: occupant of port 38527 could not be proven to be the embed 
server (identity or port ownership changed or unprovable) — refusing to signal 
anything. Free the port manually and retry.
✗  embed_server: port 38527 is still occupied after attempting to clear PID 
27663 — a child process may hold the listening socket, or the kill was aborted 
(see above). Not escalating to a broader kill; free the port manually and retry.
  [3 missing --port (legacy argv)] returned False elapsed 0.01s code signals [] child state State:	S (sleeping) poll None
PASS 3 refused: zero signals (missing --port (legacy argv)) []
PASS 3 refused: child alive (missing --port (legacy argv)) 
PASS 3 refused: returned False (missing --port (legacy argv)) False
PASS 3 cleanup port free (missing --port (legacy argv)) 
PASS 3 precondition port bound (relative model not resolving to embed model) 
  [3 relative model not resolving to embed model] child pid 27664 cmdline: b'/data/data/com.termux/files/usr/tmp/g14d/R_1/bin/llama-server -m embed.gguf --port 38527 ' exe -> /data/data/com.termux/files/usr/tmp/g14d/R_1/bin/llama-server cwd -> /data/data/com.termux/files/usr/tmp/g14d/R_1/cwdA
✗  embed_server: occupant of port 38527 could not be proven to be the embed 
server (identity or port ownership changed or unprovable) — refusing to signal 
anything. Free the port manually and retry.
✗  embed_server: port 38527 is still occupied after attempting to clear PID 
27664 — a child process may hold the listening socket, or the kill was aborted 
(see above). Not escalating to a broader kill; free the port manually and retry.
  [3 relative model not resolving to embed model] returned False elapsed 0.01s code signals [] child state State:	S (sleeping) poll None
PASS 3 refused: zero signals (relative model not resolving to embed model) []
PASS 3 refused: child alive (relative model not resolving to embed model) 
PASS 3 refused: returned False (relative model not resolving to embed model) False
PASS 3 cleanup port free (relative model not resolving to embed model) 

== case 4: replacement generation ==
  [4 start_ticks+1] child pid 27665 cmdline: b'/data/data/com.termux/files/usr/tmp/g14d/R_1/bin/llama-server -m /data/data/com.termux/files/usr/tmp/g14d/R_1/embed.gguf --port 38527 -c 2048 ' exe -> /data/data/com.termux/files/usr/tmp/g14d/R_1/bin/llama-server cwd -> /data/data/com.termux/files/usr/tmp/g14d/R_1
ℹ  Stopping stale embed server PID 27665 occupying port 38527
  [4 start_ticks+1] returned True elapsed 2.21s code signals [(27665, 15)] child state State:	Z (zombie) poll -15
✗  embed_server: occupant of port 38527 could not be proven to be the embed 
server (identity or port ownership changed or unprovable) — refusing to signal 
anything. Free the port manually and retry.
  [4 start_ticks+1] returned True code signals [] state gone
PASS 4 start_ticks+1: zero signals []
FAIL 4 start_ticks+1: child alive 
FAIL 4 start_ticks+1: False 
  [4 start_ticks-1] child pid 27678 cmdline: b'/data/data/com.termux/files/usr/tmp/g14d/R_1/bin/llama-server -m /data/data/com.termux/files/usr/tmp/g14d/R_1/embed.gguf --port 38527 -c 2048 ' exe -> /data/data/com.termux/files/usr/tmp/g14d/R_1/bin/llama-server cwd -> /data/data/com.termux/files/usr/tmp/g14d/R_1
ℹ  Stopping stale embed server PID 27678 occupying port 38527
  [4 start_ticks-1] returned True elapsed 2.21s code signals [(27678, 15)] child state State:	Z (zombie) poll -15
✗  embed_server: occupant of port 38527 could not be proven to be the embed 
server (identity or port ownership changed or unprovable) — refusing to signal 
anything. Free the port manually and retry.
  [4 start_ticks-1] returned True code signals [] state gone
PASS 4 start_ticks-1: zero signals []
FAIL 4 start_ticks-1: child alive 
FAIL 4 start_ticks-1: False 
  [4 boot_id edited] child pid 27685 cmdline: b'/data/data/com.termux/files/usr/tmp/g14d/R_1/bin/llama-server -m /data/data/com.termux/files/usr/tmp/g14d/R_1/embed.gguf --port 38527 -c 2048 ' exe -> /data/data/com.termux/files/usr/tmp/g14d/R_1/bin/llama-server cwd -> /data/data/com.termux/files/usr/tmp/g14d/R_1
ℹ  Stopping stale embed server PID 27685 occupying port 38527
  [4 boot_id edited] returned True elapsed 2.21s code signals [(27685, 15)] child state State:	Z (zombie) poll -15
✗  embed_server: occupant of port 38527 could not be proven to be the embed 
server (identity or port ownership changed or unprovable) — refusing to signal 
anything. Free the port manually and retry.
  [4 boot_id edited] returned True code signals [] state gone
PASS 4 boot_id edited: zero signals []
FAIL 4 boot_id edited: child alive 
FAIL 4 boot_id edited: False 
✗  embed_server: occupant of port 38527 could not be proven to be the embed 
server (identity or port ownership changed or unprovable) — refusing to signal 
anything. Free the port manually and retry.
✗  embed_server: port 38527 is still occupied after attempting to clear PID 
27695 — a child process may hold the listening socket, or the kill was aborted 
(see above). Not escalating to a broader kill; free the port manually and retry.
  [4 occupant changed between lookups (lookup faked)] returned False signals [] state State:	S (sleeping)
PASS 4 occupant changed between lookups: zero signals, alive, False 

== case 5: refused occupant vanishes on its own ==
  [5] capture -> None ; telling child to exit by itself (no signal)
  [5] child exited on its own rc 0
✗  embed_server: occupant of port 38527 could not be proven to be the embed 
server (identity or port ownership changed or unprovable) — refusing to signal 
anything. Free the port manually and retry.
  [5] returned True signals []
PASS 5 returns True with zero signals True []

== case 6: guards ==
PASS 6 no killpg/getpgid/pkill/os.system invoked (guards would have raised AssertionError) 
PASS 6 all signals only to retained pids (guard never fired) 
code signals total: [(27575, 15), (27593, 15), (27602, 15), (27602, 9), (27665, 15), (27678, 15), (27685, 15)]
cleanup signals total: [(27574, 9), (27657, 9), (27659, 9), (27660, 9), (27661, 9), (27662, 9), (27663, 9), (27664, 9), (27695, 9)]

SUMMARY 55 PASS / 61 total, 6 FAIL
FAILED: 4 start_ticks+1: child alive
FAILED: 4 start_ticks+1: False
FAILED: 4 start_ticks-1: child alive
FAILED: 4 start_ticks-1: False
FAILED: 4 boot_id edited: child alive
FAILED: 4 boot_id edited: False
exit=0
```

## Verbatim log: run 2 (corrected case 4, plus 5 and 6)
```
== environment ==
uid 10247 PORT 35565 HOME /data/data/com.termux/files/usr/tmp/g14d/R_2/home CODEY_STATE_DIR /data/data/com.termux/files/usr/tmp/g14d/R_2/state
es.LLAMA_SERVER_BIN /data/data/com.termux/files/usr/tmp/g14d/R_2/bin/llama-server lv.LLAMA_SERVER_BIN /data/data/com.termux/files/usr/tmp/g14d/R_2/bin/llama-server
proxy vars: {'CLAUDE_CODE_PROXY_RESOLVES_HOSTS': 'true'}
real _find_port_occupant_pid (unpatched) with real listener by pid 27842 -> None (/proc/net/tcp is permission-denied here; port lookup is monkeypatched in cases)
PASS 0 real _port_is_bound sees stub listener 
PASS 0b port free after harness cleanup 

== case 4: replacement generation ==
  [4 start_ticks+1] child pid 27844 start_ticks real 105722264 mutated 105722265 boot f3023781-05a2-44b7-a7ec-43f30d1d8422
ℹ  Stopping stale embed server PID 27844 occupying port 35565
✗  embed_server: stale embed server PID 27844 exit not confirmed (unsafe, PID 
replaced) — port 35565 not cleared; no further signals sent.
  [4 start_ticks+1] returned False code signals [] state State:	S (sleeping)
PASS 4 start_ticks+1: zero signals []
PASS 4 start_ticks+1: child alive 
PASS 4 start_ticks+1: False 
  [4 start_ticks+1] real /proc start_ticks still 105722264
  [4 start_ticks-1] child pid 27845 start_ticks real 105722271 mutated 105722270 boot f3023781-05a2-44b7-a7ec-43f30d1d8422
ℹ  Stopping stale embed server PID 27845 occupying port 35565
✗  embed_server: stale embed server PID 27845 exit not confirmed (unsafe, PID 
replaced) — port 35565 not cleared; no further signals sent.
  [4 start_ticks-1] returned False code signals [] state State:	S (sleeping)
PASS 4 start_ticks-1: zero signals []
PASS 4 start_ticks-1: child alive 
PASS 4 start_ticks-1: False 
  [4 start_ticks-1] real /proc start_ticks still 105722271
  [4 boot_id edited] child pid 27847 start_ticks real 105722278 mutated 105722278 boot 00000000-0000-0000-0000-000000000000
ℹ  Stopping stale embed server PID 27847 occupying port 35565
✗  embed_server: stale embed server PID 27847 exit not confirmed (unsafe, PID 
replaced) — port 35565 not cleared; no further signals sent.
  [4 boot_id edited] returned False code signals [] state State:	S (sleeping)
PASS 4 boot_id edited: zero signals []
PASS 4 boot_id edited: child alive 
PASS 4 boot_id edited: False 
  [4 boot_id edited] real /proc start_ticks still 105722278
✗  embed_server: occupant of port 35565 could not be proven to be the embed 
server (identity or port ownership changed or unprovable) — refusing to signal 
anything. Free the port manually and retry.
✗  embed_server: port 35565 is still occupied after attempting to clear PID 
27849 — a child process may hold the listening socket, or the kill was aborted 
(see above). Not escalating to a broader kill; free the port manually and retry.
  [4 occupant changed between lookups (lookup faked)] returned False signals [] state State:	S (sleeping)
PASS 4 occupant changed between lookups: zero signals, alive, False 

== case 5: refused occupant vanishes on its own ==
  [5] capture -> None ; telling child to exit by itself (no signal)
  [5] child exited on its own rc 0
✗  embed_server: occupant of port 35565 could not be proven to be the embed 
server (identity or port ownership changed or unprovable) — refusing to signal 
anything. Free the port manually and retry.
  [5] returned True signals []
PASS 5 returns True with zero signals True []

== case 6: guards ==
PASS 6 no killpg/getpgid/pkill/os.system invoked (guards would have raised AssertionError) 
PASS 6 all signals only to retained pids (guard never fired) 
code signals total: []
cleanup signals total: [(27842, 9), (27844, 9), (27845, 9), (27847, 9), (27849, 9)]

SUMMARY 15 PASS / 15 total, 0 FAIL
exit=0
```

## Addendum: ps match explanation
The two `ps -A -o pid,args` matches (pids 737, 740) are not harness children and not llama-server: they are the coordinator's own concurrent bash/pytest command whose argument text contains "embed" (tests/test_embed_foreign_identity.py ...). No `llama-server` process and no harness stub remained. I did not touch them.
