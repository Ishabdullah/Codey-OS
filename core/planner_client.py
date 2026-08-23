"""
planner_client — async planning interface for Codey-OS

Sends a raw user task to the primary Qwen3.5-4B server (thinking mode) for
planning, then returns the numbered step list. Designed to be awaited
directly from the main daemon's async event loop.

M1-D (2026-08-23): this used to describe a dedicated 1.5B model on its own
port (8081) — that server is retired, planning now shares the primary
server core/plannd.py:get_plan() already talks to; see that module's own
docstring for the current shape.

Failure contract:
  - If the primary server is unreachable or returns no steps → returns None
  - Any other error → returns None so caller falls back to direct execution
"""

import asyncio
from typing import List, Optional


async def send_plan_request_async(task: str) -> Optional[List[str]]:
    """
    Ask the primary model to plan *task* and return the list of step strings.

    Delegates to core.plannd.get_plan (blocking HTTP call) via
    run_in_executor so the daemon event loop is not stalled.

    Returns None if planning fails or produces fewer than 1 step, so the
    caller falls through to the direct-execution path unchanged.
    """
    from core.plannd import get_plan

    loop = asyncio.get_running_loop()
    steps = await loop.run_in_executor(None, get_plan, task)
    if steps and isinstance(steps, list) and len(steps) > 0:
        return [str(s) for s in steps]
    return None
