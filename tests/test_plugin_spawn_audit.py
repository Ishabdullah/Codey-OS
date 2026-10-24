"""G15g Unit B: audited external-plugin spawn (recording-fake Popen only).

No real process is ever started here: subprocess.Popen is replaced by a
recording fake in every test. Audit rows are read back from a disposable
JSONL sink.
"""
import json
import os
import subprocess
import sys

import pytest

from ccos.core import plugin_manager as pm
from ccos.core.plugin_manager import Plugin, PluginStatus, ProcessSupervisor
from core import action_gateway as ag


class FakeProc:
    def __init__(self, pid=424242, exits=False):
        self.pid = pid
        self.exits = exits
        self.calls = []
        self.stdout = None
        self.stderr = None
        self._done = False

    def poll(self):
        return 0 if self._done else None

    def terminate(self):
        self.calls.append("terminate")
        self._done = True

    def kill(self):
        self.calls.append("kill")
        self._done = True

    def wait(self, timeout=None):
        self.calls.append("wait")
        if self.exits:
            self._done = True
            return 0
        if not self._done:
            raise subprocess.TimeoutExpired("fake", timeout)
        return 0


@pytest.fixture
def rig(tmp_path, monkeypatch):
    audit = tmp_path / "audit.jsonl"
    monkeypatch.setenv("CODEY_ACTION_GATEWAY_AUDIT", str(audit))
    monkeypatch.setenv("HOME", str(tmp_path))
    ag.reset_action_gateway()
    monkeypatch.setattr(pm, "PLUGIN_PID_DIR", tmp_path / "state" / "plugins")
    popen_calls = []
    state = {"proc": FakeProc(), "raise": None}

    def fake_popen(cmd, **kwargs):
        popen_calls.append((cmd, kwargs))
        if state["raise"] is not None:
            raise state["raise"]
        return state["proc"]

    monkeypatch.setattr(pm.subprocess, "Popen", fake_popen)
    plugin = Plugin(
        name="fx", path=str(tmp_path), execution_mode="external_process",
        manifest={"process_spec": {
            "start_command": [sys.executable, "-c", "pass"],
            "pid_file": "fx.pid",
            "env": {"FX_OVERRIDE_TOKEN": "override-canary-value", "FX_PLAIN": "p"},
        }},
    )

    def rows():
        if not audit.exists():
            return []
        return [json.loads(l) for l in audit.read_text().splitlines() if l.strip()]

    sup = ProcessSupervisor()
    yield type("Rig", (), dict(sup=sup, plugin=plugin, rows=staticmethod(rows),
                               popen_calls=popen_calls, state=state, audit=audit,
                               root=tmp_path))
    ag.reset_action_gateway()


def test_b1_happy_path_row_names_only(rig, monkeypatch):
    monkeypatch.setenv("G15G_SECRET_TOKEN", "hunter2-canary")
    assert rig.sup.start_external_plugin(rig.plugin) is True
    rows = rig.rows()
    assert len(rows) == 1
    row = rows[0]
    assert row["authority"] == pm.ACT
    assert row["outcome"] == "allowed"
    assert row["action"] == "ccos.plugin_spawn:fx"
    for key in ("plugin=fx", "argv=", "cwd=", "argv_sha256=", "env_policy=inherit-all"):
        assert key in row["command"]
    text = rig.audit.read_text()
    assert "hunter2-canary" not in text
    assert "override-canary-value" not in text
    assert "G15G_SECRET_TOKEN" in row["command"]
    assert "FX_OVERRIDE_TOKEN" in row["command"] and "FX_PLAIN" in row["command"]


def test_b1_long_argv_truncated_with_full_hash(rig):
    import hashlib, shlex
    cmd = [sys.executable, "-c", "x" * 2000]
    rig.plugin.manifest["process_spec"]["start_command"] = cmd
    assert rig.sup.start_external_plugin(rig.plugin) is True
    command = rig.rows()[0]["command"]
    full = shlex.join(cmd)
    assert "x" * 600 not in command
    assert hashlib.sha256(full.encode()).hexdigest()[:16] in command


def test_b2_popen_failure(rig):
    rig.state["raise"] = FileNotFoundError("no such binary")
    assert rig.sup.start_external_plugin(rig.plugin) is False
    rows = rig.rows()
    assert [r["outcome"] for r in rows] == ["failed"]
    assert rig.plugin.status == PluginStatus.BROKEN
    assert rig.plugin.error == "External process startup failed"
    assert rig.sup._processes == {}
    assert not (pm.PLUGIN_PID_DIR / "fx.pid").exists()


def test_b3_pid_record_refuses_before_popen(rig):
    pm.PLUGIN_PID_DIR.mkdir(parents=True)
    (pm.PLUGIN_PID_DIR / "fx.pid").write_text("12345")
    assert rig.sup.start_external_plugin(rig.plugin) is False
    assert rig.popen_calls == []
    rows = rig.rows()
    assert len(rows) == 1 and rows[0]["outcome"] == "refused"
    assert rows[0]["action"] == "ccos.plugin_spawn:fx"
    assert rig.plugin.status == PluginStatus.BROKEN
    assert rig.plugin.error == "Unowned PID record blocks external process startup"


