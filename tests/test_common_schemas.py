"""공통 스키마 회귀 테스트 — TaskType 6종 (05 §3 · E-47)."""

from app.agent.state import AgentState
from app.schemas.chat import ChatMessage, ChatRequest
from app.schemas.common import TaskType


def test_task_type_has_six_members_including_finance_qa() -> None:
    assert TaskType.FINANCE_QA == "FINANCE_QA"
    assert len(TaskType) == 6


def test_agent_state_parses_finance_qa_task() -> None:
    request = ChatRequest(
        message="예금자보호는 얼마까지 되나요",
        task_context={"task": "FINANCE_QA", "status": "ACTIVE", "state": {}},
    )

    state = AgentState.from_request(request)

    assert state.task is TaskType.FINANCE_QA


def test_agent_state_last_question_returns_latest_assistant_message() -> None:
    state = AgentState(
        message="응",
        recent_messages=[
            ChatMessage(role="assistant", content="이 소비는 계획한 소비였나요?"),
            ChatMessage(role="user", content="아니"),
            ChatMessage(role="assistant", content="누구와 함께했나요?"),
            ChatMessage(role="user", content="혼자"),
        ],
    )

    assert state.last_question == "누구와 함께했나요?"


def test_agent_state_last_question_is_empty_without_assistant_message() -> None:
    state = AgentState(
        message="이 소비를 돌아볼래",
        recent_messages=[ChatMessage(role="user", content="안녕")],
    )

    assert state.last_question == ""
