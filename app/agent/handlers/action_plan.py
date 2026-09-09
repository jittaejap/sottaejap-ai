"""ACTION_PLAN — Spring이 계산한 행동 제안의 이유를 설명한다 (05 §3 · FR-08-01).

제안의 수치나 판정을 만들지 않고 요청된 제안 정보만 대화체로 재구성한다.

숫자 검증은 `app/agent/handlers/number_guard.py`를 쓴다 — `ANALYSIS`·`ANALYSIS_NARRATE`
(#43·#48)와 공유한다. "제공된 값에 없는 숫자를 새로 만들지 마세요"라는 프롬프트 지시만으로는
막히지 않는다는 게 실측으로 확인됐다 — "이거 지키면 몇 % 아껴요?", "1년으로 치면요?" 같은
후속 질문에서 LLM이 직접 비율·연 환산을 계산해 답했다(예: 78,000원을 "전체 지출의 약
30%"라고 자체 계산, 63,000원을 "12개월 곱하면 756,000원"이라고 자체 계산). 계산은 Spring
소유라는 원칙(AI_DESIGN)을 어기는 것이라 ANALYSIS_NARRATE와 같은 방식으로 막는다.
"""

import json
from typing import Any

from app.agent.handlers.base import HandlerContext, tool_receipt
from app.agent.handlers.number_guard import (
    has_unverified_number,
    known_numbers,
    known_percentages,
)
from app.agent.prompt import HAEYO_RULE
from app.ai.fallback import ACTION_PLAN_UNAVAILABLE_REPLY, fallback_reply
from app.schemas.chat import ChatResponse
from app.schemas.common import TaskType
from app.schemas.tool import ToolName

NO_MATCHING_SUGGESTION_REPLY = (
    "해당하는 제안을 찾을 수 없어요. 제안 목록에서 다시 확인해 주세요."
)
ACTION_PLAN_INSTRUCTION = (
    "아래 제안 정보를 바탕으로 왜 이 제안을 하게 됐는지 한두 문장으로 "
    f"설명하세요. {HAEYO_RULE} 제공된 값에 없는 숫자나 이유를 새로 만들지 마세요."
)
_PROMPT_FIELDS = (
    "behaviorName",
    "monthlyTotalAmount",
    "avgAmount",
    "txCount",
    "adjustCount",
    "expectedSaving",
    "reason",
)


async def handle(ctx: HandlerContext) -> ChatResponse:
    """요청된 제안만 선별해 이유를 설명하고 대상이 없으면 바로 안내한다."""

    suggestion_ids = _suggestion_ids(ctx.state.structured_state)
    if not suggestion_ids:
        return ChatResponse(
            reply=NO_MATCHING_SUGGESTION_REPLY,
            tool_results=[],
        )

    result = await ctx.call_tool(ToolName.ACTION_PLAN, {})
    receipt = tool_receipt(result)
    if not result.success:
        return ChatResponse(
            reply=ACTION_PLAN_UNAVAILABLE_REPLY,
            tool_results=[receipt],
        )

    matching_suggestions = [
        _prompt_suggestion(suggestion)
        for suggestion in _suggestions(result.data)
        if _matches_id(suggestion.get("id"), suggestion_ids)
    ]
    if not matching_suggestions:
        return ChatResponse(
            reply=NO_MATCHING_SUGGESTION_REPLY,
            tool_results=[receipt],
        )

    instruction = (
        f"{ACTION_PLAN_INSTRUCTION}\n"
        f"제안 정보: {json.dumps(matching_suggestions, ensure_ascii=False)}"
    )
    sentence = await ctx.generate(instruction)

    groups = [matching_suggestions]
    if has_unverified_number(
        sentence,
        known_numbers(groups),
        known_percentages=known_percentages(groups),
    ):
        return ChatResponse(
            reply=fallback_reply(TaskType.ACTION_PLAN, ctx.state.structured_state),
            tool_results=[receipt],
            fallback=True,
        )

    return ChatResponse(reply=sentence, tool_results=[receipt])


def _suggestion_ids(state: dict[str, Any]) -> set[int]:
    """느슨한 state에서 유효한 정수 제안 ID만 남긴다."""

    suggestion_ids = state.get("suggestion_ids")
    if not isinstance(suggestion_ids, list):
        return set()
    return {
        suggestion_id
        for suggestion_id in suggestion_ids
        if isinstance(suggestion_id, int) and not isinstance(suggestion_id, bool)
    }


def _suggestions(data: Any) -> list[dict[str, Any]]:
    """Tool 데이터에서 dict 형태의 제안 항목만 안전하게 꺼낸다."""

    if not isinstance(data, dict):
        return []
    suggestions = data.get("suggestions")
    if not isinstance(suggestions, list):
        return []
    return [suggestion for suggestion in suggestions if isinstance(suggestion, dict)]


def _matches_id(value: Any, suggestion_ids: set[int]) -> bool:
    """bool을 정수 ID로 오인하지 않고 요청된 제안인지 확인한다."""

    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and value in suggestion_ids
    )


def _prompt_suggestion(suggestion: dict[str, Any]) -> dict[str, Any]:
    """제안 설명에 필요한 사용자용 필드만 프롬프트에 남긴다."""

    return {
        field: suggestion[field]
        for field in _PROMPT_FIELDS
        if field in suggestion
    }
