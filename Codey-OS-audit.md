# Codey-OS Full Audit — 2026-07-29

Report-only audit. No fixes were applied. Every finding below cites real
evidence (file:line, command output, or a live reproduction performed
during this audit). Confidence is stated per finding: **Confirmed** =
reproduced or traced with certainty; **Suspected** = strong evidence but
not fully verified, with what would confirm it.

## Executive Summary

**Totals: 2 Critical, 6 High, 9 Medium, 6 Low, 6 Recommended enhancements.**

The live "Codey doesn't respond" symptom was diagnosed and reproduced
end-to-end: it is not a hang, a crash, or a backend misconfiguration —
it is a ~2,500-token baseline system prompt being processed at ~15–18
tokens/sec on-device, producing **~2.5–3 minutes of total silence before
the first output token**, with zero progress feedback, compounded this
morning by daemon churn (one daemon instance died silently mid-load) and
several process-management footguns that kill model servers out from
under live sessions. The codebase is in generally good shape structurally
(both test suites pass, Section 5 gating verified intact, path validation
in the agent filesystem layer is sound), but process lifecycle management
(blanket `pkill`), the GUI server's network exposure, and the CCOS
sandbox being non-functional on Termux are significant real problems.

---

## Priority: Live Symptom — Codey Not Responding (local 7B backend)

### What was actually observed (evidence, in order)

1. **Environment state at audit time:** daemon stopped (`codeydOS status`:
   "Main daemon: stopped, 7B model: not loaded"), no llama-server or
   orphaned processes running (`ps aux`), 6.4 GB RAM available, no
   `CODEY_*` env vars set anywhere (env + shell rc files checked) →
   `CODEY_BACKEND` correctly defaults to `local` everywhere. **The
   OpenRouter→local switch left no inconsistent config state** —
   ruled out as a cause (Confirmed).

2. **Session files record the real failures.** 
   `~/.codey_sessions/Codey-OS_cfa323501ba3.json` (saved 07:44 UTC) and
   `~/.codey_sessions/test_ad1ea826cb0f.json` (saved 07:54 UTC) show:
   `"list the files in the current directory using the ls tool"` →
   `"Done."` (**worked**), then `"hello"` →
   `"[ERROR] Chat completions inference failed"` — four times across two
   sessions.

3. **The model itself works.** `~/.codey-v3/llama-server.log` (a pre-rename
   run earlier the same morning) shows a 153-token prompt answered
   normally: prompt eval 14.1 t/s, generation 7.0 t/s, ~18 s total.

4. **The failing request reached the model and was processing fine —
   just extremely slowly.** `~/.codeyOS/llama-server.log` (last run,
   07:50–07:54 UTC) shows one task of **2,506 prompt tokens** processing
   at **~18 tokens/sec** (i.e. ~140 s needed before the first output
   token), **cancelled by the client ~148 s in** — right at the moment
   the first token would have been produced.

5. **Daemon churn this morning.** `state.db` episodic log: four daemon
   starts between 07:43 and 07:51 UTC; **PID 17682 (started 07:50:27)
   has no `daemon_stopped` entry** — it died silently, and a second
   daemon (PID 22179) was started 41 s later. A silent SIGKILL death
   during 7B model load is consistent with Android's low-memory/phantom
   process killing. The daemon task queue (`task_queue` table) is empty —
   no backlog involvement.

### Reproduction (deliberate, single, RAM-checked)

`free -h` showed 6.4 GB available before loading. One 7B llama-server was
started with the daemon's exact arguments, used for all tests, and
verified killed afterward (`pgrep -x llama-server` → none; RAM restored).

- Small prompt via the real client (`core/inference_hybrid.py`):
  **works**, first token ~1.7 s.
- ~2,500-token prompt via the same client: **works**, but **140.9 s of
  total silence** before "Hello!" appeared.
- Full real path — `python3 main.py "hello" --no-resume`: **works**, but
  took **173 s** after printing "⤁ Thinking..." with zero output or
  progress in between. Context bar printed by the agent itself:
  `2589/32768 tokens` — for the single word "hello".
- Prompt-size root cause measured directly:
  `prompts/layered_prompt.py:_build_draft_prompt("hello")` returns
  **10,134 characters ≈ 2,530 tokens** (its own `budget_chars` default is
  12,000 — `layered_prompt.py:80`).

### Root cause — Confirmed

**Every first message of a session — even "hello" — carries a ~2,500-token
system prompt that takes 2.5–3 minutes of silent prompt processing on the
local 7B before the first token appears.** The TUI shows only a static
"Thinking..." line for that entire time. To a user this is
indistinguishable from a hang, and this morning's session was cancelled
~148 s in — a few seconds before the response would have started.
(Follow-up messages in the same server lifetime are fast — llama-server's
slot cache reuses the processed prompt; the `.codey-v3` log shows a
follow-up answered in ~9 s with `sim_best = 1.000` cache reuse. This is
why the problem presents as "Codey never responds" rather than "Codey is
always slow": the first message is abandoned before the cache ever gets
populated.)

