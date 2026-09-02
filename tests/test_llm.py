"""LLMClient가 타임아웃·오류를 재시도 1회 후 LLMUnavailableError로 올리는지 확인한다."""

import asyncio

import httpx
import pytest
from openai import APITimeoutError

from app.core.config import Settings
from app.core.llm import LLMClient, LLMNotConfiguredError, LLMUnavailableError


class FakeCompletions:
    def __init__(self) -> None:
        self.calls = 0

    async def create(self, **_: object) -> object:
        self.calls += 1
        raise APITimeoutError(request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"))


class FakeOpenAI:
    def __init__(self) -> None:
        self.chat = type("Chat", (), {})()
        self.chat.completions = FakeCompletions()


def test_generate_retries_once_then_raises() -> None:
    fake = FakeOpenAI()
    client = LLMClient(settings=Settings(openai_api_key="k"), client=fake)  # type: ignore[arg-type]

    with pytest.raises(LLMUnavailableError):
        asyncio.run(client.generate("system", "user"))

    assert fake.chat.completions.calls == 2


def test_generate_without_key_raises_not_configured() -> None:
    client = LLMClient(settings=Settings(openai_api_key=None))

    with pytest.raises(LLMNotConfiguredError):
        asyncio.run(client.generate("system", "user"))