def test_b3_missing_entry_refusal_row(rig):
    rig.plugin.manifest = {"entry_point": "nope.py", "process_spec": {}}
    assert rig.sup.start_external_plugin(rig.plugin) is False
    assert rig.popen_calls == []
    rows = rig.rows()
    assert len(rows) == 1 and rows[0]["outcome"] == "refused"
    assert rig.plugin.error == "No start_command or entry_point found for external process"


def test_b3_containment_single_row_high_impact(rig):
    rig.plugin.manifest = {"entry_point": "../escape.py", "process_spec": {}}
    assert rig.sup.start_external_plugin(rig.plugin) is False
    assert rig.popen_calls == []
    rows = rig.rows()
    assert len(rows) == 1
    assert rows[0]["authority"] == pm.HIGH_IMPACT


def test_b4_handle_stored_inside_thunk(rig, monkeypatch):
    seen = {}
    orig = ag.ActionGateway._audit_exec

    def boom(self, *a, **k):
        seen["owned_at_row"] = rig.sup._processes.get("fx") is rig.state["proc"]
        raise RuntimeError("audit exploded after thunk")

    monkeypatch.setattr(ag.ActionGateway, "_audit_exec", boom)
    assert rig.sup.start_external_plugin(rig.plugin) is False
    assert seen["owned_at_row"] is True
    assert "terminate" in rig.state["proc"].calls
    assert rig.sup._processes == {}
    assert rig.plugin.status == PluginStatus.BROKEN
    assert orig  # keep reference; real method untouched elsewhere


def test_b5_env_byte_identical(rig, monkeypatch):
    monkeypatch.setenv("G15G_ENV_PIN", "v")
    assert rig.sup.start_external_plugin(rig.plugin) is True
    env = rig.popen_calls[0][1]["env"]
    expected = {**os.environ, **rig.plugin.manifest["process_spec"]["env"]}
    # G15h/D-10 will deliberately flip this to an allowlist and update here.
    assert env == expected


def test_b6_fast_path_no_row_restart_one_row(rig):
    assert rig.sup.start_external_plugin(rig.plugin) is True
    assert len(rig.rows()) == 1
    rig.sup._ready.add("fx")
    assert rig.sup.start_external_plugin(rig.plugin) is True
    assert len(rig.rows()) == 1 and len(rig.popen_calls) == 1
    rig.state["proc"]._done = True  # owned child died
    rig.state["proc"] = FakeProc(pid=424243)
    rig.sup.start_external_plugin(rig.plugin)
    assert len(rig.popen_calls) == 2
    assert len(rig.rows()) == 2


def test_b7_unreadable_liveness_writes_refusal_row(rig):
    class Bad(FakeProc):
        def poll(self):
            raise OSError("poll broke")
    rig.sup._processes["fx"] = Bad()
    assert rig.sup.start_external_plugin(rig.plugin) is False
    assert rig.popen_calls == []
    rows = rig.rows()
    assert len(rows) == 1 and rows[0]["outcome"] == "refused"
    assert rows[0]["authority"] == pm.ACT and rows[0]["action"] == "ccos.plugin_spawn:fx"
    assert "liveness unreadable" in rows[0]["reason"]


def test_b7_dead_owned_child_stop_fails_writes_refusal_row(rig, monkeypatch):
    dead = FakeProc()
    dead._done = True
    rig.sup._processes["fx"] = dead
    monkeypatch.setattr(rig.sup, "stop_external_plugin", lambda *a, **k: False)
    assert rig.sup.start_external_plugin(rig.plugin) is False
    assert rig.popen_calls == []
    rows = rig.rows()
    assert len(rows) == 1 and rows[0]["outcome"] == "refused"
    assert "could not be stopped" in rows[0]["reason"]


def test_b7_every_exit_writes_exactly_one_row_except_alive_fast_path(rig):
    """Enumerates every return of start_external_plugin: containment,
    missing entry, PID record, Popen failure, success, unreadable liveness,
    stop failure (own test above) each give one row; owned-alive fast path gives none."""
    sup, plugin = rig.sup, rig.plugin
    base = dict(plugin.manifest)

    def run(label, setup, expect_rows, expect_ret):
        rig.audit.unlink(missing_ok=True)
        rig.sup._processes.clear()
        rig.sup._ready.clear()
        pm.PLUGIN_PID_DIR.mkdir(parents=True, exist_ok=True)
        for f in pm.PLUGIN_PID_DIR.glob("*"):
            f.unlink()
        rig.state["raise"] = None
        rig.state["proc"] = FakeProc()
        plugin.manifest = {"process_spec": dict(base["process_spec"])}
        plugin.status = PluginStatus.INSTALLED
        setup()
        assert sup.start_external_plugin(plugin) is expect_ret, label
        assert len(rig.rows()) == expect_rows, label

    run("success", lambda: None, 1, True)
    run("popen-fail", lambda: rig.state.update({"raise": OSError("x")}), 1, False)
    run("pid-record", lambda: (pm.PLUGIN_PID_DIR / "fx.pid").write_text("1"), 1, False)
    run("containment", lambda: plugin.manifest.update(entry_point="../x.py", process_spec={}), 1, False)
    run("missing-entry", lambda: plugin.manifest.update(entry_point="nope.py", process_spec={}), 1, False)

    def alive():
        sup._processes["fx"] = FakeProc()
        sup._ready.add("fx")
    run("owned-alive", alive, 0, True)

    def badpoll():
        class Bad(FakeProc):
            def poll(self):
                raise OSError("x")
        sup._processes["fx"] = Bad()
    run("liveness", badpoll, 1, False)
