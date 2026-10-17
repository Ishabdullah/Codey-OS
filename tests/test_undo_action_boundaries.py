"""WP2.1 slice 14b: /undo restore mediated by the ActionGateway.

Real tmp files only; no model, network or process control. create_checkpoint
is replaced with a recorder so no real checkpoint is taken.
"""

import json

import pytest

from core import checkpoint, filehistory, filesystem
from core.filesystem import Filesystem

SECRET = "SECRET-PAYLOAD-TOKEN"


@pytest.fixture
def env(tmp_path, monkeypatch):
    code = tmp_path / "repo"
    ws = tmp_path / "ws"
    (code / "core").mkdir(parents=True)
    ws.mkdir()
    monkeypatch.setattr(checkpoint, "CODE_DIR", code)
    monkeypatch.setattr(filesystem, "CODE_DIR", code)
    audit = tmp_path / "audit.jsonl"
    monkeypatch.setenv("CODEY_ACTION_GATEWAY_AUDIT", str(audit))
    from core import action_gateway

    action_gateway.reset_action_gateway()
    checkpoints = []
    monkeypatch.setattr(
        filesystem, "create_checkpoint", lambda **kw: checkpoints.append(kw)
    )
    filehistory.clear_history()
    fs = Filesystem(workspace=ws, allow_self_modification=True)
    yield code, ws, audit, checkpoints, fs
    filehistory.clear_history()
    action_gateway.reset_action_gateway()


def _rows(audit):
    if not audit.exists():
        return []
    return [json.loads(x) for x in audit.read_text().splitlines()]


def _edit(path, old, new):
    path.write_text(old)
    assert filehistory.snapshot(str(path))
    path.write_text(new)


def test_ordinary_file_restore_acts_without_confirm(env):
    code, ws, audit, cps, fs = env
    f = ws / "a.txt"
    _edit(f, "old", "new")
    msg = filehistory.undo(str(f), filesystem=fs)
    assert msg.startswith("Restored")
    assert f.read_text() == "old"
    rows = _rows(audit)
    assert len(rows) == 1
    assert rows[0]["authority"] == "ACT" and rows[0]["outcome"] == "allowed"
    assert cps == []
    # pre-undo entry kept for redo/diff, no double snapshot
    assert [c for _, c in filehistory.get_versions(str(f))] == ["new"]


def test_core_file_refused_without_confirm_and_audited(env):
    code, ws, audit, cps, fs = env
    f = code / "core" / "x.py"
    _edit(f, "old", "new")
    msg = filehistory.undo(str(f), confirm=None, filesystem=fs)
    assert msg.startswith("[ERROR]")
    assert f.read_text() == "new"
    assert len(filehistory.get_versions(str(f))) == 1
    assert cps == []
    rows = _rows(audit)
    assert rows[-1]["authority"] == "HIGH_IMPACT" and rows[-1]["outcome"] == "refused"


@pytest.mark.parametrize("answer", ["decline", "raise", "eof", "truthy"])
def test_core_file_confirm_not_approving(env, answer):
    code, ws, audit, cps, fs = env
    f = code / "core" / "deep" / "x.py"
    f.parent.mkdir()
    _edit(f, "old", "new")

    def confirm():
        if answer == "raise":
            raise RuntimeError("boom")
        if answer == "eof":
            raise EOFError
        return False if answer == "decline" else "yes"  # non-True is not approval

    msg = filehistory.undo(str(f), confirm=confirm, filesystem=fs)
    assert msg.startswith("[ERROR]")
    assert f.read_text() == "new"
    assert len(filehistory.get_versions(str(f))) == 1
    assert cps == []
    assert _rows(audit)[-1]["outcome"] == "refused"


