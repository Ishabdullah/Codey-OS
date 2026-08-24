"""
core/planner_service.py — daemon planner request helper.

NEW-172 (NEW_ISSUES.md, fixed here): this module used to also define
get_plan(), advertised as "a single entry point for task planning" that
"both main.py and core/agent.py should go through" — that claim was untrue
for either caller (main.py's _try_daemon_plan() calls
_request_daemon_plan() directly, core/agent.py's own get_plan() is a
different function in core/planner.py) and get_plan() had zero production
callers. It's deleted; this module now contains only
_request_daemon_plan(), the one function actually called
(main.py:_try_daemon_plan()).

NEW-124 (NEW_ISSUES.md, fixed here): this docstring and the comments below
used to say the daemon planner is "0.5B or remote" — stale even before
M1-D, since the model had already been upgraded to a dedicated 1.5B (see
utils/config.py's own comment history) well before this docstring was
written. M1-D (2026-08-23) makes it moot either way: the dedicated planner
process (core/plannd.py's former 1.5B on port 8081, managed by the
now-deleted core/planner_loader.py) is retired. There is no longer a
second local model at all — "the daemon planner" now means "the primary
Qwen3.5-4B server, asked with `chat_template_kwargs: {enable_thinking:
true}`" (see core/plannd.py:get_plan()), not a separate smaller model.
"""

from utils.logger import info


def _request_daemon_plan(prompt: str):
    """
    Send *prompt* to the running plannd daemon and return the step list.
    Returns None on any failure or when the daemon is not running.
    """
    try:
        from core.daemon import is_daemon_running, send_command

        if not is_daemon_running():
            return None

        # NEW-169: this socket timeout used to be a flat 185s, independent
        # of NEW-164/165/167's formula-based timeouts in plannd.py/daemon.py
        # below it. Those fixes raised the *server-side* budget for a
        # thinking-mode plan to well over 1300s at PLANNER_MAX_TOKENS=2048 —
        # but this call is the outermost, client-side wrapper around the
        # whole RPC round trip (Unix socket, not HTTP), and it was never
        # updated to match. A flat 185s here meant the client gave up and
        # raised ConnectionError long before either server-side fix could
        # matter, for any plan needing more than 185s — which every one of
        # NEW-164/165/167's own worked examples already exceeded. Derive
        # this timeout from the same formula/inputs core/daemon.py's
        # _handle_command uses for its own outer wait_for (compute_planner_
        # timeout() + 30.0s), plus a small extra buffer for the socket
        # round trip itself, so this client always outlives every timeout
        # nested inside it rather than being the shortest one in the chain.
        try:
            from core.plannd import PLANNER_PROMPT, compute_planner_timeout
            from core.tokens import estimate_tokens
            from utils.config import PLANNER_MAX_TOKENS

            prompt_tokens_estimate = estimate_tokens(PLANNER_PROMPT) + estimate_tokens(prompt)
            daemon_outer_timeout = compute_planner_timeout(prompt_tokens_estimate, PLANNER_MAX_TOKENS) + 30.0
            socket_timeout = daemon_outer_timeout + 10.0
        except Exception:
            # Same degrade-gracefully convention as every other utils.config/
            # core.* dependency in this function: a broken import shouldn't
            # crash planning, it should fall back to a safe, generous flat
            # value comfortably above the pre-recalibration worst case.
            socket_timeout = 1400.0

        try:
            from utils.config import (CODEY_PLANNER_BACKEND,
                                      OPENROUTER_PLANNER_MODEL,
                                      UNLIMITEDCLAUDE_PLANNER_MODEL,
                                      is_remote_planner_backend)

            if is_remote_planner_backend():
                pm = (
                    UNLIMITEDCLAUDE_PLANNER_MODEL
                    if CODEY_PLANNER_BACKEND == "unlimitedclaude"
                    else OPENROUTER_PLANNER_MODEL
                )
                info(f"Requesting plan from {CODEY_PLANNER_BACKEND} planner ({pm})...")
            else:
                info("Requesting plan from local planner (primary model, thinking mode)...")
        except Exception:
            info("Requesting plan from planner...")

        response = send_command(
            "command",
            {"prompt": prompt, "no_plan": False, "plan_only": True},
            timeout=socket_timeout,
        )
        plan = response.get("plan")
        if plan and isinstance(plan, list) and len(plan) > 1:
            return plan
        if not plan:
            info("Planner returned no steps — running directly")
        elif len(plan) == 1:
            info("Planner returned 1 step — running directly")
    except Exception as _e:
        info(f"Planner unavailable ({type(_e).__name__}) — running directly")
    return None
