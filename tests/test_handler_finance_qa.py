"""FINANCE_QA Handler가 근거 유무에 따라 올바르게 답하는지 확인한다."""

import asyncio

from app.agent.handlers import HANDLERS, finance_qa
from app.agent.handlers.base import HandlerContext
from app.agent.state import AgentState
from app.agent.tool_registry import ToolRegistry
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
    # Tool 영수증에는 원본 데이터가 그대로 실리지 않는다 (응답 크기 절약).
    assert response.tool_results[0].data is None


def test_finance_qa_says_cannot_confirm_without_evidence(fake_llm: FakeLLM) -> None:
    context = HandlerContext(
        state=AgentState(message="비트코인 투자해도 될까요"),
        llm=fake_llm,  # type: ignore[arg-type]
        tools=ToolRegistry(),  # FINANCIAL_RAG 미등록 상태
    )

    response = asyncio.run(finance_qa.handle(context))

    instruction = fake_llm.calls[0][0]
    assert "확인할 수 없다" in instruction
    assert response.tool_results[0].success is False


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

    instruction = fake_llm.calls[0][0]
    assert "확인할 수 없다" in instruction
    assert response.reply == "LLM 응답"
