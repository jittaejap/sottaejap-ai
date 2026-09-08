"""LLMClient의 텍스트·JSON 응답과 공통 재시도 정책을 확인한다."""

import asyncio
from types import SimpleNamespace

import httpx
import pytest
from openai import APITimeoutError, BadRequestError

from app.core.config import Settings
from app.core.llm import LLMClient, LLMNotConfiguredError, LLMUnavailableError


class FakeCompletions:
    def __init__(
        self,
        content: str | None = "LLM 응답",
        failures_before_success: int = 0,
        error: Exception | None = None,
    ) -> None:
        self.content = content
        self.failures_before_success = failures_before_success
        self.error = error
        self.calls: list[dict[str, object]] = []

    async def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        if len(self.calls) <= self.failures_before_success:
            if self.error is not None:
                raise self.error
            raise APITimeoutError(
                request=httpx.Request(
                    "POST",
                    "https://api.openai.com/v1/chat/completions",
                )
            )
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self.content))])


class FakeOpenAI:
    def __init__(
        self,
        content: str | None = "LLM 응답",
        failures_before_success: int = 0,
        error: Exception | None = None,
    ) -> None:
        self.chat = type("Chat", (), {})()
        self.chat.completions = FakeCompletions(
            content=content,
            failures_before_success=failures_before_success,
            error=error,
        )


def test_llm_timeout_default_is_six_seconds() -> None:
    assert Settings.model_fields["llm_timeout_seconds"].default == 6.0


def test_generate_returns_text_response() -> None:
    fake = FakeOpenAI(content="텍스트 응답")
    client = LLMClient(settings=Settings(openai_api_key="k"), client=fake)  # type: ignore[arg-type]

    result = asyncio.run(client.generate("system", "user"))

    assert result == "텍스트 응답"
    assert "response_format" not in fake.chat.completions.calls[0]
    assert "temperature" not in fake.chat.completions.calls[0]


def test_generate_retries_once_then_raises() -> None:
    fake = FakeOpenAI(failures_before_success=2)
    client = LLMClient(settings=Settings(openai_api_key="k"), client=fake)  # type: ignore[arg-type]

    with pytest.raises(LLMUnavailableError):
        asyncio.run(client.generate("system", "user"))

    assert len(fake.chat.completions.calls) == 2


def test_generate_returns_second_response_after_retryable_failure() -> None:
    fake = FakeOpenAI(content="재시도 응답", failures_before_success=1)
    client = LLMClient(settings=Settings(openai_api_key="k"), client=fake)  # type: ignore[arg-type]

    result = asyncio.run(client.generate("system", "user"))

    assert result == "재시도 응답"
    assert len(fake.chat.completions.calls) == 2


def test_generate_does_not_retry_bad_request() -> None:
    response = httpx.Response(
        400,
        request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"),
    )
    fake = FakeOpenAI(
        failures_before_success=1,
        error=BadRequestError("잘못된 요청", response=response, body=None),
    )
    client = LLMClient(settings=Settings(openai_api_key="k"), client=fake)  # type: ignore[arg-type]

    # 재시도 대상이 아니므로 즉시 실패하되, 폴백 경로가 잡을 수 있도록
    # LLMUnavailableError로 감싸져야 한다 (SingleAgent는 원본 OpenAIError를 모른다).
    with pytest.raises(LLMUnavailableError):
        asyncio.run(client.generate("system", "user"))

    assert len(fake.chat.completions.calls) == 1


@pytest.mark.parametrize("content", [None, ""])
def test_generate_raises_for_empty_content(content: str | None) -> None:
    fake = FakeOpenAI(content=content)
    client = LLMClient(settings=Settings(openai_api_key="k"), client=fake)  # type: ignore[arg-type]

    with pytest.raises(LLMUnavailableError, match="content가 비어"):
        asyncio.run(client.generate("system", "user"))


def test_generate_without_key_raises_not_configured() -> None:
    client = LLMClient(settings=Settings(openai_api_key=None))

    with pytest.raises(LLMNotConfiguredError):
        asyncio.run(client.generate("system", "user"))


def test_generate_json_returns_object_with_deterministic_options() -> None:
    fake = FakeOpenAI(content='{"purpose": "충동", "companion": "혼자"}')
    settings = Settings(openai_api_key="k")
    client = LLMClient(settings=settings, client=fake)  # type: ignore[arg-type]

    result = asyncio.run(client.generate_json("system", "user"))

    assert result == {"purpose": "충동", "companion": "혼자"}
    request = fake.chat.completions.calls[0]
    assert request["response_format"] == {"type": "json_object"}
    assert request["temperature"] == 0
    assert request["timeout"] == settings.llm_timeout_seconds


def test_generate_json_raises_for_invalid_json() -> None:
    fake = FakeOpenAI(content="JSON 아님")
    client = LLMClient(settings=Settings(openai_api_key="k"), client=fake)  # type: ignore[arg-type]

    with pytest.raises(LLMUnavailableError):
        asyncio.run(client.generate_json("system", "user"))


def test_generate_json_raises_for_non_object_json() -> None:
    fake = FakeOpenAI(content='["충동", "혼자"]')
    client = LLMClient(settings=Settings(openai_api_key="k"), client=fake)  # type: ignore[arg-type]

    with pytest.raises(LLMUnavailableError):
        asyncio.run(client.generate_json("system", "user"))


def test_generate_json_retries_once_then_raises() -> None:
    fake = FakeOpenAI(failures_before_success=2)
    client = LLMClient(settings=Settings(openai_api_key="k"), client=fake)  # type: ignore[arg-type]

    with pytest.raises(LLMUnavailableError):
        asyncio.run(client.generate_json("system", "user"))

    assert len(fake.chat.completions.calls) == 2
