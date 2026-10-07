"""
WP0.1 (CODEY_OS_MASTER_BLUEPRINT.md §21, NEW-764): http-server.js's
/send-email, /send-invite, /send-cancellation now require a shared
bearer token. This covers NotificationService's side of that contract --
the token is attached when configured, and omitted (not fabricated) when
it isn't, so an unconfigured deployment gets a real 401 from the server
rather than this client silently claiming success.
"""
import json
from unittest.mock import MagicMock, patch

from restoricon_core.services.notification_service import NotificationService


def _fake_200_response():
    fake_response = MagicMock()
    fake_response.getcode.return_value = 200
    fake_response.__enter__.return_value = fake_response
    fake_response.__exit__.return_value = False
    return fake_response


def test_send_email_attaches_bearer_token_from_env(monkeypatch):
    monkeypatch.setenv("AIGENTIK_INTERNAL_TOKEN", "test-shared-secret")
    svc = NotificationService(aigentik_api_url="http://127.0.0.1:8081")

    with patch("urllib.request.urlopen", return_value=_fake_200_response()) as mock_urlopen:
        result = svc.send_email("alice@example.com", "subj", "body")

    assert result is True
    req = mock_urlopen.call_args.args[0]
    assert req.get_header("Authorization") == "Bearer test-shared-secret"


def test_send_calendar_invite_attaches_bearer_token_from_env(monkeypatch):
    monkeypatch.setenv("AIGENTIK_INTERNAL_TOKEN", "test-shared-secret")
    svc = NotificationService(aigentik_api_url="http://127.0.0.1:8081")

    with patch("urllib.request.urlopen", return_value=_fake_200_response()) as mock_urlopen:
        svc.send_calendar_invite("alice@example.com", {"uid": "x"}, "text")

    req = mock_urlopen.call_args.args[0]
    assert req.get_header("Authorization") == "Bearer test-shared-secret"


def test_send_email_sends_no_auth_header_when_token_unconfigured(monkeypatch):
    monkeypatch.delenv("AIGENTIK_INTERNAL_TOKEN", raising=False)
    monkeypatch.setattr(
        "restoricon_core.services.notification_service.get_aigentik_internal_token",
        lambda: None,
    )
    svc = NotificationService(aigentik_api_url="http://127.0.0.1:8081")

    with patch("urllib.request.urlopen", return_value=_fake_200_response()) as mock_urlopen:
        svc.send_email("alice@example.com", "subj", "body")

    req = mock_urlopen.call_args.args[0]
    assert req.get_header("Authorization") is None
    body = json.loads(req.data.decode("utf-8"))
    assert body["to"] == "alice@example.com"
