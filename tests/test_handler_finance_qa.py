"""FINANCE_QA Handler가 근거 유무에 따라 올바르게 답하는지 확인한다."""

import asyncio

from app.agent.handlers import HANDLERS, finance_qa
from app.agent.handlers.base import HandlerContext
from app.agent.prompt import HAEYO_RULE
from app.agent.state import AgentState
from app.agent.tool_registry import ToolRegistry
from app.ai.fallback import FINANCE_QA_NO_EVIDENCE_REPLY
from app.rag.retriever import RetrieverUnavailableError
from app.schemas.common import TaskType
from app.schemas.tool import ToolName, ToolRequest, ToolResult
from tests.conftest import FakeLLM


def _evidence_result() -> ToolResult:
    return ToolResult(
        tool_name=ToolName.FINANCIAL_RAG,
        data=[
            {
                "chunk": {
                    "chunk_id": "guide-0",
                    "content": "예금자보호제도는 1인당 5천만원까지 보호합니다.",
                    "source": "예금보험공사",
                    "metadata": {},
                },
                "score": 0.9,
            }
        ],
    )


def test_finance_qa_is_registered() -> None:
    assert HANDLERS[TaskType.FINANCE_QA] is finance_qa.handle


def test_finance_qa_answers_from_evidence_when_available(fake_llm: FakeLLM) -> None:
    registry = ToolRegistry()

    async def handler(request: ToolRequest) -> ToolResult:
        assert request.payload == {"query": "예금자보호 한도는 얼마인가요"}
        return _evidence_result()

    registry.register(ToolName.FINANCIAL_RAG, handler)
    context = HandlerContext(
        state=AgentState(message="예금자보호 한도는 얼마인가요"),
        llm=fake_llm,  # type: ignore[arg-type]
        tools=registry,
    )

    response = asyncio.run(finance_qa.handle(context))

    assert response.reply == "LLM 응답"
    instruction = fake_llm.calls[0][0]
    assert "예금자보호제도는 1인당 5천만원까지 보호합니다." in instruction
    assert "예금보험공사" in instruction
    assert "투자 권유" in instruction  # 근거가 있어도 투자 권유는 금지된다
    assert HAEYO_RULE in instruction  # #51 — 기존 응답 1,027건 재검토에서 94.1% 반말 확인, 규칙 고정
    # Tool 영수증에는 원본 데이터가 그대로 실리지 않는다 (응답 크기 절약).
    assert response.tool_results[0].data is None
    # 동일 질문 반복 시 답변 표현이 흔들리는 걸 줄이려고 이 Task만 낮은 temperature를 쓴다.
    assert fake_llm.temperatures[0] == 0.2


def test_finance_qa_wraps_long_declarative_evidence_with_haeyo_rule(
    fake_llm: FakeLLM,
) -> None:
    """긴 해라체 근거 앞뒤에 해요체 규칙을 둬 문체가 밀리는 회귀를 막는다 (#69)."""

    evidence_content = (
        "펀드는 투자자로부터 모은 자금을 자산에 운용하는 실적배당상품이다. "
        "운용 결과에 따라 원금 손실이 발생할 수 있으며 수익은 투자자에게 귀속된다. "
        "투자자는 상품의 위험과 수수료를 확인하고 자신의 판단과 책임으로 결정한다. "
    ) * 20
    registry = ToolRegistry()

    async def handler(request: ToolRequest) -> ToolResult:
        return ToolResult(
            tool_name=ToolName.FINANCIAL_RAG,
            data=[
                {
                    "chunk": {
                        "content": evidence_content,
                        "source": "금융교과서",
                    }
                }
            ],
        )

    registry.register(ToolName.FINANCIAL_RAG, handler)
    context = HandlerContext(
        state=AgentState(message="펀드에 넣으면 얼마 벌 수 있나요"),
        llm=fake_llm,  # type: ignore[arg-type]
        tools=registry,
    )

    asyncio.run(finance_qa.handle(context))

    instruction = fake_llm.calls[0][0]
    evidence_start = instruction.index("금융 자료:")
    evidence_end = instruction.index(evidence_content) + len(evidence_content)
    assert instruction.index(HAEYO_RULE) < evidence_start
    assert instruction.index(HAEYO_RULE, evidence_end) > evidence_end


