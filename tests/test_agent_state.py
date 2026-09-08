"""AgentState의 최근 대화 접근자 테스트."""

from app.agent.state import AgentState
from app.schemas.chat import ChatMessage


def test_last_question_returns_latest_assistant_message() -> None:
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


def test_last_question_is_empty_without_assistant_message() -> None:
    state = AgentState(
        message="이 소비를 돌아볼래",
        recent_messages=[ChatMessage(role="user", content="안녕")],
    )

    assert state.last_question == ""


def test_last_question_is_empty_when_recent_messages_are_empty() -> None:
    assert AgentState(message="이 소비를 돌아볼래").last_question == ""
