"""행동 제안 Tool.

Spring이 판정·계산한 행동 조정 결과를 조회하며 절감액을 직접 계산하지 않는다.
"""

from app.clients.spring_client import SpringClient
from app.schemas.tool import ToolName, ToolResult


class ActionPlanTool:
    """Spring 행동 제안 API의 얇은 래퍼."""

    def __init__(self, spring_client: SpringClient) -> None:
        self._spring_client = spring_client

    async def execute(self, user_id: str) -> ToolResult:
        data = await self._spring_client.get_action_plan(user_id)
        return ToolResult(tool_name=ToolName.ACTION_PLAN, data=data)

