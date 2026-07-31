"""
Recursive Inference — Phase 2 (v2.6.2)

Wraps infer() with a self-refine loop:  draft → critique → refine → critique → …

How it works
────────────
1. Generate initial draft via infer() (streaming, same as normal)
2. Send draft to a focused critique prompt — model reviews its own output
3. Quality gate: if rating ≥ threshold (default 7/10) or no critical issues → accept
4. If NEED_DOCS marker found in critique → retrieve targeted KB context
5. Send refine prompt (original messages + draft + critique + retrieved docs) → new draft
6. Repeat up to max_depth times, then accept final draft — if the final rating is
   below LOW_CONFIDENCE_FLOOR, the caller can opt in (return_confidence=True) to
   learn this and warn the user instead of presenting it as a normal success

Selective activation via classify_breadth_need():
  "minimal"  — Q&A, short lookups.       → No recursion (single pass).
  "standard" — Typical coding task.      → 1 critique+refine cycle.
  "deep"     — Multi-file / complex.     → Up to 2 critique+refine cycles.

Performance on Termux (7B @ ~0.5–2 t/s):
  Best case  (quality passes after draft):  2 infer calls  (draft + 1 critique)
  Standard   (1 critique + 1 refine):       3 infer calls
  Deep       (2 critique + refine cycles):  up to 5 infer calls

All errors are caught — recursive_infer() never raises. If any inner call fails,
it returns the last good draft or the error string.

Usage:
    from core.recursive import recursive_infer, classify_breadth_need

    breadth = classify_breadth_need(user_message)
    if breadth != "minimal":
        response = recursive_infer(messages, task_type="code",
                                   user_message=user_message,
                                   max_depth=1 if breadth == "standard" else 2)
    else:
        response = infer(messages, stream=True)
"""

import re
from typing import Optional

from prompts.layered_prompt import build_recursive_prompt
from utils.config import MODEL_CONFIG, RECURSIVE_CONFIG, THERMAL_CONFIG
from utils.logger import info, warning

# ── Breadth classification ────────────────────────────────────────────────────

_DEEP_SIGNALS = [
    "api",
    "database",
    "db",
    "auth",
    "authentication",
    "deploy",
    "deployment",
    "test",
    "tests",
    "testing",
    "migrate",
    "migration",
    "refactor",
    "integrate",
    "integration",
    "full",
    "complete",
    "entire",
    "all of",
    "multiple",
    "several",
    "then",
    "also",
    "and then",
    "after that",
]

_ACTION_KEYWORDS = [
    "create",
    "write",
    "make",
    "build",
    "edit",
    "fix",
    "run",
    "execute",
    "implement",
    "generate",
    "rewrite",
    "patch",
    "update",
    "add",
    "delete",
    "remove",
    "install",
    "deploy",
    "setup",
    "configure",
]

_QA_STARTERS = (
    "what",
    "why",
    "how",
    "when",
    "where",
    "who",
    "which",
    "is ",
    "are ",
    "do ",
    "does ",
    "can ",
    "could ",
    "would ",
    "should ",
    "will ",
    "was ",
    "were ",
    "has ",
    "have ",
)

_QA_PHRASES = [
    "tell me",
    "explain",
    "help me understand",
    "what can you",
    "hello",
    "hi ",
    "hey ",
    "thanks",
    "thank you",
]


def classify_breadth_need(user_message: str) -> str:
    """
    Classify task complexity to determine recursion depth.

    Returns:
        "minimal"  — Q&A, short lookups. No recursion.
        "standard" — Typical single-file coding tasks. 1 critique+refine pass.
        "deep"     — Multi-file, complex APIs, long tasks. 2 critique+refine passes.
    """
    msg = user_message.strip().lower()
    words = msg.split()

    # Very short messages that look like questions → minimal
    if len(words) < 8:
        if msg.endswith("?") or msg.startswith(_QA_STARTERS) or any(k in msg for k in _QA_PHRASES):
            return "minimal"

    # No action keywords → likely Q&A → minimal
    has_action = any(k in msg for k in _ACTION_KEYWORDS)
    if not has_action:
        return "minimal"

    # Long messages or many deep-complexity signals → deep
    deep_count = sum(1 for sig in _DEEP_SIGNALS if sig in msg)
    if len(words) > 50 or deep_count >= 3:
        return "deep"

    return "standard"


