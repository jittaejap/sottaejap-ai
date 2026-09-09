"""회고 조회·저장 Tool.

정형화된 회고를 Spring에 전달하고 영속화 규칙이나 점수 계산은 수행하지 않는다.
"""

from app.clients.spring_client import SpringClient
from app.reflection.schemas import ReflectionExtraction
from app.schemas.tool import ToolName, ToolResult


class ReflectionTool:
    """Spring 회고 API의 얇은 래퍼."""

    def __init__(self, spring_client: SpringClient) -> None:
        self._spring_client = spring_client

    async def get(self, user_id: str) -> ToolResult:
        data = await self._spring_client.get_reflections(user_id)
        return ToolResult(tool_name=ToolName.REFLECTION, data=data)

    async def save(
        self, user_id: str, transaction_id: int, reflection: ReflectionExtraction
    ) -> ToolResult:
        body = {
            "transaction_id": transaction_id,
            "satisfaction": reflection.satisfaction.value,
            "purpose": reflection.purpose.value
            if reflection.purpose is not None
            else None,
            "companion": reflection.companion.value
            if reflection.companion is not None
            else None,
            "repeat_intention": reflection.repeat_intention,
        }
        data = await self._spring_client.save_reflection(user_id, body)
        return ToolResult(tool_name=ToolName.REFLECTION, data=data)
