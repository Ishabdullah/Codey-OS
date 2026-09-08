"""
NEW-68 regression tests: core/inference.py's _start_server() must retry a
small bounded number of times when ensure_model() returns a transient
False with outcome LOAD_OUTCOME_DEFERRED (SWAP_GUARD busy elsewhere in-
process — see core/loader_v2.py's ensure_model() docstring), rather than
raising immediately as if it were a genuine, permanent load failure. Any
OTHER failure outcome (e.g. LOAD_OUTCOME_GATE_DENIED_HARD) must still
raise immediately with no retry.
"""
from unittest.mock import MagicMock, patch

import pytest

import core.inference as inference_mod
from core.loader_v2 import LOAD_OUTCOME_DEFERRED, LOAD_OUTCOME_GATE_DENIED_HARD


class TestStartServerDeferredRetry:
    def _patched(self, monkeypatch):
        # Avoid the real embed-server health-check branch — irrelevant to
        # this fix, and covered by tests/test_new144_embed_health_check_only.py.
        mock_embed = MagicMock()
        mock_embed.is_healthy.return_value = True
        monkeypatch.setattr(
            "core.embed_server.get_embed_server", lambda: mock_embed
        )
        monkeypatch.setattr(inference_mod.time, "sleep", lambda _s: None)

    def test_retries_and_succeeds_after_deferred_outcomes(self, monkeypatch):
        self._patched(monkeypatch)

        mock_loader = MagicMock()
        # First two calls: deferred (False). Third call: succeeds (True).
        mock_loader.ensure_model.side_effect = [False, False, True]
        mock_loader.get_last_ensure_outcome.return_value = LOAD_OUTCOME_DEFERRED

        with patch("core.loader_v2.get_loader", return_value=mock_loader):
            inference_mod._start_server()  # must not raise

        assert mock_loader.ensure_model.call_count == 3

    def test_non_deferred_failure_raises_immediately_no_retry(self, monkeypatch):
        self._patched(monkeypatch)

        mock_loader = MagicMock()
        mock_loader.ensure_model.return_value = False
        mock_loader.get_last_ensure_outcome.return_value = (
            LOAD_OUTCOME_GATE_DENIED_HARD
        )

        with patch("core.loader_v2.get_loader", return_value=mock_loader):
            with pytest.raises(RuntimeError):
                inference_mod._start_server()

        assert mock_loader.ensure_model.call_count == 1

    def test_deferred_outcome_exhausts_retries_then_raises(self, monkeypatch):
        self._patched(monkeypatch)

        mock_loader = MagicMock()
        mock_loader.ensure_model.return_value = False
        mock_loader.get_last_ensure_outcome.return_value = LOAD_OUTCOME_DEFERRED

        with patch("core.loader_v2.get_loader", return_value=mock_loader):
            with pytest.raises(RuntimeError):
                inference_mod._start_server()

        # 3 bounded attempts, all deferred, then give up.
        assert mock_loader.ensure_model.call_count == 3