### The `[ERROR] Chat completions inference failed` entries — Suspected

That string is produced only at `core/inference_v2.py:131` when
`ChatCompletionBackend.infer()` returns `None`, which happens only when
an exception was caught and swallowed at `core/inference_hybrid.py:106-111`
(the exception text went to the terminal, not to any log, so it was not
recoverable after the fact). The reproduction above shows the same
request *succeeding* when nothing disturbs the server, so the morning
failures required an external disruption. Candidates, all with supporting
evidence, none individually confirmed as the one that fired:

- The silent daemon death + restart churn (evidence item 5) killing or
  replacing the model server mid-request → `ConnectionResetError` /
  `ConnectionRefusedError` in the client → `None` → the exact error
  string. This also explains the *instant* second failure ("hello" retried
  and failed within ~11 s with no new server task appearing in the llama
  log — nothing was listening or the connection was refused immediately).
- `codeydOS start` (line 152) runs `pkill -9 -f "llama-server.*8080"`
  *before* starting — re-running `start` while a previous daemon is still
  loading kills its model server (see H-4).
- RAM/swap pressure (device had 8.3/10.8 GB used at idle in earlier
  sessions per PROJECT_LOG; swap was in use during this audit).

**What would confirm it:** reproduce with the daemon running and stderr
captured (`codeyOS 2>&1 | tee`), or add the exception text to a log file
in `inference_hybrid.py`'s handlers before any fix work.

### Explicitly ruled out

- Backend/env inconsistency from the OpenRouter work — no `CODEY_*` env
  vars set; defaults are `local` (Confirmed).
- Orphaned processes holding ports — none existed at audit start
  (Confirmed).
- The old orphaned-`llama-server` bug recurring — different mechanism;
  the current problems are the *opposite* (over-eager killing, C-1/H-1/H-4).
- Daemon task-queue backlog — queue empty (Confirmed).

---

## Critical

### [C-1] First-token latency ≈ 2.5–3 minutes with zero feedback = total perceived non-response of core functionality
- **Confidence:** Confirmed (reproduced end-to-end; timings measured)
- **Location:** `prompts/layered_prompt.py:80` (12,000-char budget),
  `core/agent.py:1447-1505` (message assembly → `infer`),
  `core/inference_v2.py:122-123` (static "Thinking..." is the only feedback)
- **Description:** Even a one-word prompt is sent with a ~2,530-token
  system prompt. At the device's measured 15–18 t/s prompt-processing
  speed the user sees nothing for 140–173 s. The morning's real session
  was cancelled ~148 s in, seconds before first token.
- **Evidence:** `main.py "hello"` → 173.2 s to completion, context bar
  `2589/32768`; `_build_draft_prompt("hello")` = 10,134 chars; llama log
  task 0: 2,506 tokens at ~18 t/s, client-cancelled at ~148 s.
- **Impact:** With the default local backend, Codey appears completely
  non-functional to an interactive user. This is the live symptom.
- **Suggested direction:** Tier the system prompt (QA/smalltalk path —
  which `agent.py` already detects at line 1405 — does not need repo map,
  file blocks, or tool instructions); add visible progress during prompt
  processing (llama-server streams `prompt processing progress` into its
  log; a poll of `/slots`, or even a simple elapsed-time spinner with an
  honest "processing N-token prompt" estimate); keep the server warm
  between sessions so the slot cache survives.

### [C-2] GUI server: unauthenticated command execution, bound to 0.0.0.0 by default, no WebSocket Origin check
- **Confidence:** Confirmed (code path; not live-exploited)
- **Location:** `gui/server.py:269` (`host = os.environ.get("CODEY_GUI_HOST",
  "0.0.0.0")`), `gui/server.py:206-238` (`handle_ws` — no auth, no Origin
  validation), `gui/server.py:135-143` (WS `command` → spawns
  `main.py <prompt>` — the full agent, which can write files and run shell
  commands)
- **Description:** Anyone who can reach port 8888 can drive the coding
  agent on the device. Default bind is all interfaces, so on a shared
  Wi-Fi network this is remote-input agent execution. Worse, because the
  WebSocket has no Origin check, **any website open in the phone's own
  browser** can connect to `ws://localhost:8888/ws` (WebSockets are not
  restricted by CORS) and issue `command` messages — so even a localhost
  bind is exploitable by a malicious web page. The GUI auto-starts on
  every interactive `codeyOS` run (`codeyOS:397-411`), so exposure is the
  norm, not opt-in.
- **Evidence:** code lines above; `codeyOS:404-410` shows unconditional
  GUI startup in direct mode.
