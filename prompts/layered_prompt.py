"""
Layered System Prompt Builder — Phase 3 (v2.6.3)

Replaces build_system_prompt() with a phase-aware, layered system prompt that
composes context optimally for each stage of the recursive inference loop.

Each recursion phase needs different context:
  "draft"    — Full context: identity, prefs, project, repo map, RAG, files
               (identical to the old build_system_prompt — no regression)
  "critique" — Lean context: critique template + prior draft embedded in system
               (drops files, history, project — focuses purely on output review)
  "refine"   — Full context minus history: identity, prefs, project, critique
               summary, targeted RAG for NEED_DOCS gaps, files
               (history dropped to free ~1000 tokens; critique replaces it)

Architecture
────────────
LayeredPrompt manages a priority-ordered list of context blocks.  Each block
has a numeric priority (lower = more important, evicted last) and an optional
required flag (never evicted).  When the total size approaches the budget,
lower-priority blocks are skipped.

Priority map:
  0 — Core identity (SYSTEM_PROMPT) ← required, never evicted
  1 — User preferences
  2 — Project memory / CODEY.md + critique summary (for refine)
  3 — Repo map + retrieved knowledge (RAG / NEED_DOCS)
  4 — Loaded file context

Usage:
    from prompts.layered_prompt import build_recursive_prompt

    # Main agent loop (replaces build_system_prompt)
    sys_prompt = build_recursive_prompt(user_message, phase="draft")

    # Critique pass (recursive.py) — pass the full draft; truncation that
    # never splits a <tool>...</tool> block happens inside build_recursive_prompt
    crit_prompt = build_recursive_prompt(
        user_message, phase="critique", prior_draft=draft
    )

    # Refine pass (recursive.py) — prior_draft (NEW-58) lets refine see and
    # revise its own actual proposal instead of regenerating blind
    ref_prompt = build_recursive_prompt(
        user_message, phase="refine",
        prior_draft=draft,
        prior_critique=critique[:800],
        retrieved_context=extra_kb_context,
    )
"""

import re
import time
from dataclasses import dataclass

# ── Layer data structure ──────────────────────────────────────────────────────


@dataclass
class _Layer:
    name: str
    content: str
    priority: int  # lower number = more important (evicted last)
    required: bool = False


class LayeredPrompt:
    """
    Priority-managed system prompt assembler.

    Add named layers with a priority number.  When building, layers are
    included greedily in priority order until the char budget is exhausted.
    Required layers are always included regardless of budget.  The final
    output preserves insertion order so the prompt reads coherently.

    Example:
        p = LayeredPrompt(budget_chars=12000)
        p.add("identity", get_system_prompt(), priority=0, required=True)
        p.add("project",  codeymd_text,  priority=2)
        p.add("files",    file_block,    priority=4)
        system_prompt = p.build()
    """

    def __init__(self, budget_chars: int = 12000):
        self._budget = budget_chars
        self._layers: list[_Layer] = []

    def add(self, name: str, content: str, priority: int, required: bool = False) -> None:
        """Add a context layer.  No-op if content is empty or whitespace."""
        if not content or not content.strip():
            return
        self._layers.append(_Layer(name, content.strip(), priority, required))

    def build(self) -> str:
        """
        Assemble included layers in insertion order within the char budget.

        Algorithm:
          1. Sort candidates: required first, then by priority ascending
          2. Greedily include until budget is exhausted
          3. Restore original insertion order in final output
        """
        candidates = sorted(
            self._layers,
            key=lambda l: (not l.required, l.priority),
        )

        selected_names: set[str] = set()
        used = 0
        for layer in candidates:
            if layer.required or (used + len(layer.content) <= self._budget):
                selected_names.add(layer.name)
                used += len(layer.content)

        # Restore insertion order for coherent prompt reading
        ordered = [l for l in self._layers if l.name in selected_names]
        return "\n".join(l.content for l in ordered)


# ── Internal context gatherers ────────────────────────────────────────────────

