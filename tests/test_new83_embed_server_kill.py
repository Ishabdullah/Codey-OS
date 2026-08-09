"""
NEW-83 regression tests: core/embed_server.py's `_kill_port_occupant()`
must never fall back to a bare `pkill -9 llama-server` name-pattern kill
(CLAUDE.md rule 3) — it must kill only a specific PID it has positively
identified as the port's occupant via /proc scanning, must verify the
port actually came free afterward, and must fail loudly (no kill at all,
or an explicit failure return) whenever it can't be sure.

Most tests use a mocked `os.kill` / `subprocess.run` and a fake /proc
layout — no real process is spawned or killed.
`test_find_port_occupant_pid_against_real_proc` is the one exception: it
binds a real listening socket in this test process (an ephemeral local
port, never touching anything CLAUDE.md guards) purely to exercise the
real /proc/net/tcp(+tcp6) parsing and fd-scan path end-to-end, since the
mocked-Path tests below validate control flow but not the actual hex/
state-code/inode parsing against a real kernel.
"""
import os
import socket
import subprocess
from unittest.mock import patch

import pytest

from core.embed_server import EmbedServer


class TestFindPortOccupantPid:
    def test_returns_none_when_proc_files_unreadable(self):
        srv = EmbedServer()
        with patch("builtins.open", side_effect=FileNotFoundError):
            assert srv._find_port_occupant_pid() is None

    def test_resolves_pid_from_matching_listen_socket_inode(self):
        srv = EmbedServer()
        srv.port = 8082
        port_hex = f"{srv.port:04X}"
        header = "  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode"
        listen_row = (
            f"   0: 0100007F:{port_hex} 00000000:0000 0A 00000000:00000000 "
            f"00:00000000 00000000  1000        0 987654 1 0 100 0 0 10 0"
        )

        def fake_open(path, *a, **k):
            import io

            if path == "/proc/net/tcp":
                return io.StringIO("\n".join([header, listen_row]))
            if path == "/proc/net/tcp6":
                return io.StringIO(header)
            raise FileNotFoundError(path)

        class FakePidDir:
            def __init__(self, name):
                self.name = name

            def __truediv__(self, other):
                return FakeFdDir(self.name)

        class FakeFdEntry:
            def __init__(self, pid):
                self._pid = pid

            def __str__(self):
                return f"/proc/{self._pid}/fd/3"

        class FakeFdDir:
            def __init__(self, pid):
                self._pid = pid

            def iterdir(self):
                return [FakeFdEntry(self._pid)]

        def fake_readlink(path):
            # Only pid 4242's fd points at our target inode.
            if "/proc/4242/" in path:
                return "socket:[987654]"
            return "socket:[111111]"

        with patch("builtins.open", side_effect=fake_open), patch(
            "core.embed_server.Path"
        ) as fake_path_cls, patch("os.readlink", side_effect=fake_readlink):
            fake_path_cls.return_value.iterdir.return_value = [
                FakePidDir("4242"),
                FakePidDir("notapid"),
            ]
            pid = srv._find_port_occupant_pid()

        assert pid == 4242

    def test_prefers_listen_row_and_keeps_scanning_on_unresolved_match(self):
        """A non-LISTEN row matching the port's hex suffix (e.g. a stale
        connection) must not cause a premature give-up — the LISTEN row's
        inode should still be resolved."""
        srv = EmbedServer()
        srv.port = 8082
        port_hex = f"{srv.port:04X}"
        header = "  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode"
        # Non-LISTEN row first with an inode that resolves to no PID,
        # LISTEN row second with the real occupant's inode. Column layout
        # matches the real kernel format used in the test above (colon-
        # joined tx:rx and tr:tm->when fields count as single columns).
        stale_row = (
            f"   0: 0100007F:{port_hex} 00000000:0000 08 00000000:00000000 "
            f"00:00000000 00000000  1000        0 111 1 0 100 0 0 10 0"
        )
        listen_row = (
            f"   1: 0100007F:{port_hex} 00000000:0000 0A 00000000:00000000 "
            f"00:00000000 00000000  1000        0 987654 1 0 100 0 0 10 0"
        )

        def fake_open(path, *a, **k):
            import io

            if path == "/proc/net/tcp":
                return io.StringIO("\n".join([header, stale_row, listen_row]))
            if path == "/proc/net/tcp6":
                return io.StringIO(header)
            raise FileNotFoundError(path)

        with patch("builtins.open", side_effect=fake_open), patch.object(
            EmbedServer, "_pid_owning_inode", side_effect=lambda inode: {"987654": 4242}.get(inode)
        ):
            pid = srv._find_port_occupant_pid()

        assert pid == 4242

    def test_find_port_occupant_pid_against_real_proc(self):
        """End-to-end sanity check against the real kernel's /proc — binds
        an actual listening socket in this test process (not the embed
        server, no llama-server involved) and confirms the scan correctly
        resolves it back to os.getpid(). This is what the mocked tests
        above can't verify: real hex formatting, state-code filtering, and
        the fd-symlink match against real inodes.

        Skips (doesn't fail) if this sandbox denies read access to
        /proc/net/tcp — confirmed present in this dev sandbox
        (PermissionError), and NOT something this test can work around:
        it's exactly the condition `_find_port_occupant_pid()` must
        already handle by falling through to the registered-slot fallback
        or failing loudly, which the other tests in this file cover with
        mocks. Whether real Termux/Android denies this too (in which case
        the /proc-scan path is effectively dead on-device and the
        registered-slot fallback / fail-loud path is the one that matters
        in practice) needs live-verifier confirmation, not a sandbox
        assumption either way.
        """
        try:
            open("/proc/net/tcp").close()
        except PermissionError:
            pytest.skip(
                "/proc/net/tcp not readable in this sandbox — needs "
                "on-device (live-verifier) confirmation of real behavior"
            )

        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        port = s.getsockname()[1]
        try:
            srv = EmbedServer()
            srv.port = port
            pid = srv._find_port_occupant_pid()
        finally:
            s.close()

        assert pid == os.getpid()


