"""NEW-970: native voice boundaries go through the Action Gateway.

Every device call (termux-speech-to-text, termux-tts-speak, subprocess.run /
Popen) is mocked before any invocation. The real main.py confirmation adapter
is AST-extracted so main.py's model imports never run.
"""

import ast
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import core.action_gateway as ag
import core.voice as voice

REPO = Path(__file__).resolve().parents[1]
SECRET = "SECRET-TRANSCRIPT-xyz"


def _extract_adapter():
    tree = ast.parse((REPO / "main.py").read_text())
    fn = next(n for n in tree.body
              if isinstance(n, ast.FunctionDef) and n.name == "_voice_confirmation")
    import os
    import sys
    ns = {"os": os, "sys": sys}
    exec(compile(ast.Module([fn], []), "main.py", "exec"), ns)
    return ns["_voice_confirmation"], ns


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("CODEY_DAEMON_MODE", raising=False)
    monkeypatch.delenv("CODEY_NON_INTERACTIVE", raising=False)
    monkeypatch.setattr(voice, "_VOICE_CONFIG_PATH", tmp_path / "voice_config.json")
    audit = tmp_path / "audit.jsonl"
    monkeypatch.setattr(ag, "_gateway", ag.ActionGateway(audit_file=audit))
    # Mock every device entry point before anything can be invoked.
    run = Mock(name="subprocess.run")
    popen = Mock(name="subprocess.Popen")
    kill = Mock(name="os.kill")
    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(subprocess, "Popen", popen)
    monkeypatch.setattr(voice.shutil, "which", lambda name: "/fake/" + name)
    import os
    monkeypatch.setattr(os, "kill", kill)
    vm = voice.VoiceManager()
    return SimpleNamespace(vm=vm, run=run, popen=popen, kill=kill, audit=audit)


def _stt(stdout, rc=0):
    return SimpleNamespace(returncode=rc, stdout=stdout, stderr="")


def _rows(env):
    if not env.audit.exists():
        return []
    return [json.loads(x) for x in env.audit.read_text().splitlines()]


def _no_payload(env):
    raw = env.audit.read_bytes() if env.audit.exists() else b""
    assert SECRET.encode() not in raw


# ---- STT -------------------------------------------------------------------

def test_listen_confirmed_records_once(env):
    env.run.return_value = _stt(json.dumps({"text": SECRET, "error": "Unset"}))
    confirm = Mock(return_value=True)
    assert env.vm.listen(confirm=confirm) == SECRET
    assert confirm.call_count == 1
    assert env.run.call_count == 1
    rows = _rows(env)
    assert len(rows) == 1
    assert rows[0]["authority"] == ag.HIGH_IMPACT
    assert rows[0]["action"] == "voice.listen"
    assert rows[0]["outcome"] == ag.OUTCOME_ALLOWED
    _no_payload(env)


def test_listen_plain_text_after_exit_zero(env):
    env.run.return_value = _stt(SECRET + "\n")
    assert env.vm.listen(confirm=lambda: True) == SECRET
    _no_payload(env)


@pytest.mark.parametrize("confirm", [
    None,
    lambda: False,
    Mock(side_effect=EOFError),
    Mock(side_effect=KeyboardInterrupt),
    Mock(side_effect=RuntimeError(SECRET)),
    lambda: "yes",  # truthy but not literal True
    "not callable",
])
def test_listen_denied_never_records(env, confirm):
    assert env.vm.listen(confirm=confirm) is None
    assert env.run.call_count == 0
    assert env.popen.call_count == 0
    rows = _rows(env)
    assert rows and all(r["outcome"] == ag.OUTCOME_REFUSED for r in rows)
    _no_payload(env)


def test_listen_confirm_is_keyword_only(env):
    with pytest.raises(TypeError):
        env.vm.listen(20, lambda: True)
    assert env.run.call_count == 0


def test_listen_nonzero_exit_with_text_is_failed(env):
    env.run.return_value = _stt(json.dumps({"text": SECRET, "error": "Unset"}), rc=1)
    assert env.vm.listen(confirm=lambda: True) is None
    rows = _rows(env)
    assert rows[-1]["outcome"] == ag.OUTCOME_FAILED
    _no_payload(env)


@pytest.mark.parametrize("effect", [
    subprocess.TimeoutExpired(["x", SECRET], 1),
    FileNotFoundError(SECRET),
    OSError(SECRET),
    KeyboardInterrupt(),
])
def test_listen_exec_errors_fail_without_payload(env, effect):
    env.run.side_effect = effect
    assert env.vm.listen(confirm=lambda: True) is None
    assert _rows(env)[-1]["outcome"] == ag.OUTCOME_FAILED
    _no_payload(env)


def test_listen_json_error_and_empty(env):
    env.run.return_value = _stt(json.dumps({"text": SECRET, "error": "Boom"}))
    assert env.vm.listen(confirm=lambda: True) is None
    assert _rows(env)[-1]["outcome"] == ag.OUTCOME_FAILED
    env.run.return_value = _stt("")
    assert env.vm.listen(confirm=lambda: True) is None
    env.run.return_value = _stt(json.dumps({"text": "  ", "error": "Unset"}))
    assert env.vm.listen(confirm=lambda: True) is None
    _no_payload(env)


