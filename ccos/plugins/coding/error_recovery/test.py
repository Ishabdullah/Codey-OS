#!/usr/bin/env python3
"""Test for error_recovery plugin."""
import importlib.util
import shutil
import tempfile
from pathlib import Path

# _pathutil.py lives at ccos/plugins/_pathutil.py, two levels above this
# plugin's directory (test.py -> error_recovery/ -> coding/ -> plugins/).
# Loaded by file path since the ccos package isn't importable yet.
_pathutil_path = Path(__file__).resolve().parent.parent.parent / "_pathutil.py"
_spec = importlib.util.spec_from_file_location("_pathutil", _pathutil_path)
_pathutil = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_pathutil)
_pathutil.ensure_repo_root_on_path()

from ccos.plugins.coding.error_recovery.error_recovery import (
    recovery_classify_error,
    recovery_execute_strategy,
    recovery_get_fallback,
    recovery_record_outcome,
    test,
)


def test_classify_error_real_messages():
    assert recovery_classify_error("ModuleNotFoundError: No module named 'requests'") == "import_error"
    assert recovery_classify_error("ImportError: cannot import name 'foo'") == "import_error"
    assert recovery_classify_error("FileNotFoundError: [Errno 2] No such file or directory: 'x.txt'") == "file_not_found"
    # Note: classify_error() checks "not found" before "command not found",
    # so this real-world shell message classifies as file_not_found, not
    # shell_error — matches core/recovery.py's actual classification order.
    assert recovery_classify_error("bash: frobnicate: command not found") == "file_not_found"
    assert recovery_classify_error("PermissionError: [Errno 13] Permission denied") == "permission_error"
    assert recovery_classify_error("SyntaxError: invalid syntax") == "syntax_error"
    assert recovery_classify_error("something totally unrelated happened") == "unknown"
    print("[PASS] recovery_classify_error() classifies real error message strings")


def test_get_fallback_for_classified_error():
    fallback = recovery_get_fallback(error_message="ModuleNotFoundError: No module named 'requests'")
    assert fallback is not None
    assert fallback["action"] == "pip_install"
    assert fallback["name"] == "install_package"
    print(f"[PASS] recovery_get_fallback() for import_error: {fallback}")

    by_type = recovery_get_fallback(error_type="file_not_found")
    assert by_type is not None
    assert by_type["action"] == "create_then_modify"
    print(f"[PASS] recovery_get_fallback() by explicit error_type: {by_type}")


def test_execute_strategy_mkdir_then_write():
    """Safe, reversible case: create a missing parent directory."""
    tmp_dir = Path(tempfile.mkdtemp(prefix="error_recovery_plugin_test_"))
    try:
        target = tmp_dir / "missing" / "nested" / "file.txt"
        assert not target.parent.exists(), "Precondition: nested dir should not exist yet"

        result = recovery_execute_strategy(
            name="create_parent_dirs",
            action="mkdir_then_write",
            description="Create parent directories first",
            confidence=0.8,
            file_path=str(target),
        )

        assert target.parent.is_dir(), f"Expected parent dir created, got result: {result}"
        print(f"[PASS] recovery_execute_strategy() created missing parent dir: {result}")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_record_outcome_routes_through_strategy_tracker():
    """
    Confirms recovery_record_outcome() writes into StrategyTracker (the
    already-used, disk-persisted tracker), not StrategySwitcher's own
    in-memory history. Uses a distinct, made-up strategy name (not a real
    built-in like "create_parent_dirs") so this test doesn't skew the
    live, shared stats for a real strategy — and resets it afterward.
    """
    from core.strategy_tracker import get_strategy_tracker

    test_strategy = "ccos_plugin_test_strategy"
    tracker = get_strategy_tracker()
    try:
        record = recovery_record_outcome(
            strategy=test_strategy,
            error_type="file_not_found",
            success=True,
            duration=0.01,
        )
        assert record["strategy"] == test_strategy
        assert record["success"] is True

        stats = tracker.get_statistics()
        assert stats["total_attempts"] >= 1
        print(f"[PASS] recovery_record_outcome() persisted via StrategyTracker: {record}")
    finally:
        tracker.reset_strategy(test_strategy)


def test_self_test():
    result = test()
    assert result is True
    print("[PASS] Self-test passed")


if __name__ == "__main__":
    test_classify_error_real_messages()
    test_get_fallback_for_classified_error()
    test_execute_strategy_mkdir_then_write()
    test_record_outcome_routes_through_strategy_tracker()
    test_self_test()
    print("\nAll error_recovery tests passed!")
