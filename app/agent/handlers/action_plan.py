"""ACTION_PLAN — Spring이 계산한 행동 제안의 이유를 설명한다 (05 §3 · FR-08-01).

제안의 수치나 판정을 만들지 않고 요청된 제안 정보만 대화체로 재구성한다.
"""

import json
from typing import Any

from app.agent.handlers.base import HandlerContext, tool_receipt
from app.ai.fallback import ACTION_PLAN_UNAVAILABLE_REPLY
from app.schemas.chat import ChatResponse
from app.schemas.tool import ToolName

NO_MATCHING_SUGGESTION_REPLY = (
    "해당하는 제안을 찾을 수 없어요. 제안 목록에서 다시 확인해 주세요."
)
ACTION_PLAN_INSTRUCTION = (
    "아래 제안 정보를 바탕으로 왜 이 제안을 하게 됐는지 한두 문장으로 "
    "설명하세요. 모든 문장은 \"~요\"로 끝나는 해요체로 씁니다. 반말로 "
    "끝내지 않습니다. 제공된 값에 없는 숫자나 이유를 새로 만들지 마세요."
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
    return ChatResponse(
        reply=await ctx.generate(instruction),
        tool_results=[receipt],
    )


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
