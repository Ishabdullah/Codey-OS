"""
core/planner_service.py — unified planning interface.

Provides a single entry point for task planning that encapsulates the
fallback hierarchy:

  1. Daemon planner (0.5B or remote) via Unix socket — fast, low overhead.
  2. Orchestrator plan_tasks (7B recursive_infer) — used when the daemon is
     unavailable or returns no steps.

Both main.py and core/agent.py should go through this module so planning
behaviour is consistent regardless of how the CLI is invoked.
"""

from utils.logger import info


def get_plan(prompt: str, no_plan: bool = False, project_context: str = ""):
    """
    Return a step list for *prompt*, or None if planning is skipped/unavailable.

    Fallback order:
      1. Daemon planner (plannd / 0.5B / remote backend).
      2. Orchestrator plan_tasks (7B recursive).

    Args:
        prompt:          The user message to plan.
        no_plan:         Skip planning entirely when True.
        project_context: Optional CODEY.md / project summary passed to
                         plan_tasks when falling back to the 7B planner.

    Returns:
        list[str] of step descriptions, or None.
    """
    if no_plan:
        return None

    # ── Tier classification (log-only) ──────────────────────────────────────
    # TODO.md 7.3 sub-task C: decide, don't act. classify_tier()'s answer is
    # observed here for visibility into what a future tier-aware dispatch
    # (sub-task E, blocked on 7.4's resource gate closing) would choose — it
    # must NOT influence which model path/port the fallback ladder below
    # actually uses. Any failure to classify must not affect planning, so
    # this is best-effort and swallows its own exceptions.
    #
    # NOTE (NEW-126, logged not fixed): under current
    # core.orchestrator._action_kws, almost every realistic coding prompt
    # matches at least one action keyword, so this will log 'large' for
    # substantially all traffic while the ladder below still tries the
    # small/daemon planner first — the log disagrees with the executed path
    # by default. The raw signal breakdown is included below specifically so
    # these logs remain useful evidence for tuning sub-task E's thresholds
    # later, rather than being a string of "large" with no discriminating
    # detail.
    try:
        from core.model_tiers import classify_tier
        from core.orchestrator import _score_message

        tier = classify_tier("coding", "planner", prompt)
        score = _score_message(prompt)
        info(
            f"classify_tier: would select '{tier}' tier for coding/planner (log-only, not acted on) "
            f"(has_action={score.has_action}, length={score.length}, signal_count={score.signal_count})"
        )
    except Exception as _e:
        info(f"classify_tier unavailable ({type(_e).__name__}) — continuing with existing fallback ladder")

    # ── Attempt 1: daemon planner ─────────────────────────────────────────────
    plan = _request_daemon_plan(prompt)
    if plan:
        return plan

    # ── Attempt 2: in-process 7B orchestrator ────────────────────────────────
    try:
        from core.orchestrator import plan_tasks

        queue = plan_tasks(prompt, project_context)
        if queue and queue.tasks:
            return [t.description for t in queue.tasks]
    except Exception as _e:
        info(f"Orchestrator planner unavailable ({type(_e).__name__}) — running directly")

    return None


def _request_daemon_plan(prompt: str):
    """
    Send *prompt* to the running plannd daemon and return the step list.
    Returns None on any failure or when the daemon is not running.
    """
    try:
        from core.daemon import is_daemon_running, send_command

        if not is_daemon_running():
            return None
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
                info("Requesting plan from 0.5B planner...")
        except Exception:
            info("Requesting plan from planner...")

        response = send_command(
            "command",
            {"prompt": prompt, "no_plan": False, "plan_only": True},
            timeout=185,
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