_PREF_LABELS = {
    "test_framework": "Test framework",
    "code_style": "Code style",
    "naming_convention": "Naming convention",
    "import_style": "Import style",
    "docstring_style": "Docstring style",
    "error_handling": "Error handling",
    "type_hints": "Type hints",
    "async_style": "Async style",
    "http_library": "HTTP library",
    "cli_library": "CLI library",
    "log_style": "Logging style",
}


def _get_notes_block() -> str:
    """Return persistent user notes block, or empty string."""
    try:
        from core.notes import get_notes_block

        return get_notes_block()
    except Exception:
        return ""


def _get_preferences_block() -> str:
    """Return formatted user-preferences block, or empty string on failure."""
    try:
        from core.learning import get_learning_manager

        prefs = get_learning_manager().get_all_preferences()
        if not prefs:
            return ""
        lines = [f"- {_PREF_LABELS.get(k, k)}: {v}" for k, v in prefs.items() if v]
        if not lines:
            return ""
        return (
            "## User Preferences\n"
            "Always match these preferences when generating code:\n" + "\n".join(lines)
        )
    except Exception:
        return ""


def _get_project_block() -> str:
    """Return CODEY.md block, or project-summary block, or empty string."""
    try:
        from core.codeymd import read_codeymd

        codeymd = read_codeymd()
        if codeymd:
            return "## Project Memory\n" + codeymd
    except Exception:
        pass
    try:
        from core.project import get_project_summary

        proj = get_project_summary()
        if proj:
            return "## Current Project\n" + proj
    except Exception:
        pass
    return ""


def _get_repo_map_block() -> str:
    """Return repo map block, or empty string."""
    try:
        from core.project import get_repo_map

        return get_repo_map() or ""
    except Exception:
        return ""


def _get_file_block(user_message: str) -> str:
    """Return loaded-files context block with relevance scoring, or empty."""
    try:
        from core.context import build_file_context_block

        ctx = build_file_context_block(user_message)
        if ctx:
            return "## Loaded Files\n" + ctx
    except Exception:
        pass
    return ""


# ── Draft prompt cache ────────────────────────────────────────────────────────
# Avoids re-running RAG retrieval, skills loading, and file context gathering
# on every call.  Invalidated when loaded files change or TTL expires.

_draft_cache = {
    "prompt": None,
    "built_at": 0.0,
    "files_hash": None,
    "lightweight": None,
}
_CACHE_TTL = 120.0  # seconds


def _files_hash():
    """Hash of loaded file names + content mtimes — invalidates on edit."""
    try:
        import os

        from core.context import list_loaded

        paths = sorted(list_loaded())
        mtimes = []
        for p in paths:
            try:
                mtimes.append(os.path.getmtime(p))
            except OSError:
                mtimes.append(0)
        return tuple(zip(paths, mtimes))
    except Exception:
        return ()


def invalidate_prompt_cache():
    """Force a fresh build on the next draft call."""
    _draft_cache["prompt"] = None


# ── Phase-specific builders ───────────────────────────────────────────────────


def _get_symbolic_graph_block() -> str:
    """Return symbolic graph state block, or empty string."""
    try:
        from core.memory_v2 import memory as _mem
        if _mem.symbolic._available:
            graph_nl = _mem.to_natural_language(lang="en")
            if graph_nl and graph_nl != "No concepts in graph.":
                return "## Symbolic Graph\n(Language-agnostic concept graph)\n" + graph_nl
    except Exception:
        pass
    return ""


