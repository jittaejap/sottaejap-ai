"""거래 조회 Tool.

거래가 필요한 Agent 요청을 SpringClient로 전달하며 직접 DB를 조회하지 않는다.
"""

from typing import Any

from app.clients.spring_client import SpringClient
from app.schemas.tool import ToolName, ToolResult


class TransactionTool:
    """Spring 거래 조회 API의 얇은 래퍼."""

    def __init__(self, spring_client: SpringClient) -> None:
        self._spring_client = spring_client

    async def execute(
        self, user_id: str, query: dict[str, Any] | None = None
    ) -> ToolResult:
        data = await self._spring_client.get_transactions(user_id, query)
        return ToolResult(tool_name=ToolName.TRANSACTION, data=data)

