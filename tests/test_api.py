"""FastAPI 기본 Endpoint 연결 테스트."""

import asyncio

import httpx

from app.main import app


async def request(method: str, path: str, **kwargs: object) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.request(method, path, **kwargs)


def test_health() -> None:
    response = asyncio.run(request("GET", "/health"))

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_chat() -> None:
    response = asyncio.run(request("POST", "/chat", json={"message": "안녕하세요"}))

    assert response.status_code == 200
    assert response.json()["reply"]