def _build_draft_prompt(user_message: str, plan_rag_block: str = "", lightweight: bool = False) -> str:
    """
    Full-context system prompt for the initial draft generation.
    Identical output to the old build_system_prompt(message) — no regression.

    Priority map:
      0 SYSTEM_PROMPT   — required
      1 User prefs
      2 Project memory
      3 Repo map
      3 Retrieved KB docs (RAG)
      3 Relevant skill patterns (Phase 5)
      4 Loaded files

    When lightweight=True (QA/smalltalk), the repo_map, retrieval, skills,
    files, and symbolic_graph blocks — and the calls that build them — are
    skipped entirely. Only identity, notes, prefs, project, and capabilities
    (when asked about) are included.
    """
    # Check cache — reuse if files haven't changed and TTL hasn't expired
    now = time.time()
    current_fh = _files_hash()
    if (
        _draft_cache["prompt"] is not None
        and now - _draft_cache["built_at"] < _CACHE_TTL
        and _draft_cache["files_hash"] == current_fh
        and _draft_cache["lightweight"] == lightweight
    ):
        return _draft_cache["prompt"]

    from prompts.system_prompt import (CAPABILITIES_PROMPT, get_qa_system_prompt,
                                       get_system_prompt)

    # 20 000 chars ≈ 5 000 tokens — well within the 32 768-token context window.
    # Previously 12 000 left 80% of the context unused; raising this lets more
    # files, RAG results, and skill patterns fit without eviction.
    p = LayeredPrompt(budget_chars=20000)
    identity = get_qa_system_prompt() if lightweight else get_system_prompt()
    p.add("identity", identity, priority=0, required=True)

    # Inject capabilities only when the user is asking about them
    _msg_low = user_message.lower() if user_message else ""
    _cap_kw = ("what can you", "what do you", "capabilities", "help", "what are you")
    if any(k in _msg_low for k in _cap_kw):
        p.add("capabilities", CAPABILITIES_PROMPT, priority=1)

    p.add("notes", _get_notes_block(), priority=1)
    p.add("prefs", _get_preferences_block(), priority=1)
    p.add("project", _get_project_block(), priority=2)

    if not lightweight:
        p.add("repo_map", _get_repo_map_block(), priority=3)

        # Phase 1 RAG: inject relevant KB docs.
        # If a pre-fetched block is supplied (e.g. from _run_with_plan retrieving
        # once on the full user prompt), use it directly — skip the per-step call.
        if plan_rag_block:
            p.add("retrieval", plan_rag_block, priority=3)
        elif user_message:
            try:
                from core.retrieval import retrieve

                retrieved = retrieve(user_message)
                if retrieved:
                    p.add("retrieval", retrieved, priority=3)
            except Exception:
                pass  # KB unavailable — continue without

        # Phase 5 skills: inject relevant skill patterns from external repos
        if user_message:
            try:
                from core.skills import load_relevant_skills

                skills = load_relevant_skills(user_message)
                if skills:
                    p.add("skills", skills, priority=3)
            except Exception:
                pass  # Skills unavailable — continue without

        p.add("files", _get_file_block(user_message), priority=4)
        # v3.0.0: Add symbolic graph context if available
        p.add("symbolic_graph", _get_symbolic_graph_block(), priority=3)

    result = p.build()

    # Store in cache
    _draft_cache["prompt"] = result
    _draft_cache["built_at"] = now
    _draft_cache["files_hash"] = current_fh
    _draft_cache["lightweight"] = lightweight
    return result


_TOOL_BLOCK_RE = re.compile(r"<tool>.*?</tool>", re.DOTALL)
# core/recursive.py's draft infer() call is stop-sequenced on "</tool>"
# (extra_stop default), and llama.cpp elides the stop string from returned
# text — so a real draft containing a tool call very often ends with the
# raw JSON and NO closing "</tool>" tag at all (confirmed by core/agent.py's
# own parse_tool_call(), which matches `<tool>\s*(\{.*)` with no closing-tag
# requirement, and by _format_tool_for_history() re-adding "</tool>" only
# when re-serializing the *parsed* dict for history — never present on the
# raw model output it's replacing). _TOOL_BLOCK_RE alone would silently miss
# this common case and fall through to the naive char-count cut it exists to
# avoid, so this second pattern catches an unterminated "<tool>" run to the
# end of the string.
_UNTERMINATED_TOOL_RE = re.compile(r"<tool>.*\Z", re.DOTALL)


