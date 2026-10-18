"""WP2.1 slice 14i: low-severity persistence writers go through the gateway.

Covers voice config, session save/clear, task-queue save and the --finetune
export. Session/queue saves are high-frequency: every save is gated, but
repeat identical outcomes per target coalesce into one static ACT row
(core/bookkeeping_persist.py); N saves must not produce N rows. All paths and audit files are tmp; run with HOME and
CODEY_STATE_DIR pointed at a disposable directory.
"""

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import core.action_gateway as ag
import core.bookkeeping_persist as bp
import core.finetune_prep as fp
import core.sessions as sessions
import core.taskqueue as taskqueue
import core.voice as voice

SECRET = "SECRET-PATH-OR-CONTENT-xyz"


@pytest.fixture
def env(tmp_path, monkeypatch):
    audit = tmp_path / "audit.jsonl"
    gateway = ag.ActionGateway(audit_file=audit)
    monkeypatch.setattr(ag, "_gateway", gateway)
    monkeypatch.setattr(sessions, "SESSIONS_DIR", tmp_path / "sessions")
    monkeypatch.setattr(taskqueue, "SESSIONS_DIR", tmp_path / "sessions")
    monkeypatch.setattr(voice, "_VOICE_CONFIG_PATH", tmp_path / "vcfg" / "voice_config.json")
    return SimpleNamespace(tmp=tmp_path, audit=audit, gateway=gateway)


def rows(env):
    if not env.audit.exists():
        return []
    return [json.loads(line) for line in env.audit.read_text().splitlines()]


def refuse_all(env, monkeypatch):
    def refuse(**kw):
        return ag.GatewayDecision(authority=kw["authority"], outcome=ag.OUTCOME_REFUSED, reason="denied")

    gate = Mock(side_effect=refuse)
    monkeypatch.setattr(env.gateway, "gate_exec", gate)
    return gate


def history(n=1, text="hello"):
    out = []
    for i in range(n):
        out += [{"role": "user", "content": f"{text} {i}"}, {"role": "assistant", "content": "ok"}]
    return out


# ---------------------------------------------------------------- voice


def test_voice_config_goes_through_gate_with_static_row(env):
    vm = voice.VoiceManager()
    vm.set_rate(1.5)
    assert json.loads(voice._VOICE_CONFIG_PATH.read_text())["tts_rate"] == 1.5
    (row,) = rows(env)
    assert {k: v for k, v in row.items() if k != "ts"} == {
        "authority": ag.ACT, "action": "voice.save_config",
        "command": "persist voice_config.json", "outcome": "allowed", "reason": "command executed",
    }
    vm.set_pitch(0.8)  # operator setters are low frequency: one row each
    assert len(rows(env)) == 2


def test_voice_config_refusal_writes_nothing_and_does_not_raise(env, monkeypatch):
    vm = voice.VoiceManager()
    refuse_all(env, monkeypatch)
    vm.set_rate(2.0)
    assert vm.tts_rate == 2.0  # in-memory setting unchanged semantics
    assert not voice._VOICE_CONFIG_PATH.exists()
    assert not voice._VOICE_CONFIG_PATH.parent.exists()


def test_voice_config_failure_audited_statically_and_swallowed(env, monkeypatch):
    blocker = env.tmp / "blocker"
    blocker.write_text(SECRET)
    monkeypatch.setattr(voice, "_VOICE_CONFIG_PATH", blocker / "sub" / "voice_config.json")
    voice.VoiceManager().set_rate(1.2)  # must not raise
    (row,) = rows(env)
    assert row["outcome"] == "failed" and row["reason"] == "voice config write failed"
    assert str(env.tmp) not in json.dumps(row)


# ------------------------------------------------------------- sessions


def test_session_saves_are_coalesced_to_one_static_row(env):
    for i in range(25):
        sessions.save_session(history(i + 1), project_dir=str(env.tmp / "proj-secret"))
    path = sessions._session_path(str(env.tmp / "proj-secret"))
    assert json.loads(path.read_text())["turns"] == 6  # latest save really landed
    (row,) = rows(env)
    assert {k: v for k, v in row.items() if k != "ts"} == {
        "authority": ag.ACT, "action": "sessions.save_session",
        "command": "persist session file", "outcome": "allowed", "reason": "command executed",
    }
    assert "proj-secret" not in json.dumps(row)


