"""회고 자유입력을 서비스 표준 값으로 정규화한다.

새로운 사실을 추론하지 않고 공백·대소문자 같은 표현 차이만 다룬다.
"""

from app.reflection.schemas import ReflectionExtraction, Satisfaction


def normalize(extraction: ReflectionExtraction) -> ReflectionExtraction:
    """명시된 후보 값을 저장 가능한 일관된 표현으로 바꾼다."""

    purpose = _clean_optional_text(extraction.purpose)
    companion = _clean_optional_text(extraction.companion)
    return extraction.model_copy(
        update={
            "purpose": purpose,
            "companion": companion,
            "satisfaction": Satisfaction(extraction.satisfaction),
        }
    )


def _clean_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.split())
    return cleaned or None

