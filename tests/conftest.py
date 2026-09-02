"""테스트 공통 설정. 외부 서비스(OpenAI · Spring · DB)를 호출하지 않는다."""

import pytest

from app.core.config import Settings, get_settings

TEST_SECRET = "test-shared-secret"


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
