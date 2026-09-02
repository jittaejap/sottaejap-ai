"""Tool 입출력에 공통으로 사용하는 DTO."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ToolName(StrEnum):
    """Agent에 등록할 수 있는 Tool 식별자."""

    TRANSACTION = "transaction"
    REFLECTION = "reflection"
    ANALYSIS = "analysis"
    ACTION_PLAN = "action_plan"
    MEMORY = "memory"
    FINANCIAL_RAG = "financial_rag"


class ToolRequest(BaseModel):
    """Tool 호출 시 전달하는 공통 요청 형태."""

    user_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    """Tool 결과를 Agent가 일관되게 다루기 위한 DTO."""

    tool_name: ToolName
    success: bool = True
    data: Any | None = None
    message: str | None = None

