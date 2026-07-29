# New Issues Found During V3 Overhaul

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

## Found during Round 1 (C-1/H-1/H-4) fix task, 2026-07-29 — NOT fixed, logged only

### [NEW-1] A live, unowned 7B `llama-server` appeared twice this session, timing-correlated with `pytest tests/` runs — matches audit finding L-6, but the causal mechanism is UNCONFIRMED (correction below)
- **Confidence: downgraded from an earlier overclaim in this same file.**
  Originally logged as "pytest tests/ itself spawns" with Confirmed
  confidence — that was **too strong**. Corrected after a follow-up static
  investigation (see below): the temporal correlation is real and
  reproduced, but no code path has actually been found that explains it.
  Treat as **Suspected**, same as the audit's own original L-6 rating, not
  upgraded.
- **Evidence for the correlation:** Ran `python3 -m pytest tests/ -q`
  (253/253 pass, no failures) inside one single shell command that also
  ran `free -h; pgrep -af llama-server` immediately after — that combined
  command's output showed a full 7B `llama-server` on port 8080 running
  with `PPID 1` (reparented/orphaned), no PID file anywhere
  (`~/.codeyOS/codeyOS.pid` doesn't exist), no daemon running. Reproduced
  in an earlier separate run too (different PID). Both times the process
  outlived the pytest run and had to be killed manually
  (`kill -TERM -<pid>`, scoped to that PID's process group) to recover RAM
  — that part (kill discipline, RAM recovery) is solid and verified both
  times via `free -h` before/after.
- **Follow-up investigation performed (2026-07-29, same session, per Ish's
  request before attempting live C-1/H-4 verification):** targeted static
  search, no pytest re-run.
  - `grep -rn "llama-server\|LlamaServer\|subprocess\|Popen\|get_loader\|ensure_model" tests/*.py`
    → only one hit, a comment in `tests/test_hybrid_inference.py`'s
    docstring. No test file calls `get_loader()`, `ensure_model()`, or
    constructs a `LlamaServer`/starts a subprocess.
  - Read `tests/test_hybrid_inference.py` in full — it only constructs
    `ChatCompletionBackend()` instances and calls `check_health()`/
    `is_server_running()`/`get_stats()` (network-probe or pure-attribute
    checks), never `.infer()`. No spawn path there.
  - Checked the 4 files that import from `core.agent`
    (`test_agent_parsing.py`, `test_hallucination.py`,
    `test_orchestration.py`, `test_parse_tool_call.py`) — all import only
    pure-parsing functions (`extract_json`, `is_hallucination`,
    `parse_tool_call`), never `run_agent`, never anything that calls
    `infer()`.
  - `grep -n "^[a-zA-Z_].*get_loader()\|^[a-zA-Z_].*ensure_model()"` across
    all of `core/*.py` → no module-level (import-time) call to either.
  - No `pytest.ini`/`pyproject.toml`/`setup.cfg` exists in the repo, so
    there's no autouse fixture or plugin hook that could be triggering it
    that way either.
  - No `crontab`, no `~/.termux/boot/`, and `ps aux` (checked while no
    llama-server was running) showed nothing resembling a supervisor or
    auto-restart process.
  - **Net result: the grep-level investigation did not find a mechanism.**
    Either the real cause is something not covered by these searches (a
    deeper transitive import, a genuinely external process on the device
    unrelated to this repo, or something that only triggers under specific
    timing/state not present in a plain grep), or the two observations
    were coincidental co-occurrence rather than pytest-caused. Given the
    tight timing (both observations occurred within a single, uninterrupted
    shell command that only ran pytest + the check), coincidence is not a
    fully satisfying explanation either — this is genuinely unresolved, not
    ruled out.
- **Impact if real:** a device crash occurred during this same session,
  and RAM went from ~6.6 GB available to under 200 MB free with 6+ GB in
  swap without any deliberate model-load action. If pytest (or something
  co-occurring with it) is really the cause, it's a plausible contributor
  to this device's RAM/crash history — but that remains **plausible, not
  confirmed**, based on one session's evidence.
- **Suggested direction:** next time this is investigated, bisect rather
  than grep — run subsets of `tests/` (e.g. `pytest tests/ -k
  "not hybrid"` vs. individual files) with a `pgrep -af llama-server`
  check after each, to narrow which file/collection step correlates with
  the spawn, before assuming a fix target. Do this only as a dedicated,
  RAM-monitored task, not bundled into unrelated work — and not
  immediately before/after a live daemon verification cycle, since it
  already appears to interact badly with RAM pressure from live model
  tests.

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
