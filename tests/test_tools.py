"""Tool이 계산 없이 Client 결과를 전달하는지 확인한다."""

import asyncio
from typing import Any

from app.schemas.tool import ToolName
from app.tools.analysis_tool import AnalysisTool


class FakeSpringClient:
    async def get_behavior_analysis(self, user_id: str) -> dict[str, Any]:
        return {"user_id": user_id, "classification": "SPRING_RESULT"}


def test_analysis_tool_forwards_spring_result() -> None:
    tool = AnalysisTool(FakeSpringClient())  # type: ignore[arg-type]

    result = asyncio.run(tool.execute("user-1"))

    assert result.tool_name == ToolName.ANALYSIS
    assert result.data == {"user_id": "user-1", "classification": "SPRING_RESULT"}