# ── Adaptive depth (Phase 8) ────────────────────────────────────────────────


def get_adaptive_depth(requested_depth: int) -> int:
    """
    Adjust recursion depth based on device thermal and battery state.

    Rules (applied in priority order):
    - temp >= temp_critical (80°C)  → force depth 0 (no recursion)
    - temp >= temp_warn (65°C)      → cap depth at 1
    - battery <= batt_low (15%) AND not charging → cap depth at 1
    - battery <= batt_critical (5%) AND not charging → force depth 0
    - charging or cool                → use requested_depth as-is

    Returns the (possibly reduced) max_depth.
    """
    if not THERMAL_CONFIG.get("enabled", True):
        return requested_depth

    cfg = THERMAL_CONFIG
    temp_crit = cfg.get("temp_critical", 80)
    temp_warn = cfg.get("temp_warn", 65)
    batt_low = cfg.get("batt_low", 15)
    batt_crit = cfg.get("batt_critical", 5)

    try:
        from core.sysmon import get_monitor

        snap = get_monitor().snapshot
    except Exception:
        return requested_depth  # monitor unavailable — use full depth

    temp = snap.get("temp")
    batt = snap.get("battery_pct")
    charging = snap.get("battery_charging", False)

    # Temperature takes priority — thermal throttling makes recursion pointless
    if temp is not None:
        if temp >= temp_crit:
            if requested_depth > 0:
                info(f"[Adaptive] {temp:.0f}°C — skipping recursion (thermal)")
            return 0
        if temp >= temp_warn and requested_depth > 1:
            info(f"[Adaptive] {temp:.0f}°C — capping recursion depth to 1")
            return 1

    # Battery — only restrict when NOT charging
    if batt is not None and not charging:
        if batt <= batt_crit:
            if requested_depth > 0:
                info(f"[Adaptive] Battery {batt}% — skipping recursion")
            return 0
        if batt <= batt_low and requested_depth > 1:
            info(f"[Adaptive] Battery {batt}% — capping recursion depth to 1")
            return 1

    return requested_depth


# ── Quality gate helpers ──────────────────────────────────────────────────────


def extract_rating(critique: str) -> Optional[float]:
    """
    Extract a numeric X/10 quality rating from critique text.

    Matches patterns like "Quality: 8/10", "7/10", "9 / 10".
    Returns None if no rating found.
    """
    # "8/10", "8 / 10", "8.5/10"
    m = re.search(r"(\d+(?:\.\d+)?)\s*/\s*10", critique)
    if m:
        return float(m.group(1))
    # "8 out of 10"
    m = re.search(r"(\d+(?:\.\d+)?)\s+out\s+of\s+10", critique, re.IGNORECASE)
    if m:
        return float(m.group(1))
    return None


def extract_doc_needs(critique: str) -> Optional[str]:
    """
    Extract NEED_DOCS markers from critique text for targeted retrieval.

    The model should emit lines like:
        NEED_DOCS: Flask error handler decorator syntax

    Returns the joined query string, or None if no markers found.
    """
    matches = re.findall(r"NEED_DOCS:\s*(.+?)(?:\n|$)", critique, re.IGNORECASE)
    if matches:
        return " ".join(m.strip() for m in matches)
    return None


# Hard floor below which a max-depth result must not be silently accepted as
# a normal success — see recursive_infer()'s return_confidence handling.
LOW_CONFIDENCE_FLOOR = 4.0

_CRITICAL_MARKERS = [
    "syntax error",
    "will crash",
    "missing import",
    "undefined variable",
    "security issue",
    "incomplete",
    "won't work",
    "logic bug",
    "wrong output",
    "broken",
    "need_docs",
    "missing return",
    "indentation error",
    "name error",
    "type error",
    "attribute error",
]


