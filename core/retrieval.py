"""
Retrieval-Augmented Generation (RAG) module — Phase 1 (v2.6.1)

Searches the local knowledge base and injects relevant chunks into the
system prompt via build_system_prompt() in core/agent.py.

Search pipeline:
  user_message
    -> extract_query()           strip filler words
    -> semantic_search() / keyword_fallback()
    -> filter by min_score
    -> format within budget
    -> return ## Reference Material block (or "" if nothing useful found)

The retrieve() function is designed to be called from build_system_prompt()
and is always wrapped in try/except there — it must never raise.

Usage:
    from core.retrieval import retrieve, retrieve_for_error
    block = retrieve("Flask JWT authentication")
    # Returns "" if KB is empty or no relevant results
"""

import re
from pathlib import Path

from utils.config import RETRIEVAL_CONFIG

# ── Filler words stripped from queries ───────────────────────────────────────
_FILLER = frozenset(
    {
        "please",
        "can",
        "you",
        "i",
        "want",
        "need",
        "to",
        "a",
        "an",
        "the",
        "me",
        "help",
        "create",
        "make",
        "write",
        "build",
        "add",
        "do",
        "in",
        "for",
        "of",
        "and",
        "or",
        "with",
        "using",
        "how",
        "is",
        "are",
        "does",
        "what",
        "why",
        "when",
        "where",
        "just",
        "some",
        "this",
        "that",
        "it",
        "my",
        "our",
        "get",
        "set",
        "use",
        "run",
        "show",
        "let",
        "into",
    }
)


def extract_query(user_message: str, max_words: int = 15) -> str:
    """
    Extract a compact search query from the user's message.

    Strips filler words, keeps technical terms and intent keywords.
    Capped at max_words to avoid over-querying the KB.

    Args:
        user_message: Raw user message
        max_words: Max query terms to keep

    Returns:
        Space-separated query string
    """
    # Remove non-alphanumeric except spaces and common code chars
    cleaned = re.sub(r"[^\w\s\.\-/_]", " ", user_message.lower())
    words = cleaned.split()
    query_words = [w for w in words if w not in _FILLER and len(w) > 2]
    return " ".join(query_words[:max_words])


def retrieve(user_message: str, budget_chars: int = None) -> str:
    """
    Retrieve relevant knowledge for a user message.

    Search order:
    1. Symbolic graph — query for related concepts first
    2. Knowledge base — semantic/keyword search
    3. Combined block within budget

    Returns a formatted ## Reference Material block ready to inject into
    the system prompt, or "" if nothing relevant is found.

    Args:
        user_message: The user's raw message (used to build the search query)
        budget_chars: Max characters of retrieved content (default from config)

    Returns:
        Formatted retrieval block string, or "" if empty
    """
    if not RETRIEVAL_CONFIG.get("enabled", True):
        return ""

    budget_chars = budget_chars or RETRIEVAL_CONFIG.get("budget_chars", 2400)
    max_chunks = RETRIEVAL_CONFIG.get("max_chunks", 4)
    min_score = RETRIEVAL_CONFIG.get("min_score", 0.0)
    use_semantic = RETRIEVAL_CONFIG.get("semantic_search", True)

    query = extract_query(user_message)
    if not query.strip():
        return ""

    # ── Step 1: Query symbolic graph first ────────────────────────────────────
    # The symbolic graph holds language-agnostic concepts and relations.
    # RAG queries hit this first to get structured context.
    graph_block = ""
    try:
        from core.memory_v2 import memory as _mem
        if _mem.symbolic._available:
            graph_results = _mem.search_symbolic(query)
            if graph_results:
                lines = []
                for r in graph_results[:max_chunks]:
                    concept = r.get("concept", "")
                    relation = r.get("relation", "")
                    if relation:
                        lines.append(f"- {concept} ({relation})")
                    else:
                        lines.append(f"- {concept}")
                if lines:
                    graph_block = "## Symbolic Graph Context\n" + "\n".join(lines) + "\n\n"
    except Exception:
        pass  # symbolic graph unavailable — continue without

    # ── Step 2: Knowledge base search ─────────────────────────────────────────
    kb_results = []
    try:
        if use_semantic:
            from tools.kb_semantic import has_index, semantic_search

            if has_index():
                kb_results = semantic_search(query, top_k=max_chunks)
            else:
                from tools.kb_semantic import keyword_fallback
                kb_results = keyword_fallback(query, top_k=max_chunks)
        else:
            from tools.kb_semantic import keyword_fallback
            kb_results = keyword_fallback(query, top_k=max_chunks)
    except Exception:
        pass  # KB unavailable — silent fallback

    if not kb_results and not graph_block:
        return ""

    # Filter KB results by semantic relevance
    if use_semantic and kb_results:
        semantic_threshold = RETRIEVAL_CONFIG.get("semantic_threshold", 0.3)
        kb_results = [
            r for r in kb_results
            if r.get("semantic_score", semantic_threshold) >= semantic_threshold
        ]
        relevance_gate = RETRIEVAL_CONFIG.get("relevance_gate", 0.72)
        best_cosine = max((r.get("semantic_score", 0.0) for r in kb_results), default=0.0)
        if best_cosine > 0.0 and best_cosine < relevance_gate:
            kb_results = []

    # Build retrieval block within budget
    header = "## Reference Material\n(Retrieved from knowledge base — use this if relevant)\n\n"
    total_chars = len(header)
    entries = []

    # Add graph block first (higher priority)
    if graph_block:
        if total_chars + len(graph_block) <= budget_chars:
            entries.append(graph_block)
            total_chars += len(graph_block)

    for r in kb_results:
        source_label = Path(r.get("source", "")).name or "knowledge-base"
        text = r.get("text", "").strip()
        if not text:
            continue
        entry = f"**[{source_label}]**\n{text}\n\n"
        if total_chars + len(entry) > budget_chars:
            remaining = budget_chars - total_chars - len(f"**[{source_label}]**\n\n")
            if remaining > 200:
                entry = f"**[{source_label}]**\n{text[:remaining]}...\n\n"
            else:
                break
        entries.append(entry)
        total_chars += len(entry)

    if not entries:
        return ""

    return header + "".join(entries)


