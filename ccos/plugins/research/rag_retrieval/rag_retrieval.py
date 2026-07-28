"""
RAG Retrieval Plugin — thin CCOS adapter over core/retrieval.py.

Wraps the existing RAG pipeline as a capability without duplicating any
of its logic. All actual retrieval work stays in core/retrieval.py.
"""

import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parents[4])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from core.retrieval import retrieve as _retrieve


def retrieve(user_message: str, budget_chars: int = None) -> str:
    """Retrieve relevant knowledge-base context for a user message."""
    return _retrieve(user_message, budget_chars=budget_chars)


def test() -> bool:
    """Plugin self-test — verify retrieval runs without raising."""
    result = retrieve("test query for plugin self-test")
    assert isinstance(result, str), "Expected str"
    return True
