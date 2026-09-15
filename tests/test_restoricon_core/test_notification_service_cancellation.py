"""
NEW-506: light unit test for NotificationService.send_calendar_cancellation,
mirroring how send_calendar_invite's own HTTP call shape would be tested
(no pre-existing dedicated test file for NotificationService's HTTP calls
existed before this round -- see loadAuditLogs/scheduling_service tests
for how the calendar-invite path is otherwise exercised only indirectly,
via mocks, in test_b6_6_notifications.py / test_b6_7_staff_schedules.py).
"""

import json
from unittest.mock import MagicMock, patch

from restoricon_core.services.notification_service import NotificationService


def test_send_calendar_cancellation_posts_to_send_cancellation_with_expected_body():
    svc = NotificationService(aigentik_api_url="http://127.0.0.1:8081")

    fake_response = MagicMock()
    fake_response.getcode.return_value = 200
    fake_response.__enter__.return_value = fake_response
    fake_response.__exit__.return_value = False

    with patch("urllib.request.urlopen", return_value=fake_response) as mock_urlopen:
        result = svc.send_calendar_cancellation(
            to_email="alice@example.com",
            appointment={"uid": "staff-sched-42", "title": "Shift"},
            text="This schedule entry has been cancelled: Shift",
        )

    assert result is True
    assert mock_urlopen.call_count == 1
    req = mock_urlopen.call_args.args[0]
    assert req.full_url == "http://127.0.0.1:8081/send-cancellation"
    body = json.loads(req.data.decode("utf-8"))
    assert body == {
        "to": "alice@example.com",
        "appointment": {"uid": "staff-sched-42", "title": "Shift"},
        "text": "This schedule entry has been cancelled: Shift",
    }


def test_send_calendar_cancellation_returns_false_on_connection_error():
    import urllib.error

    svc = NotificationService(aigentik_api_url="http://127.0.0.1:8081")

    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("connection refused")):
        result = svc.send_calendar_cancellation(
            to_email="alice@example.com",
            appointment={"uid": "staff-sched-42"},
            text="cancelled",
        )

    assert result is False
