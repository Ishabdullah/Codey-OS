"""gate_exec(coalesce_key=...) and the bookkeeping persistence built on it.

Policy is consulted on every call; only repeat identical non-refused outcomes
for the same (action, key) skip the audit row. All state is tmp.
"""

import json
import threading

import pytest

import core.action_gateway as ag
import core.sessions as sessions
import core.taskqueue as taskqueue

SECRET_KEY = "/very/secret/path/file.json"


def make(tmp_path):
    audit = tmp_path / "audit.jsonl"
    return ag.ActionGateway(audit_file=audit), audit


def rows(audit):
    if not audit.exists():
        return []
    return [json.loads(x) for x in audit.read_text().splitlines()]


def ok():
    return "r"


def boom():
    raise RuntimeError("static")


def call(gw, execute=ok, key=None, authority=ag.ACT, action="a", **kw):
    return gw.gate_exec(
        authority=authority, action=action, command="c", confirm_available=False,
        execute=execute, **({"coalesce_key": key} if key is not None else {}), **kw,
    )


def strip(rs):
    return [{k: v for k, v in r.items() if k != "ts"} for r in rs]


def test_default_unchanged_byte_for_byte(tmp_path):
    seq = [ok, ok, boom, boom, ok]
    out = {}
    for name, key in (("plain", None), ("explicit_none", "NONE")):
        (tmp_path / name).mkdir()
        gw, audit = make(tmp_path / name)
        for ex in seq:
            if key == "NONE":
                gw.gate_exec(authority=ag.ACT, action="a", command="c", confirm_available=False,
                             execute=ex, coalesce_key=None)
            else:
                call(gw, ex)
        out[name] = strip(rows(audit))
    assert len(out["plain"]) == 5 and out["plain"] == out["explicit_none"]


def test_coalesces_repeat_allowed(tmp_path):
    gw, audit = make(tmp_path)
    for _ in range(25):
        assert call(gw, key="k").allowed
    assert len(rows(audit)) == 1


def test_persistent_failure_one_row(tmp_path):
    gw, audit = make(tmp_path)
    for _ in range(30):
        assert call(gw, boom, key="k").outcome == ag.OUTCOME_FAILED
    out = rows(audit)
    assert len(out) == 1 and out[0]["reason"] == "static"


def test_transitions_each_write_a_row(tmp_path):
    gw, audit = make(tmp_path)
    for ex in (ok, ok, boom, boom, ok, ok, boom):
        call(gw, ex, key="k")
    assert [r["outcome"] for r in rows(audit)] == ["allowed", "failed", "allowed", "failed"]


def test_refusal_always_written_and_resets_state(tmp_path):
    gw, audit = make(tmp_path)
    call(gw, key="k")
    for _ in range(3):
        d = call(gw, key="k", authority=ag.HIGH_IMPACT)  # fail-closed refusal
        assert d.outcome == ag.OUTCOME_REFUSED
    assert [r["outcome"] for r in rows(audit)] == ["allowed", "refused", "refused", "refused"]
    # HIGH_IMPACT ignores coalesce_key, so refusals neither touch nor reset
    # the ACT dedupe state: a repeat ACT allowed stays coalesced.
    call(gw, key="k")
    assert len(rows(audit)) == 4


def test_refusal_via_confirm_callback_always_written(tmp_path):
    gw, audit = make(tmp_path)
    for _ in range(3):
        d = gw.gate_exec(authority=ag.HIGH_IMPACT, action="a", command="c", confirm_available=True,
                         execute=ok, confirm=lambda: False, coalesce_key="k")
        assert d.outcome == ag.OUTCOME_REFUSED
    assert len(rows(audit)) == 3


def test_policy_reconsulted_every_call(tmp_path):
    """Later saves of a known key still hit the policy: a fail-closed
    HIGH_IMPACT authority (stand-in for any future deny) refuses and never
    executes after earlier allowed calls."""
    gw, audit = make(tmp_path)
    ran = []

    def ex():
        ran.append(1)
        return "r"

    assert call(gw, ex, key="k").allowed and call(gw, ex, key="k").allowed
    d = call(gw, ex, key="k", authority=ag.HIGH_IMPACT)
    assert not d.allowed and len(ran) == 2


def test_keys_and_actions_independent(tmp_path):
    gw, audit = make(tmp_path)
    call(gw, key="a")
    call(gw, key="b")
    call(gw, key="a", action="other")
    call(gw, key="a")
    assert len(rows(audit)) == 3


def test_key_never_in_audit_bytes(tmp_path):
    gw, audit = make(tmp_path)
    call(gw, key=SECRET_KEY)
    call(gw, boom, key=SECRET_KEY)
    call(gw, key=SECRET_KEY, authority=ag.HIGH_IMPACT)
    raw = audit.read_bytes()
    assert b"secret" not in raw and b"file.json" not in raw


