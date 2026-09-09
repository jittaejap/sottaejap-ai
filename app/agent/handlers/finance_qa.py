"""FINANCE_QA — 금융 지식 질문에 근거 기반으로 답한다 (05 §3 · FR-12 · E-47 · B7).

`state`는 거의 빈 객체다 — 질문은 `message`에 있다. 근거는 `ToolName.FINANCIAL_RAG`로만
가져오고, 검색 결과가 없으면(Tool 미등록 포함) **모른다고 답한다** (FR-12-02). 투자
상품 추천·확정적 수익 표현은 하지 않는다 (FR-12-03 · NFR-05).
"""

import json
from typing import Any

from app.agent.handlers.base import HandlerContext, tool_receipt
from app.agent.prompt import HAEYO_RULE
from app.ai.fallback import FINANCE_QA_NO_EVIDENCE_REPLY
from app.rag.prompt import FINANCIAL_RAG_PROMPT
from app.schemas.chat import ChatResponse
from app.schemas.tool import ToolName

# 동일 질문을 반복해도 답변 표현이 크게 흔들리던 문제를 줄이려고 이 Task만 낮은
# 값을 쓴다 — 다른 Task의 응답 다양성은 그대로 둔다.
_FINANCE_QA_TEMPERATURE = 0.2


async def handle(ctx: HandlerContext) -> ChatResponse:
    """검색된 금융 문서 근거 안에서만 답하고, 없으면 모른다고 답한다."""

    result = await ctx.call_tool(ToolName.FINANCIAL_RAG, {"query": ctx.state.message})
    evidence = _evidence(result.data)

    if not evidence:
        # LLM을 안 부르고 고정 문장으로 바로 답한다(#74). "확인할 수 없다는
        # 문장 하나로만" 요구를 지시문으로 넣어도, 모델이 공통 SYSTEM_PROMPT의
        # few-shot 예시("...소비 흐름을 설명하기 어려워요" — 원래 ANALYSIS_NARRATE용)
        # 문장 틀을 그대로 본떠 답하는 걸 운영 실측 5/5로 못 막았다
        # (docs/DEVELOPMENT.md §13 CLUSTER_NAMING과 같은 패턴). LLM을 아예 안 부르면
        # 투자 권유 금지(FR-12-03·NFR-05) 위반 가능성도 이 경로에서 사라진다.
        # fallback=False다 — 장애가 아니라 정상적인 근거없음 처리다(#65 E-108과
        # 같은 구분).
        return ChatResponse(
            reply=FINANCE_QA_NO_EVIDENCE_REPLY,
            tool_results=[tool_receipt(result)],
        )

    # HAEYO_RULE을 근거 JSON 앞뒤에 둔다 — 긴 금융 자료(교과서 원문)의 해라체
    # 문체가 규칙 한 줄보다 강하게 작용해 반말이 샜다(#69 실측).
    instruction = (
        f"{FINANCIAL_RAG_PROMPT}\n{HAEYO_RULE}\n"
        f"금융 자료: {json.dumps(evidence, ensure_ascii=False)}\n{HAEYO_RULE}"
    )

    return ChatResponse(
        reply=await ctx.generate(instruction, temperature=_FINANCE_QA_TEMPERATURE),
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