class TestRegisteredSlotFallback:
    """Covers the secondary PID source used when the /proc scan itself
    can't identify an occupant (e.g. permission-restricted /proc/net/tcp)
    — a PID this code itself previously registered via resource_gate,
    verified alive and cmdline-confirmed as llama-server before use."""

    def test_uses_registered_slot_pid_when_alive_and_cmdline_matches(self):
        srv = EmbedServer()
        srv.port = 8082
        fake_slots = [{"model_id": "embed", "port": 8082, "pid": 4242}]
        with patch("core.embed_server.rg.list_slots", return_value=fake_slots), patch(
            "os.kill"
        ) as fake_os_kill, patch.object(
            EmbedServer, "_cmdline_is_llama_server", return_value=True
        ):
            pid = srv._find_pid_via_registered_slot()

        assert pid == 4242
        fake_os_kill.assert_called_once_with(4242, 0)  # liveness probe only

    def test_ignores_slot_for_a_different_port(self):
        srv = EmbedServer()
        srv.port = 8082
        fake_slots = [{"model_id": "embed", "port": 9999, "pid": 4242}]
        with patch("core.embed_server.rg.list_slots", return_value=fake_slots):
            assert srv._find_pid_via_registered_slot() is None

    def test_ignores_dead_pid(self):
        srv = EmbedServer()
        srv.port = 8082
        fake_slots = [{"model_id": "embed", "port": 8082, "pid": 4242}]
        with patch("core.embed_server.rg.list_slots", return_value=fake_slots), patch(
            "os.kill", side_effect=ProcessLookupError
        ):
            assert srv._find_pid_via_registered_slot() is None

    def test_ignores_recycled_pid_whose_cmdline_is_not_llama_server(self):
        """PID reuse guard: alive is not enough — must be llama-server."""
        srv = EmbedServer()
        srv.port = 8082
        fake_slots = [{"model_id": "embed", "port": 8082, "pid": 4242}]
        with patch("core.embed_server.rg.list_slots", return_value=fake_slots), patch(
            "os.kill"
        ), patch.object(EmbedServer, "_cmdline_is_llama_server", return_value=False):
            assert srv._find_pid_via_registered_slot() is None

    def test_cmdline_is_llama_server_reads_real_proc_cmdline_for_self(self):
        assert EmbedServer._cmdline_is_llama_server(os.getpid()) is False