- **Impact:** Realistic remote/cross-site execution of an agent that can
  modify files on the device. Directly contradicts the README/branding
  claim of "100% Local".
- **Suggested direction:** Default `CODEY_GUI_HOST` to `127.0.0.1`;
  validate the `Origin` header against an allowlist; require a session
  token (generated at startup, embedded in the served `index.html`).

---

## High

### [H-1] `main.py` shutdown kills every llama-server on the device, not just its own
- **Confidence:** Confirmed (it killed this audit's independently-started server)
- **Location:** `main.py:141-147` (`pkill -9 -f llama-server`), guard at
  `main.py:131-133`
- **Description:** On interactive exit, if the *main daemon's PID check*
  fails, `shutdown()` SIGKILLs every process matching `llama-server` —
  including a standalone plannd 1.5B (port 8081, the project's own
  documented lightweight-testing flow), the embed server (8082), servers
  belonging to a daemon whose main process died but whose components are
  healthy, and any unrelated llama-server the user runs. The guard is
  all-or-nothing on one PID file.
- **Evidence:** During reproduction, `main.py "hello"` exited and killed
  the audit's manually-started llama-server (background task terminated;
  `ps` empty afterward).
- **Impact:** Model servers vanish out from under other components;
  combined with the silent daemon-death pattern (see Priority section),
  this produces exactly the "worked, then suddenly
  `[ERROR] Chat completions inference failed`" behavior recorded in the
  morning's session files.
- **Suggested direction:** Track the PID the loader actually spawned and
  kill only that; never `pkill` by bare name from a session that didn't
  spawn the process.

### [H-2] CCOS sandbox is non-functional on Termux — it rejects its own default working directory
- **Confidence:** Confirmed (test failure reproduced and root-caused)
- **Location:** `ccos/core/sandbox.py:22-26` (`ALLOWED_DIRS` contains
  literal `/tmp`), `ccos/core/sandbox.py:117` (`tempfile.mkdtemp()`),
  `ccos/core/sandbox.py:138-144` (cwd validation)
- **Description:** On Termux, `tempfile.mkdtemp()` creates the sandbox's
  own working directory under `$PREFIX/tmp`
  (`/data/data/com.termux/files/usr/tmp`), which is not covered by the
  literal `/tmp` entry in `ALLOWED_DIRS`. Every `run_command`/`run_python`
  call using the default cwd is rejected by the sandbox's own path check.
- **Evidence:** `pytest ccos/tests/test_ccos.py::test_sandbox` →
  `AssertionError: echo should succeed: [SANDBOX VIOLATION] Path not
  allowed: /data/data/com.termux/files/usr/tmp/ccos_sandbox_dkd5ely1`.
  Note: this failure has been carried in the project log as a
  "pre-existing sandbox failure, confirmed unrelated" — it is actually a
  real product bug on the primary target platform, not test noise.
- **Impact:** Everything routed through the sandbox (plugin tests,
  generated-code execution, the safety model's "sandbox-first execution"
  invariant) fails on Termux. It fails *closed*, so it's a functional
  break rather than a safety hole — but the master vision's sandbox-first
  governance is currently inoperative on-device.
- **Suggested direction:** Include `tempfile.gettempdir()` (and
  `$PREFIX/tmp`) in `ALLOWED_DIRS`, or validate against the resolved tmp
  root actually used to create `_tmp_dir`.

### [H-3] Daemon shell allowlist: dangerous-flag check skipped for non-Python commands → `find -exec` arbitrary command execution with confirmations disabled
- **Confidence:** Confirmed (code trace; not runtime-tested)
- **Location:** `core/task_executor.py:177-198` — the `_DANGEROUS_FLAGS`
  loop (lines 186-189, includes `-exec`) is inside `if is_python_cmd:`;
  `find` passes the prefix allowlist (line 52) and goes straight to
  `shell(command, yolo=True)` (line 198); `tools/shell_tools.py:211`
  (`if should_confirm and not yolo`) skips confirmation **even for
  commands `is_dangerous()` flagged**, contradicting the docstring at
  lines 189-190.
