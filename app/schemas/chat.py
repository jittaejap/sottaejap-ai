"""POST /chat 요청과 응답 DTO (05 §3)."""

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.tool import ToolResult


class ChatMessage(BaseModel):
    """Agent에 선택적으로 전달할 최소 최근 대화."""

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1)


class ChatRequest(BaseModel):
    """Spring이 AI 서버에 전달하는 채팅 요청."""

    message: str = Field(min_length=1)
    user_id: str | None = None
    task_context: dict[str, Any] | None = None
    recent_messages: list[ChatMessage] = Field(default_factory=list)


class ChatResponse(BaseModel):
    """Single Agent의 자연어 응답과 Tool 실행 결과.

    `fallback`은 LLM 8초 초과·오류로 템플릿 응답을 돌려줄 때 True다 (FR-04-15 · NFR-04).
    """

    reply: str
    tool_results: list[ToolResult] = Field(default_factory=list)
    needs_clarification: bool = False
    fallback: bool = False
