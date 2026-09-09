"""ANALYSIS Handler가 집계 데이터를 근거로만 답하는지 확인한다."""

import asyncio
from typing import Any

from app.agent.handlers import HANDLERS, analysis
from app.agent.handlers.base import HandlerContext
from app.agent.state import AgentState
from app.agent.tool_registry import ToolRegistry
from app.schemas.common import TaskType
from app.schemas.tool import ToolName, ToolRequest, ToolResult
from tests.conftest import FakeLLM


def _context(
    fake_llm: FakeLLM,
    state: dict[str, Any],
    registry: ToolRegistry | None = None,
) -> HandlerContext:
    return HandlerContext(
        state=AgentState(
            user_id="user-1",
            message="이번 달 배달 얼마나 썼어?",
            structured_state=state,
        ),
        llm=fake_llm,  # type: ignore[arg-type]
        tools=registry or ToolRegistry(),
    )


def _analysis_data(by_category: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "analysisYearMonth": "2026-08",
        "byVerdict": [
            {"verdict": "SUSTAIN", "clusterCount": 5, "monthlyTotalAmount": 430000, "share": 0.36},
            {"verdict": "ADJUST", "clusterCount": 3, "monthlyTotalAmount": 210000, "share": 0.18},
        ],
        "pending": {"clusterCount": 7, "monthlyTotalAmount": 180000, "share": 0.15},
        "byCategory": by_category
        if by_category is not None
        else [
            {
                "category": "배달",
                "dominantTimeSlot": "NIGHT",
                "avgAmount": 12000,
                "monthlyTotalAmount": 96000,
                "verdict": "ADJUST",
            }
        ],
        "points": [{"x": 1, "y": 2}],
    }


def test_analysis_is_registered() -> None:
    assert HANDLERS[TaskType.ANALYSIS] is analysis.handle


def test_analysis_answers_from_aggregate(fake_llm: FakeLLM) -> None:
    registry = ToolRegistry()

    async def handler(request: ToolRequest) -> ToolResult:
        assert request.payload == {}
        return ToolResult(tool_name=ToolName.ANALYSIS, data=_analysis_data())

    registry.register(ToolName.ANALYSIS, handler)
    context = _context(fake_llm, {"analysis_year_month": "2026-08"}, registry)

    response = asyncio.run(analysis.handle(context))

    assert response.reply == "LLM 응답"
    instruction = fake_llm.calls[0][0]
    assert "배달" in instruction
    assert "집계에 없는 수치나" in instruction
    assert '"analysisYearMonth"' in instruction
    assert '"byVerdict"' in instruction
    assert '"byCategory"' in instruction
    assert '"pending"' not in instruction
    assert '"points"' not in instruction
    assert response.tool_results[0].data is None


def test_analysis_returns_fixed_reply_when_no_valid_clusters(fake_llm: FakeLLM) -> None:
    registry = ToolRegistry()

    async def handler(request: ToolRequest) -> ToolResult:
        return ToolResult(tool_name=ToolName.ANALYSIS, data=_analysis_data(by_category=[]))

    registry.register(ToolName.ANALYSIS, handler)
    context = _context(fake_llm, {}, registry)

    response = asyncio.run(analysis.handle(context))

    assert response.reply == analysis.NO_ANALYSIS_DATA_REPLY
    assert fake_llm.calls == []
    assert response.tool_results[0].data is None


def test_analysis_returns_fixed_reply_when_tool_fails(fake_llm: FakeLLM) -> None:
    context = _context(fake_llm, {})

    response = asyncio.run(analysis.handle(context))

    assert response.reply == analysis.ANALYSIS_UNAVAILABLE_REPLY
    assert fake_llm.calls == []
    assert response.tool_results[0].success is False
    assert response.tool_results[0].data is None


def test_analysis_ignores_malformed_data(fake_llm: FakeLLM) -> None:
    registry = ToolRegistry()

    async def handler(request: ToolRequest) -> ToolResult:
        return ToolResult(tool_name=ToolName.ANALYSIS, data=["잘못된 모양"])

    registry.register(ToolName.ANALYSIS, handler)
    context = _context(fake_llm, {}, registry)

    response = asyncio.run(analysis.handle(context))

    assert response.reply == analysis.NO_ANALYSIS_DATA_REPLY
    assert fake_llm.calls == []