- **Description:** A daemon task whose model output emits
  `find . -name '*' -exec rm {} \;` (or `-exec` anything) executes it
  unattended — `shlex.split` + no shell doesn't help because `find`
  itself spawns `-exec` children. The comment at line 35 ("daemon never
  passes -delete") relies on the model's behavior, not enforcement.
- **Impact:** The autonomous daemon path can run destructive commands via
  an allowlisted binary. Threat model is LLM-generated commands, which is
  exactly what this path executes.
- **Suggested direction:** Apply the dangerous-flag check to all commands;
  add `-delete`/`-exec`/`-execdir`/`-ok` to a `find`-specific denial;
  make `yolo=True` not bypass the `is_dangerous()` gate in `shell()`.

### [H-4] Daemon start race: PID file written late, and `start` pre-kills port 8080 — re-running `start` during a slow load kills the loading daemon's model server
- **Confidence:** Confirmed race window in code; the double-start it
  enables was observed live this morning
- **Location:** `codeydOS:135-153` (PID guard, then unconditional
  `pkill -9 -f "llama-server.*8080"` at 152), `core/daemon.py:676`
  (`write_pid_file()` runs inside the Python daemon, seconds after the
  shell guard already passed); episodic log: `daemon_started PID 17682`
  07:50:27 UTC with no stop entry, `daemon_started PID 22179` 07:51:08.
- **Description:** The guard checks a PID file the daemon itself writes
  only once Python is up; 7B load takes ~15-40+ s during which a second
  `codeydOS start` (an impatient retry — exactly what a user does when
  "nothing happens", see C-1) passes the stale/absent-PID check and
  SIGKILLs the first instance's llama-server mid-load.
- **Impact:** Duplicate daemons contending for one socket/port, silent
  model-server death, RAM double-pressure on a device already near its
  ceiling. Contributes directly to the live symptom.
- **Suggested direction:** Write the PID file from the shell wrapper
  immediately (it already knows `$DAEMON_PID` at line 173), or use an
  atomic lockfile; scope the pre-kill to a PID recorded by the previous
  start rather than a name pattern.

### [H-5] Task timeout leaves a zombie agent thread running with restored interactive config
- **Confidence:** Confirmed (code trace)
- **Location:** `core/daemon.py:637-648` / `663-672`
  (`asyncio.wait_for(...)` around `executor._execute_task`),
  `core/task_executor.py:133-139` (`run_in_executor` thread)
- **Description:** `asyncio.wait_for` cancels the *coroutine* on timeout,
  but the underlying executor **thread cannot be cancelled** and keeps
  running the full agent (inference, tool execution, file writes). The
  cancelled coroutine's `finally` then restores `AGENT_CONFIG`
  (`confirm_shell`/`confirm_write` back to `True`) while the zombie is
  still running — so the zombie can (a) keep modifying files after the
  task was reported "Task timed out after 1800s"/failed, and (b) block
  forever on a confirmation `input()` in a process with no stdin.
- **Impact:** Silent post-failure file modification; leaked threads;
  daemon state (task marked failed) misrepresents reality.
- **Suggested direction:** Run tasks in a subprocess (killable) rather
  than a thread, or pass a cancellation event the agent loop checks
  between steps; only restore `AGENT_CONFIG` once the worker has actually
  finished.

### [H-6] Telemetry record-ID collision silently drops records (known bug re-verified — still present, and the described impact is confirmed accurate)
- **Confidence:** Confirmed
- **Location:** `ccos/core/telemetry_engine.py:162`
  (`record_id = f"exec_{int(time.time() * 1000)}_{id(record) % 10000}"`),
  `:113` (`record_id TEXT UNIQUE`), `:198` (`INSERT OR IGNORE`)
- **Description:** Two records created in the same millisecond can get
  identical IDs (CPython reuses freed object addresses, so `id() % 10000`
  recurrence is realistic in loops); `INSERT OR IGNORE` against the
  UNIQUE column then **silently discards** the colliding record. The
  previously-tracked fix direction (uuid4/atomic counter) is right.
  Additionally: `record_execution` (line 164) appends to `self._buffer`
  *without* the lock that `_flush_buffer` (line 194) holds — a concurrent
  append during flush can be cleared unwritten by `self._buffer.clear()`
  at line 219 (second, independent silent-loss path).
- **Impact:** Telemetry undercounts executions — the drift-detection and
  baseline math this engine exists for runs on silently incomplete data.
- **Suggested direction:** `uuid.uuid4()` for IDs; take the lock around
  buffer append, or swap the buffer (`buf, self._buffer = self._buffer, []`)
  under the lock before writing.

---

## Medium

### [M-1] The 15-second streaming watchdog is dead code — and would be wrong if it worked
- **Confidence:** Confirmed (attribute path verified nonexistent on this Python)
- **Location:** `core/inference_hybrid.py:166-169`, `:231-234`
- **Description:** `response.fp._sock.settimeout(15)` — on Python 3.14
  (this device) `fp` is a `BufferedReader` with no `_sock` (the socket is
  at `fp.raw._sock`); the `AttributeError` is swallowed by the bare
  `except`, so the intended no-data timeout never applies (reads run on
  the 300 s urlopen timeout instead). Verified:
  `socket.makefile('rb')` → `hasattr(fp, '_sock')` is `False`,
  `hasattr(fp.raw, '_sock')` is `True`. Separately, the design is wrong
  even when functional: 15 s of no data is *normal* during long prompt
  processing (C-1 measured 140-170 s), and `except socket.timeout: pass`
  at line 231 treats the timeout as a normal end-of-stream — it would
  return an **empty string as success** for any first-token wait over 15 s.
- **Impact:** Currently: no watchdog (hangs rely on the 300 s cap). If
  "fixed" naively by correcting the attribute path: every cold-start
  local inference would silently return empty.
- **Suggested direction:** Distinguish "no first token yet" (allow long,
  ideally progress-aware wait) from "stream stalled mid-generation"
  (short timeout), and surface a stall as an error, not empty success.

### [M-2] `codeyOS --bg` socket client times out at 30 s while the daemon may spend up to 180 s planning — queued work reported as an error
- **Confidence:** Confirmed (code); runtime behavior not exercised
- **Location:** `codeyOS:47` (`sock.settimeout(30.0)`),
  `core/daemon.py:155-158` (`asyncio.wait_for(send_plan_request_async(...),
  timeout=180.0)` before any reply is sent)
- **Description:** For any prompt that triggers planning, the daemon
  doesn't respond on the client socket until planning finishes (up to
  180 s on the local 1.5B); the client gives up at 30 s with
  "[ERROR] Connection timed out. Daemon may be busy." while the daemon
  carries on and queues the tasks anyway — the user is told it failed,
  but it actually ran.
