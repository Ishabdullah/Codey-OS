# New Issues Found During V3 Overhaul

## Found during Round 3 (NEW-4) live-verification pass, 2026-07-29 — NOT fixed, logged only

### [NEW-5] `llama-server` child can outlive `gui/start.sh`'s (or any) parent process indefinitely on a TERM/Ctrl+C during mid-load, with no automatic recovery
- **Status: Resolved** (2026-07-30, Round 6). Fixed by commit `eed29dc`:
  `main.py`'s `repl()` (~line 1267-1274) now wraps `loader.load_primary()`
  in `try/except (KeyboardInterrupt, SystemExit)`, calling the existing
  `shutdown()` and returning cleanly, reusing the scoped-PID teardown
  path with no new kill logic. code-reviewer approved; live-verifier
  independently reproduced a genuine mid-load `SIGINT` via `pty.fork()`
  (tracked child PID) and confirmed no orphan `llama-server` remained
  (`ps -eo pid,ppid,pgid,comm | grep -E "python|llama"` empty, `free -h`
  RAM recovered), plus a regression check on the normal-completion path.
  See `PROJECT_LOG.md` 2026-07-30 entry for full verbatim evidence.
  `NEW_ISSUES.md` [NEW-6] (same unguarded pattern at three sibling call
  sites) remains open as a separate, unscoped follow-up.
- **Confidence: Confirmed** (upgraded 2026-07-29, Round 6 — live-reproduced
  and root-caused by reading the code; previously Suspected on a single
  observation).
- **Original (Suspected) finding, Round 3:** implementer's live
  verification of the default (no-flag) path for the Round 3
  `--dashboard-only` task (`gui/start.sh`, commit `ea954eb`) observed the
  spawned `llama-server` child (a tracked PID) "still alive briefly"
  after the parent script exited on a mid-load `TERM`, before being
  killed directly by that tracked PID. Not reproduced a second time at
  the time; no root cause investigated.
