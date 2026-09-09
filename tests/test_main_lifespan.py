"""lifespan이 Spring Tool 5종을 배선하고 FINANCIAL_RAG를 조건부로 등록하는지 확인한다."""

import asyncio

import pytest
from fastapi import FastAPI

import app.main as app_main
from app.core.config import get_settings
from app.main import lifespan
from app.schemas.tool import ToolName

SPRING_TOOLS = [
    ToolName.TRANSACTION,
    ToolName.REFLECTION,
    ToolName.ANALYSIS,
    ToolName.ACTION_PLAN,
    ToolName.MEMORY,
]


class _FakePool:
    """`fetch`(기동 시 BM25 인덱스용 전체 읽기)와 `close`만 흉내 낸다.

    `fetch`가 없으면 `lifespan`의 인덱스 구축이 `AttributeError`로 떨어져
    **항상 실패 분기로만** 통과한다 — 하이브리드 배선이 통째로 검증되지 않는다.
    """

    def __init__(
        self,
        rows: list[dict[str, str]] | None = None,
        fetch_error: Exception | None = None,
        fetch_delay: float = 0.0,
    ) -> None:
        self.closed = False
        self.rows = rows if rows is not None else []
        self.fetch_error = fetch_error
        self.fetch_delay = fetch_delay
        self.queries: list[str] = []

    async def fetch(self, query: str, *args: object) -> list[dict[str, str]]:
        self.queries.append(query)
        if self.fetch_delay:
            await asyncio.sleep(self.fetch_delay)
        if self.fetch_error is not None:
            raise self.fetch_error
        return self.rows

    async def close(self) -> None:
        self.closed = True


def _capture_retrievers(monkeypatch: pytest.MonkeyPatch) -> list[object]:
    """`lifespan`이 만든 `FinancialRetriever`를 가로채 검사할 수 있게 한다."""

    created: list[object] = []
    real = app_main.FinancialRetriever

    def spy(*args: object, **kwargs: object) -> object:
        retriever = real(*args, **kwargs)
        created.append(retriever)
        return retriever

    monkeypatch.setattr("app.main.FinancialRetriever", spy)
    return created


def _use_pool(monkeypatch: pytest.MonkeyPatch, pool: _FakePool) -> None:
    async def fake_create_pool(*args: object, **kwargs: object) -> _FakePool:
        return pool

    monkeypatch.setenv("DATABASE_URL", "postgresql://test")
    get_settings.cache_clear()
    monkeypatch.setattr("app.main.asyncpg.create_pool", fake_create_pool)