def test_distinct_session_targets_each_get_one_row(env):
    for proj in ("a", "b", "a", "b", "a"):
        sessions.save_session(history(), project_dir=str(env.tmp / proj))
    assert len(rows(env)) == 2


def test_session_redaction_and_location_pinned(env):
    key = "sk-" + "a" * 48
    sessions.save_session([{"role": "user", "content": f"key {key}"}, {"role": "assistant", "content": "x"}],
                          project_dir=str(env.tmp / "p"))
    path = sessions._session_path(str(env.tmp / "p"))
    assert path.parent == env.tmp / "sessions"
    assert path.name.startswith("p_") and path.suffix == ".json"
    assert key not in path.read_text() and "[REDACTED]" in path.read_text()


def test_session_refusal_leaves_nothing_and_retries_through_gate(env, monkeypatch):
    gate = refuse_all(env, monkeypatch)
    sessions.save_session(history(), project_dir=str(env.tmp / "p"))
    sessions.save_session(history(), project_dir=str(env.tmp / "p"))
    assert gate.call_count == 2  # every save consults the gate
    assert not (env.tmp / "sessions").exists()  # not even the directory


def test_session_write_failure_warns_not_raises_and_row_is_static(env, monkeypatch):
    warn = Mock()
    monkeypatch.setattr(sessions, "warning", warn)
    (env.tmp / "sessions").write_text("a file, not a dir")  # mkdir/write will fail
    sessions.save_session(history(), project_dir=str(env.tmp / "proj-secret"))
    warn.assert_called_once()
    assert warn.call_args.args[0].startswith("Could not save session:")
    (row,) = rows(env)
    assert row["outcome"] == "failed" and row["reason"] == "persistence write failed"
    assert str(env.tmp) not in json.dumps(row)


def test_session_later_failure_records_one_failed_row_and_recovery_row(env, monkeypatch):
    p = str(env.tmp / "p")
    sessions.save_session(history(), project_dir=p)
    path = sessions._session_path(p)
    path.unlink()
    path.mkdir()  # make the next write_text fail
    sessions.save_session(history(), project_dir=p)
    out = rows(env)
    assert [r["outcome"] for r in out] == ["allowed", "failed"]
    assert out[1]["reason"] == "persistence write failed"
    path.rmdir()
    sessions.save_session(history(), project_dir=p)  # failed->allowed is a change
    assert [r["outcome"] for r in rows(env)] == ["allowed", "failed", "allowed"]


def test_empty_history_no_write_no_row(env):
    sessions.save_session([], project_dir=str(env.tmp / "p"))
    assert rows(env) == [] and not (env.tmp / "sessions").exists()


def test_clear_session_row_and_later_save_coalesced(env):
    p = str(env.tmp / "p")
    sessions.save_session(history(), project_dir=p)
    sessions.clear_session(p)
    assert not sessions._session_path(p).exists()
    sessions.save_session(history(), project_dir=p)  # allowed-after-allowed: coalesced
    out = rows(env)
    assert [r["action"] for r in out] == ["sessions.save_session", "sessions.clear_session"]
    assert out[1]["command"] == "clear session file"


def test_clear_session_missing_file_no_gate_no_row(env):
    sessions.clear_session(str(env.tmp / "none"))
    assert rows(env) == []


def test_clear_session_refusal_keeps_file(env, monkeypatch):
    p = str(env.tmp / "p")
    sessions.save_session(history(), project_dir=p)
    refuse_all(env, monkeypatch)
    with pytest.raises(RuntimeError, match="refused"):
        sessions.clear_session(p)
    assert sessions._session_path(p).exists()


def test_clear_session_unlink_failure_raises_original_with_static_row(env, monkeypatch):
    p = str(env.tmp / "p")
    sessions.save_session(history(), project_dir=p)
    path = sessions._session_path(p)
    monkeypatch.setattr(type(path), "unlink", Mock(side_effect=PermissionError(SECRET)))
    with pytest.raises(PermissionError, match=SECRET):
        sessions.clear_session(p)
    clear_row = rows(env)[-1]
    assert clear_row["outcome"] == "failed" and SECRET not in json.dumps(clear_row)


# ----------------------------------------------------------- task queue


