"""lifespan이 DATABASE_URL 유무에 따라 FINANCIAL_RAG를 조건부로 등록하는지 확인한다."""

import asyncio

import pytest
from fastapi import FastAPI

from app.core.config import get_settings
from app.main import lifespan
from app.schemas.tool import ToolName


class _FakePool:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


def test_lifespan_skips_financial_rag_without_database_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "")
    get_settings.cache_clear()
    app = FastAPI()

    async def run() -> None:
        async with lifespan(app):
            assert ToolName.FINANCIAL_RAG not in app.state.agent._tool_registry.names()

    asyncio.run(run())
    get_settings.cache_clear()


def test_lifespan_starts_without_financial_rag_when_pool_creation_fails(
    monkeypatch: pytest.MonkeyPatch,
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
