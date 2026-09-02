"""회고 DTO의 UNKNOWN/null 및 검증 동작 테스트."""

from app.reflection.normalizer import normalize
from app.reflection.schemas import ReflectionExtraction, Satisfaction
from app.reflection.validator import validate


def test_reflection_allows_unknown_and_null() -> None:
    reflection = ReflectionExtraction()

    assert reflection.purpose is None
    assert reflection.companion is None
    assert reflection.satisfaction == Satisfaction.UNKNOWN
    assert reflection.repeat_intention is None


def test_reflection_normalizes_and_marks_uncertain_fields() -> None:
    reflection = ReflectionExtraction(
        purpose="  야식  ",
        companion="친구",
        satisfaction=Satisfaction.LOW,
    )

    validated = validate(normalize(reflection))

    assert validated.purpose == "야식"
    assert validated.needs_clarification is True
    assert validated.uncertain_fields == ["repeat_intention"]