- **Impact:** Misleading failure reports; duplicate submissions when the
  user retries.
- **Suggested direction:** Ack immediately ("queued, planning...") and
  deliver the plan asynchronously, or raise the client timeout to match
  the server's worst case.

### [M-3] Sandbox `cleanup()` is a silent no-op: `shutil` never imported
- **Confidence:** Confirmed
- **Location:** `ccos/core/sandbox.py:262-267` (uses `shutil.rmtree`);
  imports at lines 13-18 do not include `shutil`; the `NameError` is
  swallowed by `except Exception: pass`
- **Description / Impact:** Every sandbox instance leaks its
  `ccos_sandbox_*` temp directory forever.
- **Suggested direction:** Add the import; consider not blanket-silencing
  cleanup errors.

### [M-4] Sandbox enforcement is cosmetic where it does run
- **Confidence:** Confirmed (code inspection)
- **Location:** `ccos/core/sandbox.py:29-38` (substring blocklist),
  `:139` (only `cwd` validated, never the command's targets),
  `:152-160` (`shell=True`), `:242` (`install_package` blocks
  `; && | \`` but not `$( )`, `--index-url`, or option injection)
- **Description:** `rm -rf /*`, `rm -rf $HOME`, absolute-path writes from
  any cwd, and `$(...)` substitution inside `install_package` all pass.
  The vision's "no path escapes" is not enforced by this layer (`cwd` is
  checked; the command may operate anywhere). Related history: the
  `allowed_dirs`-parameter-ignored bug here was already found and fixed
  (dd49c1d) — the parameter is now honored (`:139` uses
  `self._allowed_dirs`), verified; these are the remaining gaps.
- **Impact:** Limited today (sandbox consumers are the gated Section-5
  modules and plugin tests, and H-2 currently breaks it entirely on
  Termux), but it is the load-bearing layer of the stated safety model.
- **Suggested direction:** Treat as a design pass, not patches: argv-list
  execution instead of `shell=True` where possible, resolve and check
  command targets, restrictive env.

### [M-5] `watchdog` missing on device despite being in `requirements.txt` and `install.sh` — file-watch silently disabled
- **Confidence:** Confirmed
- **Location:** `requirements.txt:6,26`; `install.sh:147`; runtime:
  `python3 -c "import watchdog"` → `ModuleNotFoundError`; daemon log:
  "FileWatch: watchdog not installed, file watches disabled"
- **Description:** The script and requirements are correct (no drift in
  the file — ground rule 10 checked out for this dep), but the device
  doesn't match them: either `install.sh` wasn't fully (re-)run or a pip
  environment change dropped it. The daemon degrades silently to
  no-file-watching.
- **Impact:** Documented daemon capability silently absent; symptom of
  device-vs-install.sh divergence worth a full `pip check` /
  `install.sh` re-run.
- **Suggested direction:** Re-run `install.sh`; consider a startup dep
  self-check that reports missing extras once, loudly.

### [M-6] `docs/commands.md` documents nonexistent commands and misses most real ones; `main.py` itself advertises a nonexistent flag
- **Confidence:** Confirmed
- **Location:** `docs/commands.md` (documents 8 slash commands incl.
  `/status`; `grep '"/status"' main.py` → no handler exists);
  `docs/commands.md:44` (`--rollback`) and `main.py:1518` (runtime hint
  "use --rollback to restore") — no `--rollback` in `parse_args`
  (`main.py:33-86`); real slash commands found in `main.py` dispatch:
  ~27 (`/cwd /diff /git /graph /ignore /load /memory-status /peer /rag
  /read /review /search /sessions /summarize /undo /unread /voice` etc.
  — all undocumented)