def _safe_truncate_draft(text: str, limit: int) -> str:
    """
    Truncate a prior draft to ``limit`` chars WITHOUT ever splitting a
    <tool>...</tool> JSON block mid-string (NEW-59 fix).

    A raw ``text[:limit]`` cut can land inside a real patch_file tool call's
    JSON (whose old_str/new_str fields embed verbatim file excerpts, easily
    exceeding a char cap), producing syntactically-broken JSON that makes a
    legitimately correct, complete tool call look broken to the critique/
    refine model — causing a spurious rejection or a blind, tool-call-less
    revision.

    Strategy: if the text contains a <tool>...</tool> block (terminated OR
    — the common real case, see _UNTERMINATED_TOOL_RE's comment — an
    unterminated "<tool>" run to the end of the string), that block is
    NEVER truncated, no matter how large — only the surrounding prose
    (reasoning before/after the tool call) is cut to fit the remaining
    budget. If there's no tool block at all, falls back to a plain
    char-count truncation (safe, since there's no JSON to split).
    """
    if not text or len(text) <= limit:
        return text

    m = _TOOL_BLOCK_RE.search(text) or _UNTERMINATED_TOOL_RE.search(text)
    if not m:
        return text[:limit] + "\n...[truncated]"

    block = m.group(0)
    before = text[: m.start()]
    after = text[m.end() :]

    # The tool block itself is never cut. Whatever budget remains (if any)
    # goes to the prose immediately preceding it (most relevant context for
    # judging the call), truncated from the front so the tail nearest the
    # tool call survives. Trailing prose after the tool call is dropped
    # first since it's rarely load-bearing for critique/refine.
    remaining = limit - len(block)
    if remaining <= 0:
        # Block alone already exceeds the limit — keep it whole and drop
        # all surrounding prose rather than split the JSON.
        return block

    if len(before) > remaining:
        before = "...[truncated]...\n" + before[-remaining:]
        after = ""
    else:
        after_budget = remaining - len(before)
        if len(after) > after_budget:
            after = after[:after_budget] + "\n...[truncated]"

    return before + block + after


def _build_critique_prompt(user_message: str, prior_draft: str) -> str:
    """
    Lean system prompt for the self-critique phase.

    Drops project context, files, and history — the model only needs to see
    its own output, the original request, and the critique instructions.  The
    prior draft is embedded directly in the system prompt so the user turn
    stays minimal.

    Priority map:
      0 Critique instructions — required
      1 Original request — required (so completeness can be judged)
      1 Prior draft to review — required

    NEW-59 fix: prior_draft is no longer cut with a raw char-count slice
    (which could split a <tool>{...}</tool> JSON block mid-string, making a
    correct/complete patch_file call look syntactically broken to the
    critique model). It's now passed through _safe_truncate_draft(), which
    never cuts inside a tool block. The cap is also raised from 1500 to
    4000 chars — this budget (8000 total) has headroom: CRITIQUE_CODE is
    ~1.2k chars and original_request is capped at 1000, both required, so
    even a full 4000-char prior_draft leaves ~1.8k chars of margin before
    the nominal 8000-char budget (which required layers can exceed anyway —
    see LayeredPrompt.build()).
    """
    from prompts.critique_prompts import CRITIQUE_CODE

    p = LayeredPrompt(budget_chars=8000)
    p.add("critique_instr", CRITIQUE_CODE, priority=0, required=True)

    if user_message:
        request_block = "\n## User's Original Request\n" + user_message[:1000]
        p.add("original_request", request_block, priority=1, required=True)

    if prior_draft:
        draft_block = (
            "\n## Output to Review\n"
            "(The text you wrote that needs to be critiqued)\n\n"
            + _safe_truncate_draft(prior_draft, 4000)
        )
        p.add("prior_draft", draft_block, priority=1, required=True)

    return p.build()


