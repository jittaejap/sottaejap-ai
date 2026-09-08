"""시스템 프롬프트의 맥락 조립 순서를 확인한다."""

from itertools import product

import pytest

from app.agent.prompt import SYSTEM_PROMPT, build_system_prompt
from app.agent.state import AgentState
from app.schemas.chat import ChatMessage
from app.schemas.common import TaskType


@pytest.mark.parametrize(
    ("has_task", "has_last_question", "has_instruction"),
    list(product([False, True], repeat=3)),
)
def test_build_system_prompt_context_combinations(
    has_task: bool,
    has_last_question: bool,
    has_instruction: bool,
) -> None:
    last_question = "누구와 함께했나요?"
    instruction = "JSON object로 응답하세요."
    state = AgentState(
        message="혼자였어",
        task=TaskType.REFLECTION if has_task else None,
        structured_state={"step": "COMPANION"},
        recent_messages=(
            [ChatMessage(role="assistant", content=last_question)]
            if has_last_question
            else []
        ),
    )

    prompt = build_system_prompt(state, instruction if has_instruction else "")

    assert ("현재 작업: REFLECTION" in prompt) is has_task
    assert ('현재 상태(JSON): {"step": "COMPANION"}' in prompt) is has_task
    last_message_section = f'직전 assistant 발화: "{last_question}"'
    assert (last_message_section in prompt) is has_last_question
    assert (instruction in prompt) is has_instruction

    included_sections = [
        section
        for condition, section in [
            (has_task, "현재 작업: REFLECTION"),
            (has_task, '현재 상태(JSON): {"step": "COMPANION"}'),
            (has_last_question, last_message_section),
            (has_instruction, instruction),
        ]
        if condition
    ]
    assert [prompt.index(section) for section in included_sections] == sorted(
        prompt.index(section) for section in included_sections
    )

    if not any((has_task, has_last_question, has_instruction)):
        assert prompt == SYSTEM_PROMPT


def test_build_system_prompt_preserves_existing_task_prompt() -> None:
    state = AgentState(
        message="계속할게",
        task=TaskType.REFLECTION,
        structured_state={"step": "PURPOSE"},
    )

    assert build_system_prompt(state) == (
        f'{SYSTEM_PROMPT}\n현재 작업: REFLECTION\n현재 상태(JSON): {{"step": "PURPOSE"}}\n'
    )


def test_build_system_prompt_separates_multiline_assistant_message() -> None:
    state = AgentState(
        message="답변",
        recent_messages=[
            ChatMessage(role="assistant", content="첫 줄 질문\n둘째 줄 질문")
        ],
    )

    prompt = build_system_prompt(state, "Task별 지시문")

    assert '직전 assistant 발화: "첫 줄 질문 둘째 줄 질문"\nTask별 지시문\n' in prompt
