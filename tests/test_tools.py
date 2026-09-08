"""Tool이 계산 없이 Client 결과를 전달하고 기본 Registry에 배선되는지 확인한다."""

import asyncio
from typing import Any

import httpx

from app.agent.handlers.base import HandlerContext
from app.agent.state import AgentState
from app.agent.tool_registry import build_default_registry
from app.schemas.tool import ToolName, ToolRequest
from app.tools.analysis_tool import AnalysisTool
from tests.conftest import FakeLLM, SpringClientFactory

# 05 §3 표의 Spring 내부 AI API 경로. 회고 저장(POST)은 아직 등록하지 않는다 (#10).
SPRING_TOOL_PATHS = {
    ToolName.TRANSACTION: "/internal/ai/users/user-1/transactions",
    ToolName.REFLECTION: "/internal/ai/users/user-1/reflections",
    ToolName.ANALYSIS: "/internal/ai/users/user-1/analysis",
    ToolName.ACTION_PLAN: "/internal/ai/users/user-1/suggestions",
    ToolName.MEMORY: "/internal/ai/users/user-1/memory",
}


class FakeSpringClient:
    async def get_behavior_analysis(self, user_id: str) -> dict[str, Any]:
        return {"user_id": user_id, "classification": "SPRING_RESULT"}


def test_analysis_tool_forwards_spring_result() -> None:
    tool = AnalysisTool(FakeSpringClient())  # type: ignore[arg-type]

    result = asyncio.run(tool.execute("user-1"))

    assert result.tool_name == ToolName.ANALYSIS
    assert result.data == {"user_id": "user-1", "classification": "SPRING_RESULT"}


def _envelope(request: httpx.Request) -> httpx.Response:
    """Spring 성공 봉투를 흉내 낸다. `data`는 항상 object다 (E-70)."""

    return httpx.Response(
        200, json={"success": True, "data": {"path": request.url.path}}
    )


def test_default_registry_registers_spring_pull_tools(
    make_client: SpringClientFactory,
) -> None:
    registry = build_default_registry(make_client(_envelope))

    assert registry.names() == list(SPRING_TOOL_PATHS)
    # 금융 RAG는 DB 풀이 있어야 만들 수 있어 lifespan이 조건부로 덧붙인다.
    assert ToolName.FINANCIAL_RAG not in registry.names()


def test_default_registry_routes_each_tool_to_documented_path(
    make_client: SpringClientFactory,
) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return _envelope(request)

    registry = build_default_registry(make_client(handler))

    for name, path in SPRING_TOOL_PATHS.items():
        result = asyncio.run(registry.get(name)(ToolRequest(user_id="user-1")))

        assert result.tool_name is name
        assert result.success is True
        # 봉투를 벗긴 data를 계산 없이 그대로 넘긴다.
        assert result.data == {"path": path}

    assert [request.url.path for request in calls] == list(SPRING_TOOL_PATHS.values())


def test_default_registry_passes_transaction_query_to_params(
    make_client: SpringClientFactory,
) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return _envelope(request)

    registry = build_default_registry(make_client(handler))

    asyncio.run(
        registry.get(ToolName.TRANSACTION)(
            ToolRequest(user_id="user-1", payload={"category": "배달", "size": 5})
        )
    )

    assert dict(calls[0].url.params) == {"category": "배달", "size": "5"}


def _context(
    make_client: SpringClientFactory,
    handler: Any,
    fake_llm: FakeLLM,
    user_id: str | None = "user-1",
) -> HandlerContext:
    return HandlerContext(
        state=AgentState(user_id=user_id, message="분석해 줘"),
        llm=fake_llm,  # type: ignore[arg-type]
        tools=build_default_registry(make_client(handler)),
    )


def test_default_registry_tool_without_user_id_is_absorbed(
    make_client: SpringClientFactory,
    fake_llm: FakeLLM,
) -> None:
    """user_id가 없으면 Spring을 부르지 않고 실패 결과로 바뀐다."""

    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return _envelope(request)

    context = _context(make_client, handler, fake_llm, user_id=None)

    result = asyncio.run(context.call_tool(ToolName.ANALYSIS, {}))

    assert result.success is False
    assert result.data is None
    assert calls == []


def test_default_registry_absorbs_spring_failure(
    make_client: SpringClientFactory,
    fake_llm: FakeLLM,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "success": False,
                "error": {"code": "NOT_FOUND", "message": "없습니다."},
            },
        )

    context = _context(make_client, handler, fake_llm)

    result = asyncio.run(context.call_tool(ToolName.MEMORY, {}))

    assert result.tool_name is ToolName.MEMORY
    assert result.success is False
    assert result.message == "Tool 결과를 가져오지 못했습니다."


def test_default_registry_absorbs_unregistered_financial_rag(
    make_client: SpringClientFactory,
    fake_llm: FakeLLM,
) -> None:
    """DATABASE_URL이 없어 등록되지 않은 Tool을 불러도 예외가 아니라 success=False다."""

    context = _context(make_client, _envelope, fake_llm)

    result = asyncio.run(
        context.call_tool(ToolName.FINANCIAL_RAG, {"query": "예금자 보호"})
    )

    assert result.tool_name is ToolName.FINANCIAL_RAG
    assert result.success is False
    assert result.data is None
