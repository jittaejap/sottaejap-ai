"""FinancialRetriever가 pgvector 검색을 올바르게 감싸는지 확인한다."""

import asyncio
from typing import Any

import asyncpg
import pytest

from app.core.config import Settings
from app.core.llm import LLMNotConfiguredError, LLMUnavailableError
from app.rag.keyword_index import KeywordIndex
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


# --- 하이브리드 검색(BM25 + 벡터, #78) ---
#
# "적금이란"처럼 코퍼스에 근거가 있는데도 벡터 코사인 점수가 임계값(#28)
# 근처에서 갈려 차단되는 사례가 실측으로 확인됐다. BM25(형태소 분석 기반
# 키워드 매칭)를 더해 RRF로 융합하면 이런 경계 케이스를 구조적으로 줄일 수
# 있다 — 아래 테스트는 그 융합 로직 자체를 검증한다.


def _filler_rows(count: int) -> list[dict[str, Any]]:
    """BM25는 어떤 용어가 코퍼스 전체에 다 있으면(IDF≈0) 구분을 못 한다 — 무관한
    문서를 채워 목표 용어가 코퍼스 일부에만 있게 한다. 코사인 점수는 최소
    하한(0.25)보다도 낮게 둬 최종 결과에 절대 섞여 들지 않게 한다.
    """

    return [
        {
            "chunk_id": f"filler-{i}",
            "content": f"무관한 내용 {i}입니다",
            "source": "출처",
            "metadata": {},
            "score": 0.05,
        }
        for i in range(count)
    ]


def test_hybrid_search_rescues_result_below_min_score_but_above_rescue_floor() -> None:
    """벡터 단독이면 임계값 미달로 버려질 결과를, BM25가 근거를 찾으면 살린다."""

    rows = [
        {
            "chunk_id": "c1",
            "content": "적금 적금 적금 목돈 마련을 위한 저축 상품",
            "source": "출처",
            "metadata": {},
            "score": 0.3,  # min_score(0.48) 미만, rescue floor(0.25) 이상
        },
        *_filler_rows(3),
    ]
    keyword_index = KeywordIndex.build([(row["chunk_id"], row["content"]) for row in rows])

    results = asyncio.run(
        FinancialRetriever(
            FakePool(rows=rows),
            FakeEmbedder(),
            settings=Settings(financial_rag_min_score=0.48),
            keyword_index=keyword_index,
        ).search("적금이란")
    )

    assert "c1" in [r.chunk.chunk_id for r in results]


def test_hybrid_search_still_rejects_result_below_rescue_floor() -> None:
    """BM25가 뭔가를 찾아도, 코사인 자체가 너무 낮으면(완전 무관) 통과시키지 않는다.

    BM25 원점수는 코퍼스가 작으면 절대값만으로 못 믿는다(#78) — "오늘"처럼
    흔한 명사가 특정 Chunk에 몰려 있으면 무관한 질문도 점수가 크게 나올 수
    있다. 그래서 BM25로 살아난 후보도 자기 코사인 점수가 rescue floor(0.25)는
    넘어야 한다.
    """

    rows = [
        {
            "chunk_id": "c1",
            "content": "김치찌개는 김치와 돼지고기로 끓이는 찌개",
            "source": "출처",
            "metadata": {},
            "score": 0.1,  # rescue floor(0.25) 미만
        }
    ]
    keyword_index = KeywordIndex.build([("c1", rows[0]["content"])])

    results = asyncio.run(
        FinancialRetriever(
            FakePool(rows=rows),
            FakeEmbedder(),
            settings=Settings(financial_rag_min_score=0.48),
            keyword_index=keyword_index,
        ).search("김치찌개는 뭐임")
    )

    assert results == []


def test_hybrid_search_breaks_rrf_tie_with_bm25_raw_score() -> None:
    """벡터·BM25가 서로 다른 후보를 1등으로 내 RRF가 동점이면 BM25 원점수로 가른다.

    실측(#78)에서 벡터 전용 1등이 완전히 엉뚱한 결과였고, BM25가 찾은 후보가
    실제로 더 나은 근거였다 — 이 우선순위를 그대로 코드로 고정한다.
    """

    rows = [
        {
            "chunk_id": "vector-top",
            "content": "완전히 다른 내용입니다",
            "source": "출처",
            "metadata": {},
            "score": 0.5,  # min_score 이상 — 자체로도 통과 조건은 만족한다
        },
        {
            "chunk_id": "bm25-top",
            "content": "적금 적금 적금 목돈 마련을 위한 저축 상품",
            "source": "출처",
            "metadata": {},
            "score": 0.3,  # min_score 미만, rescue floor 이상
        },
        *_filler_rows(3),
    ]
    keyword_index = KeywordIndex.build([(row["chunk_id"], row["content"]) for row in rows])

    results = asyncio.run(
        FinancialRetriever(
            FakePool(rows=rows),
            FakeEmbedder(),
            settings=Settings(financial_rag_min_score=0.48),
            keyword_index=keyword_index,
        ).search("적금이란", top_k=1)
    )

    assert [r.chunk.chunk_id for r in results] == ["bm25-top"]


def test_search_without_keyword_index_uses_vector_only_path() -> None:
    """`keyword_index`를 안 주면 기존 벡터 전용 동작 그대로다(하이브리드는 옵트인)."""

    rows = [
        {
            "chunk_id": "c1",
            "content": "적금 적금 적금 목돈 마련을 위한 저축 상품",
            "source": "출처",
            "metadata": {},
            "score": 0.3,
        }
    ]

    results = asyncio.run(
        FinancialRetriever(
            FakePool(rows=rows),
            FakeEmbedder(),
            settings=Settings(financial_rag_min_score=0.48),
        ).search("적금이란")
    )

    assert results == []  # 하이브리드가 아니므로 rescue 없이 그대로 하한 미달