def test_finance_qa_says_cannot_confirm_without_evidence(fake_llm: FakeLLM) -> None:
    """근거없음 경로는 LLM을 부르지 않고 고정 문장으로 답한다 (#74).

    운영 실측(#74)에서 NO_EVIDENCE_INSTRUCTION으로 지시해도 공통 SYSTEM_PROMPT의
    few-shot 예시("...소비 흐름을 설명하기 어려워요")를 그대로 본떠 답하는 걸
    5/5로 못 막았다. LLM을 아예 안 부르면 이 경로에서 투자 권유(FR-12-03 · NFR-05)가
    샐 가능성도 함께 사라진다.
    """

    context = HandlerContext(
        state=AgentState(message="비트코인 투자해도 될까요"),
        llm=fake_llm,  # type: ignore[arg-type]
        tools=ToolRegistry(),  # FINANCIAL_RAG 미등록 상태
    )

    response = asyncio.run(finance_qa.handle(context))

    assert response.reply == FINANCE_QA_NO_EVIDENCE_REPLY
    assert fake_llm.calls == []
    assert response.tool_results[0].success is False
    assert response.fallback is False


def test_finance_qa_uses_fixed_reply_for_empty_search_results(
    fake_llm: FakeLLM,
) -> None:
    """검색 하한으로 결과가 비어도 같은 고정 문장으로 답한다 (#28 · #74)."""

    registry = ToolRegistry()

    async def handler(request: ToolRequest) -> ToolResult:
        return ToolResult(tool_name=ToolName.FINANCIAL_RAG, data=[])

    registry.register(ToolName.FINANCIAL_RAG, handler)
    context = HandlerContext(
        state=AgentState(message="미국 기준금리 전망이 어때요?"),
        llm=fake_llm,  # type: ignore[arg-type]
        tools=registry,
    )

    response = asyncio.run(finance_qa.handle(context))

    assert response.reply == FINANCE_QA_NO_EVIDENCE_REPLY
    assert fake_llm.calls == []
    assert response.tool_results[0].success is True
    assert response.fallback is False


def test_finance_qa_falls_back_to_no_evidence_reply_when_embedding_unavailable(
    fake_llm: FakeLLM,
) -> None:
    """임베딩 실패(#65)가 `fallback: true` 전체 장애가 아니라 근거없음 답으로 흡수돼야 한다."""

    registry = ToolRegistry()

    async def handler(request: ToolRequest) -> ToolResult:
        raise RetrieverUnavailableError("금융 문서 검색을 위한 임베딩 호출에 실패했습니다.")

    registry.register(ToolName.FINANCIAL_RAG, handler)
    context = HandlerContext(
        state=AgentState(message="예금자보호 한도는 얼마인가요"),
        llm=fake_llm,  # type: ignore[arg-type]
        tools=registry,
    )

    response = asyncio.run(finance_qa.handle(context))

    assert response.reply == FINANCE_QA_NO_EVIDENCE_REPLY
    assert fake_llm.calls == []
    assert response.tool_results[0].success is False
    assert response.fallback is False


def test_finance_qa_ignores_malformed_evidence_items(fake_llm: FakeLLM) -> None:
    registry = ToolRegistry()

    async def handler(request: ToolRequest) -> ToolResult:
        return ToolResult(
            tool_name=ToolName.FINANCIAL_RAG,
            data=["문자열", {"chunk": "청크가 아님"}, {"chunk": {"content": ""}}],
        )

    registry.register(ToolName.FINANCIAL_RAG, handler)
    context = HandlerContext(
        state=AgentState(message="질문"),
        llm=fake_llm,  # type: ignore[arg-type]
        tools=registry,
    )

    response = asyncio.run(finance_qa.handle(context))

    assert response.reply == FINANCE_QA_NO_EVIDENCE_REPLY
    assert fake_llm.calls == []
