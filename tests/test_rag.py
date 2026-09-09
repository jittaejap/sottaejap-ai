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


class HybridFakePool:
    """`_SEARCH_SQL`(벡터 Top-N)과 `_BY_IDS_SQL`(ID 조회)을 구분하는 테스트용 풀.

    `FakePool`은 어떤 질의에도 같은 행을 돌려주기 때문에 "벡터 후보에는 없고
    BM25로만 올라온 Chunk" 같은 하이브리드 고유의 상황을 만들 수 없다. 여기서는
    벡터 순위를 명시적으로 주고, ID 조회는 실제로 요청받은 ID만 돌려준다.
    """

    def __init__(self, corpus: list[dict[str, Any]], vector_order: list[str]) -> None:
        self.corpus = {row["chunk_id"]: row for row in corpus}
        self.vector_order = vector_order
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    async def fetch(self, query: str, *args: Any) -> list[Any]:
        self.calls.append((query, args))
        if "ANY(" in query:
            return [self.corpus[c] for c in args[1] if c in self.corpus]
        return [self.corpus[c] for c in self.vector_order[: args[1]]]


def _chunk(chunk_id: str, content: str, score: float) -> dict[str, Any]:
    return {
        "chunk_id": chunk_id,
        "content": content,
        "source": "출처",
        "metadata": {},
        "score": score,
    }


def _hybrid(pool: HybridFakePool, corpus: list[dict[str, Any]]) -> FinancialRetriever:
    return FinancialRetriever(
        pool,
        FakeEmbedder(),
        settings=Settings(financial_rag_min_score=0.48),
        keyword_index=KeywordIndex.build([(r["chunk_id"], r["content"]) for r in corpus]),
    )


def test_hybrid_search_matches_vector_order_when_bm25_matches_nothing() -> None:
    """BM25가 한 건도 못 맞히면 순위는 벡터 전용과 똑같아야 한다.

    `scores()`는 코퍼스 **전체**를 돌려주므로, 0점 후보를 거르지 않고 상위
    N개를 자르면 질문 용어가 하나도 없는 Chunk가 후보 목록을 채운다. 그 목록이
    RRF에 들어가면 **테이블 적재 순서**만으로 순위 가점을 받아, 벡터가 꼴찌로
    민 Chunk가 1등으로 올라온다(#78 리뷰에서 발견).
    """

    # 코퍼스 적재 순서는 벡터 순위의 역순이다 — 적재 순서가 새면 순위가 뒤집힌다.
    corpus = [_chunk(f"c{i}", f"금융 문단 {i} 내용입니다", 0.9 - i * 0.05) for i in range(6)]
    vector_order = [f"c{i}" for i in reversed(range(6))]
    pool = HybridFakePool(corpus, vector_order)

    results = asyncio.run(_hybrid(pool, corpus).search("김치찌개는 뭐임", top_k=5))

    assert [r.chunk.chunk_id for r in results] == vector_order[:5]


def test_hybrid_search_keeps_vector_results_that_rejected_candidates_would_displace() -> None:
    """게이트에서 탈락할 BM25 후보가 `top_k` 자리를 먹으면 안 된다.

    후보를 `top_k`로 먼저 자르고 나중에 코사인 게이트를 걸면, 어차피 버려질
    후보가 자리를 차지해 **벡터 전용이었다면 나왔을 근거**까지 함께 사라진다.
    """

    passing = [_chunk(f"v{i}", f"금융 상품 설명 문단 {i}", 0.60) for i in range(5)]
    # BM25로만 올라오지만 코사인이 낮아(0.10) 이중 게이트에서 전부 탈락한다.
    rescued_out = [_chunk(f"b{i}", "적금 적금 적금 " + f"잡음 {i}", 0.10) for i in range(5)]
    # BM25Okapi의 IDF는 용어가 코퍼스 절반 이상에 있으면 0 이하로 눌린다 —
    # "적금"이 소수 문서에만 있도록 무관 문서를 채워야 BM25가 실제로 후보를 낸다.
    corpus = passing + rescued_out + [_chunk(f"x{i}", f"무관 문단 {i}", 0.05) for i in range(8)]
    pool = HybridFakePool(corpus, [r["chunk_id"] for r in passing])

    results = asyncio.run(_hybrid(pool, corpus).search("적금이란", top_k=5))

    assert [r.chunk.chunk_id for r in results] == [r["chunk_id"] for r in passing]


def test_hybrid_search_breaks_rrf_tie_with_bm25_raw_score() -> None:
    """벡터·BM25가 서로 다른 후보를 1등으로 내 RRF가 동점이면 BM25 원점수로 가른다.

    실측(#78)에서 벡터 전용 1등이 완전히 엉뚱한 결과였고, BM25가 찾은 후보가
    실제로 더 나은 근거였다 — 이 우선순위를 그대로 코드로 고정한다.
    """

    # `vector-top`은 벡터 목록에만, `bm25-top`은 BM25 목록에만 있어 RRF가 동점이다.
    vector_top = _chunk("vector-top", "완전히 다른 내용입니다", 0.50)
    bm25_top = _chunk("bm25-top", "적금 적금 적금 목돈 마련을 위한 저축 상품", 0.30)
    corpus = [vector_top, bm25_top, *[_chunk(f"f{i}", f"무관 {i}", 0.05) for i in range(3)]]
    pool = HybridFakePool(corpus, ["vector-top", "f0", "f1", "f2"])

    results = asyncio.run(_hybrid(pool, corpus).search("적금이란", top_k=1))

    assert [r.chunk.chunk_id for r in results] == ["bm25-top"]


def test_hybrid_search_reuses_vector_rows_instead_of_refetching() -> None:
    """벡터 질의로 이미 읽은 본문·점수를 ID 조회로 다시 읽지 않는다."""

    corpus = [_chunk(f"v{i}", f"금융 상품 설명 문단 {i}", 0.60) for i in range(5)]
    pool = HybridFakePool(corpus, [r["chunk_id"] for r in corpus])

    asyncio.run(_hybrid(pool, corpus).search("김치찌개는 뭐임", top_k=5))

    assert [c for c in pool.calls if "ANY(" in c[0]] == []
