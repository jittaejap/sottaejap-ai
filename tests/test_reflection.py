"""회고 DTO의 표준 태그 · UNKNOWN/null · 검증 동작 테스트."""

import pytest
from pydantic import ValidationError

from app.reflection.normalizer import normalize_companion, normalize_purpose
from app.reflection.schemas import Companion, Purpose, ReflectionExtraction, Satisfaction
from app.reflection.validator import validate


def test_reflection_allows_unknown_and_null() -> None:
    reflection = ReflectionExtraction()

    assert reflection.purpose is None
    assert reflection.companion is None
    assert reflection.satisfaction == Satisfaction.UNKNOWN
    assert reflection.repeat_intention is None


def test_satisfaction_has_three_values() -> None:
    assert [s.value for s in Satisfaction] == ["HIGH", "LOW", "UNKNOWN"]


def test_standard_tags_match_decision_log() -> None:
    assert [p.value for p in Purpose] == ["식사", "만남·사교", "휴식·취미", "필수품", "자기계발", "충동", "기타"]
    assert [c.value for c in Companion] == ["혼자", "친구", "가족", "연인", "동료", "기타"]


def test_reflection_rejects_free_text_tags() -> None:
    with pytest.raises(ValidationError):
        ReflectionExtraction(purpose="야식")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        ReflectionExtraction(satisfaction="MEDIUM")  # type: ignore[arg-type]


def test_normalizer_maps_only_standard_tags() -> None:
    assert normalize_purpose("  충동 ") == Purpose.IMPULSE
    assert normalize_purpose("만남 · 사교") == Purpose.SOCIAL
    assert normalize_purpose("야식") is None
    assert normalize_companion("혼자") == Companion.ALONE
    assert normalize_companion(None) is None


def test_validator_marks_uncertain_fields() -> None:
    reflection = ReflectionExtraction(
        purpose=Purpose.MEAL,
        companion=Companion.FRIEND,
        satisfaction=Satisfaction.LOW,
    )

    validated = validate(reflection)

    assert validated.needs_clarification is True
    assert validated.uncertain_fields == ["repeat_intention"]