def _build_refine_prompt(
    user_message: str,
    prior_critique: str,
    retrieved_context: str,
    prior_draft: str = "",
) -> str:
    """
    Full-context system prompt for the refine phase.

    Like draft, but:
    - History is DROPPED — the caller must not include history messages;
      the critique acts as the "memory" of what was tried and what failed
    - Critique summary injected at high priority (required) so the model
      sees what it must fix
    - Targeted retrieved context for NEED_DOCS gaps replaces normal RAG
      (fresh RAG already ran in the draft phase — no need to repeat)
    - NEW-58 fix: the draft's own actual prior proposal (including any real
      <tool>{...}</tool> call, e.g. a patch_file with verbatim old_str/
      new_str) is now also included at high priority (required), so refine
      can see and revise what it actually proposed instead of blindly
      regenerating the entire response from scratch with zero memory of the
      original tool-call content. Mirrors critique's existing prior_draft
      path. Same NEW-59 tool-block-aware truncation is applied here too
      (via _safe_truncate_draft()) so this doesn't reintroduce the same
      mid-JSON-split bug in a new location.

    Priority map:
      0 SYSTEM_PROMPT   — required
      1 User prefs
      2 Project memory
      2 Issues to Fix (critique summary) — required
      2 Your prior proposal (draft to revise) — required
      3 Repo map
      3 Targeted retrieved docs (NEED_DOCS)
      4 Loaded files
    """
    from prompts.system_prompt import get_system_prompt

    p = LayeredPrompt(budget_chars=20000)
    p.add("identity", get_system_prompt(), priority=0, required=True)
    p.add("prefs", _get_preferences_block(), priority=1)
    p.add("project", _get_project_block(), priority=2)

    # Critique summary — always included, high priority
    if prior_critique:
        critique_block = (
            "\n## Issues to Fix\n"
            "(From self-review of your previous response — "
            "address ALL of these in your revised output)\n\n" + prior_critique[:800]
        )
        p.add("critique", critique_block, priority=2, required=True)

    # Prior draft — the actual proposal (including any tool call) being
    # revised. Required so refine always has it, tool-block-aware truncated
    # so a real patch_file JSON call is never split mid-string (NEW-58/59).
    if prior_draft:
        draft_block = (
            "\n## Your Prior Proposal (revise this)\n"
            "(What you actually wrote/called last turn, before critique — "
            "revise it to fix the Issues to Fix above; do not restart from "
            "scratch or invent a different approach)\n\n"
            + _safe_truncate_draft(prior_draft, 4000)
        )
        p.add("prior_draft", draft_block, priority=2, required=True)

    p.add("repo_map", _get_repo_map_block(), priority=3)

    # Targeted retrieval for NEED_DOCS gaps (pre-fetched by recursive.py)
    if retrieved_context:
        p.add("retrieval", retrieved_context, priority=3)

    p.add("files", _get_file_block(user_message), priority=4)
    # v3.0.0: Add symbolic graph context if available
    p.add("symbolic_graph", _get_symbolic_graph_block(), priority=3)
    return p.build()


# ── Public API ────────────────────────────────────────────────────────────────


def build_recursive_prompt(
    user_message: str = "",
    phase: str = "draft",
    prior_draft: str = "",
    prior_critique: str = "",
    retrieved_context: str = "",
    plan_rag_block: str = "",
    lightweight: bool = False,
) -> str:
    """
    Phase-aware system prompt builder.  Replaces build_system_prompt().

    Args:
        user_message:      The user's current request
                           - "draft":    drives RAG query + file relevance scoring
                           - "critique": included verbatim so the critique model can
                                         judge task completeness, not just correctness
                           - "refine":   drives file relevance scoring
        phase:             "draft" | "critique" | "refine"
        prior_draft:       Output to review/revise — used by BOTH "critique"
                           (what to critique) and "refine" (NEW-58: the
                           actual prior proposal to revise, not regenerate
                           blind). Tool-block-aware truncated to 4000 chars
                           via _safe_truncate_draft() in both phases (NEW-59)
                           — never splits a <tool>{...}</tool> JSON block.
        prior_critique:    Critique text to fix (refine phase only, max 800 chars)
        retrieved_context: Pre-fetched KB docs for NEED_DOCS gaps (refine only)
        lightweight:       "draft" phase only — QA/smalltalk messages skip
                           repo_map, retrieval, skills, files, and
                           symbolic_graph entirely (see _build_draft_prompt)

    Returns:
        System prompt string, ready as messages[0]["content"].
        Never raises — all inner calls are try/except guarded.
    """
    if phase == "critique":
        return _build_critique_prompt(user_message, prior_draft)
    if phase == "refine":
        return _build_refine_prompt(
            user_message, prior_critique, retrieved_context, prior_draft=prior_draft
        )
    # default: "draft"
    return _build_draft_prompt(user_message, plan_rag_block=plan_rag_block, lightweight=lightweight)
