"""Fixture stand-in for prompts/layered_prompt.py -- exercises the
1c/6c call-site check's three discriminating cases:
  - core.memory_v2: imported AND called (_remember())       -> hit
  - core.context:   imported but never called                -> miss
  - core.embeddings: not imported at all                      -> miss
"""
from core.context import build_context  # noqa: F401 -- intentionally unused
from core.memory_v2 import remember as _remember


def build_prompt():
    return _remember()
