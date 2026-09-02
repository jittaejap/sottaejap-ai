"""소비 분석 Tool.

분석 알고리즘을 직접 수행하지 않으며 Spring의 분석 API 결과만 전달한다.
"""

from app.clients.spring_client import SpringClient
from app.schemas.tool import ToolName, ToolResult


class AnalysisTool:
    """Spring Rule Engine 분석 결과를 가져오는 래퍼."""

    def __init__(self, spring_client: SpringClient) -> None:
        self._spring_client = spring_client

    async def execute(self, user_id: str) -> ToolResult:
        data = await self._spring_client.get_behavior_analysis(user_id)
        return ToolResult(tool_name=ToolName.ANALYSIS, data=data)

