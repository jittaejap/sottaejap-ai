"""금융 문서 검색 인터페이스.

현재는 빈 결과를 반환하며 실제 pgVector 연결과 Top-K Vector Search는 TODO다.
"""

from app.rag.schemas import SearchResult


class FinancialRetriever:
    """검색 전략을 Agent와 분리하는 Retriever 경계."""

    async def search(self, query: str, top_k: int = 5) -> list[SearchResult]:
        """질문과 관련된 금융 문서 Chunk를 반환한다."""

        if not query.strip():
            raise ValueError("검색어는 비어 있을 수 없습니다.")
        if top_k <= 0:
            raise ValueError("top_k는 1 이상이어야 합니다.")

        # TODO: Query Embedding과 pgVector 유사도 검색을 연결한다.
        return []

