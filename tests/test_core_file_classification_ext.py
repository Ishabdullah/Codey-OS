"""WP2.1 group 14a-ext (Ish fork 1, 2026-10-17): ccos/plugins/** and bench/**
(any *.py, any depth) join the four core roots as HIGH_IMPACT.

Classification only (fork 3): no activation allowlist. Pure path tests
against a temporary CODE_DIR; no model, process kill or network.
"""

import pytest

from core import checkpoint, filesystem
from core.filesystem import Filesystem, FilesystemAccessError
from tools.file_tools import ACT, HIGH_IMPACT, classify_write_action


@pytest.fixture
def code_dir(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    monkeypatch.setattr(checkpoint, "CODE_DIR", root)
    monkeypatch.setattr(filesystem, "CODE_DIR", root)
    return root


@pytest.mark.parametrize(
    "rel",
    [
        "ccos/plugins/x.py",
        "ccos/plugins/coding/agent/agent.py",
        "ccos/plugins/a/b/c/d/new_plugin.py",
        "bench/gate.py",
        "bench/tasks/t01/hidden/test_x.py",
        "bench/a/b/c/d.py",
    ],
)
def test_nested_py_under_ext_roots_is_high(code_dir, rel):
    target = code_dir / rel
    assert checkpoint.is_core_file(str(target)) is True
    assert classify_write_action(str(target)) == HIGH_IMPACT


@pytest.mark.parametrize(
    "rel",
    [
        "ccos/plugins/coding/agent/manifest.json",
        "ccos/plugins/README.md",
        "ccos/plugins/a/run.sh",
        "ccos/plugins/a/x.pyc",
        "bench/scorecard.md",
        "bench/suite.lock",
        "bench/scorecard_history.jsonl",
        "bench/tasks/t01/task.yaml",
        # ccos outside plugins stays ACT
        "ccos/core/plugin_manager.py",
        "ccos/data/x.py",
        "ccos/tests/test_x.py",
        "ccos/x.py",
        # lookalikes
        "ccos/plugins_extra/x.py",
        "ccos/pluginsx.py",
        "benchmark/x.py",
        "bench.py",
        "x/bench/a.py",
        "x/ccos/plugins/a.py",
    ],
)
def test_non_py_and_non_ext_paths_unaffected(code_dir, rel):
    target = code_dir / rel
    assert checkpoint.is_core_file(str(target)) is False
    assert classify_write_action(str(target)) == ACT


def test_dotdot_and_symlink_into_ext_roots(code_dir, tmp_path):
    (code_dir / "ccos" / "plugins" / "p").mkdir(parents=True)
    assert checkpoint.is_core_file(
        str(code_dir / "ccos" / "plugins" / "p" / ".." / "q" / "x.py")
    )
    assert not checkpoint.is_core_file(
        str(code_dir / "ccos" / "plugins" / ".." / "core" / "x.py")
    )
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "link").symlink_to(code_dir / "ccos" / "plugins" / "p")
    assert checkpoint.is_core_file(str(ws / "link" / "x.py")) is True


def test_backup_scope_unchanged_by_ext_roots():
    assert checkpoint.CORE_PATTERNS == [
        "core/*.py",
        "tools/*.py",
        "utils/*.py",
        "prompts/*.py",
    ]


@pytest.fixture
def fs_factory(code_dir, tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        Filesystem, "_require_checkpoint", lambda self, path: calls.append(path)
    )
    ws = tmp_path / "ws"
    ws.mkdir()
    return (lambda allow: Filesystem(workspace=ws, allow_self_modification=allow)), calls


@pytest.mark.parametrize("rel", ["ccos/plugins/a/b.py", "bench/sub/x.py"])
def test_allow_self_modification_gate_and_checkpoint(fs_factory, code_dir, rel):
    make, calls = fs_factory
    target = code_dir / rel
    with pytest.raises(FilesystemAccessError, match="outside workspace"):
        make(False).write(str(target), "x = 1\n")
    assert not target.exists() and calls == []
    make(True).write(str(target), "x = 1\n")
    assert target.read_text() == "x = 1\n"
    assert calls == [target.resolve()]


def test_non_py_under_ext_root_skips_checkpoint(fs_factory, code_dir):
    make, calls = fs_factory
    make(True).write(str(code_dir / "ccos" / "plugins" / "a" / "m.json"), "{}")
    assert calls == []


@pytest.mark.parametrize(
    "rel",
    [
        "ccos/plugins/__wp21_14a_ext_probe/evil.py",
        "bench/__wp21_14a_ext_probe.py",
    ],
)
@pytest.mark.parametrize("tool", ["tool_write_file", "tool_append_file"])
def test_daemon_without_confirm_is_blocked_and_writes_nothing(
    tmp_path, monkeypatch, rel, tool
):
    """No confirmation channel (confirm_write False, allow_self_mod False)
    => HIGH_IMPACT is refused fail-closed before any write. Uses the REAL
    CODE_DIR with a non-existent probe path; the refusal must leave nothing
    on disk (asserted, and cleaned up defensively)."""
    from core.action_gateway import reset_action_gateway
    from tools import file_tools
    from utils import config
    from utils.config import CODE_DIR

    monkeypatch.setenv("CODEY_ACTION_GATEWAY_AUDIT", str(tmp_path / "audit.jsonl"))
    reset_action_gateway()
    monkeypatch.setitem(config.AGENT_CONFIG, "confirm_write", False)
    monkeypatch.setitem(config.AGENT_CONFIG, "allow_self_modification", False)
    target = CODE_DIR / rel
    assert not target.exists()
    try:
        out = getattr(file_tools, tool)(str(target), "x = 1\n")
        assert out.startswith("[BLOCKED]"), out
        assert not target.exists()
    finally:
        if target.exists():
            target.unlink()
        parent = target.parent
        if parent.name == "__wp21_14a_ext_probe" and parent.exists():
            parent.rmdir()
        reset_action_gateway()
