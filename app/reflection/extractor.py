"""자연어에서 회고 후보 값을 추출한다 (02 FR-04-04·05 · E-20).

LLM을 **1회만** 부르고 그 한 응답에서 후보값과 공감 한마디를 함께 받는다. 값과 문장을
따로 부르면 NFR-04의 6초 예산이 두 배가 되기 때문이다.

추출 결과는 확정 사실이 아니라 사용자가 확인할 후보다. 정규화(`normalizer`)와 검증
(`validator`)은 이미 있는 것을 호출만 하고 여기서 다시 만들지 않는다.

`LLMUnavailableError`·`LLMNotConfiguredError`를 잡지 않는다 — 폴백 전환은
`SingleAgent.run` 한 곳이 담당한다 (FR-04-15 · E-38).
"""

import json
from typing import Any, NamedTuple

from app.core.llm import LLMClient
from app.reflection.normalizer import normalize_companion, normalize_purpose
from app.reflection.schemas import Companion, Purpose, ReflectionExtraction, Satisfaction
from app.reflection.validator import validate

_EXTRACTABLE_SATISFACTION = (Satisfaction.HIGH, Satisfaction.LOW)

_SYSTEM_PROMPT = """당신은 소비 회고 발화에서 확인되는 값만 뽑아내는 추출기입니다.
사용자 발화를 읽고 아래 키를 가진 JSON object 하나만 출력합니다.

- purpose: {purposes} 중 하나. 확인되지 않으면 null
- companion: {companions} 중 하나. 확인되지 않으면 null
- satisfaction: "HIGH" 또는 "LOW". 확인되지 않으면 "UNKNOWN"
- repeat_intention: 다음에도 비슷한 소비를 할 의향이 있으면 true, 없으면 false. 확인되지 않으면 null
- ack: 사용자의 말에 공감하는 한 문장

값 규칙:
- 발화에 드러나지 않은 값은 추론하지 말고 null로 둡니다. 애매하면 null입니다.
- "기타"는 사용자가 표준 태그 어디에도 없는 목적·동행인을 분명히 말했을 때만 씁니다.
  모르겠다는 뜻으로 "기타"를 쓰지 않습니다.
- purpose와 companion은 위 목록의 한국어 문자열을 그대로 씁니다. 다른 표현을 만들지 않습니다.

ack 규칙:
- 해요체 한 문장입니다. 반말, 격식체, 이모지를 쓰지 않습니다.
- 사용자의 소비를 부정적으로 단정하거나 후회를 유도하지 않습니다.
- 질문하지 않습니다. 다음 질문은 다른 곳에서 붙입니다.
"""

_LAST_QUESTION_RULE = """직전에 시스템이 한 질문: {question}
이 질문은 사용자의 짧은 답이 어느 항목에 대한 것인지 판단할 때만 참고합니다.
질문 문장에 등장한 값은 사용자가 직접 말한 것이 아니므로 추출하지 않습니다.
"""


class ReflectionTurn(NamedTuple):
    """한 발화에서 얻은 회고 후보와 공감 문장.

    ``ack``는 ``reply``를 만들 때 쓰는 내부 값이라 ``ReflectionExtraction``에 넣지
    않는다. 그 DTO는 05 API 명세서 §3의 ``tool_results[].data`` 계약이다.
    """

    extraction: ReflectionExtraction
    ack: str


class ReflectionExtractor:
    """발화 1개를 표준 태그 후보로 바꾸는 추출기."""

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self._llm_client = llm_client or LLMClient()

    async def extract(self, text: str, last_question: str = "") -> ReflectionTurn:
        """텍스트에서 후보 값과 공감 한마디를 한 번에 추출한다."""

        if not text.strip():
            raise ValueError("회고 텍스트는 비어 있을 수 없습니다.")

        payload = await self._llm_client.generate_json(
            _build_prompt(last_question),
            text,
        )
        return ReflectionTurn(
            extraction=validate(_to_extraction(payload)),
            ack=_one_line(payload.get("ack")),
        )


def _build_prompt(last_question: str) -> str:
    """표준 태그 목록과 직전 질문 해석 규칙을 붙인 추출 프롬프트."""

    prompt = _SYSTEM_PROMPT.format(
        purposes=_tag_list(Purpose),
        companions=_tag_list(Companion),
    )
    question = _one_line(last_question)
    if question:
        rule = _LAST_QUESTION_RULE.format(
            question=json.dumps(question, ensure_ascii=False)
        )
        return f"{prompt}\n{rule}"
    return prompt


def _tag_list(tag_type: type[Purpose] | type[Companion]) -> str:
    return ", ".join(f'"{tag.value}"' for tag in tag_type)


def _to_extraction(payload: dict[str, Any]) -> ReflectionExtraction:
    """LLM 출력을 표준 태그 DTO로 좁힌다. 목록 밖 값은 None이 된다 (E-20)."""

    return ReflectionExtraction(
        purpose=normalize_purpose(_optional_text(payload.get("purpose"))),
        companion=normalize_companion(_optional_text(payload.get("companion"))),
        satisfaction=_satisfaction(payload.get("satisfaction")),
        repeat_intention=_optional_bool(payload.get("repeat_intention")),
    )


def _satisfaction(value: Any) -> Satisfaction:
    """HIGH·LOW만 값으로 받고 나머지는 UNKNOWN이다 (E-23 — 3택)."""

    for satisfaction in _EXTRACTABLE_SATISFACTION:
        if value == satisfaction.value:
            return satisfaction
    return Satisfaction.UNKNOWN


def _optional_bool(value: Any) -> bool | None:
    """참·거짓만 값으로 받는다. "true" 같은 문자열은 미확정으로 둔다."""

    return value if isinstance(value, bool) else None


def _optional_text(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _one_line(value: Any) -> str:
    """줄바꿈이 그대로 reply·프롬프트에 섞이지 않게 한 줄로 만든다."""

    return " ".join(value.split()) if isinstance(value, str) else ""