- **Description:** Confirms and extends the two known doc gaps: the
  `/status` entry describes a handler that was never wired (this is
  exactly `PENDING_ISH_DECISIONS.md` item 4 — `observability.py` still
  has no CLI handler; re-verified), and `--rollback` is advertised both
  in docs *and by the program itself* despite not existing.
- **Impact:** Users are told to run commands that don't exist; the
  post-LoRA-import hint at `main.py:1518` is actively misleading at the
  exact moment a user might need rollback.
- **Suggested direction:** Dedicated `docs/commands.md` regeneration pass
  from `main.py`'s actual dispatch + argparse; either implement
  `--rollback` (backing function exists: `core/lora_import.py:385`) or
  fix the hint.

### [M-7] `docs/architecture.md` contains zero CCOS-layer content (known gap re-verified)
- **Confidence:** Confirmed
- **Location:** `grep -c "ccos\|CCOS" docs/architecture.md` → `0`
- **Description:** The architecture doc describes only the coding agent;
  the entire OS-shell layer, plugin system, and Section-5 governance are
  absent. Already tracked as a planned rewrite
  (`CODEY_OS_MASTER_VISION.md` §7); still true.
- **Suggested direction:** The planned rewrite; no new information.

### [M-8] CCOS test suite: many tests return booleans instead of asserting — they cannot fail under pytest
- **Confidence:** Confirmed
- **Location:** all 7 `ccos/tests/test_*.py` files —
  `PytestReturnNotNoneWarning` raised 67 times in one run (pytest output);
  e.g. `ccos/tests/test_telemetry.py::test_persistence returned <class 'bool'>`
- **Description:** Functions written for a standalone runner
  (`return True/False`) pass under pytest regardless of outcome unless
  they also assert internally. Any regression whose only signal is a
  `False` return is invisible. (The suite's "67/68 passing" health signal
  is weaker than it looks.)
- **Impact:** Real coverage gap across the CCOS layer's own tests.
- **Suggested direction:** Mechanical `return` → `assert` conversion.

### [M-9] Filesystem workspace root is never resolved — symlinked workspaces would fail validation
- **Confidence:** Suspected (code inspection; not reproduced with a real
  symlinked workspace)
- **Location:** `core/filesystem.py:52` (`self.workspace` stored as-is),
  `:102-106` (candidate path is `.resolve()`d, then checked with
  `relative_to(self.workspace)` against the *unresolved* workspace)
- **Description:** If the workspace path contains a symlink (common on
  Android: `/data/data/...` vs `/data/user/0/...`, or a user symlink),
  every resolved candidate fails `relative_to` and all file access is
  denied (fails closed). The rest of the traversal protection
  (resolve-then-prefix-check, CODE_DIR opt-in gate at `:111-120`) is
  sound.
- **What would confirm:** instantiate `Filesystem(workspace=<symlink>)`
  and call `read()`.
- **Suggested direction:** `self.workspace = (workspace or
  WORKSPACE_ROOT).resolve()` in `__init__`.

---

## Low

### [L-1] Junk file `=3.9.0` committed to the repo
- **Confidence:** Confirmed
- **Location:** repo root; `git ls-files` includes it; content is pip
  install output ("Collecting aiohttp ...")
- **Description:** Artifact of an unquoted `pip install aiohttp >=3.9.0`
  (the `>=3.9.0` became a shell redirect). Committed at some point and
  never noticed.
- **Suggested direction:** `git rm`; quote version specs.

### [L-2] Stray empty file `main` at repo root (untracked)
- **Confidence:** Confirmed
- **Location:** repo root; 0 bytes, created 2026-07-29 07:10 UTC; shows
  as `?? main` in git status
- **Description:** Almost certainly another accidental shell redirect
  (e.g. a `> main` typo from a `git push origin main` variant). Harmless
  but confusing — it shadows nothing but sits next to `main.py`.
- **Suggested direction:** Delete (it is untracked; deletion is safe —
  verified empty).

### [L-3] Temp launcher scripts leak into `~/.codeyOS/` on abnormal exit
- **Confidence:** Confirmed
- **Location:** `codeyOS:419-429` (`mktemp run_XXXX.py` … `rm -f` only
  after normal return); evidence: three leftover `run_*.py` files in
  `~/.codeyOS/` dated across this morning's sessions
- **Description:** When the wrapper is killed (Ctrl+C at the wrong
  moment, terminal closed), the `rm -f` never runs. Same pattern for
  `socket_XXXX.py`/`status_XXXX.py`/`task_XXXX.py` blocks.
- **Suggested direction:** `trap ... EXIT` around the temp scripts, or a
  sweep on startup.

