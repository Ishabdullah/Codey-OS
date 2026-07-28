#!/usr/bin/env python3
"""Test for rag_retrieval plugin."""

import importlib.util
from pathlib import Path

# _pathutil.py lives at ccos/plugins/_pathutil.py, two levels above this
# plugin's directory (test.py -> rag_retrieval/ -> research/ -> plugins/).
# Loaded by file path since the ccos package isn't importable yet.
_pathutil_path = Path(__file__).resolve().parent.parent.parent / "_pathutil.py"
_spec = importlib.util.spec_from_file_location("_pathutil", _pathutil_path)
_pathutil = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_pathutil)
_pathutil.ensure_repo_root_on_path()

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
