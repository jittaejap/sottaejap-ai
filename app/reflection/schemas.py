"""자연어 회고 구조화 결과 DTO.

확인할 수 없는 값은 None 또는 UNKNOWN으로 유지해 사용자 검증이 가능하게 한다.
"""

from enum import StrEnum

from pydantic import BaseModel, Field


class Satisfaction(StrEnum):
    """서비스에서 사용하는 만족도 표준 값."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


class ReflectionExtraction(BaseModel):
    """AI가 제안하고 사용자가 추후 확인할 수 있는 회고 후보."""

    purpose: str | None = None
    companion: str | None = None
    satisfaction: Satisfaction = Satisfaction.UNKNOWN
    repeat_intention: bool | None = None
    needs_clarification: bool = True
    uncertain_fields: list[str] = Field(default_factory=list)

