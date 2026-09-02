"""자연어에서 회고 후보 값을 추출하는 인터페이스.

현재는 임의 추론 없이 미확정 결과를 반환하며 Structured Output 연동은 TODO다.
"""

from app.reflection.schemas import ReflectionExtraction


class ReflectionExtractor:
    """자연어 회고 추출기의 최소 구현."""

    async def extract(self, text: str) -> ReflectionExtraction:
        """텍스트에서 후보 값을 추출한다."""

        if not text.strip():
            raise ValueError("회고 텍스트는 비어 있을 수 없습니다.")

        # TODO: LLM Structured Output으로 명시적으로 확인되는 값만 추출한다.
        return ReflectionExtraction(
            uncertain_fields=[
                "purpose",
                "companion",
                "satisfaction",
                "repeat_intention",
            ]
        )

