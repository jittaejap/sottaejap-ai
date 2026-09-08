"""Task Handler가 공유하는 LLM·Tool 실행 경계."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import httpx

from app.agent.prompt import build_system_prompt
from app.agent.state import AgentState
from app.agent.tool_registry import ToolRegistry
from app.clients.spring_client import SpringApiError
from app.core.llm import LLMClient
from app.rag.retriever import RetrieverUnavailableError
from app.schemas.chat import ChatResponse
from app.schemas.tool import ToolName, ToolRequest, ToolResult

_TOOL_FAILURE_MESSAGE = "Tool 결과를 가져오지 못했습니다."


@dataclass(frozen=True)
class HandlerContext:
    """Handler가 공통 경계를 중복 구현하지 않도록 제공하는 요청 Context.

    Handler는 ``LLMNotConfiguredError``와 ``LLMUnavailableError``를 잡지 않는다.
    두 예외의 폴백 전환은 ``SingleAgent.run`` 한 곳에서 담당한다.
    """

    state: AgentState
    llm: LLMClient
    tools: ToolRegistry

    async def generate(self, instruction: str = "") -> str:
        """현재 요청 맥락과 Task별 지시문으로 LLM 응답을 생성한다."""

        return await self.llm.generate(
            build_system_prompt(self.state, instruction),
            self.state.message,
        )

    async def call_tool(
        self,
        name: ToolName,
        payload: dict[str, Any],
    ) -> ToolResult:
        """Tool 조회·실행 실패를 실패 결과로 변환한다."""

        try:
            handler = self.tools.get(name)
            return await handler(
                ToolRequest(user_id=self.state.user_id, payload=payload)
            )
        except (
            KeyError,
            SpringApiError,
            RetrieverUnavailableError,
            httpx.HTTPError,
            ValueError,
        ):
            return ToolResult(
                tool_name=name,
                success=False,
                message=_TOOL_FAILURE_MESSAGE,
            )


def tool_receipt(result: ToolResult) -> ToolResult:
    """응답용 Tool 영수증을 만들되 회고 후보 data는 보존한다.

    ``reflection`` 결과의 ``data``는 Spring이 회고 단계 진행에 사용하는
    계약 필드이므로 비우지 않는다 (05 API 명세서 §3).
    """

    if result.tool_name is ToolName.REFLECTION:
        return result.model_copy()

    return result.model_copy(update={"data": None})


Handler = Callable[[HandlerContext], Awaitable[ChatResponse]]
