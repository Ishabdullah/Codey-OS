"""
WP2.1 slice 14e (NEW-977, Ish fork 2, 2026-10-17): LoRA adopt and rollback are
HIGH_IMPACT and need a real per-attempt confirmation on /dev/tty, owned by
core/lora_import.py (so the documented
`python3 -c "...rollback_adoption(...)"` recovery path can still approve).
`--lora-force-adopt` only bypasses the benchmark gate; it is not the human act.

Hermetic: fake loader (core.loader_v2.get_loader), tiny tmp files, a recording
registry-free swap where needed, pty-backed fake terminals, and guards that
fail the test on any os.kill / subprocess / network use. The real /dev/tty is
never opened (a nonexistent path or a pty stands in for it).
"""
import json
import os
import pty
import signal
import socket
import subprocess
from unittest.mock import MagicMock

import pytest

import core.loader_v2 as lv
import core.lora_import as li
import core.state as state_module
import utils.config as cfg
from core.action_gateway import reset_action_gateway
from core.state import StateStore

# Captured at import (collection) time, before the conftest autouse fixture
# replaces it with an always-approving stand-in.
_REAL_CONFIRM = li._confirm_on_tty


class _Gate:
    def __init__(self, promote, reasons=None):
        self.promote = promote
        self.reasons = reasons or []
        self.stats = {}


class _FakeLoader:
    def __init__(self, events):
        self.events = events

    def unload(self):
        self.events.append("loader.unload")

    def load_primary(self):
        self.events.append("loader.load_primary")
        return True


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    # Real tty adapter under test, not the conftest approving stand-in.
    monkeypatch.setattr(li, "_confirm_on_tty", _REAL_CONFIRM)
    # Default: no terminal at all. Individual tests install a pty.
    monkeypatch.setattr(li, "_TTY_PATH", str(tmp_path / "no-such-tty"))

    audit = tmp_path / "audit.jsonl"
    monkeypatch.setenv("CODEY_ACTION_GATEWAY_AUDIT", str(audit))
    reset_action_gateway()

    # Guards: nothing in these tests may signal, spawn or touch the network.
    def _forbid(name):
        def _f(*a, **k):
            raise AssertionError(f"forbidden call in 14e test: {name}")

        return _f

    monkeypatch.setattr(os, "kill", _forbid("os.kill"))
    monkeypatch.setattr(subprocess, "Popen", _forbid("subprocess.Popen"))
    monkeypatch.setattr(subprocess, "run", _forbid("subprocess.run"))
    monkeypatch.setattr(socket.socket, "connect", _forbid("socket.connect"))

    store = StateStore(db_path=tmp_path / "state.db")
    monkeypatch.setattr(state_module, "_state_store", store)
    import core.model_registry as reg

    reg._extend_state_schema()

    events = []
    loader = _FakeLoader(events)
    monkeypatch.setattr(lv, "get_loader", lambda: loader)

    base = tmp_path / "models" / "base.gguf"
    base.parent.mkdir(parents=True)
    base.write_bytes(b"BASE-WEIGHTS")
    orig_model, orig_planner = cfg.MODEL_PATH, cfg.PLANNER_MODEL_PATH
    cfg.MODEL_PATH = base
    cfg.PLANNER_MODEL_PATH = base

    # Count copies (only tmp paths are ever involved).
    import shutil

    real_copy2 = shutil.copy2

    def _copy2(src, dst, **k):
        events.append("copy2")
        return real_copy2(src, dst, **k)

    monkeypatch.setattr(li.shutil, "copy2", _copy2)

    # Alarm so a bug can never hang the suite on a terminal read.
    signal.signal(signal.SIGALRM, lambda *a: (_ for _ in ()).throw(TimeoutError("tty read hung")))
    signal.alarm(30)
    yield {"audit": audit, "events": events, "base": base, "reg": reg, "tmp": tmp_path}
    signal.alarm(0)
    store.close()
    cfg.MODEL_PATH, cfg.PLANNER_MODEL_PATH = orig_model, orig_planner
    reset_action_gateway()


def _adapter(tmp_path):
    d = tmp_path / "adapter"
    d.mkdir()
    (d / "adapter_config.json").write_text(json.dumps({"r": 8, "target_modules": ["q_proj", "v_proj"]}))
    (d / "adapter_model.safetensors").write_bytes(b"fake-lora")
    (d / "merged.gguf").write_bytes(b"MERGED")
    return d