def test_listen_unavailable_does_nothing(env, monkeypatch):
    monkeypatch.setattr(voice.shutil, "which", lambda name: None)
    vm = voice.VoiceManager()
    confirm = Mock(return_value=True)
    assert vm.listen(confirm=confirm) is None
    assert confirm.call_count == 0 and env.run.call_count == 0


# ---- TTS -------------------------------------------------------------------

def test_speak_act_success_audits_static_labels(env):
    env.run.return_value = SimpleNamespace(returncode=0)
    assert env.vm.speak(SECRET) is True
    assert env.run.call_count == 1
    assert SECRET in env.run.call_args[0][0]  # text goes to device, not audit
    rows = _rows(env)
    assert len(rows) == 1
    assert rows[0]["authority"] == ag.ACT
    assert rows[0]["action"] == "voice.speak"
    assert rows[0]["command"] == "voice.speak"
    _no_payload(env)


def test_speak_nonzero_is_failed_false(env):
    env.run.return_value = SimpleNamespace(returncode=3)
    assert env.vm.speak(SECRET) is False
    assert _rows(env)[-1]["outcome"] == ag.OUTCOME_FAILED
    _no_payload(env)


@pytest.mark.parametrize("effect", [
    subprocess.TimeoutExpired(["x", SECRET], 1),
    FileNotFoundError(SECRET),
    KeyboardInterrupt(),
])
def test_speak_errors_and_interrupt_false(env, effect):
    env.run.side_effect = effect
    assert env.vm.speak(SECRET) is False
    assert _rows(env)[-1]["outcome"] == ag.OUTCOME_FAILED
    _no_payload(env)


def test_speak_async_launch_unchanged_semantics(env):
    child = object()
    env.popen.return_value = child
    assert env.vm.speak(SECRET, wait=False) is True
    assert env.vm._speak_proc is child  # NEW-972 behavior deliberately untouched
    assert env.kill.call_count == 0
    _no_payload(env)


def test_speak_empty_prose_makes_no_call(env):
    assert env.vm.speak("") is False
    assert env.run.call_count == 0 and _rows(env) == []


# ---- main.py adapter and call sites ---------------------------------------

def _stdin(monkeypatch, ns, tty):
    monkeypatch.setattr(ns["sys"], "stdin", SimpleNamespace(isatty=lambda: tty))


def test_adapter_unavailable_states(monkeypatch):
    adapter, ns = _extract_adapter()
    _stdin(monkeypatch, ns, True)
    monkeypatch.delenv("CODEY_DAEMON_MODE", raising=False)
    monkeypatch.delenv("CODEY_NON_INTERACTIVE", raising=False)
    assert adapter(yolo=True) is None
    monkeypatch.setenv("CODEY_DAEMON_MODE", "1")
    assert adapter(False) is None
    monkeypatch.delenv("CODEY_DAEMON_MODE")
    monkeypatch.setenv("CODEY_NON_INTERACTIVE", "1")
    assert adapter(False) is None
    monkeypatch.delenv("CODEY_NON_INTERACTIVE")
    _stdin(monkeypatch, ns, False)
    assert adapter(False) is None

    def boom():
        raise ValueError("closed")
    monkeypatch.setattr(ns["sys"], "stdin", SimpleNamespace(isatty=boom))
    assert adapter(False) is None


@pytest.mark.parametrize("answer,expected", [
    ("y", True), ("YES", True), (" yes ", True),
    ("", False), ("n", False), ("maybe", False),
])
def test_adapter_prompts_per_attempt_default_no(monkeypatch, answer, expected):
    adapter, ns = _extract_adapter()
    _stdin(monkeypatch, ns, True)
    monkeypatch.delenv("CODEY_DAEMON_MODE", raising=False)
    monkeypatch.delenv("CODEY_NON_INTERACTIVE", raising=False)
    prompts = []
    ns["input"] = lambda p: (prompts.append(p), answer)[1]
    confirm = adapter(False)
    assert callable(confirm)
    assert prompts == []  # nothing asked until the gateway calls it
    assert confirm() is expected
    assert confirm() is expected
    assert len(prompts) == 2  # a fresh prompt every attempt


def test_adapter_eof_and_interrupt_refuse_recording(env, monkeypatch):
    adapter, ns = _extract_adapter()
    _stdin(monkeypatch, ns, True)
    for exc in (EOFError, KeyboardInterrupt):
        def raiser(prompt, exc=exc):
            raise exc
        ns["input"] = raiser
        assert env.vm.listen(confirm=adapter(False)) is None
    assert env.run.call_count == 0


def test_adapter_end_to_end_confirmed_records_once(env, monkeypatch):
    adapter, ns = _extract_adapter()
    _stdin(monkeypatch, ns, True)
    ns["input"] = lambda p: "y"
    env.run.return_value = _stt(json.dumps({"text": SECRET, "error": "Unset"}))
    assert env.vm.listen(confirm=adapter(False)) == SECRET
    assert env.run.call_count == 1


def test_both_mic_call_sites_pass_adapter_and_no_unmediated_listen():
    src = (REPO / "main.py").read_text()
    tree = ast.parse(src)
    calls = [n for n in ast.walk(tree)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
             and n.func.attr == "listen"]
    assert len(calls) == 2
    for c in calls:
        kw = {k.arg: k.value for k in c.keywords}
        assert "confirm" in kw
        v = kw["confirm"]
        assert isinstance(v, ast.Call) and v.func.id == "_voice_confirmation"
        assert isinstance(v.args[0], ast.Name) and v.args[0].id == "yolo"
