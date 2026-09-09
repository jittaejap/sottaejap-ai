"""CLUSTER_NAMING — Spring이 만든 소비 묶음에 이름을 붙인다 (05 §3 · FR-05-05).

묶음 계산이나 판정 없이 전달받은 묶음 정보만 사용해 12자 이내 이름 하나를 만든다.
"""

import json
from typing import Any

from app.agent.handlers.base import HandlerContext
from app.ai.fallback import CLUSTER_NAME_MAX_LENGTH
from app.schemas.chat import ChatResponse

CLUSTER_NAME_INSTRUCTION = (
    "묶음 키는 카테고리|시간대|목적|동행인 순서입니다. 묶음 키와 가맹점 이름, "
    "소비 건수를 참고해서 이 소비 묶음에 어울리는 한국어 이름을 하나만 지어주세요. "
    "브랜드명이나 카테고리 위주로, 설명 없이 이름만 12자 이내로 답하세요."
)


async def handle(ctx: HandlerContext) -> ChatResponse:
    """전달받은 묶음 정보로 12자 이내 이름을 생성한다."""

    cluster_info = _cluster_info(ctx.state.structured_state)
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

    sample_merchants = state.get("sample_merchants")
    if isinstance(sample_merchants, list):
        sample_merchants = [
            merchant
            for merchant in sample_merchants
            if isinstance(merchant, str)
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
