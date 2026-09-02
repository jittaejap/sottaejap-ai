"""공통 상태와 응답 DTO.

서비스 계층 사이에서 공유하는 최소 상태만 정의하며 비즈니스 판정은 하지 않는다.
"""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class TaskType(StrEnum):
    """Spring이 전달할 수 있는 현재 사용자 작업 종류."""

    REFLECTION = "REFLECTION"
    ANALYSIS = "ANALYSIS"
    ACTION_PLAN = "ACTION_PLAN"


class TaskStatus(StrEnum):
    """Spring이 관리하는 작업 진행 상태."""

    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"


class HealthResponse(BaseModel):
    """서버 상태 확인 응답."""

    status: str = "ok"
    service: str = "sottaejab-ai-server"


class ApiResponse(BaseModel):
    """필요할 때 확장할 수 있는 범용 내부 응답."""

    success: bool
    data: Any | None = None
    message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

