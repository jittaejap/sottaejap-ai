"""ANALYSIS — Spring이 계산한 소비 집계를 근거로 자유 질문에 답한다 (05 §3 · FR-11-01·02).

집계 수치나 판정을 만들지 않고 Spring이 이미 계산한 값 안에서만 설명한다.
'나만의 특징' 한 문장(ANALYSIS_NARRATE, FR-11-03)은 별도 Task다.
"""

import json
from typing import Any

from app.agent.handlers.base import HandlerContext, tool_receipt
from app.ai.fallback import ANALYSIS_UNAVAILABLE_REPLY
from app.schemas.chat import ChatResponse
from app.schemas.tool import ToolName

NO_ANALYSIS_DATA_REPLY = (
    "이번 달에 돌아본 소비가 아직 없어요. 이번 달 거래를 몇 건 회고하면 분석을 보여드릴 수 있어요."
)
ANALYSIS_INSTRUCTION = (
    "아래 소비 분석 집계를 바탕으로 사용자 질문에 답하세요. 집계에 없는 수치나 "
    "판정을 새로 만들지 마세요."
)
# `pending`은 뺀다 — 판정(verdict)이 없는 금액이라, 있으면 모델이 판정된 금액과
# 섞어 말할 여지가 생긴다 (ANALYSIS_NARRATE의 state 제한과 같은 이유, 05 §3).
_PROMPT_FIELDS = ("analysisYearMonth", "byVerdict", "byCategory")


async def handle(ctx: HandlerContext) -> ChatResponse:
    """집계 데이터를 조회해 근거로 답하고, 없으면 바로 안내한다."""

    result = await ctx.call_tool(ToolName.ANALYSIS, {})
    receipt = tool_receipt(result)
    if not result.success or not isinstance(result.data, dict):
        # Tool 실패와 응답 모양이 깨진 경우를 같은 장애로 취급한다 — 둘 다
        # "대상 없음"이 아니라 "지금 답할 수 없음"이다 (#35와 같은 구분).
        return ChatResponse(
            reply=ANALYSIS_UNAVAILABLE_REPLY,
            tool_results=[receipt],
        )

    analysis = _prompt_analysis(result.data)
    if not _has_valid_data(analysis):
        return ChatResponse(
            reply=NO_ANALYSIS_DATA_REPLY,
            tool_results=[receipt],
        )

    instruction = (
        f"{ANALYSIS_INSTRUCTION}\n"
        f"소비 분석 집계: {json.dumps(analysis, ensure_ascii=False)}"
    )
    return ChatResponse(
        reply=await ctx.generate(instruction),
        tool_results=[receipt],
    )


def _prompt_analysis(data: dict[str, Any]) -> dict[str, Any]:
    """집계 dict에서 문장화에 필요한 필드만 남긴다 (dict 여부는 handle이 먼저 확인)."""

    return {field: data[field] for field in _PROMPT_FIELDS if field in data}


def _has_valid_data(analysis: dict[str, Any]) -> bool:
    """유효 묶음이 있는지 확인한다 — 없으면 LLM을 부르지 않는다 (E-91과 같은 원칙).

    `byVerdict`는 묶음이 없어도 항상 SUSTAIN·ADJUST 2행을 0으로 채워 내려오므로
    (05 §3), 데이터 유무 판단 기준으로 쓸 수 없다. 실제로 묶음이 있을 때만
    채워지는 `byCategory`로 판단한다.
    """

    by_category = analysis.get("byCategory")
    return isinstance(by_category, list) and len(by_category) > 0
