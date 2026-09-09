"""FinancialRetriever가 pgvector 검색을 올바르게 감싸는지 확인한다."""

import asyncio
from typing import Any

import asyncpg
import pytest

from app.core.config import Settings
from app.core.llm import LLMNotConfiguredError, LLMUnavailableError
from app.rag.retriever import (
    FinancialRetriever,
    RetrieverUnavailableError,
    to_vector_literal,
)


class FakeEmbedder:
    """실제 OpenAI 호출 없이 고정된 벡터를 돌려주는 테스트용 Embedder."""

    def __init__(
        self,
        vector: list[float] | None = [0.1, 0.2, 0.3],
        error: Exception | None = None,
    ) -> None:
        self.vector = vector
        self.error = error
        self.queries: list[str] = []

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.queries.extend(texts)
        if self.error is not None:
            raise self.error
        if self.vector is None:
            return []
        return [self.vector]


class FakePool:
    """`asyncpg.Pool`의 `fetch`만 흉내 내는 테스트용 연결 풀."""

    def __init__(
        self,
        rows: list[dict[str, Any]] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.rows = rows or []
        self.error = error
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    async def fetch(self, query: str, *args: Any) -> list[Any]:
        self.calls.append((query, args))
        if self.error is not None:
            raise self.error
        return self.rows


def test_search_rejects_blank_query() -> None:
    with pytest.raises(ValueError):
        asyncio.run(FinancialRetriever(FakePool(), FakeEmbedder()).search("   "))


def test_search_rejects_invalid_top_k() -> None:
    with pytest.raises(ValueError):
        asyncio.run(FinancialRetriever(FakePool(), FakeEmbedder()).search("질문", top_k=0))


@pytest.mark.parametrize(
    "query",
    [
        "예금자보호 한도는 얼마인가요?",
        "예금은 얼마까지 보호돼요?",
    ],
)
def test_search_suppresses_stale_deposit_protection_limit_evidence(
    query: str,
) -> None:
    pool = FakePool(
        rows=[
            {
                "chunk_id": "stale-limit",
                "content": "예금자보호 한도는 개정 전 금액입니다.",
                "source": "출처",
                "metadata": {},
                "score": 0.9,
            }
        ]
    )
    embedder = FakeEmbedder()

    results = asyncio.run(FinancialRetriever(pool, embedder).search(query))

    assert results == []
    assert embedder.queries == []
    assert pool.calls == []


def test_search_keeps_general_deposit_protection_question() -> None:
    rows = [
        {
            "chunk_id": "deposit-protection-overview",
            "content": "예금자보호제도의 일반적인 설명",
            "source": "출처",
            "metadata": {},
            "score": 0.9,
        }
    ]

    results = asyncio.run(
        FinancialRetriever(FakePool(rows=rows), FakeEmbedder()).search(
            "예금자보호제도란 무엇인가요?"
        )
    )

    assert [result.chunk.chunk_id for result in results] == [
        "deposit-protection-overview"
    ]


def test_search_returns_results_from_pool() -> None:
    rows = [
        {
            "chunk_id": "c1",
            "content": "가산금리는 기준금리에 덧붙이는 금리입니다.",
            "source": "금융용어집",
            "metadata": {"year": 2026},
            "score": 0.92,
        }
    ]
    pool = FakePool(rows=rows)
    embedder = FakeEmbedder(vector=[0.5, 0.5])

    results = asyncio.run(
        FinancialRetriever(pool, embedder).search("가산금리는?", top_k=3)
    )

    assert len(results) == 1
    assert results[0].chunk.chunk_id == "c1"
    assert results[0].chunk.source == "금융용어집"
    assert results[0].score == 0.92
    assert pool.calls[0][1] == (to_vector_literal([0.5, 0.5]), 3)
    assert embedder.queries == ["가산금리는?"]


def test_search_filters_results_below_minimum_score() -> None:
    rows = [
        {
            "chunk_id": "c1",
            "content": "질문과 관련이 충분하지 않은 내용",
            "source": "출처",
            "metadata": {},
            "score": 0.479,
        }
    ]

    results = asyncio.run(
        FinancialRetriever(
            FakePool(rows=rows),
            FakeEmbedder(),
            settings=Settings(financial_rag_min_score=0.48),
        ).search("질문")
    )

    assert results == []


def test_search_keeps_results_at_or_above_minimum_score() -> None:
    rows = [
        {
            "chunk_id": "at-threshold",
            "content": "임계값과 같은 점수의 내용",
            "source": "출처",
            "metadata": {},
            "score": 0.48,
        },
        {
            "chunk_id": "above-threshold",
            "content": "임계값보다 높은 점수의 내용",
            "source": "출처",
            "metadata": {},
            "score": 0.72,
        },
    ]

    results = asyncio.run(
        FinancialRetriever(
            FakePool(rows=rows),
            FakeEmbedder(),
            settings=Settings(financial_rag_min_score=0.48),
        ).search("질문")
    )

    assert [result.chunk.chunk_id for result in results] == [
        "at-threshold",
        "above-threshold",
    ]


def test_search_filters_result_without_score() -> None:
    rows = [
        {
            "chunk_id": "missing-score",
            "content": "점수가 없는 내용",
            "source": "출처",
            "metadata": {},
            "score": None,
        }
    ]

    results = asyncio.run(
        FinancialRetriever(
            FakePool(rows=rows),
            FakeEmbedder(),
            settings=Settings(financial_rag_min_score=0.48),
        ).search("질문")
    )

    assert results == []


def test_search_parses_json_string_metadata() -> None:
    rows = [
        {
            "chunk_id": "c1",
            "content": "내용",
            "source": "출처",
            "metadata": '{"year": 2026}',
            "score": 0.5,
        }
    ]

    results = asyncio.run(
        FinancialRetriever(FakePool(rows=rows), FakeEmbedder()).search("질문")
    )

    assert results[0].chunk.metadata == {"year": 2026}


def test_search_returns_empty_when_embedder_returns_nothing() -> None:
    results = asyncio.run(
        FinancialRetriever(FakePool(), FakeEmbedder(vector=None)).search("질문")
    )

    assert results == []


def test_search_wraps_connection_failure() -> None:
    pool = FakePool(error=asyncpg.PostgresError("연결 실패"))

    with pytest.raises(RetrieverUnavailableError):
        asyncio.run(FinancialRetriever(pool, FakeEmbedder()).search("질문"))


def test_search_wraps_embedding_unavailable_as_retriever_unavailable() -> None:
    """임베딩 호출 실패(#65)가 "AI 전체 장애"가 아니라 검색 실패로 흡수돼야 한다."""

    embedder = FakeEmbedder(error=LLMUnavailableError("임베딩 호출이 실패했습니다."))

    with pytest.raises(RetrieverUnavailableError):
        asyncio.run(FinancialRetriever(FakePool(), embedder).search("질문"))


def test_search_wraps_embedding_not_configured_as_retriever_unavailable() -> None:
    embedder = FakeEmbedder(error=LLMNotConfiguredError("OPENAI_API_KEY가 없습니다."))

    with pytest.raises(RetrieverUnavailableError):
        asyncio.run(FinancialRetriever(FakePool(), embedder).search("질문"))
