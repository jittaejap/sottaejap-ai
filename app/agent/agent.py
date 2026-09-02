"""소때잡 Single Agent 진입점.

현재는 요청과 Task Context를 연결해 실행 가능한 기본 응답을 반환한다. Tool 선택,
LLM Tool Calling, 결과 조합은 후속 구현 대상이며 서비스 계산이나 DB 접근은 하지 않는다.
"""

from app.agent.state import AgentState
from app.agent.tool_registry import ToolRegistry
from app.schemas.chat import ChatRequest, ChatResponse


class SingleAgent:
    """한 요청에서 의도 파악부터 최종 설명까지 조정할 Agent 골격."""

    def __init__(self, tool_registry: ToolRegistry | None = None) -> None:
        self._tool_registry = tool_registry or ToolRegistry()

    async def run(self, request: ChatRequest) -> ChatResponse:
        """현재 요청을 처리해 공통 응답 구조로 반환한다."""

        state = AgentState.from_request(request)

        # TODO: LLM Tool Calling으로 의도를 파악하고 Registry의 Tool을 선택한다.
        # TODO: Tool 결과를 근거로 최종 자연어 응답을 생성한다.
        task_suffix = f" 현재 작업은 {state.task.value}입니다." if state.task else ""
        return ChatResponse(
            reply=(
                "요청을 정상적으로 받았습니다. "
                "현재는 초기 Agent 템플릿이며 Tool Calling은 다음 단계에서 연결됩니다."
                f"{task_suffix}"
            )
        )