def test_lifespan_skips_financial_rag_without_database_url(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("DATABASE_URL", "")
    get_settings.cache_clear()
    app = FastAPI()

    async def run() -> None:
        async with lifespan(app):
            assert ToolName.FINANCIAL_RAG not in app.state.agent._tool_registry.names()

    asyncio.run(run())
    get_settings.cache_clear()
    # DATABASE_URL 자체가 없는 것과 풀 생성 실패를 로그로 구분할 수 있어야 한다.
    assert "DATABASE_URL이 설정되지 않았습니다" in capsys.readouterr().out


def test_lifespan_starts_without_financial_rag_when_pool_creation_fails(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """DATABASE_URL이 잘못됐거나 DB가 안 떠 있어도 기동 자체는 죽지 않는다 (E-38)."""

    async def failing_create_pool(*args: object, **kwargs: object) -> None:
        raise OSError("연결 거부")

    monkeypatch.setenv("DATABASE_URL", "postgresql://broken")
    get_settings.cache_clear()
    monkeypatch.setattr("app.main.asyncpg.create_pool", failing_create_pool)
    app = FastAPI()

    async def run() -> None:
        async with lifespan(app):
            assert ToolName.FINANCIAL_RAG not in app.state.agent._tool_registry.names()

    asyncio.run(run())
    get_settings.cache_clear()
    assert "DATABASE_URL로 풀을 열지 못했습니다" in capsys.readouterr().out


def test_lifespan_registers_financial_rag_with_database_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_pool = _FakePool()

    async def fake_create_pool(*args: object, **kwargs: object) -> _FakePool:
        return fake_pool

    monkeypatch.setenv("DATABASE_URL", "postgresql://test")
    get_settings.cache_clear()
    monkeypatch.setattr("app.main.asyncpg.create_pool", fake_create_pool)
    app = FastAPI()

    async def run() -> None:
        async with lifespan(app):
            assert ToolName.FINANCIAL_RAG in app.state.agent._tool_registry.names()
        # yield 밖으로 나오면(정상 종료) 풀을 닫는다.
        assert fake_pool.closed is True

    asyncio.run(run())
    get_settings.cache_clear()


def test_lifespan_registers_spring_pull_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    """Spring Tool은 DB·RAG와 무관하게 항상 등록된다 (05 §3)."""

    monkeypatch.setenv("DATABASE_URL", "")
    get_settings.cache_clear()
    app = FastAPI()

    async def run() -> None:
        async with lifespan(app):
            assert app.state.agent._tool_registry.names() == SPRING_TOOLS

    asyncio.run(run())
    get_settings.cache_clear()


def test_lifespan_closes_spring_client_on_shutdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HTTP 연결은 프로세스가 끝날 때 닫는다."""

    closed: list[bool] = []

    class _FakeSpringClient:
        async def close(self) -> None:
            closed.append(True)

    monkeypatch.setenv("DATABASE_URL", "")
    get_settings.cache_clear()
    monkeypatch.setattr("app.main.SpringClient", lambda **_: _FakeSpringClient())
    app = FastAPI()

    async def run() -> None:
        async with lifespan(app):
            assert closed == []

    asyncio.run(run())
    get_settings.cache_clear()
    assert closed == [True]


def test_lifespan_closes_pool_even_if_spring_client_close_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SpringClient 정리가 실패해도 DB 풀은 닫는다."""

    fake_pool = _FakePool()

    async def fake_create_pool(*args: object, **kwargs: object) -> _FakePool:
        return fake_pool

    class _BrokenSpringClient:
        async def close(self) -> None:
            raise RuntimeError("연결을 닫지 못했습니다.")

    monkeypatch.setenv("DATABASE_URL", "postgresql://test")
    get_settings.cache_clear()
    monkeypatch.setattr("app.main.asyncpg.create_pool", fake_create_pool)
    monkeypatch.setattr("app.main.SpringClient", lambda **_: _BrokenSpringClient())
    app = FastAPI()

    async def run() -> None:
        with pytest.raises(RuntimeError):
            async with lifespan(app):
                pass

    asyncio.run(run())
    get_settings.cache_clear()
    assert fake_pool.closed is True


# --- 기동 시 BM25 인덱스 구축 (#78 · #79 리뷰) ---


def test_lifespan_builds_keyword_index_and_hands_it_to_retriever(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """하이브리드의 배선 자체 — 기동 시 인덱스를 지어 Retriever에 넘긴다.

    이 경로가 죽으면 검색은 조용히 벡터 전용으로 돌아가고 #78이 되살아난다.
    """

    pool = _FakePool(
        rows=[
            {"chunk_id": "c1", "content": "적금은 목돈 마련을 위한 저축 상품이다"},
            {"chunk_id": "c2", "content": "복리는 원금과 이자에 이자가 붙는 방식이다"},
        ]
    )
    _use_pool(monkeypatch, pool)
    created = _capture_retrievers(monkeypatch)
    app = FastAPI()

    async def run() -> None:
        async with lifespan(app):
            assert ToolName.FINANCIAL_RAG in app.state.agent._tool_registry.names()

    asyncio.run(run())
    get_settings.cache_clear()

    assert pool.queries == ["SELECT chunk_id, content FROM financial_chunks"]
    index = created[0]._keyword_index
    assert index is not None, "인덱스를 못 지으면 하이브리드가 통째로 꺼진다"
    assert index.chunk_ids == ["c1", "c2"]


def test_lifespan_reports_cause_when_keyword_index_build_fails(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """인덱스 구축 실패는 기동을 막지 않되(E-38), 원인을 로그로 남긴다.

    테이블 없음(server Flyway `V8` 미적용) · 타임아웃 · 메모리 부족이 같은
    한 줄로 보이면 운영에서 무엇 때문에 벡터 전용으로 돌고 있는지 알 수 없다.
    """

    _use_pool(
        monkeypatch,
        _FakePool(fetch_error=RuntimeError('relation "financial_chunks" does not exist')),
    )
    created = _capture_retrievers(monkeypatch)
    app = FastAPI()

    async def run() -> None:
        async with lifespan(app):
            # 기동은 되고 FINANCIAL_RAG도 벡터 전용으로 계속 등록된다.
            assert ToolName.FINANCIAL_RAG in app.state.agent._tool_registry.names()

    asyncio.run(run())
    get_settings.cache_clear()

    assert created[0]._keyword_index is None
    out = capsys.readouterr().out
    assert "하이브리드 검색 비활성" in out
    assert 'relation "financial_chunks" does not exist' in out


def test_lifespan_does_not_hang_when_db_never_answers(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """DB가 TCP는 받아 주고 응답을 안 하면 기동이 영영 안 끝나는 걸 막는다 (E-38).

    asyncpg는 `command_timeout` 기본값이 없어서 `fetch`가 무한정 기다린다 —
    그동안 `/health`도 못 뜨고 ai-ping이 죽는다.
    """

    monkeypatch.setattr("app.main._INDEX_BUILD_TIMEOUT_SECONDS", 0.05)
    _use_pool(monkeypatch, _FakePool(fetch_delay=5.0))
    created = _capture_retrievers(monkeypatch)
    app = FastAPI()

    async def run() -> None:
        async with lifespan(app):
            assert ToolName.FINANCIAL_RAG in app.state.agent._tool_registry.names()

    asyncio.run(asyncio.wait_for(run(), timeout=2.0))
    get_settings.cache_clear()

    assert created[0]._keyword_index is None
    assert "TimeoutError" in capsys.readouterr().out
