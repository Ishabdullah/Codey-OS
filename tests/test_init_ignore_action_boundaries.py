"""WP2.1 slice 14g: /init CODEY.md (HIGH_IMPACT always), /ignore and the
dormant peer design write are mediated by the ActionGateway.

Real tmp files only; infer() is stubbed, no model/network/process control.
"""

import json

import pytest

import main
import utils.config as _cfg
from core import action_gateway, codeymd, filesystem

GENERATED = "GENERATED-MARKDOWN-SENTINEL"


@pytest.fixture
def env(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.chdir(ws)
    monkeypatch.setattr(_cfg, "WORKSPACE_ROOT", ws.resolve())
    filesystem.reset_filesystem()
    audit = tmp_path / "audit.jsonl"
    monkeypatch.setenv("CODEY_ACTION_GATEWAY_AUDIT", str(audit))
    action_gateway.reset_action_gateway()
    for v in ("CODEY_DAEMON_MODE", "CODEY_NON_INTERACTIVE"):
        monkeypatch.delenv(v, raising=False)
    calls = []

    def fake_infer(messages, stream=False):
        calls.append(messages)
        return GENERATED

    import core.inference_v2 as inf
    import core.project as proj

    monkeypatch.setattr(inf, "infer", fake_infer)
    monkeypatch.setattr(
        proj, "detect_project", lambda: {"type": "python", "cwd": str(ws), "context": ""}
    )
    monkeypatch.setattr(main, "info", lambda *a, **k: None)
    yield ws, audit, calls
    filesystem.reset_filesystem()
    action_gateway.reset_action_gateway()


def _rows(audit):
    if not audit.exists():
        return []
    return [json.loads(x) for x in audit.read_text().splitlines()]


def _tty(monkeypatch, answer):
    class FakeIn:
        def isatty(self):
            return True

    monkeypatch.setattr(main.sys, "stdin", FakeIn())
    prompts = []

    def fake_input(prompt=""):
        prompts.append(prompt)
        if isinstance(answer, BaseException):
            raise answer
        return answer

    monkeypatch.setattr("builtins.input", fake_input)
    return prompts


def _assert_no_leak(audit):
    text = audit.read_text()
    assert GENERATED not in text


def test_confirmed_init_writes_once(env, monkeypatch):
    ws, audit, calls = env
    prompts = _tty(monkeypatch, "y")
    main.run_init()
    assert (ws / "CODEY.md").read_text() == GENERATED
    assert len(calls) == 1 and len(prompts) == 1
    rows = _rows(audit)
    assert len(rows) == 1
    assert rows[0]["authority"] == "HIGH_IMPACT" and rows[0]["outcome"] == "allowed"
    assert rows[0]["action"] == "main.run_init_codeymd"
    _assert_no_leak(audit)
    assert str(ws) not in audit.read_text()


@pytest.mark.parametrize("answer", ["", "n", "no", EOFError(), KeyboardInterrupt()])
def test_declined_or_interrupted_init_refuses(env, monkeypatch, answer):
    ws, audit, calls = env
    _tty(monkeypatch, answer)
    main.run_init()
    assert not (ws / "CODEY.md").exists()
    assert calls == []  # nothing generated before approval
    rows = _rows(audit)
    assert len(rows) == 1 and rows[0]["outcome"] == "refused"
    assert rows[0]["authority"] == "HIGH_IMPACT"
    _assert_no_leak(audit)


def test_decline_leaves_existing_codeymd_bytes(env, monkeypatch):
    ws, audit, calls = env
    (ws / "CODEY.md").write_bytes(b"keep me")
    prompts = _tty(monkeypatch, "n")
    main.run_init()
    assert (ws / "CODEY.md").read_bytes() == b"keep me"
    assert "OVERWRITE" in prompts[0]
    assert _rows(audit)[-1]["outcome"] == "refused"


def test_confirmed_overwrite_replaces_existing(env, monkeypatch):
    ws, audit, calls = env
    (ws / "CODEY.md").write_text("old")
    _tty(monkeypatch, "yes")
    main.run_init()
    assert (ws / "CODEY.md").read_text() == GENERATED


@pytest.mark.parametrize("mode", ["yolo", "daemon", "noninteractive", "notty"])
def test_no_confirmation_path_refuses(env, monkeypatch, mode):
    ws, audit, calls = env
    _tty(monkeypatch, "y")  # a "y" must never be consulted
    yolo = False
    if mode == "yolo":
        yolo = True
    elif mode == "daemon":
        monkeypatch.setenv("CODEY_DAEMON_MODE", "1")
    elif mode == "noninteractive":
        monkeypatch.setenv("CODEY_NON_INTERACTIVE", "1")
    else:
        class NoTty:
            def isatty(self):
                return False

        monkeypatch.setattr(main.sys, "stdin", NoTty())
    main.run_init(yolo=yolo)
    assert not (ws / "CODEY.md").exists()
    assert calls == []
    rows = _rows(audit)
    assert len(rows) == 1 and rows[0]["outcome"] == "refused"
    assert "no confirmation path" in rows[0]["reason"]


def test_confirmation_none_and_callable(monkeypatch):
    assert main._init_confirmation(yolo=True) is None
    _tty(monkeypatch, "y")
    assert callable(main._init_confirmation())


def test_generation_failure_audits_fixed_string_and_writes_nothing(env, monkeypatch):
    ws, audit, calls = env
    import core.inference_v2 as inf

    monkeypatch.setattr(inf, "infer", lambda m, stream=False: "[ERROR] SECRET-DETAIL")
    _tty(monkeypatch, "y")
    main.run_init()
    assert not (ws / "CODEY.md").exists()
    rows = _rows(audit)
    assert rows[-1]["outcome"] == "failed"
    assert "SECRET-DETAIL" not in audit.read_text()


def test_infer_exception_text_not_audited(env, monkeypatch):
    ws, audit, calls = env
    import core.inference_v2 as inf

    def boom(m, stream=False):
        raise OSError("PRIVATE-EXC-TEXT")

    monkeypatch.setattr(inf, "infer", boom)
    _tty(monkeypatch, "y")
    main.run_init()
    assert "PRIVATE-EXC-TEXT" not in audit.read_text()
    assert _rows(audit)[-1]["outcome"] == "failed"


def test_write_outside_workspace_fails_without_file(env, monkeypatch, tmp_path):
    ws, audit, calls = env
    other = tmp_path / "other"
    other.mkdir()
    monkeypatch.chdir(other)  # cwd outside the Filesystem workspace
    _tty(monkeypatch, "y")
    main.run_init()
    assert not (other / "CODEY.md").exists()
    assert _rows(audit)[-1]["outcome"] == "failed"


def test_write_codeymd_uses_filesystem(env):
    ws, audit, calls = env
    path = codeymd.write_codeymd("x", filesystem=filesystem.Filesystem(workspace=ws))
    assert path == str(ws / "CODEY.md")
    other = codeymd.write_codeymd("x", directory="/nonexistent-outside-ws")
    assert other.startswith("[ERROR]")


# ---- /ignore ----------------------------------------------------------


def test_ignore_appends_via_gateway_act_row(env):
    ws, audit, calls = env
    handled, _ = main.handle_command("/ignore build/", [])
    assert handled
    assert (ws / ".codeyignore").read_text() == "\nbuild/"
    main.handle_command("/ignore dist/", [])
    assert (ws / ".codeyignore").read_text() == "\nbuild/\ndist/"
    rows = _rows(audit)
    assert [r["authority"] for r in rows] == ["ACT", "ACT"]
    assert all(r["action"] == "main.ignore_append" and r["outcome"] == "allowed" for r in rows)
    assert "build/" not in audit.read_text()


def test_ignore_outside_workspace_fails_no_file(env, monkeypatch, tmp_path):
    ws, audit, calls = env
    other = tmp_path / "other"
    other.mkdir()
    monkeypatch.chdir(other)
    main.handle_command("/ignore x", [])
    assert not (other / ".codeyignore").exists()
    assert _rows(audit)[-1]["outcome"] == "failed"


def test_ignore_git_metadata_denied(env):
    ws = env[0]
    (ws / ".git").mkdir()
    # .codeyignore itself is fine; a .git-rooted target is what Filesystem denies.
    fs = filesystem.Filesystem(workspace=ws)
    with pytest.raises(filesystem.FilesystemAccessError):
        fs.append(str(ws / ".git" / "config"), "x")


# ---- dormant peer design write ----------------------------------------


def test_peer_design_write_has_no_raw_open():
    import ast
    import pathlib

    src = pathlib.Path(main.__file__).parent.joinpath("core", "agent.py").read_text()
    tree = ast.parse(src)
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "open":
            for a in n.args[1:2]:
                assert not (isinstance(a, ast.Constant) and "w" in str(a.value)), n.lineno
    assert "_design_result = tool_write_file(_design_path, _output)" in src
