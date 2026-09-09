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

# 동일 질문을 반복해도 답변 표현이 크게 흔들리던 문제를 줄이려고 이 Task만 낮은
# 값을 쓴다 — 다른 Task의 응답 다양성은 그대로 둔다. 안전 지시(예시 수치 오용·
# 근거 없음 부연 설명) 위반 자체에는 로컬 테스트에서 효과가 없었다(오히려 더
# 일관되게 재현됐다) — docs/DEVELOPMENT.md "알려진 한계" 참고.
_FINANCE_QA_TEMPERATURE = 0.2

# 근거가 없을 때. 지어내지 말고 모른다고 끝내는 게 FR-12-02의 요구다.
# 투자 상품 원금 손실 위험 문서를 일부러 안 실었기 때문에(02 FR-12), 투자 질문은
# 구조적으로 이 경로로만 온다 — 투자 권유 금지(FR-12-03·NFR-05)를 여기에도 넣는다.
# "사전지식이라도 근거 없으면 언급하지 마세요" 정도의 소프트한 금지는 실제 테스트에서
# 통하지 않았다 — 모델이 실존하는 외부 기관명·통계를 그대로 답에 넣은 사례가 5/5로
# 재현됐다. "왜 안 되는지"를 설명하는 대신, 근거 없을 때 낼 수 있는 답변 형식 자체를
# 좁혀서 부연 설명을 낼 여지를 없앤다.
NO_EVIDENCE_INSTRUCTION = (
    "참고할 금융 자료를 찾지 못했습니다. 확인할 수 없다는 문장 하나로만 솔직하게 "
    "답하고, 배경 설명·수치·기관명·'~에 따르면' 같은 부연 설명은 절대 덧붙이지 "
    "마세요. 당신이 사전에 알고 있는 내용이라도 마찬가지입니다. "
    "개인화된 투자 권유나 확정적인 수익 표현도 하지 마세요."
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
