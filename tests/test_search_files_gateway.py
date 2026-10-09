"""Real temporary basename searches; bootstrap config/state before collection."""

import json
import os
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from core import action_gateway, agent
from core.action_gateway import READ, ActionGateway
from tools import shell_tools


@pytest.fixture
def gateway(tmp_path, monkeypatch):
    audit = tmp_path / "audit.jsonl"
    instance = ActionGateway(audit_file=audit)
    monkeypatch.setattr(action_gateway, "get_action_gateway", lambda: instance)
    monkeypatch.setattr(shell_tools, "get_action_gateway", lambda: instance)
    runner = Mock(side_effect=AssertionError("search must not spawn a subprocess"))
    monkeypatch.setattr(shell_tools.subprocess, "run", runner)
    return SimpleNamespace(instance=instance, audit=audit, runner=runner)


def record(gateway, outcome, reason="command executed"):
    rows = [json.loads(line) for line in gateway.audit.read_text().splitlines()]
    assert len(rows) == 1
    row = rows[0]
    assert isinstance(row.pop("ts"), float)
    assert row == {"authority": READ, "action": "shell_tools.search_files", "command": "recursive basename search", "outcome": outcome, "reason": reason}
    gateway.runner.assert_not_called()


@pytest.fixture
def tree(tmp_path):
    root = tmp_path / "search root"
    root.mkdir()
    (root / "nested.py").mkdir()
    for name in ["root.py", ".hidden.py", "Upper.PY", "name with spaces.py", "a1.txt", "a2.txt", "aX.txt", "back\\slash.txt"]:
        (root / name).write_text("unchanged")
    (root / "nested.py" / "deep.py").write_text("deep")
    return root


def test_recursive_absolute_root_files_dirs_hidden(gateway, tree):
    result = shell_tools.search_files("*.py", str(tree))
    assert set(result.splitlines()) == {str(tree / name) for name in ["root.py", ".hidden.py", "name with spaces.py", "nested.py", "nested.py/deep.py"]}
    assert all(os.path.isabs(line) for line in result.splitlines())
    record(gateway, "allowed")


@pytest.mark.parametrize(("pattern", "expected"), [("a?.txt", {"a1.txt", "a2.txt", "aX.txt"}), ("a[12].txt", {"a1.txt", "a2.txt"}), ("back\\slash.txt", {"back\\slash.txt"}), ("Upper.PY", {"Upper.PY"}), ("upper.py", set()), ("", set())])
def test_fnmatchcase_and_no_matches(gateway, tree, pattern, expected):
    result = shell_tools.search_files(pattern, str(tree))
    assert result == "(no matches)" if not expected else set(result.splitlines()) == {str(tree / name) for name in expected}
    record(gateway, "allowed")


def test_default_relative_paths_and_root_match(gateway, tree, monkeypatch):
    monkeypatch.chdir(tree)
    result = shell_tools.search_files("*")
    assert "." in result.splitlines()
    assert "./root.py" in result.splitlines() and "./nested.py/deep.py" in result.splitlines()
    record(gateway, "allowed")


def test_literal_relative_path_and_file_root(gateway, tree, monkeypatch):
    monkeypatch.chdir(tree.parent)
    assert shell_tools.search_files("root.py", "search root/root.py") == "search root/root.py"
    record(gateway, "allowed")


@pytest.mark.parametrize("name", ["-delete", "-exec", "(", "!"])
def test_command_looking_paths_and_patterns_are_literal(gateway, tmp_path, monkeypatch, name):
    monkeypatch.chdir(tmp_path)
    root = tmp_path / name
    root.mkdir()
    marker = root / "marker"
    marker.write_text("protected")
    assert shell_tools.search_files("marker", name) == f"{name}/marker"
    assert marker.read_text() == "protected"
    record(gateway, "allowed")


@pytest.mark.parametrize("pattern", ["-delete", "-exec helper ;", "$(helper)", "!"])
def test_command_looking_pattern_never_executes(gateway, tree, pattern):
    assert shell_tools.search_files(pattern, str(tree)) == "(no matches)"
    assert (tree / "root.py").read_text() == "unchanged"
    record(gateway, "allowed")


def test_symlink_entries_broken_links_and_loop_not_followed(gateway, tmp_path):
    root, outside = tmp_path / "root", tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (outside / "outside-only").write_text("protected")
    (root / "directory-link").symlink_to(outside, target_is_directory=True)
    (root / "loop").symlink_to(root, target_is_directory=True)
    (root / "broken").symlink_to(tmp_path / "missing")
    result = shell_tools.search_files("*", str(root))
    assert set(result.splitlines()) == {str(root), str(root / "directory-link"), str(root / "loop"), str(root / "broken")}
    record(gateway, "allowed")


@pytest.mark.parametrize("suffix", ["", "/", "///"])
def test_starting_symlink_not_followed_even_trailing_slashes(gateway, tmp_path, suffix):
    target = tmp_path / "target"
    target.mkdir()
    (target / "child").write_text("protected")
    link = tmp_path / "link"
    link.symlink_to(target, target_is_directory=True)
    assert shell_tools.search_files("link", str(link) + suffix) == str(link)
    record(gateway, "allowed")