### [L-4] llama-server launched with repeated deprecated `--reverse-prompt` flags — only the last survives
- **Confidence:** Confirmed
- **Location:** `core/loader_v2.py:87-89` (one `--reverse-prompt` per
  stop token); server log: four `DEPRECATED: ... only last value will be
  used` warnings per start
- **Description:** The intended server-side stop set
  (`<|im_end|>`, `<|im_start|>`, `User:`, `Human:`, `A:`) collapses to
  just the final entry. Harmless in practice today because the chat
  endpoint applies template stops and the client passes `stop` in the
  request payload — but the loader's config intent is silently not
  applied.
- **Suggested direction:** Single comma-separated value per the
  deprecation notice, or drop the flags and rely on request-level stops.

### [L-5] `codey-stop` runs under `set -e` with dependent stages
- **Confidence:** Suspected
- **Location:** `codey-stop:10` (`set -e`), line 18
  (`bash codeydOS stop` — a nonzero return here aborts the script before
  the GUI kill and the orphan sweep)
- **Description:** Most `codeydOS stop` paths return 0, but any nonzero
  (e.g. plannd stop edge case) would leave GUI/orphan cleanup unexecuted.
  Would confirm: run `codey-stop` while `codeydOS stop` is made to fail.
- **Suggested direction:** Drop `set -e` here or `|| true` the stages —
  a stop script should attempt every stage.

### [L-6] A loader-spawned llama-server appeared during the audit and outlived its parent (origin not pinned)
- **Confidence:** Suspected
- **Location / Evidence:** after the `main.py "hello"` reproduction and a
  `pytest tests/` run, `ps` showed a llama-server (PID 19513) with
  `loader_v2`-style arguments (the `--reverse-prompt` series) that no
  audit step had started directly and no shutdown path had killed; killed
  manually, RAM recovered from 8.2 GB→3.4 GB used.
- **Description:** Something in the exercised paths (most plausibly a
  test importing a module that triggers `get_loader().ensure_model()`
  with port 8080 free, or a `loader` re-spawn inside the `main.py`
  session after its original server died) spawns a full 7B server and
  does not own its lifecycle. Given this project already fixed one
  orphaned-llama-server bug (14bc42c), this looks like a distinct,
  surviving variant. Would confirm: re-run `pytest tests/ -q` with port
  8080 free and watch `pgrep -x llama-server` before/after.
- **Impact if real:** a test run or recovered session silently pins
  ~4.5 GB of RAM on a device with a known RAM ceiling.
- **Suggested direction:** Identify the spawn site (audit `ensure_model`
  callers reachable from tests); tests should never be able to spawn the
  real model server.

---

## Recommended Enhancements

*(not bugs — improvement ideas, kept separate per instructions)*

### [E-1] Progress feedback during prompt processing
The single highest-leverage UX change for the live symptom: an elapsed
timer, token-progress estimate, or llama-server `/slots`-based progress
line while "Thinking...". Even with no speedup, C-1 stops presenting as a
hang. (Direction, not design — pairs with the C-1 fix.)

### [E-2] Tiered system prompt by task class
`agent.py` already classifies QA/smalltalk (`is_qa`, line 1405) and
breadth (`classify_breadth_need`); the prompt builder doesn't use that
signal — everything gets the full ~12,000-char layered prompt. A minimal
prompt for QA/chat turns would cut cold-start first-token latency roughly
an order of magnitude for exactly the messages users open sessions with.

### [E-3] PID-ownership process management
Replace all four name-pattern `pkill` sites (`main.py:145`,
`codeydOS:152,193,202,214,223`, `codey-stop:37`) with spawn-time PID
files per component. This one change addresses H-1, H-4, and the C-1
compounding factors together.

### [E-4] GUI hardening bundle
Localhost default bind + startup token + Origin allowlist (C-2), plus
fixing the `active_proc` TOCTOU race (`gui/server.py:221-222` checks
`active_proc is None` before the spawned task sets it — two rapid
commands run concurrently).

### [E-5] Wire `/status` (observability.py)
Already `PENDING_ISH_DECISIONS.md` item 4; M-6 makes it slightly more
urgent because the docs already promise it exists.

### [E-6] Keep the model server warm across sessions by default
The measured data shows the second message is ~9 s vs ~170 s cold — the
daemon already exists as the natural owner of a persistent server.
Interactive sessions ending should not be able to take the model down
(ties into E-3/H-1); "warm by default, `codey-stop` to actually stop" is
the behavior `codey-start`'s own comments (lines 10-13) already describe.

---

## Areas Reviewed

Coverage of the requested scope, with honest depth notes:

1. **Entry points / lifecycle** — `codeyOS`, `codeydOS`, `codey-start`,
   `codey-stop` read in full; `main.py` startup/shutdown/REPL/dispatch
   paths read; `install.sh` reviewed for dependency handling (not
   line-by-line); `gui/start.sh`, `setup.sh`, `setup_repo.sh` **not
   reviewed** (time went to the live symptom; `gui/start.sh` is
   superseded by `codey-start` per the vision).
