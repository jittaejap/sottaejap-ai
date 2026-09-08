"""시스템 프롬프트의 맥락 조립 순서를 확인한다."""

from itertools import product

import pytest

from app.agent.prompt import SYSTEM_PROMPT, build_system_prompt
from app.agent.state import AgentState
from app.schemas.chat import ChatMessage
from app.schemas.common import TaskType


def test_system_prompt_follows_service_tone_rules() -> None:
    assert "해요체" in SYSTEM_PROMPT
    assert "반말, 격식체, 이모지는 사용하지 않습니다." in SYSTEM_PROMPT
    assert "한두 문장의 한 문단" in SYSTEM_PROMPT
    assert "지킬 만한 소비가 있으면 그것부터 먼저" in SYSTEM_PROMPT
    assert all(word not in SYSTEM_PROMPT for word in ("후회", "탈락", "아웃"))


def test_system_prompt_few_shot_examples_are_short_haeyo_style() -> None:
    examples = [
        "계획한 식비는 잘 지키고 있어요. 잦아진 배달 소비는 조금씩 조정해 볼 수 있어요.",
        "확인된 근거 안에서 소비 흐름을 짧게 설명해 드릴게요.",
    ]

    for example in examples:
        assert f'- "{example}"' in SYSTEM_PROMPT
        sentences = [
            sentence.strip()
            for sentence in example.removesuffix(".").split(".")
            if sentence.strip()
        ]
        assert 1 <= len(sentences) <= 2
        assert all(sentence.endswith("요") for sentence in sentences)


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
