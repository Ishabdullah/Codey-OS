"""G15j Unit A: optional `confirm=` callback on gate_write / gate_append."""

import json
from unittest.mock import Mock

import pytest

from core.action_gateway import ACT, HIGH_IMPACT, READ, ActionGateway
from core.filesystem import FilesystemAccessError

DECLINED = "Human confirmation declined; {} not attempted."
INTERRUPTED = "Human confirmation unavailable or interrupted; {} not attempted."
FAILURE = "Human confirmation unavailable due to callback failure; {} not attempted."
NO_PATH = ("HIGH_IMPACT action with no confirmation path available; "
           "failing closed per policy (not attempted).")

KINDS = ["write", "append"]


class FakeFS:
    def __init__(self, raises=None):
        self.calls = []
        self.raises = raises

    def write(self, path, content):
        self.calls.append(("write", path, content))
        if self.raises:
            raise self.raises
        return f"Written {path}"

    def append(self, path, content):
        self.calls.append(("append", path, content))
        if self.raises:
            raise self.raises
        return f"Appended {path}"


def _gate(kind, gw, fs, **kw):
    fn = gw.gate_write if kind == "write" else gw.gate_append
    kw.setdefault("path", "p.txt")
    return fn(action="t.act", content="body", filesystem=fs, **kw)


def _rows(audit):
    if not audit.exists():
        return []
    rows = [json.loads(line) for line in audit.read_text().splitlines()]
    for r in rows:
        assert isinstance(r.pop("ts"), float)
    return rows


@pytest.fixture
def audit(tmp_path):
    return tmp_path / "audit.jsonl"


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize(
    ("answer", "exc", "reason"),
    [
        (False, None, DECLINED),
        (None, None, DECLINED),
        ("yes", None, DECLINED),
        (1, None, DECLINED),
        ([1], None, DECLINED),
        (None, EOFError(), INTERRUPTED),
        (None, KeyboardInterrupt(), INTERRUPTED),
        (None, RuntimeError("private input"), FAILURE),
    ],
)
def test_non_true_refuses_without_filesystem(kind, answer, exc, reason, audit):
    fs = FakeFS()
    cb = Mock(return_value=answer, side_effect=exc)
    d = _gate(kind, ActionGateway(audit_file=audit), fs,
              authority=HIGH_IMPACT, confirm_available=True, confirm=cb)
    assert d.outcome == "refused" and not d.allowed
    assert d.reason == reason.format(kind)
    assert d.detail == {"action": "t.act", "path": "p.txt"}
    cb.assert_called_once_with()
    assert fs.calls == []
    assert _rows(audit) == [{
        "authority": HIGH_IMPACT, "action": "t.act", "path": "p.txt",
        "outcome": "refused", "reason": reason.format(kind),
    }]
    assert "private" not in audit.read_text()


@pytest.mark.parametrize("kind", KINDS)
def test_true_approves_once(kind, audit):
    fs = FakeFS()
    cb = Mock(return_value=True)
    d = _gate(kind, ActionGateway(audit_file=audit), fs,
              authority=HIGH_IMPACT, confirm_available=True, confirm=cb)
    assert d.allowed
    cb.assert_called_once_with()
    assert fs.calls == [(kind, "p.txt", "body")]
    rows = _rows(audit)
    assert [r["outcome"] for r in rows] == ["allowed"]
    assert set(rows[0]) == {"authority", "action", "path", "outcome", "reason"}


