"""lifespan이 Spring Tool 5종을 배선하고 FINANCIAL_RAG를 조건부로 등록하는지 확인한다."""

import asyncio

import pytest
from fastapi import FastAPI

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
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


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
