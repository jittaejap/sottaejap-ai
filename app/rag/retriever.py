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
from app.rag.schemas import FinancialChunk, SearchResult

_SEARCH_SQL = """
SELECT chunk_id, content, source, metadata,
       1 - (embedding <=> $1::vector) AS score
FROM financial_chunks
ORDER BY embedding <=> $1::vector
LIMIT $2
"""

_DEPOSIT_PROTECTION_LIMIT_TERMS = ("한도", "얼마", "금액", "까지")


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
    ) -> None:
        self._pool = pool
        self._embedder = embedder
        self._min_score = (settings or get_settings()).financial_rag_min_score

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

        try:
            rows = await self._pool.fetch(
                _SEARCH_SQL, to_vector_literal(vectors[0]), top_k
            )
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
