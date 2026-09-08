"""테스트 공통 설정. 외부 서비스(OpenAI · Spring · DB)를 호출하지 않는다."""

from collections.abc import Callable

import httpx
import pytest

from app.clients.spring_client import SpringClient
from app.core.config import Settings, get_settings
from app.core.llm import LLMUnavailableError

TEST_SECRET = "test-shared-secret"
HttpHandler = Callable[[httpx.Request], httpx.Response]
SpringClientFactory = Callable[[HttpHandler], SpringClient]


class FakeLLM:
    """응답·실패 시뮬레이션과 호출 기록을 제공하는 공통 LLM Fake."""

    def __init__(self, reply: str | None = "LLM 응답") -> None:
        self.reply = reply
        self.prompts: list[str] = []
        self.calls: list[tuple[str, str]] = []
        self.temperatures: list[float | None] = []

    async def generate(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float | None = None,
    ) -> str:
        self.prompts.append(system_prompt)
        self.calls.append((system_prompt, user_message))
        self.temperatures.append(temperature)
        if self.reply is None:
            raise LLMUnavailableError("timeout")
        return self.reply


@pytest.fixture
def fake_llm() -> FakeLLM:
    """테스트마다 호출 기록이 분리된 FakeLLM을 제공한다."""

    return FakeLLM()


@pytest.fixture
def make_client() -> SpringClientFactory:
    """MockTransport handler로 격리된 SpringClient를 만든다."""

    settings = Settings(
        spring_base_url="http://spring",
        internal_shared_secret="s3cret",
    )

    def factory(handler: HttpHandler) -> SpringClient:
        http_client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url=settings.spring_base_url,
            headers={"X-Internal-Secret": settings.internal_shared_secret or ""},
        )
        return SpringClient(settings=settings, http_client=http_client)

    return factory


@pytest.fixture(autouse=True)
def test_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    """로컬 .env와 무관하게 고정된 설정으로 테스트한다."""

    monkeypatch.setenv("INTERNAL_SHARED_SECRET", TEST_SECRET)
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "0.1")
    get_settings.cache_clear()
    settings = get_settings()
    yield settings
    get_settings.cache_clear()
