"""Agent에 노출할 Tool 목록을 관리한다.

실제 Tool 선택 정책이나 실행 루프는 구현하지 않고 등록·조회 경계와 기본 배선만 제공한다.
"""

from collections.abc import Awaitable, Callable

from app.clients.spring_client import SpringClient
from app.schemas.tool import ToolName, ToolRequest, ToolResult
from app.tools.action_plan_tool import ActionPlanTool
from app.tools.analysis_tool import AnalysisTool
from app.tools.memory_tool import MemoryTool
from app.tools.reflection_tool import ReflectionTool
from app.tools.transaction_tool import TransactionTool

ToolHandler = Callable[[ToolRequest], Awaitable[ToolResult]]


class ToolRegistry:
    """Tool 이름과 비동기 실행 함수를 연결하는 단순 Registry."""

    def __init__(self) -> None:
        self._handlers: dict[ToolName, ToolHandler] = {}

    def register(self, name: ToolName, handler: ToolHandler) -> None:
        """Tool 실행 함수를 등록한다."""

        self._handlers[name] = handler

    def get(self, name: ToolName) -> ToolHandler:
        """등록된 Tool을 반환한다."""

        try:
            return self._handlers[name]
        except KeyError as exc:
            raise KeyError(f"등록되지 않은 Tool입니다: {name}") from exc

    def names(self) -> list[ToolName]:
        """Agent에 제공할 Tool 이름을 반환한다."""

        return list(self._handlers)


def build_default_registry(spring_client: SpringClient) -> ToolRegistry:
    """Spring에서 데이터를 pull하는 Tool 5종을 등록한 Registry를 만든다 (05 §3).

    `FINANCIAL_RAG`는 DB 풀이 있어야 만들 수 있어 여기서 등록하지 않는다.
    `app/main.py` lifespan이 `DATABASE_URL`이 있을 때만 덧붙인다.

    회고는 조회만 등록한다. 저장 본문은 `transaction_id`를 포함한 5개인데
    (05 §3 v2.2 · E-66) `ReflectionExtraction`에 그 필드가 없어, 지금 배선하면
    문서와 어긋난 계약이 코드로 굳는다. Issue #10에서 먼저 맞춘다.
    """

    transaction_tool = TransactionTool(spring_client)
    reflection_tool = ReflectionTool(spring_client)
    analysis_tool = AnalysisTool(spring_client)
    action_plan_tool = ActionPlanTool(spring_client)
    memory_tool = MemoryTool(spring_client)

    registry = ToolRegistry()
    registry.register(
        ToolName.TRANSACTION,
        lambda request: transaction_tool.execute(
            _user_id(request), request.payload or None
        ),
    )
    registry.register(
        ToolName.REFLECTION,
        lambda request: reflection_tool.get(_user_id(request)),
    )
    registry.register(
        ToolName.ANALYSIS,
        lambda request: analysis_tool.execute(_user_id(request)),
    )
    registry.register(
        ToolName.ACTION_PLAN,
        lambda request: action_plan_tool.execute(_user_id(request)),
    )
    registry.register(
        ToolName.MEMORY,
        lambda request: memory_tool.execute(_user_id(request)),
    )
    return registry


def _user_id(request: ToolRequest) -> str:
    """사용자를 특정할 수 없으면 Spring을 부르지 않는다.

    `ChatRequest.user_id`는 선택 필드다. 비어 있을 때 `ValueError`를 올리면
    `HandlerContext.call_tool`이 잡아 `success=False`로 바꾼다 (handlers/base.py).
    """

    if not request.user_id:
        raise ValueError("user_id 없이 Spring Tool을 부를 수 없습니다.")
    return request.user_id
