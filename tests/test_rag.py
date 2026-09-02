"""금융 Retriever 최소 인터페이스 테스트."""

import asyncio

import pytest

from app.rag.retriever import FinancialRetriever


def test_retriever_can_be_called_without_external_database() -> None:
    results = asyncio.run(FinancialRetriever().search("예금 금리는 무엇인가요?", top_k=3))

    assert results == []


def test_retriever_rejects_invalid_top_k() -> None:
    with pytest.raises(ValueError):
        asyncio.run(FinancialRetriever().search("질문", top_k=0))

