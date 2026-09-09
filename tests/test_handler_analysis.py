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
    assert response.fallback is False
    instruction = fake_llm.calls[0][0]
    assert "배달" in instruction
    assert "집계에 없는 수치나" in instruction
    assert '"analysisYearMonth"' in instruction
    assert '"byVerdict"' in instruction
    assert '"byCategory"' in instruction
    assert '"pending"' not in instruction
    assert '"points"' not in instruction
    assert response.tool_results[0].data is None


def test_analysis_returns_no_retrospect_reply_when_no_valid_clusters(
    fake_llm: FakeLLM,
) -> None:
    """유효 묶음이 진짜 0개면(회고 자체가 없음) NO_RETROSPECT_REPLY다 (#50)."""

    registry = ToolRegistry()
    data = {
        "analysisYearMonth": "2026-08",
        "byVerdict": [
            {"verdict": "SUSTAIN", "clusterCount": 0, "monthlyTotalAmount": 0, "share": None},
            {"verdict": "ADJUST", "clusterCount": 0, "monthlyTotalAmount": 0, "share": None},
        ],
        "pending": {"clusterCount": 0, "monthlyTotalAmount": 0, "share": None},
        "byCategory": [],
    }
    _register(registry, data)
    context = _context(fake_llm, {}, registry)

    response = asyncio.run(analysis.handle(context))

    assert response.reply == analysis.NO_RETROSPECT_REPLY
    assert fake_llm.calls == []
    assert response.tool_results[0].data is None


def test_analysis_returns_month_activity_reply_when_clusters_exist_but_category_empty(
    fake_llm: FakeLLM,
) -> None:
    """유효 묶음은 있는데 이번 달 회고가 없어 byCategory만 빈 경우다 (#50 · E-73)."""

    registry = ToolRegistry()
    _register(registry, _analysis_data(by_category=[]))
    context = _context(fake_llm, {}, registry)

    response = asyncio.run(analysis.handle(context))

    assert response.reply == analysis.NO_MONTH_ACTIVITY_REPLY
    assert response.reply != analysis.NO_RETROSPECT_REPLY
    assert fake_llm.calls == []
    assert response.tool_results[0].data is None


def test_analysis_returns_fixed_reply_when_tool_fails(fake_llm: FakeLLM) -> None:
    context = _context(fake_llm, {})

    response = asyncio.run(analysis.handle(context))

    assert response.reply == analysis.ANALYSIS_UNAVAILABLE_REPLY
    assert fake_llm.calls == []
    assert response.tool_results[0].success is False
    assert response.tool_results[0].data is None


def test_analysis_returns_unavailable_reply_when_data_malformed(fake_llm: FakeLLM) -> None:
    """모양이 깨진 응답은 "대상 없음"이 아니라 장애로 취급한다 (#35와 같은 구분)."""

    registry = ToolRegistry()

    async def handler(request: ToolRequest) -> ToolResult:
        return ToolResult(tool_name=ToolName.ANALYSIS, data=["잘못된 모양"])

    registry.register(ToolName.ANALYSIS, handler)
    context = _context(fake_llm, {}, registry)

    response = asyncio.run(analysis.handle(context))

    assert response.reply == analysis.ANALYSIS_UNAVAILABLE_REPLY
    assert fake_llm.calls == []


def _register(registry: ToolRegistry, data: dict[str, Any]) -> None:
    async def handler(request: ToolRequest) -> ToolResult:
        return ToolResult(tool_name=ToolName.ANALYSIS, data=data)

    registry.register(ToolName.ANALYSIS, handler)


def test_analysis_rejects_unverified_number_without_fallback_flag(fake_llm: FakeLLM) -> None:
    """근거에 없는 숫자가 나오면 안내문으로 바꾸되 fallback은 세우지 않는다.

    fallback=true의 소비자는 클라이언트고 "AI 장애" 배너를 띄운다(05 §2) — 가드
    거절은 검증 실패이지 장애가 아니다(01 E-108 · #48 · #50 리뷰 · server #49).
    """

    registry = ToolRegistry()
    _register(registry, _analysis_data())
    context = _context(fake_llm, {}, registry)
    fake_llm.reply = "배달에 250000원이나 썼어요."  # 근거에 없는 금액

    response = asyncio.run(analysis.handle(context))

    assert response.reply == analysis.ANALYSIS_UNAVAILABLE_REPLY
    assert response.fallback is False


def test_analysis_allows_known_percent_from_share(fake_llm: FakeLLM) -> None:
    """`share=0.36`은 문장에서 `36%`로 나올 수 있다 — 근거로 인정한다."""

    registry = ToolRegistry()
    _register(registry, _analysis_data())
    context = _context(fake_llm, {}, registry)
    fake_llm.reply = "지켜도 좋은 소비가 예산의 36%를 차지했어요."

    response = asyncio.run(analysis.handle(context))

    assert response.reply == "지켜도 좋은 소비가 예산의 36%를 차지했어요."
    assert response.fallback is False
