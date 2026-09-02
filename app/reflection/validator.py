"""구조화된 회고의 미확정 필드를 검증한다.

비즈니스 판정이나 만족도 보정을 하지 않고 추가 질문 필요 여부만 표시한다.
"""

from app.reflection.schemas import ReflectionExtraction, Satisfaction


def validate(extraction: ReflectionExtraction) -> ReflectionExtraction:
    """미확정 항목 목록과 추가 확인 필요 여부를 갱신한다."""

    uncertain_fields: list[str] = []
    if extraction.purpose is None:
        uncertain_fields.append("purpose")
    if extraction.companion is None:
        uncertain_fields.append("companion")
    if extraction.satisfaction == Satisfaction.UNKNOWN:
        uncertain_fields.append("satisfaction")
    if extraction.repeat_intention is None:
        uncertain_fields.append("repeat_intention")

    return extraction.model_copy(
        update={
            "needs_clarification": bool(uncertain_fields),
            "uncertain_fields": uncertain_fields,
        }
    )

