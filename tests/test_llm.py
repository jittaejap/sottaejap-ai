"""LLMClient의 텍스트·JSON 응답과 공통 재시도 정책을 확인한다."""

import asyncio
from types import SimpleNamespace

import httpx
import pytest
from openai import APITimeoutError

from app.core.config import Settings
from app.core.llm import LLMClient, LLMNotConfiguredError, LLMUnavailableError


class FakeCompletions:
    def __init__(self, content: str = "LLM 응답", fails: bool = False) -> None:
        self.content = content
        self.fails = fails
        self.calls: list[dict[str, object]] = []

    async def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        if self.fails:
            raise APITimeoutError(request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"))
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self.content))])


class FakeOpenAI:
    def __init__(self, content: str = "LLM 응답", fails: bool = False) -> None:
        self.chat = type("Chat", (), {})()
        self.chat.completions = FakeCompletions(content=content, fails=fails)


def test_generate_returns_text_response() -> None:
    fake = FakeOpenAI(content="텍스트 응답")
    client = LLMClient(settings=Settings(openai_api_key="k"), client=fake)  # type: ignore[arg-type]

    result = asyncio.run(client.generate("system", "user"))

    assert result == "텍스트 응답"
    assert "response_format" not in fake.chat.completions.calls[0]
    assert "temperature" not in fake.chat.completions.calls[0]


def test_generate_retries_once_then_raises() -> None:
    fake = FakeOpenAI(fails=True)
    client = LLMClient(settings=Settings(openai_api_key="k"), client=fake)  # type: ignore[arg-type]

    with pytest.raises(LLMUnavailableError):
        asyncio.run(client.generate("system", "user"))

    assert len(fake.chat.completions.calls) == 2


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
    fake = FakeOpenAI(fails=True)
    client = LLMClient(settings=Settings(openai_api_key="k"), client=fake)  # type: ignore[arg-type]

    with pytest.raises(LLMUnavailableError):
        asyncio.run(client.generate_json("system", "user"))

    assert len(fake.chat.completions.calls) == 2
