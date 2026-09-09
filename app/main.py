"""소때잡 FastAPI 애플리케이션 진입점."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI

from app.agent.agent import SingleAgent
from app.agent.tool_registry import build_default_registry
from app.api.chat import router as chat_router
from app.clients.spring_client import SpringClient
from app.core.config import get_settings
from app.rag.embedding import FinancialEmbedder
from app.rag.keyword_index import KeywordIndex
from app.rag.retriever import FinancialRetriever
from app.schemas.common import HealthResponse
from app.schemas.tool import ToolName, ToolRequest
from app.tools.financial_rag_tool import FinancialRagTool


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Spring pull Tool과 금융 RAG를 물린 Agent를 만들어 app.state에 둔다 (05 §3 · FR-12).

    Spring Tool 5종은 항상 등록한다 — HTTP 연결은 `SpringClient` 하나를 공유하고
    프로세스가 끝날 때 닫는다. Spring이 죽어 있어도 기동은 되고, 호출 실패는
    `HandlerContext.call_tool`이 `success=False`로 흡수한다.

    `DATABASE_URL`이 없으면 기동을 실패시키지 않는다 — Retriever 없이 만든 Registry는
    `FINANCIAL_RAG`를 등록하지 않고, FINANCE_QA는 근거 없음 경로로 내려가 "확인할 수
    없다"고 답한다. 그게 FR-12-02가 요구하는 동작이다 (E-38 — 장애에도 기동은 된다).
    """

    settings = get_settings()
    pool = None
    if not settings.database_url:
        print("금융 RAG 비활성 — DATABASE_URL이 설정되지 않았습니다.")
    else:
        try:
            # min_size=0 — 기동 시 연결하지 않는다. DB가 ai보다 늦게 뜨는 순서를 견딘다.
            pool = await asyncpg.create_pool(settings.database_url, min_size=0)
        except Exception:  # noqa: BLE001 — 풀을 못 열어도 기동은 한다 (E-38 · E-86)
            print("금융 RAG 비활성 — DATABASE_URL로 풀을 열지 못했습니다.")
            pool = None

    spring_client = SpringClient(settings=settings)
    registry = build_default_registry(spring_client)
    if pool is not None:
        keyword_index = None
        try:
            # 하이브리드 검색 프로토타입(#28 후속) — BM25 인덱스는 기동 시
            # 한 번만 짓는다(861개 Chunk 기준 가벼움). 실패해도 벡터 전용으로
            # 계속 기동한다 — E-38과 같은 전제(장애에도 기동은 된다).
            rows = await pool.fetch("SELECT chunk_id, content FROM financial_chunks")
            keyword_index = KeywordIndex.build([(r["chunk_id"], r["content"]) for r in rows])
        except Exception:  # noqa: BLE001
            print("하이브리드 검색 비활성 — BM25 인덱스를 짓지 못했습니다.")
        retriever = FinancialRetriever(
            pool, FinancialEmbedder(settings=settings), keyword_index=keyword_index
        )
        rag_tool = FinancialRagTool(retriever)
        registry.register(
            ToolName.FINANCIAL_RAG,
            lambda request: rag_tool.execute(query=_query(request)),
        )

    app.state.agent = SingleAgent(tool_registry=registry)
    try:
        yield
    finally:
        # 한쪽 정리가 실패해도 다른 쪽은 반드시 닫는다.
        try:
            await spring_client.close()
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
