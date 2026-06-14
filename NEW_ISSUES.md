# New Issues Found During V3 Overhaul

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