class _Pty:
    """A pty standing in for /dev/tty; `master` is the human's side.

    The human answers only AFTER the prompt text appears on the terminal (a
    helper thread watches the master), because the adapter flushes pending
    input before prompting. `stale` is typeahead written before any prompt.
    Echo is disabled so the first bytes seen are the prompt itself."""

    def __init__(self, monkeypatch, answer: bytes, stale: bytes = b""):
        import termios
        import threading

        self.master, self.slave = pty.openpty()
        self.opened = 0
        attrs = termios.tcgetattr(self.slave)
        attrs[3] &= ~termios.ECHO
        termios.tcsetattr(self.slave, termios.TCSANOW, attrs)
        if stale:
            os.write(self.master, stale)
        self._answer = answer
        self._seen = b""
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._human, daemon=True)
        self._thread.start()

        def _open():
            self.opened += 1
            return os.dup(self.slave)

        monkeypatch.setattr(li, "_open_tty", _open)

    def _human(self):
        import select

        answered = False
        while not self._stop.is_set():
            if select.select([self.master], [], [], 0.05)[0]:
                try:
                    chunk = os.read(self.master, 4096)
                except OSError:
                    return  # master closed by close(); helper thread ends
                self._seen += chunk
                if not answered and self._answer:
                    os.write(self.master, self._answer)
                    answered = True

    def prompt_seen(self) -> str:
        import time

        time.sleep(0.3)  # let the helper thread drain the prompt
        return self._seen.decode(errors="replace")

    def close(self):
        self._stop.set()
        self._thread.join(timeout=5)
        for fd in (self.master, self.slave):
            try:
                os.close(fd)
            except OSError:
                pass  # already closed by an earlier close(); test helper only


@pytest.fixture
def tty(monkeypatch):
    made = []

    def _make(answer: bytes, stale: bytes = b""):
        t = _Pty(monkeypatch, answer, stale)
        made.append(t)
        return t

    yield _make
    for t in made:
        t.close()


def _audit_rows(env):
    if not env["audit"].exists():
        return []
    return [json.loads(line) for line in env["audit"].read_text().splitlines()]


def _swap_spy(monkeypatch, env, ok=True):
    def _swap(model_path, model_variant="primary"):
        env["events"].append("swap")
        return ok, "swapped"

    monkeypatch.setattr(li, "swap_to_finetuned_model", _swap)


def _adopt(env, **kw):
    adapter = _adapter(env["tmp"]) if not (env["tmp"] / "adapter").exists() else env["tmp"] / "adapter"
    return li.import_lora_adapter(str(adapter), **kw)


# ---------------------------------------------------------------- adopt


def test_adopt_approved_on_tty_order_and_override_recorded(env, monkeypatch, tty):
    t = tty(b"y\n")
    _swap_spy(monkeypatch, env)
    results = _adopt(env, gate_decision=None, operator_override=True)

    assert results["success"] is True, results
    # backup copy happens before swap; both after the prompt was answered.
    assert env["events"] == ["copy2", "swap"]
    shown = t.prompt_seen()
    assert "HIGH IMPACT" in shown and "Proceed? [y/N]" in shown  # visible on the tty, not stdout
    entry = env["reg"].get_adoption(results["registry_id"])
    assert entry["adopted"] is True
    assert entry["operator_override"] in (1, True)  # truthfully recorded
    assert entry["gate_promote"] == 0  # gate verdict never rewritten
    rows = _audit_rows(env)
    assert [(r["authority"], r["action"], r["outcome"]) for r in rows] == [
        ("HIGH_IMPACT", "lora_import.adopt", "allowed")
    ]


@pytest.mark.parametrize("answer", [b"n\n", b"\n", b"yep\n", b"no\n", b"\x04"])
def test_adopt_declined_or_eof_refuses_with_no_side_effects(env, monkeypatch, tty, answer):
    tty(answer)
    _swap_spy(monkeypatch, env)
    results = _adopt(env, gate_decision=None, operator_override=True)

    assert results["success"] is False
    assert results["error"].startswith("Refused: no human confirmation")
    assert env["events"] == []  # no copy, no swap, no loader call
    assert not list(env["base"].parent.glob("*.backup*"))
    # Refusal record was written outside the thunk, truthfully.
    rows = env["reg"].list_adoptions(limit=10)
    assert len(rows) == 1 and rows[0]["adopted"] is False
    assert rows[0]["operator_override"] in (1, True)
    a = _audit_rows(env)
    assert len(a) == 1 and a[0]["outcome"] == "refused" and a[0]["action"] == "lora_import.adopt"


def test_adopt_no_tty_fails_closed(env, monkeypatch):
    _swap_spy(monkeypatch, env)
    # autouse env points _TTY_PATH at a nonexistent file: OSError on open.
    results = _adopt(env, gate_decision=None, operator_override=True)
    assert results["success"] is False
    assert env["events"] == []
    a = _audit_rows(env)
    assert len(a) == 1 and a[0]["outcome"] == "refused"
    assert len(env["reg"].list_adoptions(limit=10)) == 1


