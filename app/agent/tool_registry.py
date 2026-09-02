"""Agent에 노출할 Tool 목록을 관리한다.

실제 Tool 선택 정책이나 실행 루프는 구현하지 않고 등록·조회 경계만 제공한다.
"""

from collections.abc import Awaitable, Callable

from app.schemas.tool import ToolName, ToolRequest, ToolResult

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