def passes_quality_check(critique: str, threshold: float = 0.7) -> bool:
    """
    Return True if the critique indicates acceptable quality (no refinement needed).

    Logic:
    - If a numeric X/10 rating is present: pass if rating >= threshold * 10
    - If no rating: fail if any critical issue marker is found in the critique
    """
    rating = extract_rating(critique)
    if rating is not None:
        return rating >= threshold * 10

    # No numeric rating — check for critical problem markers
    lower = critique.lower()
    return not any(marker in lower for marker in _CRITICAL_MARKERS)


# ── Internal helpers ──────────────────────────────────────────────────────────


def _strip_tool_calls(text: str) -> str:
    """Remove <tool>...</tool> blocks from text (critique should not contain them)."""
    cleaned = re.sub(r"<tool>.*?</tool>", "", text, flags=re.DOTALL)
    return cleaned.strip()


def _has_tool_call(text: str) -> bool:
    """Return True if the text contains a <tool> call block."""
    return bool(re.search(r"<tool>", text))


def _log_phase(label: str, pass_num: int, max_depth: int) -> None:
    """Print a dim phase indicator via the standard logger."""
    info(f"[Recursive] {label} ({pass_num}/{max_depth})")


def _extract_tool_name(text: str) -> Optional[str]:
    """
    Best-effort extraction of a tool call's "name" field from response text,
    for attribution-logging purposes only. This is intentionally a lighter
    regex than core/agent.py's parse_tool_call() — it exists only to answer
    "what tool (if any) did this turn produce" in the log line, not to
    actually dispatch a tool call. core/agent.py's own parser remains the
    sole source of truth for real tool execution.
    """
    if not text:
        return None
    m = re.search(r"<tool>\s*\{.*?[\"']name[\"']\s*:\s*[\"']([^\"']+)[\"']", text, re.DOTALL)
    if m:
        return m.group(1)
    return None


# ── Main API ──────────────────────────────────────────────────────────────────


