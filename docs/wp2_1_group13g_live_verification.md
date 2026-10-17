# WP2.1 13g fixed public client disposable verification

2026-10-16. Independent result: PASS. Approved5 hashes checked before/after.

Actual public codeyOS and fixed cli_client copies ran from a repository path containing quotes/newlines/metacharacters with actual unchanged daemon_config/process_identity modules and real temporary UDS. Temporary HOME/state/config/audit preceded child imports; a guarded import hook rejected real main/daemon/inference/model imports on RPC branches. Status/task/list/cancel/background JSON payloads and literal code-shaped prompts were captured by the actual socket server. Invalid IDs and unsafe/absent identities caused no requests; actual server error/empty/invalid responses and one real5-second status timeout returned nonzero. No generated state Python appeared.

Foreground branch imported only a fixed fake main. Actual subprocess outcomes matched direct fake-main baselines for normal/return7/SystemExit7/KeyboardInterrupt/-SIGTERM, preserving argv and input/output/error streams. Signals targeted only fixture process self-PIDs, never record/protocol numbers. Every public/baseline Popen was waited; ordinary identity-owner Popen was retained/finally reaped, UDS thread/socket closed. Raw output fsynced continuously to /data/data/com.termux/files/usr/tmp/wp21_13g_live_raw.log.

Limits: daemon response content and foreground main were intentional fixtures, not real application/task/model execution. Identity/config/UDS transport and shell/client were real. This verifies transport and exit fidelity, not daemon action authority or13d audit. Concurrent13f/embed/inference/core-daemon/NEW967 changes are outside this five-file claim. No real daemon/default plugins/services/cloud/network/live stores/credentials were used.

Literal output:

```text
$ free -h (before)
               total        used        free      shared  buff/cache   available
Mem:            10Gi       7.2Gi       743Mi        65Mi       3.0Gi       3.6Gi
Swap:           15Gi       5.7Gi        10Gi
Approved five source/test SHA256 matched: {"codeyOS": "8d386447d53877429b7a68d41f6bee88f9d06e6ec34557642ff96679910784a8", "core/cli_client.py": "e0c076c270d7e13e5da352c15250ed309821b51995853354139455b05c95c938", "tests/test_cli_client.py": "644977ee951da8ea49e25ff97a9848e28ea81b446a16669450b77bf4c152903e", "tests/test_cli_client_dispatcher.py": "048c5839206991bbe892945b3a3e0d15a57248174df934671439a64827366dd9", "tests/test_service_public_lifecycle.py": "8073787e9e92fa74c3330c9dc5de93b4aa76f0c6abf32e5e5c289e6a347e462e"}
Actual configured paths= {'pid_file': '/data/data/com.termux/files/usr/tmp/g13-odf2724y/state "\n; literal/pid "\n; data', 'socket_file': '/data/data/com.termux/files/usr/tmp/g13-odf2724y/socket "\n; data', 'log_file': '/data/data/com.termux/files/usr/tmp/g13-odf2724y/state "\n; literal/log `literal`'} socket_bytes= 64
PUBLIC ARGV= ['status'] OSrc= 0 stdout= 'Codey-OS Daemon Status\n========================================\nPID:            16816\nStatus:         Running\nUptime:         0 seconds\nMemory:         0 MB\n\nTask Queue:\n  Pending:      2\n  Stuck:        None\n\nRecent Actions: 0 logged\n\nState Database: /data/data/com.termux/files/usr/tmp/g13-odf2724y/state "\n; literal/custom db\n' stderr= ''
ACTUAL JSON= {"cmd": "health", "data": {}}
PUBLIC ARGV= ['task', 'list'] OSrc= 0 stdout= 'Tasks:\n  [3] ✓ literal task\n' stderr= ''
ACTUAL JSON= {"cmd": "task", "data": {"limit": 20}}
PUBLIC ARGV= ['task', '003'] OSrc= 0 stdout= 'Task 3: literal task\nStatus: ✓ done\nResult: fixture output\n' stderr= ''
ACTUAL JSON= {"cmd": "task", "data": {"id": 3}}
PUBLIC ARGV= ['cancel', '3'] OSrc= 0 stdout= 'fixture cancelled\n' stderr= ''
ACTUAL JSON= {"cmd": "cancel", "data": {"id": 3}}
PUBLIC ARGV= ['--bg', '--yolo', '"""; __import__("pathlib").Path("owned").touch(); #\n$() `x` \'literal\'', 'a b', ''] OSrc= 0 stdout= '{\n  "status": "ok",\n  "message": "literal queued"\n}\n' stderr= ''
ACTUAL literal background JSON= {"cmd": "command", "data": {"prompt": "\"\"\"; __import__(\"pathlib\").Path(\"owned\").touch(); #\n$() `x` 'literal' a b ", "yolo": true}}
PUBLIC ARGV= ['--background', '--yolo', '"""; __import__("pathlib").Path("owned").touch(); #\n$() `x` \'literal\'', 'a b', ''] OSrc= 0 stdout= '{\n  "status": "ok",\n  "message": "literal queued"\n}\n' stderr= ''
ACTUAL literal background JSON= {"cmd": "command", "data": {"prompt": "\"\"\"; __import__(\"pathlib\").Path(\"owned\").touch(); #\n$() `x` 'literal' a b ", "yolo": true}}
PUBLIC ARGV= ['task', '0'] OSrc= 1 stdout= '' stderr= '[ERROR] Task ID must be a positive decimal integer\n'
PUBLIC ARGV= ['task', '1+1'] OSrc= 1 stdout= '' stderr= '[ERROR] Task ID must be a positive decimal integer\n'
PUBLIC ARGV= ['cancel', '1\n'] OSrc= 1 stdout= '' stderr= '[ERROR] Task ID must be a positive decimal integer\n'
PUBLIC ARGV= ['cancel', '١'] OSrc= 1 stdout= '' stderr= '[ERROR] Task ID must be a positive decimal integer\n'
PUBLIC ARGV= ['cancel', '1};__import__("os").system("x");#'] OSrc= 1 stdout= '' stderr= '[ERROR] Task ID must be a positive decimal integer\n'
PUBLIC ARGV= ['--bg', 'literal'] OSrc= 1 stdout= '' stderr= '[ERROR] Codey-OS daemon is not running. Start it with: codeydOS start\n'
PUBLIC ARGV= ['--bg', 'literal'] OSrc= 1 stdout= '' stderr= '[ERROR] Daemon identity is unsafe/unverifiable; connection refused\n'
PUBLIC ARGV= ['--bg', 'literal'] OSrc= 1 stdout= '' stderr= '[ERROR] Daemon identity is unsafe/unverifiable; connection refused\n'
PASS invalid IDs and absent/unsafe identities cause zero actual UDS requests
PUBLIC ARGV= ['status'] OSrc= 1 stdout= '' stderr= '[ERROR] fixture refusal\n'
PUBLIC ARGV= ['status'] OSrc= 1 stdout= '' stderr= '[ERROR] No response from daemon\n'
PUBLIC ARGV= ['status'] OSrc= 1 stdout= '' stderr= '[ERROR] Invalid response from daemon\n'
PUBLIC ARGV= ['status'] OSrc= 1 stdout= '' stderr= '[ERROR] Connection timed out. Daemon may be busy.\n'
PASS actual single status timeout elapsed_seconds= 5.135
PASS no generated Python/state files; literal paths/prompts stayed data
PUBLIC ARGV= ['--ctx', '2048', '"\n; prompt', '--yolo'] OSrc= 0 stdout= 'fixed foreground stdout\n' stderr= 'fixed foreground stderr\n'
PASS fixed foreground baseline normal OSreturn= 0 argv/stdin/stdout/stderr preserved=True
PUBLIC ARGV= ['--ctx', '2048', '"\n; prompt', '--yolo'] OSrc= 7 stdout= 'fixed foreground stdout\n' stderr= 'fixed foreground stderr\n'
PASS fixed foreground baseline return7 OSreturn= 7 argv/stdin/stdout/stderr preserved=True
PUBLIC ARGV= ['--ctx', '2048', '"\n; prompt', '--yolo'] OSrc= 7 stdout= 'fixed foreground stdout\n' stderr= 'fixed foreground stderr\n'
PASS fixed foreground baseline exit7 OSreturn= 7 argv/stdin/stdout/stderr preserved=True
PUBLIC ARGV= ['--ctx', '2048', '"\n; prompt', '--yolo'] OSrc= -2 stdout= 'fixed foreground stdout\n' stderr= 'fixed foreground stderr\nTraceback (most recent call last):\n  File "/data/data/com.termux/files/usr/tmp/g13-odf2724y/repo "\n; $(literal)/core/cli_client.py", line 173, in <module>\n    sys.exit(main())\n             ~~~~^^\n  File "/data/data/com.termux/files/usr/tmp/g13-odf2724y/repo "\n; $(literal)/core/cli_client.py", line 141, in main\n    return _direct(arguments)\n  File "/data/data/com.termux/files/usr/tmp/g13-odf2724y/repo "\n; $(literal)/core/cli_client.py", line 129, in _direct\n    return importlib.import_module("main").main()\n           ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~^^\n  File "/data/data/com.termux/files/usr/tmp/g13-odf2724y/repo "\n; $(literal)/main.py", line 9, in main\n    if mode==\'interrupt\':raise KeyboardInterrupt()\n                         ^^^^^^^^^^^^^^^^^^^^^^^^^\nKeyboardInterrupt\n'
PASS fixed foreground baseline interrupt OSreturn= -2 argv/stdin/stdout/stderr preserved=True
PUBLIC ARGV= ['--ctx', '2048', '"\n; prompt', '--yolo'] OSrc= -15 stdout= 'fixed foreground stdout\n' stderr= 'fixed foreground stderr\n'
PASS fixed foreground baseline term OSreturn= -15 argv/stdin/stdout/stderr preserved=True
PUBLIC ARGV= ['--daemon'] OSrc= 7 stdout= 'fixed foreground stdout\n' stderr= 'fixed foreground stderr\n'
Finally actual identity-owner reaped returncode= -15 UDS/thread closed=True; all public/baseline Popen waited
Approved five source/test SHA256 matched: {"codeyOS": "8d386447d53877429b7a68d41f6bee88f9d06e6ec34557642ff96679910784a8", "core/cli_client.py": "e0c076c270d7e13e5da352c15250ed309821b51995853354139455b05c95c938", "tests/test_cli_client.py": "644977ee951da8ea49e25ff97a9848e28ea81b446a16669450b77bf4c152903e", "tests/test_cli_client_dispatcher.py": "048c5839206991bbe892945b3a3e0d15a57248174df934671439a64827366dd9", "tests/test_service_public_lifecycle.py": "8073787e9e92fa74c3330c9dc5de93b4aa76f0c6abf32e5e5c289e6a347e462e"}
$ free -h (after)
               total        used        free      shared  buff/cache   available
Mem:            10Gi       7.2Gi       750Mi        65Mi       3.0Gi       3.6Gi
Swap:           15Gi       5.7Gi        10Gi
RESULT PASS
```