@pytest.mark.parametrize("returned", [1, "yes", None, MagicMock()])
def test_adopt_non_true_confirm_result_refuses(env, monkeypatch, returned):
    monkeypatch.setattr(li, "_confirm_on_tty", lambda prompt: returned)
    _swap_spy(monkeypatch, env)
    results = _adopt(env, gate_decision=None, operator_override=True)
    assert results["success"] is False and env["events"] == []
    assert _audit_rows(env)[0]["outcome"] == "refused"


def test_promotion_gate_refusal_never_prompts(env, monkeypatch):
    def _no_prompt(prompt):
        raise AssertionError("tty must not be consulted when the promotion gate refuses")

    monkeypatch.setattr(li, "_confirm_on_tty", _no_prompt)
    results = _adopt(env, gate_decision=None, operator_override=False)
    assert results["error"].startswith("Refused by promotion gate")
    assert _audit_rows(env) == []
    assert env["events"] == []


def test_force_adopt_flag_alone_is_not_the_human_act(env, monkeypatch):
    """operator_override=True with no terminal must still refuse."""
    _swap_spy(monkeypatch, env)
    results = _adopt(env, gate_decision=_Gate(False), operator_override=True)
    assert results["success"] is False and env["events"] == []


def test_adopt_span_exception_audits_static_label_and_reraises(env, monkeypatch, tty):
    tty(b"y\n")
    secret = "SECRET-PAYLOAD-" + str(env["tmp"])

    def _boom(model_path, model_variant="primary"):
        raise RuntimeError(secret)

    monkeypatch.setattr(li, "swap_to_finetuned_model", _boom)
    with pytest.raises(RuntimeError) as ei:
        _adopt(env, gate_decision=None, operator_override=True)
    assert secret in str(ei.value)  # caller still sees the real error
    raw = env["audit"].read_text()
    assert secret not in raw and str(env["tmp"]) not in raw
    rows = _audit_rows(env)
    assert rows[0]["outcome"] == "failed"
    assert rows[0]["reason"] == "lora adoption span failed"


def test_audit_rows_never_contain_paths(env, monkeypatch, tty):
    tty(b"n\n")
    _adopt(env, gate_decision=None, operator_override=True)
    raw = env["audit"].read_text()
    assert str(env["tmp"]) not in raw and "adapter" not in raw.replace("lora adapter adoption", "")


def test_no_backup_refusal_inside_span_still_recorded(env, monkeypatch, tty):
    """Existing behaviour preserved: missing base model => refuse + record."""
    tty(b"y\n")
    _swap_spy(monkeypatch, env)
    env["base"].unlink()
    results = _adopt(env, gate_decision=None, operator_override=True)
    assert results["success"] is False and "could not create a backup" in results["error"]
    assert "swap" not in env["events"]
    assert len(env["reg"].list_adoptions(limit=10)) == 1


# ------------------------------------------------------------- rollback


def _adopted_with_backup(env, monkeypatch, tty):
    t = tty(b"y\n")
    _swap_spy(monkeypatch, env)
    results = _adopt(env, gate_decision=None, operator_override=True)
    assert results["success"] is True
    env["events"].clear()
    t.close()
    return results["registry_id"], results["backup_path"]


def test_rollback_adoption_one_liner_approves_via_default_tty_adapter(env, monkeypatch, tty):
    rid, backup = _adopted_with_backup(env, monkeypatch, tty)
    t = tty(b"y\n")  # no callback is supplied to rollback_adoption(): default adapter only
    ok, msg = li.rollback_adoption(rid)
    assert ok is True, msg
    assert env["events"] == ["loader.unload", "copy2", "loader.load_primary"]
    assert not os.path.exists(backup)  # unlinked only after the copy
    assert env["base"].read_bytes() == b"BASE-WEIGHTS"
    assert env["reg"].get_adoption(rid)["rolled_back"] in (1, True)
    assert "HIGH IMPACT" in t.prompt_seen()
    rows = [r for r in _audit_rows(env) if r["action"] == "lora_import.rollback"]
    assert [r["outcome"] for r in rows] == ["allowed"]


