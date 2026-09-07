"""
NEW-144 / TODO.md 7.4b sub-task A regression tests: a process that does not
own the embed server's lifecycle (today: `core/inference.py:_start_server()`,
called on every `infer()`) must health-check ONLY against an already-healthy
embed server and must NEVER fall into `EmbedServer.start()`'s kill-and-replace
path against an occupant it can positively confirm is healthy.

`core/embed_server.py:EmbedServer.start()`'s only "already running" fast path
checks `self.process` — this object's OWN spawned subprocess handle, `None`
in any process that didn't itself spawn the embed server. Before this fix,
falling through past that check, `start()` would see the port bound and
unconditionally kill+respawn it, even when a DIFFERENT (e.g. the daemon's)
process's embed server was perfectly healthy. The fix: `EmbedServer.is_healthy()`
is a real HTTP `/health` check against the known port, independent of which
process spawned the occupant, and `core/inference.py:_start_server()` calls
it first, only calling `start()` when it reports unhealthy.
"""
from unittest.mock import patch


from core.embed_server import EmbedServer


class TestIsHealthy:
    def test_is_healthy_true_delegates_to_check_health(self):
        srv = EmbedServer()
        with patch.object(EmbedServer, "_check_health", return_value=True):
            assert srv.is_healthy() is True

    def test_is_healthy_false_delegates_to_check_health(self):
        srv = EmbedServer()
        with patch.object(EmbedServer, "_check_health", return_value=False):
            assert srv.is_healthy() is False

    def test_is_healthy_does_not_require_self_process(self):
        """The whole point of NEW-144's fix: a fresh EmbedServer object
        (self.process is None, as in any process that didn't spawn the
        embed server itself) must still be able to positively confirm a
        foreign-but-healthy occupant via is_healthy() — it must not depend
        on self.process being set the way is_running() does."""
        srv = EmbedServer()
        assert srv.process is None
        with patch.object(EmbedServer, "_check_health", return_value=True):
            assert srv.is_healthy() is True


class TestInferenceStartServerHealthCheckOnly:
    """Drives the real embed block inside core/inference.py's _start_server()
    (not a reimplementation of its logic) against a mocked get_embed_server()
    singleton, to prove the health-check-only contract end to end."""

    def _run_embed_block(self, monkeypatch, healthy: bool):
        """Reproduces core.inference._start_server()'s embed-server branch
        verbatim (same get_embed_server()/is_healthy()/start() call shape),
        against a mock EmbedServer, so the test doesn't also have to spin up
        (or mock away) core.loader_v2's primary-model loader just to reach
        the embed block."""
        import core.inference as inference_mod

        mock_server = type(
            "MockEmbedServer",
            (),
            {
                "is_healthy": lambda self: healthy,
                "start": lambda self: True,
            },
        )()
        mock_server.start_calls = 0

        def _tracked_start(self=mock_server):
            mock_server.start_calls += 1
            return True

        mock_server.start = _tracked_start

        monkeypatch.setattr(
            "core.embed_server.get_embed_server", lambda: mock_server
        )

        # Exercise the exact code path _start_server() runs, via the real
        # module (not a copy of it), by calling the private helper directly
        # after stubbing out the primary-model loader so only the embed
        # block under test actually executes.
        with patch("core.loader_v2.get_loader") as mock_get_loader:
            mock_get_loader.return_value.ensure_model.return_value = True
            inference_mod._start_server()

        return mock_server

    def test_healthy_foreign_occupant_is_never_started(self, monkeypatch):
        """A second process's health-check-only call must NOT kill/restart a
        healthy first process's embed server — the exact NEW-144 regression."""
        mock_server = self._run_embed_block(monkeypatch, healthy=True)
        assert mock_server.start_calls == 0

    def test_unhealthy_or_absent_embed_server_is_started(self, monkeypatch):
        """When nothing answers /health (e.g. an interactive-only invocation
        that bypassed daemon startup, so no other process owns the embed
        lifecycle yet), _start_server() must still start it."""
        mock_server = self._run_embed_block(monkeypatch, healthy=False)
        assert mock_server.start_calls == 1
