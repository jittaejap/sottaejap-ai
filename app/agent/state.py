"""한 번의 Agent 실행에 필요한 현재 Context.

영구 대화 상태를 저장하지 않으며 Spring이 전달한 현재 Task와 최소 최근 대화만 담는다.
"""

from typing import Any

from pydantic import BaseModel, Field

from app.schemas.chat import ChatMessage, ChatRequest
from app.schemas.common import TaskStatus, TaskType


class AgentState(BaseModel):
    """단일 요청 동안만 유지되는 Agent 상태."""

    user_id: str | None = None
    message: str
    task: TaskType | None = None
    task_status: TaskStatus | None = None
    structured_state: dict[str, Any] = Field(default_factory=dict)
    recent_messages: list[ChatMessage] = Field(default_factory=list)

    @classmethod
    def from_request(cls, request: ChatRequest) -> "AgentState":
        """느슨한 외부 Task Context를 안전한 실행 상태로 변환한다."""

        context = request.task_context or {}
        task = _optional_enum(TaskType, context.get("task"))
        task_status = _optional_enum(TaskStatus, context.get("status"))
        structured_state = context.get("state", {})
        if not isinstance(structured_state, dict):
            structured_state = {}

        return cls(
            user_id=request.user_id,
            message=request.message,
            task=task,
            task_status=task_status,
            structured_state=structured_state,
            recent_messages=request.recent_messages,
        )


def _optional_enum(enum_type: type[TaskType] | type[TaskStatus], value: Any) -> Any:
    """알 수 없는 외부 상태를 임의 해석하지 않고 None으로 둔다."""

    if value is None:
        return None
    try:
        return enum_type(value)
    except (TypeError, ValueError):
        return None

