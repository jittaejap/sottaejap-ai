"""Single Agent 기본 계약 테스트."""

import asyncio

from app.agent.agent import SingleAgent
from app.schemas.chat import ChatRequest, ChatResponse


def test_agent_returns_chat_response() -> None:
    response = asyncio.run(SingleAgent().run(ChatRequest(message="이번 소비를 돌아볼래")))

    assert isinstance(response, ChatResponse)
    assert response.reply
    assert response.tool_results == []


def test_agent_accepts_current_task_context() -> None:
    response = asyncio.run(
        SingleAgent().run(
            ChatRequest(
                message="계속할게",
                task_context={"task": "REFLECTION", "status": "ACTIVE", "state": {}},
            )
        )
    )

    assert "REFLECTION" in response.reply

