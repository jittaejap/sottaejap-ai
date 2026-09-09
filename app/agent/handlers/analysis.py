"""ANALYSIS — Spring이 계산한 소비 집계를 근거로 자유 질문에 답한다 (05 §3 · FR-11-01·02).

집계 수치나 판정을 만들지 않고 Spring이 이미 계산한 값 안에서만 설명한다.
'나만의 특징' 한 문장(ANALYSIS_NARRATE, FR-11-03)은 별도 Task다.

숫자 검증은 `app/agent/handlers/number_guard.py`를 ANALYSIS_NARRATE와 공유한다
(#43 · #48) — 프롬프트 지시만으로는 근거 밖 수치를 100% 못 막는다(E-79).
"""

import json
from typing import Any

from app.agent.handlers.base import HandlerContext, tool_receipt
from app.agent.handlers.number_guard import (
    has_unverified_number,
    known_numbers,
    known_percentages,
)
from app.ai.fallback import ANALYSIS_UNAVAILABLE_REPLY
from app.schemas.chat import ChatResponse
from app.schemas.tool import ToolName

# byCategory가 비는 이유는 둘이고, server HighlightTemplate은 이 둘을 다른 문장으로
# 나눈다(server PR #53 · E-89) — 여기서도 같은 뜻으로 나눈다 (#50).
NO_RETROSPECT_REPLY = "아직 돌아본 소비가 없어요. 몇 건만 회고하면 분석을 보여드릴 수 있어요."
NO_MONTH_ACTIVITY_REPLY = (
    "이번 달 거래는 아직 회고한 게 없어요. 이번 달 거래를 몇 건 회고하면 분석을 보여드릴 수 있어요."
)
ANALYSIS_INSTRUCTION = (
    "아래 소비 분석 집계를 바탕으로 사용자 질문에 답하세요. 집계에 없는 수치나 "
    "판정을 새로 만들지 마세요."
)
# `pending`은 뺀다 — 판정(verdict)이 없는 금액이라, 있으면 모델이 판정된 금액과
# 섞어 말할 여지가 생긴다 (ANALYSIS_NARRATE의 state 제한과 같은 이유, 05 §3).
# 유효 묶음 판정(_effective_cluster_count)에는 원본 Tool 데이터에서 따로 읽는다.
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
    if not _has_category_data(analysis):
        reply = (
            NO_RETROSPECT_REPLY
            if _effective_cluster_count(result.data) == 0
            else NO_MONTH_ACTIVITY_REPLY
        )
        return ChatResponse(reply=reply, tool_results=[receipt])

    instruction = (
        f"{ANALYSIS_INSTRUCTION}\n"
        f"소비 분석 집계: {json.dumps(analysis, ensure_ascii=False)}"
    )
    sentence = await ctx.generate(instruction)

    groups = [analysis.get("byVerdict"), analysis.get("byCategory")]
    if has_unverified_number(
        sentence,
        known_numbers(groups, year_month=analysis.get("analysisYearMonth")),
        known_percentages=known_percentages(groups),
    ):
        # fallback=False다 — ANALYSIS_NARRATE와 달리 이 fallback 소비자는
        # 클라이언트고, true는 "AI 장애" 템플릿 배너(S11)를 띄운다(05 §2).
        # 가드 거절은 검증 실패이지 장애가 아니다(01 E-108 · server #49가
        # 이미 이 혼동으로 비용을 낸 사례).
        return ChatResponse(
            reply=ANALYSIS_UNAVAILABLE_REPLY,
            tool_results=[receipt],
        )

    return ChatResponse(reply=sentence, tool_results=[receipt])


def _prompt_analysis(data: dict[str, Any]) -> dict[str, Any]:
    """집계 dict에서 문장화에 필요한 필드만 남긴다 (dict 여부는 handle이 먼저 확인)."""

    return {field: data[field] for field in _PROMPT_FIELDS if field in data}


def _has_category_data(analysis: dict[str, Any]) -> bool:
    """`byCategory`가 채워져 있는지만 본다 — 유효 묶음 유무와는 다른 질문이다.

    `byVerdict`는 묶음이 없어도 항상 SUSTAIN·ADJUST 2행을 0으로 채워 내려오므로
    (05 §3), 데이터 유무 판단 기준으로 쓸 수 없다. `byCategory`가 비는 건 유효
    묶음이 0개이거나(진짜 데이터 없음), 묶음은 있는데 이번 달 회고가 없는 경우
    (E-73) 둘 다다 — 어느 쪽인지는 `_effective_cluster_count`로 따로 가른다.
    """

    by_category = analysis.get("byCategory")
    return isinstance(by_category, list) and len(by_category) > 0


def _effective_cluster_count(data: dict[str, Any]) -> int:
    """유효 묶음 수 = `byVerdict`의 `clusterCount` 합 + `pending`의 `clusterCount`.

    server `HighlightTemplate.effectiveClusterCount`와 같은 식이다(05 §3).
    `pending`은 프롬프트에는 안 싣지만(`_PROMPT_FIELDS`), 유효 묶음이 하나라도
    있는지 판단하는 데는 써도 된다 — 모델에게 보여주는 것과 우리가 분기
    판단에 쓰는 것은 다른 문제다.
    """

    total = 0
    by_verdict = data.get("byVerdict")
    if isinstance(by_verdict, list):
        for item in by_verdict:
            if not isinstance(item, dict):
                continue
            count = item.get("clusterCount")
            if isinstance(count, int) and not isinstance(count, bool):
                total += count

    pending = data.get("pending")
    if isinstance(pending, dict):
        count = pending.get("clusterCount")
        if isinstance(count, int) and not isinstance(count, bool):
            total += count

    return total
