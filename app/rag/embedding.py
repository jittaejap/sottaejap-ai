"""금융 문서 Embedding 생성 경계 (FR-12).

OpenAI Embeddings API를 얇게 감싼다. Provider를 바꿔도 `embed()` 하나만 다시
구현하면 되도록 인터페이스를 좁게 유지한다.

예외는 `core/llm.py`의 것을 그대로 재사용한다. 이 모듈 안에서는 `LLMClient`와
같은 타임아웃·재시도 정책을 적용할 뿐, 이걸 누가 어떻게 흡수할지는 모른다 —
`app/rag/retriever.py`가 `RetrieverUnavailableError`로 바꿔 검색 실패 경로로
보낸다(#65). 여기서 임베딩 전용 예외를 새로 만들면 그 변환 지점이 둘로 갈라진다.
"""

from typing import Any

from openai import (
    APIConnectionError,
    APITimeoutError,
    AsyncOpenAI,
    InternalServerError,
    OpenAIError,
    RateLimitError,
)

from app.core.config import Settings, get_settings
from app.core.llm import LLM_RETRY_COUNT, LLMNotConfiguredError, LLMUnavailableError

DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
# `financial_chunks.embedding`의 vector(N)과 같은 값이어야 한다 (04 §1 · E-85).
# server V8 마이그레이션 주석이 이 이름을 그대로 지목한다 — 상수명을 바꾸지 않는다.
EMBEDDING_DIMENSIONS = 1536
# OpenAI Embeddings API는 요청 하나당 최대 30만 토큰이다. 800자 Chunk(chunk_text 기본값)가
# 한국어에서 최악의 경우 글자당 3토큰 가까이 나올 수 있어, 100개씩 나눠 보내 여유를 둔다.
# 이 값은 chunk_text()의 chunk_size(현재 800자)에 암묵적으로 묶여 있다 — chunk_size를
# 키우면 배치당 토큰 수가 늘어나 이 계산이 조용히 깨질 수 있으니, chunk_size를 바꿀
# 때는 이 값도 함께 재계산한다.
EMBEDDING_BATCH_SIZE = 100


class FinancialEmbedder:
    """OpenAI 임베딩 API의 얇은 래퍼."""

    def __init__(
        self,
        settings: Settings | None = None,
        client: AsyncOpenAI | None = None,
        model: str = DEFAULT_EMBEDDING_MODEL,
    ) -> None:
        resolved = settings or get_settings()
        if client is not None:
            self._client: AsyncOpenAI | None = client
        elif resolved.openai_api_key:
            # LLMClient(core/llm.py)와 같은 정책 — SDK 자체 재시도를 끄고
            # 아래 _create_batch()에서 정확히 1회만 재시도한다(#65). 이전에는
            # 타임아웃·재시도를 안 넘겨 SDK 기본값(read 타임아웃 600초 · 일시적
            # 오류 재시도 2회)이 그대로 적용됐다. SDK는 408·409·429·5xx·연결
            # 오류만 재시도하고 403(`model_not_found`)은 원래도 재시도 대상이
            # 아니다(PR #70 리뷰) — 이 변경이 줄이는 것은 그 타임아웃 상한과
            # 일시적 오류의 재시도 횟수이지, 403의 재시도 여부가 아니다.
            self._client = AsyncOpenAI(
                api_key=resolved.openai_api_key,
                timeout=resolved.llm_timeout_seconds,
                max_retries=0,
            )
        else:
            self._client = None
        self._model = model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """텍스트 목록의 벡터를 반환한다. 빈 목록은 호출하지 않는다."""

        if not texts:
            return []
        if self._client is None:
            raise LLMNotConfiguredError("OPENAI_API_KEY가 설정되지 않았습니다.")

        vectors: list[list[float]] = []
        for start in range(0, len(texts), EMBEDDING_BATCH_SIZE):
            batch = texts[start : start + EMBEDDING_BATCH_SIZE]
            response = await self._create_batch(batch)

            # OpenAI는 배치 응답의 data 순서를 계약으로 보장하지 않는다. item.index로
            # 정렬해 입력 순서와 어긋나지 않게 한다 — 어긋나면 Chunk 본문과 벡터가
            # 서로 다른 것끼리 짝지어져도 예외 없이 조용히 저장된다. item.index는
            # 이 배치 호출 안에서의 상대 위치라, 배치 결과를 순서대로 이어 붙이면 된다.
            ordered = sorted(response.data, key=lambda item: item.index)
            vectors.extend(item.embedding for item in ordered)
        return vectors

    async def _create_batch(self, batch: list[str]) -> Any:
        """`LLMClient._complete`와 같은 재시도 정책으로 배치 하나를 호출한다(#65).

        일시적 오류(타임아웃·연결 실패·429·5xx)만 정확히 1회 재시도한다. 403
        `model_not_found` 같은 영구 오류는 SDK도 원래 재시도하지 않지만, 여기서도
        `OpenAIError` 분기로 명시적으로 즉시 올려 재시도 여부가 우연에 기대지
        않게 한다.
        """

        if self._client is None:
            raise LLMNotConfiguredError("OPENAI_API_KEY가 설정되지 않았습니다.")

        last_error: OpenAIError | None = None
        for _ in range(1 + LLM_RETRY_COUNT):
            try:
                return await self._client.embeddings.create(
                    model=self._model,
                    input=batch,
                )
            except (
                APITimeoutError,
                APIConnectionError,
                RateLimitError,
                InternalServerError,
            ) as exc:
                last_error = exc
            except OpenAIError as exc:
                raise LLMUnavailableError(
                    "임베딩 호출이 실패했습니다 (재시도 대상 아님)."
                ) from exc
        raise LLMUnavailableError("임베딩 호출이 재시도 후에도 실패했습니다.") from last_error
