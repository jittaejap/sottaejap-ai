"""평가 도구의 채점과 통과 판정이 두 축을 함께 보는지 확인한다 (A6 · #39).

평가 스크립트 자체는 `OPENAI_API_KEY`가 있어야 돌아 CI가 지켜주지 못한다. 하지만
`grade()`·`report()`·`parse_args()`는 외부를 부르지 않으므로, **판정 규칙이 느슨해지는
회귀**는 여기서 막을 수 있다.

막으려는 회귀는 실제로 한 번 있었다 — 통과 조건이 과잉추론만 봐서, 모델이 모든 항목을
`null`·`UNKNOWN`으로 돌려줘도 종료 코드가 0이었다 (#44 리뷰 1번).
"""

import pytest

from app.reflection.schemas import ReflectionExtraction, Satisfaction
from scripts.eval_reflection_extraction import Case, grade, parse_args, report

NOTHING = ReflectionExtraction()


def test_grade_counts_a_missing_value_as_a_miss() -> None:
    """값이 있어야 하는 항목이 비면 재현율 분자에 들어가지 않는다."""

    result = grade(Case("이 소비는 별로였어요", satisfaction="LOW"), NOTHING)

    assert (result.hits, result.wanted) == (0, 1)
    assert result.misses and not result.over


def test_grade_counts_an_invented_value_as_over_inference() -> None:
    """미확정이어야 하는 항목에 값이 차면 과잉추론 1건이다."""

    result = grade(
        Case("친구가 추천해준 가게였어요"),
        ReflectionExtraction(satisfaction=Satisfaction.LOW),
    )

    assert result.over == ["satisfaction='LOW'"]
    assert result.wanted == 0


def test_report_fails_when_recall_is_short() -> None:
    """과잉추론이 0이어도 재현율이 미달이면 실패다.

    이것이 #44 리뷰가 잡은 구멍이다. 모델이 전부 null로 답하는 것은 "지어내지 않았다"가
    아니라 "아무것도 못 뽑았다"이고, 이슈 #39의 완료 조건은 두 축을 함께 요구한다.
    """

    short = grade(Case("이 소비는 별로였어요", satisfaction="LOW"), NOTHING)

    assert report([short], [], 0.0) is False


def test_report_fails_on_over_inference_and_on_call_errors() -> None:
    """나머지 두 축도 그대로 실패로 남는다 (회귀 방지)."""

    invented = grade(
        Case("친구가 추천해준 가게였어요"),
        ReflectionExtraction(satisfaction=Satisfaction.LOW),
    )
    clean = grade(Case("이 소비는 별로였어요", satisfaction="LOW"), ReflectionExtraction(satisfaction=Satisfaction.LOW))

    assert report([invented], [], 0.0) is False
    assert report([clean], [RuntimeError("timeout")], 0.0) is False


def test_report_passes_only_when_all_three_hold() -> None:
    """재현율 전건 · 과잉추론 0 · 오류 0이 모두 성립할 때만 통과다."""

    hit = grade(
        Case("혼자 밥 먹었어요", purpose="식사", companion="혼자"),
        ReflectionExtraction(purpose="식사", companion="혼자"),
    )

    assert report([hit], [], 0.0) is True


def test_repeat_must_run_at_least_once() -> None:
    """`--repeat 0`은 한 문장도 재지 않고 성공으로 끝나므로 인자 단계에서 막는다."""

    assert parse_args(["--repeat", "3"]).repeat == 3
    with pytest.raises(SystemExit):
        parse_args(["--repeat", "0"])
