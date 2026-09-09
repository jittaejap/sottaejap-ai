"""Single Agent 기본 계약과 LLM 폴백 테스트."""

import asyncio

import pytest

from app.agent.agent import SingleAgent
from app.agent.handlers import HANDLERS
from app.agent.handlers.base import HandlerContext
from app.agent.reply_length import MAX_REPLY_LENGTH
from app.schemas.chat import ChatMessage, ChatRequest, ChatResponse
from app.schemas.common import TaskType
from tests.conftest import FakeLLM


def test_agent_returns_llm_reply_without_fallback(fake_llm: FakeLLM) -> None:
    response = asyncio.run(
        SingleAgent(llm_client=fake_llm).run(  # type: ignore[arg-type]
            ChatRequest(message="이번 소비를 돌아볼래")
        )
    )

    assert isinstance(response, ChatResponse)
    assert response.reply == "LLM 응답"
    assert response.fallback is False
    assert response.tool_results == []


def test_agent_passes_task_context_to_prompt_and_recent_messages_as_history(
    monkeypatch: pytest.MonkeyPatch,
    fake_llm: FakeLLM,
) -> None:
    # Handler가 없는 Task의 일반 경로를 본다. REFLECTION은 Handler가 생겼으므로
    # (A5) 라우팅을 걷어내고 `build_system_prompt` 병합만 확인한다.
    monkeypatch.delitem(HANDLERS, TaskType.REFLECTION)

    asyncio.run(
        SingleAgent(llm_client=fake_llm).run(  # type: ignore[arg-type]
            ChatRequest(
                message="계속할게",
                task_context={"task": "REFLECTION", "status": "ACTIVE", "state": {"step": "PURPOSE"}},
                recent_messages=[
                    ChatMessage(role="assistant", content="이 소비에 만족하셨나요?")
                ],
            )
        )
    )

    assert "REFLECTION" in fake_llm.prompts[0]
    assert "PURPOSE" in fake_llm.prompts[0]
    assert "직전 assistant" not in fake_llm.prompts[0]
    # `recent_messages`는 프롬프트 문자열이 아니라 `history`(→ OpenAI messages)로 간다 (#80).
    assert fake_llm.histories[0] == [
        ChatMessage(role="assistant", content="이 소비에 만족하셨나요?")
    ]


def test_agent_routes_active_task_to_registered_handler(
    monkeypatch: pytest.MonkeyPatch,
    fake_llm: FakeLLM,
) -> None:
    calls: list[str] = []

    async def handler(context: HandlerContext) -> ChatResponse:
        calls.append("handler")
        return ChatResponse(reply="처리기 응답")

    monkeypatch.setitem(HANDLERS, TaskType.REFLECTION, handler)

    response = asyncio.run(
        SingleAgent(llm_client=fake_llm).run(  # type: ignore[arg-type]
            ChatRequest(
                message="계속할게",
                task_context={"task": "REFLECTION", "status": "ACTIVE", "state": {}},
            )
        )
    )

    assert response.reply == "처리기 응답"
    assert calls == ["handler"]


def test_agent_skips_handler_for_completed_task(
    monkeypatch: pytest.MonkeyPatch,
    fake_llm: FakeLLM,
) -> None:
    calls: list[str] = []

    async def handler(context: HandlerContext) -> ChatResponse:
        calls.append("handler")
        return ChatResponse(reply="처리기 응답")

    monkeypatch.setitem(HANDLERS, TaskType.REFLECTION, handler)

    response = asyncio.run(
        SingleAgent(llm_client=fake_llm).run(  # type: ignore[arg-type]
            ChatRequest(
                message="끝났어",
                task_context={"task": "REFLECTION", "status": "COMPLETED", "state": {}},
            )
        )
    )

    assert response.reply == "LLM 응답"
    assert calls == []


def test_agent_handles_llm_failure_from_handler(
    monkeypatch: pytest.MonkeyPatch,
    fake_llm: FakeLLM,
) -> None:
    fake_llm.reply = None

    async def handler(context: HandlerContext) -> ChatResponse:
        return ChatResponse(reply=await context.generate("회고 지시문"))

    monkeypatch.setitem(HANDLERS, TaskType.REFLECTION, handler)

    response = asyncio.run(
        SingleAgent(llm_client=fake_llm).run(  # type: ignore[arg-type]
            ChatRequest(
                message="응",
                task_context={
                    "task": "REFLECTION",
                    "status": "ACTIVE",
                    "state": {"step": "SATISFACTION"},
                },
            )
        )
    )

    assert response.fallback is True
    assert response.reply == "이 소비, 만족하셨나요?"


def test_agent_falls_back_to_template_when_llm_fails(fake_llm: FakeLLM) -> None:
    fake_llm.reply = None

    response = asyncio.run(
        SingleAgent(llm_client=fake_llm).run(  # type: ignore[arg-type]
            ChatRequest(
                message="응",
                task_context={"task": "REFLECTION", "status": "ACTIVE", "state": {"step": "SATISFACTION"}},
            )
        )
    )

    assert response.fallback is True
    assert response.reply == "이 소비, 만족하셨나요?"


def test_agent_falls_back_when_llm_not_configured() -> None:
    response = asyncio.run(SingleAgent().run(ChatRequest(message="안녕")))

    assert response.fallback is True
    assert response.reply


def test_agent_truncates_reply_over_length_cap(fake_llm: FakeLLM) -> None:
    """client가 reply를 이력에 되돌려 보내므로 2,000자를 넘기지 않는다 (E-110 · #55)."""

    fake_llm.reply = "괜찮아요." * 700  # 3,500자, 해요체 문장 경계 다수 포함

    response = asyncio.run(
        SingleAgent(llm_client=fake_llm).run(  # type: ignore[arg-type]
            ChatRequest(message="질문")
        )
    )

    assert len(response.reply) <= MAX_REPLY_LENGTH
    assert response.reply.endswith("요.")


def test_agent_truncates_handler_reply_over_length_cap(
    monkeypatch: pytest.MonkeyPatch,
    fake_llm: FakeLLM,
) -> None:
    """Handler 경로도 같은 상한을 받는다 — Task마다 반복 구현하지 않는다."""

    async def handler(context: HandlerContext) -> ChatResponse:
        return ChatResponse(reply="괜찮아요." * 700)

    monkeypatch.setitem(HANDLERS, TaskType.REFLECTION, handler)

    response = asyncio.run(
        SingleAgent(llm_client=fake_llm).run(  # type: ignore[arg-type]
            ChatRequest(
                message="질문",
                task_context={"task": "REFLECTION", "status": "ACTIVE", "state": {}},
            )
        )
    )

    assert len(response.reply) <= MAX_REPLY_LENGTH
    assert response.reply.endswith("요.")