@pytest.mark.parametrize("kind", KINDS)
def test_approved_then_filesystem_failure_is_failed_row(kind, audit):
    fs = FakeFS(raises=FilesystemAccessError("Access denied: x"))
    cb = Mock(return_value=True)
    d = _gate(kind, ActionGateway(audit_file=audit), fs,
              authority=HIGH_IMPACT, confirm_available=True, confirm=cb)
    assert d.outcome == "failed"
    cb.assert_called_once_with()
    assert [r["outcome"] for r in _rows(audit)] == ["failed"]


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("with_cb", [False, True])
def test_unavailable_path_fails_closed_never_calls_callback(kind, with_cb, audit):
    fs = FakeFS()
    cb = Mock(return_value=True) if with_cb else None
    d = _gate(kind, ActionGateway(audit_file=audit), fs,
              authority=HIGH_IMPACT, confirm_available=False, confirm=cb)
    assert d.outcome == "refused" and d.reason == NO_PATH
    if cb:
        cb.assert_not_called()
    assert fs.calls == []
    assert [r["outcome"] for r in _rows(audit)] == ["refused"]


@pytest.mark.parametrize("kind", KINDS)
def test_callback_free_boolean_convention_unchanged(kind, audit):
    fs = FakeFS()
    d = _gate(kind, ActionGateway(audit_file=audit), fs,
              authority=HIGH_IMPACT, confirm_available=True)
    assert d.allowed and len(fs.calls) == 1


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("authority", [READ, ACT])
@pytest.mark.parametrize("available", [False, True])
def test_read_act_never_call_callback(kind, authority, available, audit):
    fs = FakeFS()
    cb = Mock(side_effect=AssertionError("must not be called"))
    d = _gate(kind, ActionGateway(audit_file=audit), fs,
              authority=authority, confirm_available=available, confirm=cb)
    assert d.allowed
    cb.assert_not_called()
    assert len(fs.calls) == 1


@pytest.mark.parametrize("kind", KINDS)
def test_unknown_authority_raises_before_callback(kind, audit):
    cb = Mock()
    with pytest.raises(ValueError):
        _gate(kind, ActionGateway(audit_file=audit), FakeFS(),
              authority="BOGUS", confirm_available=True, confirm=cb)
    cb.assert_not_called()


@pytest.mark.parametrize("kind", KINDS)
def test_system_exit_not_swallowed(kind, audit):
    fs = FakeFS()
    with pytest.raises(SystemExit):
        _gate(kind, ActionGateway(audit_file=audit), fs,
              authority=HIGH_IMPACT, confirm_available=True,
              confirm=Mock(side_effect=SystemExit(3)))
    assert fs.calls == []


@pytest.mark.parametrize("kind", KINDS)
def test_real_filesystem_deny_still_fails_with_callback_approved(kind, tmp_path, audit):
    """DENY/validation failures stay Filesystem's job: approval cannot override."""
    from core.filesystem import Filesystem

    fs = Filesystem(workspace=str(tmp_path))
    cb = Mock(return_value=True)
    d = _gate(kind, ActionGateway(audit_file=audit), fs, path="/etc/passwd_g15j",
              authority=HIGH_IMPACT, confirm_available=True, confirm=cb)
    assert d.outcome == "failed"
    assert [r["outcome"] for r in _rows(audit)] == ["failed"]


def test_gate_exec_strings_pinned_byte_identical(audit):
    """Literals captured from HEAD 50f9aa2; gate_exec must not change."""
    cases = [
        (False, None, "Human confirmation declined; command not attempted."),
        (None, EOFError(), "Human confirmation unavailable or interrupted; command not attempted."),
        (None, KeyboardInterrupt(), "Human confirmation unavailable or interrupted; command not attempted."),
        (None, RuntimeError("x"), "Human confirmation unavailable due to callback failure; command not attempted."),
    ]
    for answer, exc, expected in cases:
        d = ActionGateway(audit_file=audit).gate_exec(
            authority=HIGH_IMPACT, action="a", command="c", confirm_available=True,
            execute=Mock(), confirm=Mock(return_value=answer, side_effect=exc))
        assert d.reason == expected
    d = ActionGateway(audit_file=audit).gate_exec(
        authority=HIGH_IMPACT, action="a", command="c", confirm_available=False,
        execute=Mock())
    assert d.reason == ("HIGH_IMPACT command with no confirmation path available; "
                        "failing closed per policy (not attempted).")
