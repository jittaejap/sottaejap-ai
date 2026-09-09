"""공유 숫자 가드가 한글 단위 표기를 포함해 근거와 대조하는지 확인한다."""

import pytest

from app.agent.handlers.number_guard import has_unverified_number


@pytest.mark.parametrize(
    "sentence",
    [
        "예금자보호 한도는 5천만 원이에요.",
        "예금자보호 한도는 1억 원이에요.",
    ],
)
def test_korean_unit_number_without_evidence_is_rejected(sentence: str) -> None:
    assert has_unverified_number(sentence, set(), known_percentages=set()) is True


@pytest.mark.parametrize(
    ("sentence", "known"),
    [
        ("이번 달 소비는 5천만 원이에요.", {50_000_000.0}),
        ("이번 달 소비는 1억 원이에요.", {100_000_000.0}),
    ],
)
def test_korean_unit_number_with_matching_evidence_passes(
    sentence: str,
    known: set[float],
) -> None:
    assert has_unverified_number(sentence, known, known_percentages=set()) is False


def test_existing_decimal_percent_and_comma_amount_still_pass() -> None:
    assert (
        has_unverified_number(
            "예산의 3.6%이고 12,000원이에요.",
            {12_000.0},
            known_percentages={3.6},
        )
        is False
    )