def test_core_file_allowed_with_real_confirm_and_checkpoint(env):
    code, ws, audit, cps, fs = env
    f = code / "core" / "x.py"
    _edit(f, "old", "new")
    msg = filehistory.undo(str(f), confirm=lambda: True, filesystem=fs)
    assert msg.startswith("Restored")
    assert f.read_text() == "old"
    assert len(cps) == 1
    row = _rows(audit)[-1]
    assert row["authority"] == "HIGH_IMPACT" and row["outcome"] == "allowed"


def test_checkpoint_failure_keeps_file_and_history(env, monkeypatch):
    code, ws, audit, cps, fs = env
    f = code / "core" / "x.py"
    _edit(f, "old", "new")

    def bad(**kw):
        raise OSError("no space")

    monkeypatch.setattr(filesystem, "create_checkpoint", bad)
    msg = filehistory.undo(str(f), confirm=lambda: True, filesystem=fs)
    assert msg.startswith("[ERROR]")
    assert f.read_text() == "new"
    assert [c for _, c in filehistory.get_versions(str(f))] == ["old"]
    assert _rows(audit)[-1]["outcome"] == "failed"


def test_outside_workspace_path_refused_history_intact(env, tmp_path):
    code, ws, audit, cps, fs = env
    outside = tmp_path / "elsewhere" / "o.txt"
    outside.parent.mkdir()
    _edit(outside, "old", "new")  # snapshotted before a simulated /cwd change
    msg = filehistory.undo(str(outside), filesystem=fs)
    assert msg.startswith("[ERROR]") and "outside workspace" in msg
    assert outside.read_text() == "new"
    assert len(filehistory.get_versions(str(outside))) == 1
    assert _rows(audit)[-1]["outcome"] == "failed"


def test_git_metadata_target_refused(env):
    code, ws, audit, cps, fs = env
    f = ws / ".git" / "config"
    f.parent.mkdir()
    _edit(f, "old", "new")
    msg = filehistory.undo(str(f), filesystem=fs)
    assert msg.startswith("[ERROR]") and "Git metadata" in msg
    assert f.read_text() == "new"
    assert len(filehistory.get_versions(str(f))) == 1


def test_write_failure_keeps_history(env, monkeypatch):
    code, ws, audit, cps, fs = env
    f = ws / "a.txt"
    _edit(f, "old", "new")

    def bad(self, *a, **k):
        raise PermissionError("denied")

    monkeypatch.setattr(type(f), "write_text", bad)
    msg = filehistory.undo(str(f), filesystem=fs)
    monkeypatch.undo()
    assert msg.startswith("[ERROR]")
    assert [c for _, c in filehistory.get_versions(str(f))] == ["old"]


def test_no_history_never_reaches_gateway(env):
    code, ws, audit, cps, fs = env
    msg = filehistory.undo(str(ws / "none.txt"), filesystem=fs)
    assert msg.startswith("[ERROR] No history")
    assert _rows(audit) == []


def test_audit_has_no_payload_or_path(env):
    code, ws, audit, cps, fs = env
    f = ws / "a.txt"
    _edit(f, SECRET + "-old", SECRET + "-new")
    filehistory.undo(str(f), filesystem=fs)
    g = code / "core" / "x.py"
    _edit(g, SECRET + "-old", SECRET + "-new")
    filehistory.undo(str(g), confirm=None, filesystem=fs)
    text = audit.read_text()
    assert SECRET not in text
    assert str(ws) not in text and "a.txt" not in text
    for row in _rows(audit):
        assert row["action"] == "filehistory.undo" and row["command"] == "undo restore"


def _assert_audit_clean(audit, *needles):
    text = audit.read_text()
    for n in needles:
        assert n not in text
    assert SECRET not in text and "/data/" not in text and "tmp" not in text.lower()
    for row in _rows(audit):
        assert row["action"] == "filehistory.undo" and row["command"] == "undo restore"


