"""OpenAI 모델 호출을 한곳에 모으기 위한 최소 클라이언트.

타임아웃(`LLM_TIMEOUT_SECONDS`, 기본 8초)과 재시도 1회를 여기서만 적용한다 (NFR-04).
실패는 `LLMUnavailableError`로 올리고, 템플릿 대체는 Agent가 결정한다.
"""

from openai import AsyncOpenAI, OpenAIError

from app.core.config import Settings, get_settings

LLM_RETRY_COUNT = 1


class LLMNotConfiguredError(RuntimeError):
    """OpenAI 설정이 없는 상태에서 모델 호출을 시도한 경우."""


class LLMUnavailableError(RuntimeError):
    """타임아웃·API 오류로 재시도까지 실패한 경우."""


class LLMClient:
    """OpenAI 비동기 클라이언트의 얇은 래퍼."""

    def __init__(
        self,
        settings: Settings | None = None,
        client: AsyncOpenAI | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        if client is not None:
            self._client = client
        elif self._settings.openai_api_key:
            # SDK 자체 재시도를 끄고 아래에서 정확히 1회만 재시도한다.
            self._client = AsyncOpenAI(
                api_key=self._settings.openai_api_key,
                timeout=self._settings.llm_timeout_seconds,
                max_retries=0,
            )
        else:
            self._client = None

    async def generate(self, system_prompt: str, user_message: str) -> str:
        """기본 텍스트 응답을 생성한다.

        TODO: Tool Calling 도입 시 응답 타입과 실행 루프를 확장한다.
        """

        if self._client is None:
            raise LLMNotConfiguredError("OPENAI_API_KEY가 설정되지 않았습니다.")

        last_error: OpenAIError | None = None
        for _ in range(1 + LLM_RETRY_COUNT):
            try:
                response = await self._client.chat.completions.create(
                    model=self._settings.openai_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message},
                    ],
                    timeout=self._settings.llm_timeout_seconds,
                )
                return response.choices[0].message.content or ""
            except OpenAIError as exc:
                last_error = exc
        raise LLMUnavailableError("LLM 호출이 재시도 후에도 실패했습니다.") from last_error
