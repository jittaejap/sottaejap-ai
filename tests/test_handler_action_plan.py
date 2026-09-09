"""ACTION_PLAN Handler가 요청된 제안만 근거로 설명하는지 확인한다."""

import asyncio
from typing import Any

from app.agent.handlers import HANDLERS, action_plan
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
            message="왜 이 제안을 했나요?",
            structured_state=state,
        ),
        llm=fake_llm,  # type: ignore[arg-type]
        tools=registry or ToolRegistry(),
    )


def _suggestion(suggestion_id: int, behavior_name: str) -> dict[str, Any]:
    return {
        "id": suggestion_id,
        "behaviorName": behavior_name,
        "monthlyTotalAmount": 96000,
        "quadrant": "PRIORITY",
        "expectedSaving": 96000,
        "reason": (
            f"{behavior_name}은(는) 이번 달 96,000원으로 부담이 컸고 "
            "만족도도 낮았어요. 횟수를 줄여볼까요?"
        ),
    }


def test_action_plan_is_registered() -> None:
    assert HANDLERS[TaskType.ACTION_PLAN] is action_plan.handle


def test_action_plan_explains_matching_suggestion(fake_llm: FakeLLM) -> None:
    registry = ToolRegistry()

    async def handler(request: ToolRequest) -> ToolResult:
        assert request.payload == {}
        return ToolResult(
            tool_name=ToolName.ACTION_PLAN,
            data={
                "suggestions": [
                    _suggestion(7, "심야 배달"),
                    _suggestion(8, "무관한 제안"),
                ]
            },
        )

    registry.register(ToolName.ACTION_PLAN, handler)
    context = _context(fake_llm, {"suggestion_ids": [7]}, registry)

    response = asyncio.run(action_plan.handle(context))

    assert response.reply == "LLM 응답"
    instruction = fake_llm.calls[0][0]
    assert "심야 배달" in instruction
    assert "무관한 제안" not in instruction
    assert "없는 숫자나 이유를 새로 만들지 마세요" in instruction
    assert response.tool_results[0].data is None


def test_action_plan_returns_fixed_reply_when_no_suggestion_ids(
    fake_llm: FakeLLM,
) -> None:
    response = asyncio.run(action_plan.handle(_context(fake_llm, {})))

    assert response.reply == action_plan.NO_MATCHING_SUGGESTION_REPLY
    assert response.tool_results == []
    assert fake_llm.calls == []


def test_action_plan_ignores_non_integer_suggestion_ids(
    fake_llm: FakeLLM,
) -> None:
    context = _context(fake_llm, {"suggestion_ids": ["7", True, None]})

    response = asyncio.run(action_plan.handle(context))

    assert response.reply == action_plan.NO_MATCHING_SUGGESTION_REPLY
    assert response.tool_results == []
    assert fake_llm.calls == []


def test_action_plan_returns_fixed_reply_when_no_id_matches(
    fake_llm: FakeLLM,
) -> None:
    registry = ToolRegistry()

    async def handler(request: ToolRequest) -> ToolResult:
        return ToolResult(
            tool_name=ToolName.ACTION_PLAN,
            data={"suggestions": [_suggestion(999, "무관한 제안")]},
        )

    registry.register(ToolName.ACTION_PLAN, handler)
    context = _context(fake_llm, {"suggestion_ids": [7]}, registry)

    response = asyncio.run(action_plan.handle(context))

    assert response.reply == action_plan.NO_MATCHING_SUGGESTION_REPLY
    assert fake_llm.calls == []
    assert response.tool_results[0].data is None


def test_action_plan_returns_fixed_reply_when_tool_fails(
    fake_llm: FakeLLM,
) -> None:
    context = _context(fake_llm, {"suggestion_ids": [7]})

    response = asyncio.run(action_plan.handle(context))

    assert response.reply == action_plan.NO_MATCHING_SUGGESTION_REPLY
    assert fake_llm.calls == []
    assert response.tool_results[0].success is False
    assert response.tool_results[0].data is None


def test_action_plan_ignores_malformed_suggestions_data(
    fake_llm: FakeLLM,
) -> None:
    registry = ToolRegistry()

    async def handler(request: ToolRequest) -> ToolResult:
        return ToolResult(
            tool_name=ToolName.ACTION_PLAN,
            data={
                "suggestions": [
                    "문자열",
                    {"id": "숫자아님"},
                    {"no_id_field": True},
                ]
            },
        )

    registry.register(ToolName.ACTION_PLAN, handler)
    context = _context(fake_llm, {"suggestion_ids": [7]}, registry)

    response = asyncio.run(action_plan.handle(context))

    assert response.reply == action_plan.NO_MATCHING_SUGGESTION_REPLY
    assert fake_llm.calls == []
