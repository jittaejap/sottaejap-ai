"""CLUSTER_NAMING — Spring이 만든 소비 묶음에 이름을 붙인다 (05 §3 · FR-05-05).

묶음 계산이나 판정 없이 전달받은 묶음 정보만 사용해 12자 이내 이름 하나를 만든다.

실측으로 확인된 문제: `cluster_key`·`sample_merchants`가 둘 다 비어 있으면(malformed
state) LLM이 "이름만 답하라"는 지시를 무시하고 SYSTEM_PROMPT의 few-shot 예시("확인된
근거가 없어…")를 본뜬 문장을 낸다. `reply[:12]`가 그 문장을 단어 중간에서 그대로
잘라 "확인된 근거가 없어 지" 같은 의미 없는 조각이 나갔다(5회 중 5회 재현). LLM 장애가
아니라 입력 자체가 없는 경우라 `app/ai/fallback.py`의 `fallback_reply()` 템플릿을
그대로 재사용해 LLM 호출 자체를 건너뛴다 — ACTION_PLAN의 `NO_MATCHING_SUGGESTION_REPLY`
와 같은 이유로 `fallback` 플래그는 세우지 않는다(AI 장애가 아니라 정상적인 빈 입력 처리).

PR #63 리뷰에서 지적된 대로, 공백만 있는 값(`"   "`)은 문자열 타입 검사만으로는
안 걸러져서 위 사고가 재현될 수 있었다 — `cluster_key`는 trim하고, `sample_merchants`는
trim 후 빈 문자열을 제외한다.
"""

import json
from typing import Any

from app.agent.handlers.base import HandlerContext
from app.ai.fallback import CLUSTER_NAME_MAX_LENGTH, fallback_reply
from app.schemas.chat import ChatResponse
from app.schemas.common import TaskType

CLUSTER_NAME_INSTRUCTION = (
    "묶음 키는 카테고리|시간대|목적|동행인 순서입니다. 묶음 키와 가맹점 이름, "
    "소비 건수를 참고해서 이 소비 묶음에 어울리는 한국어 이름을 하나만 지어주세요. "
    "브랜드명이나 카테고리 위주로, 설명 없이 이름만 12자 이내로 답하세요."
)


async def handle(ctx: HandlerContext) -> ChatResponse:
    """전달받은 묶음 정보로 12자 이내 이름을 생성한다."""

    cluster_info = _cluster_info(ctx.state.structured_state)
    if not cluster_info["cluster_key"] and not cluster_info["sample_merchants"]:
        return ChatResponse(
            reply=fallback_reply(TaskType.CLUSTER_NAMING, ctx.state.structured_state),
            tool_results=[],
        )

    instruction = (
        f"{CLUSTER_NAME_INSTRUCTION}\n"
        f"묶음 정보: {json.dumps(cluster_info, ensure_ascii=False)}"
    )

    reply = (
        (await ctx.generate(instruction))
        .strip()
        .partition("\n")[0]
        .strip()
        .strip("\"'“”‘’「」")
        .strip()
    )

    return ChatResponse(
        reply=reply[:CLUSTER_NAME_MAX_LENGTH],
        tool_results=[],
    )


def _cluster_info(state: dict[str, Any]) -> dict[str, Any]:
    """느슨한 외부 상태에서 이름 생성에 필요한 값만 안전하게 꺼낸다."""

    cluster_key = state.get("cluster_key")
    if not isinstance(cluster_key, str):
        cluster_key = ""
    cluster_key = cluster_key.strip()

    sample_merchants = state.get("sample_merchants")
    if isinstance(sample_merchants, list):
        sample_merchants = [
            merchant
            for merchant in sample_merchants
            if isinstance(merchant, str) and merchant.strip()
        ]
    else:
        sample_merchants = []

    tx_count = state.get("tx_count")
    if not isinstance(tx_count, int) or isinstance(tx_count, bool):
        tx_count = 0

    return {
        "cluster_key": cluster_key,
        "sample_merchants": sample_merchants,
        "tx_count": tx_count,
    }