2. **`core/`** — deep: `inference_hybrid.py` (full), `inference_v2.py`
   (full), `daemon.py` (lifecycle/handlers/task loop), `task_executor.py`
   (full execution path), `filesystem.py` (validation layer),
   `loader_v2.py` (spawn path), `agent.py` (run_agent flow, QA gate,
   inference call sites, peer-delegation block), `sessions.py` (storage),
   `checkpoint.py` (git usage, spot), `main.py` `_run_with_plan`.
   Lighter (grep-level for security/concurrency patterns only):
   `recursive.py`, `orchestrator.py`, `planner*.py`, `plannd.py`,
   `memory_v2.py`, `symbolic_graph.py`, `embeddings.py`, `taskqueue.py`,
   `recovery.py` (wiring status verified: still no `agent.py` call site —
   only the CCOS plugin wrap at
   `ccos/plugins/coding/error_recovery/error_recovery.py:38` — matching
   the vision's still-open "wire up" status), `strategy_tracker.py`,
   `observability.py` (wiring status verified via M-6), `sysmon.py`,
   `thermal.py`, `githelper.py`, `voice.py`, `peer_cli.py`,
   `peer_shell.py`, `finetune_prep.py`, `lora_import.py`,
   `dashboard_data.py`. **Not meaningfully reviewed:** the remaining
   small `core/` modules (`notes.py`, `display.py`, `tokens.py`, etc.).
3. **`ccos/`** — deep: `sandbox.py` (full), `telemetry_engine.py`
   (recording/flush paths). Moderate: `plugin_manager.py` (discovery/
   load), `lifecycle_manager.py` (reachability). Grep-level:
   `capability_registry.py`, `tool_router.py`, `agent_orchestrator.py`,
   `device_manager.py`, plugins under `ccos/plugins/` (import scan only).
4. **Security-specific** — shell construction audited in
   `tools/shell_tools.py` (full), `task_executor.py` (full),
   `agent.py` test-command construction (`:1203`, `:1810` — both build
   from agent-chosen filenames but execute through `shell()`'s
   shlex/no-shell path, so injection requires the allowlist gaps in H-3
   rather than string injection); path handling in `filesystem.py` +
   sandbox; credential handling verified env-var-only
   (`utils/config.py:210,222`), no keys committed or logged in the
   inspected paths; sandbox `allowed_dirs` re-verified (prior fix holds;
   new gaps in H-2/M-4).
5. **Concurrency / resources** — llama-server spawn/kill lifecycle
   (H-1/H-4/L-6), daemon task threading (H-5), telemetry locking (H-6),
   GUI process race (E-4). Thread audit of `sysmon`/`thermal` was
   grep-level only (daemon threads, bounded sleeps — nothing alarming
   surfaced).
6. **Section 5 gating** — independently re-verified: repo-wide import
   scan shows `goal_engine` / `auto_improvement_loop` /
   `capability_optimizer` / `skill_recombiner` / `lifecycle_manager`
   reachable **only** from `ccos/demo_*.py` scripts and their own tests;
   no path from `core/daemon.py`, `main.py`, `ccos_main.py`, `gui/`, or
   any plugin. **Gate intact.**
7. **Test suites** — both executed: `tests/` 253/253 pass (24.1 s);
   `ccos/tests/` 67 pass / 1 fail (the failure root-caused as H-2, a
   product bug, not test noise); return-style anti-pattern documented
   (M-8). Possible model-server spawn from the suite noted (L-6).
8. **`tools/` / `pipeline/` / `prompts/` / `utils/` / `gui/`** —
   `gui/server.py` full; `tools/shell_tools.py`, `tools/file_tools.py`
   (validation-relevant parts), `prompts/layered_prompt.py` (structure +
   measured), `utils/config.py`, `utils/logger.py` (confirm path)
   reviewed. `pipeline/` received only a shell/injection pattern scan
   (clean) — **not a real review**; it is offline tooling with no daemon
   exposure, deprioritized deliberately.
9. **Docs accuracy** — both known gaps re-verified and extended (M-6,
   M-7). Other `docs/` files not systematically checked beyond
   `commands.md`/`architecture.md`.
10. **`install.sh` completeness** — no *file-level* drift found for the
    deps checked (`rich`, `watchdog`, `aiohttp`, espeak/termux-api all
    present); the drift found is device-vs-script (M-5).

**RAM discipline note:** the single 7B load for reproduction was done
after checking `free -h` (6.4 GB available), used for all three
reproduction tests, and torn down; the audit-discovered stray server
(L-6) was also killed. `pgrep -x llama-server` returns nothing and the
daemon remains stopped at audit end.