def test_display_cap_exactly_fifty_nonblank_lines(gateway, tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    for index in range(70):
        (root / f"item{index}").touch()
    result = shell_tools.search_files("item*", str(root))
    lines = result.splitlines()
    assert len(lines) == 50 and len(set(lines)) == 50 and all(line.strip() for line in lines)
    record(gateway, "allowed")


class ObservedScandir:
    """Wrap a real iterator to inject a late error/deadline and observe closure."""

    def __init__(self, iterator, after_entries):
        self.iterator = iterator
        self.after_entries = after_entries
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.iterator.close()
        self.closed = True

    def __iter__(self):
        yield from self.iterator
        self.after_entries()


@pytest.mark.parametrize("failure", ["error", "timeout"])
def test_after_cap_failure_discards_matches_and_closes_iterator(gateway, tmp_path, monkeypatch, failure):
    root = tmp_path / "root"
    root.mkdir()
    for index in range(60):
        (root / f"item{index}").touch()
    original = os.scandir
    clock = [0]
    monkeypatch.setattr(shell_tools, "monotonic", lambda: clock[0])

    def after_entries():
        if failure == "error":
            raise OSError("private traversal details")
        clock[0] = 16

    observed = ObservedScandir(original(root), after_entries)
    monkeypatch.setattr(shell_tools.os, "scandir", lambda path: observed)
    reason = "Search failed" if failure == "error" else "Search timed out"
    assert shell_tools.search_files("item*", str(root)) == f"[ERROR] {reason}"
    assert observed.closed
    record(gateway, "failed", reason)


@pytest.mark.parametrize(("pattern", "path"), [(None, "."), (1, "."), ("*", None), ("*", 1), ("*", ""), ("*", "bad\0path"), ("bad\0pattern", ".")])
def test_invalid_arguments_fail_inside_gate(gateway, monkeypatch, pattern, path):
    lstat = Mock()
    monkeypatch.setattr(shell_tools.os, "lstat", lstat)
    assert shell_tools.search_files(pattern, path) == "[ERROR] Invalid search arguments"
    lstat.assert_not_called()
    record(gateway, "failed", "Invalid search arguments")


def test_missing_path_static_failure_no_query_in_audit(gateway, tmp_path):
    assert shell_tools.search_files("private-query", str(tmp_path / "private-missing")) == "[ERROR] Search path not found"
    record(gateway, "failed", "Search path not found")
    assert "private" not in gateway.audit.read_text()


@pytest.mark.parametrize("operation", ["lstat", "scandir"])
@pytest.mark.parametrize(("exception", "reason"), [(PermissionError("private"), "Search permission denied"), (OSError("private"), "Search failed"), (RuntimeError("private"), "Search failed")])
def test_filesystem_errors_normalized(gateway, tree, monkeypatch, operation, exception, reason):
    monkeypatch.setattr(shell_tools.os, operation, Mock(side_effect=exception))
    assert shell_tools.search_files("private-query", str(tree)) == f"[ERROR] {reason}"
    record(gateway, "failed", reason)
    assert str(tree) not in gateway.audit.read_text() and "private" not in gateway.audit.read_text()


def test_deadline_before_initial_filesystem_operation(gateway, monkeypatch):
    monkeypatch.setattr(shell_tools, "monotonic", Mock(side_effect=[0, 15]))
    lstat = Mock()
    monkeypatch.setattr(shell_tools.os, "lstat", lstat)
    assert shell_tools.search_files("*", ".") == "[ERROR] Search timed out"
    lstat.assert_not_called()
    record(gateway, "failed", "Search timed out")


def test_validation_and_filesystem_operations_follow_gate(gateway, tree, monkeypatch):
    inside = [False]
    original_gate = gateway.instance.gate_exec
    original_lstat, original_scandir = os.lstat, os.scandir

    def gate(**kwargs):
        assert kwargs["authority"] == READ and kwargs["confirm_available"] is False
        assert kwargs["action"] == "shell_tools.search_files" and kwargs["command"] == "recursive basename search"
        inside[0] = True
        return original_gate(**kwargs)

    def lstat(path):
        assert inside[0]
        return original_lstat(path)

    def scandir(path):
        assert inside[0]
        return original_scandir(path)

    monkeypatch.setattr(gateway.instance, "gate_exec", gate)
    monkeypatch.setattr(shell_tools.os, "lstat", lstat)
    monkeypatch.setattr(shell_tools.os, "scandir", scandir)
    assert str(tree / "root.py") in shell_tools.search_files("*.py", str(tree))
    record(gateway, "allowed")
    assert str(tree) not in gateway.audit.read_text() and "root.py" not in gateway.audit.read_text()


def test_unexpected_refusal_does_no_validation_or_search(gateway, monkeypatch):
    gate = Mock(return_value=SimpleNamespace(outcome="refused", reason="test refusal"))
    monkeypatch.setattr(gateway.instance, "gate_exec", gate)
    lstat = Mock()
    monkeypatch.setattr(shell_tools.os, "lstat", lstat)
    assert shell_tools.search_files(None, None) == "[BLOCKED] test refusal"
    lstat.assert_not_called()
    gate.assert_called_once()


def test_audit_sink_failure_preserves_results(gateway, tmp_path, tree, monkeypatch):
    blocker = tmp_path / "blocker"
    blocker.write_text("unchanged")
    monkeypatch.setattr(shell_tools, "get_action_gateway", lambda: ActionGateway(audit_file=blocker / "audit.jsonl"))
    assert shell_tools.search_files("root.py", str(tree)) == str(tree / "root.py")
    assert blocker.read_text() == "unchanged"


@pytest.mark.parametrize("caller", ["tools", "execute_tool"])
def test_real_agent_mapping(gateway, tree, monkeypatch, caller):
    import core.memory_v2 as memory_module

    log = Mock()
    monkeypatch.setattr(memory_module.memory, "log_action", log)
    monkeypatch.setattr(agent, "_get_learning", Mock(return_value=Mock()))
    monkeypatch.setattr(agent, "show_tool_generic", Mock())
    args = {"pattern": "root.py", "path": str(tree)}
    result = agent.TOOLS["search_files"](args) if caller == "tools" else agent.execute_tool({"name": "search_files", "args": args})
    assert result == str(tree / "root.py")
    log.assert_not_called()
    record(gateway, "allowed")
