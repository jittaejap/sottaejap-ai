"""금융 문서 Embedding 생성 경계 (FR-12).

OpenAI Embeddings API를 얇게 감싼다. Provider를 바꿔도 `embed()` 하나만 다시
구현하면 되도록 인터페이스를 좁게 유지한다.

예외는 `core/llm.py`의 것을 그대로 재사용한다 — 키가 없거나 호출이 실패하면
`agent.py` 라우터가 이미 갖고 있는 폴백 경로(템플릿 + `fallback=True` + 200)로
흡수된다. 임베딩 전용 예외를 새로 만들면 그 경로가 둘로 갈라진다.
"""

from openai import AsyncOpenAI, OpenAIError

from app.core.config import Settings, get_settings
from app.core.llm import LLMNotConfiguredError, LLMUnavailableError

# 1536차원. `financial_chunks.embedding`의 vector(N)과 같은 값이어야 한다 (04 §1 · E-85).
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"


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
            self._client = AsyncOpenAI(api_key=resolved.openai_api_key)
        else:
            self._client = None
        self._model = model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """텍스트 목록의 벡터를 반환한다. 빈 목록은 호출하지 않는다."""

        if not texts:
            return []
        if self._client is None:
            raise LLMNotConfiguredError("OPENAI_API_KEY가 설정되지 않았습니다.")

        try:
            response = await self._client.embeddings.create(
                model=self._model,
                input=texts,
            )
        except OpenAIError as exc:
            raise LLMUnavailableError("임베딩 호출이 실패했습니다.") from exc

        # OpenAI는 배치 응답의 data 순서를 계약으로 보장하지 않는다. item.index로
        # 정렬해 입력 순서와 어긋나지 않게 한다 — 어긋나면 Chunk 본문과 벡터가
        # 서로 다른 것끼리 짝지어져도 예외 없이 조용히 저장된다.
        ordered = sorted(response.data, key=lambda item: item.index)
        return [item.embedding for item in ordered]
