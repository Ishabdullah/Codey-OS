"""
planner_client — async planning interface for Codey-OS

Sends a raw user task to the 1.5B model on port 8081 for planning,
then returns the numbered step list.  Designed to be awaited directly
from the main daemon's async event loop.

Failure contract:
  - If the 1.5B server is unreachable or returns no steps → returns None
  - Any other error → returns None so caller falls back to direct execution
"""

import asyncio
from typing import List, Optional


async def send_plan_request_async(task: str) -> Optional[List[str]]:
    """
    Ask the 1.5B model to plan *task* and return the list of step strings.

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
