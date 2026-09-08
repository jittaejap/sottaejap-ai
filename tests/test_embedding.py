"""FinancialEmbedder가 OpenAI 임베딩 API를 올바르게 감싸는지 확인한다."""

import asyncio
from types import SimpleNamespace

import httpx
import pytest
from openai import APITimeoutError

from app.core.config import Settings
from app.core.llm import LLMNotConfiguredError, LLMUnavailableError
from app.rag.embedding import EMBEDDING_DIMENSIONS, FinancialEmbedder


def test_embedding_dimensions_matches_financial_chunks_column() -> None:
    """server V8 마이그레이션의 vector(1536)과 이름·값이 같아야 한다 (04 §1 · E-85)."""

    assert EMBEDDING_DIMENSIONS == 1536


class FakeEmbeddings:
    def __init__(
        self,
        vectors: list[list[float]] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.vectors = vectors or []
        self.error = error
        self.calls: list[dict[str, object]] = []

    async def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        # 실제 API처럼 각 항목에 index를 붙인다 — 응답 순서가 입력 순서와
        # 다를 수 있다는 계약을 테스트가 실제로 검증하게 하기 위함이다.
        return SimpleNamespace(
            data=[
                SimpleNamespace(embedding=vector, index=index)
                for index, vector in enumerate(self.vectors)
            ]
        )


class FakeOpenAI:
    def __init__(
        self,
        vectors: list[list[float]] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.embeddings = FakeEmbeddings(vectors=vectors, error=error)


def test_embed_returns_empty_list_for_empty_input() -> None:
    embedder = FinancialEmbedder(
        settings=Settings(openai_api_key="k"), client=FakeOpenAI()  # type: ignore[arg-type]
    )

    result = asyncio.run(embedder.embed([]))

    assert result == []


def test_embed_raises_without_key() -> None:
    embedder = FinancialEmbedder(settings=Settings(openai_api_key=None))

    with pytest.raises(LLMNotConfiguredError):
        asyncio.run(embedder.embed(["텍스트"]))


def test_embed_returns_vectors_in_order() -> None:
    fake = FakeOpenAI(vectors=[[0.1, 0.2], [0.3, 0.4]])
    embedder = FinancialEmbedder(
        settings=Settings(openai_api_key="k"), client=fake  # type: ignore[arg-type]
    )

    result = asyncio.run(embedder.embed(["문서1", "문서2"]))

    assert result == [[0.1, 0.2], [0.3, 0.4]]
    assert fake.embeddings.calls[0]["model"] == "text-embedding-3-small"
    assert fake.embeddings.calls[0]["input"] == ["문서1", "문서2"]


def test_embed_reorders_response_by_index() -> None:
    """응답 `data` 순서가 입력 순서와 달라도 `index` 기준으로 바로잡는다."""

    class ShuffledEmbeddings:
        async def create(self, **_: object) -> object:
            # 두 번째로 요청한 텍스트의 벡터가 응답에서는 먼저 온다.
            return SimpleNamespace(
                data=[
                    SimpleNamespace(embedding=[9.0, 9.0], index=1),
                    SimpleNamespace(embedding=[1.0, 1.0], index=0),
                ]
            )

    class ShuffledOpenAI:
        def __init__(self) -> None:
            self.embeddings = ShuffledEmbeddings()

    embedder = FinancialEmbedder(
        settings=Settings(openai_api_key="k"), client=ShuffledOpenAI()  # type: ignore[arg-type]
    )

    result = asyncio.run(embedder.embed(["첫번째", "두번째"]))

    assert result == [[1.0, 1.0], [9.0, 9.0]]


def test_embed_wraps_api_error() -> None:
    error = APITimeoutError(
        request=httpx.Request("POST", "https://api.openai.com/v1/embeddings")
    )
    fake = FakeOpenAI(error=error)
    embedder = FinancialEmbedder(
        settings=Settings(openai_api_key="k"), client=fake  # type: ignore[arg-type]
    )

    with pytest.raises(LLMUnavailableError):
        asyncio.run(embedder.embed(["텍스트"]))
