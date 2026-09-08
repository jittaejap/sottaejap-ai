"""FinancialEmbedder가 OpenAI 임베딩 API를 올바르게 감싸는지 확인한다."""

import asyncio
from types import SimpleNamespace

import httpx
import pytest
from openai import APITimeoutError

from app.core.config import Settings
from app.core.llm import LLMNotConfiguredError, LLMUnavailableError
from app.rag.embedding import FinancialEmbedder


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
        return SimpleNamespace(
            data=[SimpleNamespace(embedding=vector) for vector in self.vectors]
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
