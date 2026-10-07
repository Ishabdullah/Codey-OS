"""Fixture stand-in for bench/runner.py -- imports AND calls
verify_lock, so 4a scores full credit (suite.lock also exists)."""
from bench.lock import verify_lock


def run():
    return verify_lock()
