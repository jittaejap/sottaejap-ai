"""소때잡 Single Agent 진입점.

요청과 Task Context를 연결해 LLM 응답을 만들고, LLM이 없거나 실패하면 템플릿으로
대체해 `fallback=True`로 응답한다 (FR-04-15). Tool 선택, Tool Calling, 결과 조합은
후속 구현 대상이며 서비스 계산이나 DB 접근은 하지 않는다.
"""

import json

from app.agent.prompt import SYSTEM_PROMPT
from app.agent.state import AgentState
from app.agent.tool_registry import ToolRegistry
from app.ai.fallback import fallback_reply
from app.core.llm import LLMClient, LLMNotConfiguredError, LLMUnavailableError
from app.schemas.chat import ChatRequest, ChatResponse


class SingleAgent:
    """한 요청에서 의도 파악부터 최종 설명까지 조정할 Agent 골격."""

    def __init__(
        self,
        tool_registry: ToolRegistry | None = None,
        llm_client: LLMClient | None = None,
    ) -> None:
        self._tool_registry = tool_registry or ToolRegistry()
        self._llm_client = llm_client or LLMClient()

    async def run(self, request: ChatRequest) -> ChatResponse:
        """현재 요청을 처리해 공통 응답 구조로 반환한다."""

        state = AgentState.from_request(request)

        # TODO: LLM Tool Calling으로 의도를 파악하고 Registry의 Tool을 선택한다.
        # TODO: Tool 결과를 근거로 최종 자연어 응답을 생성한다.
        try:
            reply = await self._llm_client.generate(_system_prompt(state), state.message)
        except (LLMNotConfiguredError, LLMUnavailableError):
            return ChatResponse(
                reply=fallback_reply(state.task, state.structured_state),
                fallback=True,
            )
        return ChatResponse(reply=reply)


def _system_prompt(state: AgentState) -> str:
    """시스템 프롬프트에 현재 작업과 구조화 상태를 덧붙인다."""

    if state.task is None:
        return SYSTEM_PROMPT
    context = json.dumps(state.structured_state, ensure_ascii=False)
    return f"{SYSTEM_PROMPT}\n현재 작업: {state.task.value}\n현재 상태(JSON): {context}\n"
