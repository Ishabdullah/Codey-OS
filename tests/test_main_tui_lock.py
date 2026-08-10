"""
main.py's `_write_tui_pid_file()` / `_remove_tui_pid_file()` — Track 3
Phase 5a / 7.4 sub-task B (TUI half of the interactive-session signal).

Synthetic fixtures throughout: `utils.config.TUI_SESSIONS_DIR` is
monkeypatched to a tmp_path directory for every test here, and
`os.getpid()`/a real-but-dead subprocess PID (never a guessed number)
stand in for "this process" / "some other, no-longer-running process" —
no dependency on actually running main.py's repl() or a real daemon.

Each interactive session gets its own file, `TUI_SESSIONS_DIR /
f"{pid}.pid"` — not one shared file — so that two concurrent sessions
(a normal, supported case here) can never overwrite each other's entry.
One test (`test_two_concurrent_sessions_do_not_destroy_each_others_signal`)
uses `os.fork()` so a genuinely separate PID exercises the real
`_write_tui_pid_file()`/`_remove_tui_pid_file()` code paths concurrently
with this process's own, rather than hand-placing a second session's file.
"""
import os
import subprocess

import pytest

import main as main_mod
import utils.config as config_mod


@pytest.fixture
def tui_sessions_dir(tmp_path, monkeypatch):
    path = tmp_path / "tui-sessions"
    monkeypatch.setattr(config_mod, "TUI_SESSIONS_DIR", path)
    return path


def _own_session_file(sessions_dir):
    return sessions_dir / f"{os.getpid()}.pid"


def test_write_tui_pid_file_writes_own_pid(tui_sessions_dir):
    main_mod._write_tui_pid_file()
    session_file = _own_session_file(tui_sessions_dir)
    assert session_file.exists()
    assert int(session_file.read_text().strip()) == os.getpid()


def test_remove_tui_pid_file_removes_own_entry(tui_sessions_dir):
    main_mod._write_tui_pid_file()
    main_mod._remove_tui_pid_file()
    assert not _own_session_file(tui_sessions_dir).exists()


def test_remove_tui_pid_file_missing_file_does_not_raise(tui_sessions_dir):
    # Nothing written yet — must be a safe no-op, not an exception, since
    # this runs in a `finally` block around repl().
    main_mod._remove_tui_pid_file()
    assert not _own_session_file(tui_sessions_dir).exists()


def test_remove_tui_pid_file_does_not_delete_other_sessions_pid(tui_sessions_dir):
    # A second concurrent interactive session (a different terminal) has
    # its own file under TUI_SESSIONS_DIR — this session's removal must
    # only ever touch its own PID-named path, never another session's.
    #
    # Deliberately uses a real-but-now-DEAD PID (not a live one) to prove
    # the "other" file is left alone purely because it's a different path
    # (ownership is structural now, not a liveness check) — reaping a
    # genuinely stale (dead-PID) entry is deliberately not this function's
    # job, that's is_tui_session_active()'s self-healing responsibility.
    proc = subprocess.Popen(["true"])
    other_dead_pid = proc.pid
    proc.wait()

    main_mod._write_tui_pid_file()
    other_session_file = tui_sessions_dir / f"{other_dead_pid}.pid"
    other_session_file.write_text(str(other_dead_pid))

    main_mod._remove_tui_pid_file()

    # This session's own file is gone, but the other session's file (a
    # different path entirely) must be left alone.
    assert not _own_session_file(tui_sessions_dir).exists()
    assert other_session_file.exists()
    assert int(other_session_file.read_text().strip()) == other_dead_pid


def test_remove_tui_pid_file_corrupt_content_does_not_raise(tui_sessions_dir):
    # Ownership here is path-based (this session's file is always
    # TUI_SESSIONS_DIR / f"{os.getpid()}.pid"), not content-based, so
    # corrupt content in this process's OWN file must not block its own
    # removal (unlike the old single-shared-file design, which had to
    # read-back-and-compare content before deciding whether removal was
    # safe). Must not raise, since this runs in a `finally` block around
    # repl().
    session_file = _own_session_file(tui_sessions_dir)
    tui_sessions_dir.mkdir(parents=True, exist_ok=True)
    session_file.write_text("not-a-pid")
    main_mod._remove_tui_pid_file()
    assert not session_file.exists()


def test_write_then_resource_gate_sees_it_active(tui_sessions_dir):
    import core.resource_gate as rg

    main_mod._write_tui_pid_file()
    assert rg.is_tui_session_active(sessions_dir=tui_sessions_dir) is True
    main_mod._remove_tui_pid_file()
    assert rg.is_tui_session_active(sessions_dir=tui_sessions_dir) is False


def test_two_concurrent_sessions_do_not_destroy_each_others_signal(tui_sessions_dir):
    # The regression this whole fix is for: session A writes and is live;
    # session B (a real, different PID — a forked child, not a hand-placed
    # file) starts, writes its own entry via the SAME real
    # _write_tui_pid_file()/_remove_tui_pid_file() code path A uses, and
    # must NOT overwrite/destroy A's. Both must be independently
    # representable at once, removing one must not disturb the other, and
    # the composed signal must track exactly which sessions are still
    # present. Uses os.fork() (not subprocess) specifically so the child
    # inherits this test's monkeypatched config_mod.TUI_SESSIONS_DIR from
    # the parent's memory image, letting it call the real functions
    # against the same tmp_path fixture.
    import core.resource_gate as rg

    pid_a = os.getpid()
    session_a = tui_sessions_dir / f"{pid_a}.pid"
    main_mod._write_tui_pid_file()
    assert session_a.exists()

    child_ready_r, child_ready_w = os.pipe()
    parent_go_r, parent_go_w = os.pipe()

    child_pid = os.fork()
    if child_pid == 0:
        # Session B, running as a real separate PID: write its own real
        # lock, signal readiness, block until told to remove it and exit.
        os.close(child_ready_r)
        os.close(parent_go_w)
        try:
            main_mod._write_tui_pid_file()
            os.write(child_ready_w, b"1")
            os.read(parent_go_r, 1)
            main_mod._remove_tui_pid_file()
        finally:
            os._exit(0)

    os.close(child_ready_w)
    os.close(parent_go_r)
    session_b = tui_sessions_dir / f"{child_pid}.pid"
    try:
        os.read(child_ready_r, 1)  # blocks until B's real write has landed

        # B's real write must not have disturbed A's real entry.
        assert session_a.exists()
        assert int(session_a.read_text().strip()) == pid_a
        assert session_b.exists()
        assert int(session_b.read_text().strip()) == child_pid
        assert rg.is_tui_session_active(sessions_dir=tui_sessions_dir) is True
    finally:
        os.close(child_ready_r)
        # Closing the write end (even if an assertion above failed) sends
        # EOF rather than leaving the child blocked on read() forever.
        os.close(parent_go_w)
        os.waitpid(child_pid, 0)

    # A's entry and the composed signal must survive B's real removal.
    assert session_a.exists()
    assert not session_b.exists()
    assert rg.is_tui_session_active(sessions_dir=tui_sessions_dir) is True

    # A exits too, via the real function — now nothing is left.
    main_mod._remove_tui_pid_file()
    assert not session_a.exists()
    assert rg.is_tui_session_active(sessions_dir=tui_sessions_dir) is False