def test_failed_rows_have_no_path_or_payload(env, tmp_path):
    code, ws, audit, _cps, fs = env
    # Local MonkeyPatch contexts: monkeypatch.undo() would also revert the
    # fixture's audit-path env var and drop later rows, and a failed assert
    # inside a context still unwinds the patch.
    # symlink pointing outside the workspace
    outside = tmp_path / "elsewhere" / "target-secret.txt"
    outside.parent.mkdir()
    outside.write_text("x")
    link = ws / "linkname.txt"
    link.symlink_to(outside)
    filehistory._history[str(link.resolve())] = [("00:00:00", SECRET + "-old")]
    msg = filehistory.undo(str(link), filesystem=fs)
    assert msg.startswith("[ERROR]")
    # .git target
    g = ws / ".git" / "config"
    g.parent.mkdir()
    _edit(g, SECRET + "-old", SECRET + "-new")
    assert filehistory.undo(str(g), filesystem=fs).startswith("[ERROR]")
    # checkpoint failure
    c = code / "core" / "cpname.py"
    _edit(c, SECRET + "-old", SECRET + "-new")

    def bad(**kw):
        raise OSError(f"no space {c}")

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(filesystem, "create_checkpoint", bad)
        assert filehistory.undo(str(c), confirm=lambda: True, filesystem=fs).startswith("[ERROR]")
    # write_text failure
    w = ws / "wname.txt"
    _edit(w, SECRET + "-old", SECRET + "-new")

    def badw(self, *a, **k):
        raise PermissionError(f"denied {self}")

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(type(w), "write_text", badw)
        assert filehistory.undo(str(w), filesystem=fs).startswith("[ERROR]")
    # read_text failure (the pre-restore snapshot read)
    r = ws / "rname.txt"
    _edit(r, SECRET + "-old", SECRET + "-new")

    def badr(self, *a, **k):
        raise PermissionError(f"[Errno 13] Permission denied: '{self}'")

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(type(r), "read_text", badr)
        msg = filehistory.undo(str(r), filesystem=fs)
    assert msg.startswith("[ERROR]")
    assert [c2 for _, c2 in filehistory.get_versions(str(r))] == [SECRET + "-old"]
    # read_text failure because the target is a directory
    d = ws / "dname"
    d.mkdir()
    filehistory._history[str(d.resolve())] = [("00:00:00", SECRET + "-old")]
    msg = filehistory.undo(str(d), filesystem=fs)
    assert msg.startswith("[ERROR]")
    assert [c2 for _, c2 in filehistory.get_versions(str(d))] == [SECRET + "-old"]
    rows = _rows(audit)
    assert len(rows) == 6 and all(r_["outcome"] == "failed" for r_ in rows)
    assert all(r_["reason"] == "restore failed" for r_ in rows)
    _assert_audit_clean(
        audit,
        str(ws),
        str(tmp_path),
        "linkname",
        "target-secret",
        ".git",
        "cpname",
        "wname",
        "rname",
        "dname",
        "Permission denied",
    )


def test_main_undo_call_passes_no_confirm_under_yolo(monkeypatch):
    import main

    captured = {}

    def fake_undo(path, confirm=None, filesystem=None):
        captured["confirm"] = confirm
        return "ok"

    monkeypatch.setattr("core.filehistory.undo", fake_undo)
    main.handle_command("/undo x", [], yolo=True)
    assert "confirm" in captured and captured["confirm"] is None


def test_main_confirm_adapter_fails_closed(monkeypatch):
    import main

    assert main._undo_confirmation(yolo=True) is None
    monkeypatch.setenv("CODEY_DAEMON_MODE", "1")
    assert main._undo_confirmation() is None
    monkeypatch.delenv("CODEY_DAEMON_MODE")
    monkeypatch.setenv("CODEY_NON_INTERACTIVE", "1")
    assert main._undo_confirmation() is None
    monkeypatch.delenv("CODEY_NON_INTERACTIVE")
    monkeypatch.setattr("sys.stdin.isatty", lambda: False, raising=False)
    assert main._undo_confirmation() is None
