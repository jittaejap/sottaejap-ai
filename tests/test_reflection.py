"""회고 DTO의 표준 태그 · UNKNOWN/null · 검증 · 자연어 추출 테스트."""

import asyncio

import pytest
from pydantic import ValidationError

from app.core.llm import LLMUnavailableError
from app.reflection.extractor import ReflectionExtractor
from app.reflection.normalizer import normalize_companion, normalize_purpose
from app.reflection.schemas import Companion, Purpose, ReflectionExtraction, Satisfaction
from app.reflection.validator import validate
from tests.conftest import FakeLLM


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


def test_extractor_reads_values_and_ack_in_one_call() -> None:
    llm = FakeLLM(
        json_reply={
            "purpose": "충동",
            "companion": "혼자",
            "satisfaction": "LOW",
            "repeat_intention": False,
            "ack": "배가 고프면 그럴 수 있어요.",
        }
    )
    extractor = ReflectionExtractor(llm_client=llm)  # type: ignore[arg-type]

    turn = asyncio.run(extractor.extract("그냥 배고파서 혼자 시켰어요"))

    assert len(llm.calls) == 1
    assert turn.extraction.purpose is Purpose.IMPULSE
    assert turn.extraction.companion is Companion.ALONE
    assert turn.extraction.satisfaction is Satisfaction.LOW
    assert turn.extraction.repeat_intention is False
    assert turn.extraction.needs_clarification is False
    assert turn.ack == "배가 고프면 그럴 수 있어요."


def test_extractor_drops_values_outside_standard_tags() -> None:
    llm = FakeLLM(
        json_reply={
            "purpose": "야식",
            "companion": "직장 동료들",
            "satisfaction": "MEDIUM",
            "repeat_intention": "true",
        }
    )
    extractor = ReflectionExtractor(llm_client=llm)  # type: ignore[arg-type]

    turn = asyncio.run(extractor.extract("어제 야식 먹었어요"))

    assert turn.extraction.purpose is None
    assert turn.extraction.companion is None
    assert turn.extraction.satisfaction is Satisfaction.UNKNOWN
    assert turn.extraction.repeat_intention is None
    assert turn.extraction.uncertain_fields == [
        "purpose",
        "companion",
        "satisfaction",
        "repeat_intention",
    ]
    assert turn.ack == ""


def test_extractor_uses_last_question_without_leaking_its_values() -> None:
    llm = FakeLLM(json_reply={"satisfaction": "LOW"})
    extractor = ReflectionExtractor(llm_client=llm)  # type: ignore[arg-type]

    turn = asyncio.run(
        extractor.extract(
            "별로였어요",
            last_question="혼자 드신 충동 소비로\n보이는데, 맞을까요?",
        )
    )

    prompt = llm.prompts[0]
    assert "혼자 드신 충동 소비로 보이는데, 맞을까요?" in prompt
    assert "질문 문장에 등장한 값은" in prompt
    assert turn.extraction.purpose is None
    assert turn.extraction.companion is None
    assert turn.extraction.satisfaction is Satisfaction.LOW


def test_extractor_prompt_lists_standard_tags_and_asks_for_json() -> None:
    llm = FakeLLM(json_reply={})
    extractor = ReflectionExtractor(llm_client=llm)  # type: ignore[arg-type]

    asyncio.run(extractor.extract("음"))

    prompt = llm.prompts[0]
    assert "JSON" in prompt
    for tag in list(Purpose) + list(Companion):
        assert f'"{tag.value}"' in prompt
    assert "MEDIUM" not in prompt


def test_extractor_rejects_empty_text_before_calling_llm() -> None:
    llm = FakeLLM(json_reply={})
    extractor = ReflectionExtractor(llm_client=llm)  # type: ignore[arg-type]

    with pytest.raises(ValueError):
        asyncio.run(extractor.extract("   "))

    assert llm.calls == []


def test_extractor_does_not_swallow_llm_failure() -> None:
    extractor = ReflectionExtractor(llm_client=FakeLLM(json_reply=None))  # type: ignore[arg-type]

    with pytest.raises(LLMUnavailableError):
        asyncio.run(extractor.extract("혼자 먹었어요"))
