"""
TaskContext — In-flight structured context passing between execution stages.

Per Vision §11.2 and Track A Item 7.5:
Compact structured record scoped to what the next stage actually needs,
preventing raw conversation context dumps and RAM bloat.
Enforces a 64 KB ceiling (MAX_CONTEXT_PAYLOAD_BYTES = 64 * 1024).
"""

import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

MAX_CONTEXT_PAYLOAD_BYTES: int = 64 * 1024  # 64 KB ceiling per vision §11.2


class ContextPayloadTooLargeError(ValueError):
    """Raised when TaskContext serialized payload exceeds MAX_CONTEXT_PAYLOAD_BYTES."""
    pass


_UNSET = object()


@dataclass(frozen=True)
class TaskContext:
    """
    Immutable structured task context record threaded across capability calls.

    Attributes:
        task_id: Unique task session identifier.
        step_id: Current stage / step identifier.
        goal: The overarching goal of the task session.
        current_app: Current active application or domain scope (e.g. 'com.google.android.gm').
        state: Compact domain state dictionary.
        inputs: Input arguments passed to current step.
        output: Execution result / output of the step.
        next_action: Proposed next action or capability name.
        confidence: Confidence score of output / proposal (0.0 - 1.0).
        parent_step_id: ID of the antecedent step that produced or transitioned to this step.
        created_at: Epoch timestamp of context creation.
        metadata: Extensible metadata dictionary for tags/tracing.
    """
    task_id: str
    step_id: str
    goal: str
    current_app: str = ""
    state: Dict[str, Any] = field(default_factory=dict)
    inputs: Dict[str, Any] = field(default_factory=dict)
    output: Any = None
    next_action: str = ""
    confidence: float = 1.0
    parent_step_id: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        # Validate size on construction
        self.validate_size()

    def validate_size(self) -> int:
        """
        Validate that the serialized context payload does not exceed MAX_CONTEXT_PAYLOAD_BYTES.

        Returns:
            The size in bytes of the JSON payload.

        Raises:
            ContextPayloadTooLargeError: If size exceeds MAX_CONTEXT_PAYLOAD_BYTES.
        """
        payload = self.to_json()
        payload_bytes = len(payload.encode("utf-8"))
        if payload_bytes > MAX_CONTEXT_PAYLOAD_BYTES:
            raise ContextPayloadTooLargeError(
                f"TaskContext payload size ({payload_bytes} bytes) exceeds "
                f"MAX_CONTEXT_PAYLOAD_BYTES ({MAX_CONTEXT_PAYLOAD_BYTES} bytes). "
                f"Per Vision §11.2, pass compact structured records, not raw conversation dumps."
            )
        return payload_bytes

    def evolve(
        self,
        step_id: Optional[str] = None,
        output: Any = _UNSET,
        state: Optional[Dict[str, Any]] = None,
        inputs: Optional[Dict[str, Any]] = None,
        current_app: Optional[str] = None,
        next_action: Optional[str] = None,
        confidence: Optional[float] = None,
        parent_step_id: Optional[str] = _UNSET,
        metadata: Optional[Dict[str, Any]] = None,
        goal: Optional[str] = None,
    ) -> "TaskContext":
        """
        Copy-on-write stage progression.

        Returns a new TaskContext instance with updated fields.
        Automatically sets parent_step_id to current step_id if a new step_id
        is provided and parent_step_id is not explicitly specified.
        """
        new_step_id = step_id if step_id is not None else self.step_id
        if parent_step_id is _UNSET:
            if step_id is not None and step_id != self.step_id:
                new_parent_step_id = self.step_id
            else:
                new_parent_step_id = self.parent_step_id
        else:
            new_parent_step_id = parent_step_id

        new_output = self.output if output is _UNSET else output
        new_current_app = current_app if current_app is not None else self.current_app
        new_next_action = next_action if next_action is not None else self.next_action
        new_confidence = confidence if confidence is not None else self.confidence
        new_goal = goal if goal is not None else self.goal

        # Merge or replace state
        if state is not None:
            merged_state = dict(self.state)
            merged_state.update(state)
        else:
            merged_state = dict(self.state)

        # Merge or replace inputs
        if inputs is not None:
            merged_inputs = dict(self.inputs)
            merged_inputs.update(inputs)
        else:
            merged_inputs = dict(self.inputs)

        # Merge or replace metadata
        if metadata is not None:
            merged_metadata = dict(self.metadata)
            merged_metadata.update(metadata)
        else:
            merged_metadata = dict(self.metadata)

        return TaskContext(
            task_id=self.task_id,
            step_id=new_step_id,
            goal=new_goal,
            current_app=new_current_app,
            state=merged_state,
            inputs=merged_inputs,
            output=new_output,
            next_action=new_next_action,
            confidence=new_confidence,
            parent_step_id=new_parent_step_id,
            created_at=time.time(),
            metadata=merged_metadata,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert TaskContext to a JSON-serializable dictionary."""
        return {
            "task_id": self.task_id,
            "step_id": self.step_id,
            "goal": self.goal,
            "current_app": self.current_app,
            "state": self.state,
            "inputs": self.inputs,
            "output": self.output,
            "next_action": self.next_action,
            "confidence": self.confidence,
            "parent_step_id": self.parent_step_id,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }

    def to_json(self) -> str:
        """Serialize TaskContext to a compact JSON string."""
        return json.dumps(self.to_dict(), default=str, separators=(",", ":"))

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskContext":
        """Reconstruct a TaskContext instance from a dictionary."""
        return cls(
            task_id=data.get("task_id", ""),
            step_id=data.get("step_id", ""),
            goal=data.get("goal", ""),
            current_app=data.get("current_app", ""),
            state=data.get("state", {}),
            inputs=data.get("inputs", {}),
            output=data.get("output"),
            next_action=data.get("next_action", ""),
            confidence=float(data["confidence"]) if data.get("confidence") is not None else 1.0,
            parent_step_id=data.get("parent_step_id"),
            created_at=float(data["created_at"]) if data.get("created_at") is not None else time.time(),
            metadata=data.get("metadata", {}),
        )

    @classmethod
    def from_json(cls, json_str: str) -> "TaskContext":
        """Reconstruct a TaskContext instance from a JSON string."""
        data = json.loads(json_str)
        return cls.from_dict(data)
