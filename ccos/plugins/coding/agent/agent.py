"""
Agent Plugin — CCOS capability wrapper over core/agent.py and core/recursive.py.

Provides path-addressable, stateless CCOS capabilities for autonomous coding,
recursive self-refinement, and breadth classification with fine-grained
permission and shell-execution scoping.
"""
from ccos.plugins._pathutil import ensure_repo_root_on_path

ensure_repo_root_on_path()

from contextlib import contextmanager
from typing import Any, Callable, Dict, List, Optional

from ccos.core.task_context import TaskContext
import utils.config
from utils.config import AGENT_CONFIG


class AgentExecutionResult(dict):
    """
    Result of an agent capability run.

    Subclasses dict with keys: 'response', 'history', 'success', 'error'.
    Supports unpacking as (response, history) for backward compatibility with
    standard run_agent() callers.
    """

    def __init__(
        self,
        response: str = "",
        history: Optional[List[Dict[str, Any]]] = None,
        success: bool = True,
        error: str = "",
    ):
        if history is None:
            history = []
        super().__init__(
            response=response,
            history=history,
            success=success,
            error=error,
        )

    @property
    def response(self) -> str:
        return self["response"]

    @property
    def history(self) -> List[Dict[str, Any]]:
        return self["history"]

    @property
    def success(self) -> bool:
        return self["success"]

    @property
    def error(self) -> str:
        return self["error"]

    def __iter__(self):
        """Unpack cleanly as (response, history)."""
        return iter((self["response"], self["history"]))


_UNSET = object()


@contextmanager
def scoped_agent_permissions(
    confirm_shell: Any = _UNSET,
    confirm_write: Any = _UNSET,
    shell_fn: Any = _UNSET,
):
    """
    Context manager to safely override and restore AGENT_CONFIG permissions/hooks.

    Guarantees restoration of previous values on both normal exit and exceptions.
    """
    agent_cfg = utils.config.AGENT_CONFIG
    saved: Dict[str, Any] = {}
    if confirm_shell is not _UNSET:
        saved["confirm_shell"] = agent_cfg.get("confirm_shell")
        agent_cfg["confirm_shell"] = confirm_shell
    if confirm_write is not _UNSET:
        saved["confirm_write"] = agent_cfg.get("confirm_write")
        agent_cfg["confirm_write"] = confirm_write
    if shell_fn is not _UNSET:
        saved["_shell_fn"] = agent_cfg.get("_shell_fn")
        agent_cfg["_shell_fn"] = shell_fn

    try:
        yield
    finally:
        for k, v in saved.items():
            agent_cfg[k] = v


def run_agent_capability(
    prompt: str = "",
    history: Optional[List[Dict[str, Any]]] = None,
    yolo: bool = False,
    use_plan: bool = False,
    no_plan: bool = False,
    in_subtask: bool = False,
    plan_rag_block: str = "",
    confirm_shell: Optional[bool] = None,
    confirm_write: Optional[bool] = None,
    shell_fn: Optional[Callable[[str], str]] = None,
    context: Optional[TaskContext] = None,
    **kwargs,
) -> AgentExecutionResult:
    """
    Run the full Codey-OS agent loop with scoped permissions, planning, tool execution,
    and self-healing. Supports in-flight TaskContext passing.
    """
    from core.agent import run_agent

    if history is None:
        history = []

    user_msg = prompt or kwargs.get("user_message", "")
    if not user_msg and context is not None:
        user_msg = (
            context.inputs.get("prompt")
            or context.inputs.get("user_message")
            or context.goal
        )

    subtask_flag = in_subtask or kwargs.get("_in_subtask", False)
    rag_block = plan_rag_block or kwargs.get("_plan_rag_block", "")

    perm_kwargs = {}
    if confirm_shell is not None:
        perm_kwargs["confirm_shell"] = confirm_shell
    if confirm_write is not None:
        perm_kwargs["confirm_write"] = confirm_write
    if shell_fn is not None:
        perm_kwargs["shell_fn"] = shell_fn

    try:
        with scoped_agent_permissions(**perm_kwargs):
            response, updated_history = run_agent(
                user_message=user_msg,
                history=history,
                yolo=yolo,
                use_plan=use_plan,
                no_plan=no_plan,
                _in_subtask=subtask_flag,
                _plan_rag_block=rag_block,
            )
            return AgentExecutionResult(
                response=response,
                history=updated_history,
                success=True,
                error="",
            )
    except Exception as e:
        return AgentExecutionResult(
            response="",
            history=history,
            success=False,
            error=str(e),
        )


def run_recursive_capability(
    messages: Optional[List[Dict[str, Any]]] = None,
    task_type: str = "code",
    user_message: str = "",
    max_depth: Optional[int] = None,
    return_confidence: bool = False,
    context: Optional[TaskContext] = None,
    **kwargs,
) -> Any:
    """
    Self-refining inference using draft -> critique -> refine loop via core/recursive.py.
    Supports in-flight TaskContext passing.
    """
    from core.recursive import recursive_infer

    if messages is None:
        if context is not None and "messages" in context.inputs:
            messages = context.inputs["messages"]
        else:
            messages = []

    msg = user_message
    if not msg and context is not None:
        msg = (
            context.inputs.get("user_message")
            or context.inputs.get("prompt")
            or context.goal
        )

    return recursive_infer(
        messages=messages,
        task_type=task_type,
        user_message=msg,
        max_depth=max_depth,
        return_confidence=return_confidence,
        **kwargs,
    )


def classify_breadth_capability(
    user_message: str = "",
    context: Optional[TaskContext] = None,
    **kwargs,
) -> str:
    """
    Classify task complexity and breadth need (minimal, standard, deep).
    Supports in-flight TaskContext passing.
    """
    from core.recursive import classify_breadth_need

    msg = user_message or kwargs.get("prompt", "")
    if not msg and context is not None:
        msg = (
            context.inputs.get("user_message")
            or context.inputs.get("prompt")
            or context.goal
        )
    return classify_breadth_need(msg)


def test() -> bool:
    """Plugin self-test — verify permission scoping, result unpacking, and breadth classification."""
    # 1. Scoped permissions test
    orig_shell = AGENT_CONFIG.get("confirm_shell")
    orig_write = AGENT_CONFIG.get("confirm_write")
    orig_fn = AGENT_CONFIG.get("_shell_fn")

    dummy_fn = lambda cmd: "dummy_output"
    with scoped_agent_permissions(confirm_shell=False, confirm_write=False, shell_fn=dummy_fn):
        assert AGENT_CONFIG.get("confirm_shell") is False
        assert AGENT_CONFIG.get("confirm_write") is False
        assert AGENT_CONFIG.get("_shell_fn") is dummy_fn

    assert AGENT_CONFIG.get("confirm_shell") == orig_shell
    assert AGENT_CONFIG.get("confirm_write") == orig_write
    assert AGENT_CONFIG.get("_shell_fn") == orig_fn

    # 2. AgentExecutionResult unpacking test
    res = AgentExecutionResult(
        response="hello",
        history=[{"role": "user", "content": "hi"}],
        success=True,
        error="",
    )
    r, h = res
    assert r == "hello"
    assert len(h) == 1
    assert res["success"] is True
    assert res.response == "hello"
    assert res.error == ""

    # 3. Breadth classification test with context
    assert classify_breadth_capability("what is 2+2?") == "minimal"
    ctx = TaskContext(task_id="t1", step_id="s1", goal="what is 2+2?")
    assert classify_breadth_capability(context=ctx) == "minimal"

    return True
