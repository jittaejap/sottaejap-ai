"""개인 소비 메모리 Tool.

저장소가 Spring 또는 pgVector로 바뀌어도 Agent가 영향받지 않도록 조회 경계만 제공한다.
"""

from typing import Any, Protocol

from app.schemas.tool import ToolName, ToolResult


class MemoryProvider(Protocol):
    """Spring 또는 pgVector 구현이 만족해야 할 메모리 조회 계약."""

    async def get_memory(self, user_id: str) -> dict[str, Any]: ...


class MemoryTool:
    """구체 저장소와 분리된 메모리 조회 인터페이스."""

    def __init__(self, provider: MemoryProvider) -> None:
        self._provider = provider

    async def execute(self, user_id: str) -> ToolResult:
        data = await self._provider.get_memory(user_id)
        return ToolResult(tool_name=ToolName.MEMORY, data=data)
