"""금융 문서 검색 인터페이스 (FR-12).

pgVector 코사인 거리(`<=>`)로 Top-K 근거 Chunk를 찾는다.

`financial_chunks` 테이블과 `CREATE EXTENSION vector`는 **`sottaejap-server`의
Flyway(`V8`)가 소유한다**(04 §1 · E-21 · E-85). 여기서는 만들지도 확장을 설치하지도
않고, 이미 있는 테이블을 읽기만 한다.

연결 풀은 밖에서 주입받는다 — 이 모듈이 직접 `DATABASE_URL`로 접속하면 테스트가
DB 없이는 돌지 않는다.
"""

import json
from typing import Any, Protocol

import asyncpg

from app.core.config import Settings, get_settings
from app.core.llm import LLMNotConfiguredError, LLMUnavailableError
from app.rag.embedding import FinancialEmbedder
from app.rag.keyword_index import KeywordIndex
from app.rag.schemas import FinancialChunk, SearchResult

_SEARCH_SQL = """
SELECT chunk_id, content, source, metadata,
       1 - (embedding <=> $1::vector) AS score
FROM financial_chunks
ORDER BY embedding <=> $1::vector
LIMIT $2
"""

_BY_IDS_SQL = """
SELECT chunk_id, content, source, metadata,
       1 - (embedding <=> $1::vector) AS score
FROM financial_chunks
WHERE chunk_id = ANY($2::text[])
"""

_DEPOSIT_PROTECTION_LIMIT_TERMS = ("한도", "얼마", "금액", "까지")

# RRF의 표준값(문헌·Elasticsearch 기본값) — 순위 차이를 완만하게 반영한다.
_RRF_K = 60
# 융합 전 각 방식에서 몇 개까지 후보로 볼지. 최종 top_k보다 넉넉히 크게 잡아
# 두 방식의 순위가 겹치지 않는 경우에도 융합할 여지를 준다.
_CANDIDATE_POOL_SIZE = 15
# BM25 원점수는 코퍼스가 작아(861개 Chunk) 절대값만으로 못 믿는다 — "오늘"처럼
# 흔한 명사가 특정 Chunk에 몰려 있으면 무관한 질문도 점수가 크게 나온다(실측:
# "파이썬 코딩 알려줘"가 "오늘 날씨 어때"보다도 낮은 완전 무관 사례인데
# BM25만으로는 구분이 안 됐다). 그래서 BM25로 살린 후보도 **자신의 코사인
# 점수**가 이 하한은 넘어야 한다 — `_min_score`(0.48)보다 낮지만, 실측 8개
# 표본에서 진짜 관련 있는 질문(0.28~0.40)과 완전 무관한 질문(0.07~0.22)이
# 갈리는 지점이 여기다.
_HYBRID_RESCUE_COSINE_FLOOR = 0.25


class RetrieverUnavailableError(RuntimeError):
    """저장소나 임베딩에 닿지 못했다 — DB가 내려갔거나 `financial_chunks`가 아직
    없거나, 임베딩 호출이 실패했다(#65).

    `HandlerContext.call_tool`이 이걸 흡수해 `ToolResult(success=False)`로 바꾸고,
    FINANCE_QA는 근거 없음 경로로 내려가 "확인할 수 없다"고 답한다 (FR-12-02).
    asyncpg 예외나 임베딩의 `LLMUnavailableError`를 그대로 올리면 흡수 목록에
    없어 `/chat`이 500이 되거나(asyncpg) `SingleAgent`의 전체 장애 폴백으로
    잘못 분류된다(임베딩 — 검색 실패일 뿐인데 "AI 장애" 배너가 뜬다).
    """


class ConnectionPool(Protocol):
    """`asyncpg.Pool`과 테스트용 Fake가 함께 만족하는 최소 계약."""

    async def fetch(self, query: str, *args: Any) -> list[Any]: ...