class TestKillPortOccupant:
    def test_kills_only_the_resolved_pid_no_bare_pkill(self):
        srv = EmbedServer()
        with patch.object(srv, "_find_port_occupant_pid", return_value=4242), patch(
            "os.kill"
        ) as fake_kill, patch("subprocess.run") as fake_run, patch(
            "time.sleep"
        ), patch.object(srv, "_port_is_bound", return_value=False):
            ok = srv._kill_port_occupant()

        assert ok is True
        fake_kill.assert_called_once_with(4242, 9)
        # The whole point of NEW-83: no bare name-pattern kill anywhere.
        fake_run.assert_not_called()

    def test_fails_loudly_when_occupant_pid_unknown_no_kill_attempted(self):
        srv = EmbedServer()
        with patch.object(srv, "_find_port_occupant_pid", return_value=None), patch(
            "os.kill"
        ) as fake_kill, patch("subprocess.run") as fake_run:
            ok = srv._kill_port_occupant()

        assert ok is False
        fake_kill.assert_not_called()
        fake_run.assert_not_called()

    def test_fails_when_port_still_bound_after_kill_no_escalation_to_pkill(self):
        """A session-leader-only kill can leave a child holding the port
        (the process was spawned with preexec_fn=os.setsid). Must report
        failure, not success, and must not escalate to killpg/pkill."""
        srv = EmbedServer()
        with patch.object(srv, "_find_port_occupant_pid", return_value=4242), patch(
            "os.kill"
        ) as fake_kill, patch("os.killpg") as fake_killpg, patch(
            "subprocess.run"
        ) as fake_run, patch("time.sleep"), patch.object(
            srv, "_port_is_bound", return_value=True
        ):
            ok = srv._kill_port_occupant()

        assert ok is False
        fake_kill.assert_called_once_with(4242, 9)
        fake_killpg.assert_not_called()
        fake_run.assert_not_called()

    def test_start_aborts_without_binding_when_port_cannot_be_cleared(self):
        srv = EmbedServer()
        with patch.object(srv, "process", None), patch.object(
            srv, "_check_health", return_value=False
        ), patch.object(srv, "_port_is_bound", return_value=True), patch.object(
            srv, "_kill_port_occupant", return_value=False
        ) as fake_kill, patch("subprocess.Popen") as fake_popen:
            result = srv.start()

        assert result is False
        fake_kill.assert_called_once()
        fake_popen.assert_not_called()

    def test_start_clears_port_even_when_occupant_never_answers_health(self):
        """A foreign occupant that accepts the TCP connection but never
        answers /health must still trigger port-clearing — start() must
        gate on the raw bind check (_port_is_bound), not _is_port_open()
        (which requires a successful /health response and would
        therefore skip clearing here, leading Popen to bind against an
        occupied port)."""
        srv = EmbedServer()
        with patch.object(srv, "process", None), patch.object(
            srv, "_check_health", return_value=False
        ), patch.object(srv, "_is_port_open", return_value=False), patch.object(
            srv, "_port_is_bound", return_value=True
        ), patch.object(
            srv, "_kill_port_occupant", return_value=False
        ) as fake_kill, patch("subprocess.Popen") as fake_popen:
            result = srv.start()

        assert result is False
        fake_kill.assert_called_once()
        fake_popen.assert_not_called()

    def test_no_bare_pkill_subprocess_call_reachable_in_module_source(self):
        """Static guard: the literal name-pattern kill invocation must not
        reappear (module docstring mentions `codeydOS stop`'s separate
        `pkill llama-server` lifecycle note, which is fine — this checks
        for an actual subprocess call, not the substring "pkill")."""
        import inspect

        import core.embed_server as mod

        src = inspect.getsource(mod)
        assert '"pkill"' not in src
        assert "'pkill'" not in src