- **Round 6 live reproduction (this entry's upgrade):** live-verifier sent
  `kill -TERM` to the tracked `gui/start.sh` script PID while the 7B
  model was mid-load, then polled every 0.5s for 10+ seconds. The bash
  script, `gui/server.py`, `main.py`, and `llama-server` were **all still
  alive, unchanged**, for the entire polling window — not "briefly"
  outliving the parent, but surviving it with no sign of any teardown in
  progress. Letting it run to full completion (~40s later total), the
  script's own `trap ... TERM` handler **never fired**, because bash was
  blocked in `wait()` on its foreground child (`python main.py`), which
  does not exit on its own when sent `TERM` this way. The tracked PIDs
  (`main.py` and `llama-server`) had to be killed individually and
  manually — there is no automatic recovery path.
- **Root cause (identified by reading the code, not just observing
  behavior):**
  - `main.py`'s `repl()` (around line 1269) calls
    `loader.load_primary()` with no `try/except KeyboardInterrupt`
    wrapper around the call.
  - `ModelLoader.load_primary()`'s own exception handler
    (`core/loader_v2.py` around line 351) is `except Exception`, which
    does **not** catch `KeyboardInterrupt` (it subclasses
    `BaseException`, not `Exception`), so a `KeyboardInterrupt` raised
    during the load window propagates straight out of `load_primary()`
    uncaught.
  - There is also no top-level exception handler around `main()` itself
    (bottom of `main.py`, `if __name__ == "__main__": main()` is bare),
    so an uncaught `KeyboardInterrupt` during this window exits the
    process without ever calling `shutdown()` (`main.py` line ~125,
    which contains the correct scoped-PID teardown logic via
    `loader.get_pid()` / `loader.unload()`).
  - Separately, `llama-server` is spawned with `preexec_fn=os.setsid`
    (`core/loader_v2.py` line 127), putting it in its own process
    group specifically to insulate it from terminal signal groups —
    meaning it is never touched by a terminal-delivered signal that
    hits `main.py`, and depends entirely on `main.py`'s own code
    explicitly killing it. When that code path is skipped (as above),
    `llama-server` becomes a genuine, indefinitely-running orphan.
  - Important supporting detail for any fix: `ModelLoader.load_primary()`
    (`core/loader_v2.py` line 341) assigns `self._server = LlamaServer(...)`
    **before** calling `self._server.start()` (line 342), and `start()`
    itself sets `self.process` (the `Popen` handle, with its real PID)
    immediately after spawning (line 123-130), well before the up-to-60s
    health-check polling loop that follows (lines 132-153). This means
    `loader.get_pid()` / `loader.unload()` are both usable to tear down a
    partially-started server for nearly the entire load window, not just
    after a successful load — a catch-and-teardown fix has a real target
    to kill for almost the full duration of the exposure window.
- **Confirmed NOT broken:** a normal Ctrl+C at the `You>` prompt (i.e.
  post-load, in the REPL's own input loop) works cleanly and tears
  everything down in ~1.5s — the REPL's existing
  `except (KeyboardInterrupt, EOFError)` blocks (e.g. `main.py` line 948)
  catch it fine there. The gap is specific to the model-load window,
  before any of those handlers are active.
- **Scope note:** lives entirely in `main.py`'s own model-load call site
  and `core/loader_v2.py`'s exception handling, not in `gui/start.sh`'s
  trap logic. Confirmed unreachable in `--dashboard-only` mode, since
  `main.py` never runs there.
- **Fix direction (scoped as a Round 6 follow-on task, not yet applied):**
  wrap the `loader.load_primary()` call in `repl()` (`main.py` ~line
  1269) in a `try/except (KeyboardInterrupt, SystemExit)` that, on catch,
  calls the existing `shutdown()` (`main.py` line 125) to tear down any
  partially-started server via the scoped-PID path it already uses, then
  exits cleanly — reusing `shutdown()`, not reinventing a parallel kill
  path. This is CLAUDE.md rule 4 territory (process/daemon lifecycle,
  kill logic) and requires code-reviewer's explicit approval before
  commit regardless of how small the diff looks.

## Found during Round 6 NEW-5 root-cause investigation, 2026-07-29 — NOT fixed, logged only

### [NEW-6] Same unguarded `loader.load_primary()` pattern exists at three other call sites in `main.py`
- **Confidence: Suspected** (same code shape confirmed by reading the
  code; not independently live-reproduced at each site the way NEW-5 was
  for the `repl()` path — but the mechanism is identical, so the risk is
  the same in kind).
- **Where found:** while investigating NEW-5's root cause, grepped all
  call sites of `loader.load_primary()` in `main.py`. In addition to
  `repl()` (~line 1269, the one covered by NEW-5's scoped fix), the same
  unguarded pattern (`loader = get_loader(); loader.load_primary()` with
  no surrounding `try/except KeyboardInterrupt`) appears at:
  - `args.init` path, `main.py` ~line 1458
  - `args.tdd` path, `main.py` ~line 1465-1466
  - `args.fix` path, `main.py` ~line 1485-1486
- **Why this matters:** a `KeyboardInterrupt` (e.g. Ctrl+C) during model
  load in any of these one-shot CLI paths would hit the same gap as
  NEW-5 — no handler catches it before it propagates out of
  `load_primary()`, `shutdown()` is never called, and `llama-server`
  (spawned in its own process group via `preexec_fn=os.setsid`) is left
  as an orphan.
- **Not fixed here:** the NEW-5 fix task is deliberately scoped to just
  the `repl()` call site (the one actually live-reproduced). These three
  sibling sites are logged for a possible dedicated follow-up task, not
  bundled into the NEW-5 fix, to keep that fix tightly scoped per
  CLAUDE.md's project-architect instructions.

## Found during Round 2 (C-2) live-verification pass, 2026-07-29 — NOT fixed, logged only

### [NEW-4] `gui/start.sh` unconditionally chains into `main.py`, forcing a full 7B model load just to view the dashboard
- **Confidence: Confirmed** (directly observed live during the C-2
  live-verification pass, not inferred).
- **Where found:** live-verifier's real launch of `gui/start.sh` (the
  actual daemon-managed GUI startup path, not a scratch instance) while
  confirming C-2's GUI-security fixes end-to-end.
- **Finding:** `gui/start.sh` unconditionally chains into `main.py` after
  starting `gui/server.py`, and `main.py` eagerly loads the 7B model with
  zero user interaction required. There is no path to bring up the GUI
  server/dashboard alone without also paying the full 7B model-load cost
  — observed directly: launching via `gui/start.sh` triggered a real
  `llama-server` 7B load (PID 25675) before the dashboard was usable.
- **Impact:** a user who only wants to check the dashboard (RAM/CPU/temp,
  task status, etc.) via the GUI has no way to do so without incurring a
  full model load, which on this device is a meaningful RAM/time cost and
  runs against this project's RAM-discipline concerns (rule 2 in
  `CLAUDE.md`).
- **Suggested direction (not applied — out of scope for the C-2
  live-verification task that found it):** decouple `gui/server.py`'s
  dashboard-only capabilities (which read from `core/dashboard_data.py`,
  not the model) from `main.py`'s model-loading REPL, so `gui/start.sh`
  can optionally start just the dashboard server without also spawning
  `main.py`. Needs its own scoped task — not a security issue, a
  resource-cost/UX one.

## Found during Round 2 (C-2 GUI security) sub-task 3/3, 2026-07-29 — RESOLVED in Round 4, commit `efe9f5c`

### [NEW-3] GUI session token may leak into access logs if logging is ever configured for `gui/server.py`
- **Status: RESOLVED (2026-07-29, commit `efe9f5c`).** `gui/server.py`'s
  `web.run_app()` call now passes `access_log=None`, disabling aiohttp's
  default `AccessLogger` outright rather than relying on the current
  absence of a configured `logging` handler to keep the token dormant.
  code-reviewer approved: confirmed `access_log` is a genuine documented
  `aiohttp` kwarg (aiohttp 3.14.3 installed) and verified no other log
  call site in `gui/server.py` could leak the token. No live-verification
  performed for this fix specifically — scoped as a negative/absence
  assertion with no new live-session behavior to exercise, already
  covered by the prior Round 2 (C-2) full live-verification of normal GUI
  start (see `PROJECT_LOG.md`). Original finding detail preserved below.
- **Confidence: Suspected** (dormant today, plausible future trigger; not
  verified as currently reachable).
- **Where found:** code-reviewer's review of the C-2 sub-task 3 session-token
  commit (`1198ba1`).
- **Location:** `gui/server.py`, `web.run_app()` call (entry point, ~line 300).
- **Finding:** `web.run_app(make_app(), host=HOST, port=PORT, print=lambda
  *_: None)` is called without `access_log=None`, so aiohttp's default
  `AccessLogger` remains active and logs the full request line — including
  the `?token=<SESSION_TOKEN>` query string on `/ws` upgrade requests — at
  INFO level via Python's `logging` module.
- **Why not currently exploitable:** nothing in this repo calls
  `logging.basicConfig()` (or otherwise configures a handler) for the GUI
  process, and `gui/start.sh` backgrounds `python gui/server.py &` without
  redirecting stdout/stderr to a persistent file. Python's `logging`
  module's default `lastResort` handler only surfaces WARNING+ to stderr, so
  the INFO-level access log line is silently dropped today — the token does
  not currently land in any file or terminal output.
- **Why it's still worth tracking:** this is fragile, not fixed. If a future
  change adds `logging.basicConfig()` anywhere in the process (common when
  wiring up broader observability), or if `gui/start.sh` (or any future
  daemon supervisor) redirects the GUI subprocess's stdout/stderr to a log
  file, the session token starts landing in a readable log with no code
  change to `gui/server.py` itself required to trigger it.
- **Suggested fix (not applied — out of scope for this sub-task):** either
  pass `access_log=None` to `web.run_app()`, or move the token off the query
  string (header on upgrade, or first-message-after-connect) so it's not
  part of what any access logger would capture by default.

## Found during H-4 self-race / C-1 short-prompt follow-up task, 2026-07-29 — NOT fixed, logged only

### [NEW-2] `patch_file` with `old_str: ""` silently no-ops instead of inserting or erroring
- **Confidence: Confirmed** (directly observed, not inferred).
- **Where found:** Live verification of the C-1 short-QA-prompt fix. In a
  single warm `python3 main.py --no-resume` session, after two QA turns
  ("hello", "what can you do?"), a real coding request was sent: "add a
  docstring to the `shutdown` function in `main.py`". This correctly took
  the full/non-lightweight path (`main.py` loaded into context,
  `[Recursive] Draft (1/2)` → `[Recursive] Review (2/2)` → "Accepted —
  quality 8/10") and the model emitted a `patch_file` tool call:
  `{"name": "patch_file", "args": {"path": "main.py", "old_str": "", "new_str": "def shutdown():\n    \"\"\"...docstring...\"\"\"\n    print('Shutting down...')\n    # Add your shutdown logic here."}}`.
- **Evidence it no-op'd:** Immediately after acceptance, the harness
  logged `⚠ Malformed tool call — JSON parse failed, retrying`, which
  triggered a second, near-identical `patch_file` call with the same
  `old_str: ""`. No error or success message about the patch's actual
  effect was ever printed before the next `You>` prompt appeared.
  `git diff main.py` afterward showed **zero changes** — `shutdown()` at
  line 125 has no docstring, unmodified from HEAD. The model's tool call
  ran (or was retried) but never touched the file.
- **Likely root cause (not yet verified against `tools/patch_tools.py`):**
  the model appears to be using `old_str: ""` to mean "insert without
  matching," but `patch_file`'s matching logic likely treats an empty
  `old_str` as either "match nothing" (silent no-op) or a bad match
  that gets swallowed rather than surfaced as `[PATCH_FAILED]` to the
  user. Note `tests/test_patch.py`'s pre-existing failure (further down
  this file) is about the *format* of the failure message
  (`[PATCH_FAILED]` vs `[ERROR] String not found`) — this is a different,
  possibly related but unconfirmed, issue about a failure not being
  surfaced at all for the empty-`old_str` case.
- **Impact:** A user asking for a simple, common edit ("add a docstring
  to X") can get a "quality 8/10, accepted" response with an emitted tool
  call that looks successful in the transcript, while the file is
  actually untouched — a silent-failure UX gap, not a crash.
- **Not fixed here:** out of scope for the H-4/C-1 task that surfaced it
  (this task touched `core/daemon.py`, `prompts/system_prompt.py`, and
  `prompts/layered_prompt.py` only). Needs a dedicated look at
  `tools/patch_tools.py`'s handling of empty/non-matching `old_str`
  before deciding whether the fix is in the tool implementation or in
  prompting the model to never emit an empty `old_str`.
- **Correction (2026-07-29, Round 3 scoping pass) — the hypothesized
  root cause above does not hold up; downgrading per CLAUDE.md rule 6.**
  Read `tools/patch_tools.py:19-22` directly: an empty/non-string
  `old_str` is already explicitly rejected —
  `if not old_str or not isinstance(old_str, str): return "[ERROR]
  Invalid old_str: empty or not a string"` — and `git log --follow -p`
  shows this check has existed since commit `8ab96e1` (Jun 13 2026), well
  before this session. So `tool_patch_file` itself does **not**
  silently no-op on `old_str: ""` — it returns a clear, explicit error
  string. The originally-suspected fix location (`patch_tools.py`'s
  matching logic) is not where the bug is.
  - **Re-reading the original transcript evidence with this in mind:**
    the "malformed tool call — JSON parse failed" warning fired
    *before* any tool executed, meaning `tool_patch_file` was likely
    never actually called on the first attempt (the JSON never parsed,
    probably due to unescaped literal newlines inside the multi-line
    docstring in `new_str`, which breaks strict JSON parsing). The
    retry then produced a second near-identical malformed call.
  - **New, more likely mechanism (unconfirmed, needs live reproduction
    to nail down):** `core/agent.py:1434` sets `max_retries = 1`, so
    the malformed-tool-call retry path (`core/agent.py:1537-1553`) only
    gets one retry attempt. If the second attempt *also* fails to parse,
    `auto_retries >= max_retries` and the code falls through past the
    `if tool_dict:` block entirely (nothing between lines ~1553 and
    ~1843 re-enters it for a null `tool_dict` after retries are
    exhausted) to `history.append(...); return response, history`
    around `core/agent.py:1869-1873` — i.e. the raw, still-malformed
    model text becomes the "final answer" with no explicit surfacing of
    "the patch never applied." This would explain a silent-looking
    failure without any code in `patch_tools.py` being at fault.
  - **Status:** downgraded from Confirmed-root-cause to Suspected — the
    silent-no-op *symptom* is still Confirmed (git diff showed zero
    change), but the mechanism is now believed to be in
    `core/agent.py`'s malformed-JSON-retry exhaustion path, not
    `tools/patch_tools.py`. Needs a fresh live reproduction (single warm
    session, ask for a multi-line docstring/edit likely to trigger an
    unescaped-newline JSON break) with the raw model output captured
    verbatim before scoping an implementer task — not ready to hand off
    yet.

## Found during Round 1 (C-1/H-1/H-4) fix task, 2026-07-29 — NOT fixed, logged only

### [NEW-1] `pytest tests/` spawns a real 7B `llama-server` and orphans it — matches audit finding L-6

- **Status: RESOLVED (commit `c65be95`), fully live-verified 2026-07-29.**
  live-verifier ran the full suite: `pytest tests/ -q` → **253 passed in
  0.43s** (previously ~42s, due to the hidden real 7B model load). No
  orphan `llama-server` process remained afterward, confirmed via
  `ps -eo pid,ppid,comm | grep llama` (not `pgrep -af`, which has a
  false-positive self-match issue in this shell environment — the
  wrapper's own command-line text matches the `llama` pattern). `free -h`
  was stable before/after (563Mi free → 816Mi free; swap unchanged at
  1.6Gi). Per Ground Rule 7, this closes the "code complete" →
  "fully live verified" gap left open after code-reviewer's approval,
  which had only re-run `tests/test_memory.py` in isolation, not the full
  suite.
- **Confidence: Confirmed (upgraded from Suspected, Round 5 diagnostic
  investigation, 2026-07-29).** The mechanism below was live-reproduced
  3+ times, including a decisive proof: catching the orphaned
  `llama-server`'s PPID pointing directly at the live pytest process
  itself, before OS reparenting to PID 1 had occurred.
- **Root cause:**
  `tests/test_memory.py::TestMemoryCompressSummary::test_compress_summary_handles_inference_failure`
  (lines ~351-361) calls `self.memory.compress_summary(long_history)`
  with **no mocking of inference at all**, despite its name and docstring
  ("compress_summary should return fresh turns when inference fails")
  implying it tests a failure/degraded path. Call chain: test →
  `core/memory_v2.py:600-627` `compress_summary()` unconditionally does
  `from core.inference_v2 import infer; ... compressed = infer(prompt,
  stream=False)` (line 619, wrapped in a bare `try/except Exception`,
  line 603/625, which is why the test still passes either way and never
  signaled the problem) → `core/inference_v2.py:65-94` `infer()` does
  `loader = get_loader(); if not loader.ensure_model(): ...` (lines
  92-94) — this `ensure_model()` call is the real model-load trigger,
  spawning an actual local 7B `llama-server` subprocess.
- **Evidence:**
  - A timestamped, verbose pytest log showed a 28-second gap (consistent
    with a real 7B model load) immediately before this specific test,
    versus ~5ms between every other adjacent test pair in the suite.
  - Live-reproduced 3+ times in Round 5.
  - Decisive proof: in one reproduction, the orphan `llama-server`'s PPID
    was caught pointing directly at the live pytest process ID before OS
    reparenting to PID 1 occurred (matches the two earlier PPID-1
    orphan observations logged below, which were seen only after
    reparenting had already happened).
  - Nothing in the test's setUp/tearDown (`tests/test_memory.py:335-340`,
    `reset_memory()` only) tracks or kills the spawned server, which is
    why it's left running/orphaned after the test session ends.
- **Original correlation evidence (Round 1, retained for record):** Ran
  `python3 -m pytest tests/ -q` (253/253 pass, no failures) inside one
  single shell command that also ran `free -h; pgrep -af llama-server`
  immediately after — that combined command's output showed a full 7B
  `llama-server` on port 8080 running with `PPID 1` (reparented/orphaned),
  no PID file anywhere (`~/.codeyOS/codeyOS.pid` doesn't exist), no daemon
  running. Reproduced in an earlier separate run too (different PID).
  Both times the process outlived the pytest run and had to be killed
  manually (`kill -TERM -<pid>`, scoped to that PID's process group) to
  recover RAM — that part (kill discipline, RAM recovery) is solid and
  verified both times via `free -h` before/after.
- **Impact:** a device crash occurred during the Round 1 session in which
  this was first observed, with RAM going from ~6.6 GB available to under
  200 MB free with 6+ GB in swap without any deliberate model-load
  action. Now that the mechanism is confirmed, this test is a real,
  reproducible RAM-crash contributor, not just a plausible one — every
  plain `pytest tests/` run loads a full 7B model and orphans the server.
- **Round 1 static investigation (superseded by Round 5, not
  retracted):** a targeted grep-level search
  (`grep -rn "llama-server\|LlamaServer\|subprocess\|Popen\|get_loader\|ensure_model" tests/*.py`)
  missed the mechanism because it only checked for direct spawn/loader
  calls inside `tests/*.py` files, not the indirect path through
  `core/memory_v2.py`'s `compress_summary()` (`infer(` is called from
  non-test code). That static approach could not have found this; the
  gap is closed by the Round 5 dynamic (timestamped-log + PPID-capture)
  investigation above.
- **Fix direction:** mock `core.inference_v2.infer` (or the loader it
  calls) in `test_compress_summary_handles_inference_failure` so the test
  actually exercises the inference-unavailable branch it claims to test,
  without triggering a real model load. See fix task scoped in
  `PROJECT_PLAN.md` / handed to implementer.

## Pre-existing Test Failures (Not Introduced by V3 Changes)

### test_hallucination.py (8 failures)
- **Issue**: Hallucination detection tests failing
- **Root Cause**: The `detect_hallucination()` function in `core/agent.py` doesn't detect past-tense claims like "I created", "I wrote", "I modified"
- **Impact**: Medium - hallucination detection is incomplete
- **Files**: `tests/test_hallucination.py`, `core/agent.py`
- **Recommendation**: Review and update hallucination detection patterns

### test_patch.py (1 failure)
- **Issue**: Patch error message format changed
- **Root Cause**: The patch tool now returns `[PATCH_FAILED]` instead of `[ERROR] String not found`
- **Impact**: Low - test expectation mismatch
- **Files**: `tests/test_patch.py`, `tools/patch_tools.py`
- **Recommendation**: Update test to match new error format

## Additional Security Hardening Needed

### 1. Command Injection via Filename (agent.py:863-865)
- **Status**: Partially addressed
- **Issue**: Shell commands built from LLM-generated filenames
- **Recommendation**: Add filename sanitization before shell command construction

### 2. Daemon Shell Allowlist Too Broad (task_executor.py:47-52)
- **Status**: Documented but not changed
- **Issue**: `python` and `pip` are allowed prefixes, enabling arbitrary code execution
- **Recommendation**: Consider restricting to specific script paths

### 3. Unix Socket Authentication (daemon.py)
- **Status**: Added peer UID check
- **Issue**: Current implementation relies on Unix domain socket permissions
- **Recommendation**: Consider adding token-based authentication for additional security

## Code Quality Improvements Needed

### 1. Unused Imports (129 F401 violations)
- **Files**: Multiple files throughout codebase
- **Recommendation**: Run `autoflake --remove-all-unused-imports` to clean up

### 2. Line Length Violations (1343 E501 violations)
- **Files**: Multiple files throughout codebase
- **Recommendation**: Consider using `black` formatter with line length 100

### 3. Comparison Style (74 E712 violations)
- **Files**: Multiple files
- **Recommendation**: Replace `== False` with `is False` or `not cond`

## Privacy Enhancements Needed

### 1. Network Request Logging
- **Status**: Not implemented
- **Issue**: No logging of network requests for audit trail
- **Recommendation**: Add optional network request logging

### 2. Data Retention Policy
- **Status**: Not implemented
- **Issue**: No automatic cleanup of old session data
- **Recommendation**: Add configurable data retention settings

## Testing Gaps

### 1. Integration Tests
- **Status**: Missing
- **Issue**: No integration tests for daemon mode
- **Recommendation**: Add integration tests for daemon startup/shutdown

### 2. Security Tests
- **Status**: Partial
- **Issue**: Shell injection tests exist, but no tests for path traversal
- **Recommendation**: Add path traversal tests for filesystem operations

## Documentation Updates Needed

### 1. Security Guide
- **Status**: Referenced in README but may need updates
- **Issue**: Security guide should document V3 security improvements
- **Recommendation**: Update `docs/security.md` with V3 changes

### 2. Privacy Policy
- **Status**: Missing
- **Issue**: No explicit privacy policy document
- **Recommendation**: Add `PRIVACY.md` documenting data handling practices
