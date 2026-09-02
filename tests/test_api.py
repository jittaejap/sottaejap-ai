"""FastAPI Endpoint 연결과 X-Internal-Secret 검사 테스트."""

import asyncio

import httpx

from app.agent.agent import SingleAgent
from app.api.chat import get_agent
from app.main import app
from tests.conftest import TEST_SECRET
from tests.test_agent import FakeLLM


async def request(method: str, path: str, **kwargs: object) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.request(method, path, **kwargs)


def test_health_is_open() -> None:
    response = asyncio.run(request("GET", "/health"))

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_chat_requires_internal_secret() -> None:
    missing = asyncio.run(request("POST", "/chat", json={"message": "안녕하세요"}))
    wrong = asyncio.run(
        request("POST", "/chat", json={"message": "안녕하세요"}, headers={"X-Internal-Secret": "nope"})
    )

    assert missing.status_code == 401
    assert wrong.status_code == 401
    assert missing.json()["detail"]["code"] == "UNAUTHORIZED"


def test_chat_with_secret_returns_reply_and_fallback_flag() -> None:
    app.dependency_overrides[get_agent] = lambda: SingleAgent(llm_client=FakeLLM())  # type: ignore[arg-type]
    try:
        response = asyncio.run(
            request(
                "POST",
                "/chat",
                json={"message": "안녕하세요", "user_id": "1"},
                headers={"X-Internal-Secret": TEST_SECRET},
            )
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["reply"] == "LLM 응답"
    assert body["fallback"] is False
    assert body["tool_results"] == []
