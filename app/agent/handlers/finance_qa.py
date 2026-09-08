"""FINANCE_QA — 금융 지식 질문에 근거 기반으로 답한다 (05 §3 · FR-12 · E-47 · B7).

`state`는 거의 빈 객체다 — 질문은 `message`에 있다. 근거는 `ToolName.FINANCIAL_RAG`로만
가져오고, 검색 결과가 없으면(Tool 미등록 포함) **모른다고 답한다** (FR-12-02). 투자
상품 추천·확정적 수익 표현은 하지 않는다 (FR-12-03 · NFR-05).
"""

import json
from typing import Any

from app.agent.handlers.base import HandlerContext, tool_receipt
from app.rag.prompt import FINANCIAL_RAG_PROMPT
from app.schemas.chat import ChatResponse
from app.schemas.tool import ToolName

# 근거가 없을 때. 지어내지 말고 모른다고 끝내는 게 FR-12-02의 요구다.
NO_EVIDENCE_INSTRUCTION = (
    "참고할 금융 자료를 찾지 못했습니다. 아는 것처럼 답하지 말고, 해당 내용은 "
    "확인할 수 없다고 한 문장으로 솔직하게 안내하세요. 숫자나 조건을 지어내지 마세요."
)


async def handle(ctx: HandlerContext) -> ChatResponse:
    """검색된 금융 문서 근거 안에서만 답하고, 없으면 모른다고 답한다."""

    result = await ctx.call_tool(ToolName.FINANCIAL_RAG, {"query": ctx.state.message})
    evidence = _evidence(result.data)

    instruction = (
        f"{FINANCIAL_RAG_PROMPT}\n금융 자료: {json.dumps(evidence, ensure_ascii=False)}"
        if evidence
        else NO_EVIDENCE_INSTRUCTION
    )

    return ChatResponse(
        reply=await ctx.generate(instruction),
        tool_results=[tool_receipt(result)],
    )


def _evidence(data: Any) -> list[dict[str, Any]]:
    """검색 결과에서 본문과 출처만 남긴다 — 점수·내부 식별자는 문장에 필요 없다."""

    if not isinstance(data, list):
        return []

    evidence: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        chunk = item.get("chunk")
        if not isinstance(chunk, dict):
            continue
        content = chunk.get("content")
        if not isinstance(content, str) or not content.strip():
            continue
        evidence.append({"content": content, "source": chunk.get("source")})
    return evidence
