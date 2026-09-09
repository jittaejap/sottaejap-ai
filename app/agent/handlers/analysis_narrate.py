"""ANALYSIS_NARRATE — '나만의 특징' 한 문장을 만든다 (05 §3 · FR-11-03).

`GET /analysis`가 화면에 보여줄 `highlight`를 그 자리에서 만들기 위해 부르는
Task다(05 §2). `state.by_verdict[]` · `by_category[]`만으로 문장을 만들고
별도 Tool 호출은 없다 — `ctx.generate()`가 `structured_state`를 프롬프트에
이미 실어 보낸다(`app/agent/prompt.py`).

프롬프트 지시만으로는 근거 밖 숫자를 100% 못 막는다(NFR-02) — 그래서 생성된
문장의 숫자를 `state`에 실제로 있는 값과 대조하는 가드레일을 코드로 한 번 더
건다. 하나라도 근거에 없으면 LLM 문장을 버리고 `app/ai/fallback.py`의
결정론적 폴백으로 바꾼다. 이때 `fallback=True`를 세우는 건 LLM 장애가 아니라
"정상 응답을 검증에서 버렸다"는 상태 표시다 — Spring이 이 플래그를 보고
자기 템플릿으로 갈음한다(E-75 · 06 R19).
"""

import re

from app.agent.handlers.base import HandlerContext
from app.ai.fallback import fallback_reply
from app.schemas.chat import ChatResponse
from app.schemas.common import TaskType

INSTRUCTION = (
    "아래 집계 데이터만 근거로 '나만의 특징'을 한 문장으로 요약하세요. "
    "데이터에 없는 숫자나 판단을 지어내지 마세요. 수치는 데이터에 있는 값 "
    "그대로 씁니다.\n"
    # share의 분모는 월 예산이다(05 §2 · E-73). 명시 안 하면 모델이 "전체
    # 소비 대비"로 바꿔 말하는 실측 오류가 있었다 — 분모를 문장으로 못박는다.
    "share는 그 달 소비액을 월 예산으로 나눈 비율입니다. '전체 소비의 몇 %'처럼 "
    "다른 분모로 바꿔 말하지 마세요.\n"
    "verdict는 SUSTAIN이면 '지켜도 좋은 소비', ADJUST면 '바꿔볼 소비'입니다."
)

# 소수점을 한 덩어리로 잡는다. "3.6%"를 "3"·"6"으로 쪼개면 둘 다 한 자리라
# 아래 서수 예외에 걸려 검사 없이 통과한다 — 지어낸 "9.9%"가 그 구멍으로 샜다(E-79).
_NUMBER_PATTERN = re.compile(r"\d[\d,]*(?:\.\d+)?")
_YEAR_MONTH_PATTERN = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")

# 근거 값과 문장 속 값을 견줄 때 허용하는 오차.
_TOLERANCE = 0.05


async def handle(ctx: HandlerContext) -> ChatResponse:
    """집계 근거로 한 문장을 만들고, 근거 밖 숫자가 있으면 폴백으로 바꾼다."""

    sentence = await ctx.generate(INSTRUCTION)
    state = ctx.state.structured_state

    if _has_unverified_number(
        sentence,
        _known_numbers(state),
        known_percentages=_known_percentages(state),
    ):
        return ChatResponse(
            reply=fallback_reply(TaskType.ANALYSIS_NARRATE, state),
            fallback=True,
        )

    return ChatResponse(reply=sentence)


def _known_numbers(state: dict) -> set[float]:
    """기준 연월과 집계에 실제로 있는 수치만 허용 목록으로 만든다.

    비율(`share`)은 문장에서 퍼센트로 나오므로 100배 한 값도 넣는다. 소수
    그대로(`3.6`)와 반올림한 정수(`4`) 둘 다 자연스러운 표기라 함께 허용한다.
    `analysis_year_month`는 정상 `YYYY-MM` 형식일 때만 연도와 월을 허용한다.
    """

    numbers: set[float] = set()
    year_month = state.get("analysis_year_month")
    if isinstance(year_month, str) and (
        year_month_match := _YEAR_MONTH_PATTERN.fullmatch(year_month)
    ):
        numbers.update(float(part) for part in year_month_match.groups())

    for group in ("by_verdict", "by_category"):
        items = state.get(group)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            for key, value in item.items():
                if isinstance(value, bool) or not isinstance(value, int | float):
                    continue
                numbers.add(float(value))
                if key == "share" and 0 <= value <= 1:
                    numbers.update(_percent_forms(value))
    return numbers


def _known_percentages(state: dict) -> set[float]:
    """`share`에서 실제로 표현 가능한 퍼센트 값만 모은다."""

    percentages: set[float] = set()
    for group in ("by_verdict", "by_category"):
        items = state.get(group)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            share = item.get("share")
            if isinstance(share, bool) or not isinstance(share, int | float):
                continue
            if 0 <= share <= 1:
                percentages.update(_percent_forms(share))
    return percentages


def _percent_forms(share: int | float) -> set[float]:
    percent = share * 100
    return {float(percent), float(round(percent))}


def _has_unverified_number(
    sentence: str, known: set[float], *, known_percentages: set[float]
) -> bool:
    """문장에 등장한 숫자 중 근거에 없는 게 있으면 True다.

    한 자리 정수는 서수 표현에 섞일 수 있어 건너뛰되, 바로 뒤에 `%`가 붙으면
    비율이므로 반드시 검사한다. 퍼센트는 연·월 같은 일반 숫자와 값이 같아도
    통과하지 않도록 `share`에서 만든 별도 집합과 견준다(E-79 · E-101).
    """

    for match in _NUMBER_PATTERN.finditer(sentence):
        text = match.group().replace(",", "")
        is_percent = match.end() < len(sentence) and sentence[match.end()] == "%"
        if "." not in text and len(text) < 2 and not is_percent:
            continue
        value = float(text)
        candidates = known_percentages if is_percent else known
        if not any(abs(value - candidate) < _TOLERANCE for candidate in candidates):
            return True
    return False
