"""공통 스키마 회귀 테스트 — TaskType 6종 (05 §3 · E-47)."""

from app.agent.state import AgentState
from app.schemas.chat import ChatRequest
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
