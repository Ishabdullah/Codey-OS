"""
Peer CLI Escalation Plugin — CCOS adapter over core/peer_cli.py's
discovery/selection/preview and peer delegation logic.
"""

from ccos.plugins._pathutil import ensure_repo_root_on_path

ensure_repo_root_on_path()

from typing import Dict, List, Optional

from core.peer_cli import get_peer_cli_manager


def peer_list_available(include_disabled: bool = True) -> List[Dict]:
    """List peer CLIs (antigravity/qwen/claude) detected as installed on this device."""
    mgr = get_peer_cli_manager()
    return [
        {
            "name": c.name,
            "description": c.description,
            "strengths": c.strengths,
            "aliases": c.aliases,
            "enabled": c.enabled,
            "disabled_reason": c.disabled_reason,
        }
        for c in mgr.available(include_disabled=include_disabled)
    ]


def peer_detect_task_type(user_message: str, errors: Optional[List[str]] = None) -> Dict:
    """Read-only: classify a message/error log into the task type escalate() would use."""
    mgr = get_peer_cli_manager()
    return {"task_type": mgr.detect_task_type(user_message, errors or [])}


def peer_select_cli(task_type: str, exclude: Optional[List[str]] = None) -> Dict:
    """Read-only: which installed and enabled peer CLI would be picked for a task type, without calling it."""
    mgr = get_peer_cli_manager()
    cli = mgr.select_cli(task_type, exclude=exclude or [])
    if cli is None:
        return {"selected": None}
    return {
        "selected": {
            "name": cli.name,
            "description": cli.description,
            "strengths": cli.strengths,
            "aliases": cli.aliases,
            "enabled": cli.enabled,
        }
    }


def peer_build_prompt(
    user_message: str,
    errors: Optional[List[str]] = None,
    files: Optional[List[str]] = None,
) -> Dict:
    """Read-only: preview the exact prompt text escalate() would send to a peer CLI, without sending it."""
    mgr = get_peer_cli_manager()
    return {"prompt": mgr.build_prompt(user_message, errors or [], files or [])}


def peer_delegate(peer: str, task: str) -> Dict:
    """Delegate a task to a peer CLI with fallback handling."""
    from core.agent import tool_peer_delegate

    result = tool_peer_delegate(peer, task)
    return {"result": result}


def test() -> bool:
    """Plugin self-test — verify read-only functions and delegation tool."""
    result = peer_detect_task_type("please refactor this module")
    assert result == {"task_type": "refactor"}, f"Unexpected result: {result}"
    return True
