# Codey-V3 Overhaul TODO

## Phase 1: Rename Codey-V2 → Codey-V3
- [x] Rename directory: Codey-v2 → Codey-v3
- [x] Rename all "Codey-v2" strings in code to "Codey-V3"
- [x] Rename "codey-v2" CLI references to "codey-v3"
- [x] Update BANNER and version strings
- [x] Update .gitignore, README, CHANGELOG references
- [x] Rename "CODEY.md" references to keep consistent branding

## Phase 2: Critical Security Fixes
- [x] **CRITICAL**: Fix `tools/shell_tools.py` — replace `shell=True` with `shlex.split()` + allowlist
- [x] **HIGH**: Fix `core/peer_shell.py:360,500` — replace `os.system()` with `subprocess.run(list)`
- [x] **HIGH**: Fix `core/agent.py:47` — validate shell commands before dispatch
- [x] **MED**: Fix `core/task_executor.py:47-52` — tighten daemon shell allowlist
- [x] **MED**: Fix `core/peer_shell.py:344,492` — replace `tempfile.mktemp()` with `NamedTemporaryFile()`
- [x] **MED**: Fix `core/daemon.py:53-64` — add PID file locking with `fcntl.flock()`
- [x] **MED**: Fix `core/daemon.py:296-334` — add basic auth to Unix socket handler
- [x] **MED**: Fix `core/embeddings.py:238,258` — replace `pickle.loads()` with safe deserialization
- [x] **MED**: Fix `core/agent.py:863-865` — sanitize filenames from LLM output
- [x] **LOW**: Fix `tools/shell_tools.py:7-28` — improve dangerous command detection
- [x] **LOW**: Fix `core/filesystem.py:155` — add file size limits
- [x] **LOW**: Fix `core/githelper.py:135` — validate branch names against flag injection

## Phase 3: Code Quality Fixes
- [x] Replace all bare `except:` with specific exception types (18 occurrences)
- [ ] Fix `== False` comparisons → `is False` or `not cond` (74 occurrences)
- [ ] Remove unused imports and variables (129 F401, 15 F841, 6 F811)
- [ ] Fix f-strings missing placeholders (15 F541)
- [x] Fix `global last_tps` unused in `core/inference_v2.py`
- [ ] Fix spacing/style issues (E302, E501 line length)

## Phase 4: Privacy & Production Hardening
- [x] Audit and document all network connections (ensure no telemetry)
- [x] Add privacy disclaimer in startup banner
- [x] Ensure all data stays local (no cloud calls by default)
- [ ] Add proper logging (replace print statements in critical paths)
- [ ] Add input validation at system boundaries
- [ ] Add graceful error handling throughout
- [x] Verify no secrets/credentials are hardcoded

## Phase 5: Testing & Documentation
- [x] Ensure existing tests pass after changes (253 passed, 0 failures)
- [x] Update test imports for renamed modules
- [x] Document security model in README
- [x] Update CHANGELOG for V3
- [x] Create PRIVACY.md

## Phase 6: Post-Overhaul Tasks
- [x] Fix hallucination detection (20/20 tests passing)
- [x] Tighten daemon shell allowlist
- [x] Add path traversal tests (10/10 passing)
- [x] Run autoflake (remove unused imports)
- [x] Run black (format code)
- [x] Run isort (sort imports)
- [x] Fix patch test error format

## New Issues Found During Work
- [x] Documented in NEW_ISSUES.md
