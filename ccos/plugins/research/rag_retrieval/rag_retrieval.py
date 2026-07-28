"""
RAG Retrieval Plugin — thin CCOS adapter over core/retrieval.py.

Wraps the existing RAG pipeline as a capability without duplicating any
of its logic. All actual retrieval work stays in core/retrieval.py.
"""

from ccos.plugins._pathutil import ensure_repo_root_on_path

ensure_repo_root_on_path()

from core.retrieval import retrieve as _retrieve


def retrieve(user_message: str, budget_chars: int = None) -> str:
    """Retrieve relevant knowledge-base context for a user message."""
    return _retrieve(user_message, budget_chars=budget_chars)


def test() -> bool:
    """Plugin self-test — verify retrieval runs without raising."""
    result = retrieve("test query for plugin self-test")
    assert isinstance(result, str), "Expected str"
    return True
