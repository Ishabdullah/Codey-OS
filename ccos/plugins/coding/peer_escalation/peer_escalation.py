"""
Peer CLI Escalation Plugin — thin CCOS adapter over core/peer_cli.py's
read-only discovery/selection logic.

core/peer_cli.py's escalate() is the top-level entry point core/agent.py:1715
uses when Codey exhausts its retry budget on a task. Before it ever spawns an
external CLI (via core/peer_shell.py's run_peer/run_direct/run_prompted/
run_positional), it runs PeerCLIManager.confirm() — a blocking terminal
prompt (console.input) that requires the user to type y / n / a CLI name /
a redirect instruction. That interactive confirmation *is* the "explicit
user consent before any files are shared" mechanism
CODEY_OS_MASTER_VISION.md refers to for peer CLI escalation.

That consent step only makes sense attached to a live interactive terminal
session — there is no way to preserve its meaning behind an automated
capability call, since a capability invoked by an agent has no user sitting
at a prompt to answer it. So escalate() itself, along with confirm() and
call() (and, via call(), peer_shell.py's run_peer/run_direct/run_prompted/
run_positional), are deliberately left unwrapped here. Wrapping them would
either hang on stdin in a non-interactive context, or — if some default
answer were fed in to avoid that — silently bypass the one consent gate
that exists. Same risk class as daemon_control's unwrapped `command`
handler and finetune's unwrapped model-swap functions: flagged for Ish's
explicit decision rather than wrapped mechanically. They remain reachable
exactly as before, via core/agent.py:1715's normal escalation path
(main.py:999 and core/agent.py:978 are the other existing callers).

What IS wrapped here: pure discovery/selection/preview logic that never
spawns a peer CLI session and never sends anything off-device — which peer
CLIs are installed, what task type a message would be classified as, which
CLI would be picked for it, and what prompt text would be sent if
escalation proceeded. These read the same logic escalate() uses internally,
without triggering the side effects escalate() has once consent is given.
"""

from ccos.plugins._pathutil import ensure_repo_root_on_path

ensure_repo_root_on_path()

from typing import Dict, List, Optional

from core.peer_cli import get_peer_cli_manager


def peer_list_available() -> List[Dict]:
    """Read-only: list peer CLIs (claude/gemini/qwen) detected as installed on this device."""
    mgr = get_peer_cli_manager()
    return [
        {"name": c.name, "description": c.description, "strengths": c.strengths}
        for c in mgr.available()
    ]


def peer_detect_task_type(user_message: str, errors: Optional[List[str]] = None) -> Dict:
    """Read-only: classify a message/error log into the task type escalate() would use."""
    mgr = get_peer_cli_manager()
    return {"task_type": mgr.detect_task_type(user_message, errors or [])}


def peer_select_cli(task_type: str, exclude: Optional[List[str]] = None) -> Dict:
    """Read-only: which installed peer CLI would be picked for a task type, without calling it."""
    mgr = get_peer_cli_manager()
    cli = mgr.select_cli(task_type, exclude=exclude or [])
    if cli is None:
        return {"selected": None}
    return {"selected": {"name": cli.name, "description": cli.description, "strengths": cli.strengths}}


def peer_build_prompt(
    user_message: str,
    errors: Optional[List[str]] = None,
    files: Optional[List[str]] = None,
) -> Dict:
    """Read-only: preview the exact prompt text escalate() would send to a peer CLI, without sending it."""
    mgr = get_peer_cli_manager()
    return {"prompt": mgr.build_prompt(user_message, errors or [], files or [])}


def test() -> bool:
    """Plugin self-test — verify a read-only, no-subprocess-spawn capability runs."""
    result = peer_detect_task_type("please refactor this module")
    assert result == {"task_type": "refactor"}, f"Unexpected result: {result}"
    return True
