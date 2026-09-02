"""회고 자유입력을 서비스 표준 태그로 정규화한다.

새로운 사실을 추론하지 않고 공백 같은 표현 차이만 다룬다. 표준 태그와 일치하지 않는
문자열은 None으로 돌려 사용자 확인 단계로 넘긴다 (E-20 — 자유 문자열 저장 금지).
"""

from app.reflection.schemas import Companion, Purpose


def normalize_purpose(raw: str | None) -> Purpose | None:
    """자유입력을 목적 표준 태그로 바꾼다. 일치하지 않으면 None."""

    return _match(Purpose, raw)


def normalize_companion(raw: str | None) -> Companion | None:
    """자유입력을 동행인 표준 태그로 바꾼다. 일치하지 않으면 None."""

    return _match(Companion, raw)


def _match(tag_type: type[Purpose] | type[Companion], raw: str | None):
    if raw is None:
        return None
    cleaned = "".join(raw.split())
    for tag in tag_type:
        if cleaned == "".join(tag.value.split()):
            return tag
    return None
