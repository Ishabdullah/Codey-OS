"""
NEW-74 (2026-09-08 closeout, daemon/process-lifecycle ledger sub-batch 2):
`LlamaServer.stop()` used to be a totally silent no-op when called on an
adopted-not-spawned server (`self.process is None`, `self._started ==
True` — every one of `start()`'s reuse/adoption branches leaves `self.
process` unset) — no error, no log, no signal to the caller that nothing
actually happened. Fixed by making `stop()` return `False` and log a
warning in that state, and `True` when it actually tore down a process it
spawned.

Deliberately conservative per CLAUDE.md rule 4 (daemon/kill-logic changes
need code-reviewer approval) and rule 3 (never kill by bare name
pattern): this does NOT give `stop()` new authority to kill an adopted
PID it never spawned — see `LlamaServer.stop()`'s own docstring for why
that's a separate design decision, flagged rather than made here.

No real llama-server process is spawned or killed by these tests (RAM
discipline, CLAUDE.md rule 2) — `self.process` is either left `None`
(simulating adoption) or a `MagicMock` standing in for a real
`subprocess.Popen` handle.
"""
from unittest.mock import MagicMock

import core.loader_v2 as lv


def test_stop_on_adopted_server_is_a_signalled_noop(monkeypatch):
    """Adopted state: self.process is None but self._started is True
    (start()'s reuse/adoption branches). stop() must not silently do
    nothing — it must return False and log a warning."""
    server = lv.LlamaServer("/fake/model.gguf", port=1234, n_ctx=4096)
    server.process = None
    server._started = True

    warnings = []
    monkeypatch.setattr(lv, "warning", lambda msg: warnings.append(msg))

    result = server.stop()

    assert result is False
    assert len(warnings) == 1
    assert "never spawned" in warnings[0]
    # Bookkeeping for a state this instance never controlled must be left
    # alone — it genuinely doesn't know whether the adopted server is
    # still up, so it must not claim otherwise via _started.
    assert server._started is True


def test_stop_when_never_started_is_a_quiet_noop(monkeypatch):
    """A LlamaServer that was never start()'d at all (process=None,
    _started=False) has nothing adopted to warn about either — stays a
    quiet no-op, not a warning."""
    server = lv.LlamaServer("/fake/model.gguf", port=1234, n_ctx=4096)

    warnings = []
    monkeypatch.setattr(lv, "warning", lambda msg: warnings.append(msg))

    result = server.stop()

    assert result is False
    assert warnings == []


def test_stop_swallowed_teardown_exception_returns_false_not_true(monkeypatch):
    """If signalling/waiting on a genuinely-spawned process hits an
    unexpected exception (not the already-handled ProcessLookupError/
    TimeoutExpired cases), stop() must not claim success — this is the
    same "dishonest signal" shape as NEW-74 itself, and must not be
    reintroduced by the fix."""
    server = lv.LlamaServer("/fake/model.gguf", port=1234, n_ctx=4096)
    fake_proc = MagicMock()
    fake_proc.pid = 4242
    server.process = fake_proc
    server._started = True

    monkeypatch.setattr(
        lv.os, "killpg", MagicMock(side_effect=OSError("unexpected teardown failure"))
    )
    monkeypatch.setattr(lv.os, "getpgid", MagicMock(return_value=4242))

    warnings = []
    monkeypatch.setattr(lv, "warning", lambda msg: warnings.append(msg))

    result = server.stop()

    assert result is False
    assert len(warnings) == 1
    assert "unexpected error during teardown" in warnings[0]
    # Bookkeeping is still reset — this instance is done trying either way.
    assert server.process is None
    assert server._started is False


def test_stop_on_genuinely_spawned_process_still_kills_and_returns_true(monkeypatch):
    """Baseline regression: the normal (non-adopted) case must be
    unaffected by this fix — a process this instance actually spawned is
    still torn down, and stop() now reports that with True."""
    server = lv.LlamaServer("/fake/model.gguf", port=1234, n_ctx=4096)
    fake_proc = MagicMock()
    fake_proc.pid = 4242
    fake_proc.wait.return_value = None
    server.process = fake_proc
    server._started = True

    monkeypatch.setattr(lv.os, "killpg", MagicMock())
    monkeypatch.setattr(lv.os, "getpgid", MagicMock(return_value=4242))

    result = server.stop()

    assert result is True
    assert server.process is None
    assert server._started is False
    lv.os.killpg.assert_called_once()
