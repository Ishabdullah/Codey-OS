"""
Unit tests for the thread-safe RateLimiter utility.
"""

import time
from restoricon_core.api.rate_limiter import RateLimiter


def test_rate_limiter_basic_allowance():
    limiter = RateLimiter(max_requests=5, window_seconds=10)
    ip = "192.168.1.100"

    for i in range(5):
        allowed, remaining, reset_in = limiter.is_allowed(ip)
        assert allowed is True
        assert remaining == 5 - (i + 1)
        assert reset_in <= 10

    # 6th request should be denied
    allowed, remaining, reset_in = limiter.is_allowed(ip)
    assert allowed is False
    assert remaining == 0
    assert reset_in > 0


def test_rate_limiter_multiple_ips():
    limiter = RateLimiter(max_requests=2, window_seconds=10)
    ip1 = "10.0.0.1"
    ip2 = "10.0.0.2"

    # Exhaust ip1
    assert limiter.is_allowed(ip1)[0] is True
    assert limiter.is_allowed(ip1)[0] is True
    assert limiter.is_allowed(ip1)[0] is False

    # ip2 is unaffected
    assert limiter.is_allowed(ip2)[0] is True
    assert limiter.is_allowed(ip2)[0] is True
    assert limiter.is_allowed(ip2)[0] is False


def test_rate_limiter_window_expiry():
    limiter = RateLimiter(max_requests=2, window_seconds=1)
    ip = "172.16.0.1"

    assert limiter.is_allowed(ip)[0] is True
    assert limiter.is_allowed(ip)[0] is True
    assert limiter.is_allowed(ip)[0] is False

    time.sleep(1.1)

    # After expiry, should allow again
    allowed, remaining, _ = limiter.is_allowed(ip)
    assert allowed is True
    assert remaining == 1


def test_rate_limiter_cleanup_stale():
    limiter = RateLimiter(max_requests=5, window_seconds=1)
    limiter.is_allowed("1.1.1.1")
    limiter.is_allowed("2.2.2.2")

    time.sleep(1.1)
    pruned = limiter.cleanup_stale_ips()
    assert pruned == 2
    assert len(limiter._requests) == 0
