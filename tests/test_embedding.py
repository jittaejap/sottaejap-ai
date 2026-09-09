"""FinancialEmbedder가 OpenAI 임베딩 API를 올바르게 감싸는지 확인한다."""

import asyncio
from types import SimpleNamespace

import httpx
import pytest
from openai import APITimeoutError

from app.core.config import Settings
from app.core.llm import LLMNotConfiguredError, LLMUnavailableError
from app.rag.embedding import EMBEDDING_BATCH_SIZE, EMBEDDING_DIMENSIONS, FinancialEmbedder


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


def test_embed_splits_large_input_into_batches() -> None:
    """EMBEDDING_BATCH_SIZE를 넘는 입력은 여러 번 나눠 호출한다 (OpenAI 30만 토큰 제한)."""

    class BatchAwareEmbeddings:
        def __init__(self) -> None:
            self.calls: list[list[str]] = []

        async def create(self, **kwargs: object) -> object:
            batch = kwargs["input"]
            self.calls.append(batch)
            return SimpleNamespace(
                data=[
                    SimpleNamespace(embedding=[float(len(text))], index=index)
                    for index, text in enumerate(batch)
                ]
            )

    class BatchAwareOpenAI:
        def __init__(self) -> None:
            self.embeddings = BatchAwareEmbeddings()

    fake = BatchAwareOpenAI()
    embedder = FinancialEmbedder(
        settings=Settings(openai_api_key="k"), client=fake  # type: ignore[arg-type]
    )
    texts = [f"문서{i}" for i in range(EMBEDDING_BATCH_SIZE + 1)]

    result = asyncio.run(embedder.embed(texts))

    assert len(fake.embeddings.calls) == 2
    assert len(fake.embeddings.calls[0]) == EMBEDDING_BATCH_SIZE
    assert len(fake.embeddings.calls[1]) == 1
    assert result == [[float(len(text))] for text in texts]


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


def test_embed_retries_once_on_timeout_then_succeeds() -> None:
    """`LLMClient`와 같은 정책 — 일시적 오류는 1회 재시도 후 성공하면 그대로 반환한다(#65)."""

    class FlakyEmbeddings:
        def __init__(self) -> None:
            self.calls = 0

        async def create(self, **_: object) -> object:
            self.calls += 1
            if self.calls == 1:
                raise APITimeoutError(
                    request=httpx.Request("POST", "https://api.openai.com/v1/embeddings")
                )
            return SimpleNamespace(data=[SimpleNamespace(embedding=[1.0, 2.0], index=0)])

    class FlakyOpenAI:
        def __init__(self) -> None:
            self.embeddings = FlakyEmbeddings()

    fake = FlakyOpenAI()
    embedder = FinancialEmbedder(
        settings=Settings(openai_api_key="k"), client=fake  # type: ignore[arg-type]
    )

    result = asyncio.run(embedder.embed(["텍스트"]))

    assert result == [[1.0, 2.0]]
    assert fake.embeddings.calls == 2


def test_embed_does_not_retry_permanent_error() -> None:
    """403 `model_not_found` 같은 영구 오류는 재시도 없이 바로 실패해야 한다(#65).

    SDK도 이런 오류는 원래 재시도하지 않지만(408·409·429·5xx·연결 오류만
    재시도), `_create_batch()`가 그 구분을 SDK 재시도 설정에만 기대지 않고
    직접 명시하는지 확인한다(PR #70 리뷰).
    """
    from openai import PermissionDeniedError

    class DeniedEmbeddings:
        def __init__(self) -> None:
            self.calls = 0

        async def create(self, **_: object) -> object:
            self.calls += 1
            raise PermissionDeniedError(
                message="model_not_found",
                response=httpx.Response(
                    403, request=httpx.Request("POST", "https://api.openai.com/v1/embeddings")
                ),
                body=None,
            )

    class DeniedOpenAI:
        def __init__(self) -> None:
            self.embeddings = DeniedEmbeddings()

    fake = DeniedOpenAI()
    embedder = FinancialEmbedder(
        settings=Settings(openai_api_key="k"), client=fake  # type: ignore[arg-type]
    )

    with pytest.raises(LLMUnavailableError):
        asyncio.run(embedder.embed(["텍스트"]))

    assert fake.embeddings.calls == 1


def test_client_uses_configured_timeout_and_disables_sdk_retries() -> None:
    """SDK 기본 재시도·긴 타임아웃 대신 `llm_timeout_seconds`와 자체 1회 재시도를 쓴다(#65)."""

    embedder = FinancialEmbedder(settings=Settings(openai_api_key="k", llm_timeout_seconds=6.0))

    assert embedder._client is not None  # type: ignore[attr-defined]
    assert embedder._client.timeout == 6.0  # type: ignore[attr-defined]
    assert embedder._client.max_retries == 0  # type: ignore[attr-defined]


def test_explicit_timeout_seconds_overrides_llm_timeout() -> None:
    """대량 배치 호출(적재 스크립트 등)은 `llm_timeout_seconds`와 다른 값을 쓸 수 있다(PR #70 리뷰 5).

    실시간 질문 경로(FINANCE_QA)는 배치 1개뿐이라 `llm_timeout_seconds`(6초)로
    충분하지만, `scripts/ingest_financial_docs.py`처럼 배치당 최대 100 Chunk를
    한 번에 보내는 경로는 6초가 빠듯할 수 있다 — `timeout_seconds`를 명시하면
    그 값을 그대로 쓰고 `llm_timeout_seconds`는 무시된다.
    """

    embedder = FinancialEmbedder(
        settings=Settings(openai_api_key="k", llm_timeout_seconds=6.0),
        timeout_seconds=60.0,
    )

    assert embedder._client is not None  # type: ignore[attr-defined]
    assert embedder._client.timeout == 60.0  # type: ignore[attr-defined]
    assert embedder._client.max_retries == 0  # type: ignore[attr-defined]