def test_queue_saves_coalesced_per_queue_file(env):
    q = taskqueue.TaskQueue(name="n", project_dir=str(env.tmp / "proj-secret"))
    for i in range(10):
        q.add(f"task {i}")
    q.save()
    for t in list(q.tasks):
        q.mark_running(t.id)
        q.mark_done(t.id, "r")
    saved = json.loads(q._path.read_text())
    assert all(t["status"] == "done" for t in saved["tasks"])  # later saves landed
    (row,) = rows(env)  # 21 saves, 1 row
    assert {k: v for k, v in row.items() if k != "ts"} == {
        "authority": ag.ACT, "action": "taskqueue.save",
        "command": "persist task queue file", "outcome": "allowed", "reason": "command executed",
    }
    assert q._path.parent == env.tmp / "sessions" and q._path.name.startswith("queue_proj-secret_")
    assert "proj-secret" not in json.dumps(row)
    q2 = taskqueue.TaskQueue(name="m", project_dir=str(env.tmp / "other"))
    q2.add("x")
    q2.save()
    assert len(rows(env)) == 2  # one more per distinct queue file


def test_queue_refusal_raises_and_writes_nothing(env, monkeypatch):
    refuse_all(env, monkeypatch)
    q = taskqueue.TaskQueue(project_dir=str(env.tmp / "p"))
    q.add("t")
    with pytest.raises(RuntimeError, match="refused"):
        q.save()
    assert not (env.tmp / "sessions").exists()


def test_queue_write_failure_reraises_original_row_static(env):
    (env.tmp / "sessions").write_text("blocker")
    q = taskqueue.TaskQueue(project_dir=str(env.tmp / "p"))
    with pytest.raises(OSError):
        q.save()
    (row,) = rows(env)
    assert row["outcome"] == "failed" and row["reason"] == "persistence write failed"
    assert str(env.tmp) not in json.dumps(row)


def test_queue_roundtrip_load(env):
    q = taskqueue.TaskQueue(name="n", project_dir=str(env.tmp / "p"))
    q.add("t")
    q.save()
    loaded = taskqueue.TaskQueue.load(q._path)
    assert [t.description for t in loaded.tasks] == ["t"]


# ------------------------------------------------------------- finetune


@pytest.fixture
def ft(env, monkeypatch):
    example = {"conversations": [{"from": "human", "value": "q"}, {"from": "gpt", "value": "a"}]}
    curator = Mock()
    curator.curate_examples.return_value = [example]
    monkeypatch.setattr(fp, "DatasetCurator", Mock(return_value=curator))
    monkeypatch.setattr(fp, "print_instructions", Mock())
    return SimpleNamespace(curator=curator, out=env.tmp / "out-secret")


def test_finetune_export_one_static_row_and_same_return(env, ft):
    results = fp.prepare_finetune_data(model_variant="4b", output_dir=str(ft.out))
    assert set(results) == {"dataset", "notebook"}
    assert (ft.out / "codey-finetune-4b.jsonl").exists()
    (row,) = rows(env)
    assert {k: v for k, v in row.items() if k != "ts"} == {
        "authority": ag.ACT, "action": "finetune_prep.prepare_finetune_data",
        "command": "export finetune dataset", "outcome": "allowed", "reason": "command executed",
    }
    assert "out-secret" not in json.dumps(row)


def test_finetune_refusal_writes_nothing_and_returns_error(env, ft, monkeypatch):
    refuse_all(env, monkeypatch)
    results = fp.prepare_finetune_data(output_dir=str(ft.out))
    assert list(results) == ["error"] and "refused" in results["error"]
    assert not ft.out.exists()
    ft.curator.curate_examples.assert_not_called()


def test_finetune_no_examples_keeps_error_dict(env, ft):
    ft.curator.curate_examples.return_value = []
    assert fp.prepare_finetune_data(output_dir=str(ft.out)) == {"error": "No examples found"}


def test_finetune_original_exception_propagates_with_static_row(env, ft, monkeypatch):
    monkeypatch.setattr(fp, "export_dataset", Mock(side_effect=ValueError(SECRET)))
    with pytest.raises(ValueError, match=SECRET):
        fp.prepare_finetune_data(output_dir=str(ft.out))
    (row,) = rows(env)
    assert row["outcome"] == "failed" and row["reason"] == "finetune export failed"
    assert SECRET not in json.dumps(row)


def test_finetune_unknown_variant_still_raises_valueerror(env, ft):
    with pytest.raises(ValueError, match="Unknown model variant"):
        fp.prepare_finetune_data(model_variant="9z", output_dir=str(ft.out))
