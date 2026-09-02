"""자연어 회고 구조화 결과 DTO.

확인할 수 없는 값은 None 또는 UNKNOWN으로 유지해 사용자 검증이 가능하게 한다.
purpose·companion은 표준 태그(05 §2 · E-20)만 허용한다. 자유 문자열은 검증 단계에서 거부한다.
"""

from enum import StrEnum

from pydantic import BaseModel, Field


class Satisfaction(StrEnum):
    """서비스에서 사용하는 만족도 표준 값 (E-23 — 3택)."""

    HIGH = "HIGH"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


class Purpose(StrEnum):
    """소비 목적 표준 태그 7종 (01 결정로그 §2 · 02 FR-04-04)."""

    MEAL = "식사"
    SOCIAL = "만남·사교"
    LEISURE = "휴식·취미"
    NECESSITY = "필수품"
    SELF_IMPROVEMENT = "자기계발"
    IMPULSE = "충동"
    OTHER = "기타"


class Companion(StrEnum):
    """동행인 표준 태그 6종 (01 결정로그 §2 · 02 FR-04-05)."""

    ALONE = "혼자"
    FRIEND = "친구"
    FAMILY = "가족"
    PARTNER = "연인"
    COLLEAGUE = "동료"
    OTHER = "기타"


class ReflectionExtraction(BaseModel):
    """AI가 제안하고 사용자가 추후 확인할 수 있는 회고 후보."""

    purpose: Purpose | None = None
    companion: Companion | None = None
    satisfaction: Satisfaction = Satisfaction.UNKNOWN
    repeat_intention: bool | None = None
    needs_clarification: bool = True
    uncertain_fields: list[str] = Field(default_factory=list)
