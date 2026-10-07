"""Fixture stand-in for core/memory_v2.py -- imported AND genuinely
called by prompts/layered_prompt.py, so it must count as a hit in
1c/6c's call-site check."""


def remember():
    return "memory"
