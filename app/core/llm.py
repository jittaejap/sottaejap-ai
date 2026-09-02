"""OpenAI 모델 호출을 한곳에 모으기 위한 최소 클라이언트.

현재 Agent 흐름에서는 호출하지 않는다. 향후 Tool Calling 구현이 기능별 코드에
직접 결합되지 않도록 공통 진입점만 제공한다.
"""

from openai import AsyncOpenAI

from app.core.config import Settings, get_settings


class LLMNotConfiguredError(RuntimeError):
    """OpenAI 설정이 없는 상태에서 모델 호출을 시도한 경우."""


class LLMClient:
    """OpenAI 비동기 클라이언트의 얇은 래퍼."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._client = (
            AsyncOpenAI(api_key=self._settings.openai_api_key)
            if self._settings.openai_api_key
            else None
        )

    async def generate(self, system_prompt: str, user_message: str) -> str:
        """기본 텍스트 응답을 생성한다.

        TODO: Tool Calling 도입 시 응답 타입과 실행 루프를 확장한다.
        """

        if self._client is None:
            raise LLMNotConfiguredError("OPENAI_API_KEY가 설정되지 않았습니다.")

        response = await self._client.chat.completions.create(
            model=self._settings.openai_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        )
        return response.choices[0].message.content or ""
