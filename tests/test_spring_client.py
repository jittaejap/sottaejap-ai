"""SpringClient가 05 §3 경로 · 헤더 · 봉투 규칙을 지키는지 MockTransport로 확인한다."""

import asyncio
import json

import httpx
import pytest

from app.clients.spring_client import SpringApiError, SpringClient
from app.core.config import Settings

SETTINGS = Settings(spring_base_url="http://spring", internal_shared_secret="s3cret")


def make_client(handler) -> SpringClient:
    http = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url=SETTINGS.spring_base_url,
        headers={"X-Internal-Secret": SETTINGS.internal_shared_secret or ""},
    )
    return SpringClient(settings=SETTINGS, http_client=http)


def test_paths_and_header_follow_spec() -> None:
    seen: list[tuple[str, str, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.raw_path.decode(), request.headers.get("X-Internal-Secret")))
        return httpx.Response(200, json={"success": True, "data": {"ok": True}})

    async def run() -> None:
        async with make_client(handler) as client:
            await client.get_transactions("7", {"from": "2026-08-01", "size": 5})
            await client.get_reflections("7")
            await client.save_reflection("7", {"transaction_id": 1, "satisfaction": "HIGH"})
            await client.get_behavior_analysis("7")
            await client.get_action_plan("7")
            await client.get_memory("7")

    asyncio.run(run())

    assert [s[:2] for s in seen] == [
        ("GET", "/internal/ai/users/7/transactions?from=2026-08-01&size=5"),
        ("GET", "/internal/ai/users/7/reflections"),
        ("POST", "/internal/ai/users/7/reflections"),
        ("GET", "/internal/ai/users/7/analysis"),
        ("GET", "/internal/ai/users/7/suggestions"),
        ("GET", "/internal/ai/users/7/memory"),
    ]
    assert all(s[2] == "s3cret" for s in seen)


def test_save_reflection_sends_snake_case_json_body() -> None:
    bodies: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"success": True, "data": {"id": 1}})

    async def run() -> dict:
        async with make_client(handler) as client:
            return await client.save_reflection("7", {"transaction_id": 1, "repeat_intention": False})

    assert asyncio.run(run()) == {"id": 1}
    assert bodies == [{"transaction_id": 1, "repeat_intention": False}]


def test_envelope_is_unwrapped_and_errors_raise() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/memory"):
            return httpx.Response(
                200, json={"success": False, "error": {"code": "NOT_FOUND_USER", "message": "없음"}}
            )
        return httpx.Response(200, json={"success": True, "data": {"transactions": []}})

    async def run() -> None:
        async with make_client(handler) as client:
            assert await client.get_transactions("7") == {"transactions": []}
            with pytest.raises(SpringApiError) as exc:
                await client.get_memory("7")
            assert exc.value.code == "NOT_FOUND_USER"

    asyncio.run(run())


def test_http_error_propagates() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"success": False, "error": {"code": "UNAUTHORIZED", "message": ""}})

    async def run() -> None:
        async with make_client(handler) as client:
            with pytest.raises(httpx.HTTPStatusError):
                await client.get_reflections("7")

    asyncio.run(run())
