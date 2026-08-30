"""
Thread-safe sliding-window in-memory rate limiter for Restoricon Core public API.
Protects inbound endpoints against spam floods and bot abuse.
"""

from __future__ import annotations

import threading
import time
from typing import Dict, List, Tuple


class RateLimiter:
    """Sliding-window rate limiter per client IP address."""

    def __init__(self, max_requests: int = 20, window_seconds: float = 60.0):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._lock = threading.Lock()
        self._requests: Dict[str, List[float]] = {}

    def is_allowed(self, client_ip: str) -> Tuple[bool, int, float]:
        """
        Check if a request from client_ip is allowed.
        Returns: (is_allowed, remaining_requests, retry_after_seconds)
        """
        now = time.time()
        with self._lock:
            cutoff = now - self.window_seconds
            timestamps = self._requests.get(client_ip, [])
            valid_timestamps = [t for t in timestamps if t > cutoff]

            if len(valid_timestamps) >= self.max_requests:
                oldest = valid_timestamps[0]
                retry_after = max(0.1, (oldest + self.window_seconds) - now)
                self._requests[client_ip] = valid_timestamps
                return False, 0, retry_after

            valid_timestamps.append(now)
            self._requests[client_ip] = valid_timestamps
            remaining = self.max_requests - len(valid_timestamps)
            return True, remaining, 0.0

    def cleanup_stale_ips(self) -> int:
        """Prunes IPs that have had no requests in the current window."""
        now = time.time()
        cutoff = now - self.window_seconds
        pruned = 0
        with self._lock:
            stale_keys = [ip for ip, timestamps in self._requests.items() if not any(t > cutoff for t in timestamps)]
            for ip in stale_keys:
                del self._requests[ip]
                pruned += 1
        return pruned

    def reset(self) -> None:
        """Clear all rate limit buckets (useful for tests)."""
        with self._lock:
            self._requests.clear()