def recursive_infer(
    messages: list,
    task_type: str = "code",
    user_message: str = "",
    max_depth: int = None,
    quality_threshold: float = None,
    extra_stop: list = None,
    stream: bool = True,
    return_confidence: bool = False,
):
    """
    Self-refining inference: draft → critique → refine loop.

    Wraps core/inference_v2.infer() without changing the agent's message history
    or tool-call protocol. The refined response is returned in place of the
    plain infer() response.

    Args:
        messages:          Full message list (system + history + user message)
        task_type:         "code" | "write_file" | "patch_file" | "plan" | "tool"
        user_message:      Original user message text (for KB retrieval queries)
        max_depth:         Max critique+refine cycles (default from RECURSIVE_CONFIG)
        quality_threshold: 0–1 gate; above this the draft is accepted (default 0.7)
        extra_stop:        Additional stop tokens forwarded to infer()
        stream:            Whether to stream final output tokens (default True)
        return_confidence: If True, return (response, low_confidence, quality) instead
                           of just the response string. low_confidence is True only
                           when max_depth was reached and the final rating is below
                           LOW_CONFIDENCE_FLOOR. Default False preserves the plain
                           string return for existing callers (e.g. core/orchestrator.py).

    Returns:
        Final (possibly refined) response string, or a
        (response, low_confidence, quality) tuple if return_confidence=True.
        Never raises — errors are returned as "[ERROR] ..." strings matching the
        normal infer() contract.
    """

    # Sub-task 1 (attribution logging, WORK_QUEUE.md "7B coder system-prompt
    # round"): tracks how many critique/refine cycles this call actually ran,
    # so the final log line can tell a future live-verifier pass whether a
    # given turn's tool call came from the recursive draft/critique/refine
    # path (this module) or, for the config-disabled fallback below, from a
    # plain infer() call made through this same function. Note: this module
    # has no visibility into core/agent.py's *other* plain-infer() branch
    # (the `step != 1` case that bypasses recursive_infer() entirely) — that
    # branch is out of this task's file scope (core/agent.py), so it produces
    # no log line here at all; its absence is itself the signal.
    _cycles_run = 0

    def _finish(text, low_confidence=False, quality=None, path="recursive"):
        tool_name = _extract_tool_name(text)
        info(
            f"[Recursive] Turn attribution: path={path} cycles={_cycles_run} "
            f"tool={tool_name or 'none'}"
        )
        if return_confidence:
            return text, low_confidence, quality
        return text

    # Guard: return immediately if recursive inference is disabled
    if not RECURSIVE_CONFIG.get("enabled", True):
        from core.inference_v2 import infer

        return _finish(
            infer(
                messages, stream=stream, extra_stop=extra_stop or ["</tool>"], show_thinking=True
            ),
            path="plain-infer(recursive-disabled)",
        )

    cfg = RECURSIVE_CONFIG
    if max_depth is None:
        max_depth = cfg.get("max_depth", 1)
    if quality_threshold is None:
        quality_threshold = cfg.get("quality_threshold", 0.7)
    if extra_stop is None:
        extra_stop = ["</tool>"]

    # Phase 8: Adapt depth to thermal/battery state
    max_depth = get_adaptive_depth(max_depth)

    # ── Step 1: Generate initial draft ────────────────────────────────────────
    try:
        from core.inference_v2 import infer
    except Exception as e:
        return _finish(f"[ERROR] recursive_infer: cannot import infer: {e}")

    try:
        _log_phase("Draft", 1, max_depth + 1)
        draft = infer(messages, stream=stream, extra_stop=extra_stop, show_thinking=True)
    except Exception as e:
        return _finish(f"[ERROR] recursive_infer draft: {e}")

    if not draft or draft.startswith("[ERROR]"):
        return _finish(draft)  # propagate immediately

    # Pre-critique: if the step is an action that requires a tool call but the
    # draft contains no <tool> block, the model hallucinated the action (wrote
    # "I created the file" instead of calling write_file). Force one retry with
    # an explicit instruction before entering the critique loop.
    if (
        user_message
        and any(k in user_message.lower() for k in _ACTION_KEYWORDS)
        and not _has_tool_call(draft)
    ):
        warning("[Recursive] No tool call found for action step — forcing tool retry")
        _retry_msgs = messages + [
            {"role": "assistant", "content": draft},
            {
                "role": "user",
                "content": (
                    "You described an action but did not call any tool. "
                    "Output ONLY a <tool> call to perform the action. "
                    "No explanatory text — just the tool call."
                ),
            },
        ]
        try:
            draft = infer(_retry_msgs, stream=stream, extra_stop=extra_stop, show_thinking=True)
        except Exception as _e:
            warning(f"[Recursive] Tool retry failed: {_e}")

    # ── Steps 2…N: Critique + optionally refine ───────────────────────────────
    low_confidence = False
    final_quality = None
    for cycle in range(1, max_depth + 1):
        _cycles_run = cycle

        # ── Phase 3: Critique phase — lean layered prompt ─────────────────────
        # The prior draft is embedded in the system prompt (not the user turn).
        # This keeps the critique call well within the context budget and avoids
        # duplicating context across system + user messages.
        #
        # NEW-59 fix: the full draft is passed through unsliced now — the old
        # `draft[:2000]` cut here, stacked on top of layered_prompt.py's own
        # `prior_draft[:1500]` cut, was a double truncation that could split a
        # <tool>{...}</tool> JSON block mid-string (a real patch_file call's
        # old_str/new_str can easily exceed 1500-2000 chars). The single
        # remaining truncation point (layered_prompt.py's
        # _safe_truncate_draft()) is tool-block-aware and never does this.
        critique_system = build_recursive_prompt(
            user_message=user_message,
            phase="critique",
            prior_draft=draft,
        )
        critique_msgs = [
            {"role": "system", "content": critique_system},
            {
                "role": "user",
                "content": "Rate quality 1-10 and list specific issues (plain text only, no tool calls):",
            },
        ]

        try:
            _log_phase("Review", cycle + 1, max_depth + 1)
            critique_raw = infer(
                critique_msgs,
                stream=False,
                # Block tool calls inside the critique response
                extra_stop=["<tool>", "\nUser:", "\nHuman:"] + MODEL_CONFIG.get("stop", []),
                show_thinking=False,
            )
            critique = _strip_tool_calls(critique_raw).strip()
        except Exception as e:
            warning(f"[Recursive] Critique failed (cycle {cycle}): {e}")
            break  # Accept current draft

        if not critique:
            break  # Empty critique — accept draft

        # Quality gate: if good enough, stop here
        if passes_quality_check(critique, quality_threshold):
            rating = extract_rating(critique)
            final_quality = rating
            if rating is not None:
                info(f"[Recursive] Accepted — quality {rating:.0f}/10")
            else:
                info("[Recursive] Accepted — no critical issues")
            break

        # Last cycle reached — accept draft even if quality didn't pass, but
        # flag it as low-confidence if the rating is below the hard floor so
        # the caller can warn the user instead of presenting it as a normal
        # success.
        if cycle >= max_depth:
            rating = extract_rating(critique)
            final_quality = rating
            if rating is not None:
                info(f"[Recursive] Max depth — using draft (quality {rating:.0f}/10)")
                if rating < LOW_CONFIDENCE_FLOOR:
                    low_confidence = True
                    warning(
                        f"[Recursive] Low-confidence result: quality {rating:.1f}/10 "
                        f"< floor {LOW_CONFIDENCE_FLOOR}"
                    )
            else:
                info("[Recursive] Max depth — using draft")
            break

        # ── Targeted KB retrieval for NEED_DOCS gaps ──────────────────────────
        extra_context = ""
        doc_needs = extract_doc_needs(critique)
        if doc_needs:
            info(f"[Recursive] Retrieving: {doc_needs[:60]}...")
            try:
                from core.retrieval import retrieve

                extra_context = retrieve(doc_needs, budget_chars=1200)
            except Exception:
                pass  # KB unavailable — continue without

        # ── Phase 3: Refine phase — full-context layered prompt, no history ───
        # History is dropped to free ~1000 tokens.  The critique summary in the
        # system prompt replaces history as the "memory" of what went wrong.
        # Targeted retrieved context (NEED_DOCS) is injected here if available.
        #
        # NEW-58 fix: pass the current `draft` (the actual proposal critique
        # just reviewed, including any real <tool>{...}</tool> call) forward
        # as prior_draft, so refine can see and revise its own prior proposal
        # instead of regenerating the entire response from scratch with zero
        # memory of what it originally proposed (e.g. a patch_file call's
        # exact old_str/new_str). layered_prompt.py applies the same
        # tool-block-aware truncation used by critique (NEW-59), so this
        # doesn't reintroduce a mid-JSON-split bug in a new location.
        refine_system = build_recursive_prompt(
            user_message=user_message,
            phase="refine",
            prior_draft=draft,
            prior_critique=critique,
            retrieved_context=extra_context,
        )
        refine_messages = [
            {"role": "system", "content": refine_system},
            {
                "role": "user",
                "content": (
                    f"{user_message}\n\n"
                    "Revise your response to fix all issues listed in the system prompt above. "
                    "Output ONLY the revised response — nothing else."
                ),
            },
        ]

        try:
            _log_phase("Refine", cycle + 1, max_depth + 1)
            draft = infer(refine_messages, stream=stream, extra_stop=extra_stop, show_thinking=True)
        except Exception as e:
            warning(f"[Recursive] Refine failed (cycle {cycle}): {e}")
            break  # Return last known good draft

        if not draft or draft.startswith("[ERROR]"):
            break  # Propagate or fall back

    return _finish(draft, low_confidence, final_quality)
