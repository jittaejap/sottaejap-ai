"""금융 문서 Chunk와 검색 결과 DTO."""

from typing import Any

from pydantic import BaseModel, Field


class FinancialChunk(BaseModel):
    """Embedding 및 저장 대상 금융 문서 조각."""

    chunk_id: str
    content: str
    source: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchResult(BaseModel):
    """Retriever가 Agent에 반환하는 근거 Chunk."""

    chunk: FinancialChunk
    score: float | None = None

