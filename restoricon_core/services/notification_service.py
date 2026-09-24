import json
import urllib.request
import urllib.error
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class NotificationService:
    def __init__(self, aigentik_api_url: str = "http://127.0.0.1:8081"):
        self.aigentik_api_url = aigentik_api_url.rstrip("/")

    def send_email(
        self, to_email: str, subject: str, body: str, html: Optional[str] = None,
        timeout: float = 2.0,
    ) -> bool:
        """NEW-623: `timeout` defaults to the original 2.0s (unchanged for
        existing callers -- the PM-assignment notification path at
        crm_service.py:3037) but the actual Aigentik /send-email endpoint
        does not write its HTTP response until the real, live SMTP round
        trip to Gmail completes (http-server.js awaits
        emailProvider.sendEmail() before responding), so 2.0s is not a
        defensible default for a caller where a false-failure/duplicate-
        send risk matters -- see the B8.10c compose route, which passes an
        explicit longer timeout instead of relying on this default."""
        url = f"{self.aigentik_api_url}/send-email"
        data = {
            "to": to_email,
            "subject": subject,
            "text": body
        }
        if html:
            data["html"] = html

        return self._post_request(url, data, timeout=timeout)

    def send_calendar_invite(self, to_email: str, appointment: Dict[str, Any], text: str) -> bool:
        url = f"{self.aigentik_api_url}/send-invite"
        data = {
            "to": to_email,
            "appointment": appointment,
            "text": text
        }
        return self._post_request(url, data)

    def send_calendar_cancellation(self, to_email: str, appointment: Dict[str, Any], text: str) -> bool:
        """Posts a METHOD:CANCEL ICS to the same UID as the corresponding
        send_calendar_invite() call (NEW-506)."""
        url = f"{self.aigentik_api_url}/send-cancellation"
        data = {"to": to_email, "appointment": appointment, "text": text}
        return self._post_request(url, data)

    def _post_request(self, url: str, data: Dict[str, Any], timeout: float = 2.0) -> bool:
        payload = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})

        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                if response.getcode() == 200:
                    return True
                else:
                    logger.warning(f"NotificationService: Unexpected status code {response.getcode()} from {url}")
                    return False
        except urllib.error.URLError as e:
            logger.warning(f"NotificationService: Failed to connect to {url}: {e}")
            return False
        except Exception as e:
            logger.warning(f"NotificationService: Unexpected error calling {url}: {e}")
            return False
