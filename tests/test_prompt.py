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
    assert "사용자의 소비를 부정적으로 단정하지 않습니다." in SYSTEM_PROMPT
    assert "사용자에게 '후회'를 유도하는 언어를 사용하지 않습니다." in SYSTEM_PROMPT
    assert "'탈락', '아웃', 'Out'처럼 소비를 판결하는 어휘" in SYSTEM_PROMPT


def test_system_prompt_few_shot_examples_are_short_haeyo_style() -> None:
    examples = [
        "이번 달 식비는 계획한 금액 안으로 확인돼요. 배달 소비는 지난달보다 늘어난 것으로 나와요.",
        "확인된 근거가 없어 지금은 소비 흐름을 설명하기 어려워요.",
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
    ("has_task", "has_instruction"),
    list(product([False, True], repeat=2)),
)
def test_build_system_prompt_context_combinations(
    has_task: bool,
    has_instruction: bool,
) -> None:
    instruction = "JSON object로 응답하세요."
    state = AgentState(
        message="혼자였어",
        task=TaskType.REFLECTION if has_task else None,
        structured_state={"step": "COMPANION"},
    )

    prompt = build_system_prompt(state, instruction if has_instruction else "")

    assert ("현재 작업: REFLECTION" in prompt) is has_task
    assert ('현재 상태(JSON): {"step": "COMPANION"}' in prompt) is has_task
    assert (instruction in prompt) is has_instruction

    included_sections = [
        section
        for condition, section in [
            (has_task, "현재 작업: REFLECTION"),
            (has_task, '현재 상태(JSON): {"step": "COMPANION"}'),
            (has_instruction, instruction),
        ]
        if condition
    ]
    assert [prompt.index(section) for section in included_sections] == sorted(
        prompt.index(section) for section in included_sections
    )

    if not any((has_task, has_instruction)):
        assert prompt == SYSTEM_PROMPT


def test_build_system_prompt_never_embeds_recent_messages() -> None:
    """`recent_messages`는 `messages` 배열 자리로 옮겼다 — 시스템 프롬프트 문자열에는

    더 이상 섞이지 않는다 (#80). 한 덩어리 문자열로 섞으면 "사용자가 말한 것"과
    "내가 말한 것"의 구분이 사라지고, 지시문 뒤 텍스트가 문체 규칙을 밀어내는
    함정(§12 · §13 · §17)이 하나 더 생긴다.
    """

    state_with_history = AgentState(
        message="그럼 한도는요?",
        recent_messages=[
            ChatMessage(role="assistant", content="예금자 보호는 5천만원까지예요."),
            ChatMessage(role="user", content="적금도 해당되나요?"),
        ],
    )
    state_without_history = AgentState(message="그럼 한도는요?")

    assert build_system_prompt(state_with_history) == build_system_prompt(
        state_without_history
    )
    assert "직전 assistant" not in build_system_prompt(state_with_history)
    assert "5천만원" not in build_system_prompt(state_with_history)


def test_build_system_prompt_preserves_existing_task_prompt() -> None:
    state = AgentState(
        message="계속할게",
        task=TaskType.REFLECTION,
        structured_state={"step": "PURPOSE"},
    )

    assert build_system_prompt(state) == (
        f'{SYSTEM_PROMPT}\n현재 작업: REFLECTION\n현재 상태(JSON): {{"step": "PURPOSE"}}\n'
    )