class FinancialRetriever:
    """검색 전략을 Agent와 분리하는 Retriever 경계."""

    def __init__(
        self,
        pool: ConnectionPool,
        embedder: FinancialEmbedder,
        settings: Settings | None = None,
        keyword_index: KeywordIndex | None = None,
    ) -> None:
        self._pool = pool
        self._embedder = embedder
        self._min_score = (settings or get_settings()).financial_rag_min_score
        # None이면 기존 벡터 전용 검색으로 동작한다 — 하이브리드는 옵트인이다
        # (app/main.py가 기동 시 인덱스를 지어 넘겨줄 때만 켜진다).
        self._keyword_index = keyword_index

    async def search(self, query: str, top_k: int = 5) -> list[SearchResult]:
        """질문과 관련된 금융 문서 Chunk를 유사도 높은 순으로 반환한다."""

        if not query.strip():
            raise ValueError("검색어는 비어 있을 수 없습니다.")
        if top_k <= 0:
            raise ValueError("top_k는 1 이상이어야 합니다.")
        # 현재 배포 코퍼스의 예금자보호 한도는 개정 전 값이다. 잘못된 금액을
        # 근거로 답하기보다 한도 질문만 근거없음 경로로 보내고, 제도 설명 검색은
        # 유지한다. 문서를 최신 기준으로 재적재하면 이 임시 가드를 제거한다.
        if _asks_deposit_protection_limit(query):
            return []

        try:
            vectors = await self._embedder.embed([query])
        except (LLMNotConfiguredError, LLMUnavailableError) as exc:
            # 임베딩 실패는 "AI 전체 장애"가 아니라 이 검색 하나의 실패다(#65) —
            # RetrieverUnavailableError로 다시 던져 위 docstring의 흡수 경로를 타게 한다.
            raise RetrieverUnavailableError(
                "금융 문서 검색을 위한 임베딩 호출에 실패했습니다."
            ) from exc
        if not vectors:
            return []

        if self._keyword_index is not None:
            return await self._hybrid_search(query, vectors[0], top_k)
        return await self._vector_search(vectors[0], top_k)

    async def _vector_search(self, vector: list[float], top_k: int) -> list[SearchResult]:
        try:
            rows = await self._pool.fetch(_SEARCH_SQL, to_vector_literal(vector), top_k)
        except (asyncpg.PostgresError, asyncpg.InterfaceError, OSError) as exc:
            # PostgresError는 연결 실패(PostgresConnectionError)와 테이블 없음
            # (UndefinedTableError)을 함께 덮고, OSError는 접속 거부·타임아웃을 덮는다.
            raise RetrieverUnavailableError(
                "금융 문서 저장소에 접근할 수 없습니다."
            ) from exc

        results = [_to_result(row) for row in rows]
        # SQL 검색 경로에서는 score가 항상 계산되지만 DTO는 다른 Retriever 구현을
        # 위해 옵셔널이다. 품질을 확인할 수 없는 None은 하한 미달과 같이 버린다.
        return [
            result
            for result in results
            if result.score is not None and result.score >= self._min_score
        ]

    async def _hybrid_search(
        self, query: str, vector: list[float], top_k: int
    ) -> list[SearchResult]:
        """벡터·BM25 후보를 RRF로 합친다(#28 후속 — 실측 중 프로토타입).

        "적금이란"처럼 벡터 유사도만으로는 임계값 근처에서 갈리던 질문이
        BM25(형태소 분석 기반 키워드 매칱)로는 뚜렷하게 잡히는 사례가 실측으로
        확인됐다. 두 순위를 점수 스케일이 다른 채로 그냥 더하지 않고 RRF(순위
        기반)로 합친다 — 코사인(0~1)과 BM25(코퍼스 크기에 따라 스케일이
        다름)를 직접 비교할 필요가 없다. 두 방식이 서로 다른 후보를 1등으로
        내면 RRF 점수가 정확히 같아지는 동점이 생기는데(각자 리스트에만 있어
        순위 기여가 같음), 이때는 BM25 원점수가 더 높은 쪽을 선택한다 —
        실측상 벡터 전용이 완전히 엉뚱한 결과를 낸 사례에서, BM25가 정확한
        용어 일치를 찾은 쪽이 실제로 더 나은 근거였다.
        """

        assert self._keyword_index is not None  # 호출자가 이미 확인했다.

        try:
            vector_rows = await self._pool.fetch(
                _SEARCH_SQL, to_vector_literal(vector), _CANDIDATE_POOL_SIZE
            )
        except (asyncpg.PostgresError, asyncpg.InterfaceError, OSError) as exc:
            raise RetrieverUnavailableError(
                "금융 문서 저장소에 접근할 수 없습니다."
            ) from exc

        vector_ranked = [row["chunk_id"] for row in vector_rows]
        bm25_scores = self._keyword_index.scores(query)
        bm25_ranked = [
            chunk_id
            for chunk_id, _ in sorted(
                bm25_scores.items(), key=lambda kv: kv[1], reverse=True
            )[:_CANDIDATE_POOL_SIZE]
        ]

        fused: dict[str, float] = {}
        for ranked in (vector_ranked, bm25_ranked):
            for position, chunk_id in enumerate(ranked):
                fused[chunk_id] = fused.get(chunk_id, 0.0) + 1.0 / (_RRF_K + position + 1)

        ordered_ids = [
            chunk_id
            for chunk_id, _ in sorted(
                fused.items(),
                key=lambda kv: (kv[1], bm25_scores.get(kv[0], 0.0)),
                reverse=True,
            )[:top_k]
        ]
        if not ordered_ids:
            return []

        try:
            rows = await self._pool.fetch(_BY_IDS_SQL, to_vector_literal(vector), ordered_ids)
        except (asyncpg.PostgresError, asyncpg.InterfaceError, OSError) as exc:
            raise RetrieverUnavailableError(
                "금융 문서 저장소에 접근할 수 없습니다."
            ) from exc

        by_id = {row["chunk_id"]: row for row in rows}
        results: list[SearchResult] = []
        for chunk_id in ordered_ids:
            row = by_id.get(chunk_id)
            if row is None or row["score"] is None:
                continue
            cosine = row["score"]
            # 벡터 자체로 자신 있는 후보(기존 #28 기준)는 그대로 통과한다.
            # BM25로만 살아남은 후보는 완전 무관 질문을 걸러내기 위해 코사인
            # 하한(_HYBRID_RESCUE_COSINE_FLOOR)도 같이 넘어야 한다 — BM25
            # 원점수 하나만으로는 위 상수 설명대로 신뢰할 수 없다.
            if cosine >= self._min_score or (
                cosine >= _HYBRID_RESCUE_COSINE_FLOOR and bm25_scores.get(chunk_id, 0.0) > 0
            ):
                results.append(_to_result(row))
        return results


def _asks_deposit_protection_limit(query: str) -> bool:
    """낡은 금액 근거를 노출할 수 있는 예금자보호 한도 질문인지 확인한다."""

    compact = "".join(query.split())
    asks_about_deposit_protection = "예금자보호" in compact or (
        "예금" in compact and "보호" in compact
    )
    return asks_about_deposit_protection and any(
        term in compact for term in _DEPOSIT_PROTECTION_LIMIT_TERMS
    )


def to_vector_literal(vector: list[float]) -> str:
    """asyncpg는 pgvector 타입을 모른다 — `'[1,2,3]'::vector` 리터럴로 넘긴다."""

    return "[" + ",".join(repr(float(value)) for value in vector) + "]"


def _to_result(row: Any) -> SearchResult:
    metadata = row["metadata"]
    if isinstance(metadata, str):
        metadata = json.loads(metadata)

    return SearchResult(
        chunk=FinancialChunk(
            chunk_id=row["chunk_id"],
            content=row["content"],
            source=row["source"],
            metadata=dict(metadata or {}),
        ),
        score=row["score"],
    )
