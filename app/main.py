"""소때잡 FastAPI 애플리케이션 진입점."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI

from app.agent.agent import SingleAgent
from app.agent.tool_registry import ToolRegistry
from app.api.chat import router as chat_router
from app.core.config import get_settings
from app.rag.embedding import FinancialEmbedder
from app.rag.retriever import FinancialRetriever
from app.schemas.common import HealthResponse
from app.schemas.tool import ToolName, ToolRequest
from app.tools.financial_rag_tool import FinancialRagTool


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """금융 RAG용 DB 풀을 열고 그 Retriever를 물린 Agent를 app.state에 둔다 (FR-12).

    `DATABASE_URL`이 없으면 기동을 실패시키지 않는다 — Retriever 없이 만든 Registry는
    `FINANCIAL_RAG`를 등록하지 않고, FINANCE_QA는 근거 없음 경로로 내려가 "확인할 수
    없다"고 답한다. 그게 FR-12-02가 요구하는 동작이다 (E-38 — 장애에도 기동은 된다).
    """

    settings = get_settings()
    # min_size=0 — 기동 시 연결하지 않는다. DB가 ai보다 늦게 뜨는 순서를 견딘다.
    pool = (
        await asyncpg.create_pool(settings.database_url, min_size=0)
        if settings.database_url
        else None
    )

    registry = ToolRegistry()
    if pool is not None:
        retriever = FinancialRetriever(pool, FinancialEmbedder(settings=settings))
        rag_tool = FinancialRagTool(retriever)
        registry.register(
            ToolName.FINANCIAL_RAG,
            lambda request: rag_tool.execute(query=_query(request)),
        )

    app.state.agent = SingleAgent(tool_registry=registry)
    try:
        yield
    finally:
        if pool is not None:
            await pool.close()


def _query(request: ToolRequest) -> str:
    """FINANCE_QA 처리기가 `payload["query"]`에 사용자 질문을 넣어 보낸다."""

    query = request.payload.get("query")
    if not isinstance(query, str) or not query.strip():
        raise ValueError("검색어 없이 금융 RAG를 부를 수 없습니다.")
    return query


app = FastAPI(
    title="소때잡 AI Server",
    description="Single Agent, Tool Calling, 회고 구조화, 금융 RAG를 위한 AI 서버",
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(chat_router)


@app.get("/health", response_model=HealthResponse, tags=["health"])
async def health() -> HealthResponse:
    """프로세스가 요청을 받을 수 있는지 확인한다."""

    return HealthResponse()