@pytest.mark.parametrize("answer", [b"n\n", b"\n", b"\x04", None])
def test_rollback_declined_eof_or_no_tty_refuses_untouched(env, monkeypatch, tty, answer):
    rid, backup = _adopted_with_backup(env, monkeypatch, tty)
    if answer is not None:
        tty(answer)
    marker = MagicMock()
    import core.model_registry as reg

    monkeypatch.setattr(reg, "mark_rolled_back", marker)
    ok, msg = li.rollback_adoption(rid)
    assert ok is False and msg.startswith("Rollback refused")
    assert env["events"] == []  # no unload, no copy, no reload
    assert os.path.exists(backup)  # backup kept for a later, confirmed rollback
    marker.assert_not_called()
    rows = [r for r in _audit_rows(env) if r["action"] == "lora_import.rollback"]
    assert [r["outcome"] for r in rows] == ["refused"]
    assert backup not in env["audit"].read_text()


def test_rollback_to_backup_direct_is_gated_too(env, monkeypatch):
    """The CCOS finetune plugin and any shell-tool caller reach
    rollback_to_backup() directly; it must be gated, not only the wrapper."""
    backup = env["base"].parent / "base.backup.gguf"
    backup.write_bytes(b"OLD")
    ok, msg = li.rollback_to_backup(str(backup), "primary")
    assert ok is False and msg.startswith("Rollback refused")
    assert backup.exists() and env["events"] == []


def test_rollback_failed_copy_keeps_backup(env, monkeypatch, tty):
    tty(b"y\n")
    backup = env["base"].parent / "base.backup.gguf"
    backup.write_bytes(b"OLD")

    def _bad_copy(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(li.shutil, "copy2", _bad_copy)
    ok, msg = li.rollback_to_backup(str(backup), "primary")
    assert ok is False and msg.startswith("Rollback failed")
    assert backup.exists()  # unlink only after a confirmed copy


# ------------------------------------------------------ tty adapter itself


@pytest.mark.parametrize("answer,expected", [(b"y\n", True), (b"YES\n", True), (b" Yes \n", True), (b"n\n", False), (b"\n", False), (b"yes please\n", False)])
def test_confirm_adapter_answers(monkeypatch, tty, answer, expected):
    t = tty(answer)
    assert _REAL_CONFIRM("Proceed? ") is expected
    assert "Proceed?" in t.prompt_seen()


def test_confirm_adapter_eof_raises(monkeypatch, tty):
    tty(b"\x04")
    with pytest.raises(EOFError):
        _REAL_CONFIRM("Proceed? ")


def test_stale_typeahead_yes_is_flushed_and_cannot_approve(monkeypatch, tty):
    t = tty(b"n\n", stale=b"y\n")
    assert _REAL_CONFIRM("Proceed? ") is False  # read the fresh "n", not the stale "y"
    assert "Proceed?" in t.prompt_seen()


def test_stale_typeahead_with_eof_answer_raises_not_approves(monkeypatch, tty):
    tty(b"\x04", stale=b"y\n")
    with pytest.raises(EOFError):
        _REAL_CONFIRM("Proceed? ")


def test_fresh_yes_after_prompt_still_approves_despite_stale_input(monkeypatch, tty):
    t = tty(b"y\n", stale=b"n\nn\n")
    assert _REAL_CONFIRM("Proceed? ") is True
    assert "Proceed?" in t.prompt_seen()


def test_flush_failure_fails_closed(monkeypatch, tty):
    import termios

    t = tty(b"y\n")

    def _boom(fd, queue):
        raise termios.error(25, "not a tty")

    monkeypatch.setattr(termios, "tcflush", _boom)
    with pytest.raises(OSError):
        _REAL_CONFIRM("Proceed? ")
    assert t.prompt_seen() == ""  # prompt never written


def test_confirm_adapter_open_failure_propagates_oserror(monkeypatch):
    # _TTY_PATH is a nonexistent path from the env fixture.
    with pytest.raises(OSError):
        _REAL_CONFIRM("Proceed? ")


def test_prompt_escapes_control_characters_in_paths(env, monkeypatch):
    seen = {}

    def _capture(prompt):
        seen["p"] = prompt
        return False

    monkeypatch.setattr(li, "_confirm_on_tty", _capture)
    adapter = _adapter(env["tmp"])
    evil = adapter / ".." / "adapter"
    li.import_lora_adapter(str(evil) + "\x1b[2J", gate_decision=_Gate(True), operator_override=False)
    # validate_lora_adapter rejects the nonexistent path before any prompt;
    # drive the prompt directly via a valid dir name containing an escape.
    d = env["tmp"] / "ad\x1b[2Japter"
    d.mkdir()
    (d / "adapter_config.json").write_text(json.dumps({"r": 8, "target_modules": ["q_proj"]}))
    (d / "adapter_model.safetensors").write_bytes(b"x")
    li.import_lora_adapter(str(d), gate_decision=_Gate(True))
    assert "\x1b" not in seen["p"]
