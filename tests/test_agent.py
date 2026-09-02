"""Single Agent 기본 계약과 LLM 폴백 테스트."""

import asyncio

from app.agent.agent import SingleAgent
from app.core.llm import LLMUnavailableError
from app.schemas.chat import ChatRequest, ChatResponse


class FakeLLM:
    def __init__(self, reply: str | None = "LLM 응답") -> None:
        self.reply = reply
        self.prompts: list[str] = []

    async def generate(self, system_prompt: str, user_message: str) -> str:
        self.prompts.append(system_prompt)
        if self.reply is None:
            raise LLMUnavailableError("timeout")
        return self.reply


def test_agent_returns_llm_reply_without_fallback() -> None:
    llm = FakeLLM()
    response = asyncio.run(
        SingleAgent(llm_client=llm).run(ChatRequest(message="이번 소비를 돌아볼래"))  # type: ignore[arg-type]
    )

    assert isinstance(response, ChatResponse)
    assert response.reply == "LLM 응답"
    assert response.fallback is False
    assert response.tool_results == []


def test_agent_passes_task_context_to_prompt() -> None:
    llm = FakeLLM()
    asyncio.run(
        SingleAgent(llm_client=llm).run(  # type: ignore[arg-type]
            ChatRequest(
                message="계속할게",
                task_context={"task": "REFLECTION", "status": "ACTIVE", "state": {"step": "PURPOSE"}},
            )
        )
    )

    assert "REFLECTION" in llm.prompts[0]
    assert "PURPOSE" in llm.prompts[0]


def test_agent_falls_back_to_template_when_llm_fails() -> None:
    response = asyncio.run(
        SingleAgent(llm_client=FakeLLM(reply=None)).run(  # type: ignore[arg-type]
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
