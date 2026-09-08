"""Task Handler 공통 LLM·Tool 실행 경계를 확인한다."""

import asyncio

import httpx
import pytest

from app.agent.handlers.base import HandlerContext, tool_receipt
from app.agent.state import AgentState
from app.agent.tool_registry import ToolRegistry
from app.clients.spring_client import SpringApiError
from app.rag.retriever import RetrieverUnavailableError
from app.schemas.tool import ToolName, ToolRequest, ToolResult
from tests.conftest import FakeLLM


def test_handler_context_generate_uses_prompt_builder(fake_llm: FakeLLM) -> None:
    context = HandlerContext(
        state=AgentState(message="사용자 메시지"),
        llm=fake_llm,  # type: ignore[arg-type]
        tools=ToolRegistry(),
    )

    result = asyncio.run(context.generate("Task별 지시문"))

    assert result == "LLM 응답"
    assert fake_llm.calls[0][1] == "사용자 메시지"
    assert "Task별 지시문" in fake_llm.calls[0][0]


def test_handler_context_call_tool_returns_result(fake_llm: FakeLLM) -> None:
    registry = ToolRegistry()
    requests: list[ToolRequest] = []

    async def handler(request: ToolRequest) -> ToolResult:
        requests.append(request)
        return ToolResult(tool_name=ToolName.ANALYSIS, data={"result": "Spring"})

    registry.register(ToolName.ANALYSIS, handler)
    context = HandlerContext(
        state=AgentState(user_id="user-1", message="분석해 줘"),
        llm=fake_llm,  # type: ignore[arg-type]
        tools=registry,
    )

    result = asyncio.run(
        context.call_tool(ToolName.ANALYSIS, {"yearMonth": "2026-09"})
    )

    assert result.success is True
    assert result.data == {"result": "Spring"}
    assert requests == [
        ToolRequest(
            user_id="user-1",
            payload={"yearMonth": "2026-09"},
        )
    ]


def test_handler_context_absorbs_unknown_tool(fake_llm: FakeLLM) -> None:
    context = HandlerContext(
        state=AgentState(message="분석해 줘"),
        llm=fake_llm,  # type: ignore[arg-type]
        tools=ToolRegistry(),
    )

    result = asyncio.run(context.call_tool(ToolName.ANALYSIS, {}))

    assert result.tool_name is ToolName.ANALYSIS
    assert result.success is False
    assert result.data is None
    assert result.message


@pytest.mark.parametrize(
    "error",
    [
        KeyError("Tool 내부 키 없음"),
        SpringApiError("SPRING_ERROR", "Spring 실패"),
        RetrieverUnavailableError("검색 실패"),
        httpx.HTTPError("HTTP 실패"),
        ValueError("잘못된 결과"),
    ],
)
def test_handler_context_absorbs_tool_errors(
    error: Exception,
    fake_llm: FakeLLM,
) -> None:
    registry = ToolRegistry()

    async def handler(request: ToolRequest) -> ToolResult:
        raise error

    registry.register(ToolName.ANALYSIS, handler)
    context = HandlerContext(
        state=AgentState(message="분석해 줘"),
        llm=fake_llm,  # type: ignore[arg-type]
        tools=registry,
    )

    result = asyncio.run(context.call_tool(ToolName.ANALYSIS, {}))

    assert result.tool_name is ToolName.ANALYSIS
    assert result.success is False
    assert result.data is None
    assert result.message == "Tool 결과를 가져오지 못했습니다."


def test_handler_context_does_not_expose_internal_url_in_error_message(
    fake_llm: FakeLLM,
) -> None:
    registry = ToolRegistry()
    request = httpx.Request(
        "GET",
        "http://spring:8080/internal/ai/users/user-42/transactions",
    )

    async def handler(tool_request: ToolRequest) -> ToolResult:
        raise httpx.HTTPStatusError(
            "404 Not Found",
            request=request,
            response=httpx.Response(404, request=request),
        )

    registry.register(ToolName.TRANSACTION, handler)
    context = HandlerContext(
        state=AgentState(user_id="user-42", message="거래를 보여 줘"),
        llm=fake_llm,  # type: ignore[arg-type]
        tools=registry,
    )

    result = asyncio.run(context.call_tool(ToolName.TRANSACTION, {}))

    assert result.success is False
    assert result.message == "Tool 결과를 가져오지 못했습니다."
    assert "spring:8080" not in result.message
    assert "user-42" not in result.message


def test_tool_receipt_removes_data_without_mutating_original() -> None:
    result = ToolResult(
        tool_name=ToolName.ANALYSIS,
        data={"private": "result"},
        message="조회 완료",
    )

    receipt = tool_receipt(result)

    assert receipt == ToolResult(
        tool_name=ToolName.ANALYSIS,
        data=None,
        message="조회 완료",
    )
    assert result.data == {"private": "result"}


def test_tool_receipt_preserves_reflection_data() -> None:
    reflection = {
        "purpose": "충동",
        "companion": "혼자",
        "uncertain_fields": ["satisfaction"],
    }
    result = ToolResult(
        tool_name=ToolName.REFLECTION,
        data=reflection,
        message="회고 후보 추출 완료",
    )

    receipt = tool_receipt(result)

    assert receipt == result
    assert receipt is not result
    assert receipt.data == reflection
