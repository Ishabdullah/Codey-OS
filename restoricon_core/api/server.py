"""
Local HTTP REST API server for Restoricon Core.
Provides a standard, lightweight multi-threaded HTTP server bound to localhost (127.0.0.1)
by default with token authentication and JSON request processing.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional

from ..auth import AuthService
from ..database import DatabaseManager, DEFAULT_DB_PATH
from ..services.audit_service import AuditService
from ..services.automation_service import AutomationService
from ..services.communication_service import CommunicationService
from ..services.crm_service import CRMService
from ..services.scheduling_service import SchedulingService
from .routes import APIRouter

logger = logging.getLogger("restoricon_core.api")

DEFAULT_HOST = os.getenv("RESTORICON_API_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.getenv("RESTORICON_API_PORT", "8770"))


class RestoriconRequestHandler(BaseHTTPRequestHandler):
    """Handles incoming HTTP requests and delegates to APIRouter."""

    router: APIRouter

    def do_GET(self) -> None:
        self._dispatch("GET")

    def do_POST(self) -> None:
        self._dispatch("POST")

    def do_PUT(self) -> None:
        self._dispatch("PUT")

    def do_DELETE(self) -> None:
        self._dispatch("DELETE")

    def _dispatch(self, method: str) -> None:
        content_length = int(self.headers.get("Content-Length", 0))
        body_bytes = self.rfile.read(content_length) if content_length > 0 else b""

        headers_dict = {k: v for k, v in self.headers.items()}
        status, resp_headers, resp_data = self.router.handle_request(
            method=method,
            path_with_query=self.path,
            headers=headers_dict,
            body_bytes=body_bytes,
        )

        resp_bytes = json.dumps(resp_data).encode("utf-8")
        self.send_response(status)
        for h_key, h_val in resp_headers.items():
            self.send_header(h_key, h_val)
        self.send_header("Content-Length", str(len(resp_bytes)))
        self.end_headers()
        self.wfile.write(resp_bytes)

    def log_message(self, format: str, *args: object) -> None:
        """Suppress default stderr logging or route to logger."""
        logger.debug("%s - - [%s] %s", self.address_string(), self.log_date_time_string(), format % args)


class RestoriconAPIServer:
    """Manages the lifecycle of the Restoricon Core HTTP API server."""

    def __init__(
        self,
        db_path: Optional[str] = None,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
    ):
        self.host = host
        self.port = port
        self.db = DatabaseManager(db_path or DEFAULT_DB_PATH)
        self.auth_service = AuthService(self.db)
        self.audit_service = AuditService(self.db)
        self.comm_service = CommunicationService(self.db)
        self.crm_service = CRMService(self.db, self.audit_service)
        self.scheduling_service = SchedulingService(self.db, self.audit_service)
        self.automation_service = AutomationService(self.db, self.audit_service)

        # RBAC for these two services (and CRMService's subcontractor
        # methods) is enforced in the service layer, not here -- see
        # APIRouter's own class docstring.
        self.router = APIRouter(
            auth_service=self.auth_service,
            crm_service=self.crm_service,
            comm_service=self.comm_service,
            audit_service=self.audit_service,
            scheduling_service=self.scheduling_service,
            automation_service=self.automation_service,
        )

        class CustomHandler(RestoriconRequestHandler):
            router = self.router

        self.httpd = ThreadingHTTPServer((self.host, self.port), CustomHandler)
        self._thread: Optional[threading.Thread] = None
        self._is_running = False

    def start(self, background: bool = False) -> None:
        """Start the API server."""
        self._is_running = True
        logger.info("Restoricon Core API server starting on http://%s:%d", self.host, self.port)
        if background:
            self._thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
            self._thread.start()
        else:
            self.httpd.serve_forever()

    def stop(self) -> None:
        """Stop the API server and clean up resources."""
        if self._is_running:
            self._is_running = False
            self.httpd.shutdown()
            self.httpd.server_close()
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=5.0)
            self.db.close()
            logger.info("Restoricon Core API server stopped")
