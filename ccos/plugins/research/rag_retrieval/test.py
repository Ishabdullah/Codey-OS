#!/usr/bin/env python3
"""Test for rag_retrieval plugin."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from ccos.plugins.research.rag_retrieval.rag_retrieval import retrieve, test


def test_retrieve():
    result = retrieve("how do I authenticate a Flask app with JWT")
    assert isinstance(result, str)
    print(f"[PASS] retrieve() returned a string ({len(result)} chars)")


def test_retrieve_budget():
    result = retrieve("test query", budget_chars=500)
    assert isinstance(result, str)
    assert len(result) <= 500 + 200  # header/entry overhead tolerance
    print("[PASS] retrieve() respects budget_chars")


def test_self_test():
    result = test()
    assert result is True
    print("[PASS] Self-test passed")


if __name__ == "__main__":
    test_retrieve()
    test_retrieve_budget()
    test_self_test()
    print("\nAll rag_retrieval tests passed!")
