"""
Error Recovery Plugin — thin CCOS adapter over core/recovery.py.

core/recovery.py's StrategySwitcher classifies errors, picks fallback
strategies, and (via execute_strategy()) actually performs recovery
actions — installing a missing pip package, searching for a similarly
named file, creating a missing parent directory, checking for a missing
shell command, or isolating and re-running a failing pytest test. That
action-taking logic has no equivalent anywhere else in the codebase, and
is the reason this plugin exists.

core/recovery.py's StrategySwitcher also carries its own success-rate
tracking (record_error/get_success_rate/adapt_strategy), stored only in
an in-memory list on the global switcher instance — never persisted to
disk. core/strategy_tracker.py's StrategyTracker tracks the same concept
(per-strategy success rates) but is already the live path: it's imported
and used by core/learning.py, and persists through core/state.py's
state store. Wrapping StrategySwitcher's own tracking as CCOS
capabilities would stand up a second, competing, non-persisted tracking
system for something the codebase already tracks properly elsewhere.

Decision: this plugin wraps the unique recovery *actions*
(classify_error, get_fallback, execute_strategy) as-is, but backs
outcome tracking with StrategyTracker.record_attempt() rather than
StrategySwitcher.record_error(). record_outcome() below calls
core.strategy_tracker, not core.recovery — so a recovery attempt made
through this plugin feeds the same strategy-performance data that
core/learning.py already reads, instead of a second, disconnected
history. core/recovery.py itself is untouched; this is a plugin-layer
routing choice, not a change to StrategySwitcher's internals.
"""
from ccos.plugins._pathutil import ensure_repo_root_on_path

ensure_repo_root_on_path()

from dataclasses import asdict

from core.recovery import ErrorType, FallbackStrategy, get_switcher
from core.recovery import execute_strategy as _execute_strategy
from core.strategy_tracker import get_strategy_tracker


def recovery_classify_error(error_message: str) -> str:
    """Classify an error message. Returns the ErrorType value string."""
    return get_switcher().classify_error(error_message).value


def recovery_get_fallback(error_type: str = None, error_message: str = None):
    """
    Get the best fallback strategy for an error.

    Args:
        error_type: An ErrorType value string (e.g. "import_error"). Optional.
        error_message: Raw error text to classify if error_type isn't given.

    Returns:
        The fallback strategy as a dict, or None.
    """
    et = ErrorType(error_type) if error_type else None
    strategy = get_switcher().get_fallback(error_type=et, error_message=error_message)
    return asdict(strategy) if strategy else None


def recovery_execute_strategy(
    name: str,
    action: str,
    description: str = "",
    confidence: float = 0.5,
    error_message: str = "",
    tool_name: str = "",
    tool_args: dict = None,
    file_path: str = "",
):
    """
    Execute a recovery strategy (real action — may install packages, run
    shell commands, create directories, or run pytest; see core/recovery.py).

    Args:
        name, action, description, confidence: fields of a FallbackStrategy
            (typically taken from a prior recovery_get_fallback() result).
        error_message, tool_name, tool_args, file_path: recovery context.

    Returns:
        A result string describing what was done.
    """
    strategy = FallbackStrategy(
        name=name, description=description, action=action, confidence=confidence
    )
    context = {
        "error_message": error_message,
        "tool_name": tool_name,
        "tool_args": tool_args or {},
        "file_path": file_path,
    }
    return _execute_strategy(strategy, context)


def recovery_record_outcome(
    strategy: str,
    error_type: str,
    success: bool,
    duration: float = 0.0,
    context: dict = None,
):
    """
    Record a recovery attempt's outcome via the already-used, disk-persisted
    StrategyTracker (core/strategy_tracker.py) — not StrategySwitcher's own
    in-memory history. See module docstring for why.

    Returns:
        The recorded attempt as a dict.
    """
    record = get_strategy_tracker().record_attempt(
        strategy=strategy,
        error_type=error_type,
        success=success,
        duration=duration,
        context=context,
    )
    return record.to_dict()


def test() -> bool:
    """Plugin self-test — classify, get a fallback, and execute a safe action."""
    import shutil
    import tempfile
    from pathlib import Path

    assert recovery_classify_error("ModuleNotFoundError: No module named 'foo'") == "import_error"
    assert recovery_classify_error("FileNotFoundError: no such file or directory") == "file_not_found"

    fallback = recovery_get_fallback(error_message="No such file or directory: 'x.txt'")
    assert fallback is not None and fallback["action"] == "create_then_modify"

    tmp_dir = Path(tempfile.mkdtemp(prefix="recovery_selftest_"))
    try:
        target = tmp_dir / "nested" / "dir" / "file.txt"
        result = recovery_execute_strategy(
            name="create_parent_dirs",
            action="mkdir_then_write",
            description="Create parent directories first",
            confidence=0.8,
            file_path=str(target),
        )
        assert target.parent.is_dir(), f"Expected parent dir created, got: {result}"
        return True
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
