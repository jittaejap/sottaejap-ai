"""추출 프롬프트의 규칙이 살아 있는지 확인한다 (A6 · #39).

여기 있는 규칙은 전부 **실측으로 필요가 확인된 것**이다. `scripts/eval_reflection_extraction.py`를
실제 LLM으로 돌려 과잉추론이나 과소추출이 나온 자리에만 넣었고, 지웠을 때 다시 나빠지는 것을
확인했다 (`docs/DEVELOPMENT.md` §11).

그 평가 스크립트는 `OPENAI_API_KEY`가 있어야 돌아서 CI가 지켜주지 못한다. 그래서 **규칙이
문자열에서 사라지지 않았는지**를 여기서 못박는다. `tests/test_rag_prompt.py`가 같은 일을 한다.
"""

import pytest

from app.reflection.extractor import _build_prompt
from app.reflection.schemas import Companion, Purpose

PROMPT = _build_prompt("")
WITH_QUESTION = _build_prompt("이 소비, 만족하셨나요?")


@pytest.mark.parametrize("tag", [*Purpose, *Companion])
def test_prompt_lists_every_standard_tag(tag: Purpose | Companion) -> None:
    """표준 태그 13종이 모두 프롬프트에 있어야 목록 밖 값이 덜 나온다 (E-20)."""

    assert tag.value in PROMPT


def test_prompt_keeps_the_null_first_rule() -> None:
    """A6가 태그 힌트를 넣어도 A4의 '애매하면 null' 원칙은 그대로 남아야 한다.

    이 문장이 빠지면 태그 구분 규칙만 남아 모델이 무엇이든 분류하려 든다.
    """

    assert "애매하면 null" in PROMPT
    assert "추론하지 말고" in PROMPT


def test_prompt_forbids_other_as_dont_know() -> None:
    """"기타"는 표준 태그 밖 값을 말했을 때지, 모르겠다는 뜻이 아니다.

    실측: 목적 구분 규칙을 넣자 "편의점에 잠깐 들렀어요"에 `purpose="기타"`가 나왔다.
    아래 두 문장을 함께 넣은 뒤 사라졌다.
    """

    assert '모르겠다는 뜻으로 "기타"를 쓰지 않습니다' in PROMPT
    assert '고르기 어렵다고 "기타"를 쓰지 않습니다' in PROMPT


def test_prompt_separates_satisfaction_from_next_action() -> None:
    """다음 행동을 말한 문장에서 만족도를 짐작하면 만족도 지도가 틀어진다.

    실측: 기준선에서 "이건 다신 안 살래요"에 `satisfaction="LOW"`가 5회 중 5회 나왔다.
    같은 문장이 `repeat_intention`에는 답이 된다는 점까지 적어야 반대쪽이 죽지 않는다.
    """

    assert "다신 안 살래요" in PROMPT
    assert "repeat_intention이 false" in PROMPT
    assert 'satisfaction은\n  "UNKNOWN"입니다' in PROMPT


def test_prompt_rejects_resolutions_and_regret_as_repeat_intention() -> None:
    """다짐도 후회도 반복 의향의 답이 아니다.

    실측 1: 만족도 가드에 "그만하겠다" 같은 낱말을 예로 들었더니 그 낱말이
    `repeat_intention`으로 새어 "앞으로는 좀 줄여야겠어요"가 false로 찍혔다.
    가드는 항목마다 따로 쓴다.

    실측 2: 목적 태그 판단 기준을 프롬프트에서 빼자(#44 리뷰 2번)
    "세일한다길래 계획에 없던 걸 홧김에 질렀어요"의 `repeat_intention`이 10회 중 6회
    false로 새어 나왔다. 목적이 갈 곳을 잃자 후회하는 말이 옆 항목으로 흘렀다.
    후회 표현을 이 가드에 직접 적어 막았다 — 10회 전부 0건이 됐다. 정본에 없는 태그
    정의를 되살리는 대신, **새는 항목 쪽에** 가드를 둔 것이다.
    """

    assert "줄이겠다" in PROMPT
    assert "홧김에 샀다" in PROMPT
    assert "지난 소비를 후회하는 말은" in PROMPT
    assert "반복 의향의 답이 아니라 null" in PROMPT


def test_prompt_requires_being_together_for_companion() -> None:
    """문장에 사람이 나온다고 동행인이 아니다.

    실측: 기준선에서 "친구가 추천해준 가게였어요"에 `companion="친구"`가 5회 중 5회 나왔다.
    server `nextStep()`은 값이 차 있으면 그 단계를 묻지 않으므로, 지어낸 동행인은
    되묻기 자체를 없앤다 (02 FR-04-08).
    """

    assert "함께 있었다는 말이 없으면 companion은 null" in PROMPT
    assert "추천해 준 사람" in PROMPT


def test_prompt_keeps_the_short_answer_path_alive() -> None:
    """직전 질문에 기대는 짧은 답("아니요")이 살아 있어야 한다.

    실측: repeat 규칙을 "직접 말했을 때만"으로 좁혔더니 직전 질문이 반복 의향을 물은
    상태의 "아니요"가 null로 떨어졌다. 회고는 버튼과 짧은 답으로 진행되는 대화라
    이 경로가 죽으면 정상 흐름이 막힌다.
    """

    assert "직전 질문이 반복 의향을" in PROMPT
    # 이 문구는 넣지 않는다 — 직전 질문 참조를 통째로 막아 짧은 답을 죽였다.
    assert "그 항목을 말한 부분만 보고" not in PROMPT


def test_purpose_rules_are_for_ties_not_new_definitions() -> None:
    """정본(01 §2 · 02 FR-04-04)에 태그 정의가 없으므로 정의가 아니라 구분 규칙만 쓴다.

    "식사란 무엇이다"를 프롬프트가 새로 정하면 근거 없는 해석을 AI가 만드는 것이 된다 (NFR-02).

    헤더에 "둘 이상 걸릴 때"라고 적어도, 발화를 한 태그로 **매핑하는 문장**은 모델에게
    그대로 판단 기준이 된다. 그래서 헤더 문자열만 보지 않고, 매핑 문구가 다시 들어오지
    않았는지도 함께 본다 (#44 리뷰).

    실측에서 필요했다는 사실은 품질 근거이지 정본에 없는 정의를 넣을 권한이 아니다.
    남은 것은 두 태그가 **함께 걸릴 때 어느 쪽을 고르는가**와 null 복귀뿐이다. 태그별
    판단 기준은 정본(01 §2)에 먼저 올린 뒤에 프롬프트가 인용한다.
    """

    assert "목적을 고르는 규칙 (둘 이상 걸릴 때 씁니다)" in PROMPT
    assert "어느 것도 걸리지 않으면 purpose는 null" in PROMPT

    definitions = (
        "즐기거나 쉬려고",
        "배우거나 실력을",
        "없으면 생활이 안 되는",
        "즉흥적으로 샀다고",
    )
    for definition in definitions:
        assert definition not in PROMPT, f"정본에 없는 태그 판단 기준이 들어왔다: {definition}"


def test_last_question_rule_is_appended_only_when_present() -> None:
    """직전 질문 규칙은 질문이 있을 때만 붙는다 (A4 계약 — 회귀 방지)."""

    assert "직전에 시스템이 한 질문" not in PROMPT
    assert "이 소비, 만족하셨나요?" in WITH_QUESTION
    assert "질문 문장에 등장한 값은" in WITH_QUESTION