def test_eviction_cap_is_bounded_and_only_over_audits(tmp_path, monkeypatch):
    monkeypatch.setattr(ag, "COALESCE_MAX_KEYS", 3)
    gw, audit = make(tmp_path)
    for k in "abcd":
        call(gw, key=k)
    assert len(gw._coalesce) == 3
    n = len(rows(audit))
    call(gw, key="d")  # still remembered: coalesced
    assert len(rows(audit)) == n
    call(gw, key="a")  # evicted: audited again (extra row, never a missing one)
    assert len(rows(audit)) == n + 1
    assert len(gw._coalesce) == 3


def test_thread_safety_smoke(tmp_path):
    gw, audit = make(tmp_path)
    errors = []

    def work(i):
        try:
            for _ in range(200):
                call(gw, key=f"k{i % 4}")
        except Exception as e:  # pragma: no cover
            errors.append(e)

    ts = [threading.Thread(target=work, args=(i,)) for i in range(8)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert not errors
    assert len(rows(audit)) == 4  # one allowed row per distinct key


def test_high_impact_key_ignored_approved_every_row(tmp_path):
    gw, audit = make(tmp_path)
    for _ in range(4):
        d = gw.gate_exec(authority=ag.HIGH_IMPACT, action="a", command="c", confirm_available=True,
                         execute=ok, confirm=lambda: True, coalesce_key="k")
        assert d.allowed
    assert [r["outcome"] for r in rows(audit)] == ["allowed"] * 4
    assert not gw._coalesce


def test_high_impact_key_ignored_failures_every_row(tmp_path):
    gw, audit = make(tmp_path)
    for _ in range(4):
        d = gw.gate_exec(authority=ag.HIGH_IMPACT, action="a", command="c", confirm_available=True,
                         execute=boom, confirm=lambda: True, coalesce_key="k")
        assert d.outcome == ag.OUTCOME_FAILED
    assert [r["outcome"] for r in rows(audit)] == ["failed"] * 4
    assert not gw._coalesce


def test_act_still_coalesces_after_authority_restriction(tmp_path):
    gw, audit = make(tmp_path)
    for _ in range(5):
        call(gw, key="k")
        call(gw, boom, key="k")
    assert [r["outcome"] for r in rows(audit)] == ["allowed", "failed"] * 5
    (tmp_path / "x").mkdir()
    gw2, audit2 = make(tmp_path / "x")
    for _ in range(5):
        call(gw2, key="k")
    assert len(rows(audit2)) == 1


def test_nul_in_action_does_not_collide_dedupe_state(tmp_path):
    gw, audit = make(tmp_path)
    call(gw, action="a\0b", key="c")
    call(gw, action="a", key="b\0c")
    assert len(rows(audit)) == 2
    assert len(gw._coalesce) == 2
    call(gw, action="a\0b", key="c")  # same pair repeats: coalesced
    assert len(rows(audit)) == 2


# ------------------------------------------- end-to-end via bookkeeping


@pytest.fixture
def env(tmp_path, monkeypatch):
    gw, audit = make(tmp_path)
    monkeypatch.setattr(ag, "_gateway", gw)
    monkeypatch.setattr(sessions, "SESSIONS_DIR", tmp_path / "sessions")
    monkeypatch.setattr(taskqueue, "SESSIONS_DIR", tmp_path / "sessions")
    return tmp_path, gw, audit


def hist():
    return [{"role": "user", "content": "q"}, {"role": "assistant", "content": "a"}]


def test_25_session_saves_one_row_and_gate_called_each_time(env, monkeypatch):
    tmp, gw, audit = env
    real = gw.gate_exec
    calls = []
    monkeypatch.setattr(gw, "gate_exec", lambda **kw: (calls.append(1), real(**kw))[1])
    for _ in range(25):
        sessions.save_session(hist(), project_dir=str(tmp / "p"))
    assert len(calls) == 25 and len(rows(audit)) == 1


def test_21_queue_saves_one_row(env):
    tmp, gw, audit = env
    q = taskqueue.TaskQueue(name="n", project_dir=str(tmp / "p"))
    for i in range(10):
        q.add(f"t{i}")
    q.save()
    for t in list(q.tasks):
        q.mark_running(t.id)
        q.mark_done(t.id, "r")
    assert len(rows(audit)) == 1


def test_later_session_save_refused_after_earlier_allowed(env, monkeypatch):
    tmp, gw, audit = env
    p = str(tmp / "p")
    sessions.save_session(hist(), project_dir=p)
    path = sessions._session_path(p)
    before = path.read_text()
    real = gw.gate_exec

    def deny(**kw):
        return real(**{**kw, "authority": ag.HIGH_IMPACT})  # fail-closed refusal

    monkeypatch.setattr(gw, "gate_exec", deny)
    sessions.save_session(hist() * 3, project_dir=p)
    sessions.save_session(hist() * 3, project_dir=p)
    assert path.read_text() == before  # nothing written
    assert [r["outcome"] for r in rows(audit)] == ["allowed", "refused", "refused"]


def test_persistent_session_failure_one_failed_row(env):
    tmp, gw, audit = env
    (tmp / "sessions").write_text("blocker")
    for _ in range(10):
        sessions.save_session(hist(), project_dir=str(tmp / "p"))
    out = rows(audit)
    assert [r["outcome"] for r in out] == ["failed"]
    assert str(tmp) not in json.dumps(out)