def retrieve_for_error(error_text: str, tool_name: str, budget_chars: int = 1200) -> str:
    """
    Specialised retrieval for error recovery.

    Extracts the most informative part of an error (usually the last line
    of a traceback) and searches the KB for solutions.

    Args:
        error_text: The error/traceback text from a failed tool call
        tool_name: Name of the tool that failed (used as context)
        budget_chars: Max retrieved chars (smaller than normal — used in retries)

    Returns:
        Formatted retrieval block, or ""
    """
    lines = error_text.strip().split("\n")
    # Last non-empty line of a traceback is usually the most diagnostic
    error_summary = next((l.strip() for l in reversed(lines) if l.strip()), error_text[:200])
    query = f"{tool_name} {error_summary}"
    return retrieve(query, budget_chars=budget_chars)


def retrieve_debug(user_message: str) -> dict:
    """
    Run retrieval for *user_message* and return a detailed breakdown for
    inspection.  Intended for the /rag command — never called during normal
    inference.

    Returns a dict with:
        query       — the cleaned query sent to the search backend
        backend     — "semantic" | "keyword" | "unavailable"
        all_chunks  — every result before score filtering, with score + source
        kept_chunks — results that passed the score threshold
        block       — the ## Reference Material string that would be injected
                      (empty string if nothing passed)
    """
    budget_chars = RETRIEVAL_CONFIG.get("budget_chars", 2400)
    max_chunks = RETRIEVAL_CONFIG.get("max_chunks", 4)
    min_score = RETRIEVAL_CONFIG.get("min_score", 0.0)
    use_semantic = RETRIEVAL_CONFIG.get("semantic_search", True)
    semantic_threshold = RETRIEVAL_CONFIG.get("semantic_threshold", 0.3)

    query = extract_query(user_message)
    if not query.strip():
        return {"query": query, "backend": "none", "all_chunks": [], "kept_chunks": [], "block": ""}

    all_chunks = []
    backend = "unavailable"
    try:
        if use_semantic:
            from tools.kb_semantic import (has_index, keyword_fallback,
                                           semantic_search)

            if has_index():
                all_chunks = semantic_search(query, top_k=max_chunks * 2)
                backend = "semantic"
            else:
                all_chunks = keyword_fallback(query, top_k=max_chunks * 2)
                backend = "keyword"
        else:
            from tools.kb_semantic import keyword_fallback

            all_chunks = keyword_fallback(query, top_k=max_chunks * 2)
            backend = "keyword"
    except Exception as e:
        return {
            "query": query,
            "backend": "unavailable",
            "error": str(e),
            "all_chunks": [],
            "kept_chunks": [],
            "block": "",
        }

    # Apply the same score filter as retrieve()
    kept = list(all_chunks)
    if use_semantic and backend == "semantic":
        if kept and kept[0].get("score", 0) <= 1.0:
            kept = [r for r in kept if r.get("score", 0) >= semantic_threshold]
    kept = kept[:max_chunks]

    block = retrieve(user_message, budget_chars=budget_chars)

    return {
        "query": query,
        "backend": backend,
        "threshold": semantic_threshold if backend == "semantic" else min_score,
        "all_chunks": all_chunks,
        "kept_chunks": kept,
        "block": block,
    }


def retrieval_status() -> dict:
    """Return status info about the retrieval system (for /status command)."""
    try:
        from tools.kb_semantic import index_stats

        stats = index_stats()
        stats["retrieval_enabled"] = RETRIEVAL_CONFIG.get("enabled", True)
        return stats
    except Exception as e:
        return {"error": str(e), "retrieval_enabled": False}
